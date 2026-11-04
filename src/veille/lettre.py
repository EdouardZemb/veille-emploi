"""La lettre comme OBJET REDIGE, et non comme artefact derive.

POURQUOI CE MODULE EXISTE. Jusqu'ici la lettre etait un derive : gabarit ->
assemblage -> substitution -> PDF. `affiner/appliquer` et `affiner/annuler`
appellent tous deux `dossier.regenerer_pdf()`, donc la reecrivent sans
sommation. C'etait sans consequence tant que personne ne pouvait l'editer.

Des qu'il peut l'editer, une regeneration DETRUIT SON TRAVAIL. D'ou la regle
unique dont tout le reste decoule :

    CE QU'UN HUMAIN A DECIDE NE SE REGENERE JAMAIS.

Trois etats, et une seule transition qui compte :

    assemblee  -> le programme decide, regenerable librement
    proposee   -> un modele propose, la proposition est jetable
    redigee    -> IL a decide. Plus jamais regeneree sans geste explicite.

L'IDENTITE DES PARAGRAPHES EST LE POINT DELICAT, et c'est ce que ce module
resout. Un `id` ne peut pas etre un indice : inserer un paragraphe decalerait
tout le reste et la provenance mentirait — elle dirait « ce paragraphe est de
toi » d'un paragraphe du gabarit. Or la provenance est precisement ce qu'il a
demande : savoir toujours quelles phrases sont les siennes.

On associe donc PAR EMPREINTE D'ABORD, PAR POSITION ENSUITE, et l'echec se
degrade du bon cote : un bloc qu'on ne reconnait pas devient `edouard`, jamais
`gabarit`. Mieux vaut lui attribuer une phrase du gabarit que lui en retirer
une qu'il a ecrite.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Noms de fichiers. Tous dans le repertoire du dossier de candidature : le
# dossier doit rester complet et lisible sur le disque, c'est deja le cas pour
# `fiche-offre.md`, `preparation-entretien.md` et les deux zips.
# --------------------------------------------------------------------------

NOM_LETTRE = "lettre-de-motivation.md"
NOM_META = "lettre.meta.json"
NOM_HISTORIQUE = "lettre.historique"
NOM_ASSEMBLEE = "lettre-assemblee.md"
NOM_PROPOSITION = "lettre-affinee.md"
# G1 : le gabarit est COPIE dans le dossier a la redaction. Quatre kilo-octets,
# et le differentiel « voici ce qui a change dans le gabarit » devient possible
# sans versionner le kit.
NOM_GABARIT = "gabarit-source.md"

# Ce qui ne part JAMAIS au recruteur. Par NOM DECLARE, pas par extension :
# `fiche-offre.md` n'est exclu du paquet d'envoi aujourd'hui que parce qu'il
# finit par `.md`, ce qui est un controle accidentel et non une intention.
JAMAIS_AU_RECRUTEUR = (NOM_META, NOM_HISTORIQUE, NOM_GABARIT, NOM_ASSEMBLEE,
                       NOM_PROPOSITION, "fiche-offre.md",
                       "preparation-entretien.md")

ETATS = ("assemblee", "proposee", "redigee")

# Quatre origines, et PAS DE CINQUIEME. Un paragraphe ecrit par un agent et
# non accepte n'existe pas dans le document.
#
#   gabarit       : vient de sa lettre type, inchange
#   assemblage    : la charniere « Votre annonce cite ... », produite par
#                   assemblage.py a partir des termes releves par le scoring
#   edouard       : il l'a ecrit ou modifie
#   agent_accepte : il a CHOISI une formulation proposee par la relecture.
#                   Choisir n'est pas ecrire : confondre les deux est
#                   exactement la degradation qu'il veut eviter.
ORIGINES = ("gabarit", "assemblage", "edouard", "agent_accepte")

# Origines qui font d'une lettre un objet redige. Les deux autres restent
# derivables.
ORIGINES_HUMAINES = ("edouard", "agent_accepte")

# --------------------------------------------------------------------------
# Contraintes de la relecture (E2). CABLEES DES MAINTENANT pour que la
# relecture n'ait pas a y revenir, et surtout pour qu'elle ne puisse pas s'en
# affranchir discretement.
# --------------------------------------------------------------------------

# Dix suggestions a arbitrer sur un telephone, c'est un dossier qui ne part
# pas. Meme arbitrage que `assemblage.MAX_TERMES = 3` : « Quatre termes font
# une liste, pas une lecture. »
MAX_ANNOTATIONS = 3

# JAMAIS UNE SEULE PROPOSITION. Une proposition unique est une reecriture
# deguisee en suggestion ; deux ou trois le forcent a trancher, et choisir
# coute moins que rediger. Zero est legitime : le defaut est signalable mais
# pas reparable sans qu'il decide quoi dire.
MIN_PROPOSITIONS = 2
MAX_PROPOSITIONS = 3


def propositions_recevables(propositions: list[str]) -> bool:
    """Zero, deux ou trois. Jamais une. Invariant, pas reglage."""
    n = len(propositions)
    return n == 0 or MIN_PROPOSITIONS <= n <= MAX_PROPOSITIONS


# --------------------------------------------------------------------------
# Empreintes
# --------------------------------------------------------------------------

# MD5, comme `empreintes.py` : meme algorithme pour le kit et pour la lettre,
# pour qu'il n'y ait qu'une notion d'empreinte dans le projet.
#
# NORMALISATION MINIMALE, ET C'EST VOULU. On ramene les fins de ligne et on
# retire les blancs de bord ; on ne touche a RIEN d'autre. En particulier on ne
# desaccentue pas : une empreinte qui ignorerait les accents ne verrait pas
# qu'un accent a ete casse, alors que c'est precisement un des defauts que la
# porte doit attraper.
def empreinte(texte: str) -> str:
    net = (texte or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.md5(net.encode("utf-8")).hexdigest()


def empreinte_fichier(chemin: Path) -> str:
    """Empreinte d'un fichier, ou chaine vide s'il est absent.

    LA CHAINE VIDE EST UN RESULTAT. Un gabarit absent n'est pas un gabarit
    identique : c'est la lecon de `_kit_est_provisoire`, qui rendait False des
    que la variable etait definie, sans regarder le contenu.
    """
    if not chemin.exists() or not chemin.is_file():
        return ""
    return hashlib.md5(chemin.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Decoupage en paragraphes
# --------------------------------------------------------------------------

# MEME DECOUPAGE QUE LE RENDU. `rendu._SEPARATEUR_BLOC` vaut `\n\s*\n` : un
# paragraphe de l'editeur est donc exactement un bloc du PDF. Sans cet
# alignement, l'editeur montrerait une structure que le PDF ne respecte pas, et
# une annotation ancree sur « le paragraphe 4 » ne designerait pas le meme
# texte des deux cotes.
_SEPARATEUR = re.compile(r"(\n\s*\n)")


def decouper(texte: str) -> list[tuple[str, str]]:
    """[(contenu, separateur_qui_suit), ...].

    LE SEPARATEUR EST CONSERVE TEL QUEL. `recoller(decouper(t)) == t`, au
    caractere pres, et c'est verrouille par un test. Un editeur qui
    reformaterait le fichier en silence — fins de ligne, lignes vides, espaces
    de fin — produirait a chaque ouverture un diff que personne n'a demande, et
    toutes les empreintes changeraient d'un coup : la provenance dirait que
    tout est de lui.
    """
    if not texte:
        return []
    morceaux = _SEPARATEUR.split(texte)
    sortie: list[tuple[str, str]] = []
    for i in range(0, len(morceaux), 2):
        contenu = morceaux[i]
        separateur = morceaux[i + 1] if i + 1 < len(morceaux) else ""
        if contenu == "" and separateur == "":
            continue
        sortie.append((contenu, separateur))
    return sortie


def recoller(blocs: list[tuple[str, str]]) -> str:
    return "".join(c + s for c, s in blocs)


_SEPARATEUR_DEFAUT = "\n\n"


# --------------------------------------------------------------------------
# Un paragraphe
# --------------------------------------------------------------------------


@dataclass
class Paragraphe:
    id: str
    texte: str
    origine: str
    separateur: str = _SEPARATEUR_DEFAUT
    modifie_le: str = ""
    # Renseigne seulement pour `agent_accepte` : quel defaut la relecture
    # signalait. Sert a mesurer, plus tard, quelles relectures il accepte.
    code_relecture: str = ""

    @property
    def empreinte(self) -> str:
        return empreinte(self.texte)

    @property
    def est_de_lui(self) -> bool:
        return self.origine in ORIGINES_HUMAINES

    @property
    def mots(self) -> int:
        return len(self.texte.split())

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "origine": self.origine,
                "empreinte": self.empreinte, "modifie_le": self.modifie_le,
                "code_relecture": self.code_relecture,
                "mots": self.mots}


# --------------------------------------------------------------------------
# Reassociation : le coeur du module
# --------------------------------------------------------------------------


# UN IDENTIFIANT SUPPRIME NE SE REATTRIBUE JAMAIS, et c'est un test qui l'a
# impose. Premiere version : `_prochain_id` cherchait le plus petit `pNN` libre
# parmi les identifiants presents. Supprimer p03 puis ajouter un paragraphe
# rendait donc p03 a un texte qui n'a rien a voir — et l'historique, comme les
# annotations de la relecture, pointeraient vers l'ancien.
#
# D'ou `dernier_id` : une borne haute MONOTONE, conservee dans la meta. Elle ne
# redescend jamais, meme quand des paragraphes disparaissent.
_RE_ID = re.compile(r"^p(\d+)$")


def _numero_de(pid: str) -> int:
    m = _RE_ID.match(pid or "")
    return int(m.group(1)) if m else 0


def _prochain_id(connus: set[str], plancher: int) -> tuple[str, int]:
    """(identifiant neuf, nouveau plancher). Strictement au-dessus du plancher."""
    n = plancher + 1
    while f"p{n:02d}" in connus:
        n += 1
    return f"p{n:02d}", n


def reassocier(
    blocs: list[tuple[str, str]],
    anciens: list[dict[str, Any]],
    dernier_id: int = 0,
) -> tuple[list[Paragraphe], int]:
    """Associe les blocs lus sur le disque aux paragraphes connus.

    TROIS PASSES, dans cet ordre, et l'ordre est la conception :

      1. EMPREINTE EXACTE. Un bloc dont l'empreinte est connue garde son `id`
         ET son origine. C'est le cas courant : ouvrir la lettre, ne rien
         changer, la refermer, ne doit rien modifier.
         Une empreinte presente deux fois — deux paragraphes identiques, cas
         rare mais legitime — est consommee dans l'ordre de lecture.

      2. POSITION, ENTRE DEUX ANCRES. Les blocs non reconnus sont repartis
         entre les paragraphes ancres par la passe 1. Si, entre deux ancres, il
         reste autant de blocs que d'anciens paragraphes, on les apparie dans
         l'ordre : ce sont des paragraphes MODIFIES. Ils gardent leur `id` —
         pour que l'historique et, demain, les annotations restent ancres — mais
         leur origine devient `edouard`, parce que le texte a change et que
         personne d'autre n'a pu le changer.

      3. TOUT LE RESTE est nouveau : `id` neuf, origine `edouard`.

    POURQUOI PAS UNE SIMILARITE DE TEXTE EN PASSE 2. Parce qu'elle devinerait,
    et que ce projet refuse de deviner partout ailleurs — `_remplir` ne repare
    pas la ponctuation « parce qu'il faudrait deviner ce que l'auteur voulait ».
    Un appariement par position est faux de facon previsible ; un appariement
    par ressemblance est faux de facon surprenante.

    L'ECHEC SE DEGRADE DU BON COTE. Si la lettre a ete editee hors console — il
    ouvre le `.md` dans un editeur de texte — la provenance dit « tout est de
    lui » au lieu de mentir. C'est le bon echec : on lui attribue une phrase du
    gabarit, on ne lui retire pas une phrase qu'il a ecrite.
    """
    maintenant = datetime.now().astimezone().isoformat(timespec="seconds")
    ids_connus = {a.get("id", "") for a in anciens if a.get("id")}
    # Le plancher ne redescend jamais : il tient compte des identifiants encore
    # presents ET de la borne conservee dans la meta.
    plancher = max([dernier_id] + [_numero_de(i) for i in ids_connus] or [0])

    # --- passe 1 : empreinte exacte ---------------------------------------
    par_empreinte: dict[str, list[dict[str, Any]]] = {}
    for a in anciens:
        par_empreinte.setdefault(a.get("empreinte", ""), []).append(a)

    ancres: dict[int, dict[str, Any]] = {}
    for i, (contenu, _sep) in enumerate(blocs):
        file = par_empreinte.get(empreinte(contenu))
        if file:
            ancres[i] = file.pop(0)

    # Les anciens non consommes, dans leur ordre d'origine : candidats a la
    # passe 2.
    consommes = {id(a) for a in ancres.values()}
    restants = [a for a in anciens if id(a) not in consommes]

    # --- passe 2 : position, entre deux ancres ----------------------------
    # On decoupe la liste des blocs en tranches separees par les ancres, et on
    # fait de meme pour les anciens restants en se servant de leur position
    # declaree. Une tranche n'est appariee que si les deux comptes coincident.
    position_ancienne = {id(a): a.get("position", i) for i, a in enumerate(anciens)}
    resultat: list[Paragraphe | None] = [None] * len(blocs)

    def neuf_id() -> str:
        nonlocal plancher
        nid, plancher = _prochain_id(ids_connus, plancher)
        ids_connus.add(nid)
        return nid

    for i, ancienne in ancres.items():
        contenu, sep = blocs[i]
        resultat[i] = Paragraphe(
            id=ancienne.get("id") or neuf_id(),
            texte=contenu,
            origine=(ancienne.get("origine") if ancienne.get("origine") in ORIGINES
                     else "edouard"),
            separateur=sep,
            modifie_le=ancienne.get("modifie_le", ""),
            code_relecture=ancienne.get("code_relecture", ""),
        )
        ids_connus.add(resultat[i].id)

    bornes = sorted(ancres)
    tranches: list[tuple[int, int]] = []
    debut = 0
    for b in bornes + [len(blocs)]:
        if b > debut:
            tranches.append((debut, b))
        debut = b + 1
    if debut < len(blocs):
        tranches.append((debut, len(blocs)))

    for deb, fin in tranches:
        indices = [i for i in range(deb, fin) if resultat[i] is None]
        if not indices:
            continue
        # Les anciens dont la position declaree tombe dans cette tranche.
        candidats = [a for a in restants
                     if deb <= position_ancienne[id(a)] < fin]
        if len(candidats) == len(indices) and candidats:
            for i, ancienne in zip(indices, candidats):
                contenu, sep = blocs[i]
                resultat[i] = Paragraphe(
                    id=ancienne.get("id") or neuf_id(),
                    texte=contenu,
                    # LE TEXTE A CHANGE : l'origine devient la sienne. Aucune
                    # autre conclusion n'est possible — le programme n'ecrit
                    # jamais dans une lettre redigee.
                    origine="edouard",
                    separateur=sep,
                    modifie_le=maintenant,
                )
                ids_connus.add(resultat[i].id)
                restants.remove(ancienne)

    # --- passe 3 : tout le reste est neuf ---------------------------------
    for i, (contenu, sep) in enumerate(blocs):
        if resultat[i] is not None:
            continue
        resultat[i] = Paragraphe(id=neuf_id(), texte=contenu, origine="edouard",
                                 separateur=sep, modifie_le=maintenant)

    return [p for p in resultat if p is not None], plancher


# --------------------------------------------------------------------------
# La lettre
# --------------------------------------------------------------------------


@dataclass
class Filiation:
    """De quoi cette lettre est issue, FIGE au moment de la redaction.

    `gabarit_empreinte` n'est JAMAIS rafraichie automatiquement. C'est la
    lecon d'`empreintes.py`, mot pour mot : « Un controle qui relirait
    l'empreinte du disque surveille mesurerait sa propre copie et passerait
    toujours — il ne dirait rien, tres regulierement. »
    """

    gabarit_nom: str = ""
    gabarit_source: str = ""          # "kit" | "depot"
    gabarit_empreinte: str = ""
    langue_gabarit: str = ""
    # Ce qu'on savait de l'offre au moment de rediger. Si une de ces valeurs
    # change ensuite, la lettre porte l'ancienne : c'est bloquant.
    marqueurs_resolus: dict[str, str] = field(default_factory=dict)
    # L'assemblage : la phrase charniere et les termes cites par le scoring.
    assemblage_empreinte: str = ""
    assemblage_termes: list[str] = field(default_factory=list)
    assemblage_paragraphe: str = ""
    pieces_annoncees: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "gabarit_nom": self.gabarit_nom,
            "gabarit_source": self.gabarit_source,
            "gabarit_empreinte": self.gabarit_empreinte,
            "gabarit_empreinte_methode": "md5",
            "langue_gabarit": self.langue_gabarit,
            "marqueurs_resolus": self.marqueurs_resolus,
            "assemblage_empreinte": self.assemblage_empreinte,
            "assemblage_termes": self.assemblage_termes,
            "assemblage_paragraphe": self.assemblage_paragraphe,
            "pieces_annoncees": self.pieces_annoncees,
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Filiation":
        d = d or {}
        return cls(
            gabarit_nom=d.get("gabarit_nom", ""),
            gabarit_source=d.get("gabarit_source", ""),
            gabarit_empreinte=d.get("gabarit_empreinte", ""),
            langue_gabarit=d.get("langue_gabarit", ""),
            marqueurs_resolus=d.get("marqueurs_resolus") or {},
            assemblage_empreinte=d.get("assemblage_empreinte", ""),
            assemblage_termes=d.get("assemblage_termes") or [],
            assemblage_paragraphe=d.get("assemblage_paragraphe", ""),
            pieces_annoncees=d.get("pieces_annoncees") or [],
        )


@dataclass
class Lettre:
    repertoire: Path
    etat: str
    paragraphes: list[Paragraphe]
    filiation: Filiation
    redigee_le: str = ""
    # Borne haute monotone des identifiants attribues. Conservee pour qu'un
    # identifiant supprime ne soit JAMAIS reattribue.
    dernier_id: int = 0
    # Vrai quand aucun `lettre.meta.json` n'existait : dossier genere avant
    # l'editeur. On ne devine pas une provenance qu'on n'a pas enregistree —
    # voir `_meta_reconstruite`.
    meta_reconstruite: bool = False

    @property
    def texte(self) -> str:
        return recoller([(p.texte, p.separateur) for p in self.paragraphes])

    @property
    def paragraphes_de_lui(self) -> list[Paragraphe]:
        return [p for p in self.paragraphes if p.est_de_lui]

    @property
    def mots_de_lui(self) -> int:
        return sum(p.mots for p in self.paragraphes_de_lui)

    @property
    def derniere_modification(self) -> str:
        dates = [p.modifie_le for p in self.paragraphes if p.modifie_le]
        return max(dates) if dates else self.redigee_le

    def par_id(self, pid: str) -> Paragraphe | None:
        return next((p for p in self.paragraphes if p.id == pid), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "etat": self.etat,
            "redigee_le": self.redigee_le,
            "meta_reconstruite": self.meta_reconstruite,
            "filiation": self.filiation.as_dict(),
            "paragraphes": [
                {**p.as_dict(), "texte": p.texte, "position": i}
                for i, p in enumerate(self.paragraphes)
            ],
            "compte_de_lui": len(self.paragraphes_de_lui),
            "mots_de_lui": self.mots_de_lui,
            "derniere_modification": self.derniere_modification,
        }


# --------------------------------------------------------------------------
# Lecture et ecriture
# --------------------------------------------------------------------------


def _meta_reconstruite(blocs, filiation: Filiation) -> list[dict[str, Any]]:
    """Provenance d'un dossier genere AVANT l'editeur.

    Les quatre dossiers deja generes n'ont pas de `lettre.meta.json`. On ne
    peut pas savoir quel paragraphe venait du gabarit : on ne le devine donc
    pas. Tout est marque `gabarit`, SAUF la charniere d'assemblage si la
    filiation la connait — elle est reconnaissable au caractere pres.

    Marquer tout `gabarit` plutot que tout `edouard` est le choix prudent
    DANS CE SENS-LA : sur une lettre jamais editee, dire « c'est du gabarit »
    est vrai. Des qu'il edite un bloc, la passe 2 le repasse a `edouard`.
    """
    sortie = []
    for i, (contenu, _sep) in enumerate(blocs):
        origine = "gabarit"
        if (filiation.assemblage_paragraphe
                and contenu.strip() == filiation.assemblage_paragraphe.strip()):
            origine = "assemblage"
        sortie.append({"id": f"p{i + 1:02d}", "origine": origine,
                       "empreinte": empreinte(contenu), "position": i,
                       "modifie_le": "", "code_relecture": ""})
    return sortie


def lire(repertoire: Path) -> Lettre:
    """La lettre du dossier, avec sa provenance reassociee.

    Fonction de lecture PURE : elle n'ecrit rien, pas meme le
    `lettre.meta.json` qu'elle vient de reconstruire. Un dossier qu'on ouvre
    pour regarder ne doit pas changer d'etat sur le disque.
    """
    repertoire = Path(repertoire)
    chemin = repertoire / NOM_LETTRE
    if not chemin.exists():
        raise FileNotFoundError(f"aucune lettre dans {repertoire}")
    texte = chemin.read_text(encoding="utf-8")
    blocs = decouper(texte)

    meta_chemin = repertoire / NOM_META
    if meta_chemin.exists():
        brut = json.loads(meta_chemin.read_text(encoding="utf-8"))
        filiation = Filiation.depuis_dict(brut.get("filiation"))
        anciens = brut.get("paragraphes") or []
        etat = brut.get("etat") if brut.get("etat") in ETATS else "assemblee"
        redigee_le = brut.get("redigee_le", "")
        borne = int(brut.get("dernier_id") or 0)
        reconstruite = False
    else:
        filiation = Filiation()
        anciens = _meta_reconstruite(blocs, filiation)
        etat = "assemblee"
        redigee_le = ""
        borne = len(blocs)
        reconstruite = True

    paragraphes, borne = reassocier(blocs, anciens, borne)
    # Un paragraphe de lui dans une lettre declaree `assemblee` : l'etat suit
    # le contenu, jamais l'inverse.
    if etat != "redigee" and any(p.est_de_lui for p in paragraphes):
        etat = "redigee"
        redigee_le = redigee_le or datetime.now().astimezone().isoformat(timespec="seconds")

    return Lettre(repertoire=repertoire, etat=etat, paragraphes=paragraphes,
                  filiation=filiation, redigee_le=redigee_le,
                  dernier_id=borne, meta_reconstruite=reconstruite)


def ecrire(lettre: Lettre) -> None:
    """Ecrit la lettre ET sa meta. Les deux ou aucune.

    L'ordre compte : la meta d'abord, la lettre ensuite. Si l'ecriture
    s'interrompt entre les deux, on a une meta qui decrit un texte legerement
    plus ancien — la reassociation s'en remet. L'inverse donnerait une lettre
    sans provenance, donc une provenance qui mentirait au prochain chargement.
    """
    rep = lettre.repertoire
    rep.mkdir(parents=True, exist_ok=True)
    corps = {
        "schema": "lettre/1",
        "etat": lettre.etat,
        "redigee_le": lettre.redigee_le,
        "dernier_id": max([lettre.dernier_id]
                          + [_numero_de(p.id) for p in lettre.paragraphes] or [0]),
        "filiation": lettre.filiation.as_dict(),
        "paragraphes": [
            {**p.as_dict(), "position": i}
            for i, p in enumerate(lettre.paragraphes)
        ],
    }
    (rep / NOM_META).write_text(
        json.dumps(corps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (rep / NOM_LETTRE).write_text(lettre.texte, encoding="utf-8")
    try:
        (rep / NOM_META).chmod(0o600)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Historique
# --------------------------------------------------------------------------

_RE_VERSION = re.compile(r"^(\d{3})-(\d{8}T\d{4})-([a-z-]+)\.md$")


@dataclass
class Version:
    numero: int
    horodatage: str
    etiquette: str
    fichier: str

    @property
    def lisible(self) -> str:
        h = self.horodatage
        return f"{h[6:8]}/{h[4:6]} {h[9:11]}:{h[11:13]}"

    def as_dict(self) -> dict[str, Any]:
        return {"numero": self.numero, "horodatage": self.horodatage,
                "etiquette": self.etiquette, "fichier": self.fichier,
                "lisible": self.lisible}


def versions(repertoire: Path) -> list[Version]:
    """Les versions conservees, de la plus ancienne a la plus recente."""
    dossier = Path(repertoire) / NOM_HISTORIQUE
    if not dossier.exists():
        return []
    sortie = []
    for f in sorted(dossier.iterdir()):
        m = _RE_VERSION.match(f.name)
        if m:
            sortie.append(Version(int(m.group(1)), m.group(2), m.group(3), f.name))
    return sorted(sortie, key=lambda v: v.numero)


def historiser(repertoire: Path, etiquette: str) -> Version | None:
    """Ecrit la lettre courante dans l'historique, et rend la version creee.

    LE NOM DIT QUOI : `003-20261010T2148-redigee.md`. C'est ce que
    `lettre-assemblee.md` ne fait plus des la deuxieme application de
    l'affinement — il recoit la version COURANTE, donc apres deux affinements
    il contient le premier affinement, et `affiner/annuler` restaure un texte
    produit par un modele en promettant « retour a la version assemblee ».

    Une version est ecrite A CHAQUE TRANSITION D'ETAT, pas a chaque frappe.
    Quatre kilo-octets par version, quatre versions par dossier, soixante
    dossiers : un megaoctet. Negligeable.
    """
    rep = Path(repertoire)
    source = rep / NOM_LETTRE
    if not source.exists():
        return None
    etiquette = re.sub(r"[^a-z-]+", "-", etiquette.lower()).strip("-") or "version"
    dossier = rep / NOM_HISTORIQUE
    dossier.mkdir(exist_ok=True)
    try:
        dossier.chmod(0o700)
    except OSError:
        pass
    numero = (versions(rep)[-1].numero + 1) if versions(rep) else 1
    horodatage = datetime.now().strftime("%Y%m%dT%H%M")
    nom = f"{numero:03d}-{horodatage}-{etiquette}.md"
    shutil.copy2(source, dossier / nom)
    return Version(numero, horodatage, etiquette, nom)


def derniere_version(repertoire: Path, etiquette: str) -> Version | None:
    """La plus recente version portant cette etiquette.

    Permet de demander vraiment « la derniere version assemblee » et de
    l'obtenir — ce que le fichier unique `lettre-assemblee.md` ne permet pas.
    """
    return next((v for v in reversed(versions(repertoire))
                 if v.etiquette == etiquette), None)


def texte_de_version(repertoire: Path, numero: int) -> str:
    v = next((v for v in versions(repertoire) if v.numero == numero), None)
    if not v:
        raise FileNotFoundError(f"version {numero} inconnue")
    return (Path(repertoire) / NOM_HISTORIQUE / v.fichier).read_text(encoding="utf-8")
