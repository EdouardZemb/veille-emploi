"""Séparation employeur / lieu, sur la forme des lignes réellement rencontrées.

Les chaînes ci-dessous ont la forme exacte de celles de la première collecte
sur sa vraie boîte mail ; les employeurs et les intitulés sont inventés. Le
défaut observé : le salaire se retrouvait dans le champ employeur, et
l'employeur dans le champ lieu.
"""

from __future__ import annotations

import pytest

from veille.collectors.parsers.base import separer_employeur_lieu


@pytest.mark.parametrize(
    "lignes,employeur,lieu",
    [
        # Format LinkedIn : « Employeur · Ville (Mode) », puis le salaire.
        (
            ["Testeur logiciel H/F – Recette WMS",
             "Exemple Logistik AG · Mulhouse (Sur site)",
             "Entre 42 k € et 47 k € par an",
             "Recrutement actif"],
            "Exemple Logistik AG", "Mulhouse (Sur site)",
        ),
        (
            ["Test Automation Engineer",
             "XY Group (Switzerland) · Bâle (Hybride)",
             "Entre 1 CHF et 2 CHF par heure"],
            "XY Group (Switzerland)", "Bâle (Hybride)",
        ),
        (
            ["Senior Test Automation Engineer",
             "Fictilinx · Bâle (Hybride)",
             "Recrutement actif"],
            "Fictilinx", "Bâle (Hybride)",
        ),
        (
            ["QA engineer", "exem2 Switzerland · Mulhouse (Sur site)"],
            "exem2 Switzerland", "Mulhouse (Sur site)",
        ),
        # Format Indeed : « Employeur - Ville (dept) »
        (
            ["Ingénieur QA H/F", "Entreprise Exemple SA - Mulhouse (68)", "CDI"],
            "Entreprise Exemple SA", "Mulhouse (68)",
        ),
        # Deux lignes distinctes, format LinkedIn classique
        (
            ["Test Automation Engineer", "Exemplia", "Bâle, Bâle-Ville, Suisse"],
            "Exemplia", "Bâle, Bâle-Ville, Suisse",
        ),
    ],
)
def test_separation_sur_des_lignes_reelles(lignes, employeur, lieu):
    e, l = separer_employeur_lieu(lignes, lignes[0])
    assert e == employeur
    assert l == lieu


@pytest.mark.parametrize(
    "ligne",
    [
        "Entre 50 k € et 55 k € par an",
        "Entre 1 CHF et 2 CHF par heure",
        "Entre 100 k CHF et 115 k CHF par an",
        "CHF 100'000 - 115'000",
        "44 000 € par an",
    ],
)
def test_une_ligne_de_salaire_ne_devient_jamais_un_employeur(ligne):
    """Le defaut d'origine : « Entre 50 k € et 55 k € par an » en employeur."""
    e, _ = separer_employeur_lieu(["Titre", ligne], "Titre")
    assert e == "", f"pris pour un employeur : {ligne}"


@pytest.mark.parametrize(
    "ligne",
    ["Recrutement actif", "Actively recruiting", "Candidature simplifiee",
     "Promu", "il y a 3 jours", "2 heures"],
)
def test_les_badges_de_plateforme_sont_ignores(ligne):
    e, _ = separer_employeur_lieu(["Titre", ligne], "Titre")
    assert e == "", f"badge pris pour un employeur : {ligne}"


def test_le_salaire_reste_disponible_pour_le_scoring():
    """On l'ecarte du champ employeur, mais l'extrait le conserve : c'est lui
    qui alimente l'extraction de salaire."""
    from veille.collectors.base import extraire_salaire

    smin, smax, devise = extraire_salaire("Entre 50 k € et 55 k € par an")
    assert (smin, smax, devise) == (50000, 55000, "EUR")


def test_aucune_ligne_exploitable_rend_deux_chaines_vides():
    """Une case vide se voit a la relecture, une valeur inventee non."""
    assert separer_employeur_lieu(["Titre"], "Titre") == ("", "")


def test_indices_de_lieu_de_la_configuration(monkeypatch, request, tmp_path):
    """Une ville présente seulement dans `geographie.indices_lieu` est reconnue comme lieu."""
    from tests.aide_criteres import poser_criteres

    lignes = ["Titre", "Entreprise Exemple SA", "Zzvillebourg"]
    _, lieu = separer_employeur_lieu(lignes, "Titre")
    assert lieu == ""

    def modifier(brut):
        brut.setdefault("geographie", {})["indices_lieu"] = ["zzvillebourg"]

    poser_criteres(monkeypatch, request, tmp_path, modifier)
    employeur, lieu = separer_employeur_lieu(lignes, "Titre")
    assert (employeur, lieu) == ("Entreprise Exemple SA", "Zzvillebourg")


@pytest.mark.parametrize("ville", ["Mulhouse", "Colmar", "Saint-Louis", "Altkirch"])
def test_les_villes_de_l_exemple_sont_des_indices_de_lieu(ville):
    """Sa region n'est pas dans les indices generiques : l'exemple la declare, et une
    ligne « Entreprise · Ville » sans parenthese donne bien un lieu."""
    lignes = ["Titre", f"Entreprise Exemple SA · {ville}"]
    assert separer_employeur_lieu(lignes, "Titre") == ("Entreprise Exemple SA", ville)


def test_les_grandes_villes_restent_reconnues_sans_configuration(monkeypatch, request, tmp_path):
    from tests.aide_criteres import poser_criteres

    poser_criteres(
        monkeypatch, request, tmp_path,
        lambda brut: brut.setdefault("geographie", {}).pop("indices_lieu", None),
    )
    for ville in ("Paris", "Lyon", "Zurich", "Basel", "Strasbourg"):
        _, lieu = separer_employeur_lieu(["Titre", "Entreprise Exemple SA", ville], "Titre")
        assert lieu == ville
