"""Registre des parseurs d'alertes mail.

POUR AJOUTER UN SITE :
  1. copie `generique.py` en `mon_site.py`, adapte `reconnait` et `extraire` ;
  2. importe la classe ici et ajoute-la dans PARSEURS, AVANT ParseurGenerique
     (qui accepte tout et doit donc rester en dernier).
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import AnnonceBrute, Parseur
from .generique import ParseurGenerique
from .indeed import ParseurIndeed
from .jobs_ch import ParseurJobsCh
from .linkedin import ParseurLinkedIn

# L'ordre compte : le premier qui reconnait le mail l'emporte.
PARSEURS: list[Parseur] = [
    ParseurLinkedIn(),
    ParseurIndeed(),
    ParseurJobsCh(),
    ParseurGenerique(),  # toujours en dernier
]


def choisir(expediteur: str, sujet: str) -> Parseur:
    for p in PARSEURS:
        try:
            if p.reconnait(expediteur, sujet):
                return p
        except Exception:
            continue
    return PARSEURS[-1]


def analyser(html: str, texte: str, expediteur: str, sujet: str) -> tuple[str, list[AnnonceBrute]]:
    """Rend (cle_du_parseur, annonces)."""
    parseur = choisir(expediteur, sujet)
    soup = BeautifulSoup(html or texte or "", "lxml")
    annonces = [a for a in parseur.extraire(soup, texte) if a.valide()]
    return parseur.cle, annonces


__all__ = ["AnnonceBrute", "PARSEURS", "analyser", "choisir"]
