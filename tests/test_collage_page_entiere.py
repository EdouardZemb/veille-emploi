"""Le collage d'une page entière, et le bruit qu'il apporte.

Le geste réel n'est pas « sélectionner la description » : c'est Ctrl+A, Ctrl+C
sur l'onglet LinkedIn, puis coller. Ce qui arrive contient donc la colonne
« Offres similaires », les « Personnes également consultées » et le pied de
page — c'est-à-dire **d'autres annonces**.

Le risque est asymétrique, et c'est ce qui le rend grave :

- une astreinte mentionnée dans l'offre **voisine** disqualifierait la bonne
  offre, en citant une phrase qui ne la concerne pas ;
- les intitulés voisins gonfleraient le score avec des familles et des atouts
  absents du poste.

⚠️ **D'où vient l'échantillon.** LinkedIn interdit la lecture automatisée
(`robots.txt` : `Disallow: /`), donc cette page n'a pas été capturée : elle est
**reconstituée** à partir de la structure connue de leurs pages d'offre. Les
intitulés des rubriques sont ceux que LinkedIn affiche ; le contenu des offres
voisines est inventé pour porter les pièges. Le jour où Édouard colle une vraie
page, ce test dira si la structure a bougé — pas si elle était exacte au départ.
"""

from __future__ import annotations

import pytest

from veille import db, enrichissement
from veille.models import Offre
from veille.scoring import scorer

# --------------------------------------------------------------------------
# La page reconstituée
# --------------------------------------------------------------------------

ANNONCE = """Ingénieur Recette WMS (IVVQ) H/F
Entrepôts Fictifs du Rhin · Mulhouse, Grand Est, France · il y a 2 jours
Postuler

À propos du poste
Vous pilotez la recette de notre logiciel de gestion d'entrepôt (WMS) sur notre
site logistique. Vous rédigez les plans de test et les rapports de recette.
Vous garantissez l'accessibilité des écrans de préparation au RGAA 4.1.
Vous participez à la migration et à la qualité des données lors du changement
d'ERP prévu l'an prochain.

Profil recherché
Formation supérieure en informatique ou en qualité. Une première expérience en
environnement logistique est appréciée. Anglais professionnel.

Rémunération : 46 000 à 56 000 euros selon profil. Poste en CDI, deux jours de
télétravail par semaine."""

ANNEXES = """
Offres similaires
Technicien de maintenance industrielle
Groupe Verrier · Colmar
Astreinte une semaine sur quatre et interventions le week-end.

Ingénieur Qualité Fournisseurs
MetalNord · Belfort
Déplacements fréquents, permis B obligatoire, allemand courant exigé.

Personnes également consultées
Chef de projet SAP · Strasbourg
Data Scientist · Paris

Explorer des sujets collaboratifs
Applications mobiles
Développement logiciel

LinkedIn © 2026
À propos Accessibilité Conditions générales Politique de confidentialité"""

PAGE_ENTIERE = ANNONCE + "\n" + ANNEXES


@pytest.fixture(autouse=True)
def base():
    db.initialiser()
    with db.connexion() as cx:
        cx.execute("DELETE FROM offres WHERE source = 'test:page_entiere'")


def _offre() -> int:
    o = scorer(Offre(
        titre="Ingenieur Recette WMS (IVVQ) H/F",
        employeur="Entrepots Fictifs du Rhin",
        lieu="Mulhouse",
        description="Voir l'annonce.",
        url="https://www.linkedin.com/jobs/view/4000000001",
        source="test:page_entiere",
        donnees_partielles=True,
    ))
    oid, _ = db.enregistrer_offre(o)
    return oid


# --------------------------------------------------------------------------
# La coupe
# --------------------------------------------------------------------------


def test_les_rubriques_annexes_sont_coupees():
    texte, repere, retires = enrichissement.nettoyer_texte_detaille(PAGE_ENTIERE)
    assert "RGAA 4.1" in texte, "l'annonce elle-meme doit rester entiere"
    assert "Offres similaires" not in texte
    assert "Astreinte une semaine sur quatre" not in texte
    assert repere.lower().startswith("offres similaires")
    assert retires > 400


def test_le_repere_est_rendu_a_lutilisateur():
    """Une troncature silencieuse serait pire que le bruit qu'elle enleve."""
    oid = _offre()
    r = enrichissement.appliquer_texte(oid, PAGE_ENTIERE, "colle a la main")
    assert r.ok
    d = r.as_dict()
    assert d["annexes_retires"] > 400
    assert "similaires" in d["annexes_repere"].lower()


# --------------------------------------------------------------------------
# Ce que la coupe évite — le cœur de l'affaire
# --------------------------------------------------------------------------


def test_une_astreinte_de_loffre_voisine_ne_disqualifie_pas_la_bonne():
    """LE piege. « Astreinte » figure dans la page, mais dans une AUTRE offre."""
    oid = _offre()
    r = enrichissement.appliquer_texte(oid, PAGE_ENTIERE, "colle a la main")
    assert not r.alerte_eliminatoire, (
        f"ecartee sur un critere qui appartient a l'offre voisine : "
        f"{r.alerte_eliminatoire}"
    )
    apres = db.lire_offre(oid)
    assert not apres["rejete_auto"]
    assert apres["statut"] != "ecartee"


def test_lallemand_de_loffre_voisine_ne_penalise_pas():
    oid = _offre()
    r = enrichissement.appliquer_texte(oid, PAGE_ENTIERE, "colle a la main")
    libelles = [p.libelle.lower() for p in r.revelations_defavorables]
    assert not any("allemand" in l for l in libelles), libelles


def test_le_salaire_retenu_est_celui_de_la_bonne_offre():
    oid = _offre()
    enrichissement.appliquer_texte(oid, PAGE_ENTIERE, "colle a la main")
    apres = db.lire_offre(oid)
    assert apres["salaire_min"] == 46000, apres["salaire_min"]


def test_sans_la_coupe_le_piege_se_refermerait():
    """On verifie que le danger etait REEL, pas suppose.

    Si ce test cesse d'echouer a couper, c'est que les annexes n'etaient
    finalement pas dangereuses — et la coupe ne servirait a rien.
    """
    oid = _offre()
    r = enrichissement.appliquer_texte(oid, ANNONCE + "\n" + ANNEXES.replace(
        "Offres similaires", "Suite de la description"), "colle a la main")
    assert r.alerte_eliminatoire, (
        "sans repere de coupe, l'astreinte voisine aurait du disqualifier l'offre"
    )


# --------------------------------------------------------------------------
# Ne pas couper ce qu'il ne faut pas
# --------------------------------------------------------------------------


def test_une_annonce_qui_parle_doffres_similaires_nest_pas_tronquee_trop_tot():
    """Un repere trop pres du debut est ignore : couper la ne laisserait rien."""
    texte = "Offres similaires\n" + ANNONCE
    propre, repere, _ = enrichissement.nettoyer_texte_detaille(texte)
    assert "RGAA 4.1" in propre
    assert not repere


def test_un_repere_au_milieu_dune_phrase_ne_coupe_pas():
    texte = ANNONCE + "\nNous publions regulierement des offres similaires sur notre site."
    propre, repere, _ = enrichissement.nettoyer_texte_detaille(texte)
    assert not repere
    assert "notre site" in propre


def test_une_annonce_sans_annexes_passe_intacte():
    propre, repere, retires = enrichissement.nettoyer_texte_detaille(ANNONCE)
    assert repere == "" and retires == 0
    assert propre.strip().endswith("télétravail par semaine.")
