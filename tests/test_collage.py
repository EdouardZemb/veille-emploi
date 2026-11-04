"""Le collage du texte complet, vu de bout en bout.

Ce qui décidera de l'usage réel, c'est que son geste serve visiblement à
quelque chose. Ces tests vérifient donc surtout ce qui lui est *montré* :
la phrase exacte qui a déclenché une détection, la montée comme la chute, et
la possibilité de revenir en arrière.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from veille import db, enrichissement
from veille.app import app
from veille.models import Offre
from veille.scoring import scorer
from tests.aide_session import connecter

# Une annonce realiste : l'astreinte et le week-end sont noyes dans le texte,
# exactement comme dans la vraie vie.
ANNONCE_AVEC_PIEGE = """
Test Manager (H/F) — Mulhouse

Rejoignez une equipe de dix personnes au sein de notre direction informatique.
Vous piloterez les campagnes de recette applicative et animerez les comites de
validation avec les equipes metier.

Vos missions :
- definir la strategie de test des projets du domaine
- animer les campagnes et suivre les anomalies
- accompagner la montee en competence des testeurs

Conditions particulieres : le poste comporte une astreinte une semaine sur
quatre, avec interventions le week-end en cas d'incident majeur.

Remuneration entre 46000 et 50000 euros selon profil et experience.
"""

ANNONCE_QUI_REVELE_MIEUX = """
Ingenieur Qualite (H/F) — Mulhouse

Au sein de notre direction, vous interviendrez sur la recette de notre logiciel
de gestion d'entrepot. Vous prendrez en charge l'automatisation des tests de
l'application mobile des preparateurs, et la migration de donnees vers le
nouveau referentiel.

Vous participerez egalement aux audits d'accessibilite RGAA lances cette
annee.

Environnement : Python, pytest, Appium. Remuneration selon profil.
"""


@pytest.fixture(autouse=True)
def base_prete():
    """Les tests qui n'ouvrent pas le client web ont besoin des tables aussi."""
    db.initialiser()


@pytest.fixture
def client():
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        yield c


def _offre(titre: str) -> int:
    with db.connexion() as cx:
        cx.execute("DELETE FROM offres WHERE source = 'test:collage'")
    o = scorer(Offre(
        titre=titre, employeur="Societe Test Collage", lieu="Mulhouse",
        description="Poste a pourvoir. Voir l'annonce.",   # extrait pauvre
        url="https://www.linkedin.com/jobs/view/4000000001",
        source="test:collage", donnees_partielles=True,
    ))
    oid, _ = db.enregistrer_offre(o)
    return oid


# --------------------------------------------------------------------------
# La phrase exacte de l'annonce
# --------------------------------------------------------------------------


def test_la_phrase_qui_a_declenche_la_detection_est_citee():
    """Lui dire « astreinte détectée » ne vaut rien s'il ne peut pas vérifier."""
    oid = _offre("Test Manager")
    r = enrichissement.appliquer_texte(oid, ANNONCE_AVEC_PIEGE, "colle a la main")
    assert r.ok

    astreinte = next(
        (p for p in r.revelations_defavorables if "astreinte" in p.libelle.lower()), None
    )
    assert astreinte is not None, "l'astreinte doit etre signalee"
    assert astreinte.phrase, "la phrase de l'annonce doit etre citee"
    assert "une semaine sur" in astreinte.phrase.lower()


def test_phrase_autour_trouve_malgre_accents_et_casse():
    texte = "Vous participerez à une Astreinte hebdomadaire selon le planning."
    assert "astreinte" in enrichissement.phrase_autour(texte, "astreinte").lower()


def test_phrase_autour_ne_rend_rien_si_absent():
    assert enrichissement.phrase_autour("Un texte quelconque.", "astreinte") == ""


# --------------------------------------------------------------------------
# La chute — le cas le plus utile
# --------------------------------------------------------------------------


def test_une_offre_au_dessus_du_seuil_qui_tombe_est_signalee():
    # Sa premiere famille : sur un extrait, un intitule de pilotage resterait
    # sous le seuil de l'exemple.
    oid = _offre("Test Automation Engineer")
    avant = db.lire_offre(oid)
    assert avant["score"] >= 45

    r = enrichissement.appliquer_texte(oid, ANNONCE_AVEC_PIEGE, "colle a la main")
    assert r.alerte_eliminatoire
    assert "astreinte" in r.alerte_eliminatoire.lower()
    assert "week-end" in r.alerte_eliminatoire.lower()
    assert r.score_apres <= r.score_avant or db.lire_offre(oid)["rejete_auto"]
    assert db.lire_offre(oid)["statut"] == "ecartee"


def test_le_salaire_cache_dans_le_corps_est_retrouve():
    oid = _offre("Test Manager")
    r = enrichissement.appliquer_texte(oid, ANNONCE_AVEC_PIEGE, "colle a la main")
    assert "46" in r.salaire_trouve
    assert db.lire_offre(oid)["salaire_min"] == 46000


# --------------------------------------------------------------------------
# La montée — elle compte autant
# --------------------------------------------------------------------------


def test_un_texte_complet_peut_faire_monter_une_offre():
    """Une offre peut cacher de l'automatisation, de l'accessibilite ou du
    mobile que l'extrait ne laissait pas voir."""
    oid = _offre("Ingenieur Qualite")
    avant = db.lire_offre(oid)["score"]
    r = enrichissement.appliquer_texte(oid, ANNONCE_QUI_REVELE_MIEUX, "colle a la main")
    assert r.ok
    assert r.score_apres > avant, "le texte revele de l'automatisation et de l'accessibilite"
    assert not r.alerte_eliminatoire
    assert r.revelations_favorables, "les gains doivent etre montres, pas seulement le score"
    libelles = " ".join(p.libelle.lower() for p in r.revelations_favorables)
    assert "accessibilit" in libelles or "automatisation" in libelles or "mobile" in libelles


# --------------------------------------------------------------------------
# L'extrait d'origine est conservé
# --------------------------------------------------------------------------


def test_lextrait_dorigine_est_conserve():
    """L'extrait vient de la source, le collage vient de lui : on garde les deux."""
    oid = _offre("Test Manager")
    extrait = db.lire_offre(oid)["description"]
    enrichissement.appliquer_texte(oid, ANNONCE_AVEC_PIEGE, "colle a la main")
    with db.connexion() as cx:
        ligne = cx.execute("SELECT extrait_source FROM offres WHERE id=?", (oid,)).fetchone()
    assert ligne["extrait_source"] == extrait


def test_un_second_collage_necrase_pas_loriginal():
    oid = _offre("Test Manager")
    extrait = db.lire_offre(oid)["description"]
    enrichissement.appliquer_texte(oid, ANNONCE_AVEC_PIEGE, "colle a la main")
    enrichissement.appliquer_texte(oid, ANNONCE_QUI_REVELE_MIEUX, "colle a la main")
    with db.connexion() as cx:
        ligne = cx.execute("SELECT extrait_source FROM offres WHERE id=?", (oid,)).fetchone()
    assert ligne["extrait_source"] == extrait


def test_on_peut_revenir_a_lextrait_apres_un_collage_rate(client):
    oid = _offre("Test Manager")
    extrait = db.lire_offre(oid)["description"]
    enrichissement.appliquer_texte(oid, ANNONCE_AVEC_PIEGE, "colle a la main")
    assert db.lire_offre(oid)["description"] != extrait

    r = client.post(f"/api/offres/{oid}/texte/annuler")
    assert r.status_code == 200
    apres = db.lire_offre(oid)
    assert apres["description"] == extrait
    assert apres["donnees_partielles"]
    assert not apres["enrichi_le"]


def test_annuler_sans_enrichissement_est_refuse(client):
    oid = _offre("Test Manager")
    assert client.post(f"/api/offres/{oid}/texte/annuler").status_code == 400


# --------------------------------------------------------------------------
# La fiabilité devient visible
# --------------------------------------------------------------------------


def test_la_fiabilite_du_score_est_exposee_dans_la_liste(client):
    """La plupart des offres reposent sur un extrait sans que rien ne le dise."""
    oid = _offre("Test Manager")
    avant = next(o for o in client.get("/api/offres").json()["offres"] if o["id"] == oid)
    assert avant["donnees_partielles"] is True
    assert not avant.get("enrichi_le")

    enrichissement.appliquer_texte(oid, ANNONCE_QUI_REVELE_MIEUX, "colle a la main")
    apres = next(o for o in client.get("/api/offres?inclure_ecartees=true").json()["offres"]
                 if o["id"] == oid)
    assert apres["donnees_partielles"] is False
    assert apres["enrichi_le"]
    assert apres["enrichi_par"] == "colle a la main"


# --------------------------------------------------------------------------
# Le collage brut
# --------------------------------------------------------------------------


def test_un_collage_avec_miettes_de_navigation_est_nettoye(client):
    """Il colle depuis un site : mise en forme, retours a la ligne en desordre,
    miettes de navigation. A moi de nettoyer, pas a lui."""
    oid = _offre("Test Manager")
    brut = (
        "<nav>Accueil | Offres | Mon compte</nav>"
        "<script>window.dataLayer=[];</script>"
        "<h1>Test Manager</h1>\n\n\n"
        "<p>Vous piloterez les campagnes de recette applicative et animerez les "
        "comites de validation avec les equipes metier.   Astreinte une semaine sur quatre.</p>"
        "<p>Remuneration entre 46000 et 50000 euros selon profil et experience acquise. "
        "Poste base a Mulhouse, au sein d'une equipe de dix personnes.</p>"
        "<footer>Mentions legales — Politique de confidentialite</footer>"
    )
    r = client.post(f"/api/offres/{oid}/texte", json={"texte": brut})
    assert r.status_code == 200, r.text
    texte = db.lire_offre(oid)["description"]
    assert "window.dataLayer" not in texte
    assert "Mentions legales" not in texte
    assert "Astreinte une semaine sur quatre." in texte
    assert "   " not in texte, "les espaces multiples sont normalises"


# --------------------------------------------------------------------------
# La citation : LA phrase declenchante, pas une fenetre autour
#
# Trouve en verifiant l'ecran du telephone, pas en lisant le code : sur une
# vraie offre, le critere « Astreinte » citait la phrase sur la migration de
# donnees. Une citation fausse est pire que pas de citation — il croit avoir
# verifie.
# --------------------------------------------------------------------------

_ANNONCE = (
    "Vous pilotez la recette d'un logiciel de gestion d'entrepot (WMS). "
    "Vous participez a la migration et a la qualite des donnees lors du "
    "changement d'ERP. "
    "Le poste implique une astreinte une semaine sur quatre, avec des "
    "interventions le week-end en cas d'incident. "
    "Remuneration entre 48000 et 58000 euros selon profil."
)


def test_la_citation_est_la_phrase_qui_contient_le_motif():
    p = enrichissement.phrase_autour(_ANNONCE, "astreinte")
    assert "Le poste implique une astreinte" in p
    assert "migration" not in p, "la phrase precedente n'a rien a faire dans la citation"
    assert "Remuneration" not in p, "la phrase suivante non plus"


def test_la_citation_ne_depend_ni_des_accents_ni_de_la_casse():
    texte = "Le poste impose des Astreintes. Une Présence totale est exigée sur site."
    assert "Présence totale" in enrichissement.phrase_autour(texte, "presence totale")


def test_la_citation_traverse_la_ponctuation_interne_du_motif():
    """L'annonce ecrit « week-end », le critere dit « week end » — ou l'inverse."""
    texte = "Rien ici. Des interventions le week-end sont a prevoir. Rien la."
    p = enrichissement.phrase_autour(texte, "week end")
    assert "interventions le week-end" in p
    assert "Rien" not in p


def test_un_motif_absent_ne_cite_rien():
    assert enrichissement.phrase_autour(_ANNONCE, "allemand") == ""


def test_un_pave_sans_ponctuation_est_borne():
    """Certaines annonces collees n'ont ni point ni retour a la ligne."""
    texte = "mot " * 400 + "astreinte " + "mot " * 400
    p = enrichissement.phrase_autour(texte, "astreinte", marge=100)
    assert "astreinte" in p
    assert len(p) < 400, "une citation de 3000 caracteres n'est pas une citation"


def test_revenir_a_lextrait_remet_aussi_le_salaire():
    """« Score sur extrait » doit vouloir dire ce qu'il dit.

    Vu en base apres une demonstration : l'annulation rendait l'extrait mais
    laissait la fourchette de salaire trouvee dans le texte complet. L'offre
    repassait en « donnees partielles » avec des points venus du texte qu'on
    venait de retirer.
    """
    oid = _offre("Ingenieur de recette WMS")
    avant = db.lire_offre(oid)
    assert avant["salaire_min"] is None

    enrichissement.appliquer_texte(
        oid,
        "Poste de recette a Mulhouse. Remuneration entre 48000 et 58000 euros "
        "selon profil. Equipe de dix personnes, projets varies, environnement "
        "stimulant. Le poste est a pourvoir des que possible, en CDI.",
        "colle a la main",
    )
    assert db.lire_offre(oid)["salaire_min"] == 48000

    db.annuler_texte_complet(oid)
    db.rescorer_offre(oid)
    apres = db.lire_offre(oid)
    assert apres["salaire_min"] is None, "le salaire venait du texte retire"
    assert apres["donnees_partielles"]
    assert apres["score"] == avant["score"], "le score doit revenir a l'identique"
