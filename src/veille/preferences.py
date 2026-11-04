"""PORT DE LECTURE vers le magasin de preferences. Rien d'autre.

⚠️ CE MODULE NE DEFINIT AUCUN MAGASIN, ET NE DOIT JAMAIS EN DEFINIR UN.

Le contrat du magasin — format, champs, domaines, provenance, dates de revue,
regles de contradiction, interface de lecture — est ecrit ailleurs, et il est
PARTAGE avec le projet Pupitre. Deux magasins concurrents seraient exactement
le defaut que ce projet combat partout ailleurs : deux arborescences
paralleles, aucune synchronisation, aucune alarme — la phrase d'ouverture
d'`empreintes.py`, qui existe parce que ca s'est produit.

CE QUE CE MODULE EST :

  - un PORT. Une seule fonction de lecture, `lire(domaine)`. Tout le reste du
    projet passe par elle et ne sait rien de l'origine des preferences.
  - une PROJECTION. `Preference` ci-dessous n'est pas un schema de stockage :
    c'est le minimum dont la veille a besoin pour travailler. Quand le contrat
    arrivera, on adapte la projection, pas les appelants.

CE QUE CE MODULE N'EST PAS :

  - il n'ECRIT jamais. ADR-3 applique aux preferences : l'agent n'ecrit jamais
    dans le magasin. Il INDUIT une regle candidate, qu'Edouard ratifie. Les
    regles candidates vivent donc du cote de la veille, dans `evenements`,
    jusqu'a ratification — voir `candidats.py`.
  - il ne stocke RIEN. Pas de fichier de preferences, pas de table, pas de
    cache sur disque. Un cache sur disque EST un deuxieme magasin.

L'INDISPONIBILITE EST UN RESULTAT, PAS UN PASSE-DROIT. Tant que le contrat
n'existe pas, `lire()` rend une liste vide et `disponible()` rend False avec sa
raison. Un controle qui depend des preferences doit alors se declarer
`indisponible` — **jamais `ok`**. C'est la distinction que
`Affinement.depassement` a du apprendre : « rien n'a ete propose » et « la
proposition a ete refusee » ne s'affichent pas pareil.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from .config import ConfigurationInvalide, charger_criteres, problemes_d_affirmations

# Les domaines dont la veille a besoin. Les noms definitifs viendront du
# contrat ; ceux-ci sont les intentions, et ils sont volontairement peu
# nombreux.
DOMAINE_AFFIRMATIONS = "affirmations_refusees"
DOMAINE_STYLE = "style_redaction"
DOMAINE_CANDIDATURE = "candidature"

DOMAINES = (DOMAINE_AFFIRMATIONS, DOMAINE_STYLE, DOMAINE_CANDIDATURE)


@dataclass
class Preference:
    """PROJECTION de lecture, pas un schema de stockage.

    Quatre champs, parce que ce sont les quatre dont la veille a besoin pour
    afficher un refus qu'il puisse verifier en trois secondes :

      domaine    : a quoi ca s'applique
      valeur     : le contenu, dont la forme depend du domaine
      provenance : d'ou ca vient, pour qu'il puisse remonter a la decision
      revue_le   : quand il l'a revue pour la derniere fois. Une preference
                   jamais revue n'est pas fausse, mais elle vieillit : ce qui
                   etait « en cours » le mois dernier peut etre devenu faux.
    """

    domaine: str
    valeur: Any
    provenance: str = ""
    revue_le: str = ""
    # Motifs de recherche, quand le domaine en comporte. Pour les affirmations
    # refusees, c'est ce qui rend le controle DETERMINISTE.
    motifs: list[str] = field(default_factory=list)
    libelle: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"domaine": self.domaine, "valeur": self.valeur,
                "provenance": self.provenance, "revue_le": self.revue_le,
                "motifs": self.motifs, "libelle": self.libelle}


@dataclass
class Disponibilite:
    possible: bool
    raison: str = ""


def disponible() -> Disponibilite:
    """Le magasin est-il lisible ? Sinon on le DIT, sans erreur obscure.

    Meme forme que `affinement.disponible()` et `exigences`, pour que l'ecran
    traite les trois pareil.
    """
    chemin = os.environ.get("VEILLE_PREFERENCES", "").strip()
    if not chemin:
        return Disponibilite(False, (
            "Le magasin de préférences n'est pas branché : son contrat est en "
            "cours d'écriture, et il est partagé avec Pupitre. La veille ne "
            "stocke aucune préférence de son côté — ce serait un second "
            "magasin. Les contrôles qui en dépendent se déclarent "
            "« indisponibles », jamais « au vert »."))
    return Disponibilite(False, (
        f"VEILLE_PREFERENCES est posé sur {chemin}, mais aucun lecteur n'est "
        f"encore écrit : le contrat du magasin n'est pas arrêté. Dès qu'il "
        f"l'est, seul ce module change."))


def lire(domaine: str) -> list[Preference]:
    """Les preferences d'un domaine. Liste vide si le magasin est absent.

    LA LISTE VIDE N'EST PAS UNE AUTORISATION. L'appelant doit regarder
    `disponible()` avant de conclure quoi que ce soit : une liste vide parce
    qu'il n'a rien interdit et une liste vide parce que le magasin n'est pas
    branche sont deux situations opposees, et les confondre est exactement ce
    qui a produit de nombreuses offres dans le mauvais pays.
    """
    if domaine not in DOMAINES:
        raise ValueError(
            f"domaine inconnu : {domaine!r}. Un domaine que personne ne lit ne "
            f"fait RIEN — meme regle que verifier_environnement(). "
            f"Domaines connus : {', '.join(DOMAINES)}")
    if not disponible().possible:
        return []
    return []  # pragma: no cover - sera le lecteur du contrat


# --------------------------------------------------------------------------
# Le repli provisoire : la configuration, en attendant le magasin
# --------------------------------------------------------------------------
#
# ⚠️ À RETIRER DES QUE LE CONTRAT DU MAGASIN EXISTE. Ce n'est PAS un magasin :
# aucune ecriture, pas de date de revue a tenir. C'est la cle
# `affirmations_refusees` de `criteres.yaml`, une liste de tables
# `{libelle, valeur, provenance, motifs}`, dont la seule raison d'exister est que
# le controle le plus rentable de la porte puisse tourner aujourd'hui.
#
# CE QU'ELLE PORTE A TOUJOURS LA MEME FORME : une affirmation fausse qui SURVIT
# A SA PROPRE CORRECTION. Corrigee dans le kit, elle ressort d'un gabarit, d'une
# copie, d'une proposition de l'affinement. La relecture ne la rattrape pas ; un
# motif, cherche mot pour mot, la rattrape a chaque fois. Les regles disent des
# faits de la vie d'une personne : elles vivent dans sa configuration, jamais
# dans le code.
#
# Tant que ce repli sert, `disponible()` rend False : l'ecran dit donc que le
# magasin n'est pas branche, ET le controle tourne quand meme. On ne fait pas
# passer une configuration pour un magasin : l'origine reste « repli ».


def _affirmations_de_la_configuration() -> list[Preference]:
    """Les regles de `affirmations_refusees`. Cle absente : aucune regle.

    TOUT OU RIEN. Une entree mal formee rend la liste entiere inutilisable :
    verifier une partie des regles et dire `ok` serait un vert sans verification.
    La liste vide fait se declarer le controle `indisponible`, et
    `veille config verifier` nomme l'entree fautive.

    UN FICHIER ILLISIBLE NE FAIT PAS TOMBER LA PORTE. Lecture impossible, YAML
    tronque, version inconnue : le controle des affirmations n'a pas pu tourner,
    il se declare `indisponible`, et les autres controles tournent. Ailleurs, le
    chargement leve toujours.
    """
    try:
        brut = charger_criteres().brut
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ConfigurationInvalide):
        return []
    if "affirmations_refusees" not in brut or problemes_d_affirmations(brut):
        return []
    return [
        Preference(domaine=DOMAINE_AFFIRMATIONS,
                   libelle=regle.get("libelle", ""),
                   valeur=regle.get("valeur", ""),
                   provenance=regle.get("provenance", ""),
                   motifs=list(regle["motifs"]))
        for regle in brut["affirmations_refusees"]
    ]


def affirmations_refusees() -> tuple[list[Preference], str]:
    """(liste, origine). `origine` vaut "magasin" ou "repli".

    L'ORIGINE VOYAGE AVEC LA LISTE, pour que l'ecran puisse dire d'ou vient un
    refus. Une interdiction qu'il ne peut pas remonter a une decision est une
    interdiction qu'il contournera.
    """
    if disponible().possible:
        return lire(DOMAINE_AFFIRMATIONS), "magasin"
    return _affirmations_de_la_configuration(), "repli"
