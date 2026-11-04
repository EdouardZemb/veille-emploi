"""L'image et le deploiement : ce que la cible `serveur` du modele lance.

Le `compose.yml` du modele (gere) et `compose.projet.yml` (au projet) passent
des variables au conteneur ; le `Dockerfile` en pose d'autres. Une variable
`VEILLE_*` ou `FT_*` inconnue arrete la console au demarrage (invariant 6) :
chacune doit etre connue de `config.py`. Le `.dockerignore` garde hors de
l'image les secrets et les donnees d'Edouard, mais pas ce que la console lit
sous `/app` (le jeu factice du staging, les criteres, les gabarits).

L'image elle-meme se construit et se lance en CI (job `image`) : ces tests en
lisent les fichiers, pour qu'une erreur se voie avant.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from tests.aide_session import connecter
from veille import affinement, cli, config, db, notifications
from veille.config import VARIABLES_CONNUES

RACINE = Path(__file__).resolve().parent.parent
DEPLOIEMENT = RACINE / "deploiement"
PREFIXES = ("VEILLE_", "FT_")


def _port_app() -> int:
    """Le port de l'app, tel que le modele l'a rendu (`.copier-answers.yml`)."""
    reponses = yaml.safe_load((RACINE / ".copier-answers.yml").read_text(encoding="utf-8"))
    return int(reponses["port_app"])


# --------------------------------------------------------------------------
# Les fichiers compose
# --------------------------------------------------------------------------


def _environnement_app(fichier: Path) -> dict[str, str | None]:
    """Les variables que ce fichier compose passe au service `app`."""
    document = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
    service = (document.get("services") or {}).get("app") or {}
    brut = service.get("environment") or {}
    if isinstance(brut, list):  # la forme `- CLE=valeur`
        return {e.partition("=")[0]: e.partition("=")[2] or None for e in brut}
    return {cle: (None if v is None else str(v)) for cle, v in brut.items()}


def _cles(fichier: Path) -> list[str]:
    """Les cles d'un `.cles` : une par ligne, commentaires et lignes vides ignores."""
    lignes = (l.strip() for l in fichier.read_text(encoding="utf-8").splitlines())
    return [l for l in lignes if l and not l.startswith("#")]


def test_le_compose_ne_passe_que_des_variables_connues():
    passees = {
        **_environnement_app(DEPLOIEMENT / "compose.yml"),
        **_environnement_app(DEPLOIEMENT / "compose.projet.yml"),
    }
    # le compose du modele est bien lu : sans cela, le test passerait a vide
    assert {"VEILLE_EMPLOI_ENV", "VEILLE_EMPLOI_VERSION", "VEILLE_EMPLOI_URL_PUBLIQUE"} <= set(passees)
    inconnues = sorted(n for n in passees if n.startswith(PREFIXES) and n not in VARIABLES_CONNUES)
    assert inconnues == [], f"variables passees au conteneur, inconnues de config.py : {inconnues}"


def test_les_secrets_du_compose_sont_ceux_de_la_prod():
    """Chaque secret que `compose.projet.yml` lit est nomme dans `prod.cles`, et
    chaque secret de l'app nomme dans `prod.cles` est passe a la console."""
    lus: set[str] = set()
    for valeur in _environnement_app(DEPLOIEMENT / "compose.projet.yml").values():
        lus |= set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", valeur or ""))
    de_l_app = {c for c in _cles(DEPLOIEMENT / "secrets" / "prod.cles") if not c.startswith("HC_")}
    assert lus, "compose.projet.yml ne lit aucun secret"
    assert lus == de_l_app


def test_le_staging_demarre_sans_les_secrets_de_l_app():
    """Le staging n'a que `HC_SONDE` : chaque secret lu par `compose.projet.yml`
    a une valeur par defaut (`${NOM:-}`), sinon compose refuserait de lancer."""
    assert _cles(DEPLOIEMENT / "secrets" / "staging.cles") == ["HC_SONDE"]
    for nom, valeur in _environnement_app(DEPLOIEMENT / "compose.projet.yml").items():
        for reference in re.findall(r"\$\{[^}]*\}", valeur or ""):
            assert re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-[^}]*\}", reference), (nom, reference)


def test_les_adresses_de_supervision_ne_vont_pas_a_la_console():
    """Les `HC_*` servent aux scripts du serveur ; la console n'en a que faire."""
    for fichier in ("compose.yml", "compose.projet.yml"):
        for nom, valeur in _environnement_app(DEPLOIEMENT / fichier).items():
            assert not nom.startswith("HC_"), (fichier, nom)
            assert "HC_" not in (valeur or ""), (fichier, nom)


# --------------------------------------------------------------------------
# Le Dockerfile
# --------------------------------------------------------------------------


def _instructions() -> list[tuple[str, str]]:
    """(INSTRUCTION, arguments) de chaque instruction du Dockerfile, lignes jointes."""
    instructions: list[tuple[str, str]] = []
    courante = ""
    for brut in (RACINE / "Dockerfile").read_text(encoding="utf-8").splitlines():
        ligne = brut.strip()
        if not courante and (not ligne or ligne.startswith("#")):
            continue
        if courante and ligne.startswith("#"):
            continue  # un commentaire au milieu d'une instruction continuee
        if ligne.endswith("\\"):
            courante += ligne[:-1] + " "
            continue
        courante += ligne
        mot, _, reste = courante.partition(" ")
        instructions.append((mot.upper(), reste.strip()))
        courante = ""
    return instructions


def _env_de_l_image() -> dict[str, str]:
    variables: dict[str, str] = {}
    for mot, reste in _instructions():
        if mot != "ENV":
            continue
        jetons = shlex.split(reste)
        if jetons and "=" not in jetons[0]:  # la forme ancienne : ENV CLE valeur
            variables[jetons[0]] = " ".join(jetons[1:])
            continue
        for jeton in jetons:
            cle, _, valeur = jeton.partition("=")
            variables[cle] = valeur
    return variables


def test_l_image_ne_pose_que_des_variables_connues():
    posees = _env_de_l_image()
    assert "VEILLE_DB" in posees, "aucun ENV lu dans le Dockerfile"
    inconnues = sorted(n for n in posees if n.startswith(PREFIXES) and n not in VARIABLES_CONNUES)
    assert inconnues == [], f"variables posees par l'image, inconnues de config.py : {inconnues}"


def test_l_image_range_tout_dans_donnees():
    """M-0003 : tout l'etat dans /donnees ; /tmp sert de HOME et de cache, la
    racine est en lecture seule. Les heures de collecte sont celles de Paris."""
    posees = _env_de_l_image()
    attendues = {
        "VEILLE_DB": "/donnees/veille.sqlite3",
        "VEILLE_DOSSIERS": "/donnees/dossiers",
        "VEILLE_KIT": "/donnees/kit",
        "VEILLE_VAPID": "/donnees/vapid.json",
        "TZ": "Europe/Paris",
        "HOME": "/tmp",
        "XDG_CACHE_HOME": "/tmp/cache",
    }
    assert {n: posees.get(n) for n in attendues} == attendues
    # la version vient de l'environnement, jamais de l'image (M-0003, section 2)
    assert "VEILLE_EMPLOI_VERSION" not in posees


def test_l_image_tourne_en_uid_1000_et_porte_sa_revision():
    instructions = _instructions()
    users = [reste for mot, reste in instructions if mot == "USER"]
    assert users and users[-1] == "1000:1000"
    assert ("ARG", "REVISION") in instructions
    assert _env_de_l_image().get("REVISION") == "$REVISION"
    labels = " ".join(reste for mot, reste in instructions if mot == "LABEL")
    assert "org.opencontainers.image.revision=$REVISION" in labels


def test_l_image_se_lance_par_veille_servir():
    """La commande par defaut, en forme exec et sans ENTRYPOINT : le serveur lance
    `docker run <image> veille instantane verifier /donnees` tel quel (M-0003)."""
    instructions = _instructions()
    assert not [reste for mot, reste in instructions if mot == "ENTRYPOINT"]
    cmds = [reste for mot, reste in instructions if mot == "CMD"]
    assert len(cmds) == 1
    commande = json.loads(cmds[0])  # la forme exec ; la forme shell ne se lit pas en JSON
    assert commande == ["veille", "servir", "--hote", "0.0.0.0", "--port", str(_port_app())]
    assert "--rechargement" not in commande
    assert [reste for mot, reste in instructions if mot == "EXPOSE"] == [str(_port_app())]


def test_la_sante_de_l_image_vise_la_route_du_modele():
    sondes = [reste for mot, reste in _instructions() if mot == "HEALTHCHECK"]
    assert len(sondes) == 1
    options, _, commande = sondes[0].partition("CMD")
    assert json.loads(commande)[:2] == ["python", "-c"]
    assert f"http://127.0.0.1:{_port_app()}/sante" in commande


def _servir_sans_serveur(journal: list[str]) -> subprocess.CompletedProcess[str]:
    """La commande de l'image, jouee par la CLI avec la configuration de journal
    d'uvicorn (`uvicorn.Config`), mais sans serveur ; puis `journal`, des lignes
    de Python. Un sous-processus : sous pytest, le journal racine a deja ses
    gestionnaires et `logging.basicConfig` ne ferait rien."""
    commande = json.loads([r for m, r in _instructions() if m == "CMD"][0])
    script = "\n".join([
        "import json, logging, sys, uvicorn",
        "from veille import cli",
        "def lancer(app, **options):",
        "    uvicorn.Config(app, **options)",
        "    print('OPTIONS ' + json.dumps({'app': app, **options}), flush=True)",
        *(f"    {ligne}" for ligne in journal),
        "uvicorn.run = lancer",
        f"sys.exit(cli.principal({commande[1:]!r}))",
    ])
    env = {**os.environ, "PYTHONPATH": str(RACINE / "src")}
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(RACINE), timeout=120,
    )
    assert r.returncode == 0, r.stderr
    return r


def test_veille_servir_un_seul_processus_et_le_journal_info():
    """Un seul processus (le verrou du planificateur ne couvre que le sien), et
    les lignes INFO de `veille.*` vont sur stderr, donc dans `docker logs` ; pas
    les etapes de WeasyPrint (huit lignes par PDF)."""
    r = _servir_sans_serveur([
        "logging.getLogger('veille.essai').info('une ligne de journal')",
        "logging.getLogger('weasyprint.progress').info('Step 6 - Creating PDF')",
        "logging.getLogger('weasyprint').warning('une regle CSS ignoree')",
    ])
    lignes = [l for l in r.stdout.splitlines() if l.startswith("OPTIONS ")]
    options = json.loads(lignes[0].removeprefix("OPTIONS "))
    assert options == {"app": "veille.app:app", "host": "0.0.0.0", "port": _port_app(),
                       "reload": False}
    assert "INFO    veille.essai | une ligne de journal" in r.stderr
    assert "Creating PDF" not in r.stderr
    assert "WARNING weasyprint | une regle CSS ignoree" in r.stderr


def test_veille_servir_tait_les_sondes_de_sante_reussies():
    """Le HEALTHCHECK de l'image, le deploiement et la sonde interrogent /sante
    sans cesse : pres de 3 000 lignes par jour dans `docker logs`. Seuls les
    `GET /sante` reussis se taisent ; une sante en echec et toute autre requete
    restent. Le journal d'acces d'uvicorn va sur stdout."""
    r = _servir_sans_serveur([
        "def acces(methode, chemin, statut):",
        "    logging.getLogger('uvicorn.access').info(",
        "        '%s - \"%s %s HTTP/%s\" %d', '127.0.0.1:1', methode, chemin, '1.1', statut)",
        "acces('GET', '/sante', 200)",
        "acces('GET', '/sante', 503)",
        "acces('POST', '/sante', 200)",
        "acces('GET', '/api/offres', 200)",
    ])
    assert '"GET /sante HTTP/1.1" 200' not in r.stdout
    assert '"GET /sante HTTP/1.1" 503' in r.stdout
    assert '"POST /sante HTTP/1.1" 200' in r.stdout
    assert '"GET /api/offres HTTP/1.1" 200' in r.stdout


# --------------------------------------------------------------------------
# Le .dockerignore
# --------------------------------------------------------------------------


def _regex_docker(motif: str) -> re.Pattern[str]:
    """Un motif de `.dockerignore` : `**` traverse les dossiers, `*` et `?` non."""
    morceaux, i = [], 0
    while i < len(motif):
        if motif.startswith("**/", i):
            morceaux.append("(?:.*/)?")
            i += 3
        elif motif.startswith("**", i):
            morceaux.append(".*")
            i += 2
        elif motif[i] == "*":
            morceaux.append("[^/]*")
            i += 1
        elif motif[i] == "?":
            morceaux.append("[^/]")
            i += 1
        else:
            morceaux.append(re.escape(motif[i]))
            i += 1
    return re.compile("".join(morceaux))


def _motifs() -> list[tuple[bool, re.Pattern[str]]]:
    motifs = []
    for brut in (RACINE / ".dockerignore").read_text(encoding="utf-8").splitlines():
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue
        exception = ligne.startswith("!")
        ligne = ligne.lstrip("!").strip()
        ligne = ligne.removeprefix("./").strip("/")
        motifs.append((exception, _regex_docker(ligne)))
    return motifs


def _exclu(chemin: str, motifs: list[tuple[bool, re.Pattern[str]]]) -> bool:
    """Comme Docker : le dernier motif qui vise le chemin, ou l'un de ses dossiers, decide."""
    parties = chemin.split("/")
    prefixes = ["/".join(parties[:n]) for n in range(1, len(parties) + 1)]
    exclu = False
    for exception, motif in motifs:
        if any(motif.fullmatch(p) for p in prefixes):
            exclu = not exception
    return exclu


def _fichiers_suivis(*dossiers: str) -> list[str]:
    """Les fichiers versionnes de ces dossiers : ceux de la copie que construit la
    CI. Un fichier local et ignore (un PDF laisse dans gabarits/ sur le serveur)
    n'entre dans aucune image publiee. Sans git, tout le dossier."""
    try:
        r = subprocess.run(["git", "ls-files", "-z", "--", *dossiers], cwd=str(RACINE),
                           capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        r = None
    if r is not None and r.returncode == 0 and r.stdout:
        return sorted(n for n in r.stdout.decode("utf-8").split("\0") if n)
    return sorted(
        f.relative_to(RACINE).as_posix()
        for d in dossiers for f in (RACINE / d).rglob("*")
        if f.is_file() and "__pycache__" not in f.parts
    )


def test_l_image_ignore_les_fichiers_prives():
    motifs = _motifs()
    prives = [
        ".git", ".git/config", ".venv", ".venv/Scripts/python.exe",
        "donnees", "donnees/veille.sqlite3", "donnees/kit/cv.pdf",
        "config/.env", "config/auth.json", "config/vapid.json",
        ".githooks", ".githooks/pre-commit", "scripts/modele", "scripts/modele/garde_claude.py",
        ".superpowers", ".superpowers/sdd/progress.md", ".claude", ".claude/settings.json",
        # ce qu'un poste laisse trainer
        "veille.sqlite3", "src/veille/__pycache__/app.cpython-313.pyc",
        "src/veille_emploi.egg-info/PKG-INFO", "deploiement/secrets/prod.env.enc",
    ]
    gardes = [c for c in prives if not _exclu(c, motifs)]
    assert gardes == [], f"entreraient dans l'image : {gardes}"


def test_l_image_garde_ce_que_la_console_lit():
    """`config.RACINE` vaut /app : la console y lit le jeu factice du staging, l'exemple
    (sa configuration par defaut) et son propre code. Le modele du fichier
    d'environnement, `exemple/.env.exemple`, se recopie a la main : la console ne le lit
    pas, et aucun fichier d'environnement n'entre dans une image."""
    motifs = _motifs()
    lus = ["pyproject.toml"]
    lus += [c for c in _fichiers_suivis("exemple", "factice", "src/veille")
            if c != "exemple/.env.exemple"]
    assert any(c.startswith("factice/") for c in lus)
    assert any(c.startswith("exemple/") for c in lus)
    exclus = [c for c in lus if _exclu(c, motifs)]
    assert exclus == [], f"manqueraient dans l'image : {exclus}"


def test_l_image_n_embarque_aucun_dossier_d_instance():
    """Le dépôt de code ne porte pas l'instance : elle vit au dépôt de données et se monte sur
    /config. Si un clone en reçoit une copie, aucune image ne l'embarque."""
    assert _fichiers_suivis("instance", "config", "contenu") == []
    motifs = _motifs()
    candidats = ["instance/config/criteres.yaml", "instance/docs/LIMITES.md",
                 "config/criteres.yaml", "config/sources.yaml", "config/gabarits/lettre.md",
                 "config/empreintes-kit.json", "contenu/README.md",
                 "gabarits/lettre.md", "tests/empreintes-kit.json"]
    gardes = [c for c in candidats if not _exclu(c, motifs)]
    assert gardes == [], f"entreraient dans l'image : {gardes}"


# --------------------------------------------------------------------------
# Les commandes de l'instantane (deploiement/projet.env)
# --------------------------------------------------------------------------


def _projet_env() -> dict[str, list[str]]:
    """`CLE=mots` : lu, jamais source, comme le fait lib.sh."""
    reglages: dict[str, list[str]] = {}
    for brut in (DEPLOIEMENT / "projet.env").read_text(encoding="utf-8").splitlines():
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue
        cle, signe, valeur = ligne.partition("=")
        assert signe and re.fullmatch(r"[A-Z][A-Z0-9_]*", cle), ligne
        assert cle not in reglages, f"{cle} declaree deux fois"
        reglages[cle] = valeur.split()
    return reglages


def test_les_commandes_de_l_instantane_sont_celles_de_la_cli(tmp_path, monkeypatch):
    """Les mots de `SAUVEGARDER` et `VERIFIER`, rejoues par la CLI : un instantane
    cree par l'un est sain pour l'autre (ce que la CI fait dans l'image)."""
    commandes = _projet_env()
    assert commandes["SAUVEGARDER"] == ["veille", "instantane", "creer"]
    assert commandes["VERIFIER"] == ["veille", "instantane", "verifier"]
    assert "REPORTER" not in commandes  # rien ne doit survivre a une restauration (ADR-0002, 7)

    donnees = tmp_path / "donnees"
    donnees.mkdir()
    monkeypatch.setattr(config, "CHEMIN_DB", donnees / "veille.sqlite3")
    monkeypatch.setattr(config, "CHEMIN_DOSSIERS", donnees / "dossiers")
    monkeypatch.setattr(config, "CHEMIN_KIT", donnees / "kit")
    monkeypatch.setattr(notifications, "CHEMIN_VAPID", donnees / "vapid.json")
    monkeypatch.setattr(db, "CHEMIN_DB", donnees / "veille.sqlite3")
    db.initialiser()

    instantane = tmp_path / "instantane"
    assert cli.principal(commandes["SAUVEGARDER"][1:] + [str(instantane)]) == 0
    assert cli.principal(commandes["VERIFIER"][1:] + [str(instantane)]) == 0
    vide = tmp_path / "vide"
    vide.mkdir()
    assert cli.principal(commandes["VERIFIER"][1:] + [str(vide)]) == 2


def test_la_commande_de_la_configuration_est_celle_de_la_cli(tmp_path):
    """`VERIFIER_CONFIG`, rejouee par la CLI comme la chaine la lance (`<mots> /config`) :
    0 sur l'exemple, 2 sur un dossier vide. Aucune commande du contenu : les gabarits
    portent l'identite, ils restent de la configuration (M-0006)."""
    commandes = _projet_env()
    assert commandes["VERIFIER_CONFIG"] == ["veille", "config", "verifier"]
    assert "VERIFIER_CONTENU" not in commandes

    assert cli.principal(commandes["VERIFIER_CONFIG"][1:] + [str(RACINE / "exemple")]) == 0
    vide = tmp_path / "vide"
    vide.mkdir()
    assert cli.principal(commandes["VERIFIER_CONFIG"][1:] + [str(vide)]) == 2


# --------------------------------------------------------------------------
# L'affinement, absent de l'image
# --------------------------------------------------------------------------


def _comme_dans_l_image(tmp_path: Path) -> dict[str, str]:
    """Ni `claude` ni Node sur le PATH, HOME vide (/tmp dans l'image), aucun jeton."""
    maison = tmp_path / "maison"
    maison.mkdir()
    chemin = tmp_path / "bin"
    chemin.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in affinement.VARIABLES_JETON}
    env.update(PATH=str(chemin), HOME=str(maison), USERPROFILE=str(maison))
    return env


def test_pas_d_affinement_sans_cli_claude(tmp_path):
    """Quel que soit le critere que lit `disponible()` : un processus neuf, dont
    les chemins sont calcules a l'import depuis un HOME vide."""
    env = {**_comme_dans_l_image(tmp_path), "PYTHONPATH": str(RACINE / "src")}
    script = (
        "import json, shutil\n"
        "from veille import affinement\n"
        "d = affinement.disponible()\n"
        "print(json.dumps({'claude': shutil.which('claude'), 'node': shutil.which('node'),\n"
        "                  'possible': d.possible, 'raison': d.raison}))\n"
    )
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        capture_output=True, text=True, encoding="utf-8", env=env,
        cwd=str(tmp_path / "maison"), timeout=120,
    )
    assert r.returncode == 0, r.stderr
    etat = json.loads(r.stdout)
    assert (etat["claude"], etat["node"]) == (None, None)
    assert etat["possible"] is False
    assert etat["raison"]


def test_l_api_dit_que_l_affinement_est_indisponible(tmp_path, monkeypatch):
    env = _comme_dans_l_image(tmp_path)
    for variable in affinement.VARIABLES_JETON:
        monkeypatch.delenv(variable, raising=False)
    for variable in ("PATH", "HOME", "USERPROFILE"):
        monkeypatch.setenv(variable, env[variable])
    maison = Path(env["HOME"])
    monkeypatch.setattr(affinement, "RACINE_SDK", maison / "sdk-agent")
    monkeypatch.setattr(affinement, "IDENTIFIANTS", maison / ".claude" / ".credentials.json")

    from veille.app import app

    db.initialiser()
    client = TestClient(app)
    connecter(client)
    r = client.get("/api/affinement")

    assert r.status_code == 200
    corps = r.json()
    assert corps["possible"] is False
    assert corps["raison"]


def test_la_ci_charge_le_jeu_factice_avant_de_publier():
    """Le rendu PDF (WeasyPrint, uid 1000, racine en lecture seule) se prouve dans
    le conteneur lance, avant la publication de l'image."""
    ci = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml")
    etapes = yaml.safe_load(ci.read_text(encoding="utf-8"))["jobs"]["image"]["steps"]
    commandes = [e.get("run", "") for e in etapes]
    rang = [i for i, c in enumerate(commandes) if "docker exec veille-emploi veille factice" in c]
    assert rang, "le job image ne lance pas `veille factice` dans le conteneur"
    publier = [i for i, e in enumerate(etapes) if "modele-image-publier" in e.get("uses", "")]
    assert publier and rang[0] < publier[0]


def test_la_ci_verifie_l_image_construite_avant_de_publier():
    """Les deux tests de `.dockerignore` lisent des listes : l'image construite, elle, se
    regarde dans le conteneur lancé. L'exemple y est, l'instance n'y est pas, et sans `/config`
    monté la santé dit qu'elle sert l'exemple, avant toute publication."""
    ci = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml")
    etapes = yaml.safe_load(ci.read_text(encoding="utf-8"))["jobs"]["image"]["steps"]
    publier = [i for i, e in enumerate(etapes) if "modele-image-publier" in e.get("uses", "")]
    assert publier, "le job image ne publie plus par modele-image-publier"
    avant = "\n".join(e.get("run", "") for e in etapes[:publier[0]])
    assert "docker exec veille-emploi test -f /app/exemple/criteres.yaml" in avant
    assert "docker exec veille-emploi test ! -e /app/instance" in avant
    assert """jq -e '.configuration == "exemple"'""" in avant
