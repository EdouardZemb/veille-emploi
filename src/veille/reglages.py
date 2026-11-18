"""Reglages modifiables depuis la console, donc depuis son telephone.

Ce qui vit ici est ce qu'on ajuste en marchant : le seuil qui declenche une
notification, la frequence de collecte. Le reste - familles
de metiers, motifs, planchers salariaux - reste dans le `criteres.yaml` de la configuration,
qui se modifie a l'aise sur un clavier.

Le seuil vit en base (table `reglages`), amorce une fois depuis
le `criteres.yaml` de la configuration, que la console n'ecrit plus. La frequence vit aussi en
base, dans tous les modes : le planificateur la lit, et seule la prod collecte.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from . import db
from .config import charger_criteres, environnement

PARIS = ZoneInfo("Europe/Paris")
FREQUENCE_DEFAUT = "trois_fois"

# Frequences proposees. On ne laisse pas saisir d'heures libres : une heure fausse
# casserait la collecte en silence. Le planificateur lit les `heures`.
FREQUENCES = {
    "trois_fois": {
        "libelle": "Trois fois par jour (7h15, 12h15, 18h15)",
        "heures": [(7, 15), (12, 15), (18, 15)],
        "detail": "Après les envois d'alertes du matin, du midi et du soir.",
    },
    "deux_fois": {
        "libelle": "Deux fois par jour (7h15, 18h15)",
        "heures": [(7, 15), (18, 15)],
        "detail": "Suffit si tu consultes matin et soir.",
    },
    "une_fois": {
        "libelle": "Une fois par jour (7h15)",
        "heures": [(7, 15)],
        "detail": "Le minimum utile : les alertes mail arrivent surtout la nuit.",
    },
    "toutes_les_deux_heures": {
        "libelle": "Toutes les deux heures (7h à 21h)",
        "heures": [(7, 15), (9, 15), (11, 15), (13, 15), (15, 15), (17, 15), (19, 15), (21, 15)],
        "detail": "Pour une période de recherche intensive.",
    },
}


# --------------------------------------------------------------------------
# Seuil de notification
# --------------------------------------------------------------------------


def initialiser() -> None:
    """Amorce la base : le seuil de criteres.yaml, une seule fois."""
    if db.lire_reglage("seuil") is None:
        defaut = charger_criteres().scoring.get("seuil_interessant", 45)
        db.ecrire_reglage("seuil", f"{float(defaut):g}")


def lire_seuil() -> float:
    """Le seuil en base ; a defaut (base pas encore amorcee), celui de criteres.yaml."""
    valeur = db.lire_reglage("seuil")
    if valeur is not None:
        return float(valeur)
    return float(charger_criteres().scoring.get("seuil_interessant", 45))


def ecrire_seuil(valeur: float) -> None:
    if not 0 <= valeur <= 200:
        raise ValueError("le seuil doit être compris entre 0 et 200")

    db.ecrire_reglage("seuil", f"{float(valeur):g}")


# --------------------------------------------------------------------------
# Frequence de collecte
# --------------------------------------------------------------------------


def prochain_passage(cle: str, instant: datetime) -> datetime:
    """Le prochain passage de la collecte, en heure de Paris, strictement apres `instant`."""
    heures = FREQUENCES[cle]["heures"]
    local = instant.astimezone(PARIS)
    for decalage in range(3):
        jour = local.date() + timedelta(days=decalage)
        for h, m in heures:
            candidat = datetime(jour.year, jour.month, jour.day, h, m, tzinfo=PARIS)
            if candidat.astimezone(timezone.utc) > instant.astimezone(timezone.utc):
                return candidat
    raise RuntimeError("aucun passage trouve")  # inatteignable : une heure par jour au moins


def _public(frequence: dict[str, Any]) -> dict[str, Any]:
    """La frequence sans ses heures (tuples) : le reste part vers la console."""
    return {k: v for k, v in frequence.items() if k != "heures"}


def _choix() -> list[dict[str, Any]]:
    return [{"cle": k, **_public(v)} for k, v in FREQUENCES.items()]


def lire_frequence() -> dict[str, Any]:
    """La frequence lue en base, dans tous les modes ; la collecte n'est active qu'en prod."""
    cle = db.lire_reglage("frequence")
    if cle not in FREQUENCES:
        cle = FREQUENCE_DEFAUT
    prochain = prochain_passage(cle, datetime.now(timezone.utc))
    return {
        "cle": cle,
        "prochain_passage": prochain.strftime("%Y-%m-%d %H:%M"),
        "actif": environnement() == "prod",
        "choix": _choix(),
    }


def ecrire_frequence(cle: str) -> dict[str, Any]:
    """Ecrit la frequence en base, dans tous les modes. Une cle inconnue leve ValueError."""
    if cle not in FREQUENCES:
        raise ValueError(f"fréquence inconnue : {cle}")
    db.ecrire_reglage("frequence", cle)
    return lire_frequence()


# --------------------------------------------------------------------------
# Etat des sources, en lecture seule
# --------------------------------------------------------------------------


def etat_sources() -> list[dict[str, Any]]:
    """Ce qui est pret et ce qui attend encore une action de sa part."""
    import os

    from . import db
    from .config import charger_sources

    sources = charger_sources()
    with db.connexion() as cx:
        passages = {
            r["source"]: dict(r)
            for r in cx.execute("SELECT * FROM etat_collecte").fetchall()
        }

    def passage(nom: str) -> dict[str, str]:
        p = passages.get(nom, {})
        return {
            "derniere_execution": p.get("derniere_execution") or "",
            "dernier_resultat": p.get("dernier_resultat") or "",
        }

    ft_pret = bool(os.environ.get("FT_CLIENT_ID") and os.environ.get("FT_CLIENT_SECRET"))
    mail_pret = bool(
        os.environ.get("VEILLE_IMAP_UTILISATEUR") and os.environ.get("VEILLE_IMAP_MOTDEPASSE")
    )

    return [
        {
            "cle": "france_travail",
            "libelle": "France Travail (API officielle)",
            "pret": ft_pret,
            "manque": "" if ft_pret else "FT_CLIENT_ID et FT_CLIENT_SECRET à créer sur francetravail.io",
            "detail": f"{len((sources.get('france_travail') or {}).get('recherches', []))} recherches configurées",
            **passage("france_travail"),
        },
        {
            "cle": "courriel",
            "libelle": "Alertes mail (IMAP)",
            "pret": mail_pret,
            "manque": "" if mail_pret else "mot de passe d'application Gmail, et les alertes à créer sur chaque site",
            "detail": f"libellé lu : {os.environ.get('VEILLE_IMAP_DOSSIER', 'veille-emploi')}",
            **passage("courriel"),
        },
        {
            "cle": "arbeitnow",
            "libelle": "Arbeitnow (API publique)",
            "pret": True,
            "manque": "",
            "detail": "aucun identifiant nécessaire",
            **passage("arbeitnow"),
        },
        {
            "cle": "rss",
            "libelle": "Flux RSS",
            "pret": True,
            "manque": "",
            "detail": f"{len(sources.get('rss') or [])} flux déclarés",
            **passage("rss"),
        },
    ]
