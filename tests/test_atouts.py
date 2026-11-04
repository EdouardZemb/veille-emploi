"""Tests des atouts — les bonus cumulatifs.

Enjeu principal : l'atout le plus rare sur le marche — dans l'exemple,
l'accessibilite numerique. Toute offre parlant de tests ou d'audits
d'accessibilite doit remonter en tete, meme si le reste de l'annonce est
banal.
"""

from __future__ import annotations

import pytest

from veille.config import charger_criteres
from veille.models import Offre
from veille.scoring import scorer


@pytest.fixture(scope="module")
def criteres():
    return charger_criteres()


def _score(criteres, **kwargs) -> Offre:
    # Une ville de la zone la plus large de l'exemple : l'offre reste recevable.
    base = {"titre": "Software Engineer", "lieu": "Colmar"}
    return scorer(Offre(**{**base, **kwargs}), criteres)


def _contribution(offre: Offre, fragment: str):
    return next((c for c in offre.explication if fragment.lower() in c.libelle.lower()), None)


# --------------------------------------------------------------------------
# L'atout accessibilite
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texte",
    [
        "You will run WCAG audits on our web shop.",
        "Mise en conformite RGAA de nos applications.",
        "Mise en place des tests d'accessibilite.",
        "Digital accessibility under the European Accessibility Act.",
        "Screen reader testing with NVDA and VoiceOver.",
        "Audit d'accessibilite numerique, a11y.",
    ],
)
def test_toute_mention_d_accessibilite_declenche_le_bonus(criteres, texte):
    o = _score(criteres, description=texte)
    assert "accessibilite" in o.atouts, texte
    c = _contribution(o, "Accessibilité")
    assert c is not None and c.points == 25


def test_une_offre_accessibilite_banale_depasse_une_offre_de_test_ordinaire(criteres):
    """Le but explicite : son atout rare doit primer sur un bon poste generique."""
    a11y = _score(
        criteres,
        titre="Software Engineer",
        lieu="Colmar",
        description="You will work on WCAG audits and accessibility testing.",
    )
    test_ordinaire = _score(
        criteres, titre="QA Engineer", lieu="Colmar", description="Tests fonctionnels."
    )
    assert a11y.score > test_ordinaire.score


def test_le_bonus_accessibilite_ne_se_declenche_pas_sur_un_mot_isole(criteres):
    """« Accessible » seul est trop generique : on exige une expression parlante."""
    o = _score(criteres, description="Nos bureaux sont accessibles en tram, a deux pas de la gare.")
    assert "accessibilite" not in o.atouts


def test_le_contexte_mobile_est_plus_modeste_que_l_accessibilite(criteres):
    contexte = _score(criteres, description="We build mobile apps for iOS and Android.")
    a11y = _score(criteres, description="We need WCAG audits and accessibility testing.")
    assert "contexte_mobile" in contexte.atouts
    assert "accessibilite" not in contexte.atouts
    assert a11y.score > contexte.score


# --------------------------------------------------------------------------
# Cumul et plafonnement
# --------------------------------------------------------------------------


def test_les_atouts_se_cumulent_avec_la_famille(criteres):
    """Contrairement aux familles, dont une seule s'applique."""
    o = _score(
        criteres,
        titre="Test Automation Engineer",
        lieu="Basel",
        description="pytest, Postman. You will own WCAG compliance for our platform.",
    )
    assert o.famille in ("automatisation_tests", "test_fonctionnel")
    assert {"accessibilite", "outils_test"} <= set(o.atouts)
    assert _contribution(o, "Famille") is not None
    assert _contribution(o, "Accessibilité") is not None
    assert _contribution(o, "Outils de test") is not None


def test_le_plafond_empeche_une_annonce_bavarde_de_gonfler_son_score(criteres):
    peu = _score(criteres, description="We use pytest and Postman.")
    beaucoup = _score(
        criteres,
        description="pytest, Postman, Appium, JMeter, SoapUI, Behave, TestRail, "
        "Redmine, Gatling, LoadRunner, load testing, API testing.",
    )
    plafond = float(criteres.atouts["outils_test"]["plafond"])
    c = _contribution(beaucoup, "Outils de test")
    assert c.points == plafond
    assert "plafonné" in c.detail
    assert beaucoup.score > peu.score  # plus d'outils reste mieux, mais borne


def test_sans_atout_aucune_ligne_parasite(criteres):
    o = _score(criteres, titre="Comptable", lieu="Strasbourg", description="Saisie comptable.")
    assert o.atouts == []
    assert not any("Outils de test" in c.libelle for c in o.explication)


# --------------------------------------------------------------------------
# Les autres atouts
# --------------------------------------------------------------------------


def test_la_stack_pratiquee_est_reconnue(criteres):
    o = _score(criteres, description="Stack : Java, MySQL, Linux.")
    assert "stack_pratiquee" in o.atouts


@pytest.mark.parametrize(
    "titre,employeur",
    [
        ("Test Engineer", "Rhein Logistik AG"),
        ("Testeuse QA - Logistique", "Une societe"),
        ("QA Engineer WMS", "Une societe"),
        ("Ingenieur de test", "Transports Exemple SA"),
    ],
)
def test_domaine_logistique_reconnu(criteres, titre, employeur):
    """Le domaine se lit dans l'intitule ou chez l'employeur."""
    o = _score(criteres, titre=titre, employeur=employeur)
    assert "domaine_logistique" in o.atouts


@pytest.mark.parametrize(
    "titre,description",
    [
        # Un mot voisin n'est pas le domaine : un entrepôt de données (« data
        # warehouse ») n'a rien de logistique, et le motif se cherche en
        # expression entière. Tester un entrepôt de données, c'est du décisionnel.
        ("Testeur BI, entrepôt de données", "Tests fonctionnels."),
        ("Data Warehouse Tester", "Tests fonctionnels."),
        # La description cite une clientele ou des avantages sociaux, pas le
        # poste : le domaine ne se cherche pas dans la description.
        ("Software Engineer", "Our customers include logistics and transport companies."),
        ("Backend Engineer", "Prise en charge de l'abonnement aux transports en commun et tickets restaurant."),
    ],
)
def test_le_domaine_logistique_ne_se_declenche_pas_a_tort(criteres, titre, description):
    o = _score(criteres, titre=titre, description=description)
    assert "domaine_logistique" not in o.atouts, f"faux positif sur : {titre}"


def test_les_champs_restreints_ignorent_la_description(criteres):
    """`champs` limite la recherche : c'est ce qui coupe le bruit."""
    assert criteres.atouts["domaine_logistique"]["champs"] == ["titre", "employeur"]
    dans_titre = _score(criteres, titre="Test Engineer Logistics Company")
    dans_description = _score(criteres, titre="Test Engineer", description="logistics company")
    assert "domaine_logistique" in dans_titre.atouts
    assert "domaine_logistique" not in dans_description.atouts


def test_les_atouts_napparaissent_pas_par_sous_chaine(criteres):
    """"behave" ne doit pas se declencher sur "behaves", ni "llm" au hasard."""
    o = _score(criteres, description="This role behaves like a product owner, "
                                     "with a strong impact on our customers.")
    assert "outils_test" not in o.atouts


# --------------------------------------------------------------------------
# Coherence du score
# --------------------------------------------------------------------------


def test_le_score_reste_la_somme_exacte_des_contributions(criteres):
    o = _score(
        criteres,
        titre="Senior QA Engineer",
        lieu="Basel",
        description="WCAG audits, pytest, Java, iOS. 100% remote.",
        salaire_min=100000,
        salaire_max=115000,
        salaire_devise="CHF",
        type_contrat="CDI",
    )
    assert o.score == pytest.approx(sum(c.points for c in o.explication), abs=0.05)
