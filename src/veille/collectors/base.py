"""Socle commun aux collecteurs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from ..models import Offre

log = logging.getLogger(__name__)


@dataclass
class Rapport:
    """Ce qu'un collecteur rend a la fin de son passage."""

    source: str
    collectees: int = 0
    nouvelles: int = 0
    erreurs: list[str] = field(default_factory=list)

    def resume(self) -> str:
        base = f"{self.collectees} vues, {self.nouvelles} nouvelles"
        if self.erreurs:
            base += f", {len(self.erreurs)} erreur(s)"
        return base


class Collecteur(Protocol):
    nom: str

    def collecter(self) -> Iterable[Offre]:  # pragma: no cover - interface
        ...


# --------------------------------------------------------------------------
# Extraction de salaire : partagee par tous les collecteurs, car la moitie des
# annonces met le salaire en texte libre plutot que dans un champ dedie.
# --------------------------------------------------------------------------

_MILLIERS = re.compile(r"[\s .,']")

_RE_SALAIRE = re.compile(
    r"""
    (?P<devise_avant>CHF|EUR|€|Fr\.?)?\s*
    (?P<n1>\d{2,3}(?:[\s .,']\d{3})+|\d{2,3}(?:[.,]\d)?\s*[kK]|\d{4,7})
    # La devise se glisse souvent ENTRE les deux montants :
    # "41 000 EUR - 50 000 EUR". Sans ce groupe, la plage n'etait pas vue et
    # on retombait sur le montant unique, donc sur un maximum faux.
    \s*(?P<devise_milieu>CHF|EUR|€|Fr\.?|k€|K€)?
    \s*(?:[-–—]|a|à|to|bis|et|and|und|jusqu'a|jusqu'à)\s*
    (?P<n2>\d{2,3}(?:[\s .,']\d{3})+|\d{2,3}(?:[.,]\d)?\s*[kK]|\d{4,7})
    \s*(?P<devise_apres>CHF|EUR|€|Fr\.?|k€|K€|euros?)?
    """,
    re.VERBOSE | re.IGNORECASE,
)

_RE_SALAIRE_SIMPLE = re.compile(
    r"(?P<devise_avant>CHF|EUR|€)?\s*"
    r"(?P<n>\d{2,3}(?:[\s .,']\d{3})+|\d{2,3}[.,]?\d?\s*[kK]€?|\d{5,7})"
    r"\s*(?P<devise_apres>CHF|EUR|€|k€|K€)?",
    re.IGNORECASE,
)

_CONTEXTE_SALAIRE = re.compile(
    r"salaire|remuneration|rémunération|package|lohn|gehalt|salary|compensation|brut|annuel",
    re.IGNORECASE,
)


def _nombre(brut: str) -> float | None:
    b = brut.strip()
    facteur = 1.0
    if b.lower().endswith(("k", "k€")):
        b = b.rstrip("€").rstrip("kK").strip()
        facteur = 1000.0
        b = b.replace(",", ".")
        try:
            return float(b) * facteur
        except ValueError:
            return None
    b = _MILLIERS.sub("", b)
    try:
        return float(b) * facteur
    except ValueError:
        return None


def _devise(m: re.Match) -> str | None:
    for cle in ("devise_avant", "devise_milieu", "devise_apres"):
        v = (m.groupdict().get(cle) or "").strip().upper()
        if not v:
            continue
        if v.startswith("CHF") or v.startswith("FR"):
            return "CHF"
        if v.startswith("EUR") or "€" in v or v.startswith("K€"):
            return "EUR"
    return None


def extraire_salaire(texte: str, devise_par_defaut: str | None = None) -> tuple[float | None, float | None, str | None]:
    """(min, max, devise) trouves dans un texte libre, sinon (None, None, None).

    On ne retient que les montants plausibles pour un salaire ANNUEL cadre :
    entre 20 000 et 400 000. Cela evite de confondre avec un numero de
    telephone, un code postal ou un chiffre d'affaires.
    """
    if not texte:
        return None, None, None

    def plausible(v: float | None) -> bool:
        return v is not None and 20_000 <= v <= 400_000

    for m in _RE_SALAIRE.finditer(texte):
        v1, v2 = _nombre(m.group("n1")), _nombre(m.group("n2"))
        if plausible(v1) and plausible(v2) and v1 <= v2:
            return v1, v2, _devise(m) or devise_par_defaut

    # Montant unique, mais seulement s'il est proche d'un mot parlant de salaire.
    for m in _RE_SALAIRE_SIMPLE.finditer(texte):
        debut = max(0, m.start() - 60)
        if not _CONTEXTE_SALAIRE.search(texte[debut : m.end() + 30]):
            continue
        v = _nombre(m.group("n"))
        if plausible(v):
            d = _devise(m) or devise_par_defaut
            return v, v, d

    return None, None, None


def ingerer(offres: Iterable[Offre], source: str) -> Rapport:
    """Score puis enregistre une serie d'offres. Point de passage unique."""
    from .. import db
    from ..scoring import scorer

    rapport = Rapport(source=source)
    for offre in offres:
        rapport.collectees += 1
        try:
            if not offre.source:
                offre.source = source
            scorer(offre)
            _, nouvelle = db.enregistrer_offre(offre)
            if nouvelle:
                rapport.nouvelles += 1
        except Exception as exc:
            log.exception("ingestion impossible : %s", offre.titre[:60])
            rapport.erreurs.append(f"{offre.titre[:40]} : {exc}")
    db.marquer_etat_collecte(source, resultat=rapport.resume())
    return rapport
