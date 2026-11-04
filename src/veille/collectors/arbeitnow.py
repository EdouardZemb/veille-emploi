"""Collecteur Arbeitnow - API publique, sans identifiants.

Arbeitnow publie son tableau d'offres via une API libre d'acces et documentee
(https://www.arbeitnow.com/api). Couverture : Europe germanophone, dont une
part de Suisse alemanique et beaucoup de postes en anglais. C'est la source qui
permet de faire tourner la chaine des le premier jour, sans inscription.

Elle ne remplace pas France Travail ni les alertes mail : c'est un complement.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable

import httpx

from ..config import charger_sources, contient, normaliser
from ..models import Offre
from .base import extraire_salaire

log = logging.getLogger(__name__)

URL = "https://www.arbeitnow.com/api/job-board-api"
nom = "arbeitnow"


def _pertinente(brut: dict[str, Any], mots_cles: list[str]) -> bool:
    """Filtre en amont : l'API ne sait pas chercher, elle rend tout le tableau.

    Sans ce filtre on ingererait 300 offres sans rapport a chaque passage. On
    garde large : le scoring fera le tri fin derriere.
    """
    if not mots_cles:
        return True
    cible = normaliser(f"{brut.get('title','')} {' '.join(brut.get('tags') or [])}")
    return any(contient(cible, m) for m in mots_cles)


def convertir(brut: dict[str, Any]) -> Offre:
    description = brut.get("description") or ""
    # L'API rend du HTML : on le degrossit pour que le scoring lise du texte.
    import re

    texte = re.sub(r"<[^>]+>", " ", description)
    texte = re.sub(r"&nbsp;?", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()

    lieu = brut.get("location") or ""
    if brut.get("remote"):
        lieu = f"{lieu} - Remote".strip(" -")
        texte += " Full remote possible."

    smin, smax, devise = extraire_salaire(texte, devise_par_defaut="EUR")

    horodatage = brut.get("created_at")
    publication = None
    if isinstance(horodatage, (int, float)):
        publication = datetime.fromtimestamp(horodatage).date()

    return Offre(
        titre=brut.get("title") or "",
        employeur=brut.get("company_name") or "",
        lieu=lieu,
        description=texte[:8000],
        url=brut.get("url") or "",
        source="arbeitnow",
        date_publication=publication,
        salaire_min=smin,
        salaire_max=smax,
        salaire_devise=devise,
        type_contrat=", ".join(brut.get("job_types") or []),
    )


def collecter() -> Iterable[Offre]:
    bloc = (charger_sources().get("arbeitnow") or {})
    if not bloc.get("actif", True):
        return []
    mots_cles = bloc.get("mots_cles", []) or []
    pages = int(bloc.get("pages", 1))

    offres: list[Offre] = []
    with httpx.Client(timeout=30.0, headers={"Accept": "application/json"}) as cli:
        for page in range(1, pages + 1):
            try:
                rep = cli.get(URL, params={"page": page} if page > 1 else None)
                rep.raise_for_status()
            except httpx.HTTPError as exc:
                log.error("Arbeitnow page %d : %s", page, exc)
                break
            lot = (rep.json() or {}).get("data", []) or []
            if not lot:
                break
            retenues = [b for b in lot if _pertinente(b, mots_cles)]
            log.info("Arbeitnow page %d : %d offres, %d retenues", page, len(lot), len(retenues))
            offres.extend(convertir(b) for b in retenues)
    return offres
