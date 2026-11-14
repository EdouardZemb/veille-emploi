"""« Préparer ma candidature » : de « Je postule » au dossier prêt (ADR-0003, § 5).

`preparer` enchaîne ce qui se fait seul et ne s'arrête que sur ce qui manque : le texte de
l'annonce (étape `texte`), une information trop mince (`mince`), ou une génération en échec
(`echec`). Sinon, le dossier est prêt (`pret`). Un dossier déjà sur le disque est rendu, pas
refait : seul `regenerer` le refait. Le module n'appelle que l'existant, sans le changer : la
lecture et l'enregistrement du texte (`enrichissement`), la complétude, la génération
(`dossier`), l'historique de la lettre (`lettre`), les noms d'envoi (`rendu`), les états et la
base.

L'ORDRE COMPTE.
- Le statut s'écrit avant le texte. `db.enregistrer_texte_complet` peut écarter une offre
  dont le statut est automatique (`nouveau`), jamais une offre `interessante` : écrit après,
  un texte qui révèle un critère éliminatoire écarterait l'offre dont Edouard vient de dire
  « Je postule ». L'alerte se dit à la place, en tête des avertissements de l'étape.
- Un texte fourni s'enregistre avant toute génération : une génération en échec ne le perd
  pas (invariant 2 du projet).
- La lettre courante entre dans l'historique avant la génération, qui la réécrit sans
  l'historiser : une régénération n'efface rien, pas même en échec (invariant 4 du projet).
"""

from __future__ import annotations

import logging
import shutil
import zipfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import completude, db, dossier, enrichissement, etats, lettre, rendu

log = logging.getLogger(__name__)

ETAPES: tuple[str, ...] = ("texte", "mince", "pret", "echec")
# L'étiquette, dans l'historique de la lettre, de celle qu'une régénération remplace.
ETIQUETTE_REGENERATION = "avant-regeneration"
# Les statuts que « Je postule » fait passer en `interessante`. `differee` aussi : la fiche
# d'une offre mise de côté propose « Je postule » depuis le lot 1.
STATUTS_A_PRENDRE: tuple[str, ...] = ("nouveau", "a_traiter", "differee")
# Une offre envoyée, en entretien ou close n'a plus de candidature à préparer.
ETATS_PREPARABLES: tuple[str, ...] = ("a_voir", "mise_de_cote", "je_postule")
# Un extrait, l'annonce « reçue en extrait » (ADR-0003, Contexte) : une description plus courte,
# ou marquée `donnees_partielles`, telle que la source l'a donnée.
LONGUEUR_EXTRAIT = 400
MANQUES_MONTRES = 3
# À qui la lettre est adressée, sous les clés de l'offre (la route `api_maj` les enregistre).
CHAMPS_DESTINATAIRE: tuple[str, ...] = (
    "contact_nom", "contact_civilite", "adresse_entreprise", "reference_annonce",
)


class OffreInconnue(LookupError):
    """Aucune offre ne porte cet identifiant."""


class EtatIncompatible(ValueError):
    """L'offre est envoyée, en entretien ou close : il n'y a plus de candidature à préparer."""


@dataclass
class Etape:
    """Ce que rend la préparation : l'étape suivante, et de quoi l'afficher.

    `url` porte toujours le lien de l'annonce. `mince` porte la complétude et ses manques les
    plus lourds ; `pret`, le dossier, et au seul passage qui génère, la complétude, `genere`,
    `kit_provisoire` et les avertissements de la génération. `avertissements` commence par
    l'alerte éliminatoire du texte enregistré par ce passage, s'il en porte une, et une étape
    `pret` le finit par ceux du dossier."""

    etape: str
    message: str = ""
    url: str = ""
    manques: list[dict[str, Any]] = field(default_factory=list)
    completude: dict[str, Any] | None = None
    dossier: dict[str, Any] | None = None
    genere: bool = False
    avertissements: list[str] = field(default_factory=list)
    kit_provisoire: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def preparer(
    offre_id: int,
    texte: str | None = None,
    forcer: bool = False,
    regenerer: bool = False,
) -> Etape:
    """L'étape suivante de la candidature à cette offre.

    `texte`, le texte de l'annonce collé par Edouard, s'enregistre d'abord ; vide ou blanc, il
    vaut None. `forcer` génère malgré un extrait ou une complétude mince (« Générer avec
    l'extrait », « Générer quand même »). Un dossier déjà sur le disque est rendu tel quel :
    un double appel ne régénère jamais. `regenerer` le refait sans rien redemander, puisqu'il a
    déjà été accepté une fois, et sans rien perdre : la lettre remplacée entre dans
    l'historique, qui suit le dossier d'un autre jour. Lève `OffreInconnue`, ou
    `EtatIncompatible` sans rien écrire."""
    offre = db.lire_offre(offre_id)
    if offre is None:
        raise OffreInconnue
    if etats.etat_de(offre) not in ETATS_PREPARABLES:
        raise EtatIncompatible
    if offre["statut"] in STATUTS_A_PRENDRE:
        db.changer_statut(offre_id, "interessante")
    # Le lien montré à Edouard, comme la fiche ; vide, l'écran ne le montre pas.
    lien = offre["url"] or offre["url_canonique"] or ""
    alertes: list[str] = []
    if (texte or "").strip():
        refus = _enregistrer(offre_id, texte, "colle a la main", alertes)
        if refus is not None:
            return Etape("texte", message=refus, url=lien)
    offre = db.lire_offre(offre_id)
    ancien = dossier.chemin_du_dossier(offre)
    # `is_dir`, comme `dossier_pret` : un fichier à cette place n'est pas un dossier à rendre.
    if not regenerer and ancien is not None and ancien.is_dir():
        pret = dossier_pret(offre)
        return Etape(
            "pret", url=lien, dossier=pret, avertissements=[*alertes, *pret["avertissements"]],
        )
    # Ni lecture ni complétude ne retiennent « Générer avec l'extrait », « Générer quand même »,
    # ni une régénération : le dossier a déjà été accepté une fois.
    passer = forcer or regenerer
    if not passer and _est_un_extrait(offre):
        # Un extrait n'a aucun texte enregistré : un refus de la lecture ne suit aucune alerte.
        refus = _lire_l_annonce(offre_id, offre, alertes)
        if refus is not None:
            return Etape("texte", message=refus, url=lien)
        offre = db.lire_offre(offre_id)
    bilan = completude.evaluer(offre)
    if not passer and not bilan.suffisant_pour_dossier:
        return Etape(
            "mince", url=lien, manques=[m.as_dict() for m in bilan.manques[:MANQUES_MONTRES]],
            completude=bilan.as_dict(), avertissements=alertes,
        )
    if ancien is not None:
        # `generer` réécrit la lettre sans l'historiser : elle y entre d'abord, affinée peut-être,
        # et y reste si la génération échoue. Sans lettre, `historiser` n'écrit rien. Hors
        # régénération, on n'arrive ici que sans dossier sur le disque : rien à historiser.
        lettre.historiser(ancien, ETIQUETTE_REGENERATION)
    try:
        resultat = dossier.generer(offre)
    except Exception as erreur:
        log.exception("offre %s : la génération du dossier a échoué", offre_id)  # pragma: no mutate
        return Etape(
            "echec", message=str(erreur) or type(erreur).__name__, url=lien, avertissements=alertes,
        )
    _emporter_l_historique(ancien, resultat.chemin)
    db.maj_champs(offre_id, dossier_chemin=str(resultat.chemin))
    db.journaliser(
        offre_id, "dossier_regenere" if regenerer else "dossier_genere", resultat.gabarit_lettre,
    )
    pret = dossier_pret(db.lire_offre(offre_id))
    return Etape(
        "pret", url=lien, completude=bilan.as_dict(), dossier=pret, genere=True,
        avertissements=[*alertes, *resultat.avertissements, *pret["avertissements"]],
        kit_provisoire=resultat.kit_provisoire,
    )


def _emporter_l_historique(ancien: Path | None, nouveau: Path) -> None:
    """Un autre jour, `generer` crée un autre dossier (son nom porte la date) : l'historique de
    la lettre y est copié, s'il existe et si le nouveau dossier n'en a pas. Jamais fusionné :
    les numéros des deux historiques se heurteraient. L'ancien dossier reste sur le disque."""
    if ancien is None or nouveau == ancien:
        return
    source, cible = ancien / lettre.NOM_HISTORIQUE, nouveau / lettre.NOM_HISTORIQUE
    if source.is_dir() and not cible.exists():
        shutil.copytree(source, cible)


def _est_un_extrait(offre: Mapping[str, Any]) -> bool:
    """Une description plus courte que `LONGUEUR_EXTRAIT`, ou marquée partielle, que la source a
    donnée : un texte complet déjà enregistré (`enrichi_le`, que `appliquer_texte` pose et que
    `db.annuler_texte_complet` retire) n'en est plus un, quelle que soit sa longueur. Court, la
    complétude le dira (« Description complete de l'annonce ») ; la préparation ne le redemande
    pas."""
    recue_en_extrait = offre["donnees_partielles"] or len(offre["description"] or "") < LONGUEUR_EXTRAIT
    return recue_en_extrait and not offre["enrichi_le"]


def _enregistrer(offre_id: int, texte: str, origine: str, alertes: list[str]) -> str | None:
    """Enregistre le texte de l'annonce et garde son alerte ; rend le refus du `Rapport`, ou None."""
    rapport = enrichissement.appliquer_texte(offre_id, texte, origine)
    if not rapport.ok:
        return rapport.message
    if rapport.alerte_eliminatoire:
        alertes.append(rapport.alerte_eliminatoire)
    return None


def _lire_l_annonce(offre_id: int, offre: Mapping[str, Any], alertes: list[str]) -> str | None:
    """Lit le texte de l'annonce quand la source et la cadence le permettent ; rend le premier
    refus, ou None. La lecture prend l'adresse canonique, sinon l'adresse, comme `api_enrichir`."""
    adresse = offre["url_canonique"] or offre["url"] or ""
    politique = enrichissement.politique(adresse)
    if not politique.autorise:
        return politique.raison
    possible, message = enrichissement.verifier_cadence()
    if not possible:
        return message
    texte, message = enrichissement.recuperer(adresse)
    if not texte:
        return message
    return _enregistrer(offre_id, texte, f"recupere sur {politique.domaine}", alertes)


def dossier_pret(offre: Mapping[str, Any]) -> dict[str, Any] | None:
    """Ce que montre l'écran « Dossier prêt » ; None sans dossier sur le disque.

    Une pièce est un fichier du dossier dont le nom d'envoi figure dans le paquet d'envoi : un
    formulaire en ligne reçoit les mêmes noms que le zip. Un paquet absent ou illisible (un
    dossier ancien, un paquet tronqué) ne donne aucune pièce, et `archive` le dit. Deux pièces
    au même nom d'envoi n'arriveraient pas toutes les deux : un avertissement les nomme."""
    repertoire = dossier.chemin_du_dossier(offre)
    if repertoire is None or not repertoire.is_dir():
        return None
    try:
        # Refermé en sortant : ouvert, Windows refuserait à `generer` de supprimer le paquet.
        with zipfile.ZipFile(repertoire / f"{rendu.prefixe()}-candidature.zip") as paquet:
            noms = set(paquet.namelist())
    except (FileNotFoundError, zipfile.BadZipFile):
        noms, archive = set(), False
    else:
        archive = True
    # Les fichiers dans l'ordre de leur nom (des chaînes : l'ordre ne dépend pas du système),
    # puis triés par nom d'envoi : deux pièces au même nom d'envoi gardent l'ordre de leur nom.
    noms_sur_le_disque = sorted(f.name for f in repertoire.iterdir())
    envoi = {fichier: rendu.nom_pour_envoi(fichier) for fichier in noms_sur_le_disque}
    pieces = sorted(
        ({"nom": nom, "fichier": fichier} for fichier, nom in envoi.items() if nom in noms),
        key=lambda piece: piece["nom"],
    )
    par_nom: dict[str, list[str]] = {}
    for piece in pieces:
        par_nom.setdefault(piece["nom"], []).append(piece["fichier"])
    avertissements = [
        f"{', '.join(memes)} partent sous le même nom, {nom} : le recruteur n'en recevra "
        f"qu'une. Renomme les autres dans le kit."
        for nom, memes in par_nom.items()
        if len(memes) > 1
    ]
    return {
        "nom": repertoire.name,
        "pieces": pieces,
        "archive": archive,
        "destinataire": {cle: offre.get(cle) or "" for cle in CHAMPS_DESTINATAIRE},
        "avertissements": avertissements,
    }
