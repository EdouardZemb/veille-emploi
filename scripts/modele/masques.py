"""Porte « fichiers masqués » : refuse un commit qui aligne ou met à jour le projet quand son
.gitignore masque un fichier que le modèle écrit, ou un secret chiffré que la chaîne lit.

Un fichier géré masqué par le .gitignore n'est pas indexé : la mise à jour du modèle l'écrit sur
le disque, mais il n'entre jamais dans un commit (LE-23). La porte ne s'applique qu'à un commit qui
touche `.copier-answers.yml` (indexé, ou présent sans être suivi). Elle examine ce que le modèle
écrit pour la cible déclarée (`chemins_examines`) : les chemins communs ; en cible `serveur` (une
cible illisible vaut `serveur`), ceux de `deploiement/`, ses fichiers de premier niveau par leur
nom, et, à un dépôt (nature `donnees`, ou illisible), l'instance et ses secrets chiffrés ; en cible
`donnees`, ses deux README.md et, sauf `cible_code: aucune`, l'instance et ses secrets chiffrés. Un
motif (`cles/*.pub`) ne vaut qu'au premier niveau de son dossier.

Le principe du remède : il n'admet que ce que la porte examine, toujours par des lignes ancrées.
Un dossier exclu qu'elle examine en entier, un dossier du modèle comme `scripts/modele/`, se lève
par `!/<dossier>/`. Un dossier mixte, où un fichier local peut vivre à côté d'un fichier examiné
(`cles/`, `env/`, `secrets/`, `deploiement/`…), se lève, en exclut le contenu, puis n'admet que ce
qu'elle y examine : `!/cles/`, `/cles/*`, `!/cles/*.pub`. Un ancêtre exclu se lève de même, suivi
des lignes de ses dossiers. Un fichier masqué hors d'un dossier exclu se lève par `!/<fichier>`.
Sous un .gitignore imbriqué, les lignes partent de son dossier, comme git les y lit. Un chemin cité
s'échappe : ses `[`, `*`, `?` et barres obliques inverses ne se lisent pas comme un motif.

Ce que la porte n'examine pas reste donc masqué, sans refus : dans un dossier mixte, un secret en
clair, une clé privée ou un fichier local ; sous un ancêtre levé, un semé du projet
(`docs/cadrage.md` sous `docs/`), que `docs/aligner.md` fait vérifier à la main. Sous un dossier du
modèle, tout fichier est du modèle, sauf un dossier de secrets ou de clés imbriqué, quelle que soit
sa casse, ou un cache Python, que le remède ré-exclut par son chemin.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : masques.py [--racine DOSSIER]  (--racine sert aux tests ; sinon la racine du dépôt courant)

Retour : 0 rien à signaler, 1 refus (fichier masqué, ou git en échec), 64 erreur d'usage.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

EXIT_USAGE = 64
REPONSES = ".copier-answers.yml"
# Un chemin qui finit par `/` est un dossier du modèle, examiné en entier ; un autre est un fichier,
# ou un motif de premier niveau, et son dossier est mixte : le remède n'y admet que lui.
CHEMINS_COMMUNS: tuple[str, ...] = (
    ".githooks/",
    "scripts/modele/",
    "docs/modele/",
    ".github/modele/",
    ".github/workflows/modele-*.yml",
    ".github/ISSUE_TEMPLATE/lot.yml",
    ".github/pull_request_template.md",
    ".claude/skills/consigner/",
    ".claude/settings.json",
    ".copier-answers.yml",
)
# La cible `serveur`. `deploiement/` est mixte : un projet y garde ses fichiers à côté de ceux du
# modèle. La porte n'y examine que ce que le modèle y écrit, ses fichiers de premier niveau par
# leur nom, et, sous `secrets/`, que ce que la chaîne y lit.
CHEMINS_SERVEUR: tuple[str, ...] = (
    "deploiement/alerter.sh",
    "deploiement/deployer.sh",
    "deploiement/installer-unites.sh",
    "deploiement/lib.sh",
    "deploiement/nettoyer-images.sh",
    "deploiement/sonder.sh",
    "deploiement/restaurer.sh",
    "deploiement/sauvegarder.sh",
    "deploiement/tester-restauration.sh",
    "deploiement/compose.yml",
    "deploiement/compose.config.yml",
    "deploiement/compose.contenu.yml",
    "deploiement/compose.projet.yml",
    "deploiement/projet.env",
    "deploiement/ci/",
    "deploiement/systemd/",
    "deploiement/secrets/*.cles",
    "tests/deploiement/",
    ".github/actions/modele-image-construire/",
    ".github/actions/modele-image-publier/",
)
# L'instance d'un projet `serveur` à un dépôt (nature `donnees`), et les secrets chiffrés que sa
# chaîne lit. Un dépôt de code n'en a rien : son instance vit dans `<nom>-donnees` (M-0006, § 3).
CHEMINS_SERVEUR_A_UN_DEPOT: tuple[str, ...] = (
    "deploiement/env/prod.env",
    "deploiement/env/staging.env",
    "deploiement/cles/*.pub",
    "deploiement/secrets/*.env.enc",
    ".sops.yaml",
)
# Un dépôt de données (cible `donnees`) : ses deux README.md, semés. Le reste de `config/` et de
# `contenu/` est au projet.
CHEMINS_DONNEES: tuple[str, ...] = (
    "config/README.md",
    "contenu/README.md",
)
# L'instance d'un projet `serveur` dans son dépôt de données (sauf `cible_code: aucune`) : ce que
# le modèle y sème, et les secrets chiffrés que la chaîne y lit.
CHEMINS_INSTANCE: tuple[str, ...] = (
    ".sops.yaml",
    "env/prod.env",
    "env/staging.env",
    "cles/*.pub",
    "secrets/*.env.enc",
)
# Les secrets chiffrés que la chaîne lit : ils ne sont pas du modèle, mais doivent entrer.
SECRETS_CHIFFRES: tuple[str, ...] = ("secrets/*.env.enc", "deploiement/secrets/*.env.enc")
# Sous un dossier du modèle, un dossier de ce nom n'est pas à la porte : des secrets, des clés.
DOSSIERS_HORS_DE_LA_PORTE: tuple[str, ...] = ("*secret*", "cles")
LIGNE_CIBLE = re.compile(r"^cible:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
LIGNE_CIBLE_CODE = re.compile(r"^cible_code:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
LIGNE_NATURE = re.compile(r"^nature:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
# Ce qu'un motif du .gitignore lit autrement que tel quel, dans un chemin cité par un remède.
CARACTERES_DE_MOTIF = re.compile(r"([\\\[*?])")
SOURCE_HORS_DU_DEPOT = re.compile(r"^([A-Za-z]:|~|\.\./)")
AUTRE_REMEDE = (
    "Si ce fichier n'est ni du modèle ni un secret chiffré que la chaîne lit (un fichier local), "
    "le sortir de ce dossier ; ne jamais lever le masque d'un secret en clair."
)
RENVOI = "Voir docs/modele/methode.md, « Les garde-fous »."


class ErreurGit(Exception):
    """Une commande git a échoué ou n'a pas pu être lancée."""


def _git(racine: Path, *args: str, entree: bytes | None = None) -> subprocess.CompletedProcess:
    """Lance git dans `racine` ; la sortie est lue en octets. Un échec de lancement lève ErreurGit."""
    try:
        return subprocess.run(
            ["git", *args],
            check=False,
            cwd=racine,
            capture_output=True,
            stdin=subprocess.DEVNULL if entree is None else None,
            input=entree,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise ErreurGit(f"git {' '.join(args)} : {e}") from e


def _git_ok(
    racine: Path, *args: str, entree: bytes | None = None, codes: tuple[int, ...] = (0,)
) -> str:
    """La sortie (UTF-8) d'une commande git qui doit rendre l'un des `codes` ; sinon ErreurGit."""
    r = _git(racine, *args, entree=entree)
    if r.returncode not in codes:
        erreur = r.stderr.decode("utf-8", errors="replace").strip()
        raise ErreurGit(f"git {' '.join(args)} : {erreur}")
    return r.stdout.decode("utf-8", errors="replace")


def racine_du_depot(cwd: Path) -> Path:
    return Path(_git_ok(cwd, "rev-parse", "--show-toplevel").strip())


def declenche(racine: Path) -> bool:
    """Vrai si le commit touche les réponses du modèle : indexées, ou présentes sans être suivies."""
    if _git_ok(racine, "diff", "--cached", "--name-only", "--", REPONSES).strip():
        return True
    if not (racine / REPONSES).exists():
        return False
    return _git(racine, "ls-files", "--error-unmatch", "--", REPONSES).returncode != 0


def _reponse(texte: str, ligne: re.Pattern[str]) -> str | None:
    """La valeur d'une réponse de premier niveau, sans ses guillemets ; None si elle est absente."""
    m = ligne.search(texte)
    return None if m is None else m.group(1).strip("'\"")


def chemins_examines(racine: Path) -> tuple[str, ...]:
    """Les chemins à examiner, selon la cible que déclarent les réponses.

    Toujours les chemins communs. En cible `serveur`, ou si la cible est illisible, ceux de la
    cible `serveur`, et l'instance à un dépôt sauf si `nature` vaut `code` : une nature illisible
    vaut `donnees`. En cible `donnees`, les deux README.md, et l'instance sauf si `cible_code`
    vaut `aucune` : une `cible_code` illisible vaut `serveur`."""
    try:
        texte = (racine / REPONSES).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return CHEMINS_COMMUNS + CHEMINS_SERVEUR + CHEMINS_SERVEUR_A_UN_DEPOT
    cible = _reponse(texte, LIGNE_CIBLE)
    if cible is None or cible == "serveur":
        instance = () if _reponse(texte, LIGNE_NATURE) == "code" else CHEMINS_SERVEUR_A_UN_DEPOT
        return CHEMINS_COMMUNS + CHEMINS_SERVEUR + instance
    if cible == "donnees":
        instance = () if _reponse(texte, LIGNE_CIBLE_CODE) == "aucune" else CHEMINS_INSTANCE
        return CHEMINS_COMMUNS + CHEMINS_DONNEES + instance
    return CHEMINS_COMMUNS


def _masques_sous(racine: Path, chemins: tuple[str, ...]) -> list[str]:
    """Les fichiers présents sur le disque, sous les `chemins`, que le .gitignore masque.

    `--glob-pathspecs` : un `*` ne franchit pas un `/`, comme dans un .gitignore. Sans lui,
    `secrets/*.env.enc` prendrait aussi `secrets/sous/x.env.enc`. Un dossier vaut toujours pour ce
    qu'il contient."""
    sortie = _git_ok(
        racine,
        "--glob-pathspecs",
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
        "--",
        *chemins,
    )
    return [n for n in sortie.split("\0") if n]


def hors_de_la_porte(chemin: str, chemins: tuple[str, ...]) -> str | None:
    """Ce que la porte n'examine pas sous ses `chemins` : un cache Python, ou, sous un dossier du
    modèle, un dossier de secrets ou de clés imbriqué (`DOSSIERS_HORS_DE_LA_PORTE`), quelle que soit
    sa casse : sous Windows, `core.ignorecase` fait masquer `Secrets/` par `*secret*`. Rend ce qu'un
    remède en ré-exclut (le dossier, comme `…/secrets/`, ou le fichier `.pyc`), sinon None."""
    parties = chemin.split("/")
    if "__pycache__" in parties[:-1]:
        return "/".join(parties[: parties.index("__pycache__") + 1]) + "/"
    if chemin.endswith(".pyc"):
        return chemin
    dossier = next((c for c in chemins if c.endswith("/") and chemin.startswith(c)), None)
    if dossier is None:
        return None
    sous = chemin[len(dossier) :].split("/")[:-1]
    for i, nom in enumerate(sous):
        if any(fnmatch.fnmatchcase(nom.lower(), motif) for motif in DOSSIERS_HORS_DE_LA_PORTE):
            return dossier + "/".join(sous[: i + 1]) + "/"
    return None


def fichiers_masques(racine: Path, chemins: tuple[str, ...]) -> list[str]:
    """Les fichiers examinés, présents sur le disque, que le .gitignore masque, triés."""
    return sorted(n for n in _masques_sous(racine, chemins) if hors_de_la_porte(n, chemins) is None)


def regles(racine: Path, chemins: list[str]) -> dict[str, tuple[str, str, str]]:
    """Pour chaque chemin masqué, la règle qui le masque : (source, ligne, motif). Un seul appel à
    `git check-ignore` ; -z n'existe qu'avec --stdin, et rend quatre champs par chemin."""
    if not chemins:
        return {}
    entree = b"".join(c.encode("utf-8") + b"\0" for c in chemins)
    sortie = _git_ok(racine, "check-ignore", "-v", "-z", "--stdin", entree=entree, codes=(0, 1))
    champs = sortie.split("\0")
    return {
        champs[i + 3]: (champs[i], champs[i + 1], champs[i + 2])
        for i in range(0, len(champs) - 3, 4)
    }


def _parents(chemin: str) -> list[str]:
    """Les dossiers qui contiennent `chemin`, de la racine vers lui : `a/`, `a/b/`."""
    parties = chemin.split("/")[:-1]
    return ["/".join(parties[: i + 1]) + "/" for i in range(len(parties))]


def dossiers_exclus(racine: Path, chemins: list[str]) -> dict[str, str]:
    """Pour chaque chemin sous un dossier que git exclut, le plus haut de ces dossiers (`a/b/`).

    Une exception `!/<chemin>` ne lève pas un tel masque : git ne regarde pas dans un dossier exclu.
    Un seul appel à `git check-ignore`, pour tous les dossiers. Il passe `--no-index` : sans lui,
    un dossier qui contient déjà un fichier suivi compte comme suivi, et git ne le dit pas exclu.
    Les dossiers lui passent sans leur `/` final : git compare `env/*` à `env/` et l'y trouve, alors
    que ce motif n'exclut que le contenu. Ils existent, puisqu'ils contiennent un fichier listé, et
    git y reconnaît encore un motif de dossier (`env/`)."""
    dossiers = list(dict.fromkeys(d for chemin in chemins for d in _parents(chemin)))
    if not dossiers:
        return {}
    entree = b"".join(d.rstrip("/").encode("utf-8") + b"\0" for d in dossiers)
    sortie = _git_ok(
        racine, "check-ignore", "--no-index", "-z", "--stdin", entree=entree, codes=(0, 1)
    )
    exclus = {d + "/" for d in sortie.split("\0") if d}
    resultat = {}
    for chemin in chemins:
        haut = next((d for d in _parents(chemin) if d in exclus), None)
        if haut is not None:
            resultat[chemin] = haut
    return resultat


def echapper(chemin: str) -> str:
    """Un chemin cité tel quel dans un .gitignore : ses caractères de motif s'échappent."""
    return CARACTERES_DE_MOTIF.sub(r"\\\1", chemin)


def exceptions(dossier: str, chemins: tuple[str, ...]) -> list[str]:
    """Les lignes qui lèvent le dossier exclu `dossier`, ancrées à la racine, dans leur ordre :
    elles n'admettent que ce que la porte y examine.

    Un dossier du modèle, ou un dossier qu'il contient, se lève par `!/<dossier>/`. Tout autre
    dossier est mixte, ou l'ancêtre d'un chemin examiné : il se lève, son contenu s'exclut, puis
    chaque chemin examiné qu'il contient s'admet, un sous-dossier par ses propres lignes. Le
    chemin du dossier s'échappe ; ce qui vient des chemins examinés garde ses motifs."""
    cite = echapper(dossier)
    if any(c.endswith("/") and dossier.startswith(c) for c in chemins):
        return [f"!/{cite}"]
    lignes = [f"!/{cite}", f"/{cite}*"]
    enfants: list[str] = []
    for chemin in chemins:
        if chemin.startswith(dossier) and chemin != dossier:
            reste = chemin[len(dossier) :]
            enfant = reste.split("/", 1)[0] + ("/" if "/" in reste else "")
            if enfant not in enfants:
                enfants.append(enfant)
    for enfant in enfants:
        if enfant.endswith("/"):
            lignes += exceptions(dossier + enfant, chemins)
        else:
            lignes.append(f"!/{cite}{enfant}")
    return lignes


def a_poser(
    chemin: str, dossier: str | None, chemins: tuple[str, ...], hors: list[str]
) -> list[str]:
    """Les lignes du remède, ancrées à la racine : l'exception du fichier, ou celles du dossier
    exclu, suivies de ce qu'elles lèveraient sans que la porte l'examine, ré-exclu par son chemin."""
    if dossier is None:
        return [f"!/{echapper(chemin)}"]
    return [
        *exceptions(dossier, chemins),
        *(f"/{echapper(h)}" for h in hors if h.startswith(dossier)),
    ]


def dossier_de_la_regle(source: str) -> str:
    """Le dossier d'un .gitignore imbriqué qui porte la règle (`secrets/`) ; "" pour celui de la
    racine, `.git/info/exclude` ou un fichier d'exclusion hors du dépôt, lus depuis la racine."""
    p = PurePosixPath(source)
    if p.name != ".gitignore" or p.is_absolute() or SOURCE_HORS_DU_DEPOT.match(source):
        return ""
    parent = p.parent.as_posix()
    return "" if parent == "." else f"{parent}/"


def relative(ligne: str, base: str) -> str:
    """Une ligne ancrée à la racine, récrite pour le .gitignore du dossier `base` : sans ce
    préfixe, échappé comme la ligne, avec le `/` de tête."""
    signe = "!" if ligne.startswith("!") else ""
    chemin = ligne[len(signe) + 1 :]
    prefixe = echapper(base)
    return f"{signe}/{chemin[len(prefixe) :]}" if base and chemin.startswith(prefixe) else ligne


def remede(lignes: list[str], fichier: bool, base: str = "") -> str:
    """Le remède à poser dans le fichier qui porte la règle : ses lignes, dans leur ordre."""
    cites = [f"`{relative(ligne, base)}`" for ligne in lignes]
    ou = f" (ses lignes partent de son dossier, `{base}`)" if base else ""
    if len(cites) == 1:
        suite = "puis l'indexer" if fichier else "puis indexer le fichier"
        return f"Ajouter {cites[0]} à ce fichier{ou}, {suite}."
    return (
        f"Ajouter à la fin de ce fichier {', '.join(cites[:-1])} et {cites[-1]}, dans cet "
        f"ordre{ou}, puis indexer le fichier : ces lignes n'admettent que ce que la porte "
        f"examine, et {cites[0]} seul ferait entrer tout le dossier."
    )


def secret_chiffre(chemin: str) -> bool:
    """Vrai si `chemin` est un secret chiffré que la chaîne lit (`SECRETS_CHIFFRES`)."""
    return any(
        chemin.count("/") == motif.count("/") and fnmatch.fnmatchcase(chemin, motif)
        for motif in SECRETS_CHIFFRES
    )


def constat(chemin: str) -> str:
    """Ce qu'est le fichier masqué, pour le message de refus."""
    if secret_chiffre(chemin):
        return "secret chiffré que la chaîne lit, masqué par le .gitignore"
    return "fichier du modèle masqué par le .gitignore"


def refus(racine: Path) -> list[str]:
    """Une ligne de refus par fichier examiné que le .gitignore masque, avec son remède."""
    chemins = chemins_examines(racine)
    sous = _masques_sous(racine, chemins)
    masques = sorted(n for n in sous if hors_de_la_porte(n, chemins) is None)
    hors = sorted({h for n in sous if (h := hors_de_la_porte(n, chemins)) is not None})
    dossiers = dossiers_exclus(racine, masques)
    leurs_regles = regles(racine, masques)
    lignes = []
    for chemin in masques:
        source, numero, motif = leurs_regles.get(chemin, ("", "", ""))
        texte = f"{source}:{numero}:{motif}" if source else "règle inconnue"
        dossier = dossiers.get(chemin)
        lignes.append(
            f"modele-projet : refusé — {constat(chemin)} : {chemin} (règle {texte}). "
            + remede(
                a_poser(chemin, dossier, chemins, hors),
                dossier is None,
                dossier_de_la_regle(source),
            )
        )
    return lignes


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):
        self.exit(EXIT_USAGE, "masques : usage invalide (voir --help)\n")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(
        prog="masques.py",
        description="Refuse un fichier du modèle, ou un secret chiffré, masqué par le .gitignore.",
    )
    p.add_argument("--racine", type=Path, default=None, help="racine du dépôt (pour les tests)")
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        racine = args.racine if args.racine is not None else racine_du_depot(Path.cwd())
        if not declenche(racine):
            return 0
        lignes = refus(racine)
    except ErreurGit as e:
        print(
            f"modele-projet : refusé — fichiers masqués invérifiables ({e}). {RENVOI}",
            file=sys.stderr,
        )
        return 1
    if lignes:
        print("\n".join(lignes), AUTRE_REMEDE, RENVOI, sep="\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
