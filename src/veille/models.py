"""Structures de donnees partagees entre collecteurs, scoring et console."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Statuts du pipeline de candidature. L'ordre compte : c'est celui de l'entonnoir.
STATUTS = [
    "nouveau",
    "a_traiter",
    "interessante",
    "differee",
    "candidature_envoyee",
    "relance_envoyee",
    "reponse_recue",
    "entretien",
    "refus",
    "accepte",
    "ecartee",
]

# Statuts qui retirent definitivement l'offre du flux de veille.
STATUTS_CLOS = {"ecartee", "refus", "accepte"}

# Statuts qui sortent du flux courant sans etre un refus :
# "differee" = recevable plus tard, quand son allemand aura progresse.
STATUTS_HORS_FLUX = {"ecartee", "differee"}

# Parametres de tracking a retirer d'une URL avant de la comparer.
_PARAMS_TRACKING = re.compile(
    r"^(utm_|ut_|trk|trackingId|refId|eBP|lipi|midToken|midSig|trkEmail|otpToken"
    r"|sig|jsa|from|source|src|campaign|mc_cid|mc_eid|gclid|fbclid|_ga|ref)",
    re.IGNORECASE,
)


# Sites qui publient la MEME annonce sous plusieurs domaines nationaux.
# Sans cette table, une offre vue sur arbeitnow.ch et sur arbeitnow.fr compte
# pour deux offres differentes et pollue la liste.
_ALIAS_HOTES = (
    (re.compile(r"^arbeitnow\.[a-z.]{2,6}$"), "arbeitnow.com"),
)


def _hote_canonique(hote: str) -> str:
    for motif, remplacant in _ALIAS_HOTES:
        if motif.match(hote):
            return remplacant
    return hote


def canoniser_url(url: str | None) -> str:
    """Retire les parametres de tracking et normalise la forme de l'URL.

    Les alertes mail encapsulent les liens dans des redirecteurs ; ceux-ci sont
    resolus en amont par `collectors.liens.resoudre()`. Ici on ne fait que
    nettoyer ce qui reste, pour que deux annonces identiques recues par deux
    canaux differents produisent la meme empreinte.
    """
    if not url:
        return ""
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return url.strip()
    hote = parts.netloc.lower()
    if hote.startswith("www."):
        hote = hote[4:]
    hote = _hote_canonique(hote)
    # LinkedIn : /jobs/view/1234567890/?... -> on ne garde que l'identifiant
    chemin = parts.path.rstrip("/")
    garde = [(k, v) for k, v in parse_qsl(parts.query) if not _PARAMS_TRACKING.match(k)]
    garde.sort()
    return urlunsplit(("https", hote, chemin, urlencode(garde), ""))


def empreinte(url_canonique: str, titre: str, employeur: str) -> str:
    """Cle de deduplication principale, fondee sur l'URL.

    On prefere l'URL canonique quand elle existe. Sinon - cas d'un mail qui ne
    donne qu'un extrait sans lien exploitable - on retombe sur titre+employeur.
    """
    from .config import normaliser

    base = url_canonique or f"{normaliser(titre)}|{normaliser(employeur)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def empreinte_titre(titre: str, employeur: str) -> str:
    """Cle de deduplication secondaire, fondee sur l'intitule et l'employeur.

    POURQUOI ELLE EXISTE : un meme poste est souvent republie avec un nouvel
    identifiant. Observe en conditions reelles chez un employeur dont une offre
    arrivait trois fois sous les URL ...-100001, ...-100002 et
    ...-100003. Aucune normalisation d'URL ne peut les rapprocher.

    Elle sert aussi quand la meme annonce arrive par deux canaux : une alerte
    LinkedIn et l'API France Travail. La premiere vue est conservee, les
    suivantes sont enregistrees comme un simple evenement "revue".

    Limite assumee : deux ouvertures reellement distinctes portant le meme
    intitule chez le meme employeur seront fusionnees. C'est le bon compromis
    pour une liste a parcourir tous les jours.
    """
    from .config import normaliser

    if not titre.strip():
        return ""
    base = f"{normaliser(titre)}|{normaliser(employeur)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


@dataclass
class Contribution:
    """Une ligne de l'explication du score."""

    libelle: str
    points: float
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"libelle": self.libelle, "points": round(self.points, 1), "detail": self.detail}


@dataclass
class Offre:
    """Une annonce, quelle que soit sa provenance."""

    titre: str
    employeur: str = ""
    lieu: str = ""
    description: str = ""
    url: str = ""
    source: str = ""
    date_publication: date | None = None

    salaire_min: float | None = None
    salaire_max: float | None = None
    salaire_devise: str | None = None

    type_contrat: str = ""
    duree_mois: int | None = None

    # Vrai quand le mail ne contenait qu'un extrait : le score porte alors sur
    # un titre et un lieu seulement, et l'explication doit le dire.
    donnees_partielles: bool = False

    # Exigences qu'EDOUARD a validees sur cette annonce, relevees dans le texte
    # colle : {attribut: {"valeur": ..., "citation": ...}}. Elles REMPLACENT
    # une detection par motifs, elles n'ajoutent aucun bareme : les points
    # restent ceux de criteres.yaml. Une proposition non validee n'arrive
    # jamais ici — voir `exigences.py`.
    exigences: dict[str, dict[str, str]] = field(default_factory=dict)

    # Famille qu'EDOUARD a validee quand aucun motif ne l'a trouvee. Elle
    # prime sur la detection, et le bareme reste celui de criteres.yaml.
    famille_validee: str = ""

    # Renseignes par le scoring.
    score: float = 0.0
    famille: str = ""
    zone: str = ""
    # Cles des groupes d'atouts declenches (contexte_mobile, outils_test...).
    # Sert a filtrer dans la console : "montre-moi tout ce qui touche au mobile".
    atouts: list[str] = field(default_factory=list)
    rejete_auto: bool = False
    motif_rejet_auto: str = ""
    # Recevable plus tard : mise de cote sans refus.
    differee: bool = False
    motif_differe: str = ""
    explication: list[Contribution] = field(default_factory=list)

    date_collecte: datetime = field(default_factory=datetime.now)

    @property
    def url_canonique(self) -> str:
        return canoniser_url(self.url)

    @property
    def empreinte(self) -> str:
        return empreinte(self.url_canonique, self.titre, self.employeur)

    @property
    def empreinte_titre(self) -> str:
        return empreinte_titre(self.titre, self.employeur)

    @property
    def texte_complet(self) -> str:
        return " \n ".join(
            p for p in (self.titre, self.employeur, self.lieu, self.description, self.type_contrat) if p
        )

    @property
    def salaire_affiche(self) -> str:
        if self.salaire_min is None and self.salaire_max is None:
            return ""
        dev = self.salaire_devise or ""
        if self.salaire_min is not None and self.salaire_max is not None:
            if self.salaire_min == self.salaire_max:
                return f"{self.salaire_min:,.0f} {dev}".replace(",", " ")
            return f"{self.salaire_min:,.0f} - {self.salaire_max:,.0f} {dev}".replace(",", " ")
        seul = self.salaire_min if self.salaire_min is not None else self.salaire_max
        prefixe = "a partir de" if self.salaire_min is not None else "jusqu'a"
        return f"{prefixe} {seul:,.0f} {dev}".replace(",", " ")
