"""Socle des parseurs d'alertes mail.

Chaque site a son format HTML. Un parseur sait :
  - `reconnait(expediteur, sujet)` : est-ce un mail pour moi ?
  - `extraire(soup, texte_brut)`   : rendre la liste des annonces trouvees.

POUR AJOUTER UN SITE : copie `generique.py`, adapte les deux methodes, et
inscris la classe dans `parsers/__init__.py`. Rien d'autre a toucher.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from bs4 import BeautifulSoup, Tag


@dataclass
class AnnonceBrute:
    """Ce qu'un parseur arrive a tirer d'un bloc de mail.

    Volontairement pauvre : la plupart des alertes ne donnent qu'un intitule,
    un employeur, un lieu et un lien. Le texte complet de l'annonce n'y est
    presque jamais - d'ou `donnees_partielles` en aval.
    """

    titre: str
    url: str = ""
    employeur: str = ""
    lieu: str = ""
    extrait: str = ""
    contrat: str = ""
    salaire_texte: str = ""

    def valide(self) -> bool:
        return bool(self.titre.strip()) and len(self.titre.strip()) > 2


class Parseur(Protocol):
    cle: str
    libelle: str

    def reconnait(self, expediteur: str, sujet: str) -> bool: ...
    def extraire(self, soup: BeautifulSoup, texte: str) -> Iterable[AnnonceBrute]: ...


# --------------------------------------------------------------------------
# Aides communes
# --------------------------------------------------------------------------

_ESPACES = re.compile(r"[\s ​]+")

# Formulations de mise en page a ne jamais prendre pour un intitule de poste.
_BRUIT = re.compile(
    r"^(voir (toutes? )?les? offres?|see all jobs|view job|postuler|apply now|se desabonner"
    r"|unsubscribe|gerer mes alertes|manage alerts|afficher|alle jobs anzeigen|jetzt bewerben"
    r"|mehr erfahren|en savoir plus|voir l'offre|view all|show more|\d+ nouvelles? offres?"
    # Navigation des lettres d'information, l'Apec en particulier : 18 liens de
    # pied de page etaient enregistres comme des offres.
    r"|cliquez? ici|cliquant sur|lien suivant|mon compte|mon centre|mon espace"
    r"|je (consulte|telecharge|decouvre|postule)|politique de confidentialite"
    r"|mentions legales|protection des donnees|donnees personnelles|contactez"
    r"|consultez? la faq|gerer les alertes|votre alerte|vos alertes|ne manquez"
    r"|cet ete|telecharge[rz]? l'application|se connecter|nous contacter"
    r"|centre d'aide|aide et contact|alle$|tout voir|plus d'infos?)",
    re.IGNORECASE,
)

# "Employeur · Lieu", "Employeur - Lieu", "Employeur, Lieu"
_SEPARATEURS = re.compile(r"\s*[·•\|–—-]\s*|\s{2,}")

# Separateurs FORTS : ceux qui annoncent vraiment deux informations distinctes.
# Le trait d'union nu en est exclu, sinon « Bale-Ville » se coupe en deux et le
# nom de ville devient un employeur.
_SEPARATEURS_FORTS = re.compile(r"\s*[·•\|]\s*|\s+[–—-]\s+|\s{2,}")


def nettoyer(texte: str | None) -> str:
    if not texte:
        return ""
    return _ESPACES.sub(" ", texte).strip(" ·•|-–—\n\t")


def est_bruit(texte: str) -> bool:
    """Vrai pour un lien de navigation plutot qu'un intitule de poste.

    La comparaison se fait SANS ACCENTS : les motifs sont ecrits en clair
    (« mentions legales ») alors que les vrais liens sont accentues
    (« Mentions légales »). Cinq libelles passaient au travers.
    """
    from ...config import normaliser

    t = nettoyer(texte)
    if not t or len(t) < 3:
        return True
    return bool(_BRUIT.match(normaliser(t).strip()))


def texte_du_bloc(noeud: Tag | None, limite: int = 12) -> list[str]:
    """Lignes de texte lisibles d'un bloc HTML, sans les vides ni le bruit."""
    if noeud is None:
        return []
    lignes: list[str] = []
    for morceau in noeud.stripped_strings:
        t = nettoyer(morceau)
        if t and not est_bruit(t) and t not in lignes:
            lignes.append(t)
        if len(lignes) >= limite:
            break
    return lignes


def conteneur_parent(lien: Tag, niveaux: int = 4) -> Tag | None:
    """Remonte jusqu'au bloc qui contient probablement toute l'annonce.

    Les alertes mail sont faites de tableaux imbriques : le lien du titre est
    profondement enfoui, et l'employeur/le lieu sont dans un <td> voisin.

    REGLE DE REMONTEE : on monte tant que le bloc ne contient aucun AUTRE lien
    porteur de texte visible. Elle tient sur les deux cas qui comptent :
      - un logo cliquable ou une icone (lien sans texte) n'arrete pas la
        remontee, donc on recupere bien l'employeur place a cote ;
      - une deuxieme annonce, ou un lien de pied de page ("voir toutes nos
        offres", "se desabonner"), l'arrete net.

    Sans ce garde-fou, sur un mail contenant peu de liens on remontait jusqu'au
    <body> et la phrase d'introduction du mail devenait le nom de l'employeur.
    """
    href_reference = lien.get("href", "")

    def contient_autre_lien(noeud: Tag) -> bool:
        for a in noeud.find_all("a", href=True):
            if a is lien or a.get("href") == href_reference:
                continue
            if not a.get_text(strip=True):
                continue  # logo, pixel de suivi, icone : sans importance
            return True
        return False

    courant: Tag | None = lien
    meilleur: Tag | None = lien
    for _ in range(niveaux):
        courant = courant.parent if courant is not None else None
        if not isinstance(courant, Tag):
            break
        if contient_autre_lien(courant):
            break
        meilleur = courant
    return meilleur


# Lignes qui ne sont ni un employeur ni un lieu : montants, badges de plateforme.
# Sans ce filtre, « Entre 50 k € et 55 k € par an » se retrouvait dans le champ
# employeur, observe sur de vraies alertes.
_LIGNE_SALAIRE = re.compile(
    r"(\d[\d\s .,']{2,}\s*(?:k\s*)?(?:€|EUR|CHF|Fr\.)"
    r"|(?:€|EUR|CHF)\s*\d"
    r"|par an|par heure|par mois|pro Jahr|pro Stunde|per year|per hour)",
    re.IGNORECASE,
)
_BADGE_PLATEFORME = re.compile(
    r"^(recrutement actif|actively recruiting|easy apply|candidature simplifiee"
    r"|promu|promoted|sponsorise|sponsored|nouveau|new|il y a \d|\d+ (jours?|heures?|days?|hours?))",
    re.IGNORECASE,
)


def _sans_interet(ligne: str) -> bool:
    # Comparaison sans accents : « Candidature simplifiée » passait au travers.
    from ...config import normaliser

    return bool(_LIGNE_SALAIRE.search(ligne) or _BADGE_PLATEFORME.match(normaliser(ligne).strip()))


# Les indices qui valent pour tout le monde : des pays, le télétravail, les grandes
# villes de France et de Suisse. Ceux d'une instance (sa région, ses villes) sont
# dans `geographie.indices_lieu` de `criteres.yaml`.
_INDICES_LIEU_GENERIQUES = (
    "france", "suisse", "switzerland", "schweiz", "deutschland", "remote",
    "teletravail", "télétravail", "hybrid", "hybride", "home office",
    "basel", "bâle", "bale", "zurich", "zürich", "geneve", "genève", "bern",
    "strasbourg", "paris", "lyon", "lille", "nantes",
    "bordeaux", "toulouse", "marseille", "rennes", "nancy", "metz", "dijon",
    "(", "canton", "kanton", "region", "région",
)


def _indices_lieu_configures() -> list:
    from ...config import charger_criteres

    indices = (charger_criteres().brut.get("geographie") or {}).get("indices_lieu") or []
    return indices if isinstance(indices, list) else []


def separer_employeur_lieu(lignes: list[str], titre: str) -> tuple[str, str]:
    """Devine (employeur, lieu) dans les lignes qui accompagnent un intitule.

    Heuristique assumee : le lieu contient un indice geographique connu, tout
    le reste est l'employeur. En cas de doute on rend une chaine vide plutot
    qu'une valeur inventee - une case vide se voit, une fausse valeur non.
    """
    indices_lieu = _INDICES_LIEU_GENERIQUES + tuple(
        str(i).lower() for i in _indices_lieu_configures()
    )
    employeur, lieu = "", ""

    # PREMIERE PASSE : la ligne composee « Employeur · Ville (Mode) », qui est
    # le format standard des alertes LinkedIn. Elle porte les deux
    # informations ; la traiter comme un simple « lieu » faisait remonter le
    # salaire au rang d'employeur sur la ligne suivante.
    for ligne in lignes:
        if nettoyer(ligne).lower() == nettoyer(titre).lower() or _sans_interet(ligne):
            continue
        morceaux = [m.strip() for m in _SEPARATEURS_FORTS.split(ligne) if m.strip()]
        if len(morceaux) < 2:
            continue
        # Le DERNIER morceau qui ressemble a un lieu, pas le premier : un nom
        # d'entreprise contient souvent un pays (« XY Group (Switzerland) »),
        # ce qui faisait prendre l'employeur pour le lieu.
        correspondants = [
            i for i, m in enumerate(morceaux) if any(ind in m.lower() for ind in indices_lieu)
        ]
        indice = correspondants[-1] if correspondants else None
        if indice:  # un morceau de lieu, precede d'au moins un autre morceau
            employeur = " ".join(morceaux[:indice])
            lieu = " ".join(morceaux[indice:])
            return nettoyer(employeur), nettoyer(lieu)

    # DEUXIEME PASSE : une information par ligne.
    for ligne in lignes:
        if nettoyer(ligne).lower() == nettoyer(titre).lower() or _sans_interet(ligne):
            continue
        bas = ligne.lower()
        if not lieu and any(i in bas for i in indices_lieu):
            lieu = ligne
        elif not employeur and len(ligne) < 90:
            employeur = ligne
        if employeur and lieu:
            break

    # Repli : une seule ligne « Employeur - Lieu » sans indice reconnu avant.
    if employeur and not lieu:
        morceaux = [m for m in _SEPARATEURS.split(employeur) if m.strip()]
        if len(morceaux) >= 2 and any(i in morceaux[-1].lower() for i in indices_lieu):
            lieu = morceaux[-1].strip()
            employeur = " ".join(morceaux[:-1]).strip()
    return nettoyer(employeur), nettoyer(lieu)
