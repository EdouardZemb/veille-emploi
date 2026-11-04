"""Parseur des alertes mail jobs.ch / jobup.ch / jobscout24.

Formats proches : liens vers /vacancies/detail/<id> ou /fr/vacancies/detail/.
Le lieu est presque toujours un canton ou une ville suisse, et les montants
sont en CHF - ce qui bascule le bareme salarial du scoring cote suisse.
"""

from __future__ import annotations

import re
from typing import Iterable

from bs4 import BeautifulSoup

from .base import AnnonceBrute, conteneur_parent, est_bruit, nettoyer, separer_employeur_lieu, texte_du_bloc

_RE_LIEN_OFFRE = re.compile(
    r"(jobs\.ch|jobup\.ch|jobscout24\.ch)/[^\"'\s]*?(vacancies?/detail|job/|stelle|emploi)",
    re.IGNORECASE,
)
_RE_ID = re.compile(r"detail/(\d{5,})", re.IGNORECASE)
_RE_SALAIRE_CHF = re.compile(r"(CHF\s*\d[\d\s .,']{3,}[^\n]{0,40}|\d[\d\s .,']{3,}\s*CHF[^\n]{0,40})", re.IGNORECASE)
_RE_TAUX = re.compile(r"(\d{2,3}\s*[-–]\s*\d{2,3}\s*%|\d{2,3}\s*%)")


class ParseurJobsCh:
    cle = "jobs_ch"
    libelle = "jobs.ch / jobup.ch - alertes offres"

    def reconnait(self, expediteur: str, sujet: str) -> bool:
        e = (expediteur or "").lower()
        return any(d in e for d in ("jobs.ch", "jobup.ch", "jobscout24", "jobcloud"))

    def extraire(self, soup: BeautifulSoup, texte: str) -> Iterable[AnnonceBrute]:
        vues: set[str] = set()
        annonces: list[AnnonceBrute] = []

        for lien in soup.find_all("a", href=True):
            href = lien["href"]
            if not _RE_LIEN_OFFRE.search(href):
                continue

            titre = nettoyer(lien.get_text(" "))
            if est_bruit(titre):
                continue

            m_id = _RE_ID.search(href)
            cle_dedup = m_id.group(1) if m_id else titre.lower()
            if cle_dedup in vues:
                continue
            vues.add(cle_dedup)

            bloc = conteneur_parent(lien, niveaux=4)
            lignes = texte_du_bloc(bloc)
            employeur, lieu = separer_employeur_lieu(lignes, titre)
            bloc_texte = " ".join(lignes)

            m_sal = _RE_SALAIRE_CHF.search(bloc_texte)
            m_taux = _RE_TAUX.search(bloc_texte)

            annonces.append(
                AnnonceBrute(
                    titre=titre,
                    url=href,
                    employeur=employeur,
                    # Si le lieu n'a pas ete devine, on marque quand meme la Suisse
                    # pour que le bon bareme salarial s'applique.
                    lieu=lieu or "Suisse",
                    extrait=bloc_texte[:600],
                    salaire_texte=m_sal.group(1) if m_sal else "",
                    contrat=f"Taux {m_taux.group(1)}" if m_taux else "",
                )
            )
        return annonces
