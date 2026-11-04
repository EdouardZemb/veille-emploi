"""Couverture des intitulés d'offres.

Écrits à l'origine après l'analyse des offres restées sans famille. Les intitulés
ci-dessous sont ceux des familles de l'exemple, Camille Exemple, testeuse.

La leçon, déjà apprise sur un intitulé français : les motifs étaient en anglais
alors que les alertes françaises parlent français, et les alertes jobs.ch
parlent allemand.
"""

from __future__ import annotations

import pytest

from veille.config import charger_criteres, contient, normaliser
from veille.models import Offre
from veille.scoring import scorer


@pytest.fixture(scope="module")
def criteres():
    return charger_criteres()


def _famille(criteres, titre: str) -> str:
    return scorer(Offre(titre=titre, lieu="Mulhouse"), criteres).famille


# --------------------------------------------------------------------------
# La barre oblique
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texte,motif",
    [
        ("Ingénieur qualification/validation H/F", "qualification validation"),
        ("Technicien / Technicienne Validation Fonctionnelle", "validation fonctionnelle"),
        ("MES Ingenieur/in (50%)", "mes ingenieur"),
    ],
)
def test_la_barre_oblique_vaut_separateur(texte, motif):
    """Regression : « qualification/validation » ne repondait pas au motif
    « qualification validation », la barre etant gardee pour « ci/cd »."""
    assert contient(normaliser(texte), motif)


def test_ci_cd_reste_reconnu():
    """La correction ne doit pas casser ce pour quoi la barre etait gardee."""
    assert contient(normaliser("Pipeline CI/CD moderne"), "ci/cd")


# --------------------------------------------------------------------------
# Vocabulaire français de l'automatisation — sa première porte
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "titre",
    [
        "Automaticien de tests H/F",
        "Automaticienne de test (F/H)",
        "Ingénieur automatisation des tests H/F",
        "Ingénieur(e) en automatisation de tests",
        "Spécialiste de l'automatisation de tests",
        "Ingénieur tests automatisés - H/F",
        "Testeur automaticien H/F",
        "Ingénieur QA Automatisation H/F",
        "Développeur en automatisation des tests H/F",
        "Automatisation de test et recette H/F",
    ],
)
def test_le_vocabulaire_francais_de_son_premier_metier_est_reconnu(criteres, titre):
    """Dix intitules francais de la famille d'automatisation de l'exemple : ni
    « testeur » ni « developpeur » ne doivent l'emporter."""
    assert _famille(criteres, titre) == "automatisation_tests", titre


# --------------------------------------------------------------------------
# Allemand — ses alertes jobs.ch sont dans cette langue
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "titre,famille",
    [
        ("Softwaretester (m/w/d)", "test_fonctionnel"),
        ("Fachtester", "test_fonctionnel"),
        ("Testmanager 80-100%", "pilotage_tests"),
        ("Qualitätssicherung Spezialist", "test_fonctionnel"),
        ("Testautomatisierer (m/w/d)", "automatisation_tests"),
        ("Ingenieur Testautomatisierung", "automatisation_tests"),
        ("Performancetester (m/w/d)", "test_performance"),
        ("Datenqualität Analyst", "recette_donnees"),
        ("Systemtester Software", "qualification_logicielle"),
        ("Testleiter Software (m/w/d)", "pilotage_tests"),
    ],
)
def test_le_vocabulaire_allemand_est_reconnu(criteres, titre, famille):
    assert _famille(criteres, titre) == famille, titre


# --------------------------------------------------------------------------
# Français : les autres familles
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "titre",
    [
        "Sr. Test Engineer",
        "QA Analyst",
        "Senior Manual QA",
        "Senior Software Quality Assurance Engineer",
        "QA Tester (Web & Mobile)",
        "Manual Tester",
        "Software Tester",
        "UAT Tester",
    ],
)
def test_les_variantes_anglaises_de_son_metier(criteres, titre):
    """Huit variantes anglaises de son metier de tous les jours, le test
    fonctionnel."""
    assert _famille(criteres, titre) == "test_fonctionnel", titre


@pytest.mark.parametrize(
    "titre,famille",
    [
        ("Chargé de recette applicative", "test_fonctionnel"),
        ("Consultante recette fonctionnelle", "test_fonctionnel"),
        ("Ingénieur IVVQ", "qualification_logicielle"),
        ("Responsable qualité des données", "recette_donnees"),
        ("Chef de projet recette décisionnelle", "recette_donnees"),
        ("Responsable recette", "pilotage_tests"),
        ("Ingénieure tests de performance", "test_performance"),
    ],
)
def test_les_equivalents_francais_des_familles(criteres, titre, famille):
    assert _famille(criteres, titre) == famille, titre


# --------------------------------------------------------------------------
# Le bruit des lettres d'information
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "faux_titre",
    [
        "cliquez ici", "Mon compte", "Mon centre",
        "Je consulte les tendances", "Je télécharge l'application Apec sur iPhone",
        "Politique de confidentialité", "Mentions légales", "Protection des données",
        "Contactez un conseiller", "Consultez la FAQ", "Gérer les alertes",
        "Votre alerte Emploi pour software tester", "cliquant sur le lien suivant",
        "Ne manquez aucune opportunité d'emploi", "Alle",
    ],
)
def test_la_navigation_des_lettres_dinformation_est_ecartee(faux_titre):
    """Des liens de pied de page etaient enregistres comme des offres."""
    from veille.collectors.parsers.base import est_bruit

    assert est_bruit(faux_titre), f"pris pour une offre : {faux_titre}"


def test_un_vrai_intitule_nest_pas_pris_pour_du_bruit():
    from veille.collectors.parsers.base import est_bruit

    for vrai in ["Ingénieur IVVQ H/F", "Test Manager", "Softwaretester",
                 "Business Analyst ERP", "QA Engineer"]:  # le domaine releve, neutralise
        assert not est_bruit(vrai), vrai


# --------------------------------------------------------------------------
# La hiérarchie reste cohérente
# --------------------------------------------------------------------------


def test_le_developpement_reste_sous_les_metiers_du_test(criteres):
    """Le developpement pur reste en retrait : c'est le test qu'elle vise."""
    poids = {k: v["poids"] for k, v in criteres.familles.items()}
    assert poids["developpement_outillage"] == 10
    assert poids["automatisation_tests"] == 32
    for famille in ("automatisation_tests", "test_performance", "test_fonctionnel",
                    "qualification_logicielle"):
        assert poids["developpement_outillage"] < poids[famille], famille


def test_un_poste_de_dev_ne_prime_pas_sur_l_automatisation(criteres):
    dev = scorer(Offre(titre="Staff Software Engineer", lieu="Remote"), criteres)
    auto = scorer(Offre(titre="Automaticienne de tests", lieu="Mulhouse"), criteres)
    assert auto.score > dev.score
