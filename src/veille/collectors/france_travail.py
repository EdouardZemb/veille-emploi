"""Collecteur France Travail - API officielle Offres d'emploi v2.

C'est le canal le plus fiable cote francais : API publique, gratuite, prevue
pour cet usage. Identifiants a creer sur https://francetravail.io (voir
docs/DEMARRAGE.md), puis renseignes dans config/.env :

    FT_CLIENT_ID=...
    FT_CLIENT_SECRET=...

Sans identifiants, le collecteur se met en pause proprement plutot que
d'echouer : le reste de la chaine continue de tourner.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import httpx

from ..config import charger_sources, masquer
from ..models import Offre
from .base import extraire_salaire

log = logging.getLogger(__name__)

URL_TOKEN = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
URL_API = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPES = "api_offresdemploiv2 o2dsoffre"

# L'API plafonne a 150 resultats par requete et refuse un index au-dela de 3000.
TAILLE_PAGE = 150
INDEX_MAX = 3000


class IdentifiantsManquants(RuntimeError):
    pass


class ClientFranceTravail:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        self.client_id = client_id or os.environ.get("FT_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("FT_CLIENT_SECRET", "")
        if not self.client_id or not self.client_secret:
            raise IdentifiantsManquants(
                "FT_CLIENT_ID / FT_CLIENT_SECRET absents - cree une application sur francetravail.io"
            )
        self._jeton: str | None = None
        self._expire_a: float = 0.0
        self._http = httpx.Client(timeout=30.0, headers={"Accept": "application/json"})

    # -- authentification ------------------------------------------------
    def _jeton_valide(self) -> str:
        if self._jeton and time.time() < self._expire_a - 30:
            return self._jeton
        rep = self._http.post(
            URL_TOKEN,
            params={"realm": "/partenaire"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": SCOPES,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if rep.status_code != 200:
            # `raise_for_status` met le corps de la reponse dans le message de
            # l'exception, qui finira au journal. On le masque d'abord.
            raise RuntimeError(
                f"France Travail refuse les identifiants (HTTP {rep.status_code}) : "
                f"{masquer(rep.text)[:200]}"
            )
        charge = rep.json()
        self._jeton = charge["access_token"]
        self._expire_a = time.time() + float(charge.get("expires_in", 1499))
        return self._jeton

    # -- recherche -------------------------------------------------------
    def rechercher(self, parametres: dict[str, Any], plafond: int = 300) -> list[dict[str, Any]]:
        """Pagine la recherche jusqu'a `plafond` resultats."""
        resultats: list[dict[str, Any]] = []
        debut = 0
        while debut < min(plafond, INDEX_MAX):
            fin = min(debut + TAILLE_PAGE - 1, plafond - 1, INDEX_MAX - 1)
            p = dict(parametres, range=f"{debut}-{fin}")
            rep = self._http.get(
                URL_API, params=p, headers={"Authorization": f"Bearer {self._jeton_valide()}"}
            )
            if rep.status_code == 204:  # aucun resultat
                break
            if rep.status_code == 429:  # l'API demande de ralentir
                time.sleep(2.0)
                continue
            rep.raise_for_status()
            lot = (rep.json() or {}).get("resultats", []) or []
            resultats.extend(lot)
            if len(lot) < (fin - debut + 1):
                break
            debut = fin + 1
            time.sleep(0.15)  # l'API tolere 10 req/s ; on reste tres en dessous
        return resultats

    def close(self) -> None:
        self._http.close()


# --------------------------------------------------------------------------
# Conversion vers notre modele
# --------------------------------------------------------------------------

_CONTRATS_LISIBLES = {
    "CDI": "CDI",
    "CDD": "CDD",
    "MIS": "Interim",
    "SAI": "Saisonnier",
    "FRA": "Franchise",
    "LIB": "Profession liberale",
}


def _date(brut: str | None) -> date | None:
    if not brut:
        return None
    try:
        return datetime.fromisoformat(brut.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def convertir(brut: dict[str, Any]) -> Offre:
    lieu = (brut.get("lieuTravail") or {}).get("libelle") or ""
    entreprise = (brut.get("entreprise") or {}).get("nom") or ""
    description = brut.get("description") or ""

    bloc_salaire = brut.get("salaire") or {}
    texte_salaire = " ".join(
        str(v) for v in (bloc_salaire.get("libelle"), bloc_salaire.get("commentaire")) if v
    )
    smin, smax, devise = extraire_salaire(texte_salaire, devise_par_defaut="EUR")

    contrat = brut.get("typeContratLibelle") or _CONTRATS_LISIBLES.get(
        brut.get("typeContrat", ""), brut.get("typeContrat", "")
    )

    url = (brut.get("origineOffre") or {}).get("urlOrigine") or ""
    if not url and brut.get("id"):
        url = f"https://candidat.francetravail.fr/offres/recherche/detail/{brut['id']}"

    # Le teletravail est parfois un champ dedie, parfois seulement dans le texte.
    if brut.get("teletravail") is True and "teletravail" not in description.lower():
        description += "\nTeletravail possible (champ France Travail)."

    return Offre(
        titre=brut.get("intitule") or "",
        employeur=entreprise,
        lieu=lieu,
        description=description,
        url=url,
        source="france_travail",
        date_publication=_date(brut.get("dateCreation")),
        salaire_min=smin,
        salaire_max=smax,
        salaire_devise=devise,
        type_contrat=contrat,
    )


# --------------------------------------------------------------------------
# Entree du collecteur
# --------------------------------------------------------------------------

nom = "france_travail"


def _recherches_configurees() -> list[dict[str, Any]]:
    sources = charger_sources()
    bloc = (sources.get("france_travail") or {})
    if not bloc.get("actif", True):
        return []
    return bloc.get("recherches", []) or []


def collecter(jours: int = 7) -> Iterable[Offre]:
    """Execute toutes les recherches declarees dans le sources.yaml de la configuration."""
    recherches = _recherches_configurees()
    if not recherches:
        log.info("France Travail : aucune recherche configuree")
        return []

    try:
        client = ClientFranceTravail()
    except IdentifiantsManquants as exc:
        log.warning("France Travail en pause : %s", exc)
        return []

    depuis = (datetime.now(timezone.utc) - timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    vues: set[str] = set()
    offres: list[Offre] = []
    try:
        for recherche in recherches:
            params = {k: v for k, v in recherche.items() if k not in ("libelle", "plafond")}
            params.setdefault("minCreationDate", depuis)
            params.setdefault("maxCreationDate", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            try:
                bruts = client.rechercher(params, plafond=int(recherche.get("plafond", 150)))
            except httpx.HTTPStatusError as exc:
                log.error(
                    "France Travail, recherche %s : HTTP %s %s",
                    recherche.get("libelle", "?"),
                    exc.response.status_code,
                    masquer(exc.response.text)[:200],
                )
                continue
            log.info("France Travail / %s : %d offres", recherche.get("libelle", "?"), len(bruts))
            for b in bruts:
                if b.get("id") in vues:
                    continue
                vues.add(b.get("id"))
                offres.append(convertir(b))
    finally:
        client.close()
    return offres
