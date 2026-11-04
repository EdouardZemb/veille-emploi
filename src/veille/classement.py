"""Proposer une famille aux offres qui n'en ont aucune.

LE CONSTAT QUI JUSTIFIE CE MODULE. Mesure du 02/10/2026 : une part notable des
offres n'a aucune famille, dont certaines encore actives. La plupart le meritent — une
annonce de Hauswart ou de Sozialpadagogin n'entre dans aucun de ses metiers, et
lui en attribuer un serait une erreur. Mais parmi elles :

    « Automation Tester with Level 2 clearance »
    « Specialiste de l'automatisation de tests »
    « Test Practitioner/Automation »

Les motifs disent « test automation engineer » et « automatisation des tests ».
Ils ne disent pas « automation tester », ni « automatisation DE tests ». Ces
offres sont son metier, et elles sont tombees dans le trou entre deux libelles.

CE QUE FAIT CE MODULE, ET CE QU'IL NE FAIT PAS. Il ne devine pas un metier : il
mesure un RECOUVREMENT DE MOTS entre l'intitule et les motifs d'une famille,
et il montre les mots. Chaque proposition se lit : « famille X, parce que le
mot "automation" est dans l'intitule et dans le motif "automation engineer" ».

Aucune proposition ne s'applique seule. Validee, la famille est enregistree
comme SA decision, et elle survit aux rescorages — c'est la meme regle que
partout : le moteur peut revenir sur ses decisions, jamais sur les siennes.

Les points, eux, restent ceux de `criteres.yaml`. Une famille validee rapporte
exactement ce que rapporte la meme famille detectee par motif.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .config import Criteres, charger_criteres, normaliser

# Mots qui ne discriminent rien : ils sont dans la moitie des intitules de
# toutes les familles. Les compter ferait proposer « developpement » pour
# n'importe quel poste d'ingenieur.
VIDES = {
    "de", "du", "des", "le", "la", "les", "un", "une", "et", "en", "a", "au",
    "aux", "d", "l", "of", "in", "the", "and", "for", "with", "der", "die",
    "das", "und", "fur", "im", "zur",
    "engineer", "ingenieur", "ingenieure", "consultant", "consultante",
    "manager", "specialist", "specialiste", "responsable", "chef", "senior",
    "junior", "lead", "expert", "analyst", "analyste", "technique", "projet",
    "project", "it", "informatique", "software", "logiciel", "systeme",
    "systemes", "system", "systems", "h", "f", "m", "w", "d", "cdi", "cdd",
    # Releves sur la vraie base : « Analytical Associate in Analytical
    # DEVELOPMENT » etait propose dans la famille de l'automatisation parce que
    # « development » figure dans « software development engineer in test »,
    # et « QA ENGINEERING » dans une autre famille, par un motif qui contenait
    # « engineering ». Ces deux mots ne nomment pas un metier a eux seuls.
    "development", "developpement", "engineering",
    # Bruit de deux lettres, admis depuis qu'on descend a deux caracteres.
    "ou", "on", "to", "is", "an", "as", "at", "by", "we", "up", "no", "si",
    "ag", "sa", "gmbh", "se", "ii", "iii",
}

# Sous ce seuil, le recouvrement est du bruit. 0.8 laisse passer un mot qui
# domine nettement une famille sans y etre exclusif — « qa » etait dans cinq
# motifs d'une famille et un seul d'une autre, et « QA Engineering » restait
# sans proposition avec un seuil a 1.
CONFIANCE_MINIMALE = 0.8

_MOT = re.compile(r"[a-z0-9]+")


@dataclass
class Proposition:
    offre_id: int
    titre: str
    employeur: str
    score: float
    famille: str
    libelle: str
    confiance: float
    preuves: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"offre_id": self.offre_id, "titre": self.titre,
                "employeur": self.employeur, "score": self.score,
                "famille": self.famille, "libelle": self.libelle,
                "confiance": round(self.confiance, 2), "preuves": self.preuves}


def _mots(texte: str) -> list[str]:
    """Mots significatifs, pluriel rabattu sur le singulier.

    « tests » et « test » sont le meme mot pour un intitule de poste, et c'est
    exactement la difference qui faisait rater « automatisation de tests ».
    """
    bruts = _MOT.findall(normaliser(texte))
    sortie = []
    for mot in bruts:
        if len(mot) > 3 and mot.endswith("s"):
            mot = mot[:-1]
        # Deux caracteres suffisent : « qa » est un mot de metier, et le
        # filtre a trois lettres le jetait — « QA Engineering » n'avait alors
        # AUCUN mot significatif et ne recevait jamais de proposition.
        if len(mot) >= 2 and mot not in VIDES:
            sortie.append(mot)
    return sortie


def vocabulaire(c: Criteres | None = None) -> tuple[dict[str, dict[str, set[str]]],
                                                    Counter]:
    """({famille: {mot: motifs ou il apparait}}, nombre de familles par mot).

    Le second terme est ce qui donne son poids a un mot : un mot present dans
    une seule famille tranche, un mot present dans six ne dit rien.
    """
    c = c or charger_criteres()
    par_famille: dict[str, dict[str, set[str]]] = {}
    for cle, groupe in c.familles.items():
        index: dict[str, set[str]] = {}
        for motif in groupe.get("motifs", []):
            for mot in _mots(motif):
                index.setdefault(mot, set()).add(motif)
        par_famille[cle] = index
    # Nombre de MOTIFS, toutes familles confondues, ou le mot apparait. On
    # compte les motifs et non les familles : « qa » etait dans cinq motifs d'une
    # famille et un seul d'une autre. Compter les familles rendait ces deux-la
    # egales, et « QA Engineering » tombait sous le seuil.
    etendue: Counter = Counter()
    for index in par_famille.values():
        for mot, motifs in index.items():
            etendue[mot] += len(motifs)
    return par_famille, etendue


def proposer(offre: dict[str, Any], c: Criteres | None = None,
             vocab=None) -> Proposition | None:
    """La famille la mieux recouverte par l'intitule — ou None.

    On ne lit QUE l'intitule. Le corps d'une annonce parle de qualite, de
    tests et de donnees pour cent raisons ; l'intitule nomme le poste. C'est
    la meme regle que `_texte_des_champs` dans le scoring, et elle a deja
    evite une vague de faux positifs.
    """
    c = c or charger_criteres()
    par_famille, etendue = vocab or vocabulaire(c)

    mots_titre = set(_mots(offre.get("titre") or ""))
    if not mots_titre:
        return None

    meilleur: Proposition | None = None
    for cle, index in par_famille.items():
        confiance = 0.0
        preuves: list[str] = []
        for mot in sorted(mots_titre):
            if mot not in index:
                continue
            # Part des motifs portant ce mot qui appartiennent a CETTE
            # famille. Un mot exclusif vaut 1 ; un mot partage se dilue.
            poids = len(index[mot]) / etendue[mot]
            confiance += poids
            motif = sorted(index[mot], key=len)[0]
            preuves.append(f'« {mot} » — motif « {motif} »')
        if confiance < CONFIANCE_MINIMALE or not preuves:
            continue
        if meilleur is None or confiance > meilleur.confiance:
            meilleur = Proposition(
                offre_id=int(offre.get("id") or 0),
                titre=offre.get("titre") or "",
                employeur=offre.get("employeur") or "",
                score=float(offre.get("score") or 0),
                famille=cle,
                libelle=c.familles[cle].get("libelle", cle),
                confiance=confiance,
                preuves=preuves,
            )
    return meilleur


def proposer_pour(offres: list[dict[str, Any]],
                  c: Criteres | None = None) -> list[Proposition]:
    """Les propositions, la plus sure d'abord.

    Le vocabulaire est construit UNE fois : sur quelques centaines d'offres, le
    reconstruire a chaque appel coute plus cher que tout le reste du traitement.
    """
    c = c or charger_criteres()
    vocab = vocabulaire(c)
    sorties = [p for p in (proposer(o, c, vocab) for o in offres) if p]
    sorties.sort(key=lambda p: (-p.confiance, -p.score))
    return sorties
