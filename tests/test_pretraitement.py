"""Le piège récurrent : un prétraitement qui mange un motif avant le test.

Trois fois, sous trois formes différentes, le même mécanisme a produit un
défaut de production :

1. **Télétravail.** « 2 jours sur site » était lu comme une présence totale,
   parce que le motif général (« sur site ») était examiné avant le motif
   spécifique (« 2 jours sur site »).
2. **Bâle-Ville.** Le séparateur employeur / lieu coupait sur le trait d'union
   et rendait « Bâle » puis « Ville » — un lieu inventé.
3. **Sa région.** Le retrait du bruit (« france ») s'exécutait *avant* la
   recherche des motifs, donc « france entiere » était coupé en deux et n'était
   jamais reconnu ; et « Grand Est, France (Sur site) » — son bassin d'emploi —
   était écarté comme trop loin.

Deux mécanismes, un seul effet :

- **(A) ordre des motifs** : le général examiné avant le spécifique ;
- **(B) réécriture du texte** : une étape de nettoyage détruit le motif avant
  qu'on le cherche.

Les tests du haut verrouillent les trois cas historiques. Ceux du bas
verrouillent la **classe entière** : tout motif déclaré dans `criteres.yaml`
doit survivre au prétraitement qui le concerne. Un quatrième cas de la même
famille échouera ici avant d'atteindre sa console.
"""

from __future__ import annotations

import pytest

from veille.collectors.parsers.base import separer_employeur_lieu
from veille.config import charger_criteres, contient, normaliser
from veille.models import Offre
from veille.scoring import detecter_teletravail, lieu_imprecis, scorer


@pytest.fixture(scope="module")
def criteres():
    return charger_criteres()


# --------------------------------------------------------------------------
# Les trois cas historiques, nommés
# --------------------------------------------------------------------------


def test_regression_1_deux_jours_sur_site_nest_pas_du_presentiel(criteres):
    """Le motif spécifique doit être examiné avant le général."""
    o = Offre(titre="Test Manager", lieu="Mulhouse",
              description="Poste hybride : 2 jours sur site par semaine.")
    niveau, _ = detecter_teletravail(o, criteres)
    assert niveau == "partiel", "« 2 jours sur site » n'est pas une presence totale"


def test_regression_2_bale_ville_nest_pas_coupee_sur_son_trait_dunion():
    employeur, lieu = separer_employeur_lieu(
        ["Exemplia Logistik AG - Bâle-Ville, Suisse"], "Quality Engineer"
    )
    assert "Ville" in lieu, (employeur, lieu)
    assert lieu.strip() not in ("Bâle", "Bale")


def test_regression_3_france_entiere_survit_au_retrait_du_bruit(criteres):
    """« france » est un mot de bruit ET le début d'un motif.

    Retirer le bruit avant de chercher les motifs coupait « france entiere »
    en deux : le motif n'était jamais reconnu.
    """
    motif, _poids, groupe = lieu_imprecis(Offre(titre="x", lieu="France entière"), criteres)
    assert motif, "le motif a ete detruit par le retrait du bruit"
    assert groupe == "lointains"


def test_regression_3bis_son_bassin_demploi_nest_pas_ecarte(criteres):
    o = scorer(Offre(titre="Automaticienne de tests", lieu="Sundgau, France (Sur site)",
                     description="Poste sur site."), criteres)
    assert not o.rejete_auto, f"son bassin d'emploi ecarte : {o.motif_rejet_auto}"


# --------------------------------------------------------------------------
# (B) La classe entière : tout motif déclaré doit survivre au prétraitement
# --------------------------------------------------------------------------


def _tous_les_motifs(criteres) -> list[tuple[str, str]]:
    """(chemin, motif) pour chaque motif declare dans criteres.yaml."""
    trouves: list[tuple[str, str]] = []

    def descendre(noeud, chemin: str):
        if isinstance(noeud, dict):
            for cle, valeur in noeud.items():
                descendre(valeur, f"{chemin}.{cle}" if chemin else str(cle))
        elif isinstance(noeud, list) and chemin.endswith("motifs"):
            for m in noeud:
                if isinstance(m, str):
                    trouves.append((chemin, m))

    descendre(criteres.brut, "")
    return trouves


def test_il_y_a_bien_des_motifs_a_verifier(criteres):
    """Si la structure de la configuration change, ce garde-fou doit crier."""
    assert len(_tous_les_motifs(criteres)) > 100


@pytest.mark.parametrize("chemin,motif", _tous_les_motifs(charger_criteres()),
                         ids=lambda v: str(v)[:60])
def test_tout_motif_declare_survit_a_la_normalisation(chemin, motif):
    """Un motif que `normaliser` détruit ne peut jamais être détecté.

    C'est le filet le plus large : il ne dépend d'aucune règle métier. Un motif
    contenant un caractère que la normalisation mange — ponctuation, ligature,
    espace insécable — échoue ici, à l'écriture, et pas en production.
    """
    if chemin.endswith("bruit_agregateur"):
        pytest.skip("expressions regulieres, pas des motifs textuels")
    phrase = f"Avant, {motif}, apres."
    assert contient(normaliser(phrase), motif), (
        f"{chemin} : le motif « {motif} » ne se retrouve pas dans une phrase "
        f"qui le contient pourtant mot pour mot"
    )


def _motifs_de_lieu() -> list[tuple[str, str]]:
    geo = charger_criteres().brut.get("geographie", {})
    return [(groupe, m)
            for groupe, bloc in geo.get("lieux_imprecis", {}).items()
            for m in bloc.get("motifs", [])]


@pytest.mark.parametrize("groupe,motif", _motifs_de_lieu(), ids=lambda v: str(v)[:40])
def test_tout_motif_de_lieu_survit_au_retrait_du_bruit(groupe, motif, criteres):
    """LE test qui aurait attrapé le bug de sa région.

    Chaque motif de lieu imprécis, entouré du bruit réel qu'on rencontre dans
    les annonces, doit rester détectable.
    """
    for habillage in ("{m}", "{m}, France", "{m} (Sur site)", "{m}, France (Sur site)"):
        lieu = habillage.format(m=motif)
        trouve, _poids, groupe_vu = lieu_imprecis(Offre(titre="x", lieu=lieu), criteres)
        assert trouve, f"« {lieu} » n'est plus reconnu comme imprecis"
        assert groupe_vu == groupe, f"« {lieu} » classe en {groupe_vu} au lieu de {groupe}"


def _motifs_de_teletravail() -> list[tuple[str, str, str]]:
    geo = charger_criteres().brut.get("geographie", {})
    paires = [
        ("teletravail_complet_motifs", "complet"),
        ("presence_partielle_motifs", "partiel"),
        ("presence_totale_motifs", "presentiel"),
    ]
    return [(cle, m, attendu) for cle, attendu in paires for m in geo.get(cle, [])]


@pytest.mark.parametrize("cle,motif,attendu", _motifs_de_teletravail(),
                         ids=lambda v: str(v)[:40])
def test_tout_motif_de_teletravail_donne_bien_son_niveau(cle, motif, attendu, criteres):
    """(A) l'ordre d'examen et (B) le retrait du bruit agrégateur, ensemble.

    Un motif spécifique masqué par un motif général ressort ici : le niveau
    rendu ne serait pas celui que sa liste annonce.
    """
    o = Offre(titre="Test Manager", lieu="Mulhouse",
              description=f"Description du poste. {motif}. Equipe de dix personnes.")
    niveau, preuve = detecter_teletravail(o, criteres)
    assert niveau == attendu, (
        f"{cle} : « {motif} » donne « {niveau} » au lieu de « {attendu} » "
        f"(preuve retenue : {preuve!r}) — un motif plus general l'a emporte"
    )
