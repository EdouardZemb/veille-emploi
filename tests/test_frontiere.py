"""La frontière entre le code et la configuration d'une instance.

Le code et les tests tournent sur l'exemple (`exemple/`). La configuration d'une
instance vit dans le dossier que désigne `VEILLE_CONFIG`, et ni le code ni les tests
ne vont la chercher par son chemin : un test qui affirme sur ses valeurs casse à
chaque réglage de l'instance, et figerait dans le dépôt de code ce qui lui est propre.
La configuration réelle vit au dépôt de données, dont la CI la vérifie, par
`veille config verifier`, contre l'image publiée de ce dépôt.

Un test nomme ce dossier, et c'est permis : `tests/test_deploiement.py` vérifie qu'il
n'entre dans aucune image. Le banc du modèle, `tests/deploiement/`, le nomme aussi : il
fabrique le sien pour la règle des paires du déploiement (M-0003, § 6).

La suite ne lit que des fixtures : aucun test ne va non plus chercher le fichier
d'environnement de la console par son chemin. `VEILLE_ENV` le désigne, et la suite
la pointe sur un fichier absent (`conftest.py`).
"""

from __future__ import annotations

import ast
import re
import subprocess

import yaml

from veille import config

RACINE = config.RACINE

# Le nom du dossier, assemblé pour que ce fichier ne se désigne pas lui-même : le
# chemin écrit en clair (barre oblique ou inversée), ou une jonction de pathlib
# (`… / "…"` ou `"…" / …`).
_NOM = "instance"
_CITE = r"[\"']" + re.escape(_NOM) + r"[\"']"
CHEMIN_DE_L_INSTANCE = re.compile(
    re.escape(_NOM) + r"[/\\]" + "|" + _CITE + r"\s*/" + "|" + r"/\s*" + _CITE
)

# Ceux qui ont le droit de nommer le dossier.
INSTANCE_TOLERES = {
    # il vérifie que le dossier n'entre dans aucune image
    "tests/test_deploiement.py",
}

# Les dossiers dont aucun fichier n'est examiné.
INSTANCE_TOLERES_DOSSIERS = (
    # le banc des scripts de déploiement, géré par le modèle (docs/modele/methode.md) : la
    # règle des paires (M-0003, § 6) nomme le dossier, que le banc pose dans des clones
    # factices ; il ne lit jamais celui du dépôt
    "tests/deploiement/",
)


def _suivis(*dossiers: str) -> list[str]:
    """Les fichiers versionnés de ces dossiers ; sans git, tout ce qu'ils contiennent."""
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


def _qui_nomment_l_instance(fichiers: list[str]) -> list[str]:
    """Un fichier Python se lit par son arbre (`_construit_l_instance`). Ailleurs,
    toute ligne qui porte le chemin compte, commentaire compris."""
    trouves = []
    for nom in fichiers:
        chemin = RACINE / nom
        if (nom in INSTANCE_TOLERES or nom.startswith(INSTANCE_TOLERES_DOSSIERS)
                or not chemin.is_file()):
            continue
        texte = chemin.read_bytes().decode("utf-8", errors="replace")
        if nom.endswith(".py"):
            trouves += [f"{nom}:{n}" for n in _construit_l_instance(texte)]
            continue
        for numero, ligne in enumerate(texte.splitlines(), start=1):
            if CHEMIN_DE_L_INSTANCE.search(ligne):
                trouves.append(f"{nom}:{numero}")
    return trouves


# Le fichier d'environnement de la console, `config` / `.env`, écrit d'un bloc (barre
# oblique ou inversée).
CHEMIN_DU_ENV = re.compile(r"config[/\\]+\.env(?![\w.])")

# Ceux qui le nomment sans le lire : ils vérifient un texte qui le cite.
ENV_TOLERES = {
    # le message d'indisponibilité de l'affinement dit où poser la variable
    "tests/test_affinement.py",
    # le fichier est exclu de l'image
    "tests/test_deploiement.py",
}


def _chaine(noeud) -> bool:
    return isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)


def _finit_par_config(noeud) -> bool:
    if _chaine(noeud):
        return noeud.value.rstrip("/\\").endswith("config")
    if isinstance(noeud, ast.BinOp) and isinstance(noeud.op, ast.Div):
        return _finit_par_config(noeud.right)
    return False


def _docstrings(arbre) -> set[int]:
    """Les chaînes posées seules, en instruction : docstrings et commentaires en chaîne."""
    return {id(n.value) for n in ast.walk(arbre) if isinstance(n, ast.Expr) and _chaine(n.value)}


def _est_l_instance(noeud) -> bool:
    return _chaine(noeud) and noeud.value.strip("/\\") == _NOM


# Les appels qui joignent un chemin : les classes de pathlib, `.joinpath(…)` et
# `os.path.join(…)`.
_JOINTURES = frozenset({"Path", "PurePath", "PosixPath", "WindowsPath", "PurePosixPath",
                        "PureWindowsPath", "joinpath", "join"})


def _nom_appele(fonction) -> str:
    if isinstance(fonction, ast.Name):
        return fonction.id
    if isinstance(fonction, ast.Attribute):
        return fonction.attr
    return ""


def _construit_l_instance(source: str) -> list[int]:
    """Les lignes où un code Python construit un chemin vers le dossier de l'instance.

    Une jonction pathlib (`… / "…"` ou `"…" / …`), un `Path(…, "…")`, un
    `.joinpath("…")`, un `os.path.join(…, "…")`, ou une chaîne qui porte le chemin.
    Un commentaire ou une docstring qui le cite n'en est pas une, ni un appel qui
    passe le nom sans joindre de chemin (`_fichiers_suivis("…")`).
    """
    arbre = ast.parse(source)
    docstrings = _docstrings(arbre)
    lignes = set()
    for n in ast.walk(arbre):
        if (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
                and (_est_l_instance(n.left) or _est_l_instance(n.right))):
            lignes.add(n.lineno)
        elif (isinstance(n, ast.Call) and _nom_appele(n.func) in _JOINTURES
              and any(_est_l_instance(a) for a in n.args)):
            lignes.add(n.lineno)
        elif _chaine(n) and id(n) not in docstrings and CHEMIN_DE_L_INSTANCE.search(n.value):
            lignes.add(n.lineno)
    return sorted(lignes)


def _construit_le_env(source: str) -> list[int]:
    """Les lignes où un code Python construit le chemin `config` / `.env`.

    Une jonction pathlib, un `os.path.join(…, "config", ".env")`, ou une chaîne qui
    porte le chemin. Un commentaire ou une docstring qui le cite n'en est pas une.
    """
    arbre = ast.parse(source)
    docstrings = _docstrings(arbre)
    lignes = set()
    for n in ast.walk(arbre):
        if (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div) and _chaine(n.right)
                and n.right.value == ".env" and _finit_par_config(n.left)):
            lignes.add(n.lineno)
        elif isinstance(n, ast.Call):
            args = [a.value if _chaine(a) else None for a in n.args]
            if any(a == "config" and b == ".env" for a, b in zip(args, args[1:])):
                lignes.add(n.lineno)
        elif _chaine(n) and id(n) not in docstrings and CHEMIN_DU_ENV.search(n.value):
            lignes.add(n.lineno)
    return sorted(lignes)


def _qui_construisent_le_env(fichiers: list[str]) -> list[str]:
    trouves = []
    for nom in fichiers:
        chemin = RACINE / nom
        if nom in ENV_TOLERES or not chemin.is_file():
            continue
        texte = chemin.read_bytes().decode("utf-8", errors="replace")
        if nom.endswith(".py"):
            trouves += [f"{nom}:{n}" for n in _construit_le_env(texte)]
            continue
        for numero, ligne in enumerate(texte.splitlines(), start=1):
            if not ligne.lstrip().startswith("#") and CHEMIN_DU_ENV.search(ligne):
                trouves.append(f"{nom}:{numero}")
    return trouves


def test_le_garde_du_env_reconnait_ses_formes():
    """Il voit les constructions qu'on écrit vraiment, et pas une simple citation.

    Le chemin d'un bloc est assemblé, pour que ce fichier ne se désigne pas lui-même."""
    d_un_bloc = "config" + "/" + ".env"
    inverse = "config" + "\\\\" + ".env"
    for source in ('p = RACINE / "config" / ".env"\n',
                   'p = Path(__file__).parent.parent / "config" / ".env"\n',
                   f'p = Path("{d_un_bloc}")\n',
                   f'p = RACINE / "{inverse}"\n',
                   'p = os.path.join(r, "config", ".env")\n'):
        assert _construit_le_env(source) == [1], source
    for source in (f'"""Il lit `{d_un_bloc}`."""\n',
                   f'# il lisait {d_un_bloc}\nx = 1\n',
                   'x = ".env.exemple"\n',
                   f'x = "{d_un_bloc}.exemple"\n',
                   'p = RACINE / "config" / ".env.exemple"\n'):
        assert _construit_le_env(source) == [], source


def test_les_tests_ne_lisent_pas_le_env_de_la_console():
    """Le critère 6 de #22 : la suite ne lit que des fixtures. Le kit réel, les
    secrets et les chemins du serveur passent par `VEILLE_ENV`, que la suite pointe
    sur un fichier absent."""
    fichiers = _suivis("tests", "tests_navigateur")
    assert fichiers, "aucun fichier suivi sous tests/"
    trouves = _qui_construisent_le_env(fichiers)
    assert trouves == [], (
        "un test construit le chemin du fichier d'environnement de la console :\n"
        + "\n".join(trouves)
    )


def test_le_motif_reconnait_les_formes_du_chemin():
    """Le garde ne vaut que s'il voit les formes qu'on écrit vraiment."""
    for forme in (_NOM + "/config", _NOM + "\\config", f'RACINE / "{_NOM}" / "config"',
                  f"RACINE / '{_NOM}'"):
        assert CHEMIN_DE_L_INSTANCE.search(forme), forme
    for neutre in ("une_instance", "self.instance", f'_fichiers_suivis("{_NOM}")',
                   f'A_FOUILLER = ("src", "{_NOM}")'):
        assert not CHEMIN_DE_L_INSTANCE.search(neutre), neutre


def test_le_garde_de_l_instance_reconnait_ses_formes():
    """Les jonctions qu'on écrit vraiment, pathlib comme `os.path`, et pas une citation.

    Le nom est assemblé (`_NOM`), pour que ce fichier ne se désigne pas lui-même."""
    for source in (f'p = RACINE / "{_NOM}" / "config"\n',
                   f'p = "{_NOM}" / Path("config")\n',
                   f'p = Path(RACINE, "{_NOM}")\n',
                   f'p = RACINE.joinpath("{_NOM}", "config")\n',
                   f'p = os.path.join(r, "{_NOM}")\n',
                   f'p = os.path.join(r, "{_NOM}", "config")\n',
                   f'p = Path("{_NOM}/config")\n',
                   f'p = f"{{RACINE}}/{_NOM}/config"\n'):
        assert _construit_l_instance(source) == [1], source
    for source in (f'"""La configuration vit sous `{_NOM}/config`."""\n',
                   f'# lisait {_NOM}/config\nx = 1\n',
                   f'_fichiers_suivis("{_NOM}")\n',
                   f'A_FOUILLER = ("src", "{_NOM}")\n',
                   'x = self.instance\n',
                   f'p = RACINE / "une_{_NOM}"\n',
                   f'p = os.path.join(r, "{_NOM}s")\n'):
        assert _construit_l_instance(source) == [], source


def test_le_code_ignore_l_instance():
    fichiers = _suivis("src")
    assert fichiers, "aucun fichier suivi sous src/"
    trouves = _qui_nomment_l_instance(fichiers)
    assert trouves == [], (
        "le code nomme le dossier de l'instance ; il ne doit connaître que VEILLE_CONFIG :\n"
        + "\n".join(trouves)
    )


def test_la_ci_ne_lit_aucune_configuration_d_instance():
    """La configuration réelle vit au dépôt de données : sa CI la vérifie contre l'image
    publiée. Le job `verifier` de ce dépôt n'en lit aucune."""
    ci = yaml.safe_load((RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    commandes = [etape.get("run", "") for etape in ci["jobs"]["verifier"]["steps"]]
    lisent = [c for c in commandes if "config verifier" in c or CHEMIN_DE_L_INSTANCE.search(c)]
    assert lisent == [], f"le job verifier lit une configuration d'instance : {lisent}"


def test_le_banc_du_modele_n_est_pas_examine():
    """Le banc des scripts de déploiement est géré par le modèle : il nomme le dossier de
    l'instance pour la règle des paires (M-0003, § 6), sur des clones qu'il fabrique."""
    banc = _suivis("tests/deploiement")
    assert banc, "aucun fichier suivi sous tests/deploiement/"
    assert _qui_nomment_l_instance(banc) == []


def test_les_tests_ignorent_l_instance():
    fichiers = _suivis("tests", "tests_navigateur")
    assert fichiers, "aucun fichier suivi sous tests/"
    trouves = _qui_nomment_l_instance(fichiers)
    assert trouves == [], (
        "un test nomme le dossier de l'instance ; il doit tourner sur l'exemple :\n"
        + "\n".join(trouves)
    )
