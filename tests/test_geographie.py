"""La règle géographique — trois cas, un seul passe.

Écrits après le premier retour d'usage : des annonces remontaient au-dessus du
seuil alors qu'elles n'étaient pas en télétravail et qu'elles étaient trop loin.

Les formulations ci-dessous sont celles du corpus réel. Les employeurs sont
inventés, et les lieux de la région sont ceux de l'exemple.
"""

from __future__ import annotations

import pytest

from veille.config import charger_criteres
from veille.models import Offre
from veille.scoring import detecter_teletravail, scorer


@pytest.fixture(scope="module")
def criteres():
    return charger_criteres()


def _score(criteres, **kwargs) -> Offre:
    return scorer(Offre(**{"titre": "Software Engineer", **kwargs}), criteres)


def _ligne(offre: Offre, fragment: str):
    return next((c for c in offre.explication if fragment.lower() in c.libelle.lower()), None)


# --------------------------------------------------------------------------
# Détection du télétravail
# --------------------------------------------------------------------------


def test_remote_first_avec_bureau_nest_pas_du_teletravail_complet(criteres):
    """LE cas qui a déclenché le retour : cette offre était en tête de liste."""
    o = Offre(
        titre="Quality Assurance Engineer",
        employeur="Exemple Analytics",
        lieu="Zürich, Zürich, Switzerland",
        description="Enjoy remote-first culture with hybrid options (office in Zürich) when it fits best.",
    )
    niveau, _ = detecter_teletravail(o, criteres)
    assert niveau == "partiel"


@pytest.mark.parametrize(
    "description",
    [
        "Fully remote and global, we are in the middle of something bigger.",
        "This position is 100% remote.",
        "You can work from anywhere in Europe.",
        "Poste en teletravail integral.",
    ],
)
def test_un_engagement_ferme_vaut_teletravail_complet(criteres, description):
    o = Offre(titre="Software Engineer", lieu="", description=description)
    assert detecter_teletravail(o, criteres)[0] == "complet"


@pytest.mark.parametrize(
    "description",
    [
        "Flexibilite Hybride : 2 jours de teletravail par semaine.",
        "3 days in-office in central Paris, with 2 days WFH.",
        "Wir bieten Dir die Option auf mobiles Arbeiten.",
    ],
)
def test_une_exigence_de_presence_vaut_teletravail_partiel(criteres, description):
    o = Offre(titre="Software Engineer", lieu="Paris", description=description)
    assert detecter_teletravail(o, criteres)[0] == "partiel"


@pytest.mark.parametrize(
    "description",
    [
        "Employees primarily work from their office 5 days a week.",
        "Travail en presentiel dans nos locaux.",
        "Anwesenheit vor Ort erforderlich.",
    ],
)
def test_une_presence_a_temps_plein_est_distinguee_de_lhybride(criteres, description):
    """« 5 days a week » au bureau n'est pas de l'hybride : c'est du presentiel
    integral. La distinction decide si Colmar passe ou non."""
    o = Offre(titre="QA Engineer", lieu="Munich", description=description)
    assert detecter_teletravail(o, criteres)[0] == "presentiel"


def test_le_silence_de_lannonce_nest_pas_du_presentiel(criteres):
    """Le cas le plus frequent, et le piege : assimiler le silence a une
    exigence de presence ecarterait la moitie du Grand Est."""
    o = Offre(titre="QA Engineer", lieu="Colmar", description="Rejoignez notre equipe.")
    assert detecter_teletravail(o, criteres)[0] == "inconnu"
    note = scorer(o, criteres)
    assert not note.rejete_auto
    assert any("non précisé" in c.libelle.lower() for c in note.explication)


def test_un_avantage_bureau_ne_contredit_pas_le_teletravail_complet(criteres):
    """Ma première correction écartait à tort un poste réellement distant : « home
    office budget » dans les avantages n'est pas une exigence de présence."""
    o = Offre(
        titre="Senior Software Engineer",
        employeur="Nuagia",
        lieu="Remote - Remote",
        description=(
            "Fully remote and global. Work from anywhere with the setup that suits you, "
            "home office budget, co-working space support, and flexible working hours."
        ),
    )
    assert detecter_teletravail(o, criteres)[0] == "complet"


def test_le_lieu_remote_suffit(criteres):
    o = Offre(titre="Software Engineer", lieu="Remote - Remote", description="Rejoins-nous.")
    assert detecter_teletravail(o, criteres)[0] == "complet"


@pytest.mark.parametrize(
    "lieu,attendu",
    [
        # Formulations relevees sur ses vraies alertes.
        ("France (À distance)", "complet"),
        ("Bâle (Hybride)", "partiel"),
        ("Mulhouse (Sur site)", "presentiel"),
        ("Strasbourg (67)", "inconnu"),
    ],
)
def test_le_champ_lieu_porte_le_mode_de_travail(criteres, lieu, attendu):
    """Regression : « France (À distance) » etait lu comme « rien d'annonce »,
    puis ecarte comme hors zone. Des offres en teletravail complet perdues."""
    o = Offre(titre="QA Engineer", lieu=lieu, description="Rejoignez notre equipe.")
    assert detecter_teletravail(o, criteres)[0] == attendu


def test_une_offre_full_remote_en_france_nest_plus_ecartee(criteres):
    o = scorer(Offre(titre="QA/Testeur Logiciel Full Remote", employeur="EXEMPLAR",
                     lieu="France (À distance)", description="Poste ouvert partout en France."),
               criteres)
    assert not o.rejete_auto
    assert o.zone == "teletravail_total"


def test_le_pied_de_page_de_lagregateur_est_ignore(criteres):
    """« Find Jobs in Switzerland on Arbeitnow Full remote possible. » parle du
    site de l'agrégateur, pas du poste. Des offres en dépendaient."""
    o = Offre(
        titre="Senior Manager, QA Engineering",
        lieu="Munich",
        description=(
            "You will lead the QA team in our Munich office. "
            "Find Jobs in Switzerland on Arbeitnow Full remote possible."
        ),
    )
    assert detecter_teletravail(o, criteres)[0] != "complet"


# --------------------------------------------------------------------------
# Cas 1 : télétravail complet — recevable partout
# --------------------------------------------------------------------------


def test_le_teletravail_complet_passe_ou_que_soit_lemployeur(criteres):
    o = _score(criteres, employeur="Nuagia", lieu="Remote - Remote",
               description="Fully remote and global.")
    assert not o.rejete_auto
    assert o.zone == "teletravail_total"
    assert _ligne(o, "Zone").points == 18


def test_un_full_remote_chez_un_employeur_lointain_est_signale(criteres):
    """« Fully remote » a Londres veut presque toujours dire « fully remote au
    Royaume-Uni ». Reperé sur une offre reelle du corpus."""
    o = _score(criteres, titre="Warehouse Test Analyst", lieu="London",
               description="This is a fully remote position.")
    assert not o.rejete_auto
    ligne = _ligne(o, "hors de France")
    assert ligne is not None
    assert "entite" in ligne.detail.lower()


def test_un_full_remote_francais_nest_pas_signale(criteres):
    o = _score(criteres, lieu="Remote - Remote", description="Poste en teletravail complet.")
    assert _ligne(o, "hors de France") is None


def test_un_employeur_suisse_en_full_remote_est_signale_sans_etre_ecarte(criteres):
    """Au-delà de 40 % de télétravail depuis la France, son statut de
    frontalier est remis en cause. Son choix : signaler, pas écarter."""
    o = _score(criteres, employeur="Exemplia", lieu="Basel, Switzerland",
               description="This role is 100% remote.")
    assert not o.rejete_auto
    avertissement = _ligne(o, "employeur suisse")
    assert avertissement is not None
    assert "frontalier" in avertissement.detail.lower()


# --------------------------------------------------------------------------
# Cas 2 : présence exigée, zone atteignable
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lieu,zone", [
    ("Basel, Switzerland", "zone_proche"),
    ("Saint-Louis", "zone_proche"),
    ("Mulhouse", "zone_trajet"),
    ("Altkirch", "zone_trajet"),
])
def test_presentiel_dans_le_rayon_quotidien_passe(criteres, lieu, zone):
    """L'exemple a deux rayons quotidiens : l'agglomération, puis le trajet."""
    o = _score(criteres, lieu=lieu, description="Poste en presentiel dans nos locaux.")
    assert not o.rejete_auto, lieu
    assert o.zone == zone


def test_hybride_a_colmar_passe(criteres):
    """~70 km : tenable deux jours par semaine."""
    o = _score(criteres, lieu="Colmar", description="Hybride : 2 jours sur site par semaine.")
    assert not o.rejete_auto
    assert o.zone == "zone_occasionnelle"


def test_presentiel_quotidien_a_colmar_est_ecarte(criteres):
    """C'est la distinction que la zone occasionnelle apporte : 70 km tous les
    jours, l'exemple répond non."""
    o = _score(criteres, lieu="Colmar", description="Presence sur site tous les jours.")
    assert o.rejete_auto
    assert "chaque jour" in o.motif_rejet_auto.lower()


# --------------------------------------------------------------------------
# Cas 3 : présence exigée hors zone — éliminatoire
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lieu,description",
    [
        ("Nantes, Loire-Atlantique", "Flexibilite Hybride : 2 jours de teletravail par semaine."),
        ("Paris Office", "3 days in-office in central Paris."),
        ("London", "You will join our London team."),
        ("Berlin", "Flexible working hours in our Berlin office."),
        ("Zurich", "Software Engineer, Platform - Zurich."),
        ("Karlsruhe", "Wir bieten mobiles Arbeiten."),
        ("Munich", "Employees work from their office 5 days a week."),
    ],
)
def test_les_offres_qui_le_genaient_sont_maintenant_ecartees(criteres, lieu, description):
    o = _score(criteres, lieu=lieu, description=description)
    assert o.rejete_auto, f"{lieu} devrait etre ecartee"
    assert ("zone géographique" in o.motif_rejet_auto.lower()
            or "chaque jour" in o.motif_rejet_auto.lower())


def test_le_motif_geographique_est_visible_dans_lexplication(criteres):
    """Il doit pouvoir vérifier que la règle ne se trompe pas."""
    o = _score(criteres, lieu="Toulouse", description="Poste en presentiel.")
    ligne = _ligne(o, "ÉLIMINATOIRE - hors de ta zone")
    assert ligne is not None
    assert "Toulouse" in ligne.detail


def test_une_offre_parfaite_hors_zone_reste_ecartee(criteres):
    """« Une offre parfaite à Toulouse n'est pas une offre. »"""
    o = _score(
        criteres,
        titre="Test Automation Engineer",
        lieu="Toulouse",
        description="AI governance, pytest, Java. Presence sur site.",
        salaire_min=60000, salaire_max=70000, salaire_devise="EUR",
        type_contrat="CDI",
    )
    assert o.rejete_auto
    assert o.score > 45, "le score reste calcule, pour qu'il puisse verifier le rejet"


# --------------------------------------------------------------------------
# Lieu inconnu
# --------------------------------------------------------------------------


def test_un_lieu_absent_nest_pas_eliminatoire_mais_signale(criteres):
    """Des offres du corpus sont dans ce cas, dont de vraies opportunités."""
    o = _score(criteres, lieu="", description="Rejoins notre equipe produit.")
    assert not o.rejete_auto
    ligne = _ligne(o, "Lieu non précisé")
    assert ligne is not None
    assert ligne.points < 0


# --------------------------------------------------------------------------
# Lieu trop large pour trancher
#
# Trouve dans le corpus : un lieu qui designe une region entiere — celle de la
# zone proche — etait ecarte avec le motif « trop loin pour s'y rendre chaque
# jour ». Des offres pertinentes, jetees. France Travail rendra beaucoup de
# lieux de ce grain.
#
# Dans l'exemple, sa region est le Sundgau, autour de Saint-Louis ; le Grand
# Est, qui la contient a peine, est une region large.
# --------------------------------------------------------------------------


def _o(lieu: str, description: str = "Poste sur site.") -> Offre:
    return scorer(Offre(titre="Automaticienne de tests", lieu=lieu,
                        description=description, source="test:geo"))


def test_sa_propre_region_nest_pas_ecartee_comme_trop_loin():
    o = _o("Sundgau, France (Sur site)")
    assert not o.rejete_auto, f"ecartee a tort : {o.motif_rejet_auto}"
    libelles = [c.libelle for c in o.explication]
    assert any("imprécis" in l.lower() for l in libelles), libelles


def test_sa_region_nest_pas_penalisee_comme_un_lieu_inconnu():
    """« Sundgau » est imprecis, pas lointain : l'information reste positive.

    Penalise comme un lieu inconnu, un bon poste tombait au bas du flux : dans
    le flux, mais invisible. Ni faux negatif (ecarte), ni faux positif (points
    de zone) : neutre, et signale.
    """
    o = _o("Sundgau, France (Sur site)")
    ligne = next(c for c in o.explication if "imprécis" in c.libelle.lower())
    assert ligne.points == 0
    assert o.zone == "", "un lieu imprecis ne vaut aucune zone"
    assert o.lieu in ligne.detail, "le detail doit citer ce que l'annonce dit"
    assert "demande la ville" in ligne.detail.lower()


def test_un_lieu_qui_ne_dit_rien_est_penalise():
    o = _o("France entiere")
    ligne = next(c for c in o.explication if "imprécis" in c.libelle.lower())
    assert ligne.points < 0, "« France entiere » ne vaut pas « Grand Est »"
    assert not o.rejete_auto


def test_une_ville_dans_la_region_reste_precise():
    """« Mulhouse, Grand Est » ne doit pas devenir imprecis."""
    o = _o("Mulhouse, Grand Est, France")
    libelles = [c.libelle for c in o.explication]
    assert not any("imprécis" in l.lower() for l in libelles), libelles
    assert o.zone, "Mulhouse reste dans sa zone quotidienne"


def test_une_ville_lointaine_reste_ecartee():
    """La correction ne doit pas rouvrir la porte a tout."""
    o = _o("Paris, France")
    assert o.rejete_auto
    assert "hors de ta zone" in o.motif_rejet_auto
