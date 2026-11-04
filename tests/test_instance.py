"""Le code sans la configuration personnelle : le défaut sur l'exemple, le refus de collecter
sans configuration désignée, et la prod qui refuse de démarrer sans elle.

Ces tests posent ou retirent eux-mêmes `VEILLE_CONFIG`, `VEILLE_CRITERES`, `VEILLE_SOURCES` et
`VEILLE_EMPLOI_ENV` : `conftest.py` désigne l'exemple pour le reste de la suite.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_instantane import source  # noqa: F401  (la fixture : des données vivantes)
from veille import collecte, config, db, instantane, planificateur
from veille.app import app

RACINE = config.RACINE
EXEMPLE = RACINE / "exemple"
VARIABLES = ("VEILLE_CONFIG", "VEILLE_CRITERES", "VEILLE_SOURCES", "VEILLE_EMPLOI_ENV")
MESSAGE = (
    "aucune configuration n'est désignée : cette console sert l'exemple. "
    "Pose VEILLE_CONFIG (docs/exploitation.md, « La configuration désignée »)."
)


@pytest.fixture
def rien_de_designe(monkeypatch):
    for nom in VARIABLES:
        monkeypatch.delenv(nom, raising=False)


@pytest.fixture
def copie_exemple(tmp_path) -> Path:
    destination = tmp_path / "copie"
    shutil.copytree(EXEMPLE, destination)
    return destination


def _cli(args, tmp_path, **variables):
    env = {k: v for k, v in os.environ.items() if k not in VARIABLES}
    env["VEILLE_DB"] = str(tmp_path / "veille.sqlite3")
    env["VEILLE_ENV"] = str(tmp_path / "aucun.env")
    env["PYTHONPATH"] = str(RACINE / "src")
    env.update(variables)
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "veille.cli", *args],
        capture_output=True, text=True, encoding="utf-8", timeout=120, env=env, cwd=str(RACINE),
    )


# --- Le défaut -------------------------------------------------------------


def test_defaut_sur_l_exemple():
    code = (
        "from veille import config; "
        "print(config.DOSSIER_CONFIG == config.RACINE / 'exemple', "
        "config.CHEMIN_GABARITS == config.DOSSIER_CONFIG / 'gabarits', "
        "config.CHEMIN_KIT == config.CHEMIN_GABARITS, config.config_designee())"
    )
    env = {k: v for k, v in os.environ.items() if k not in VARIABLES and k != "VEILLE_KIT"}
    env["PYTHONPATH"] = str(RACINE / "src")
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True,
                       text=True, encoding="utf-8", env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["True", "True", "True", "False"]


def test_la_reference_des_empreintes_suit_le_dossier_de_configuration():
    from veille import empreintes

    assert empreintes.REFERENCE == config.DOSSIER_CONFIG / "empreintes-kit.json"


# --- Le refus de collecter ---------------------------------------------------


def test_collecte_refuse_sans_configuration_designee(tmp_path):
    r = _cli(["collecter", "--jours", "1"], tmp_path)
    assert r.returncode == 2
    assert MESSAGE in r.stderr
    assert not (tmp_path / "veille.sqlite3").exists()

    r = _cli(["rescorer"], tmp_path)
    assert r.returncode == 2
    assert MESSAGE in r.stderr
    assert not (tmp_path / "veille.sqlite3").exists()


def test_collecter_refuse_en_python(rien_de_designe, monkeypatch):
    appels = []
    monkeypatch.setattr(db, "initialiser", lambda: appels.append("initialiser"))
    with pytest.raises(config.ConfigurationInvalide, match=re.escape(MESSAGE)):
        collecte.collecter(jours=1)
    assert appels == []


def test_le_bouton_collecter_rend_une_erreur_lisible(rien_de_designe, monkeypatch, tmp_path):
    from tests.aide_session import connecter

    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    lances = []
    monkeypatch.setattr(planificateur.PLANIFICATEUR, "collecter_maintenant",
                        lambda: lances.append(1) or True)
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        r = c.post("/api/reglages/collecter")
    assert r.status_code == 409
    assert r.json() == {"erreur": "configuration_non_designee"}
    assert lances == []


def test_le_recalcul_de_la_console_refuse_sans_configuration_designee(rien_de_designe,
                                                                     monkeypatch, tmp_path):
    from tests.aide_session import connecter

    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    appels = []
    monkeypatch.setattr(db, "rescorer_tout", lambda: appels.append(1) or (0, 0, 0, 0))
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        r = c.post("/api/rescorer")
    assert r.status_code == 409
    assert r.json() == {"erreur": "configuration_non_designee"}
    assert appels == []


def test_le_message_du_bouton_se_lit_a_l_ecran():
    source_js = (RACINE / "src" / "veille" / "static" / "app.js").read_text(encoding="utf-8")
    erreurs = source_js[source_js.index("const ERREURS_API"):source_js.index("async function api(")]
    assert "configuration_non_designee:" in erreurs


def test_le_planificateur_journalise_sans_lever(rien_de_designe, monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    db.initialiser()
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "prod")
    # La vraie collecte : elle refuse, et le planificateur le dit sans lever.
    p = planificateur.Planificateur(
        horloge=lambda: datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc))
    with caplog.at_level(logging.WARNING, logger="veille.planificateur"):
        p._collecter()
    assert any(MESSAGE in m for m in caplog.messages)
    assert not any(r.exc_info for r in caplog.records)


# --- /sante et le démarrage --------------------------------------------------


def test_la_console_s_ouvre_sans_configuration_designee(rien_de_designe, monkeypatch, tmp_path):
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    with TestClient(app, follow_redirects=False) as c:
        assert c.get("/sante").status_code == 200
        assert c.get("/connexion").status_code == 200


def test_sante_dit_la_configuration(rien_de_designe, monkeypatch, tmp_path, copie_exemple):
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    with TestClient(app, follow_redirects=False) as c:
        corps = c.get("/sante").json()
        assert corps["configuration"] == "exemple"
        assert set(corps) == {"statut", "environnement", "version", "revision", "configuration"}
        monkeypatch.setenv("VEILLE_CONFIG", str(copie_exemple))
        assert c.get("/sante").json()["configuration"] == "montee"


def test_prod_sans_configuration_refuse_de_demarrer(rien_de_designe, monkeypatch, tmp_path,
                                                    copie_exemple):
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "prod")
    with pytest.raises(config.ConfigurationInvalide, match="en prod, aucune configuration"):
        with TestClient(app):
            pass
    monkeypatch.setenv("VEILLE_CONFIG", str(copie_exemple))
    with TestClient(app) as c:
        assert c.get("/sante").json()["configuration"] == "montee"


@pytest.mark.parametrize("mode", ["staging", "ci", None])
def test_hors_prod_le_repli_demeure(rien_de_designe, monkeypatch, tmp_path, mode):
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    if mode is not None:
        monkeypatch.setenv("VEILLE_EMPLOI_ENV", mode)
        monkeypatch.setattr("veille.factice.charger_au_demarrage", lambda: None)
    with TestClient(app) as c:
        corps = c.get("/sante").json()
    assert corps["configuration"] == "exemple"


def test_l_instantane_tourne_en_prod_sans_configuration(source, tmp_path):  # noqa: F811
    d = tmp_path / "inst"
    instantane.creer(d)
    r = _cli(["instantane", "verifier", str(d)], tmp_path, VEILLE_EMPLOI_ENV="prod",
             VEILLE_DB=str(d / "veille.sqlite3"), VEILLE_DOSSIERS=str(d / "dossiers"),
             VEILLE_KIT=str(d / "kit"), VEILLE_VAPID=str(d / "vapid.json"))
    assert r.returncode == 0, r.stderr + r.stdout


# --- Après la revue de branche ---------------------------------------------


def test_en_staging_sans_configuration_le_bouton_dit_l_environnement(rien_de_designe,
                                                                    monkeypatch, tmp_path):
    """L'environnement d'abord : en staging, « la collecte est coupée » est le bon message,
    pas « aucune configuration n'est désignée »."""
    from tests.aide_session import connecter

    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "staging")
    monkeypatch.setattr("veille.factice.charger_au_demarrage", lambda: None)
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        r = c.post("/api/reglages/collecter")
    assert r.status_code == 409
    assert r.json() == {"erreur": "collecte_coupee"}


def test_empreintes_kit_refuse_sans_configuration_designee(rien_de_designe, monkeypatch,
                                                          tmp_path, capsys):
    """Sans configuration, la référence serait celle de l'exemple : chaque pièce du kit réel
    sortirait « NOUVEAU », et `--mettre-a-jour` écrirait la référence du kit réel dans
    `exemple/`. La commande refuse d'abord, comme `collecter` (code 2)."""
    from veille import cli, empreintes

    ecrites = []
    monkeypatch.setattr(empreintes, "REFERENCE", tmp_path / "empreintes-kit.json")
    monkeypatch.setattr(empreintes, "ecrire_reference", lambda *a, **k: ecrites.append(a))
    for arguments in (["empreintes-kit"], ["empreintes-kit", "--mettre-a-jour"]):
        assert cli.principal(arguments) == 2
        sortie = capsys.readouterr()
        assert MESSAGE in sortie.err
        assert sortie.out == ""
    assert ecrites == []
    assert not (tmp_path / "empreintes-kit.json").exists()


def test_verifier_refuse_sans_configuration_designee_quand_il_rescore(tmp_path):
    """`veille verifier` enrichit puis rescore : comme `rescorer`, il refuse (code 2)."""
    r = _cli(["verifier"], tmp_path)
    assert r.returncode == 2
    assert MESSAGE in r.stderr
    assert not (tmp_path / "veille.sqlite3").exists()


def test_l_app_demarre_sur_l_exemple_sans_rien_de_designe(tmp_path):
    """Chemins calculés à neuf, aucune variable de configuration : la console sert l'exemple."""
    code = (
        "from fastapi.testclient import TestClient\n"
        "from veille import config\n"
        "from veille.app import app\n"
        "assert config.DOSSIER_CONFIG == config.RACINE / 'exemple', config.DOSSIER_CONFIG\n"
        "assert not config.config_designee()\n"
        "familles = config.charger_criteres().familles\n"
        "assert len(familles) == 7, list(familles)\n"
        "with TestClient(app) as c:\n"
        "    assert c.get('/').status_code == 200\n"
        "    assert c.get('/sante').json()['configuration'] == 'exemple'\n"
        "print('ok')\n"
    )
    env = {k: v for k, v in os.environ.items()
           if k not in VARIABLES and k not in ("VEILLE_KIT", "VEILLE_DB", "VEILLE_ENV")}
    env["VEILLE_DB"] = str(tmp_path / "veille.sqlite3")
    env["VEILLE_ENV"] = str(tmp_path / "aucun.env")
    env["PYTHONPATH"] = str(RACINE / "src")
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True,
                       text=True, encoding="utf-8", timeout=120, env=env, cwd=str(RACINE))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ok"


def test_prod_avec_une_configuration_cassee_refuse_de_demarrer(tmp_path):
    """Un dossier non vide mais sans `criteres.yaml` : le démarrage échoue, `/sante` ne dit pas ok."""
    cassee = tmp_path / "cassee"
    cassee.mkdir()
    (cassee / "sources.yaml").write_text("{}\n", encoding="utf-8")
    code = (
        "from fastapi.testclient import TestClient\n"
        "from veille.app import app\n"
        "with TestClient(app):\n"
        "    pass\n"
        "print('demarre')\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in VARIABLES and k != "VEILLE_KIT"}
    env.update(VEILLE_EMPLOI_ENV="prod", VEILLE_CONFIG=str(cassee),
               VEILLE_DB=str(tmp_path / "veille.sqlite3"),
               VEILLE_ENV=str(tmp_path / "aucun.env"), PYTHONPATH=str(RACINE / "src"))
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True,
                       text=True, encoding="utf-8", timeout=120, env=env, cwd=str(RACINE))
    assert r.returncode != 0
    assert "demarre" not in r.stdout
    assert "ConfigurationInvalide" in r.stderr
    assert "la configuration montée est inutilisable" in r.stderr
    assert "criteres.yaml" in r.stderr


# --- Sans conteneur ni configuration : la page le dit, une offre ne se travaille pas -----
# Une console sans `VEILLE_EMPLOI_ENV` sert une instance : si elle sert l'exemple, c'est un
# oubli de `VEILLE_CONFIG`. Le staging et la CI servent l'exemple par contrat, et gardent
# leurs gestes. La suite désigne l'exemple (`conftest.py`) : ces tests retirent la variable.

BANDEAU = "Cette console sert l'exemple"


def _page_de_la_console(monkeypatch, tmp_path) -> str:
    from tests.aide_session import connecter

    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        r = c.get("/")
    assert r.status_code == 200
    return r.text


def test_sans_conteneur_ni_configuration_la_page_le_dit(rien_de_designe, monkeypatch, tmp_path):
    page = _page_de_la_console(monkeypatch, tmp_path)
    assert BANDEAU in page
    assert "VEILLE_CONFIG" in page[page.index(BANDEAU):]


@pytest.mark.parametrize("cas", ["designee", "staging", "ci"])
def test_le_bandeau_ne_parait_ni_avec_une_configuration_ni_en_conteneur(
        cas, rien_de_designe, monkeypatch, tmp_path, copie_exemple):
    if cas == "designee":
        monkeypatch.setenv("VEILLE_CONFIG", str(copie_exemple))
    else:
        monkeypatch.setenv("VEILLE_EMPLOI_ENV", cas)
        monkeypatch.setattr("veille.factice.charger_au_demarrage", lambda: None)
    assert BANDEAU not in _page_de_la_console(monkeypatch, tmp_path)


# Ce que chaque geste ferait avec l'exemple : rien de tout cela ne doit tourner.
TRAVAUX_D_UNE_OFFRE = (
    ("veille.dossier", "generer"),
    ("veille.relance", "preparer"),
    ("veille.enrichissement", "appliquer_texte"),
    ("veille.enrichissement", "recuperer"),
    ("veille.verification", "verifier_offre"),
    ("veille.db", "annuler_texte_complet"),
    ("veille.db", "rescorer_offre"),
    ("veille.db", "valider_exigences"),
    ("veille.db", "oublier_exigences"),
    ("veille.db", "valider_famille"),
    ("veille.affinement", "affiner"),
    ("veille.lettre", "lire"),
    ("veille.lettre", "derniere_version"),
    ("veille.lettre", "historiser"),
    ("veille.dossier", "regenerer_pdf"),
)

# Générer un dossier ou une relance, tout recalcul d'une seule offre, et l'affinement : sa
# consigne et ses règles seraient celles de l'exemple, appliquées à une lettre réelle, et le
# PDF refait porterait le préfixe de l'exemple.
GESTES_SUR_UNE_OFFRE = (
    ("POST", "/api/offres/{id}/dossier?forcer=true", None),
    ("GET", "/api/offres/{id}/relance", None),
    ("POST", "/api/offres/{id}/texte", {"texte": "Le texte complet de l'annonce, collé."}),
    ("POST", "/api/offres/{id}/verifier", None),
    ("POST", "/api/offres/{id}/enrichir", None),
    ("POST", "/api/offres/{id}/texte/annuler", None),
    ("POST", "/api/offres/{id}/exigences/valider", {"attributs": []}),
    ("POST", "/api/offres/{id}/exigences/oublier", None),
    ("POST", "/api/classement/valider",
     {"decisions": [{"offre_id": "{id}", "famille": "test_fonctionnel"}]}),
    ("POST", "/api/offres/{id}/affiner", None),
    ("POST", "/api/offres/{id}/affiner/appliquer", None),
    ("POST", "/api/offres/{id}/affiner/annuler", None),
)


def _une_offre(dossier: Path | None = None) -> int:
    """Une offre en base ; avec `dossier`, un dossier déjà généré, sa lettre et une proposition
    d'affinement : sans refus, chaque geste irait jusqu'à son travail."""
    from veille.models import Offre

    offre_id, _ = db.enregistrer_offre(Offre(
        titre="Testeuse logiciel", employeur="Entreprise d'essai", lieu="Ville d'essai",
        description="Tests fonctionnels.", url="https://offres.exemple.invalid/1"))
    if dossier is not None:
        dossier.mkdir()
        for nom in ("lettre-de-motivation.md", "lettre-assemblee.md", "lettre-affinee.md"):
            (dossier / nom).write_text("Madame, Monsieur,\n\nUne lettre d'essai.\n",
                                       encoding="utf-8")
        db.maj_champs(offre_id, dossier_chemin=str(dossier))
    return offre_id


def _avec_l_offre(corps, offre_id: int):
    if corps is None:
        return None
    if "decisions" in corps:
        return {"decisions": [dict(d, offre_id=offre_id) for d in corps["decisions"]]}
    return corps


@pytest.mark.parametrize("methode, chemin, corps", GESTES_SUR_UNE_OFFRE)
def test_sans_conteneur_ni_configuration_une_offre_ne_se_travaille_pas(
        methode, chemin, corps, rien_de_designe, monkeypatch, tmp_path):
    from tests.aide_session import connecter

    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    appels = []
    for module, nom in TRAVAUX_D_UNE_OFFRE:
        monkeypatch.setattr(f"{module}.{nom}",
                            lambda *_a, _nom=nom, **_k: appels.append(_nom))
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        offre_id = _une_offre(tmp_path / "dossier")
        r = c.request(methode, chemin.format(id=offre_id), json=_avec_l_offre(corps, offre_id))
    assert r.status_code == 409, r.text
    assert r.json() == {"erreur": "configuration_non_designee"}
    assert appels == []


@pytest.mark.parametrize("chemin", [
    "/api/affinement",
    "/api/offres",
    "/api/offres/{id}",
    "/api/offres/{id}/completude",
])
def test_sans_conteneur_ni_configuration_les_lectures_restent_ouvertes(
        chemin, rien_de_designe, monkeypatch, tmp_path):
    """Lire n'écrit rien : la console s'ouvre et se consulte, le bandeau dit le reste."""
    from tests.aide_session import connecter

    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        offre_id = _une_offre()
        r = c.get(chemin.format(id=offre_id))
    assert r.status_code == 200, r.text


def _message_a_l_ecran() -> str:
    source_js = (RACINE / "src" / "veille" / "static" / "app.js").read_text(encoding="utf-8")
    trouve = re.search(r'^\s*configuration_non_designee: "([^"]*)",$', source_js, re.MULTILINE)
    assert trouve, "configuration_non_designee manque à ERREURS_API"
    return trouve.group(1)


def test_le_message_du_refus_vaut_pour_tous_les_gestes():
    """Un seul refus sert la collecte, le rescorage, les empreintes du kit, le dossier, la
    relance, le recalcul et l'affinement : ses deux messages, celui des commandes et celui de
    l'écran, disent l'état et le remède, sans parler d'un geste en particulier."""
    for message in (config.MESSAGE_SANS_CONFIGURATION, _message_a_l_ecran()):
        assert "aucune configuration n'est désignée : cette console sert l'exemple." in (
            message.lower()), message
        assert "Pose VEILLE_CONFIG" in message, message
        assert "docs/exploitation.md, « La configuration désignée »" in message, message
        for propre_a_un_geste in ("collecte", "noter", "noterait", "offres"):
            assert propre_a_un_geste not in message, message


@pytest.mark.parametrize("cas", ["designee", "staging", "ci"])
def test_avec_une_configuration_ou_en_conteneur_une_offre_se_recalcule(
        cas, rien_de_designe, monkeypatch, tmp_path, copie_exemple):
    """Le staging garde le recalcul d'une offre (il sert l'exemple par contrat) ; une console
    qui désigne sa configuration aussi. Sans texte complet, l'annulation dit pourquoi."""
    from tests.aide_session import connecter

    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    if cas == "designee":
        monkeypatch.setenv("VEILLE_CONFIG", str(copie_exemple))
    else:
        monkeypatch.setenv("VEILLE_EMPLOI_ENV", cas)
        monkeypatch.setattr("veille.factice.charger_au_demarrage", lambda: None)
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        offre_id = _une_offre()
        r = c.post(f"/api/offres/{offre_id}/texte/annuler")
    assert r.status_code == 400, r.text
    assert "aucun texte complet" in r.json()["detail"]
