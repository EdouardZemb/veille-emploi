"""Preparer l'entretien d'une offre precise, a partir de SES reponses.

CE MODULE N'ECRIT AUCUNE REPONSE. Il n'en a pas besoin : le fichier `17` du
kit contient deja les reponses, ecrites et corrigees plusieurs fois, avec les
pieges nommes (le chiffre a ne jamais dire, le temps a employer pour ce qui
n'a pas encore eu lieu). Un modele qui les reecrirait les abimerait.

Ce que le module fait, et c'est tout : il LIT le fichier `17`, et il choisit
les sections qui concernent CETTE annonce. Rien de plus. Les declencheurs
generiques, poses a tout candidat, sont dans le code ; ceux qui disent un fait
de son parcours sont dans sa configuration (`entretien.declencheurs` de
`criteres.yaml`), comme les intitules a risque (`entretien.intitules_a_risque`).

LA REGLE QUI TIENT LE MODULE : chaque point retenu porte son ancrage, et le
dit a l'ecran.

  - ancrage « annonce » : une phrase LITTERALE de l'annonce. Verifiee comme
    telle — `verifier_ancrages()` refuse une citation qui n'est pas un extrait
    exact du texte de l'offre.
  - ancrage « dossier » : une ligne LITTERALE du fichier `17`, ou un fait
    verifiable de l'offre enregistree (le lieu).

Pourquoi cette severite sur un document qui ne part chez personne : une
question inventee lui ferait preparer la mauvaise chose. Il arriverait arme
contre une objection qu'on ne lui fera pas, et desarme devant celle qu'on lui
fera. Le cout n'est pas la gene, c'est l'entretien.

Si Edouard renomme un titre de section dans son fichier `17`, le declencheur
ne trouve plus rien. On ne le tait pas : la section manquante est SIGNALEE.
Un briefing silencieusement incomplet serait pire qu'une erreur visible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import CHEMIN_KIT, charger_criteres, normaliser, problemes_de_declencheur

# Le fichier du kit qui porte ses reponses. Reconnu par son numero de tete,
# pas par son nom complet : il a deja change de libelle une fois.
MOTIF_FICHIER = re.compile(r"^17[-_. ]", re.IGNORECASE)

# Au-dela, ce n'est plus une preparation, c'est une relecture du kit entier.
MAX_POINTS = 9

_TITRE = re.compile(r"^(#{1,3})\s+(.*)$")


@dataclass
class Section:
    """Une section du fichier 17, telle qu'il l'a ecrite."""

    titre: str
    niveau: int
    corps: str

    @property
    def premiere_ligne(self) -> str:
        """La premiere ligne non vide du corps — sert d'ancrage « dossier »."""
        for ligne in self.corps.splitlines():
            net = ligne.strip().lstrip("> ").strip()
            # Les cloisons de tableau, les filets et les blocs de code ne
            # sont pas des phrases : « ``` » etait sorti comme ancrage.
            if net and not net.startswith(("|", "---", "```", "![", "<!--")):
                return net
        return self.titre


@dataclass
class Point:
    """Une question probable, et d'ou elle sort."""

    question: str
    categorie: str          # "attaque" | "appui" | "rituel"
    ancrage: str            # "annonce" | "dossier"
    citation: str           # extrait LITTERAL de la source
    pourquoi: str
    section: str            # le titre de section du fichier 17
    reponse: str            # son texte, copie tel quel

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question, "categorie": self.categorie,
            "ancrage": self.ancrage, "citation": self.citation,
            "pourquoi": self.pourquoi, "section": self.section,
            "reponse": self.reponse,
        }


@dataclass
class Preparation:
    points: list[Point] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    sections_absentes: list[str] = field(default_factory=list)
    kit_disponible: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "points": [p.as_dict() for p in self.points],
            "avertissements": self.avertissements,
            "sections_absentes": self.sections_absentes,
            "kit_disponible": self.kit_disponible,
            "attaques": sum(1 for p in self.points if p.categorie == "attaque"),
        }


# --------------------------------------------------------------------------
# Les declencheurs
#
# `motifs` vide = le point sort toujours, et s'ancre alors sur une ligne de
# son dossier. Sinon il faut que l'annonce porte l'un des motifs, et c'est la
# PHRASE DE L'ANNONCE qui devient l'ancrage.
#
# DU PLUS SPECIFIQUE AU PLUS GENERAL, dans une liste de motifs : c'est le
# premier motif present qui choisit la phrase citee. Un mot general en tete
# ancre le point sur une phrase vraie mais creuse (la presentation de
# l'employeur, son paragraphe de marketing) au lieu de la ligne qui exige.
#
# DEUX SOURCES. Les declencheurs generiques, poses a tout candidat, sont
# ci-dessous. Ceux qui disent un fait de son parcours (une lacune, une langue,
# sa situation, son meilleur sujet) vivent dans sa configuration :
# `entretien.declencheurs` de `criteres.yaml`, une liste de tables de la forme
# de `Declencheur`. Ils passent devant les generiques, et une cle qu'ils
# redeclarent prend la place du generique.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Declencheur:
    cle_section: str        # fragment du titre, normalise, qui identifie la section
    categorie: str          # "attaque" | "appui" | "rituel"
    pourquoi: str
    motifs: tuple[str, ...] = ()
    pays: str = ""          # "ch" pour restreindre a la Suisse


# La question que declenche un dossier technique joint a la candidature.
CLE_CODE = "avez vous ecrit ce code"

DECLENCHEURS_GENERIQUES: tuple[Declencheur, ...] = (
    Declencheur(
        CLE_CODE,
        "attaque",
        "son dossier technique part avec la candidature",
    ),
    Declencheur(
        "quel est votre preavis",
        "attaque",
        "l'annonce parle de la date d'entree",
        ("asap", "immediately", "immediate", "start date", "disponibilite",
         "des que possible", "eintrittsdatum", "ab sofort",
         "entree en fonction"),
    ),
    Declencheur(
        "pourquoi vous partez",
        "attaque",
        "posee dans tous les entretiens, sans exception",
    ),
    Declencheur(
        "le salaire la question qui vaut",
        "attaque",
        "posee dans tous les entretiens, et c'est la plus chere",
    ),
    Declencheur(
        "tes questions a eux",
        "rituel",
        "fin d'entretien : ne jamais arriver sans questions",
    ),
    Declencheur(
        "a faire avant chaque entretien",
        "rituel",
        "la liste de la veille",
    ),
)


def _entretien_configure() -> tuple[dict[str, Any], int]:
    """(la table `entretien` de la configuration, nombre d'elements ecartes)."""
    brut = charger_criteres().brut
    if "entretien" not in brut:
        return {}, 0
    if not isinstance(brut["entretien"], dict):
        return {}, 1
    return brut["entretien"], 0


def _declencheurs_et_ecartes(entretien: dict[str, Any], ecartes: int
                             ) -> tuple[tuple[Declencheur, ...], int]:
    """(declencheurs, nombre d'entrees mal formees ecartees de la configuration).

    `entretien` et `ecartes` : ce que rend `_entretien_configure()`, lu UNE fois
    par l'appelant. Les declencheurs et les intitules a risque viennent ainsi
    de la meme table, meme si le fichier change entre deux lectures.

    Une entree mal formee est ECARTEE, et le compte remonte a l'ecran : sans cle
    de section, elle trouverait la premiere section venue. `veille config
    verifier` la nomme, par le meme controle (`config.problemes_de_declencheur`).
    """
    brut = entretien.get("declencheurs", [])
    if not isinstance(brut, list):
        brut, ecartes = [], ecartes + 1
    propres: list[Declencheur] = []
    for rang, entree in enumerate(brut):
        if problemes_de_declencheur(entree, f"entretien.declencheurs[{rang}]"):
            ecartes += 1
            continue
        propres.append(Declencheur(
            cle_section=entree["cle_section"], categorie=entree["categorie"],
            pourquoi=entree.get("pourquoi", ""), motifs=tuple(entree.get("motifs") or ()),
            pays=entree.get("pays") or ""))
    redeclarees = {normaliser(d.cle_section).strip() for d in propres}
    generiques = tuple(d for d in DECLENCHEURS_GENERIQUES
                       if normaliser(d.cle_section).strip() not in redeclarees)
    return tuple(propres) + generiques, ecartes


def declencheurs() -> tuple[Declencheur, ...]:
    """Ceux de la configuration d'abord, puis les generiques qu'elle ne redeclare pas."""
    return _declencheurs_et_ecartes(*_entretien_configure())[0]


def _intitules_a_risque(entretien: dict[str, Any]) -> tuple[tuple[str, ...], str, int]:
    """(intitules, avertissement, nombre d'elements ecartes).

    Les intitules pour lesquels son kit dit que ce n'est pas le moment :
    `entretien.intitules_a_risque` de la configuration, `{motifs, avertissement}`.
    Absents : aucun avertissement. Mal formes : ecartes, et comptes a l'ecran.
    Une table `entretien` qui n'en est pas une est deja comptee par
    `_entretien_configure()` : elle arrive ici vide.
    """
    if "intitules_a_risque" not in entretien:
        return (), "", 0
    risque = entretien["intitules_a_risque"]
    motifs = risque.get("motifs") if isinstance(risque, dict) else None
    avertissement = risque.get("avertissement") if isinstance(risque, dict) else None
    if (not isinstance(motifs, list) or not all(isinstance(m, str) for m in motifs)
            or not isinstance(avertissement, str) or not avertissement.strip()):
        return (), "", 1
    return tuple(motifs), avertissement, 0


# --------------------------------------------------------------------------
# Lecture du fichier 17
# --------------------------------------------------------------------------


def fichier_kit() -> Path | None:
    """Le fichier `17` du kit, s'il est la."""
    if not CHEMIN_KIT.exists():
        return None
    for f in sorted(CHEMIN_KIT.iterdir()):
        if f.is_file() and f.suffix.lower() == ".md" and MOTIF_FICHIER.match(f.name):
            return f
    return None


def decouper(markdown: str) -> list[Section]:
    """Decoupe le fichier en sections, par titre."""
    sections: list[Section] = []
    titre, niveau, corps = "", 0, []
    for ligne in markdown.splitlines():
        m = _TITRE.match(ligne)
        if m:
            if titre:
                sections.append(Section(titre, niveau, "\n".join(corps).strip()))
            niveau, titre, corps = len(m.group(1)), m.group(2).strip(), []
        else:
            corps.append(ligne)
    if titre:
        sections.append(Section(titre, niveau, "\n".join(corps).strip()))
    return sections


def _trouver(sections: list[Section], cle: str) -> Section | None:
    """La section dont le titre contient `cle`, une fois normalise."""
    cible = normaliser(cle).strip()
    for s in sections:
        if cible in normaliser(s.titre):
            return s
    return None


# --------------------------------------------------------------------------
# L'ancrage dans l'annonce — une PHRASE, pas une fenetre de caracteres
#
# Le meme piege que dans `assemblage.phrase_autour`, corrige une fois deja :
# une fenetre de N caracteres autour du motif coupe au milieu des mots et
# cite la phrase d'a cote. On decoupe sur les fins de phrase, et on rend le
# morceau du TEXTE D'ORIGINE — jamais une reconstruction.
# --------------------------------------------------------------------------

_FIN_DE_PHRASE = re.compile(r"(?<=[.!?;:])\s+|\n")


def phrase_contenant(texte: str, motif: str) -> str:
    """La phrase de `texte` qui contient `motif`, rendue mot pour mot.

    Rend une chaine vide si le motif n'y est pas. Le resultat est TOUJOURS un
    extrait litteral : c'est ce que `verifier_ancrages` controle.
    """
    if not texte or not motif:
        return ""
    cible = normaliser(motif).strip()
    if not cible:
        return ""
    debut = 0
    for morceau in _FIN_DE_PHRASE.split(texte):
        if not morceau:
            continue
        i = texte.find(morceau, debut)
        if i < 0:
            continue
        debut = i + len(morceau)
        if f" {cible} " not in normaliser(morceau):
            continue
        net = morceau.strip()
        if len(net) > 320:
            # Phrase-fleuve : on coupe, mais DANS le texte d'origine, pour que
            # l'extrait reste litteral.
            j = net.lower().find(cible[:12].lower())
            depart = max(0, min(len(net) - 300, (j if j >= 0 else 0) - 100))
            net = net[depart:depart + 300]
        return net
    return ""


def _premier_motif_present(offre: dict[str, Any],
                           motifs: tuple[str, ...]) -> tuple[str, str]:
    """(motif trouve, phrase litterale de l'annonce) — ou ("", "")."""
    description = offre.get("description") or ""
    titre = (offre.get("titre") or "").strip()
    for motif in motifs:
        phrase = phrase_contenant(description, motif)
        if phrase:
            return motif, phrase
        if f" {normaliser(motif).strip()} " in normaliser(titre):
            return motif, titre
    return "", ""


def _est_suisse(offre: dict[str, Any]) -> bool:
    """Le poste est-il en Suisse ? Les lieux sont ceux de `geographie.pays`."""
    from .models import Offre
    from .scoring import detecter_pays

    return detecter_pays(Offre(
        titre="", lieu=offre.get("lieu") or "", employeur=offre.get("employeur") or "",
        salaire_devise=offre.get("salaire_devise"),
    )) == "suisse"


def _joint_le_dossier_technique(pieces: list[str]) -> list[str]:
    """Les pieces jointes qui sont son dossier technique."""
    return [p for p in pieces
            if "technical" in p.lower() or "technique" in p.lower()]


# --------------------------------------------------------------------------
# La preparation
# --------------------------------------------------------------------------


def preparer(offre: dict[str, Any], pieces: list[str] | None = None) -> Preparation:
    """Les points a preparer pour CETTE offre, chacun avec son ancrage.

    `pieces` : les fichiers qui partent au recruteur. Sert a declencher la
    question « avez-vous ecrit ce code ? » uniquement quand le dossier
    technique est reellement joint.
    """
    prep = Preparation()
    fichier = fichier_kit()
    if fichier is None:
        prep.kit_disponible = False
        prep.avertissements.append(
            "Le fichier « 17 - Préparation d'entretien » n'est pas dans le kit "
            "du serveur. Sans lui, aucune reponse n'est disponible : la console "
            "n'en invente pas. Depose-le dans le dossier du kit."
        )
        return prep

    sections = decouper(fichier.read_text(encoding="utf-8"))
    pieces = list(pieces or [])
    techniques = _joint_le_dossier_technique(pieces)
    # Une seule lecture de la table `entretien` par preparation.
    table, ecartes = _entretien_configure()
    tous, ecartes = _declencheurs_et_ecartes(table, ecartes)

    for d in tous:
        section = _trouver(sections, d.cle_section)
        if section is None:
            prep.sections_absentes.append(d.cle_section)
            continue
        if any(p.section == section.titre for p in prep.points):
            continue
        if d.pays == "ch" and not _est_suisse(offre):
            continue
        if d.cle_section == CLE_CODE and not techniques:
            continue

        if d.motifs:
            motif, phrase = _premier_motif_present(offre, d.motifs)
            if not phrase:
                continue
            ancrage, citation = "annonce", phrase
            pourquoi = f"{d.pourquoi} — « {motif.strip()} »"
        else:
            ancrage, citation, pourquoi = "dossier", section.premiere_ligne, d.pourquoi
            if d.cle_section == CLE_CODE:
                pourquoi = f"{d.pourquoi} : {', '.join(techniques)}"
            if d.pays == "ch":
                citation = (offre.get("lieu") or "").strip() or section.premiere_ligne

        prep.points.append(Point(
            question=section.titre, categorie=d.categorie, ancrage=ancrage,
            citation=citation, pourquoi=pourquoi, section=section.titre,
            reponse=section.corps,
        ))

    # Les attaques d'abord : c'est ce qui decide l'entretien.
    ordre = {"attaque": 0, "appui": 1, "rituel": 2}
    prep.points.sort(key=lambda p: ordre.get(p.categorie, 3))
    if len(prep.points) > MAX_POINTS:
        coupes = len(prep.points) - MAX_POINTS
        prep.points = prep.points[:MAX_POINTS]
        prep.avertissements.append(
            f"{coupes} point(s) de moindre priorite non repris. Ton fichier 17 "
            f"les contient : relis-le en entier la veille."
        )

    intitules, avertissement, ecartes_risque = _intitules_a_risque(table)
    titre_norm = normaliser(offre.get("titre") or "")
    for intitule in intitules:
        if f" {normaliser(intitule).strip()} " in titre_norm:
            prep.avertissements.append(f"Intitule « {intitule} » : {avertissement}")
            break

    ecartes += ecartes_risque
    if ecartes:
        prep.avertissements.append(
            f"{ecartes} élément(s) mal formé(s) dans la configuration de l'entretien, "
            f"ignoré(s) : lance « veille config verifier »."
        )

    if prep.sections_absentes:
        prep.avertissements.append(
            "Sections introuvables dans ton fichier 17 (titre renomme ?) : "
            + ", ".join(prep.sections_absentes)
        )
    return prep


def verifier_ancrages(prep: Preparation, offre: dict[str, Any],
                      kit_texte: str) -> list[str]:
    """Chaque citation est-elle un extrait LITTERAL de sa source ?

    C'est le controle qui interdit la question inventee. Rend la liste des
    manquements ; vide = tout est ancre.
    """
    manques: list[str] = []
    annonce = f"{offre.get('titre') or ''}\n{offre.get('description') or ''}"
    lieu = (offre.get("lieu") or "").strip()
    for p in prep.points:
        if not p.citation.strip():
            manques.append(f"{p.question} : aucune citation")
        elif p.ancrage == "annonce":
            if p.citation not in annonce:
                manques.append(f"{p.question} : citation absente de l'annonce")
        elif p.ancrage == "dossier":
            if p.citation not in kit_texte and p.citation != lieu:
                manques.append(f"{p.question} : citation absente du fichier 17")
        else:
            manques.append(f"{p.question} : ancrage inconnu « {p.ancrage} »")
    return manques


def rendre_markdown(prep: Preparation, offre: dict[str, Any]) -> str:
    """La note d'entretien. Tout ce qui est prose vient du fichier 17."""
    if not prep.kit_disponible:
        return ("# Préparation d'entretien\n\n"
                + "\n".join(f"> {a}" for a in prep.avertissements) + "\n")

    blocs = [
        f"# Préparation d'entretien — {offre.get('titre') or ''}\n\n"
        f"**{offre.get('employeur') or 'employeur non précisé'}** · "
        f"{offre.get('lieu') or 'lieu non précisé'}\n\n"
        "Chaque point ci-dessous est retenu pour une raison verifiable, et "
        "elle est ecrite. Les reponses sont celles de ton fichier `17` : "
        "elles ne sont ni reecrites ni resumees.\n"
    ]
    etiquette = {"attaque": "⚠ On t'attendra la-dessus",
                 "appui": "Ce que tu peux sortir",
                 "rituel": "Rituel"}
    for p in prep.points:
        source = "l'annonce dit" if p.ancrage == "annonce" else "ton dossier dit"
        blocs.append(
            f"\n---\n\n## {p.question}\n\n"
            f"*{etiquette.get(p.categorie, '')} — {p.pourquoi}*\n\n"
            f"**Ancrage ({source})** :\n\n> {p.citation}\n\n"
            f"{p.reponse}\n"
        )
    if prep.avertissements:
        blocs.append("\n---\n\n## A savoir\n\n"
                     + "\n".join(f"- {a}" for a in prep.avertissements) + "\n")
    return "".join(blocs)
