"""Collecteur de flux RSS / Atom.

Deuxieme canal par ordre de fiabilite : le site publie lui-meme le flux, on ne
fait que le lire. Chaque flux est declare dans le sources.yaml de la configuration.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Iterable

import feedparser

from ..config import charger_sources, contient, normaliser
from ..models import Offre
from .base import extraire_salaire

log = logging.getLogger(__name__)

nom = "rss"

_BALISES = re.compile(r"<[^>]+>")


def _texte(html: str | None) -> str:
    if not html:
        return ""
    t = _BALISES.sub(" ", html)
    t = re.sub(r"&(nbsp|amp|lt|gt|quot|#39);", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _date_entree(entree: Any) -> date | None:
    for champ in ("published_parsed", "updated_parsed"):
        valeur = getattr(entree, champ, None)
        if valeur:
            try:
                return datetime(*valeur[:6]).date()
            except (TypeError, ValueError):
                continue
    return None


def _employeur(entree: Any, flux: dict[str, Any]) -> str:
    """L'employeur n'a pas de place normalisee en RSS.

    Ordre : champ explicite du flux, puis auteur, puis motif d'extraction
    declare dans la configuration (ex. un titre "Poste chez Employeur").
    """
    if flux.get("employeur_fixe"):
        return flux["employeur_fixe"]
    for champ in ("author", "dc_creator", "publisher"):
        v = getattr(entree, champ, None)
        if v:
            return str(v).strip()
    motif = flux.get("employeur_motif")
    if motif:
        m = re.search(motif, getattr(entree, "title", "") or "")
        if m and m.groups():
            return m.group(1).strip()
    return ""


def _lieu(entree: Any, flux: dict[str, Any]) -> str:
    for champ in ("location", "job_location", "region"):
        v = getattr(entree, champ, None)
        if v:
            return str(v).strip()
    motif = flux.get("lieu_motif")
    if motif:
        m = re.search(motif, getattr(entree, "title", "") or "")
        if m and m.groups():
            return m.group(1).strip()
    return flux.get("lieu_par_defaut", "")


def convertir(entree: Any, flux: dict[str, Any]) -> Offre:
    description = _texte(
        getattr(entree, "summary", None)
        or (getattr(entree, "content", [{}])[0].get("value") if getattr(entree, "content", None) else "")
    )
    titre = _texte(getattr(entree, "title", "")) or "(sans intitule)"
    if flux.get("titre_nettoyage"):
        titre = re.sub(flux["titre_nettoyage"], "", titre).strip(" -|–")

    devise = flux.get("devise", "EUR")
    smin, smax, dev = extraire_salaire(f"{titre} {description}", devise_par_defaut=devise)

    return Offre(
        titre=titre,
        employeur=_employeur(entree, flux),
        lieu=_lieu(entree, flux),
        description=description[:8000],
        url=getattr(entree, "link", "") or "",
        source=f"rss:{flux.get('cle', 'inconnu')}",
        date_publication=_date_entree(entree),
        salaire_min=smin,
        salaire_max=smax,
        salaire_devise=dev,
        type_contrat=flux.get("contrat_par_defaut", ""),
        # Un flux RSS ne donne souvent qu'un resume : on le signale si le
        # texte recupere est trop court pour porter un jugement.
        donnees_partielles=len(description) < 250,
    )


def collecter() -> Iterable[Offre]:
    flux_declares = charger_sources().get("rss", []) or []
    offres: list[Offre] = []
    for flux in flux_declares:
        if not flux.get("actif", True):
            continue
        url = flux.get("url")
        if not url:
            continue
        try:
            analyse = feedparser.parse(url, agent="veille-emploi/1.0 (usage personnel)")
        except Exception as exc:
            log.error("RSS %s : %s", flux.get("cle"), exc)
            continue
        if getattr(analyse, "bozo", 0) and not analyse.entries:
            log.error("RSS %s illisible : %s", flux.get("cle"), getattr(analyse, "bozo_exception", ""))
            continue

        mots_cles = flux.get("mots_cles", []) or []
        retenues = 0
        for entree in analyse.entries:
            if mots_cles:
                cible = normaliser(f"{getattr(entree,'title','')} {getattr(entree,'summary','')}")
                if not any(contient(cible, m) for m in mots_cles):
                    continue
            offres.append(convertir(entree, flux))
            retenues += 1
        log.info("RSS %s : %d entrees, %d retenues", flux.get("cle"), len(analyse.entries), retenues)
    return offres
