"""Lire le texte complet d'une annonce, et rescorer avec.

DEUX VOIES, ET LA SECONDE EST LA PLUS IMPORTANTE.

1. `recuperer()` — recuperation automatique, sur les seules sources qui
   l'autorisent. Declenchee par une action humaine, jamais par le minuteur.

2. `appliquer_texte()` — le texte colle a la main. Il ouvre l'annonce dans SON
   navigateur, ou il est connecte et voit tout, selectionne, colle. Couverture
   totale, LinkedIn compris, et zero requete automatisee. C'est lui qui lit, le
   programme ne fait que scorer.

POURQUOI LA SECONDE VOIE EXISTE : le robots.txt de LinkedIn declare
`User-agent: * / Disallow: /` — tout le site. Or la plupart des offres
au-dessus de son seuil en viennent. Une recuperation automatique y serait interdite, et de
toute facon vaine puisque LinkedIn masque le detail aux visiteurs non connectes.

LIMITES A NE PAS LAISSER DERIVER — voir docs/LIMITES.md :
  - declenchement humain uniquement, jamais depuis veille-collecte.timer ;
  - une page a la fois, delai minimal entre deux, plafond quotidien ;
  - liste blanche ET robots.txt, les deux, pas l'un ou l'autre ;
  - jamais de contournement : pas de navigateur sans tete, pas de cookie de
    session, pas d'en-tete falsifie pour passer pour un humain.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import db
from .config import normaliser, charger_sources

log = logging.getLogger(__name__)

AGENT = "veille-emploi/1.0 (recherche d'emploi personnelle; une page a la demande)"

# Cache memoire des robots.txt, pour ne pas les redemander a chaque clic.
_ROBOTS: dict[str, tuple[float, urllib.robotparser.RobotFileParser | None]] = {}
DUREE_CACHE_ROBOTS = 24 * 3600


@dataclass
class Politique:
    """Ce qu'on a le droit de faire sur un domaine, et pourquoi."""

    autorise: bool
    domaine: str
    raison: str
    conseil: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "autorise": self.autorise,
            "domaine": self.domaine,
            "raison": self.raison,
            "conseil": self.conseil,
        }


@dataclass
class Preuve:
    """Un critère détecté, avec la phrase de l'annonce qui l'a déclenché."""

    libelle: str
    points: float
    phrase: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"libelle": self.libelle, "points": self.points, "phrase": self.phrase}


@dataclass
class Rapport:
    """Ce que l'enrichissement a change, pour l'afficher."""

    ok: bool
    message: str
    origine: str = ""
    caracteres: int = 0
    score_avant: float = 0
    score_apres: float = 0
    # Ce qui pénalise ou disqualifie, et ce qui valorise : les deux comptent.
    revelations_defavorables: list[Preuve] = field(default_factory=list)
    revelations_favorables: list[Preuve] = field(default_factory=list)
    alerte_eliminatoire: str = ""
    salaire_trouve: str = ""
    # Rubriques « Offres similaires » retirees du collage, et leur taille.
    annexes_repere: str = ""
    annexes_retires: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "origine": self.origine,
            "caracteres": self.caracteres,
            "score_avant": self.score_avant,
            "score_apres": self.score_apres,
            "ecart": round(self.score_apres - self.score_avant, 1),
            "revelations_defavorables": [p.as_dict() for p in self.revelations_defavorables],
            "revelations_favorables": [p.as_dict() for p in self.revelations_favorables],
            "alerte_eliminatoire": self.alerte_eliminatoire,
            "salaire_trouve": self.salaire_trouve,
            "annexes_repere": self.annexes_repere,
            "annexes_retires": self.annexes_retires,
        }


# Le detail d'une contribution ressemble a : « "astreinte" reperee dans le texte ».
_MOTIF_CITE = re.compile(r'"([^"]{2,60})"')


# Correspondances accentuees : l'annonce ecrit « Astreinte », le motif dit
# "astreinte". On cherche dans le texte D'ORIGINE pour pouvoir citer la phrase
# telle qu'elle est ecrite — une recherche dans le texte normalise donnerait une
# position qu'on ne sait pas reporter (la normalisation coupe « l'annonce » en
# deux mots et decale tout ce qui suit).
_VARIANTES = {
    "a": "aàáâãäåāăą", "c": "cçćĉċč", "e": "eèéêëēĕėęě",
    "i": "iìíîïĩīĭįı", "n": "nñńņňŉ", "o": "oòóôõöøōŏő",
    "u": "uùúûüũūŭůűų", "y": "yýÿŷ", "s": "sśŝşš", "z": "zźżž",
}
_FIN_DE_PHRASE = ".!?" + chr(10) + chr(13) + "•·"


def _motif_regex(motif: str) -> re.Pattern | None:
    """Le motif, tolerant aux accents, a la casse et a la ponctuation interne.

    « week-end », « week end » et « Week-End » doivent tous etre trouves.
    """
    from .config import normaliser

    mots = normaliser(motif).split()
    if not mots:
        return None
    morceaux = []
    for mot in mots:
        morceaux.append("".join(
            f"[{v}{v.upper()}]" if (v := _VARIANTES.get(c)) else re.escape(c)
            for c in mot
        ))
    motif_re = r"[^A-Za-z0-9]+".join(morceaux)
    return re.compile(rf"(?<![A-Za-z0-9]){motif_re}(?![A-Za-z0-9])", re.IGNORECASE)


def phrase_autour(texte: str, motif: str, marge: int = 130) -> str:
    """LA phrase de l'annonce qui contient `motif` — pas une fenetre autour.

    C'est ce qui donne confiance : lui dire « astreinte detectee » ne vaut rien
    s'il ne peut pas verifier. Lui montrer « Le poste implique une astreinte une
    semaine sur quatre » lui evite un entretien inutile.

    La citation doit etre LA phrase declenchante. Une fenetre de N caracteres
    commence au milieu de la phrase precedente et fait citer le mauvais passage
    — ce qui est pire que de ne rien citer, parce qu'il croira avoir verifie.
    """
    if not motif or not texte:
        return ""
    regex = _motif_regex(motif)
    if regex is None:
        return ""
    trouve = regex.search(texte)
    if not trouve:
        return ""

    debut_motif, fin_motif = trouve.span()
    debut = 0
    for i in range(debut_motif - 1, -1, -1):
        if texte[i] in _FIN_DE_PHRASE:
            debut = i + 1
            break
    fin = len(texte)
    for i in range(fin_motif, len(texte)):
        if texte[i] in _FIN_DE_PHRASE:
            fin = i + 1
            break

    # Une « phrase » sans ponctuation — une puce, un titre, un pave colle sans
    # points — peut faire des milliers de caracteres. On recentre sur le motif.
    if fin - debut > 2 * marge:
        debut = max(debut, debut_motif - marge)
        fin = min(fin, fin_motif + marge)

    extrait = re.sub(r"\s+", " ", texte[debut:fin]).strip()
    if not extrait:
        return ""
    return ("… " if debut > 0 else "") + extrait + (" …" if fin < len(texte) else "")


def _config() -> dict[str, Any]:
    return charger_sources().get("enrichissement") or {}


def _domaine(url: str) -> str:
    h = (urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


# --------------------------------------------------------------------------
# Politique : liste blanche ET robots.txt
# --------------------------------------------------------------------------


def _robots(domaine: str) -> urllib.robotparser.RobotFileParser | None:
    """robots.txt du domaine, mis en cache 24 h. None si illisible."""
    maintenant = time.time()
    if domaine in _ROBOTS and maintenant - _ROBOTS[domaine][0] < DUREE_CACHE_ROBOTS:
        return _ROBOTS[domaine][1]

    analyseur: urllib.robotparser.RobotFileParser | None = None
    try:
        rep = httpx.get(
            f"https://{domaine}/robots.txt", timeout=15,
            headers={"User-Agent": AGENT}, follow_redirects=True,
        )
        if rep.status_code == 200:
            analyseur = urllib.robotparser.RobotFileParser()
            analyseur.parse(rep.text.splitlines())
    except Exception as exc:
        log.warning("robots.txt de %s illisible : %s", domaine, exc)
    _ROBOTS[domaine] = (maintenant, analyseur)
    return analyseur


def politique(url: str) -> Politique:
    """Peut-on aller chercher cette page ? Liste blanche ET robots.txt.

    Les deux, pas l'un ou l'autre : la liste blanche dit ce qu'on a etudie, le
    robots.txt dit ce que le site declare aujourd'hui. Une politique peut
    changer apres notre etude.
    """
    d = _domaine(url)
    if not d:
        return Politique(False, "", "lien absent ou illisible")

    cfg = _config()
    if not cfg.get("actif", True):
        return Politique(False, d, "enrichissement desactive dans sources.yaml")

    for interdit in cfg.get("domaines_interdits", []) or []:
        if d == interdit or d.endswith("." + interdit):
            return Politique(
                False, d,
                f"{interdit} interdit la lecture automatisee",
                "Ouvre l'annonce dans ton navigateur, puis colle le texte ci-dessous.",
            )

    autorises = cfg.get("domaines_autorises", []) or []
    if autorises and not any(d == a or d.endswith("." + a) for a in autorises):
        return Politique(
            False, d,
            "domaine absent de la liste blanche",
            "Ajoute-le dans sources.yaml, bloc enrichissement, apres avoir verifie "
            "son robots.txt — ou colle le texte a la main.",
        )

    analyseur = _robots(d)
    if analyseur is None:
        return Politique(
            False, d, "robots.txt illisible : dans le doute, on s'abstient",
            "Colle le texte a la main.",
        )
    if not analyseur.can_fetch(AGENT, url):
        return Politique(
            False, d, f"le robots.txt de {d} interdit cette page",
            "Ouvre l'annonce dans ton navigateur, puis colle le texte ci-dessous.",
        )
    return Politique(True, d, f"autorise par le robots.txt de {d}")


# --------------------------------------------------------------------------
# Cadence : un delai entre deux requetes, un plafond par jour
# --------------------------------------------------------------------------

CLE_CADENCE = "enrichissement"


def _cadence() -> dict[str, Any]:
    brut = db.lire_marqueur(CLE_CADENCE)
    try:
        etat = json.loads(brut) if brut else {}
    except json.JSONDecodeError:
        etat = {}
    if etat.get("jour") != date.today().isoformat():
        etat = {"jour": date.today().isoformat(), "compte": 0, "dernier": 0.0}
    return etat


def _enregistrer_cadence(etat: dict[str, Any]) -> None:
    db.marquer_etat_collecte(CLE_CADENCE, marqueur=json.dumps(etat))


def verifier_cadence() -> tuple[bool, str]:
    """(possible, message). Ne consomme rien : c'est une consultation."""
    cfg = _config()
    etat = _cadence()
    plafond = int(cfg.get("plafond_quotidien", 30))
    if etat["compte"] >= plafond:
        return False, f"plafond quotidien atteint ({plafond} pages). Colle le texte a la main."

    delai = float(cfg.get("delai_entre_requetes_s", 20))
    reste = delai - (time.time() - float(etat.get("dernier", 0)))
    if reste > 0:
        return False, f"attends {reste:.0f} s — une page a la fois, {delai:.0f} s entre deux."
    return True, ""


# --------------------------------------------------------------------------
# Nettoyage du texte
# --------------------------------------------------------------------------

LONGUEUR_MAX = 20000
# En dessous, c'est un collage accidentel plutot qu'une annonce. Volontairement
# bas : mieux vaut accepter une annonce courte que refuser un geste honnete.
LONGUEUR_MIN = 150


# Reperes de FIN D'ANNONCE.
#
# Le geste reel n'est pas « selectionner la description » : c'est Ctrl+A sur
# l'onglet, puis coller. Ce qui arrive contient donc la colonne « Offres
# similaires », les « Personnes egalement consultees » et le pied de page —
# c'est-a-dire D'AUTRES ANNONCES.
#
# Le risque est asymetrique, et c'est ce qui le rend grave :
#   - une astreinte mentionnee dans l'offre VOISINE disqualifierait la bonne
#     offre, en citant une phrase qui ne la concerne pas ;
#   - les intitules voisins gonfleraient le score avec des familles et des
#     atouts absents du poste.
#
# On coupe donc au premier repere, et on lui DIT ce qu'on a coupe : une
# troncature silencieuse serait pire que le bruit qu'elle enleve.
MARQUEURS_FIN = [
    # LinkedIn
    "offres similaires", "emplois similaires", "similar jobs",
    "personnes egalement consultees", "people also viewed",
    "d autres personnes ont egalement consulte",
    "offres recommandees", "recommande pour vous", "recommended for you",
    "plus d offres chez", "plus d offres de", "more jobs at",
    "explorer des sujets collaboratifs", "explore collaborative articles",
    "voir toutes les offres", "voir plus d offres",
    # jobs.ch et marche germanophone
    "ahnliche jobs", "ahnliche stellen", "weitere jobs", "weitere stellen",
    "das konnte sie auch interessieren",
    # Agregateurs francais
    "offres d emploi similaires", "postes similaires",
    "ces offres pourraient vous interesser",
    "les internautes ont aussi consulte",
]

# En deca de ce nombre de caracteres, un repere est ignore : une annonce qui
# dit « offres similaires » dans son premier paragraphe existe, et couper la
# ne laisserait rien.
MINIMUM_AVANT_COUPE = 400


def couper_sections_annexes(texte: str) -> tuple[str, str, int]:
    """Coupe au debut des rubriques qui parlent d'AUTRES offres.

    Rend (texte, repere_trouve, caracteres_retires).
    """
    if not texte:
        return "", "", 0
    from .config import normaliser

    meilleur, repere = len(texte), ""
    position = 0
    for ligne in texte.split("\n"):
        # Un repere ne compte que s'il tient une ligne a lui seul ou la
        # commence : « nous publions des offres similaires » au milieu d'un
        # paragraphe n'est pas une fin d'annonce.
        aplatie = normaliser(ligne).strip()
        for marqueur in MARQUEURS_FIN:
            m = normaliser(marqueur).strip()
            if aplatie == m or aplatie.startswith(m + " "):
                if MINIMUM_AVANT_COUPE <= position < meilleur:
                    meilleur, repere = position, ligne.strip()[:60]
                break
        position += len(ligne) + 1
    if not repere:
        return texte, "", 0
    return texte[:meilleur].rstrip(), repere, len(texte) - meilleur


def nettoyer_texte_detaille(brut: str) -> tuple[str, str, int]:
    """Rend un texte lisible a partir d'un collage brut ou d'une page.

    Accepte le HTML comme le texte : il colle depuis un site, avec la mise en
    forme, et ne doit rien avoir a nettoyer lui-meme.
    """
    if not brut:
        return ""
    texte = brut
    if "<" in texte and ">" in texte:
        try:
            from bs4 import BeautifulSoup

            soupe = BeautifulSoup(texte, "lxml")
            for balise in soupe(["script", "style", "nav", "footer", "header", "noscript"]):
                balise.decompose()
            texte = soupe.get_text("\n")
        except Exception:
            texte = re.sub(r"<[^>]+>", " ", texte)
    texte = re.sub(r"&(nbsp|amp|lt|gt|quot|#39|eacute|egrave|agrave);", " ", texte)
    # On garde les sauts de ligne : ils portent la structure de l'annonce.
    texte = re.sub(r"[ \t ]+", " ", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    texte, _repere, _retires = couper_sections_annexes(texte.strip())
    return texte[:LONGUEUR_MAX], _repere, _retires


def nettoyer_texte(brut: str) -> str:
    """Le texte seul. `nettoyer_texte_detaille` dit aussi ce qui a ete coupe."""
    return nettoyer_texte_detaille(brut)[0]


# --------------------------------------------------------------------------
# Récupération automatique
# --------------------------------------------------------------------------


def recuperer(url: str) -> tuple[str, str]:
    """(texte, message). Texte vide si la page ne donne rien d'exploitable."""
    possible, message = verifier_cadence()
    if not possible:
        return "", message

    etat = _cadence()
    etat["dernier"] = time.time()
    etat["compte"] = int(etat.get("compte", 0)) + 1
    _enregistrer_cadence(etat)

    try:
        with httpx.Client(
            timeout=25, follow_redirects=True,
            headers={"User-Agent": AGENT, "Accept-Language": "fr,en;q=0.8"},
        ) as client:
            rep = client.get(url)
    except Exception as exc:
        return "", f"page injoignable : {type(exc).__name__}"

    if rep.status_code == 410:
        return "", "l'annonce a ete retiree par le site (HTTP 410)"
    if rep.status_code == 404:
        return "", "l'annonce n'existe plus (HTTP 404)"
    if rep.status_code != 200:
        return "", f"le site a repondu HTTP {rep.status_code}"

    texte = nettoyer_texte(rep.text)
    if len(texte) < 400:
        # Beaucoup d'annonces sont rendues en JavaScript : la page arrive vide.
        # On le DIT, plutot que de laisser croire que l'annonce est pauvre.
        return "", (
            f"la page n'a rendu que {len(texte)} caracteres — probablement "
            "construite en JavaScript. Colle le texte a la main."
        )
    return texte, ""


# --------------------------------------------------------------------------
# Application : rescorage et compte rendu
# --------------------------------------------------------------------------

# Les libelles qui signalent un critere que le texte complet fait apparaitre.
# Libelles surveilles, compares APRES normalisation. Ils servent de cle de
# comparaison, et les libelles affiches portent desormais leurs accents :
# « ELIMINATOIRE » ne retrouvait plus « ÉLIMINATOIRE », et le signalement des
# revelations defavorables s'etait tu sans bruit. On normalise pour comparer,
# jamais pour ecrire.
_CRITERES_SURVEILLES = ("eliminatoire", "allemand", "salaire", "interim",
                        "mise en attente")


def appliquer_texte(offre_id: int, texte: str, origine: str) -> Rapport:
    """Enregistre le texte, rescore, et rend ce qui a change."""
    from .config import charger_criteres
    from .models import Offre
    from .scoring import scorer

    avant = db.lire_offre(offre_id)
    if not avant:
        return Rapport(False, "offre inconnue")

    propre, repere_annexes, retires_annexes = nettoyer_texte_detaille(texte)
    if len(propre) < LONGUEUR_MIN:
        return Rapport(
            False,
            f"Seulement {len(propre)} caracteres apres nettoyage — on dirait un "
            f"fragment. Selectionne toute l'annonce, du titre jusqu'au bas de "
            f"la description.",
        )

    from . import reglages

    seuil = reglages.lire_seuil()
    etait_au_dessus = avant["score"] >= seuil
    libelles_avant = {c["libelle"] for c in avant["explication"]}

    offre = Offre(
        titre=avant["titre"] or "",
        employeur=avant["employeur"] or "",
        lieu=avant["lieu"] or "",
        description=propre,
        url=avant["url"] or "",
        source=avant["source"] or "",
        salaire_min=avant["salaire_min"],
        salaire_max=avant["salaire_max"],
        salaire_devise=avant["salaire_devise"],
        type_contrat=avant["type_contrat"] or "",
        donnees_partielles=False,      # on a le texte : ce n'est plus un extrait
    )
    # Le salaire peut apparaitre dans le corps alors qu'il manquait avant.
    if offre.salaire_min is None and offre.salaire_max is None:
        from .collectors.base import extraire_salaire

        devise = "CHF" if (avant["salaire_devise"] == "CHF") else None
        offre.salaire_min, offre.salaire_max, offre.salaire_devise = extraire_salaire(
            propre, devise_par_defaut=devise
        )
    scorer(offre)

    db.enregistrer_texte_complet(offre_id, propre, offre, origine)

    # Ce que le texte complet revele, dans les deux sens. La montee compte
    # autant que la chute : une offre peut cacher du WMS, de la recette de
    # donnees ou de l'accessibilite que l'extrait ne laissait pas voir.
    defavorables: list[Preuve] = []
    favorables: list[Preuve] = []
    for c in offre.explication:
        if c.libelle in libelles_avant:
            continue
        cite = _MOTIF_CITE.search(c.detail or "")
        phrase = phrase_autour(propre, cite.group(1)) if cite else ""
        preuve = Preuve(c.libelle, round(c.points, 1), phrase)
        if "eliminatoire" in normaliser(c.libelle) or c.points < 0:
            defavorables.append(preuve)
        elif c.points > 0:
            favorables.append(preuve)

    alerte = ""
    if etait_au_dessus and offre.rejete_auto:
        alerte = (
            f"Cette offre etait au-dessus de ton seuil. Le texte complet revele : "
            f"{offre.motif_rejet_auto}"
        )
    elif etait_au_dessus and offre.differee:
        alerte = f"Cette offre etait au-dessus de ton seuil. {offre.motif_differe}"

    salaire = offre.salaire_affiche if not (avant["salaire_min"] or avant["salaire_max"]) else ""

    db.journaliser(
        offre_id, "texte_complet",
        f"{origine}, {len(propre)} caracteres, score {avant['score']:g} -> {offre.score:g}"
        + (f" | {alerte}" if alerte else ""),
    )

    return Rapport(
        ok=True,
        message=f"Texte enregistre ({len(propre)} caracteres) et offre rescoree.",
        origine=origine,
        caracteres=len(propre),
        score_avant=avant["score"],
        score_apres=offre.score,
        revelations_defavorables=defavorables,
        revelations_favorables=favorables,
        alerte_eliminatoire=alerte,
        salaire_trouve=salaire,
        annexes_repere=repere_annexes,
        annexes_retires=retires_annexes,
    )
