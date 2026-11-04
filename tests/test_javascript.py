"""La page doit au moins se charger.

POURQUOI CE FICHIER EXISTE : le champ de collage a ete livre avec deux
apostrophes non echappees dans des chaines simples — `'Lire l'annonce'`.
Le fichier partait, le serveur repondait 200, les 394 tests passaient, et
pourtant la console etait **entierement morte** dans le navigateur : une
`SyntaxError` au chargement, aucune offre affichee, aucun filtre repliable.

Un test HTTP verifie que le serveur sert le fichier. Il ne verifie pas que le
navigateur sait le lire. C'est exactement le genre d'ecart que la methode du
projet condamne : on verifie la chose reelle, pas son substitut.

Le francais rend ce piege permanent — « l'annonce », « l'extrait »,
« aujourd'hui » — donc le garde-fou doit etre automatique.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

STATIQUE = Path(__file__).resolve().parents[1] / "src" / "veille" / "static"
FICHIERS = sorted(STATIQUE.glob("*.js"))


def _verificateur() -> str | None:
    return shutil.which("node") or shutil.which("node.exe")


def test_il_y_a_bien_du_javascript_a_verifier():
    """Si les fichiers sont renommes ou deplaces, le garde-fou doit crier."""
    assert FICHIERS, f"aucun .js trouve dans {STATIQUE}"


@pytest.mark.parametrize("fichier", FICHIERS, ids=lambda f: f.name)
def test_le_javascript_se_parse(fichier: Path):
    node = _verificateur()
    if not node:
        pytest.skip("node absent : installe-le pour activer ce garde-fou")
    r = subprocess.run([node, "--check", str(fichier)], capture_output=True, text=True)
    assert r.returncode == 0, (
        f"{fichier.name} ne se parse pas — la console serait morte dans le "
        f"navigateur :\n{r.stderr.strip()}"
    )


@pytest.mark.parametrize("fichier", FICHIERS, ids=lambda f: f.name)
def test_pas_de_texte_place_dans_le_html_sans_echappement(fichier: Path):
    """Deuxieme filet : les donnees d'une annonce passent par `echapper()`.

    Un employeur nomme `<script>` ne doit pas pouvoir executer quoi que ce soit
    dans sa console, et un titre avec une apostrophe ne doit pas casser la page.
    """
    source = fichier.read_text(encoding="utf-8")
    if "echapper" not in source:
        pytest.skip(f"{fichier.name} ne construit pas de HTML")
    assert "innerHTML = o." not in source, "donnee d'offre injectee sans echapper()"


# --------------------------------------------------------------------------
# Ce que le rapport affiche quand l'offre tombe
#
# Trouve a l'ecran : une offre ecartee pour astreinte affichait
# « Score : 55 -> 99 ▲ +44 » en vert. Le chiffre montait parce que le texte
# complet apportait des points ; l'offre etait pourtant morte. Lu vite, sur un
# telephone, c'est l'inverse du message.
# --------------------------------------------------------------------------


def _app_js() -> str:
    return (STATIQUE / "app.js").read_text(encoding="utf-8")


def test_un_ecartement_ne_sannonce_pas_comme_une_hausse():
    source = _app_js()
    debut = source.index("function afficherRapportTexte")
    fin = source.index("function blocTexteComplet")
    corps = source[debut:fin]
    branche = corps[corps.index("if (r.alerte_eliminatoire)"):corps.index("} else {")]
    assert "monte" not in branche, (
        "la branche eliminatoire ne doit pas reutiliser l'affichage de hausse"
    )
    assert "\u00c9cart\u00e9e" in branche, "le mot doit etre dit"


def test_lalerte_eliminatoire_passe_avant_le_chiffre():
    corps = _app_js()
    i_alerte = corps.index("ce que l'extrait ne montrait pas")
    i_score = corps.index("Score avant \u00e9cartement")
    assert i_alerte < i_score, "l'ecartement se lit d'abord, le score ensuite"


# --------------------------------------------------------------------------
# Aucun secret reel dans le depot
#
# Ecrit apres l'avoir fait : en ajoutant un test de masquage, j'y ai recopie
# son VRAI mot de passe d'application Gmail et la moitie de sa cle France
# Travail, comme valeurs de fixture. Un fichier de test est versionne, lu,
# copie, envoye ; c'est exactement l'endroit ou un secret ne doit pas etre.
# --------------------------------------------------------------------------

DEPOT = Path(__file__).resolve().parents[1]
# `config` n'existe que dans le clone d'une console sans conteneur (son `.env`, écarté plus bas) ;
# la configuration de l'instance vit au dépôt de données.
A_FOUILLER = ("src", "tests", "docs", "config", "exemple")

# Formes des secrets du projet, pas leurs valeurs : on cherche la FORME.
FORMES_SUSPECTES = (
    (re.compile(r"\bPAR_[A-Za-z0-9]+_[0-9a-f]{32,}"), "identifiant client France Travail"),
    (re.compile(r"\b[0-9a-f]{64}\b"), "cle secrete de 64 caracteres hexadecimaux"),
    (re.compile(r"\bBQ[A-Za-z0-9_-]{60,}"), "cle VAPID"),
)

# Valeurs manifestement fictives, admises : elles servent aux tests.
FICTIVES = re.compile(r"^(0123456789abcdef|0+|f+|a+|deadbeef|1234567890)+$", re.IGNORECASE)

# Les empreintes SHA-256 ont la forme d'une cle. Deux formes seulement sont
# retirees du texte avant la recherche, celles de tests/deploiement/Dockerfile,
# gere par le modele : l'empreinte d'une image epinglee (`@sha256:<hex>`) et la
# ligne de `sha256sum -c` (`<hex>  /chemin`, l'empreinte en debut de valeur, le
# chemin absolu ou en `./`). Une empreinte se publie, un secret jamais : tout le
# reste compte, `=<hex>` ou `sha256:<hex>` sans `@` compris.
EMPREINTES = re.compile(r"@sha256:[0-9a-f]{64}\b|(?<![^\s\"'])[0-9a-f]{64}(?=  \.?/)")


@pytest.mark.parametrize("dossier", A_FOUILLER)
def test_aucun_secret_de_forme_reelle_dans_le_depot(dossier):
    racine = DEPOT / dossier
    if not racine.exists():
        pytest.skip(f"{dossier} absent")
    coupables = []
    for chemin in racine.rglob("*"):
        if not chemin.is_file() or "__pycache__" in chemin.parts:
            continue
        # `.env` et `auth.json` portent les secrets par construction et ne
        # sont pas versionnes ; c'est leur raison d'etre.
        if chemin.name in ("auth.json",) or chemin.name.startswith(".env"):
            continue
        if chemin.suffix in (".png", ".jpg", ".pdf", ".db", ".sqlite"):
            continue
        try:
            contenu = chemin.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        contenu = EMPREINTES.sub("", contenu)
        for forme, quoi in FORMES_SUSPECTES:
            for trouve in forme.findall(contenu):
                if FICTIVES.match(trouve):
                    continue
                coupables.append(f"{chemin.relative_to(DEPOT)} : {quoi} ({trouve[:12]}…)")
    assert not coupables, (
        "secret de forme reelle dans un fichier versionne :\n  " + "\n  ".join(coupables)
    )


def test_le_garde_fou_attrape_bien_un_secret():
    """Un garde-fou qu'on ne teste pas ne garde rien.

    Les chaines ci-dessous sont fabriquees a la volee, jamais ecrites en dur :
    ce fichier ne doit contenir aucune valeur de forme reelle, y compris pour
    se tester lui-meme — sinon il se denoncerait.
    """
    faux = "".join("13579bdf"[i % 8] for i in range(64))
    assert not FICTIVES.match(faux), "le faux doit ressembler a un vrai"
    forme_id, _ = FORMES_SUSPECTES[0]
    assert forme_id.search(f"FT_CLIENT_ID=PAR_applicationtest_{faux}")
    forme_cle, _ = FORMES_SUSPECTES[1]
    assert forme_cle.search(f"FT_CLIENT_SECRET={faux}")
    # une empreinte n'est pas un secret ; un secret le reste, commentaire ou non
    assert not forme_cle.search(EMPREINTES.sub("", f"FROM debian@sha256:{faux}"))
    assert not forme_cle.search(EMPREINTES.sub("", f'echo "{faux}  /tmp/age.tar.gz"'))
    assert forme_cle.search(EMPREINTES.sub("", f"FT_CLIENT_SECRET={faux}"))
    assert forme_cle.search(EMPREINTES.sub("", f"FT_CLIENT_SECRET={faux}  # le secret"))
    assert forme_cle.search(EMPREINTES.sub("", f"FT_CLIENT_SECRET={faux}  suite"))
    assert forme_cle.search(EMPREINTES.sub("", f"FT_CLIENT_SECRET={faux}  /chemin"))
    assert forme_cle.search(EMPREINTES.sub("", f"FT_CLIENT_SECRET=sha256:{faux}"))
    assert forme_cle.search(EMPREINTES.sub("", f"cle : {faux}  voir plus bas"))


# --------------------------------------------------------------------------
# Toute route appelee par le JS doit exister
#
# Trouve en production, par Edouard : « je clique sur "elle n'y est plus,
# archiver" et l'offre est toujours la ». La route `/api/offres/{id}/retiree`
# avait ete renommee en `/constat` cote serveur ; le JS appelait toujours
# l'ancienne. `fetch` ne leve RIEN sur un 404 : le code fermait la fenetre,
# rechargeait la liste, et tout avait l'air normal. Plusieurs offres concernees,
# une action definitivement perdue.
#
# Aucun test ne pouvait le voir : les tests Python appelaient la bonne route,
# les tests JS verifiaient la syntaxe. Personne ne confrontait les deux.
# --------------------------------------------------------------------------

_APPEL = re.compile(r"""[`'"](/api/[^`'"?\s]+)""")


def _routes_declarees() -> set[str]:
    """Les chemins que FastAPI expose, gabarits compris."""
    from veille.app import app

    return {r.path for r in app.routes if hasattr(r, "path")}


def _gabarit(chemin: str) -> str:
    """Remplace les interpolations JS par le nom de parametre FastAPI.

    `/api/offres/${id}/constat` -> `/api/offres/{offre_id}/constat`
    """
    return re.sub(r"\$\{[^}]+\}", "{X}", chemin)


def test_toute_route_appelee_par_le_js_existe():
    source = (STATIQUE / "app.js").read_text(encoding="utf-8")
    declarees = {_gabarit(re.sub(r"\{[^}]+\}", "{X}", r)) for r in _routes_declarees()}

    manquantes = []
    for appel in sorted(set(_APPEL.findall(source))):
        if _gabarit(appel) not in declarees:
            manquantes.append(appel)
    assert not manquantes, (
        "le JS appelle des routes qui n'existent pas — `fetch` ne leve rien sur "
        "un 404, donc l'echec serait silencieux :\n  " + "\n  ".join(manquantes)
    )


def test_le_garde_fou_attrape_bien_une_route_disparue():
    """Un garde-fou qu'on ne teste pas ne garde rien."""
    declarees = {_gabarit(re.sub(r"\{[^}]+\}", "{X}", r)) for r in _routes_declarees()}
    assert _gabarit("/api/offres/${id}/retiree") not in declarees, (
        "la route morte est revenue : ce test ne prouve plus rien"
    )
    assert _gabarit("/api/offres/${id}/constat") in declarees


# --------------------------------------------------------------------------
# Le service worker n'intercepte rien
#
# Point d'attention 4 du lot des passkeys : une session expiree dans
# l'application installee doit finir sur /connexion. L'API rend 401 et
# `app.js` y renvoie ; un service worker qui servirait une reponse en cache
# masquerait le 401, et la console afficherait des donnees perimees au lieu
# de demander la connexion.
# --------------------------------------------------------------------------


def test_le_service_worker_n_intercepte_rien():
    source = (STATIQUE / "sw.js").read_text(encoding="utf-8")
    assert "'fetch'" not in source and '"fetch"' not in source, (
        "sw.js ecoute les requetes : il pourrait masquer un 401"
    )
    assert "caches." not in source, "sw.js met des reponses en cache"


# --------------------------------------------------------------------------
# Une erreur de l'API se lit a l'ecran
#
# Les routes de la connexion repondent `{"erreur": "<code>"}`, les autres
# `{"detail": "..."}`. `api()` ne lisait que `detail` : un 403 `origine`
# s'affichait « Forbidden », sans dire que VEILLE_URL etait en cause.
# --------------------------------------------------------------------------


def test_api_lit_le_code_d_erreur_du_corps():
    node = _verificateur()
    if not node:
        pytest.skip("node absent : installe-le pour activer ce garde-fou")
    source = _app_js()
    # Les erreurs dites en clair et `api()`, seuls : le reste du fichier demande le DOM.
    harnais = source[source.index("const ERREURS_API"):source.index("const niveau")] + """
const corps = [{ erreur: 'origine' }, { detail: 'offre inconnue' }, { erreur: 'code_neuf' }, null];
(async () => {
  for (const c of corps) {
    globalThis.fetch = async () => ({
      ok: false, status: 403, statusText: 'Forbidden',
      json: async () => { if (c === null) throw new Error('pas de JSON'); return c; },
    });
    try { await api('/api/x', { method: 'POST' }); console.log('AUCUNE ERREUR'); }
    catch (e) { console.log(e.message); }
  }
})();
"""
    r = subprocess.run([node], input=harnais, capture_output=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    origine, detail, code_neuf, sans_json = r.stdout.splitlines()
    assert "VEILLE_URL" in origine, origine
    assert detail == "offre inconnue"
    assert code_neuf == "code_neuf"
    assert sans_json == "Forbidden"


# --------------------------------------------------------------------------
# Une passkey deja sur l'appareil renvoie a la connexion
#
# `excludeCredentials` fait lever `InvalidStateError` a `create()` quand
# l'appareil porte deja une passkey de la console. « La connexion a echoue »
# laisserait Edouard rouvrir le lien en boucle ; il doit aller a /connexion.
# Le parcours reel est dans tests_navigateur/.
# --------------------------------------------------------------------------


def test_une_passkey_deja_sur_l_appareil_renvoie_a_la_connexion():
    source = (STATIQUE / "connexion.js").read_text(encoding="utf-8")
    assert "InvalidStateError" in source
    assert ("Cet appareil a déjà une passkey. "
            "Connecte-toi depuis la page de connexion.") in source
    assert "'/connexion'" in source


def test_ajouter_un_appareil_demande_d_abord_une_touche():
    source = (STATIQUE / "app.js").read_text(encoding="utf-8")
    assert "parseRequestOptionsFromJSON" in source
    assert (source.index("/api/auth/connexion/options")
            < source.index("/api/auth/lien/creer"))
    assert "Ajout annulé." in source


def test_le_javascript_ne_nomme_aucun_atout():
    """L'atout mis en avant vient de la configuration, par la page (`data-atout`) : le
    JavaScript ne nomme aucun atout, ni ceux de l'exemple, ni ceux d'une instance."""
    criteres = STATIQUE.parents[2] / "exemple" / "criteres.yaml"
    atouts = list(yaml.safe_load(criteres.read_text(encoding="utf-8"))["atouts"])
    assert atouts, "l'exemple n'a plus d'atout : le test ne vérifierait rien"
    for fichier in FICHIERS:
        texte = fichier.read_text(encoding="utf-8")
        nommes = [a for a in atouts if a in texte]
        assert nommes == [], f"{fichier.name} nomme {nommes}"
