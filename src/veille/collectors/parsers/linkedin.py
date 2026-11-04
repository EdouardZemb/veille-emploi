"""Parseur des alertes mail LinkedIn ("nouvelles offres pour ...").

Rappel de la regle du projet : on ne parcourt JAMAIS LinkedIn. On lit
uniquement le mail que LinkedIn envoie de lui-meme. Le seul appel reseau
eventuel est la resolution du lien de suivi contenu dans ce mail, et il est
fait en aval par `collectors.liens`.

Structure observee : chaque annonce est un lien vers /comm/jobs/view/<id>,
dont le texte est l'intitule. L'employeur et le lieu sont dans le meme bloc
de tableau, sur les lignes suivantes.
"""

from __future__ import annotations

import re
from typing import Iterable

from bs4 import BeautifulSoup

from .base import AnnonceBrute, conteneur_parent, est_bruit, nettoyer, separer_employeur_lieu, texte_du_bloc

_RE_LIEN_OFFRE = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d{6,})", re.IGNORECASE)
_RE_ID = re.compile(r"/jobs/view/(\d{6,})")


class ParseurLinkedIn:
    cle = "linkedin"
    libelle = "LinkedIn - alertes offres"

    def reconnait(self, expediteur: str, sujet: str) -> bool:
        e = (expediteur or "").lower()
        s = (sujet or "").lower()
        if "linkedin.com" not in e:
            return False
        marqueurs = (
            "offre", "offres", "job", "jobs", "poste", "alerte", "alert",
            "recrute", "hiring", "opportunit", "stelle",
        )
        return any(m in s for m in marqueurs)

    def extraire(self, soup: BeautifulSoup, texte: str) -> Iterable[AnnonceBrute]:
        vues: set[str] = set()
        annonces: list[AnnonceBrute] = []

        for lien in soup.find_all("a", href=True):
            href = lien["href"]
            m = _RE_LIEN_OFFRE.search(href)
            if not m:
                continue
            identifiant = m.group(1)
            if identifiant in vues:
                continue

            titre = nettoyer(lien.get_text(" "))
            # Le lien "postuler" pointe vers la meme offre : on le saute, le
            # lien porteur du titre viendra (ou est deja venu).
            if est_bruit(titre):
                continue
            vues.add(identifiant)

            bloc = conteneur_parent(lien, niveaux=4)
            lignes = texte_du_bloc(bloc)
            employeur, lieu = separer_employeur_lieu(lignes, titre)

            annonces.append(
                AnnonceBrute(
                    titre=titre,
                    # On garde le lien de suivi tel quel : la resolution en URL
                    # canonique est faite plus loin, avec repli sur l'identifiant.
                    url=href,
                    employeur=employeur,
                    lieu=lieu,
                    extrait=" ".join(lignes[:6]),
                )
            )
        return annonces
