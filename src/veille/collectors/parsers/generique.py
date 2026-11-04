"""Parseur generique - filet de securite pour tous les autres emetteurs.

C'est lui qui fait rentrer dans le dispositif les employeurs sans API ni flux :
toute page carriere proposant une alerte, que `sources.yaml` declare.

Il ne connait aucun format : il cherche les liens qui ressemblent a une fiche
de poste, prend le texte du lien comme intitule, et lit le bloc alentour. Le
resultat est plus pauvre qu'un parseur dedie, et c'est assume - le champ
`donnees_partielles` le dira dans l'explication du score.

MODELE A COPIER pour ecrire un parseur dedie a un site precis.
"""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .base import AnnonceBrute, conteneur_parent, est_bruit, nettoyer, separer_employeur_lieu, texte_du_bloc

# Un segment d'URL qui annonce une fiche de poste.
_SEGMENT_METIER = re.compile(
    r"^(jobs?|joboffers?|jobdetails?|careers?|karriere|stellen?|stellenangebote?"
    r"|vacancy|vacancies|offres?|emplois?|positions?|openings?|postings?"
    r"|recruit|recruitment|apply|vacatures?)$",
    re.IGNORECASE,
)

# Un identifiant porte par un parametre de requete.
#
# ATTENTION : ne PAS accepter un simple `id=`. Les lettres d'information
# numerotent tous leurs liens ainsi (`/r/?id=h2801326e,18a0dc9c,15ca1ed7`), et
# une newsletter marketing de l'Apec produisait ainsi 14 fausses offres — ses
# liens « Mon compte », « Je consulte les tendances » ou « Cet ete, prenez un
# temps d'avance » etaient enregistres comme des postes. Le parametre doit
# nommer explicitement une offre.
_PARAM_IDENTIFIANT = re.compile(
    r"(job_?id|jobref|requisition_?id|req_?id|vacancy_?id|posting_?id"
    r"|offre_?id|offerid|annonce_?id|stellen_?id)=[\w-]{3,}",
    re.IGNORECASE,
)

# Reseaux sociaux : compares sur l'HOTE, et ancres.
# Sans ancrage, "x.com" rejetait aussi linux.com, phoenix.com et netflix.com -
# des domaines qui peuvent parfaitement heberger une page carriere.
_HOTES_IGNORES = re.compile(
    r"(^|\.)(facebook|twitter|x|instagram|youtube|xing|glassdoor|tiktok|pinterest)"
    r"\.(com|fr|de|ch|co|be)$",
    re.IGNORECASE,
)

# Liens de service : le mot peut etre dans le chemin ou dans la requete.
_SERVICES_IGNORES = re.compile(
    r"(unsubscribe|desabonn|se-desinscrire|preferences|privacy|imprint|impressum"
    r"|mentions-legales|datenschutz)",
    re.IGNORECASE,
)

# Ressources : l'extension se juge sur le CHEMIN SEUL, sinon la requete
# ajoutee derriere fait echouer l'ancre de fin ("/logo.png?" ne finit pas
# par ".png").
_EXTENSIONS_IGNOREES = re.compile(r"\.(png|jpe?g|gif|svg|webp|css|js|ico)$", re.IGNORECASE)


def _a_ignorer(href: str) -> bool:
    parties = urlsplit(href)
    if _HOTES_IGNORES.search((parties.hostname or "").lower()):
        return True
    if _EXTENSIONS_IGNOREES.search(parties.path):
        return True
    return bool(_SERVICES_IGNORES.search(parties.path + " " + (parties.query or "")))

_RE_SALAIRE = re.compile(
    r"((?:CHF|EUR|€)\s*\d[\d\s .,']{3,}[^\n]{0,30}|\d[\d\s .,']{3,}\s*(?:CHF|EUR|€)[^\n]{0,30})",
    re.IGNORECASE,
)


def _ressemble_a_une_fiche(href: str) -> bool:
    """Distingue une fiche de poste d'un lien de navigation.

    Regle : un segment d'URL annonce une fiche ("/job/", "/careers/"), et il
    faut quelque chose APRES lui. C'est ce qui separe
    `/careers/senior-test-engineer` (une fiche) de `/careers` ("voir toutes nos
    offres").

    On n'exige PAS d'identifiant numerique. La version precedente le faisait, et
    elle aurait rejete toutes les pages carriere a slug - or ce sont justement
    les employeurs sans API ni flux, ceux que seul le canal mail fait entrer.
    """
    parties = urlsplit(href)
    segments = [s for s in parties.path.split("/") if s]

    for i, segment in enumerate(segments):
        if _SEGMENT_METIER.match(segment) and i + 1 < len(segments):
            return True

    # Certains sites gardent tout en parametres : /recherche?jobId=12345
    return bool(_PARAM_IDENTIFIANT.search(parties.query or ""))


class ParseurGenerique:
    cle = "generique"
    libelle = "Generique (page carriere, employeur direct)"

    def reconnait(self, expediteur: str, sujet: str) -> bool:
        # Dernier recours : appele seulement si aucun parseur dedie n'a repondu.
        return True

    def extraire(self, soup: BeautifulSoup, texte: str) -> Iterable[AnnonceBrute]:
        vues: set[str] = set()
        annonces: list[AnnonceBrute] = []

        for lien in soup.find_all("a", href=True):
            href = lien["href"]
            if _a_ignorer(href) or not _ressemble_a_une_fiche(href):
                continue

            titre = nettoyer(lien.get_text(" "))
            if est_bruit(titre) or len(titre) > 160:
                continue
            cle_dedup = titre.lower()
            if cle_dedup in vues:
                continue
            vues.add(cle_dedup)

            bloc = conteneur_parent(lien, niveaux=4)
            lignes = texte_du_bloc(bloc)
            employeur, lieu = separer_employeur_lieu(lignes, titre)
            bloc_texte = " ".join(lignes)
            m_sal = _RE_SALAIRE.search(bloc_texte)

            annonces.append(
                AnnonceBrute(
                    titre=titre,
                    url=href,
                    employeur=employeur,
                    lieu=lieu,
                    extrait=bloc_texte[:600],
                    salaire_texte=m_sal.group(1) if m_sal else "",
                )
            )
        return annonces
