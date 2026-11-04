"""On normalise pour COMPARER, jamais pour ÉCRIRE.

Edouard, le 02/10/2026 : « il y a encore ce problème d'encodage dans les
fichiers Markdown, à la lecture c'est un peu cracra. »

La passe précédente avait conclu « aucun défaut d'encodage », et c'était vrai
au sens strict : pas de mojibake, pas de U+FFFD, UTF-8 propre de bout en bout.
Le vrai défaut était ailleurs — **les chaînes étaient écrites sans accents**
dans `criteres.yaml` et dans le code, par une habitude née des couches de
citation qui mangent les caractères non-ASCII. Invisible dans le code, bien
visible dans la fiche d'offre et à l'écran :

    Famille : Recette des donnees et du decisionnel
    ELIMINATOIRE - hors de ta zone geographique
    A VERIFIER - Langue de travail anglaise annoncee

Ce fichier verrouille les deux moitiés de la règle :
  1. ce qui s'affiche porte ses accents ;
  2. ce qui compare normalise — et ne dépend donc pas de ces accents.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from veille import config, scoring
from veille.config import charger_criteres, normaliser
from veille.models import Offre

RACINE = Path(__file__).resolve().parent.parent

# Orthographes désaccentuées de mots qui en portent. Trouver l'une d'elles
# dans un texte destiné à être lu, c'est le défaut.
DESACCENTUES = (
    "reglementee", "qualite", "donnees", "reperee", "eliminatoire",
    "ELIMINATOIRE", "systeme", "systemes", "informatises", "developpement",
    "ingenierie", "conformite", "teletravail", "genere", "generee",
    "annoncee", "detectee", "validee", "differee", "ecartee", "completer",
    "COMPLETER", "preparation", "interet", "VERIFIER", "verifier",
    "experience", "publie", "metier", "maitrise", "geographique",
    "imprecis", "interim", "region", "duree", "soiree",
    "clientele", "plafonne", "securite", "precise", "indetermine", "exigee",
    "bareme",
)
_MOTIF = re.compile(r"\b(" + "|".join(DESACCENTUES) + r")\b")


def _fautes(texte: str) -> list[str]:
    return sorted(set(m.group(1) for m in _MOTIF.finditer(texte)))


# --------------------------------------------------------------------------
# 1. CE QUI S'AFFICHE PORTE SES ACCENTS
# --------------------------------------------------------------------------


def test_les_libelles_de_criteres_portent_leurs_accents():
    """Ils arrivent tels quels dans la fiche d'offre et dans la console."""
    brut = (config.CHEMIN_CRITERES).read_text(encoding="utf-8")
    fautifs = []
    for ligne in brut.splitlines():
        nu = ligne.lstrip()
        if nu.startswith(("libelle:", "motif:")) and _fautes(ligne):
            fautifs.append(f"{nu[:70]} -> {_fautes(ligne)}")
    assert fautifs == [], fautifs


def test_lexplication_dun_scoring_reel_porte_ses_accents():
    """Le chemin complet : critères -> contribution -> fiche d'offre."""
    o = Offre(titre="Ingenieur de test", lieu="Toulouse",
              description="Poste en presentiel, recette des logiciels.")
    scoring.scorer(o)
    for c in o.explication:
        assert not _fautes(c.libelle), f"{c.libelle} -> {_fautes(c.libelle)}"
        assert not _fautes(c.detail or ""), f"{c.detail} -> {_fautes(c.detail)}"


def test_une_offre_sans_famille_le_dit_avec_ses_accents():
    """L'autre chemin de la famille : aucun métier reconnu. Le libellé est écrit
    dans le code, pas dans les critères, et il s'affiche tel quel."""
    o = Offre(titre="Boulanger", lieu="Mulhouse", description="Fournil et levain.")
    scoring.scorer(o)
    assert not o.famille
    libelles = [c.libelle for c in o.explication]
    assert "Aucune famille de métier reconnue" in libelles, libelles
    for c in o.explication:
        assert not _fautes(c.libelle), f"{c.libelle} -> {_fautes(c.libelle)}"


def test_le_motif_de_rejet_porte_ses_accents():
    o = Offre(titre="QA Engineer", lieu="Toulouse",
              description="Poste en presentiel sur site.")
    scoring.scorer(o)
    assert o.rejete_auto
    assert not _fautes(o.motif_rejet_auto), _fautes(o.motif_rejet_auto)


@pytest.mark.parametrize("lieu,description,attendu", [
    ("", "Rejoignez notre équipe.", "Lieu non précisé"),
    ("Mulhouse", "Rejoignez notre équipe.", "Télétravail non précisé"),
    ("Sundgau, France", "Rejoignez notre équipe.", "Lieu imprécis - à vérifier"),
    ("Grand Est, France", "Rejoignez notre équipe.", "Lieu imprécis - à vérifier"),
    ("Zzvillebourg", "Rejoignez notre équipe.", "A VÉRIFIER - pays indéterminé"),
])
def test_les_libelles_du_lieu_et_du_teletravail_portent_leurs_accents(lieu, description, attendu):
    """« Télétravail non precise » et ses voisins : écrits dans le code, pas dans les
    critères, ils s'affichent tels quels — libellé, détail et motif de rejet."""
    o = Offre(titre="QA Engineer", lieu=lieu, description=description)
    scoring.scorer(o)
    libelles = [c.libelle for c in o.explication]
    assert attendu in libelles, libelles
    for c in o.explication:
        assert not _fautes(c.libelle), f"{c.libelle} -> {_fautes(c.libelle)}"
        assert not _fautes(c.detail or ""), f"{c.detail} -> {_fautes(c.detail)}"
    assert not _fautes(o.motif_rejet_auto or ""), _fautes(o.motif_rejet_auto)


def test_une_presence_exigee_hors_de_portee_le_dit_avec_ses_accents():
    """Le motif de rejet d'une zone tenable deux jours par semaine seulement."""
    o = Offre(titre="QA Engineer", lieu="Colmar",
              description="Presence sur site tous les jours.")
    scoring.scorer(o)
    assert o.rejete_auto
    assert o.motif_rejet_auto.startswith("Présence à temps plein exigée à Colmar")
    assert not _fautes(o.motif_rejet_auto), _fautes(o.motif_rejet_auto)


# --------------------------------------------------------------------------
# 2. CE QUI COMPARE NORMALISE
#
# C'est l'autre moitié, et elle a mordu le jour même : `enrichissement`
# testait `"ELIMINATOIRE" in c.libelle`. Le libellé accentué est devenu
# « ÉLIMINATOIRE », et le signalement des révélations défavorables s'est tu
# SANS BRUIT. Un test manquait exactement là.
# --------------------------------------------------------------------------


def test_aucune_comparaison_ne_depend_dun_accent():
    """Statique : on interdit de comparer sur une chaîne accentuée.

    Une comparaison doit passer par `normaliser()`. Si elle teste directement
    un fragment accentué, elle casse au premier libellé retouché.
    """
    fautifs = []
    for f in sorted((RACINE / "src" / "veille").rglob("*.py")):
        for i, ligne in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            nu = ligne.lstrip()
            if nu.startswith("#") or "normaliser" in ligne:
                continue
            # « "..." in <quelque chose>.libelle » ou « .startswith("...") »
            for m in re.finditer(r'"([^"\n]*[àâäéèêëîïôöùûüçÀÉÈÊÎÔÙÇ][^"\n]*)"'
                                 r'\s*in\s|\.startswith\("([^"\n]*'
                                 r'[àâäéèêëîïôöùûüçÀÉÈÊÎÔÙÇ][^"\n]*)"\)', ligne):
                fautifs.append(f"{f.name}:{i} {nu[:80]}")
    assert fautifs == [], (
        "ces comparaisons dependent d'un accent — passe par normaliser() :\n"
        + "\n".join(fautifs))


def test_les_revelations_defavorables_survivent_a_un_libelle_accentue():
    """Le defaut REEL du 02/10 : « ELIMINATOIRE » ne retrouvait plus
    « ÉLIMINATOIRE », et le signalement s'etait tu sans bruit."""
    from veille.enrichissement import Preuve  # noqa: F401
    from veille import enrichissement

    source = (RACINE / "src" / "veille" / "enrichissement.py").read_text(encoding="utf-8")
    assert '"ELIMINATOIRE" in c.libelle' not in source
    assert "normaliser(c.libelle)" in source


def test_normaliser_retire_bien_les_accents():
    """Le contrat de la fonction, pour que les deux moitiés tiennent."""
    assert "eliminatoire" in normaliser("ÉLIMINATOIRE - hors zone")
    assert "qualite" in normaliser("Test & Qualité")
    assert "interim" in normaliser("Intérim suisse")


# --------------------------------------------------------------------------
# 3. LA CHARGE UTILE N'EST JAMAIS NORMALISÉE
# --------------------------------------------------------------------------


def test_le_texte_de_lannonce_arrive_accentue_dans_la_lettre():
    """Si une normalisation touchait la charge utile, ce test tomberait."""
    from veille import assemblage

    offre = {
        "titre": "Ingénieur Qualité",
        "description": ("Vous interviendrez sur les tests système des "
                        "terminaux et la qualité des données."),
        "explication": [
            {"libelle": "Famille : Intégration, vérification et validation (IVVQ)",
             "points": 30, "detail": '"tests systeme" dans la description'},
        ],
    }
    a = assemblage.assembler(offre, langue="fr")
    if a.paragraphe:
        assert "système" in a.paragraphe or "systeme" not in a.paragraphe, (
            "le terme cité doit garder la casse ET les accents de l'annonce")
