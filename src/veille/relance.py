"""Le mot de relance — petit, et c'est le geste qu'on ne fait jamais.

MEME REGLE QUE LE RESTE : ce module n'ecrit aucune prose. Il prend un gabarit
— `gabarits/relance.md` du dossier de configuration, ou `relance_en.md`, ou celui du kit s'il en depose un
— et il remplace des marqueurs par des faits enregistres : l'employeur, le
poste, la date d'envoi, le nombre de jours ecoules, le canal utilise.

Ce qui fait la valeur d'une relance, c'est qu'elle rappelle le bon poste a la
bonne date. Ce sont precisement les deux choses que la base sait et que lui a
oubliees trois semaines plus tard.

CE QU'IL FAUT NE PAS FAIRE : relancer une offre dont le texte a disparu, ou
relancer deux fois. Les deux sont signales, ils ne sont pas bloques — c'est sa
decision, et il peut avoir une raison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import CHEMIN_GABARITS, CHEMIN_KIT

# En-deca, ce n'est pas une relance, c'est de l'impatience. Au-dela de 45
# jours, le recrutement est souvent clos et la relance se transforme en
# candidature spontanee — ce n'est plus le meme texte.
DELAI_RAISONNABLE = 10
DELAI_TARDIF = 45

_RE_MARQUEUR = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


@dataclass
class Relance:
    texte: str = ""
    objet: str = ""
    gabarit: str = ""
    jours: int = 0
    avertissements: list[str] = field(default_factory=list)
    marqueurs_restants: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"texte": self.texte, "objet": self.objet,
                "gabarit": self.gabarit, "jours": self.jours,
                "avertissements": self.avertissements,
                "marqueurs_restants": self.marqueurs_restants}


def _jour(valeur: str | None) -> date | None:
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(str(valeur)[:19]).date()
    except ValueError:
        try:
            return date.fromisoformat(str(valeur)[:10])
        except ValueError:
            return None


def _langue(offre: dict[str, Any]) -> str:
    from .dossier import detecter_langue

    try:
        return detecter_langue(offre)
    except Exception:
        return "fr"


def gabarit_pour(offre: dict[str, Any]) -> Path | None:
    """Le gabarit de relance : celui du kit d'abord, celui du depot ensuite.

    Ordre identique a celui de la lettre : `relance_<langue>.md`, puis
    `relance.md`. S'il en depose un dans son kit, c'est le sien qui sert.
    """
    langue = _langue(offre)
    # Une langue indeterminee ou non servie ne doit pas retomber sur le
    # francais : c'est le defaut qui faisait partir une lettre francaise a un
    # recruteur germanophone. Meme regle ici que pour la lettre.
    from .dossier import LANGUES_SERVIES

    if langue not in LANGUES_SERVIES:
        return None
    noms = [f"relance_{langue}.md", "relance.md"]
    for dossier in (CHEMIN_KIT, CHEMIN_GABARITS):
        for nom in noms:
            chemin = dossier / nom
            if chemin.exists():
                return chemin
    return None


def _corps_du_gabarit(brut: str) -> str:
    """Ce qui suit la premiere ligne `---` seule, sinon tout le fichier.

    Un gabarit commence par sa propre notice — la liste des marqueurs, ce
    qu'il faut en faire. Sans cette coupe, la notice partait au recruteur,
    marqueurs remplaces, ce qui donnait : « Marqueurs : `Exemple Logistik AG`
    `Testeur logiciel` ». Un gabarit sans separateur reste pris en entier : on ne coupe
    jamais un texte qui n'a pas demande a l'etre.
    """
    lignes = brut.splitlines()
    for i, ligne in enumerate(lignes):
        if ligne.strip() == "---":
            return "\n".join(lignes[i + 1:]).strip("\n")
    return brut


def preparer(offre: dict[str, Any], aujourdhui: date | None = None) -> Relance:
    """Le mot de relance pour cette candidature."""
    aujourdhui = aujourdhui or date.today()
    r = Relance()

    envoyee = _jour(offre.get("date_candidature"))
    if not envoyee:
        r.avertissements.append(
            "Aucune date d'envoi enregistree : la relance ne peut pas dire "
            "depuis quand tu attends. Renseigne la date de candidature.")
    else:
        r.jours = (aujourdhui - envoyee).days
        if r.jours < DELAI_RAISONNABLE:
            r.avertissements.append(
                f"Envoyee il y a {r.jours} jour(s). En dessous de "
                f"{DELAI_RAISONNABLE} jours, une relance passe pour de "
                f"l'impatience — sauf si l'annonce annoncait une reponse rapide.")
        elif r.jours > DELAI_TARDIF:
            r.avertissements.append(
                f"Envoyee il y a {r.jours} jours. Au-dela de {DELAI_TARDIF} "
                f"jours le poste est souvent pourvu : relis le texte avant de "
                f"l'envoyer, il parle d'une candidature encore en cours.")

    if (offre.get("statut") or "") == "relance_envoyee":
        r.avertissements.append(
            "Tu as deja relance cette offre une fois. Une seconde relance se "
            "fait, mais elle se voit : verifie que tu as quelque chose de "
            "nouveau a dire.")
    if offre.get("archivee_le"):
        r.avertissements.append(
            "Cette annonce est archivee : la verification l'a trouvee retiree "
            "de son site. Relancer reste possible — une annonce retiree veut "
            "souvent dire que le recrutement avance.")

    chemin = gabarit_pour(offre)
    if chemin is None:
        from .dossier import LANGUES_SERVIES, detecter_langue, langue_lisible

        langue = detecter_langue(offre)
        if langue not in LANGUES_SERVIES:
            r.avertissements.append(
                f"Langue de l'annonce : {langue_lisible(langue)}. Aucune "
                f"relance n'a ete redigee — une relance dans la mauvaise "
                f"langue se remarque autant qu'une lettre.")
        else:
            r.avertissements.append(
                "Aucun gabarit de relance trouve. Depose `relance.md` dans ton kit.")
        return r
    r.gabarit = chemin.name

    valeurs = {
        "employeur": (offre.get("employeur") or "").strip() or "Madame, Monsieur",
        "titre": (offre.get("titre") or "").strip(),
        "lieu": (offre.get("lieu") or "").strip(),
        "contact": (offre.get("contact_nom") or "").strip(),
        "contact_civilite": (offre.get("contact_civilite") or "").strip(),
        "date_candidature": envoyee.strftime("%d/%m/%Y") if envoyee else "",
        "jours": str(r.jours) if envoyee else "",
        "canal": (offre.get("canal_candidature") or "").strip(),
        "date": aujourdhui.strftime("%d/%m/%Y"),
    }
    brut = _corps_du_gabarit(chemin.read_text(encoding="utf-8"))
    r.texte = _RE_MARQUEUR.sub(
        lambda m: valeurs.get(m.group(1)) or f"[[{m.group(1)} - À COMPLÉTER]]", brut)
    r.marqueurs_restants = sorted(set(re.findall(r"\[\[([^\]]+)\]\]", r.texte)))

    premiere = next((l.strip() for l in r.texte.splitlines()
                     if l.strip().lower().startswith(("objet", "subject"))), "")
    if premiere:
        r.objet = premiere.split(":", 1)[-1].strip()
        r.texte = "\n".join(l for l in r.texte.splitlines() if l.strip() != premiere)
    return r
