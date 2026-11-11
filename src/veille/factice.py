"""Le jeu de donnees factice du staging.

Le staging ne tient jamais de donnees reelles (invariant M-0001) : le dossier
`factice/` du depot, ecrit a la main, le remplit au premier demarrage. Les
offres passent par `ingerer`, donc par le scoring normal ; les candidatures
passent par `changer_statut`, donc par l'historique normal.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import config, db
from .collectors.base import ingerer
from .models import Offre

log = logging.getLogger(__name__)

SOURCE = "factice"

# Les statuts qu'une candidature du jeu peut porter : un par etat du parcours.
STATUTS_ADMIS = ("interessante", "a_traiter", "candidature_envoyee", "entretien")


class BaseNonVide(Exception):
    """Le jeu factice ne se charge que dans une base sans offre."""


def _dossier() -> Path:
    return config.RACINE / "factice"


def _lire(nom: str) -> dict:
    return yaml.safe_load((_dossier() / nom).read_text(encoding="utf-8")) or {}


def _rendre_pdf(html: str, destination: Path) -> None:
    """HTML -> PDF par WeasyPrint (importe ici : absent de certains postes)."""
    from weasyprint import HTML

    HTML(string=html).write_pdf(str(destination))


def _rendre_le_kit() -> None:
    kit = Path(config.CHEMIN_KIT)
    kit.mkdir(parents=True, exist_ok=True)
    for source in sorted((_dossier() / "kit").glob("*.html")):
        _rendre_pdf(source.read_text(encoding="utf-8"), kit / f"{source.stem}.pdf")


def _offre(d: dict) -> Offre:
    publiee = d.get("date_publication")
    return Offre(
        titre=d["titre"],
        employeur=d.get("employeur", ""),
        lieu=d.get("lieu", ""),
        description=d.get("description", ""),
        url=d.get("url", ""),
        date_publication=publiee if isinstance(publiee, date) else None,
        salaire_min=d.get("salaire_min"),
        salaire_max=d.get("salaire_max"),
        salaire_devise=d.get("salaire_devise"),
        type_contrat=d.get("type_contrat", ""),
    )


def charger() -> int:
    """Charge le jeu dans une base vide ; rend le nombre d'offres chargees.

    Ordre : refus si la base a des offres, puis le kit (un echec du rendu laisse
    la base vide, le demarrage suivant reessaie), puis les offres, puis les
    candidatures."""
    with db.connexion() as cx:
        if cx.execute("SELECT COUNT(*) FROM offres").fetchone()[0]:
            raise BaseNonVide("la base contient deja des offres")

    _rendre_le_kit()

    offres = [_offre(d) for d in _lire("offres.yaml")["offres"]]
    rapport = ingerer(offres, SOURCE)
    if rapport.erreurs:
        raise RuntimeError(f"jeu factice : {len(rapport.erreurs)} offre(s) refusee(s) : {rapport.erreurs[0]}")

    for c in _lire("candidatures.yaml").get("candidatures", []):
        with db.connexion() as cx:
            ligne = cx.execute("SELECT id FROM offres WHERE url = ?", (c["url"],)).fetchone()
        if ligne is None:
            raise RuntimeError(f"jeu factice : candidature sur une offre inconnue : {c['url']}")
        statut = c.get("statut", "candidature_envoyee")
        if statut not in STATUTS_ADMIS:
            raise RuntimeError(f"jeu factice : statut refusé : {statut}")
        if statut == "candidature_envoyee":
            db.changer_statut(ligne["id"], statut, canal=c.get("canal"))
        else:
            db.changer_statut(ligne["id"], statut)
        if c.get("relance_due"):
            veille = (date.today() - timedelta(days=1)).isoformat()
            db.maj_champs(ligne["id"], date_relance_due=veille)

    return rapport.nouvelles


def charger_au_demarrage() -> None:
    """Appele par le demarrage de la console en staging : ne bloque jamais."""
    try:
        n = charger()
    except BaseNonVide:
        return  # un redemarrage ordinaire
    except Exception as exc:
        log.error("jeu factice non charge : %s", exc)
    else:
        log.info("jeu factice charge : %d offres", n)
