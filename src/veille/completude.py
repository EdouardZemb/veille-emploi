"""Combien sait-on de ce poste ? — score de COMPLETUDE.

⚠️ CE N'EST PAS LE SCORE DE CORRESPONDANCE, et les deux ne doivent jamais etre
melanges ni moyennes. Ils repondent a deux questions differentes :

    correspondance : est-ce que ce poste lui va ?
    complétude     : en sait-on assez pour ecrire une candidature qui tienne ?

Une offre parfaite mal documentee (score 87, complétude 20) et une offre
mediocre bien documentee (score 25, complétude 90) doivent rester lisibles
separement. C'est exactement le genre de chiffre qu'on a envie de fusionner
« pour simplifier », et ce serait la pire des simplifications : il perdrait la
seule information qui lui dit OU passer dix minutes.

USAGE PRINCIPAL : le bouton « Generer le dossier ». Aujourd'hui il peut sortir
une lettre a partir d'un extrait de trois lignes, et le resultat sera creux sans
que rien ne l'avertisse. Le bilan previent AVANT, et dit CE QUI manque — « donnees
insuffisantes » sans preciser laquelle ne sert a rien.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .config import charger_criteres, contient, normaliser

# Seuil au-dela duquel une candidature serieuse est possible sans aller
# chercher autre chose. Cale sur un corpus reel, pas choisi au hasard : la
# repartition mesuree vit dans la documentation de l'instance.
SEUIL_DOSSIER = 55

# Agregateurs : l'annonce y est relayee, pas publiee. Il manque presque
# toujours le nom du contact, la page « qui sommes-nous » et le process.
AGREGATEURS = {
    "arbeitnow.com", "indeed.com", "fr.indeed.com", "ch.indeed.com",
    "linkedin.com", "jobs.ch", "jobup.ch", "jobscout24.ch", "glassdoor.com",
    "welcometothejungle.com", "apec.fr", "monster.fr", "hellowork.com",
    "stepstone.de", "talent.com", "jooble.org",
}

_CONTACT = re.compile(
    r"(contact|kontakt|ansprechpartner|recruteur|recruiter|responsable\s+recrutement"
    r"|talent\s+acquisition|hiring\s+manager)\s*[:\-–]?\s*[A-ZÉÈÀÄÖÜ][\w'’-]+",
    re.IGNORECASE,
)
_TAILLE = re.compile(
    r"(\d[\d\s.,]{1,9})\s*(collaborateurs?|salaries?|employe|employees?|personnes?"
    r"|mitarbeiter|people)|groupe\s+de\s+\d|pme|start-?up|scale-?up|multinationale",
    re.IGNORECASE,
)


@dataclass
class Manque:
    libelle: str
    points: int
    quoi_faire: str

    def as_dict(self) -> dict[str, Any]:
        return {"libelle": self.libelle, "points": self.points, "quoi_faire": self.quoi_faire}


@dataclass
class Bilan:
    score: int
    niveau: str                       # solide | correct | mince | insuffisant
    manques: list[Manque] = field(default_factory=list)
    acquis: list[str] = field(default_factory=list)
    suffisant_pour_dossier: bool = False

    def as_dict(self) -> dict[str, Any]:
        # Aucune cle ne doit ressembler a une fusion avec le score de
        # correspondance. Verrouille par tests/test_completude.py.
        return {
            "score": self.score,
            "niveau": self.niveau,
            "manques": [m.as_dict() for m in self.manques],
            "acquis": self.acquis,
            "suffisant_pour_dossier": self.suffisant_pour_dossier,
            "seuil": SEUIL_DOSSIER,
        }


def _domaine(url: str) -> str:
    h = (urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _lieu_precis(offre: dict, criteres) -> bool:
    """Une ville, pas une region. « Grand Est, France » ne permet rien."""
    lieu = (offre.get("lieu") or "").strip()
    if not lieu:
        return False
    from .models import Offre
    from .scoring import lieu_imprecis

    motif, _poids, _groupe = lieu_imprecis(Offre(titre="x", lieu=lieu), criteres)
    return not motif


def evaluer(offre: dict[str, Any]) -> Bilan:
    """Ce qu'on sait de ce poste, et ce qu'il faudrait aller chercher."""
    criteres = charger_criteres()
    description = offre.get("description") or ""
    texte = normaliser(f"{description} {offre.get('titre') or ''}")
    score = 0
    manques: list[Manque] = []
    acquis: list[str] = []

    # --- La description : de loin le plus lourd --------------------------
    # C'est elle qui porte les missions, les exigences et le contexte. Sans
    # elle, une lettre ne peut qu'etre generique.
    if offre.get("donnees_partielles") or len(description) < 400:
        manques.append(Manque(
            "Description complete de l'annonce", 35,
            "Ouvre l'annonce, selectionne tout, et colle le texte dans « Lire "
            "l'annonce » : c'est le geste qui rapporte le plus.",
        ))
    else:
        score += 35
        acquis.append(f"description complete ({len(description)} caracteres)")

    # --- Le salaire ------------------------------------------------------
    if offre.get("salaire_min") or offre.get("salaire_max"):
        score += 12
        acquis.append("salaire connu")
    else:
        manques.append(Manque(
            "Fourchette de salaire", 12,
            "Cherche la fourchette sur la page d'origine ou sur Glassdoor : sans "
            "elle tu negocieras a l'aveugle, et tu ne sauras pas si l'offre passe "
            "ton plancher.",
        ))

    # --- Le lieu ---------------------------------------------------------
    if _lieu_precis(offre, criteres):
        score += 10
        acquis.append("lieu precis")
    else:
        manques.append(Manque(
            "Ville exacte du poste", 10,
            "L'annonce ne donne qu'une region ou rien. Demande la ville au "
            "premier contact : elle decide si le poste est tenable au quotidien.",
        ))

    # --- L'employeur -----------------------------------------------------
    employeur = (offre.get("employeur") or "").strip()
    if employeur:
        score += 10
        acquis.append(f"employeur identifie ({employeur})")
    else:
        manques.append(Manque(
            "Nom de l'employeur", 10,
            "L'annonce est anonyme ou passe par un cabinet. Sans le nom, impossible "
            "d'ecrire une lettre qui parle d'eux — cherche l'annonce sur le site du "
            "recruteur, ou demande-le.",
        ))

    # --- Le regime de presence ------------------------------------------
    geo = criteres.brut.get("geographie", {})
    motifs_presence = (geo.get("teletravail_complet_motifs", [])
                       + geo.get("presence_partielle_motifs", [])
                       + geo.get("presence_totale_motifs", []))
    if offre.get("zone") or any(contient(texte, m) for m in motifs_presence):
        score += 8
        acquis.append("regime de presence connu")
    else:
        manques.append(Manque(
            "Teletravail ou presence sur site", 8,
            "Rien dans l'annonce ne le dit. A poser au premier echange : c'est le "
            "critere qui decide le plus souvent.",
        ))

    # --- La langue exigee ------------------------------------------------
    langues = criteres.brut.get("langues", {})
    motifs_langue = []
    for bloc in langues.values():
        if isinstance(bloc, dict):
            motifs_langue += bloc.get("motifs", [])
    if any(contient(texte, m) for m in motifs_langue) or contient(texte, "anglais") \
            or contient(texte, "english"):
        score += 5
        acquis.append("exigences de langue connues")
    else:
        manques.append(Manque(
            "Niveau de langue attendu", 5,
            "L'annonce n'en parle pas. Sur le bassin balois c'est determinant : "
            "verifie sur la page d'origine avant d'investir du temps.",
        ))

    # --- La source -------------------------------------------------------
    domaine = _domaine(offre.get("url_canonique") or offre.get("url") or "")
    if domaine and domaine not in AGREGATEURS:
        score += 10
        acquis.append("source primaire (site de l'employeur)")
    else:
        manques.append(Manque(
            "Source primaire de l'annonce", 10,
            "Tu n'as que la version agregee. Cherche l'annonce sur le site carriere "
            "de l'employeur : elle est souvent plus complete, et donne le process "
            "de recrutement.",
        ))

    # --- L'employeur, en tant qu'organisation ----------------------------
    if _TAILLE.search(description):
        score += 5
        acquis.append("taille ou nature de l'entreprise")
    else:
        manques.append(Manque(
            "Taille et secteur de l'entreprise", 5,
            "Regarde leur page LinkedIn ou leur site : une lettre qui situe "
            "l'entreprise vaut mieux qu'une lettre qui parle de toi seul.",
        ))

    # --- Un interlocuteur ------------------------------------------------
    if _CONTACT.search(description):
        score += 5
        acquis.append("interlocuteur nomme")
    else:
        manques.append(Manque(
            "Nom d'un interlocuteur", 5,
            "Cherche le recruteur sur LinkedIn a la main. Une lettre adressee a "
            "quelqu'un passe mieux qu'un « Madame, Monsieur ».",
        ))

    score = max(0, min(100, score))
    if score >= 75:
        niveau = "solide"
    elif score >= SEUIL_DOSSIER:
        niveau = "correct"
    elif score >= 30:
        niveau = "mince"
    else:
        niveau = "insuffisant"

    return Bilan(
        score=score,
        niveau=niveau,
        manques=sorted(manques, key=lambda m: -m.points),
        acquis=acquis,
        suffisant_pour_dossier=score >= SEUIL_DOSSIER,
    )
