"""Parseur des alertes mail Indeed.

Structure observee : chaque annonce est un lien vers /rc/clk?jk=<identifiant>
(ou /pagead/clk), le texte du lien est l'intitule, et la ligne suivante porte
"Employeur - Lieu". Indeed affiche souvent le salaire quand il est connu.
"""

from __future__ import annotations

import re
from typing import Iterable

from bs4 import BeautifulSoup

from .base import AnnonceBrute, conteneur_parent, est_bruit, nettoyer, separer_employeur_lieu, texte_du_bloc

_RE_LIEN_OFFRE = re.compile(r"indeed\.[a-z.]{2,6}/(?:rc/clk|pagead/clk|viewjob|applystart)", re.IGNORECASE)
_RE_JK = re.compile(r"[?&]jk=([0-9a-f]{10,20})", re.IGNORECASE)
_RE_SALAIRE = re.compile(
    r"(\d[\d\s .,']{2,}\s*(?:€|EUR|CHF)[^\n]{0,40}"
    r"|(?:€|EUR|CHF)\s*\d[\d\s .,']{2,}[^\n]{0,40})",
    re.IGNORECASE,
)
_RE_CONTRAT = re.compile(r"\b(CDI|CDD|Intérim|Interim|Temps plein|Temps partiel|Freelance|Stage|Apprentissage)\b", re.IGNORECASE)


class ParseurIndeed:
    cle = "indeed"
    libelle = "Indeed - alertes offres"

    def reconnait(self, expediteur: str, sujet: str) -> bool:
        e = (expediteur or "").lower()
        return "indeed.com" in e or "indeed.fr" in e or "indeedemail" in e

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

            jk = _RE_JK.search(href)
            # Sans identifiant on se rabat sur l'intitule pour eviter les doublons
            # a l'interieur du meme mail.
            cle_dedup = jk.group(1) if jk else titre.lower()
            if cle_dedup in vues:
                continue
            vues.add(cle_dedup)

            bloc = conteneur_parent(lien, niveaux=4)
            lignes = texte_du_bloc(bloc)
            employeur, lieu = separer_employeur_lieu(lignes, titre)
            bloc_texte = " ".join(lignes)

            m_sal = _RE_SALAIRE.search(bloc_texte)
            m_ctr = _RE_CONTRAT.search(bloc_texte)

            annonces.append(
                AnnonceBrute(
                    titre=titre,
                    url=href,
                    employeur=employeur,
                    lieu=lieu,
                    extrait=bloc_texte[:600],
                    salaire_texte=m_sal.group(1) if m_sal else "",
                    contrat=m_ctr.group(1) if m_ctr else "",
                )
            )
        return annonces
