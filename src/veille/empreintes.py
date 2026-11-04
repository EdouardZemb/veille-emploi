"""Le kit a-t-il bouge sans qu'on le dise ?

POURQUOI CE MODULE EXISTE. Des lettres servies par la console divergeaient
de leurs sources. L'une d'elles portait une affirmation corrigee cote kit, et
elle partait malgre tout, pendant qu'on la croyait reglee ailleurs.

Deux arborescences paralleles, aucune synchronisation, aucune alarme.

CE QUE CE CONTROLE EST, ET CE QU'IL N'EST PAS.

  - Il EST un test qui ECHOUE. Un avertissement dans un journal est encore
    de la prose, et on a etabli deux fois dans la meme journee que la prose
    ne tient pas : elle se lit une fois, puis plus jamais.
  - Il N'EST PAS un recalcul. La reference vit dans `empreintes-kit.json`, dans
    le dossier de configuration (`VEILLE_CONFIG`), a cote du code de l'instance, et pas dans le kit qu'elle surveille. Un controle qui
    relirait l'empreinte du disque surveille mesurerait sa propre copie et
    passerait toujours — il ne dirait rien, tres regulierement.

Valider un changement est donc un geste explicite : `veille empreintes-kit
--mettre-a-jour`, qui reecrit le fichier de reference. Faire taire l'alarme
oblige a ecrire qu'on l'assume.

LE KIT ABSENT N'EST PAS UNE DIVERGENCE. Sur une machine de developpement
sans kit, le controle se saute en le disant. Il ne crie que si le kit est la
ET qu'il a bouge.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DOSSIER_CONFIG, RACINE

# La reference vit avec la configuration de l'instance, pas avec le code.
REFERENCE = DOSSIER_CONFIG / "empreintes-kit.json"

# Ce qui n'est pas une piece du kit et n'a donc pas a etre fige.
IGNORES = (".provisoire", ".DS_Store", "Thumbs.db")


@dataclass
class Ecart:
    fichier: str
    nature: str          # "modifie" | "absent" | "nouveau"
    attendu: str = ""
    lu: str = ""

    def __str__(self) -> str:
        if self.nature == "modifie":
            return (f"{self.fichier} : LE KIT A BOUGE\n"
                    f"        empreinte attendue (reference figee) : {self.attendu}\n"
                    f"        empreinte lue (kit du serveur)        : {self.lu}\n"
                    f"        -> si le changement est VOULU : "
                    f"`veille empreintes-kit --mettre-a-jour`\n"
                    f"        -> sinon : redepose la bonne version dans le kit")
        if self.nature == "absent":
            return (f"{self.fichier} : DISPARU DU KIT\n"
                    f"        empreinte attendue : {self.attendu}\n"
                    f"        -> redepose-le, ou retire-le de la reference avec "
                    f"`veille empreintes-kit --mettre-a-jour`")
        return (f"{self.fichier} : NOUVEAU, pas encore fige\n"
                f"        empreinte lue : {self.lu}\n"
                f"        -> `veille empreintes-kit --mettre-a-jour` pour "
                f"l'inscrire dans la reference")


def dossier_kit() -> Path | None:
    """Le kit REEL : la variable d'environnement, sinon `config/.env`.

    On ne passe pas par `config.CHEMIN_KIT` : sous pytest, les chemins sont
    rediriges vers un dossier temporaire, et le controle mesurerait le vide.
    """
    brut = os.environ.get("VEILLE_KIT")
    if not brut:
        env = Path(os.environ.get("VEILLE_ENV") or RACINE / "config" / ".env")
        if env.exists():
            for ligne in env.read_text(encoding="utf-8").splitlines():
                if ligne.strip().startswith("VEILLE_KIT="):
                    brut = ligne.split("=", 1)[1].strip()
                    break
    if not brut:
        return None
    chemin = Path(os.path.expanduser(brut))
    return chemin if chemin.is_dir() else None


def pieces(dossier: Path) -> list[Path]:
    return sorted(f for f in dossier.iterdir()
                  if f.is_file() and f.name not in IGNORES)


def calculer(dossier: Path) -> dict[str, str]:
    """{nom: empreinte} pour tout le contenu du kit."""
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:32]
            for f in pieces(dossier)}


def lire_reference() -> dict[str, str]:
    if not REFERENCE.exists():
        return {}
    charge = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return charge.get("empreintes", {})


def ecrire_reference(empreintes: dict[str, str], note: str = "") -> None:
    REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE.write_text(json.dumps(
        {
            "_lire_dabord": (
                "Reference FIGEE des pieces du kit. Ce fichier n'est jamais "
                "recalcule par les tests : il est la pour qu'un changement du "
                "kit se voie. Si un test de parite echoue et que le changement "
                "est voulu, lance `veille empreintes-kit --mettre-a-jour` et "
                "dis dans ton message de validation ce qui a change et pourquoi."
            ),
            "note": note,
            "empreintes": dict(sorted(empreintes.items())),
        },
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def comparer(reference: dict[str, str], lu: dict[str, str]) -> list[Ecart]:
    """Les ecarts entre la reference figee et le kit sur le disque."""
    ecarts: list[Ecart] = []
    for nom, attendu in sorted(reference.items()):
        if nom not in lu:
            ecarts.append(Ecart(nom, "absent", attendu=attendu))
        elif lu[nom] != attendu:
            ecarts.append(Ecart(nom, "modifie", attendu=attendu, lu=lu[nom]))
    for nom, valeur in sorted(lu.items()):
        if nom not in reference:
            ecarts.append(Ecart(nom, "nouveau", lu=valeur))
    return ecarts


def etat() -> dict[str, Any]:
    """Pour la ligne de commande : ce qu'on sait, et ce qui diverge."""
    dossier = dossier_kit()
    if dossier is None:
        return {"kit": None, "raison": "VEILLE_KIT n'est pas definie, ou le "
                                       "dossier n'existe pas", "ecarts": []}
    lu = calculer(dossier)
    if not lu:
        return {"kit": str(dossier), "raison": "le kit est vide", "ecarts": []}
    return {"kit": str(dossier), "raison": "",
            "reference": len(lire_reference()), "lues": len(lu),
            "ecarts": comparer(lire_reference(), lu)}
