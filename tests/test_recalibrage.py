"""La hiérarchie des familles et des atouts de l'exemple.

Trois décisions de Camille, l'exemple, à faire tenir dans le scoring :
  - l'automatisation des tests est sa première porte, devant le pilotage,
    qu'elle n'a encore jamais tenu : il reste en retrait sans être écarté,
  - chaque autre famille porte son poids, et un intitulé de test générique qui
    nomme une spécialité va à la famille de cette spécialité,
  - l'expérience d'un domaine ne vaut pas la même chose des deux côtés de la
    frontière : dans l'exemple, la logistique, mieux payée à Bâle qu'en France.
"""

from __future__ import annotations

import pytest

from veille.config import charger_criteres
from veille.models import Offre
from veille.scoring import scorer


@pytest.fixture(scope="module")
def criteres():
    return charger_criteres()


def _s(criteres, **kw) -> Offre:
    return scorer(Offre(**{"lieu": "Mulhouse", **kw}), criteres)


def _ligne(o: Offre, fragment: str):
    return next((c for c in o.explication if fragment.lower() in c.libelle.lower()), None)


# --------------------------------------------------------------------------
# Hiérarchie des familles
# --------------------------------------------------------------------------


def test_l_automatisation_passe_devant_le_pilotage(criteres):
    """Sa meilleure porte doit primer sur celle qu'elle ne tiendrait pas encore."""
    auto = _s(criteres, titre="Test Automation Engineer")
    pilotage = _s(criteres, titre="Test Manager")
    assert auto.score > pilotage.score
    assert auto.famille == "automatisation_tests"
    assert pilotage.famille == "pilotage_tests"


def test_le_pilotage_reste_en_retrait_sans_etre_ecarte(criteres):
    """Elle pourra y venir : on ne le met pas en tete, on ne le supprime pas."""
    o = _s(criteres, titre="QA Lead - Responsable recette")
    assert o.famille == "pilotage_tests"
    assert not o.rejete_auto
    assert _ligne(o, "Famille").points == 18


def test_le_test_fonctionnel_reste_a_son_niveau(criteres):
    """Son metier de tous les jours ne bouge pas."""
    o = _s(criteres, titre="Testeuse fonctionnelle")
    assert o.famille == "test_fonctionnel"
    assert _ligne(o, "Famille").points == 24


@pytest.mark.parametrize(
    "titre,famille,poids",
    [
        ("Ingenieure tests de performance", "test_performance", 27),
        ("Ingenieur IVVQ", "qualification_logicielle", 20),
        ("ETL Tester", "recette_donnees", 14),
        ("Ingenieur logiciel", "developpement_outillage", 10),
    ],
)
def test_les_autres_familles_a_leur_poids(criteres, titre, famille, poids):
    o = _s(criteres, titre=titre)
    assert o.famille == famille
    assert _ligne(o, "Famille").points == poids


def test_la_performance_est_reconnue_dans_un_intitule_de_test(criteres):
    """« Performance Test Engineer » contient « test engineer », du test
    generique ; c'est de la performance, et la famille de la performance le dit."""
    o = _s(criteres, titre="Senior Performance Test Engineer")
    assert o.famille == "test_performance"


# --------------------------------------------------------------------------
# Une pratique qui se lit dans le corps de l'annonce : la stack
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description",
    [
        "Vous automatiserez les tests de non-regression en Python.",
        "Backend in Java, deployed on Linux.",
        "Requetes SQL sur une base MySQL.",
        "Scripts de recette en Bash.",
        "Reporting decisionnel sur une base SQL.",
    ],
)
def test_la_stack_pratiquee_bonifie(criteres, description):
    """L'intitule n'en dit rien : c'est le corps de l'annonce qui la revele, et
    elle compte quand meme."""
    o = _s(criteres, titre="Consultant", description=description)
    assert "stack_pratiquee" in o.atouts, description


def test_la_stack_pratiquee_est_plafonnee(criteres):
    o = _s(criteres, titre="Consultant",
           description="Python, Java, Bash, SQL, MySQL, Linux.")
    c = _ligne(o, "Stack technique")
    assert c.points == 12
    assert "plafonné" in c.detail


# --------------------------------------------------------------------------
# Le domaine vaut différemment selon le pays
# --------------------------------------------------------------------------


def test_la_logistique_vaut_plus_en_suisse_quen_france(criteres):
    """A Bale, plaque tournante du fret, l'experience logistique se paie ; en
    France elle compte moins."""
    fr = _s(criteres, titre="QA Engineer", employeur="Rhein Logistique France", lieu="Mulhouse")
    ch = _s(criteres, titre="QA Engineer", employeur="Rhein Logistik AG",
            lieu="Basel, Switzerland")
    assert _ligne(fr, "logistique").points == 6
    assert _ligne(ch, "logistique").points == 12
    assert ch.score > fr.score


def test_les_faux_positifs_logistique_restent_corriges(criteres):
    """La correction precedente ne doit pas avoir saute : un entrepot de donnees
    et une clientele citee dans la description ne sont pas de la logistique."""
    for titre, description in [
        ("Data Warehouse Tester", "Tests fonctionnels."),
        ("Software Engineer", "Our customers include logistics companies."),
    ]:
        o = _s(criteres, titre=titre, description=description)
        assert "domaine_logistique" not in o.atouts, titre


# --------------------------------------------------------------------------
# L'allemand : recevable plus tard
# --------------------------------------------------------------------------


def test_par_defaut_lallemand_penalise_sans_mettre_en_attente(criteres):
    o = _s(criteres, titre="Test Manager", lieu="Basel",
           description="Verhandlungssicheres Deutsch erforderlich.")
    assert not o.differee
    assert not o.rejete_auto


def test_la_mise_en_attente_sort_du_flux_sans_refuser(criteres):
    """Une offre germanophone n'est pas un refus : c'est une offre recevable
    plus tard. Elle revient d'un seul reglage."""
    import copy

    modifies = copy.deepcopy(criteres.brut)
    modifies["langues"]["allemand_exige"]["mise_en_attente"] = True
    from veille.config import Criteres

    o = scorer(
        Offre(titre="Test Manager", lieu="Basel",
              description="Verhandlungssicheres Deutsch erforderlich."),
        Criteres(modifies),
    )
    assert o.differee
    assert not o.rejete_auto, "differer n'est pas refuser"
    assert "allemand" in o.motif_differe.lower()


def test_une_offre_refusee_par_ailleurs_nest_pas_juste_differee(criteres):
    """Inutile de mettre en attente ce qui est deja au rebut."""
    import copy

    from veille.config import Criteres

    modifies = copy.deepcopy(criteres.brut)
    modifies["langues"]["allemand_exige"]["mise_en_attente"] = True
    o = scorer(
        Offre(titre="Test Manager", lieu="Hamburg",
              description="Gute Deutschkenntnisse. Astreinte une semaine sur quatre."),
        Criteres(modifies),
    )
    assert o.rejete_auto
    assert not o.differee
