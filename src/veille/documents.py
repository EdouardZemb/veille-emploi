"""Acces a ses documents depuis la console, donc depuis son telephone.

Deux familles :
  - le KIT : CV francais, dossier suisse, lettres, annexe technique, strategie,
    preparation d'entretien. Il vit dans VEILLE_KIT.
  - les DOSSIERS GENERES : un par candidature, dans VEILLE_DOSSIERS.

REGLE : le dossier du kit est relu A CHAQUE APPEL. Aucun nom de fichier n'est
code en dur ici. Le kit s'enrichit (la preparation d'entretien vient d'arriver,
d'autres suivront) et rien dans ce module ne doit avoir a etre modifie pour
qu'un nouveau document apparaisse.

SECURITE : ces documents portent son etat civil, ses pretentions salariales et
sa strategie de negociation. Toutes les routes qui les servent exigent une
session, et tout chemin demande est verifie comme contenu dans son dossier
d'origine - liens symboliques resolus.
"""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import CHEMIN_DOSSIERS, CHEMIN_KIT

# Extensions servies. Tout le reste est ignore : on ne sert pas un fichier
# dont on ne sait pas ce qu'il est.
EXTENSIONS = {
    ".pdf", ".docx", ".odt", ".md", ".txt", ".rtf",
    ".png", ".jpg", ".jpeg", ".zip",
}

# Classement par intitule, du plus specifique au plus general. Un fichier qui
# ne correspond a rien tombe dans "Autres" - il reste visible et
# telechargeable, il n'est simplement pas range.
_CATEGORIES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"^cv\b|curriculum", re.I), "CV"),
    (re.compile(r"^dossier|candidature", re.I), "Dossier de candidature"),
    (re.compile(r"^lettre|^letter|motivation", re.I), "Lettres"),
    (re.compile(r"entretien|interview|preparation", re.I), "Préparation d'entretien"),
    (re.compile(r"strategie|strategy|negoc", re.I), "Stratégie"),
    (re.compile(r"annexe|technique|certificat|istqb", re.I), "Annexes et certifications"),
)

_ETIQUETTES_CONTEXTE = {
    "fr": "français", "en": "anglais", "de": "allemand",
    "ch": "Suisse", "suisse": "Suisse", "france": "France", "fr-fr": "France",
}


def _categorie(nom: str) -> str:
    for motif, libelle in _CATEGORIES:
        if motif.search(nom):
            return libelle
    return "Autres"


def _taille_lisible(octets: int) -> str:
    for unite in ("o", "ko", "Mo"):
        if octets < 1024 or unite == "Mo":
            return f"{octets:.0f} {unite}" if unite == "o" else f"{octets:.1f} {unite}"
        octets /= 1024
    return f"{octets:.1f} Mo"


def _contexte(nom: str) -> str:
    """Rend lisible l'etiquetage 'cv.ch.en.pdf' -> 'Suisse, anglais'."""
    etiquettes = [e.lower() for e in nom.split(".")[1:-1]]
    lisibles = [_ETIQUETTES_CONTEXTE[e] for e in etiquettes if e in _ETIQUETTES_CONTEXTE]
    return ", ".join(dict.fromkeys(lisibles))


@dataclass
class Document:
    nom: str
    categorie: str
    contexte: str
    taille: str
    modifie_le: str
    type_mime: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "nom": self.nom,
            "categorie": self.categorie,
            "contexte": self.contexte,
            "taille": self.taille,
            "modifie_le": self.modifie_le,
            "type_mime": self.type_mime,
        }


def _decrire(chemin: Path) -> Document:
    stat = chemin.stat()
    type_mime, _ = mimetypes.guess_type(chemin.name)
    return Document(
        nom=chemin.name,
        categorie=_categorie(chemin.name),
        contexte=_contexte(chemin.name),
        taille=_taille_lisible(stat.st_size),
        modifie_le=datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y"),
        type_mime=type_mime or "application/octet-stream",
    )


def lister_kit() -> dict[str, Any]:
    """Le kit, relu depuis le disque a chaque appel."""
    if not CHEMIN_KIT.exists():
        return {
            "emplacement": str(CHEMIN_KIT),
            "present": False,
            "documents": [],
            "message": (
                "Aucun kit a cet emplacement. Copie-le sur le serveur puis renseigne "
                "VEILLE_KIT dans config/.env — voir la section Réglages."
            ),
        }

    fichiers = [
        p for p in sorted(CHEMIN_KIT.iterdir())
        if p.is_file() and p.suffix.lower() in EXTENSIONS and not p.name.startswith(".")
    ]
    documents = [_decrire(p) for p in fichiers]

    # Regroupement, dans l'ordre de declaration des categories.
    ordre = [libelle for _, libelle in _CATEGORIES] + ["Autres"]
    groupes: list[dict[str, Any]] = []
    for categorie in ordre:
        lot = [d.as_dict() for d in documents if d.categorie == categorie]
        if lot:
            groupes.append({"categorie": categorie, "documents": lot})

    return {
        "emplacement": str(CHEMIN_KIT),
        "present": True,
        "total": len(documents),
        "groupes": groupes,
        "message": "" if documents else "Le dossier existe mais ne contient aucun document reconnu.",
    }


def chemin_kit_sur(nom: str) -> Path:
    """Chemin verifie d'un document du kit. Leve ValueError si hors du kit."""
    return _chemin_contenu(CHEMIN_KIT, nom)


def _chemin_contenu(base: Path, nom: str) -> Path:
    """Resout `nom` sous `base` et refuse tout ce qui en sort.

    `resolve()` suit les liens symboliques : un lien pose dans le kit et
    pointant vers /etc ne permet pas de s'echapper.
    """
    racine = base.resolve()
    cible = (racine / nom).resolve()
    if not cible.is_relative_to(racine):
        raise ValueError("chemin hors du dossier autorise")
    if not cible.is_file():
        raise ValueError("fichier introuvable")
    if cible.suffix.lower() not in EXTENSIONS:
        raise ValueError("type de fichier non servi")
    return cible


# --------------------------------------------------------------------------
# Dossiers de candidature generes
# --------------------------------------------------------------------------


def lister_dossiers() -> list[dict[str, Any]]:
    """Les dossiers produits, du plus recent au plus ancien, avec leur offre."""
    from . import db, dossier

    if not CHEMIN_DOSSIERS.exists():
        return []

    # On rattache chaque dossier a son offre quand c'est possible : le nom
    # seul ne dit pas le score ni le statut de la candidature. Le nom est celui
    # que retrouve `chemin_du_dossier` : une barre inverse separe aussi.
    par_chemin = {}
    for o in db.lister_offres(limite=1000, inclure_ecartees=True):
        chemin = dossier.chemin_du_dossier(o)
        if chemin is not None:
            par_chemin[chemin.name] = o

    resultats = []
    for repertoire in sorted(CHEMIN_DOSSIERS.iterdir(), reverse=True):
        if not repertoire.is_dir():
            continue
        fichiers = [
            _decrire(p).as_dict()
            for p in sorted(repertoire.iterdir())
            if p.is_file() and p.suffix.lower() in EXTENSIONS
        ]
        if not fichiers:
            continue
        offre = par_chemin.get(repertoire.name)
        resultats.append({
            "dossier": repertoire.name,
            "cree_le": datetime.fromtimestamp(repertoire.stat().st_mtime).strftime("%d/%m/%Y"),
            "offre_id": offre["id"] if offre else None,
            "titre": offre["titre"] if offre else repertoire.name,
            "employeur": (offre or {}).get("employeur", ""),
            "statut": (offre or {}).get("statut", ""),
            "fichiers": fichiers,
        })
    return resultats


def chemin_dossier_sur(dossier: str, nom: str) -> Path:
    """Chemin verifie d'un fichier d'un dossier genere."""
    racine = CHEMIN_DOSSIERS.resolve()
    repertoire = (racine / dossier).resolve()
    if not repertoire.is_relative_to(racine) or not repertoire.is_dir():
        raise ValueError("dossier introuvable")
    return _chemin_contenu(repertoire, nom)
