"""Automatisme industriel : un autre métier, donc écarté.

L'exemple, Camille, est testeuse logiciel, et son premier métier est
l'automatisation des tests. L'automatisme industriel (automates programmables,
robots, convoyeurs, mise en service sur site) est un autre métier : elle n'y
prétend pas. Ce n'est pas une préférence, c'est de l'employabilité.

⚠️ **LE PIÈGE.** Les deux métiers partagent leurs mots : « automatisation »,
« automation », « automaticien », « Automatisierung ». Et les entrepôts de son
domaine, la logistique, recrutent les deux. Une exclusion sur le mot seul lui
coûterait sa famille la mieux notée.

Ce fichier verrouille le mécanisme d'un éliminatoire à deux étages,
`toujours_motifs` et `sauf_si`. Le corpus est inventé : intitulés et employeurs.
Les cas imposés sont marqués ⭐.

La règle, du plus spécifique au plus général :

1. l'intitulé parle-t-il d'automatisme ou d'automatisation ? sinon, on ne
   touche à rien ;
2. l'intitulé porte-t-il un **signal industriel sans ambiguïté** (automate
   programmable, PLC, robotique, convoyeur, mise en service) ? alors on écarte,
   même si une famille est reconnue ;
3. l'offre a-t-elle reçu une **famille** de son métier ? alors on garde ;
4. l'annonce porte-t-elle un **signal de son terrain** (test, recette,
   logiciel, application, ses outils) dans l'intitulé, l'employeur ou le
   corps ? alors on garde ;
5. sinon seulement, on écarte.

L'asymétrie est voulue : un faux maintien coûte un coup d'œil, un faux
écartement coûte un poste.
"""

from __future__ import annotations

import pytest

from veille.config import charger_criteres
from veille.models import Offre
from veille.scoring import scorer


@pytest.fixture(scope="module")
def criteres():
    return charger_criteres()


def _juger(criteres, titre: str, employeur: str = "", description: str = "") -> Offre:
    return scorer(
        Offre(titre=titre, employeur=employeur, lieu="Mulhouse",
              description=description or titre, source="test:ai"),
        criteres,
    )


def _ecartee_automatisme(o: Offre) -> bool:
    return bool(o.rejete_auto and "automatisme industriel" in (o.motif_rejet_auto or "").lower())


# --------------------------------------------------------------------------
# ⭐ Les cas imposés
# --------------------------------------------------------------------------


@pytest.mark.parametrize("titre,employeur", [
    ("Ingénieure automatisation des tests – entrepôt connecté (H/F)", "Exemple Logistique SA"),
    ("Test Automation Engineer – Warehouse Systems (m/w/d)", "Muster Logistik AG"),
    ("Automaticienne de tests web et mobile", "Une societe"),
    ("QA Automation Engineer / Automatisierung", "Une societe"),
])
def test_etoile_son_premier_metier_est_garde(criteres, titre, employeur):
    o = _juger(criteres, titre, employeur)
    assert not _ecartee_automatisme(o), (
        f"ECARTEE A TORT — c'est sa famille la mieux notee : {o.motif_rejet_auto}"
    )


@pytest.mark.parametrize("titre,employeur", [
    ("Automaticien (H/F)", "Usine Exemple SA"),
    ("Technicien automatisme – convoyeurs (H/F)", "Entrepôt Exemple SAS"),
])
def test_etoile_l_automatisme_industriel_est_ecarte(criteres, titre, employeur):
    o = _juger(criteres, titre, employeur)
    assert _ecartee_automatisme(o), f"pas ecartee : score {o.score}, famille {o.famille!r}"


# --------------------------------------------------------------------------
# Tout le recouvrement, sur un corpus inventé
# --------------------------------------------------------------------------

A_GARDER = [
    ("Ingénieur automatisation des tests H/F", "Exemple Logistique SA"),
    ("Automaticien de tests logiciels (H/F)", "Entrepôt Exemple SAS"),
    ("Test Automation Engineer (Appium)", "Example Robotics Ltd"),
    ("Senior QA Automation Engineer – WMS", "Muster Logistik AG"),
    ("Ingenieur Testautomatisierung / Automatisierung (m/w/d)", "Muster Logistik AG"),
    ("Automatisation des tests de non-régression (H/F)", "Une societe"),
    ("Testeur automaticien H/F", "Une societe"),
    ("SDET – Automation Framework", "Example Robotics Ltd"),
    ("Automation Tester – Lagerverwaltungssoftware", "Muster Logistik AG"),
    # Son terrain dit dans l'intitule : garde, meme sans famille attribuee.
    ("Automaticienne – applications mobiles (H/F)", "Une societe"),
    ("Automation Engineer – pytest / JMeter", "Une societe"),
    ("Spécialiste automatisation – recette du WMS", "Exemple Logistique SA"),
    ("Ingénieure en automatisation – tests d'API", "Une societe"),
    ("Automation QA – application mobile", "Une societe"),
    ("DevOps Automation Engineer", "Une societe"),
    # « Logiciel » dit dans l'intitule : c'est du logiciel, meme chez un
    # fabricant de convoyeurs.
    ("Ingénieur automatisation – logiciel de pilotage d'entrepôt", "Convoyeurs Exemple SA"),
    ("Automatisierung Software (m/w/d)", "Muster Logistik AG"),
    # « API » seul ne garde pas (c'est aussi l'automate programmable) ;
    # Postman, si.
    ("Automation Engineer – API / Postman", "Une societe"),
]

A_ECARTER = [
    ("Automaticien (H/F)", "Usine Exemple SA"),
    ("Technicien automatisme – convoyeurs (H/F)", "Entrepôt Exemple SAS"),
    ("Automaticienne – programmation d'automates programmables", "Usine Exemple SA"),
    ("Ingénieur automatisme industriel H/F", "Usine Exemple SA"),
    ("Automation Engineer PLC (m/f/d)", "Example Robotics Ltd"),
    ("SPS-Programmierer Automatisierung (m/w/d)", "Muster Automation GmbH"),
    ("Automatiker EFZ (m/w/d)", "Muster Automation GmbH"),
    ("Technicien de maintenance – automatismes et robotique", "Usine Exemple SA"),
    ("Techniker Automatisierung und Robotik (m/w/d)", "Muster Automation GmbH"),
    ("Automaticien mise en service – lignes de convoyage", "Convoyeurs Exemple SA"),
    ("Inbetriebnahmetechniker Automation (m/w/d)", "Muster Automation GmbH"),
    ("Automaticien GTB (H/F)", "Exemple Bâtiment SAS"),
    ("Responsable automatisme et électrotechnique", "Usine Exemple SA"),
    ("Automation Technician – Conveyor Systems", "Example Robotics Ltd"),
    ("Électricien automaticien (H/F)", "Exemple Bâtiment SAS"),
    ("Automation Engineer – SCADA", "Example Robotics Ltd"),
    ("Projeteur automatisme (H/F)", "Usine Exemple SA"),
    ("Chef d'équipe automatisation – ligne de production", "Usine Exemple SA"),
    # En français, l'API est aussi l'automate programmable industriel.
    ("Automaticien API (H/F)", "Usine Exemple SA"),
]


@pytest.mark.parametrize("titre,employeur", A_GARDER, ids=lambda v: str(v)[:46])
def test_le_recouvrement_est_garde(criteres, titre, employeur):
    o = _juger(criteres, titre, employeur)
    assert not _ecartee_automatisme(o), f"ECARTEE A TORT : {o.motif_rejet_auto}"


@pytest.mark.parametrize("titre,employeur", A_ECARTER, ids=lambda v: str(v)[:46])
def test_l_automatisme_industriel_est_ecarte(criteres, titre, employeur):
    o = _juger(criteres, titre, employeur)
    assert _ecartee_automatisme(o), f"pas ecartee : score {o.score}, famille {o.famille!r}"


# --------------------------------------------------------------------------
# Les garde-fous de la règle elle-même
# --------------------------------------------------------------------------


def test_une_offre_sans_vocabulaire_d_automatisme_nest_pas_concernee(criteres):
    """La regle ne doit pas deborder sur le reste du flux : un signal
    industriel seul, sans le mot du metier, ne suffit pas."""
    for titre in ("Ingénieur robotique (H/F)", "Test Manager",
                  "Business Analyst", "Développeur TypeScript"):
        o = _juger(criteres, titre)
        assert not _ecartee_automatisme(o), titre


def test_un_signal_industriel_l_emporte_sur_la_famille(criteres):
    """« Test Engineer » donne une famille, mais « PLC » ne peut rien vouloir
    dire d'autre : le signal sans ambiguïté court-circuite le filet."""
    o = _juger(criteres, "Test Engineer – Automation PLC (m/w/d)", "Muster Automation GmbH")
    assert o.famille, "le test doit porter sur une offre qui a recu une famille"
    assert _ecartee_automatisme(o), f"pas ecartee : score {o.score}, famille {o.famille!r}"


def test_le_texte_de_lannonce_peut_rattraper_un_intitule_muet(criteres):
    """« Automaticien » avec un corps qui parle de tests logiciels reste une
    offre a elle.

    C'est le sens de l'ordre : le signal specifique l'emporte sur l'intitule
    generique, jamais l'inverse.
    """
    o = _juger(
        criteres,
        "Automaticien (H/F)",
        "Un logisticien",
        "Automaticien. Vous automatisez les tests de notre logiciel de gestion "
        "d'entrepot et maintenez les scripts pytest avec les equipes "
        "metier.",
    )
    assert not _ecartee_automatisme(o), o.motif_rejet_auto


def test_le_motif_dit_pourquoi(criteres):
    """Elle doit pouvoir contester la decision, donc la comprendre."""
    o = _juger(criteres, "Technicien automatisme – convoyeurs (H/F)", "Entrepôt Exemple SAS")
    ligne = next(c for c in o.explication if "automatisme industriel" in c.libelle.lower())
    assert ligne.detail, "le motif doit etre explicite"
    assert "convoyeur" in ligne.detail.lower()
