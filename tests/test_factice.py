"""Le jeu factice du staging, et les cles des notifications en mode conteneur."""

from __future__ import annotations

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from veille import config, db, factice, notifications, reglages
from veille.app import app

from .sauts import sauter


def _weasyprint_utilisable() -> bool:
    try:
        from weasyprint import HTML  # noqa: F401
    except Exception:
        return False
    return True


@pytest.fixture(autouse=True)
def _base_propre(tmp_path, monkeypatch):
    """Base, kit, cles : tout dans tmp_path, rien dans le depot."""
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    monkeypatch.setattr(config, "CHEMIN_KIT", tmp_path / "kit")
    monkeypatch.setattr(notifications, "CHEMIN_VAPID", tmp_path / "donnees" / "vapid.json")
    monkeypatch.delenv("VEILLE_EMPLOI_ENV", raising=False)
    db.initialiser()


@pytest.fixture
def pdf_bouchon(monkeypatch):
    """Remplace le rendu PDF : ces tests ne verifient pas WeasyPrint."""
    appels = []

    def faux(html, destination):
        appels.append(destination)
        destination.write_bytes(b"%PDF-1.4 bouchon\n")

    monkeypatch.setattr(factice, "_rendre_pdf", faux)
    return appels


def _nb_offres() -> int:
    with db.connexion() as cx:
        return cx.execute("SELECT COUNT(*) FROM offres").fetchone()[0]


def _demarrer() -> None:
    with TestClient(app):
        pass


# --------------------------------------------------------------------------
# charger()
# --------------------------------------------------------------------------


def test_charger_dans_une_base_vide(pdf_bouchon):
    n = factice.charger()
    assert 18 <= n <= 30
    assert _nb_offres() == n
    with db.connexion() as cx:
        envoyees = cx.execute(
            "SELECT COUNT(*) FROM offres WHERE statut = 'candidature_envoyee'"
        ).fetchone()[0]
        evenements = cx.execute(
            "SELECT COUNT(*) FROM evenements WHERE type = 'statut:candidature_envoyee'"
        ).fetchone()[0]
    assert envoyees >= 1
    assert evenements == envoyees  # passe par le chemin normal, historique compris
    assert sorted(f.name for f in config.CHEMIN_KIT.iterdir()) == [
        "annexe-technique.pdf", "cv.fr.pdf",
    ]


def test_le_jeu_couvre_les_deux_cotes_du_seuil(pdf_bouchon):
    factice.charger()
    seuil = reglages.lire_seuil()
    with db.connexion() as cx:
        scores = [r[0] for r in cx.execute("SELECT score FROM offres")]
    assert any(s >= seuil for s in scores), scores
    assert any(s < seuil for s in scores), scores
    assert len({round(s) for s in scores}) >= 8, "des scores varies"


def test_le_jeu_couvre_plusieurs_familles(pdf_bouchon):
    factice.charger()
    with db.connexion() as cx:
        familles = {r[0] for r in cx.execute("SELECT famille FROM offres") if r[0]}
    assert len(familles) >= 6, familles


@pytest.mark.skipif(sauter(_weasyprint_utilisable), reason="WeasyPrint indisponible sur cette machine")
def test_le_kit_est_rendu_en_vrais_pdf():
    factice.charger()
    for nom in ("cv.fr.pdf", "annexe-technique.pdf"):
        assert (config.CHEMIN_KIT / nom).read_bytes().startswith(b"%PDF")


def test_charger_refuse_une_base_non_vide(pdf_bouchon):
    factice.charger()
    avant = _nb_offres()
    with pytest.raises(factice.BaseNonVide):
        factice.charger()
    assert _nb_offres() == avant


def test_un_echec_du_rendu_laisse_la_base_vide(monkeypatch):
    def casse(html, destination):
        raise OSError("pango absent")

    monkeypatch.setattr(factice, "_rendre_pdf", casse)
    with pytest.raises(OSError):
        factice.charger()
    assert _nb_offres() == 0


# --------------------------------------------------------------------------
# Le demarrage
# --------------------------------------------------------------------------


def test_le_staging_charge_au_demarrage(monkeypatch, pdf_bouchon):
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "staging")
    _demarrer()
    n = _nb_offres()
    assert n >= 18
    _demarrer()  # un redemarrage : aucun doublon
    assert _nb_offres() == n


@pytest.mark.parametrize("mode", ["prod", "ci", None])
def test_ni_prod_ni_nue_ne_chargent(monkeypatch, pdf_bouchon, mode):
    if mode:
        monkeypatch.setenv("VEILLE_EMPLOI_ENV", mode)
    _demarrer()
    assert _nb_offres() == 0
    assert pdf_bouchon == []


def test_un_echec_du_chargement_n_empeche_pas_de_demarrer(monkeypatch, caplog):
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "staging")

    def casse(html, destination):
        raise OSError("pango absent")

    monkeypatch.setattr(factice, "_rendre_pdf", casse)
    with caplog.at_level(logging.ERROR):
        with TestClient(app) as c:
            assert c.get("/sante").status_code == 200
    assert any("pango absent" in m for m in caplog.messages)
    assert _nb_offres() == 0


@pytest.mark.parametrize("mode", ["prod", "staging"])
def test_les_cles_push_naissent_au_demarrage_en_conteneur(monkeypatch, pdf_bouchon, mode):
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", mode)
    chemin = notifications.CHEMIN_VAPID
    assert not chemin.exists()
    _demarrer()
    assert chemin.exists()
    octets = chemin.read_bytes()
    _demarrer()  # presentes : intactes
    assert chemin.read_bytes() == octets


def test_le_sujet_vapid_du_conteneur_est_l_origine_publique(monkeypatch, pdf_bouchon):
    # M-0001 : le staging ne porte aucune adresse reelle
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "staging")
    monkeypatch.setenv("VEILLE_EMPLOI_URL_PUBLIQUE", "https://staging.exemple.invalid")
    _demarrer()
    brut = notifications.CHEMIN_VAPID.read_text(encoding="utf-8")
    assert json.loads(brut)["sujet"] == "https://staging.exemple.invalid"
    assert "@gmail.com" not in brut


def test_le_sujet_vapid_du_conteneur_sans_origine_est_un_substitut(monkeypatch, pdf_bouchon):
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "staging")
    monkeypatch.delenv("VEILLE_EMPLOI_URL_PUBLIQUE", raising=False)
    monkeypatch.delenv("VEILLE_URL", raising=False)
    _demarrer()
    brut = notifications.CHEMIN_VAPID.read_text(encoding="utf-8")
    assert json.loads(brut)["sujet"] == notifications.SUJET_SANS_ORIGINE
    assert "@gmail.com" not in brut


def test_sans_mode_les_cles_ne_naissent_pas():
    _demarrer()
    assert not notifications.CHEMIN_VAPID.exists()


# --------------------------------------------------------------------------
# Le jeu est ecrit pour l'exemple (exemple/criteres.yaml), qui note les offres
# --------------------------------------------------------------------------

# Les offres sans lieu exploitable, celles que le test de zone ne regarde pas.
LIEU_INCONNU = {
    "https://offres.exemple.invalid/o/2017": "aucun lieu",
    "https://offres.exemple.invalid/o/2018": "region sans ville (Alsace)",
}

# Les offres que l'exemple ecarte, et le critere eliminatoire qui les ecarte.
ELIMINEES = {
    "https://offres.exemple.invalid/o/2020": "automatisme_industriel",
    "https://offres.exemple.invalid/o/2021": "astreinte",
    "https://offres.exemple.invalid/o/2022": "week_end",
    "https://offres.exemple.invalid/o/2023": "horaires_decales",
    "https://offres.exemple.invalid/o/2024": "support_premier_niveau",
    "https://offres.exemple.invalid/o/2025": "deplacements_frequents",
    "https://offres.exemple.invalid/o/2026": "relation_client_allemand",
}

# La seule offre en allemand : mise de cote, pas ecartee.
DIFFEREES = {"https://offres.exemple.invalid/o/2019"}


def _offres_notees():
    """Les offres du jeu, notees par la configuration que la suite designe (l'exemple)."""
    from veille.scoring import scorer

    criteres = config.charger_criteres()
    return [scorer(factice._offre(d), criteres) for d in factice._lire("offres.yaml")["offres"]]


def test_chaque_offre_factice_tombe_dans_une_famille_de_l_exemple():
    familles = set(config.charger_criteres().familles)
    for o in _offres_notees():
        assert o.famille in familles, (o.url, o.titre, o.famille)


def test_le_jeu_couvre_l_exemple():
    criteres = config.charger_criteres()
    offres = _offres_notees()
    par_famille = {f: [o for o in offres if o.famille == f] for f in criteres.familles}
    assert {f: len(v) for f, v in par_famille.items() if len(v) < 2} == {}, "deux offres au moins par famille"
    zones = {o.zone for o in offres}
    assert set(criteres.zones) <= zones, set(criteres.zones) - zones
    suisses = [o for o in offres if o.salaire_devise == "CHF"]
    assert suisses, "au moins une offre suisse en francs"
    assert all(o.zone for o in suisses if o.url not in LIEU_INCONNU)


def test_aucun_lieu_hors_de_l_exemple():
    zones = set(config.charger_criteres().zones)
    for o in _offres_notees():
        if o.url in LIEU_INCONNU:
            continue
        assert o.zone in zones, (o.url, o.lieu, "hors des zones de l'exemple")
    # La liste des lieux inconnus est exacte : aucune de ces offres n'a de zone.
    assert {o.url for o in _offres_notees() if not o.zone} == set(LIEU_INCONNU)


def test_les_offres_ecartees_le_sont_par_un_eliminatoire_voulu():
    criteres = config.charger_criteres()
    offres = _offres_notees()
    ecartees = {o.url: o for o in offres if o.rejete_auto}
    assert set(ecartees) == set(ELIMINEES), "aucune offre ecartee par erreur, aucune ecartee en moins"
    for url, cle in ELIMINEES.items():
        libelle = criteres.eliminatoires[cle]["libelle"]
        assert ecartees[url].motif_rejet_auto == libelle, (url, ecartees[url].motif_rejet_auto)
    assert set(ELIMINEES.values()) == set(criteres.eliminatoires), "chaque eliminatoire ecarte une offre"
    assert {o.url for o in offres if o.differee} == DIFFEREES


# --------------------------------------------------------------------------
# M-0001 : le jeu est factice
# --------------------------------------------------------------------------

_MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"https?://([^/\s\"'<>)]+)")


def _fichiers_du_jeu():
    fichiers = [f for f in (config.RACINE / "factice").rglob("*") if f.is_file()]
    assert fichiers, "factice/ est vide"
    return fichiers


def test_le_jeu_est_factice():
    lisezmoi = (config.RACINE / "factice" / "LISEZMOI.md").read_text(encoding="utf-8")
    nom = re.search(r"\(([A-ZÉ][\w'’-]+(?: [A-ZÉ][\w'’-]+)+)\)", lisezmoi)
    assert nom, "LISEZMOI.md doit nommer la personne fictive entre parentheses"
    nom = nom.group(1)
    for f in _fichiers_du_jeu():
        texte = f.read_text(encoding="utf-8")
        for adresse in _MAIL.findall(texte):
            assert adresse.lower().endswith("@exemple.invalid"), (f.name, adresse)
        for hote in _URL.findall(texte):
            assert hote.lower().split(":")[0].endswith(".exemple.invalid"), (f.name, hote)
    cv = (config.RACINE / "factice" / "kit" / "cv.fr.html").read_text(encoding="utf-8")
    assert nom in cv


def test_le_garde_de_factice_voit_un_mail_ou_une_url_reelle(tmp_path):
    """Les deux regexes attrapent bien ce qu'elles doivent attraper."""
    assert _MAIL.findall("ecrire a contact@example.com")
    assert _URL.findall("https://www.france-travail.fr/x") == ["www.france-travail.fr"]


# --------------------------------------------------------------------------
# veille factice
# --------------------------------------------------------------------------


def test_la_commande_factice(pdf_bouchon, capsys):
    from veille import cli

    assert cli.principal(["factice"]) == 0
    assert "Jeu factice chargé" in capsys.readouterr().out
    assert cli.principal(["factice"]) == 1
    assert "déjà des offres" in capsys.readouterr().out


# --------------------------------------------------------------------------
# le jeu couvre le parcours (ADR-0003)
# --------------------------------------------------------------------------


def _offres_du_jeu() -> list[dict]:
    with db.connexion() as cx:
        return [dict(r) for r in cx.execute("SELECT * FROM offres")]


def test_le_jeu_factice_couvre_chaque_etat(pdf_bouchon):
    from veille.etats import etat_de

    factice.charger()
    offres = _offres_du_jeu()
    etats = {etat_de(o) for o in offres}
    assert {"a_voir", "je_postule", "envoyee", "entretien"} <= etats
    assert any(o["statut"] == "a_traiter" for o in offres)


def test_le_jeu_factice_a_une_relance_due(pdf_bouchon):
    from datetime import date

    factice.charger()
    dues = [
        o for o in _offres_du_jeu()
        if o["statut"] == "candidature_envoyee"
        and o["date_relance_due"]
        and o["date_relance_due"] < date.today().isoformat()
    ]
    assert dues


def test_un_statut_factice_refuse_arrete_le_chargement(pdf_bouchon, monkeypatch):
    lire = factice._lire

    def fausse(nom):
        if nom == "candidatures.yaml":
            return {"candidatures": [
                {"url": "https://offres.exemple.invalid/o/2001", "statut": "refus"},
            ]}
        return lire(nom)

    monkeypatch.setattr(factice, "_lire", fausse)
    with pytest.raises(RuntimeError, match="statut refusé : refus"):
        factice.charger()
    with db.connexion() as cx:
        assert cx.execute("SELECT COUNT(*) FROM evenements WHERE type LIKE 'statut:%'").fetchone()[0] == 0
