"""L'historique, et le defaut que `lettre-assemblee.md` portait.

DEFAUT CORRIGE. `api_appliquer_affinement` ecrivait dans
`lettre-assemblee.md` la version COURANTE de la lettre. Apres DEUX
affinements appliques, le fichier contenait donc le premier affinement, et
`affiner/annuler` — dont la docstring promet « Retour a la version
assemblee » — restaurait un texte produit par un modele.

Le test qui compte est `test_deux_applications_successives_...` : il echoue
sur l'ancien code et passe sur le nouveau. Les autres verrouillent
l'historique sur lequel la correction s'appuie.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from veille import lettre as L

ASSEMBLEE = "Madame, Monsieur,\n\nLe texte assemblé.\n\nCamille Exemple\n"
AFFINEE_1 = "Madame, Monsieur,\n\nLe texte affiné une fois.\n\nCamille Exemple\n"
AFFINEE_2 = "Madame, Monsieur,\n\nLe texte affiné deux fois.\n\nCamille Exemple\n"


def _lettre(rep: Path, texte: str) -> None:
    (rep / L.NOM_LETTRE).write_text(texte, encoding="utf-8")


# --------------------------------------------------------------------------
# L'historique
# --------------------------------------------------------------------------


def test_sans_historique_la_liste_est_vide_et_cest_un_resultat(tmp_path):
    assert L.versions(tmp_path) == []
    assert L.derniere_version(tmp_path, "assemblee") is None


def test_une_version_porte_son_numero_son_horodatage_et_son_etiquette(tmp_path):
    _lettre(tmp_path, ASSEMBLEE)
    v = L.historiser(tmp_path, "assemblee")
    assert v is not None
    assert v.numero == 1
    assert v.etiquette == "assemblee"
    assert v.fichier.startswith("001-")
    assert v.fichier.endswith("-assemblee.md")
    assert L.texte_de_version(tmp_path, 1) == ASSEMBLEE
    # TEMOIN : le fichier existe vraiment sur le disque.
    assert (tmp_path / L.NOM_HISTORIQUE / v.fichier).exists()


def test_les_numeros_sont_croissants_et_ne_se_reutilisent_pas(tmp_path):
    _lettre(tmp_path, ASSEMBLEE)
    L.historiser(tmp_path, "assemblee")
    _lettre(tmp_path, AFFINEE_1)
    L.historiser(tmp_path, "affinee")
    _lettre(tmp_path, AFFINEE_2)
    L.historiser(tmp_path, "affinee")
    numeros = [v.numero for v in L.versions(tmp_path)]
    assert numeros == [1, 2, 3], "TEMOIN : trois versions, numerotees"


def test_historiser_sans_lettre_ne_cree_rien(tmp_path):
    assert L.historiser(tmp_path, "assemblee") is None
    assert not (tmp_path / L.NOM_HISTORIQUE).exists()


def test_une_etiquette_sale_est_nettoyee_pas_refusee(tmp_path):
    _lettre(tmp_path, ASSEMBLEE)
    v = L.historiser(tmp_path, "Assemblée / version 2 !")
    assert v is not None
    assert "/" not in v.fichier and " " not in v.fichier
    assert L.texte_de_version(tmp_path, v.numero) == ASSEMBLEE


def test_une_version_inconnue_echoue_franchement(tmp_path):
    _lettre(tmp_path, ASSEMBLEE)
    L.historiser(tmp_path, "assemblee")
    with pytest.raises(FileNotFoundError):
        L.texte_de_version(tmp_path, 99)


# --------------------------------------------------------------------------
# LE TEST QUI PORTE LA CORRECTION
# --------------------------------------------------------------------------


def test_deux_applications_successives_ne_falsifient_pas_lassemblee(tmp_path):
    """ECHOUE SUR L'ANCIEN CODE. C'est tout l'interet du test.

    L'ancien code faisait, a chaque application :
        lettre-assemblee.md <- lettre-de-motivation.md (la COURANTE)
    Donc apres deux applications, « la version assemblee » etait le premier
    affinement. On verifie ici que l'assemblee d'origine reste atteignable
    APRES deux applications.
    """
    # 1. etat assemble, historise comme tel
    _lettre(tmp_path, ASSEMBLEE)
    L.historiser(tmp_path, "assemblee")

    # 2. premier affinement applique
    _lettre(tmp_path, AFFINEE_1)
    L.historiser(tmp_path, "affinee")

    # 3. second affinement applique
    _lettre(tmp_path, AFFINEE_2)
    L.historiser(tmp_path, "affinee")

    # La derniere version ETIQUETEE `assemblee` est bien l'assemblee d'origine.
    v = L.derniere_version(tmp_path, "assemblee")
    assert v is not None, "TEMOIN : une version assemblee doit exister"
    assert L.texte_de_version(tmp_path, v.numero) == ASSEMBLEE, (
        "apres deux affinements, « la version assemblee » doit rester "
        "l'assemblee d'origine, pas le premier affinement")

    # Et la derniere version `affinee` est bien la seconde.
    va = L.derniere_version(tmp_path, "affinee")
    assert L.texte_de_version(tmp_path, va.numero) == AFFINEE_2


def test_un_retour_arriere_est_une_nouvelle_version_jamais_une_suppression(tmp_path):
    """L'historique ne se reecrit pas. C'est la regle qui manquait a
    `affiner/annuler` : revenir a 001 doit ECRIRE 004, pas effacer 002 et 003."""
    _lettre(tmp_path, ASSEMBLEE)
    L.historiser(tmp_path, "assemblee")
    _lettre(tmp_path, AFFINEE_1)
    L.historiser(tmp_path, "affinee")
    avant = len(L.versions(tmp_path))
    assert avant == 2, "TEMOIN"

    # Retour arriere : on historise l'etat courant, puis on restaure.
    L.historiser(tmp_path, "avant-retour-arriere")
    _lettre(tmp_path, L.texte_de_version(tmp_path, 1))
    L.historiser(tmp_path, "assemblee-restauree")

    apres = L.versions(tmp_path)
    assert len(apres) == 4, "deux versions de plus, aucune perdue"
    assert [v.etiquette for v in apres] == [
        "assemblee", "affinee", "avant-retour-arriere", "assemblee-restauree"]
    # Les deux premieres sont INTACTES.
    assert L.texte_de_version(tmp_path, 1) == ASSEMBLEE
    assert L.texte_de_version(tmp_path, 2) == AFFINEE_1


def test_lhistorique_ne_part_jamais_au_recruteur():
    """Par NOM DECLARE, pas par extension. `fiche-offre.md` n'est exclu du
    paquet d'envoi aujourd'hui que parce qu'il finit par `.md` : c'est un
    controle accidentel, pas une intention."""
    for nom in (L.NOM_META, L.NOM_HISTORIQUE, L.NOM_GABARIT, L.NOM_ASSEMBLEE):
        assert nom in L.JAMAIS_AU_RECRUTEUR
    assert "fiche-offre.md" in L.JAMAIS_AU_RECRUTEUR
    assert "preparation-entretien.md" in L.JAMAIS_AU_RECRUTEUR
    # TEMOIN NEGATIF : la lettre elle-meme, et le CV, en sont ABSENTS.
    assert L.NOM_LETTRE not in L.JAMAIS_AU_RECRUTEUR
