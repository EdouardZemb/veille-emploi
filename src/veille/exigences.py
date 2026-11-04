"""Relever les exigences d'une annonce collee — le modele PROPOSE, rien d'autre.

POURQUOI UN MODELE ICI, ALORS QUE LE RESTE N'EN UTILISE PAS. « Deux jours sur
site par semaine », « sehr gute Deutschkenntnisse », « mindestens drei Jahre
Berufserfahrung » : ces phrases disent la meme chose de mille facons, et une
expression reguliere les rate. On a corrige QUATRE variantes du meme defaut de
filtrage, chacune apres coup, chacune sur une offre reellement perdue.

CE QUE LE MODELE NE FAIT PAS, ET NE FERA JAMAIS : donner un point.

La propriete qui fait la valeur de cet outil — meme offre, meme score, chaque
point explicable par une ligne — n'est pas echangeable contre du confort. Elle
tient par une chaine de trois maillons, et chacun est verifie par un test :

  1. **Le modele ne rend qu'un triplet contraint** : un attribut pris dans une
     liste fermee, une valeur prise dans un domaine ferme, et une citation. Il
     ne rend aucun nombre de points, et aucun champ libre n'atteint le score.
  2. **La citation doit etre un extrait LITTERAL du texte colle.** Verifiee par
     `filtrer()`, caractere par caractere. Une proposition dont la citation
     n'est pas dans le texte est jetee — pas corrigee, jetee.
  3. **Rien n'agit tant qu'Edouard n'a pas valide.** Une proposition vit dans
     la base avec `validee_le IS NULL`, et le scoring ne lit que les validees.

Une fois validee, l'exigence ne cree PAS une regle nouvelle : elle REMPLACE un
fait que la detection automatique avait mal lu. Le bareme reste entierement
dans le `criteres.yaml` de la configuration. Deux offres portant la meme exigence validee
recoivent exactement les memes points, et la contribution cite SA phrase.

Si le modele est indisponible, la fonctionnalite disparait et rien d'autre ne
change : la detection par motifs continue, comme avant.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------
# Le domaine ferme. Le modele ne peut rien dire en dehors.
#
# Seuls les trois premiers attributs touchent au score, et ils le font en
# REMPLACANT une detection, jamais en ajoutant des points. Les autres sont
# renseignes pour lui — ils nourrissent la lecture, pas le calcul.
# --------------------------------------------------------------------------

ATTRIBUTS: dict[str, dict[str, Any]] = {
    "teletravail": {
        "libelle": "Teletravail",
        "valeurs": ("complet", "hybride", "aucun"),
        "agit_sur_le_score": True,
        "question": "L'annonce engage-t-elle un mode de travail ?",
    },
    "jours_sur_site": {
        "libelle": "Jours de presence exiges par semaine",
        "valeurs": ("0", "1", "2", "3", "4", "5"),
        "agit_sur_le_score": True,
        "question": "Un nombre de jours de presence est-il exige ?",
    },
    "allemand": {
        "libelle": "Allemand",
        "valeurs": ("aucun", "souhaite", "courant", "natif"),
        "agit_sur_le_score": True,
        "question": "Quel niveau d'allemand est exige ?",
    },
    "anglais": {
        "libelle": "Anglais",
        "valeurs": ("aucun", "souhaite", "courant"),
        "agit_sur_le_score": False,
        "question": "Quel niveau d'anglais est exige ?",
    },
    "annees_experience": {
        "libelle": "Annees d'experience demandees",
        "valeurs": tuple(str(n) for n in range(0, 21)),
        "agit_sur_le_score": False,
        "question": "Combien d'annees d'experience sont demandees ?",
    },
    "deplacements": {
        "libelle": "Deplacements",
        "valeurs": ("aucun", "occasionnels", "frequents"),
        "agit_sur_le_score": False,
        "question": "Des deplacements sont-ils annonces ?",
    },
    "astreinte": {
        "libelle": "Astreinte ou travail hors horaires",
        "valeurs": ("oui", "non"),
        "agit_sur_le_score": False,
        "question": "Une astreinte ou du travail de nuit / week-end est-il annonce ?",
    },
    "permis_travail": {
        "libelle": "Permis de travail suisse exige",
        "valeurs": ("oui", "non"),
        "agit_sur_le_score": False,
        "question": "Un permis de travail ou une residence est-il exige ?",
    },
}

ATTRIBUTS_QUI_AGISSENT = tuple(
    k for k, v in ATTRIBUTS.items() if v["agit_sur_le_score"])

# Une citation plus courte ne prouve rien ; plus longue, ce n'est plus une
# citation mais un recopiage de l'annonce.
MIN_CITATION = 8
MAX_CITATION = 300


@dataclass
class Exigence:
    attribut: str
    valeur: str
    citation: str

    @property
    def libelle(self) -> str:
        return ATTRIBUTS.get(self.attribut, {}).get("libelle", self.attribut)

    @property
    def agit_sur_le_score(self) -> bool:
        return bool(ATTRIBUTS.get(self.attribut, {}).get("agit_sur_le_score"))

    def as_dict(self) -> dict[str, Any]:
        return {"attribut": self.attribut, "valeur": self.valeur,
                "citation": self.citation, "libelle": self.libelle,
                "agit_sur_le_score": self.agit_sur_le_score}


@dataclass
class Relevé:
    ok: bool = False
    propositions: list[Exigence] = field(default_factory=list)
    rejetees: list[str] = field(default_factory=list)
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "message": self.message,
                "rejetees": self.rejetees,
                "propositions": [e.as_dict() for e in self.propositions]}


# Alias sans accent, pour les appelants.
Releve = Relevé


# --------------------------------------------------------------------------
# Le filtre — le maillon qui tient tout
# --------------------------------------------------------------------------

_ESPACES = re.compile(r"\s+")


def _citation_litterale(citation: str, texte: str) -> str:
    """La citation, telle qu'elle apparait dans le texte — ou "".

    On tolere une difference d'espaces (un modele reflow les retours a la
    ligne), mais RIEN d'autre : les mots doivent etre les siens, dans l'ordre.
    Le resultat rendu est l'extrait du TEXTE, jamais celui du modele.
    """
    net = (citation or "").strip()
    if not net:
        return ""
    if net in texte:
        return net
    # Meme suite de mots, espaces libres : on retrouve la tranche d'origine.
    motif = r"\s+".join(re.escape(mot) for mot in net.split())
    trouve = re.search(motif, texte)
    return trouve.group(0) if trouve else ""


def filtrer(brut: list[dict[str, Any]], texte: str) -> tuple[list[Exigence], list[str]]:
    """Ne garde que ce qui est verifiable. Rend (gardees, motifs de rejet).

    Rien n'est corrige : une proposition fausse est jetee. Corriger reviendrait
    a produire soi-meme ce que le modele n'a pas su produire, et la chaine de
    verification ne voudrait plus rien dire.
    """
    gardees: list[Exigence] = []
    rejetees: list[str] = []
    vus: set[str] = set()

    for item in brut or []:
        if not isinstance(item, dict):
            rejetees.append("proposition illisible")
            continue
        attribut = str(item.get("attribut") or "").strip()
        valeur = str(item.get("valeur") or "").strip()
        citation = str(item.get("citation") or "")

        if attribut not in ATTRIBUTS:
            rejetees.append(f"attribut hors liste : « {attribut[:40]} »")
            continue
        if valeur not in ATTRIBUTS[attribut]["valeurs"]:
            rejetees.append(f"{attribut} : valeur hors domaine « {valeur[:40]} »")
            continue
        if attribut in vus:
            rejetees.append(f"{attribut} : propose deux fois")
            continue

        exacte = _citation_litterale(citation, texte)
        if not exacte:
            rejetees.append(
                f"{attribut} : la citation n'est pas dans le texte colle")
            continue
        if not (MIN_CITATION <= len(exacte) <= MAX_CITATION):
            rejetees.append(f"{attribut} : citation de longueur invraisemblable")
            continue

        vus.add(attribut)
        gardees.append(Exigence(attribut, valeur, exacte))

    return gardees, rejetees


# --------------------------------------------------------------------------
# L'appel au modele
# --------------------------------------------------------------------------

def _consigne() -> str:
    lignes = [
        "Tu lis le texte d'une offre d'emploi et tu releves ce qu'elle EXIGE.",
        "",
        "Tu ne donnes aucune note, aucun score, aucun avis. Tu releves, c'est tout.",
        "",
        "Rends un tableau JSON, et RIEN d'autre. Chaque element a exactement",
        "trois champs : attribut, valeur, citation.",
        "",
        "ATTRIBUTS AUTORISES, et leurs seules valeurs possibles :",
    ]
    for cle, d in ATTRIBUTS.items():
        lignes.append(f"  {cle} : {' | '.join(d['valeurs'])}")
        lignes.append(f"      ({d['question']})")
    lignes += [
        "",
        "LA CITATION EST LA REGLE LA PLUS IMPORTANTE.",
        "",
        "Elle doit etre un extrait COPIE MOT POUR MOT du texte qu'on te donne.",
        "Pas une traduction, pas un resume, pas une reformulation, pas une",
        "correction d'orthographe. Si tu ne peux pas copier une phrase qui le",
        "prouve, N'INCLUS PAS l'attribut : un controle automatique compare ta",
        "citation au texte, et jette tout ce qui ne s'y trouve pas.",
        "",
        "N'invente aucun attribut que le texte ne dit pas. Un silence n'est pas",
        "un « aucun » : si l'annonce ne parle pas d'allemand, ne mets rien.",
        "",
        "Exemple de sortie :",
        '[{"attribut": "jours_sur_site", "valeur": "2",',
        '  "citation": "2 Tage pro Woche vor Ort"}]',
    ]
    return "\n".join(lignes)


def disponible():
    """Meme condition que l'affinement : meme SDK, meme jeton."""
    from . import affinement

    return affinement.disponible()


def _extraire_json(texte: str) -> list[dict[str, Any]]:
    """Le tableau JSON, meme entoure de bavardage ou d'un bloc markdown."""
    net = (texte or "").strip()
    if net.startswith("```"):
        net = re.sub(r"^```[a-z]*\s*|\s*```$", "", net, flags=re.IGNORECASE)
    try:
        charge = json.loads(net)
    except json.JSONDecodeError:
        debut, fin = net.find("["), net.rfind("]")
        if debut < 0 or fin <= debut:
            return []
        try:
            charge = json.loads(net[debut:fin + 1])
        except json.JSONDecodeError:
            return []
    if isinstance(charge, dict):
        charge = charge.get("exigences") or charge.get("resultats") or []
    return charge if isinstance(charge, list) else []


def proposer(texte: str) -> Relevé:
    """Propose des exigences pour ce texte. N'ecrit rien, ne score rien."""
    from . import affinement

    etat = disponible()
    if not etat.possible:
        return Relevé(False, message=etat.raison)
    if len((texte or "").strip()) < 200:
        return Relevé(False, message="Texte trop court pour un relevé serieux.")

    reponse = affinement.appeler_modele(texte[:12000], _consigne())
    if not reponse.ok:
        return Relevé(False, message=reponse.message)

    gardees, rejetees = filtrer(_extraire_json(reponse.texte), texte)
    if not gardees and not rejetees:
        return Relevé(True, message="Aucune exigence relevée dans ce texte.")
    return Relevé(
        True, propositions=gardees, rejetees=rejetees,
        message=(f"{len(gardees)} proposition(s). "
                 f"Rien n'est pris en compte avant ta validation."
                 + (f" {len(rejetees)} rejetée(s) avant de t'être montrée(s)."
                    if rejetees else "")),
    )


def ce_qui_part() -> str:
    return ("Le texte de l'annonce est envoyé à Anthropic pour y relever les "
            "exigences. Il quitte ton serveur. Ton dossier, ta lettre et tes "
            "critères ne partent pas.")
