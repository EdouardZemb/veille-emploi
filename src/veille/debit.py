"""Limite de debit : un nombre de demandes par fenetre glissante, par cle.

POURQUOI : la connexion est la seule porte de la console. Sans limite, rien
n'empeche de la marteler. Derriere `tailscale serve` ou le tunnel, tout arrive
de la meme adresse : la cle du client vient donc de `CF-Connecting-IP` (voir
`cle_client`), et un plafond global, a cle vide, borne le total. Un seul
compteur laisserait un client qui martele enfermer tous les autres dehors.

Mecanique : les instants des demandes acceptees, dans la fenetre, une fenetre
par cle. Une demande refusee ne compte pas : le budget se rouvre une fenetre
apres les dernieres acceptees. Une cle dont la fenetre est vide est retiree ;
et, au plus une fois par fenetre, on balaie les cles qu'on ne revoit jamais
(adresses qui tournent) : la memoire reste bornee. L'horloge est
`auth.maintenant`, que les tests remplacent.
"""

from __future__ import annotations

import ipaddress
import threading
from collections import deque
from datetime import datetime, timedelta

from fastapi import Request

from . import auth

LONGUEUR_CLE_OPAQUE = 64


def cle_client(request: Request) -> str:
    """Le client pour la limite : `CF-Connecting-IP`, sinon l'adresse de la connexion.

    Une IPv6 compte pour son /64 (un abonne en a des milliards). Une valeur
    illisible reste une cle opaque telle quelle ; sans client, la cle est vide."""
    brute = request.headers.get("cf-connecting-ip", "").strip()
    if not brute:
        brute = request.client.host if request.client else ""
    try:
        adresse = ipaddress.ip_address(brute)
    except ValueError:
        return brute[:LONGUEUR_CLE_OPAQUE]
    if adresse.version == 6 and adresse.ipv4_mapped is not None:
        adresse = adresse.ipv4_mapped
    if adresse.version == 6:
        return str(ipaddress.ip_network(f"{adresse}/64", strict=False))
    return str(adresse)


class LimiteDebit:
    def __init__(self, maximum: int, fenetre: timedelta) -> None:
        self.maximum = maximum
        self.fenetre = fenetre
        self._acceptees: dict[str, deque[datetime]] = {}
        self._dernier_balayage: datetime | None = None
        self._verrou = threading.Lock()

    def autoriser(self, cle: str = "") -> bool:
        """Vrai si la demande passe ; elle compte alors dans la fenetre de la cle."""
        instant = auth.maintenant()
        with self._verrou:
            self._balayer(instant)
            fenetre = self._acceptees.get(cle)
            if fenetre is not None:
                self._purger(fenetre, instant)
                if not fenetre:
                    del self._acceptees[cle]
                    fenetre = None
            if fenetre is not None and len(fenetre) >= self.maximum:
                return False
            if fenetre is None:
                fenetre = self._acceptees[cle] = deque()
            fenetre.append(instant)
            return True

    def disponible(self, cle: str = "") -> bool:
        """Vrai s'il reste du budget a la cle ; ne compte rien et ne cree pas la cle."""
        instant = auth.maintenant()
        with self._verrou:
            self._balayer(instant)
            fenetre = self._acceptees.get(cle)
            if fenetre is None:
                return True
            self._purger(fenetre, instant)
            return len(fenetre) < self.maximum

    def enregistrer(self, cle: str = "") -> None:
        """Compte une demande acceptee (apres `disponible`)."""
        instant = auth.maintenant()
        with self._verrou:
            self._acceptees.setdefault(cle, deque()).append(instant)

    def _purger(self, fenetre: deque[datetime], instant: datetime) -> None:
        while fenetre and instant - fenetre[0] >= self.fenetre:
            fenetre.popleft()

    def _balayer(self, instant: datetime) -> None:
        """Retire les cles dont la derniere demande est hors fenetre (sous le verrou)."""
        if (self._dernier_balayage is not None
                and instant - self._dernier_balayage < self.fenetre):
            return
        self._dernier_balayage = instant
        for cle in [c for c, f in self._acceptees.items()
                    if not f or instant - f[-1] >= self.fenetre]:
            del self._acceptees[cle]

    def nombre_de_cles(self) -> int:
        """Les cles en memoire (pour les tests)."""
        with self._verrou:
            return len(self._acceptees)

    def vider(self) -> None:
        with self._verrou:
            self._acceptees.clear()
            self._dernier_balayage = None
