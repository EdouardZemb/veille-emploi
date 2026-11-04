"""Assembler une lettre à partir de SES phrases et des mots de l'annonce.

POURQUOI CE MODULE N'APPELLE AUCUN MODELE. La console ne sait pas ecrire, et
elle n'a pas besoin de savoir : elle a mieux. Le scoring a deja releve, dans
l'annonce, les termes exacts qui l'interessent — les mots de ses familles
et de ses atouts, « environnement international » — avec la phrase qui les
contient. Et le kit contient ses lettres, ecrites et corrigees plusieurs fois.

Assembler les deux donne un texte plus specifique qu'une redaction a froid,
parce qu'un modele ne connait ni ses realisations chiffrees, ni le nom de
son client, ni ce qu'il accepte de dire de lui.

TROIS REGLES, et elles tiennent tout :

  1. **Rien n'est invente.** Chaque phrase vient soit de son gabarit, soit de
     l'annonce. Aucune formulation n'est produite de toutes pieces.
  2. **On ne cite l'annonce que si le scoring l'a relevee.** Pas de recherche
     de mots-cles a l'aveugle : on reutilise ce qui a deja ete prouve.
  3. **Deux exigences au maximum.** Une lettre qui recite l'annonce en entier
     se voit autant qu'une lettre generique.

Le resultat est deterministe : la meme offre donne deux fois le meme texte.
C'est ce qui permet a l'affinement par modele d'etre un choix, et pas une
dependance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .config import charger_criteres, normaliser

# Les contributions qui parlent du POSTE. On ecarte celles qui parlent de lui
# (zone, salaire, contrat) : elles n'ont rien a faire dans un paragraphe qui
# dit « votre annonce demande ceci ».
LIBELLES_IGNORES = ("zone", "salaire", "contrat", "donnees partielles",
                    "teletravail", "lieu", "eliminatoire", "a verifier")

# Au-dela, la lettre recite l'annonce au lieu d'y repondre.
MAX_EXIGENCES = 2

# Quatre termes font une liste, pas une lecture.
MAX_TERMES = 3

# Les termes cites par le scoring arrivent sous la forme : "test automation",
# "appium", "jmeter" - plafonne
_TERMES_CITES = re.compile(r'"([^"]{2,60})"')


@dataclass
class Exigence:
    """Un point de l'annonce auquel la lettre repond, et d'ou il vient."""

    termes: list[str]
    libelle: str
    points: float
    phrase: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"termes": self.termes, "libelle": self.libelle,
                "points": self.points, "phrase": self.phrase}


@dataclass
class Assemblage:
    paragraphe: str = ""
    exigences: list[Exigence] = field(default_factory=list)
    phrase_cv: str = ""
    raison_vide: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "paragraphe": self.paragraphe,
            "exigences": [e.as_dict() for e in self.exigences],
            "phrase_cv": self.phrase_cv,
            "raison_vide": self.raison_vide,
        }


def _frequences(termes: list[str]) -> dict[str, int]:
    """Dans combien d'annonces de SON corpus chaque terme apparait-il ?

    C'est la mesure de specificite, et elle est verifiable : sur quelques
    centaines de descriptions completes, un terme de niche sort dans deux ou
    trois annonces, « test » dans une sur cinq. Citer les rares prouve qu'on
    a lu CETTE annonce ; citer les courants ne prouve rien.

    Si la base est indisponible, on rend un dictionnaire vide et l'appelant
    retombe sur la longueur du terme — un terme compose est plus specifique
    qu'un sigle.
    """
    if not termes:
        return {}
    try:
        from . import db

        with db.connexion() as cx:
            descriptions = [
                normaliser(l["description"] or "")
                for l in cx.execute(
                    "SELECT description FROM offres WHERE donnees_partielles = 0"
                )
            ]
    except Exception:
        return {}
    if not descriptions:
        return {}
    return {
        t: sum(1 for d in descriptions if f" {normaliser(t).strip()} " in d)
        for t in termes
    }


def _dans_le_corps(terme: str, description: str) -> bool:
    """Le terme est-il dans le CORPS de l'annonce, pas seulement son titre ?"""
    return f" {normaliser(terme).strip()} " in normaliser(description)


def exigences_de_loffre(offre: dict[str, Any]) -> list[Exigence]:
    """Ce que le scoring a releve DANS LE CORPS de l'annonce, par poids.

    Un terme present seulement dans l'intitule est ecarte : le citer montre
    qu'on a lu le titre, pas l'annonce. C'est toute la difference entre une
    lettre qui parait personnalisee et une qui l'est.
    """
    description = offre.get("description") or ""
    trouvees: list[Exigence] = []
    for c in offre.get("explication") or []:
        libelle = (c.get("libelle") or "")
        if any(mot in normaliser(libelle) for mot in LIBELLES_IGNORES):
            continue
        if float(c.get("points") or 0) <= 0:
            continue
        detail = c.get("detail") or ""
        termes = [t for t in _TERMES_CITES.findall(detail)
                  if len(t) > 2 and _dans_le_corps(t, description)]
        if not termes:
            continue
        trouvees.append(Exigence(
            termes=termes[:3],
            libelle=libelle,
            points=float(c["points"]),
            phrase=detail,
        ))
    return sorted(trouvees, key=lambda e: -e.points)[:MAX_EXIGENCES]


def termes_a_citer(exigences: list[Exigence]) -> list[str]:
    """Les trois termes les plus SPECIFIQUES, mesures sur son corpus.

    Quatre termes font une liste. Trois suffisent, et on garde les plus rares :
    un terme rare prouve la lecture mieux qu'un terme courant.
    """
    candidats: list[str] = []
    for e in exigences:
        for t in e.termes:
            if t not in candidats:
                candidats.append(t)
    if not candidats:
        return []
    freq = _frequences(candidats)
    # A defaut de mesure, le terme le plus long fait foi : « test automation »
    # est plus specifique que « qa ».
    candidats.sort(key=lambda t: (freq.get(t, 10_000 - len(t)), -len(t)))
    return candidats[:MAX_TERMES]


def _casse_dorigine(terme: str, description: str) -> str:
    """Le terme tel que l'ANNONCE l'ecrit, ou le terme tel quel.

    Recherche insensible a la casse dans le texte d'origine, et rend la
    tranche trouvee — jamais une reconstruction. Si le terme n'y figure pas
    sous cette forme, on ne devine pas : on le rend inchange.
    """
    if not description:
        return terme
    # LA RECHERCHE DOIT TOLERER LES ACCENTS, parce que le terme vient du
    # scoring : il est ecrit SANS accents, puisqu'il sert a comparer du texte
    # normalise. Le chercher tel quel dans l'annonce echouait des qu'elle
    # ecrivait « gestion d'entrepôt » correctement — et la lettre citait
    # alors « gestion d'entrepot », desaccente, sous les yeux du
    # recruteur. C'est bien une normalisation qui atteignait la charge utile,
    # par un detour : le terme compare devenait le terme ecrit.
    from .enrichissement import _motif_regex

    regex = _motif_regex(terme)
    trouve = regex.search(description) if regex else None
    return trouve.group(0) if trouve else terme


def _enumerer(termes: list[str], langue: str) -> str:
    """« a, b et c » — ou « a, b and c » en anglais."""
    liaison = " and " if langue == "en" else " et "
    if len(termes) == 1:
        return termes[0]
    return ", ".join(termes[:-1]) + liaison + termes[-1]


# Les charnieres. Ce sont les SEULES phrases que ce module ecrit, et elles ne
# disent rien de lui : elles relient son texte a l'annonce. Volontairement
# sobres — une charniere qui se remarque est une charniere de trop.
# LA CHARNIERE EST LA SEULE PHRASE QUE CE MODULE ECRIT. Elle doit donc etre
# vraie pour TOUTE offre, sans exception — on ne peut pas la relire a chaque
# fois.
#
# L'ancienne version disait : « C'est précisément le terrain sur lequel je
# travaille aujourd'hui, et ce que décrit le paragraphe ci-dessus. » Deux
# fautes, lues sur un dossier reel le 02/10/2026 :
#
#   1. Elle AFFIRME une experience. Sur une offre reelle, les termes cites
#      etaient trois sigles de l'annonce, et la lettre avouait trois
#      paragraphes plus loin ne pas avoir ce vecu. Le meme document disait
#      qu'il y travaille tous les jours et qu'il n'y a jamais touche.
#   2. Elle COMMENTE le document au lieu de s'y enchainer — « ce que décrit le
#      paragraphe ci-dessus ». Dans la lettre francaise, le paragraphe
#      ci-dessus etait « Madame, Monsieur, ».
#
# La version actuelle ne dit qu'une chose, et cette chose est verifiable par
# construction : ces termes sont dans l'annonce, puisque le scoring les y a
# releves. Elle ne pretend rien sur lui. C'est au texte de SA lettre, juste
# apres, de dire ce qu'il sait faire.
CHARNIERES = {
    "fr": "Votre annonce cite {termes}.",
    "en": "Your advertisement names {termes}.",
}


def assembler(offre: dict[str, Any], langue: str = "en") -> Assemblage:
    """Le paragraphe qui relie SON texte aux mots de l'annonce."""
    exigences = exigences_de_loffre(offre)
    a = Assemblage(exigences=exigences)

    if not exigences:
        # Deux causes tres differentes, et il doit savoir laquelle : soit
        # l'annonce n'a rien a citer, soit tout ce qu'elle cite vient de son
        # intitule — auquel cas c'est le corps qui manque.
        cites = any(_TERMES_CITES.findall(c.get("detail") or "")
                    for c in (offre.get("explication") or []))
        a.raison_vide = (
            "Les termes relevés par le scoring viennent de l'intitulé, pas du "
            "corps de l'annonce. Colle le texte complet : citer une exigence "
            "enfouie dans la description prouve la lecture, citer le titre non."
            if cites else
            "Le scoring n'a relevé aucun terme cité dans cette annonce — "
            "elle n'a probablement qu'un extrait. Colle le texte complet : "
            "le paragraphe se construira tout seul."
        )
        return a

    termes = termes_a_citer(exigences)
    if not termes:
        a.raison_vide = (
            "Les termes relevés par le scoring viennent de l'intitulé, pas du "
            "corps de l'annonce. Colle le texte complet : citer une exigence "
            "enfouie dans la description prouve la lecture, citer le titre non."
        )
        return a
    # On cite les termes AVEC LA CASSE DE L'ANNONCE. Le scoring travaille sur
    # du texte normalise : « sql » et « rgaa » sortaient en minuscules au
    # milieu d'une phrase, ce qui se lit comme une faute de frappe la ou
    # l'annonce ecrit « SQL » et « RGAA ».
    description = offre.get("description") or ""
    termes = [_casse_dorigine(x, description) for x in termes]
    a.paragraphe = CHARNIERES.get(langue, CHARNIERES["en"]).format(
        termes=_enumerer(termes, langue)
    )
    a.phrase_cv = phrase_cv(offre, langue)
    return a


# --------------------------------------------------------------------------
# La phrase du CV — proposée, jamais appliquée
# --------------------------------------------------------------------------

# `[[tailor per application]]` clot le paragraphe « Looking for » d'un CV.
# C'est UNE PHRASE, pas un document : on la propose, il la valide.
# Rien au-dela — un CV qui se reecrit tout seul est un CV qu'il ne peut plus
# defendre en entretien.
# Les formules vivent dans `criteres.yaml` : `familles.<f>.formule_cv` et
# `atouts.<a>.formule`, chacune sous la forme `{en, fr}`.


def _formule(entree: Any, langue: str) -> str:
    """La formule d'une famille ou d'un atout dans cette langue, ou ''."""
    if not isinstance(entree, dict):
        return ""
    return str(entree.get(langue) or "")


def phrase_cv(offre: dict[str, Any], langue: str = "en") -> str:
    """La phrase proposee pour `[[tailor per application]]`.

    Construite a partir de la famille et des atouts DEJA attribues par le
    scoring : elle ne dit rien que l'offre et son profil ne disent deja.
    """
    famille = offre.get("famille") or ""
    criteres = charger_criteres()
    base = _formule((criteres.familles.get(famille) or {}).get("formule_cv"), langue)
    if not base:
        return ""

    atouts = offre.get("atouts") or []
    if isinstance(atouts, str):
        atouts = [a for a in atouts.split(",") if a]
    complement = next(
        (f for f in (_formule((criteres.atouts.get(a) or {}).get("formule"), langue)
                     for a in atouts) if f),
        "",
    )

    if langue == "fr":
        phrase = f"avec un intérêt particulier pour {base}"
        if complement:
            phrase += f" et {complement}"
    else:
        phrase = f"with a particular interest in {base}"
        if complement:
            phrase += f" and {complement}"
    return phrase


def familles_couvertes() -> set[str]:
    """Pour le test : toute famille du referentiel a-t-elle une formule ?"""
    return {nom for nom, famille in charger_criteres().familles.items()
            if _formule((famille or {}).get("formule_cv"), "fr")
            and _formule((famille or {}).get("formule_cv"), "en")}
