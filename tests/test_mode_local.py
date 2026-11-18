"""La source ne parle plus du mode systemd (la fin du mode systemd, veille-emploi#34).

Sans `VEILLE_EMPLOI_ENV`, la console est en mode local : celui du poste, des tests et du test de
restauration du modele. Le mode d'avant, une console servie par des unites systemd dans un clone
du serveur, est retire. Ses mots ne reviennent ni dans le code, ni dans ce qu'il affiche, ni dans
l'exemple qu'on recopie : un message qui renverrait a une commande retiree, a un fichier qui n'est
plus lu ou a une unite qui n'existe plus enverrait Edouard sur un geste mort.

Le garde lit chaque fichier `.py`, `.js`, `.html` ou `.css` de `src/veille/`, et chaque fichier de
`exemple/`. Un motif se cherche sans egard a la casse, et deux mots se suivent a travers tout ce
qui n'est pas une lettre, un chiffre ou `_` : un retour a la ligne, un `#` ou un `//` ne coupent
pas « sans conteneur ». Un identifiant, comme `sans_conteneur`, ne compte pas ; une unite ne
compte qu'avec son suffixe, si bien que le fil `veille-collecte` du planificateur reste.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "src" / "veille"
EXEMPLE = RACINE / "exemple"
EXTENSIONS = {".py", ".js", ".html", ".css"}

# Le chemin du fichier d'environnement s'ecrit en deux morceaux, ici et dans les cas plus
# bas : `tests/test_frontiere.py` refuse un test qui le porte d'un bloc, qu'il prend pour le
# chemin du fichier de la console.
MOTS_RETIRES = (
    r"systemctl",
    r"systemd",
    r"EnvironmentFile",
    r"config/" + r"\.env",
    r"config/vapid\.json",
    r"veille\W+init\b",
    r"sans\W+conteneur",
    r"tailnet",
    r"tailscale",
    r"veille-web\.service",
    r"veille-collecte\.(?:timer|service)",
    r"veille-verification\.(?:timer|service)",
)

_MOTIF = re.compile("|".join(f"(?:{m})" for m in MOTS_RETIRES), re.IGNORECASE)


def _occurrences(texte: str) -> list[tuple[int, str]]:
    """Chaque mot retire, avec le numero de la ligne ou il commence."""
    return [(texte.count("\n", 0, m.start()) + 1, m.group(0)) for m in _MOTIF.finditer(texte)]


def trouver(texte: str) -> list[str]:
    """Les mots du mode retire que porte ce texte, dans l'ordre."""
    return [mot for _, mot in _occurrences(texte)]


def _fichiers_gardes() -> list[Path]:
    source = [f for f in SOURCE.rglob("*") if f.is_file() and f.suffix in EXTENSIONS]
    exemple = [f for f in EXEMPLE.rglob("*") if f.is_file()]
    return sorted(source + exemple)


def test_la_source_ne_parle_plus_du_mode_systemd():
    fichiers = _fichiers_gardes()
    lus = {f.relative_to(RACINE).as_posix() for f in fichiers}
    # Un garde qui ne lit rien passe toujours : il doit au moins lire ces trois-la.
    for attendu in ("src/veille/static/app.js", "src/veille/templates/index.html",
                    "exemple/.env.exemple"):
        assert attendu in lus, f"le garde ne lit pas {attendu}"
    lieux = []
    for fichier in fichiers:
        texte = fichier.read_text(encoding="utf-8")
        if trouver(texte) == []:
            continue
        nom = fichier.relative_to(RACINE).as_posix()
        lieux += [f"{nom}:{ligne} : {mot!r}" for ligne, mot in _occurrences(texte)]
    assert lieux == [], "la source parle encore du mode systemd :\n  " + "\n  ".join(lieux)


@pytest.mark.parametrize("texte", [
    "systemctl --user",
    "le minuteur\n  SystemD",
    "EnvironmentFile=-x",
    "lu dans config/" + ".env",
    "config/vapid.json",
    "// veille\n// init",
    "# sans\n# conteneur",
    "le Tailnet",
    "tailscale serve",
    "veille-web.service",
    "veille-collecte.timer",
    "veille-collecte.service",
    "veille-verification.timer",
    "veille-verification.service",
])
def test_le_garde_trouve_chaque_motif(texte):
    assert trouver(texte), f"le garde ne trouve pas {texte!r}"


@pytest.mark.parametrize("texte", [
    "sans_conteneur",
    "veille_init",
    "la veille initialise la base",
    'name="veille-collecte"',
])
def test_le_garde_laisse_ce_qui_ne_parle_pas_du_mode(texte):
    assert trouver(texte) == []
