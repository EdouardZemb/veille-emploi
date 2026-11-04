"""Garde de Claude Code (hook PreToolUse) : refuse ce qu'un agent ne doit pas faire seul.

Cinq choses sont refusées : un envoi vers la branche principale, tout contournement des hooks
git, la fusion d'une PR avant que tous ses contrôles soient verts, toute fusion quand le projet est
en mode `fusion : edouard`, et dans les deux modes l'envoi d'une étiquette et l'écriture d'une
publication. La vraie serrure est la protection de branche de GitHub ; ce garde évite seulement à
l'agent de s'y heurter, et de la chercher.

Le mode de fusion se lit sur GitHub (`.copier-answers.yml` de la branche principale), jamais dans la
copie locale ni dans `origin/<branche>`, qu'une session peut réécrire. Tout ce qui est illisible
vaut `edouard`. Le mode et les contrôles se lisent dans le dossier de la session (le `cwd` du hook),
jamais dans celui d'un `cd` : une fusion qui suit, dans la même commande, un changement de dossier
(`cd`, `popd`, `Set-Location`, `env -C`, `Start-Process -WorkingDirectory`…) est refusée, même
vers le dossier de la session.

Le dossier suivi au fil des `cd` sert à lire la branche courante d'un `git push`. Un retour que le
garde ne suit pas (`cd -`, `cd ~`, `popd`…) le rend inconnu : la branche courante est alors
illisible, et un push qui ne nomme pas sa branche est refusé. Un sous-shell Bash (`( … )`, un
élément d'un pipeline, une commande lancée en fond par `&`), ou un interprète enfant (`bash -c`),
rend en sortant le dossier d'avant. Un bloc PowerShell (`try { … }`, `% { … }`, `&{…}`) et une
affectation (`$x = …`) se lisent comme les commandes qu'ils portent.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : garde_claude.py [--branche NOM] [--fusion session|edouard]  (lit sur l'entrée standard le JSON du hook :
    {"tool_name": ..., "tool_input": {"command": ...}, "cwd": ...})

Outils surveillés : `Bash` et `Monitor` (lecture Bash), `PowerShell` (lecture PowerShell), et
tout autre outil qui porte une commande, un outil MCP par exemple (toutes les lectures). La
commande est le premier champ utilisable de `tool_input` parmi `command`, `cmd`, `input`,
`script` : un texte, ou une liste de textes (argv) jointe par des espaces. Pour `Bash`,
`PowerShell` et `Monitor`, un champ d'un autre type est refusé ; pour tout autre outil, il est
ignoré. Un outil sans champ utilisable passe sans que rien soit lancé.

Retour : 0 rien refusé, 2 commande refusée (Claude Code affiche l'erreur à l'agent),
1 entrée illisible (erreur non bloquante), 64 erreur d'usage (branche inconnue).

Principe : dans le doute, refuser. Une commande qu'on ne sait pas lire à fond est analysée
quand même, par un découpage plus grossier, jamais ignorée.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

EXIT_USAGE = 64
# La lecture de chaque outil connu ; tout autre outil est lu de toutes les façons (None).
LECTURES = {"Bash": "Bash", "PowerShell": "PowerShell", "Monitor": "Bash"}
CHAMPS_COMMANDE = ("command", "cmd", "input", "script")
PROFONDEUR_MAX = 4
BUDGET = 20.0  # secondes, pour tous les sous-processus d'une invocation (délai du hook : 30)
_echeance: float | None = None
WINDOWS = os.name == "nt"
# Le dossier suivi quand le garde ne sait plus où est le shell (`cd -`, `popd`, `cd ~`…) : un
# octet nul ne vient jamais d'une commande. La branche courante y est illisible.
INCONNU = chr(0) + "inconnu"
# Les marques des opérateurs, chacune en segment à part : ouverture et fermeture d'un sous-shell
# `( … )`, `|` d'un pipeline, `&` qui lance en fond, et ce qui enchaîne (`;`, `&&`, `||`, saut).
OUVRE, FERME = chr(0) + "(", chr(0) + ")"
TUBE, FOND, SUITE = chr(0) + "|", chr(0) + "&", chr(0) + ";"
MARQUES = {OUVRE, FERME, TUBE, FOND, SUITE}
GIT_GH = ("git", "gh")

ASSIGNATION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# PowerShell : le membre de gauche d'une affectation (`$x = `, `$a, $b = `, `[string]$s = `,
# `$x += `), collé ou non à la commande qui suit (`$x=gh …`).
VARIABLE_PS = r"(?:\[[\w.\[\]]+\])*\$[\w:?{}]+"
GAUCHE_PS = re.compile(VARIABLE_PS + ",?")
AFFECTATION_PS = re.compile(rf"(?:{VARIABLE_PS})?(?:[-+*/%]|\?\?)?=(.*)")
# Ce qui fait viser à gh un autre dépôt que celui du dossier : GH_REPO, et le dépôt git où il lit
# ses remotes (GIT_DIR, GIT_WORK_TREE, GIT_COMMON_DIR).
DEPOT_PAR_ENVIRONNEMENT = re.compile(r"gh_repo|git_dir|git_work_tree|git_common_dir", re.IGNORECASE)
REDIRECTIONS = set("<>")
PONCTUATION = ";|&()<>\n"
# Marque le texte d'une here-string (`<<<`) parmi les jetons : un octet nul ne vient jamais d'une
# commande. Pour un interprète, ce texte est une commande ; pour tout autre, c'est une donnée.
ICI = chr(0) + "<<<"
# Configuration git passée par l'environnement : elle prime sur le core.hooksPath du dépôt.
CONFIG_PAR_ENVIRONNEMENT = re.compile(r"git_config_(?:count|key_|parameters)", re.IGNORECASE)
REFUS_CONFIG_ENVIRONNEMENT = (
    "configuration git par l'environnement (GIT_CONFIG_…), qui peut détourner les hooks"
)
REFUS_HOOKS = "hooks git détournés (core.hooksPath)"
REFUS_AUTRE_DEPOT = "fusion dans un autre dépôt : contrôles invérifiables ici"
REFUS_APRES_CD = (
    "fusion après un changement de dossier, peut-être dans un autre dépôt : contrôles invérifiables "
    "ici ; lancer gh pr merge <n> depuis le clone, sans cd"
)
REFUS_COURANTE_ILLISIBLE = (
    "branche courante illisible : push refusé, nommer la branche (git push origin <branche>)"
)
REFUS_MODE = "fusion réservée à Edouard (mode fusion : edouard)"
REFUS_ETIQUETTE = (
    "envoi d'une étiquette ou écriture de publication : à Edouard (étiquette ou publication)"
)
MODES_FUSION = ("session", "edouard")
REPONSE_SESSION = re.compile(r"^fusion:[ \t]*session[ \t]*\r?$", re.MULTILINE)
# Une étiquette du code (`v1.2.3`) ou de données (`donnees-2026.11.03.1`, et tout `donnees-…`).
DESTINATION_ETIQUETTE = re.compile(r"^(?:v[0-9]|donnees-)")
RELEASE_LECTURE = {"view", "list", "download"}

# Mots qui précèdent la vraie commande sans la changer.
PREFIXES = {
    "env", "command", "exec", "sudo", "time", "nohup", "builtin", "nice", "timeout", "!", "{", "}",
    "if", "then", "do", "else", "elif", "while", "until", "try", "catch", "finally", "elseif",
}  # fmt: skip
# Options de ces enveloppes qui prennent une valeur (`env -u NOM`, `timeout -s KILL`) : les lettres
# des options courtes, et les options longues. Une courte se groupe (`env -iC DIR`) ou se colle à sa
# valeur (`nice -n5`) ; une longue s'abrège (`--ch`) ou prend `=valeur`.
ENVELOPPES_AVEC_VALEUR = {
    "env": ("uCS", {"--unset", "--chdir", "--split-string"}),
    "timeout": ("sk", {"--signal", "--kill-after"}),
    "nice": ("n", {"--adjustment"}),
    "exec": ("a", set()),
    "sudo": (
        "ugDCprtURh",
        {"--user", "--group", "--chdir", "--close-from", "--prompt", "--role", "--type",
         "--other-user", "--chroot", "--host"},
    ),
    "time": ("fo", {"--format", "--output"}),
}  # fmt: skip
# Les options d'une enveloppe qui lancent la commande dans un autre dossier.
DOSSIER_D_ENVELOPPE = {"env": {"-C", "--chdir"}, "sudo": {"-D", "--chdir", "-R", "--chroot"}}
# `env -S TEXTE` : le texte est découpé en arguments, une commande donc.
ECLATE = {"-S", "--split-string"}
# Enveloppes dont le premier argument est une durée, pas la commande (`timeout 60 git …`).
ENVELOPPES_A_DUREE = {"timeout"}
# Interpréteurs dont un argument est lui-même une commande.
INTERPRETES = {
    "bash", "sh", "zsh", "dash", "ksh", "pwsh", "powershell", "cmd", "eval", "xargs", "wsl", "start",
    "start-process", "saps", "invoke-expression", "iex", "trap",
}  # fmt: skip
# Ceux qui exécutent dans le shell même : un `cd` qu'ils font y reste.
DANS_LE_SHELL = {"eval", "invoke-expression", "iex", "trap"}
# Ceux qui lancent un programme, dans un dossier qu'on peut leur donner.
LANCEURS = {"start-process", "saps", "start"}
# Les paramètres de Start-Process, et s'ils prennent une valeur. Un nom s'abrège (`-Work`) ; un
# alias vaut son paramètre.
START_PROCESS = {
    "-filepath": True, "-argumentlist": True, "-workingdirectory": True, "-credential": True,
    "-verb": True, "-windowstyle": True, "-redirectstandardinput": True,
    "-redirectstandardoutput": True, "-redirectstandarderror": True, "-environment": True,
    "-loaduserprofile": False, "-nonewwindow": False, "-passthru": False, "-wait": False,
    "-usenewenvironment": False,
    "-erroraction": True, "-warningaction": True, "-informationaction": True, "-errorvariable": True,
    "-warningvariable": True, "-informationvariable": True, "-outvariable": True,
    "-outbuffer": True, "-pipelinevariable": True,
}  # fmt: skip
START_PROCESS_ALIAS = {
    "-path": "-filepath", "-pspath": "-filepath", "-args": "-argumentlist",
    "-rsi": "-redirectstandardinput", "-rso": "-redirectstandardoutput",
    "-rse": "-redirectstandarderror", "-lup": "-loaduserprofile", "-nnw": "-nonewwindow",
    "-ea": "-erroraction", "-wa": "-warningaction", "-infa": "-informationaction",
    "-ev": "-errorvariable", "-wv": "-warningvariable", "-iv": "-informationvariable",
    "-ov": "-outvariable", "-ob": "-outbuffer", "-pv": "-pipelinevariable",
}  # fmt: skip
CHANGE_DOSSIER = {"cd", "pushd", "chdir", "set-location", "sl", "push-location"}
# Les retours à un dossier d'une pile : le garde ne la suit pas.
RETOURS_DE_DOSSIER = {"popd", "pop-location"}
# Commandes qui effacent, déplacent ou renomment : Bash, cmd, PowerShell et ses alias.
EFFACE_OU_DEPLACE = {
    "rm", "rmdir", "del", "erase", "rd", "remove-item", "ri",
    "mv", "move", "move-item", "mi", "ren", "rename", "rename-item", "rni",
}  # fmt: skip
REFUS_GARDE_FOUS = "effacement ou déplacement des garde-fous (.githooks, scripts/modele)"
REFUS_IDENTIFIANTS = (
    "identifiants affichés (git credential, gh auth git-credential), "
    "qui permettraient de contourner le garde"
)


def _affiche_identifiants(commande: str, args: list[str]) -> bool:
    """`git credential fill`, ou `get` d'un assistant (`git credential-manager get`,
    `git-credential-store get`) : ils impriment l'identifiant enregistré."""
    if commande == "credential":
        return "fill" in args
    return commande.startswith(("credential-", "git-credential-")) and "get" in args


# Les commandes de `gh help` (gh 2.93) : de base, d'actions, d'alias et additionnelles. Tout autre
# premier mot est un alias ou une extension, qui pourrait masquer `gh pr merge`.
COMMANDES_GH = {
    "auth", "browse", "codespace", "gist", "issue", "org", "pr", "project", "release", "repo",
    "skill", "cache", "run", "workflow", "co", "agent-task", "alias", "api", "attestation",
    "completion", "config", "copilot", "extension", "gpg-key", "label", "licenses", "preview",
    "ruleset", "search", "secret", "ssh-key", "status", "variable", "help", "--version", "--help",
}  # fmt: skip

SOUS_COMMANDES_HOOKS = {"commit", "merge", "push", "am", "rebase", "cherry-pick", "revert"}
LONGUES_AVEC_VALEUR = {
    "--message", "--file", "--author", "--date", "--template", "--reuse-message",
    "--reedit-message", "--fixup", "--squash", "--cleanup", "--trailer",
}  # fmt: skip
COURTES_AVEC_VALEUR = "mFCct"
PUSH_AVEC_VALEUR = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
GH_MERGE_AVEC_VALEUR = {
    "-b", "--body", "-t", "--subject", "-F", "--body-file", "-A", "--author-email",
    "--match-head-commit",
}  # fmt: skip
GH_API_AVEC_VALEUR = {
    "-H", "--header", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview",
}  # fmt: skip
GH_API_CHAMPS = {"-f", "-F", "--field", "--raw-field", "--input"}
API_ECRITURE = re.compile(
    r"/merge|git/refs|/contents/|/rulesets|/protection|git/(commits|trees|tags)|/update-branch"
    r"|/releases"
)
API_FUSION = re.compile(r"/merge")
GRAPHQL_FUSION = re.compile(r"mergepullrequest|enablepullrequestautomerge|mergebranch")
GRAPHQL_ECRITURE = re.compile(
    r"mergepullrequest|enablepullrequestautomerge|updateref|createref|deleteref"
    r"|createcommitonbranch|branchprotectionrule|ruleset|mergebranch"
)


def chemin_natif(chemin: str) -> str:
    """Sous Windows, un chemin au format Git Bash (`/c/src/x`) devient `C:/src/x` (et `/c`, `C:/`) :
    git.exe ne lit pas le premier. Tout autre chemin, et tout chemin hors de Windows, reste tel
    quel."""
    if not WINDOWS:
        return chemin
    m = re.match(r"/([A-Za-z])(?=/|$)", chemin)
    if m is None:
        return chemin
    return m.group(1).upper() + ":" + (chemin[m.end() :] or "/")


def _absolu(chemin: str) -> bool:
    return bool(re.match(r"[\\/]|[A-Za-z]:[\\/]", chemin))


class Contexte:
    """Les rappels (branche courante, contrôles, mode) et le dossier suivi au fil des `cd`.

    `dossier` est le dossier où tourne la commande lue : None pour celui de la session, INCONNU
    quand le garde ne sait plus le suivre. `hors_du_dossier` dit qu'un changement de dossier a été
    vu dans cette lecture de la commande : il ne retombe jamais, même après un retour, et toute
    fusion qui le suit est refusée. `changements` compte les changements de dossier vus."""

    def __init__(self, branche, branche_courante, checks_verts, outil=None, fusion=None):
        self.branche = branche
        self.outil = outil
        self._courante = branche_courante
        self._verts = checks_verts
        self._fusion = fusion if fusion is not None else (lambda dossier: "edouard")
        self.dossier: str | None = None
        self.hors_du_dossier = False
        self.changements = 0
        self.depot_par_environnement = False  # la commande mentionne GH_REPO, GIT_DIR…
        self._memo: dict[tuple[str, str | None], Any] = {}

    def courante(self, chemin: str | None) -> str | None:
        """La branche courante dans `chemin`, None si illisible ; jamais lue dans INCONNU."""
        if chemin == INCONNU:
            return None
        cle = ("courante", chemin)
        if cle not in self._memo:
            self._memo[cle] = self._courante(chemin)
        return self._memo[cle]

    def verts(self, pr: str | None) -> bool:
        cle = ("verts", pr)
        if cle not in self._memo:
            self._memo[cle] = bool(self._verts(pr))
        return self._memo[cle]

    def fusion(self) -> str:
        """Le mode de fusion du dépôt de la session, lu une fois, jamais celui d'un dossier suivi
        par les `cd` : une fusion qui suit un changement de dossier est refusée de toute façon.

        Tout ce qui n'est pas `session` vaut `edouard`."""
        cle = ("fusion", None)
        if cle not in self._memo:
            try:
                mode = self._fusion(None)
            except Exception:  # noqa: BLE001 - fail-closed
                mode = "edouard"
            self._memo[cle] = "session" if mode == "session" else "edouard"
        return self._memo[cle]

    def chemin(self, option_c: str | None) -> str | None:
        """Le dossier d'un `git -C option_c` ou d'un `cd option_c`, à partir du dossier suivi."""
        if option_c is not None:
            option_c = chemin_natif(option_c)
            if _absolu(option_c):
                return option_c
        if self.dossier == INCONNU:
            return INCONNU
        if self.dossier is None:
            return option_c
        if option_c is None:
            return self.dossier
        return os.path.join(self.dossier, option_c)

    def aller(self, cible: str | None) -> None:
        """Un changement de dossier, vers `cible`, ou vers un dossier inconnu si elle est vide."""
        self.hors_du_dossier = True
        self.changements += 1
        self.dossier = self.chemin(cible) if cible else INCONNU

    def perdre(self) -> None:
        """Un changement de dossier que le garde ne sait pas suivre."""
        self.aller(None)


def _nom(mot: str) -> str:
    """Nom de commande réduit : `/usr/bin/git`, `C:\\...\\git.exe` donnent `git`."""
    base = re.split(r"[\\/]", mot)[-1].lower()
    for suffixe in (".exe", ".cmd", ".bat"):
        if base.endswith(suffixe):
            return base[: -len(suffixe)]
    return base


def _est_operateur(jeton: str, ponctuation: str = PONCTUATION) -> bool:
    return bool(jeton) and all(c in ponctuation for c in jeton)


def _marques(operateur: str, apres: bool) -> tuple[list[list[str]], bool]:
    """Les marques d'un opérateur (`;`, `|(`…), et si la fin de l'opérateur suit une commande.

    `(` et `)` ouvrent et ferment un sous-shell ; `|` (ou `|&`) sépare les éléments d'un pipeline ;
    `&` lance en fond ; `;`, `&&`, `||` et le saut de ligne enchaînent. `|` et `&` ne marquent que
    s'ils suivent une commande (`apres`) : `; & cmd` est l'opérateur d'appel de PowerShell, et
    `&>` une redirection. Une accolade, une redirection ne marquent rien."""
    marques: list[list[str]] = []
    i = 0
    while i < len(operateur):
        c, deux = operateur[i], operateur[i : i + 2]
        if c in "()":
            marques.append([OUVRE if c == "(" else FERME])
        elif deux in ("&&", "||"):
            marques.append([SUITE])
            i += 1
        elif c == "|" and apres:
            marques.append([TUBE])
            i += deux == "|&"
        elif c == "&" and apres and deux != "&>":
            marques.append([FOND])
        elif c in ";\n":
            marques.append([SUITE])
        apres = c == ")"
        i += 1
    return marques, apres


def _segments_shlex(
    commande: str, echappement: bool, virgules: bool, accolades: bool = False
) -> list[list[str]]:
    # PowerShell, seconde lecture : une accolade, collée ou non, sépare comme un `;`.
    ponctuation = PONCTUATION + ("{}" if accolades else "")
    lex = shlex.shlex(commande, posix=True, punctuation_chars=ponctuation)
    # PowerShell : `a,b` hors guillemets est une liste, chaque élément devient un argument.
    lex.whitespace = " \t\r" + ("," if virgules else "")
    lex.whitespace_split = True
    lex.commenters = ""
    if not echappement:
        lex.escape = ""
    segments: list[list[str]] = [[]]
    sauter = False
    chaine = False
    apres = False  # le dernier jeton lu est un mot d'une commande, ou la fin d'un sous-shell
    for jeton in lex:
        if _est_operateur(jeton, ponctuation):
            if any(c in jeton for c in ";|(){}\n") or not (set(jeton) & REDIRECTIONS):
                # chaque marque devient un segment à part, pour suivre les sous-shells
                marques, apres = _marques(jeton, apres)
                segments += marques
                segments.append([])
            else:  # redirection : l'opérateur et sa cible ne sont pas des arguments
                sauter = True
                chaine = jeton == "<<<"
                if segments[-1] and segments[-1][-1].isdigit():
                    segments[-1].pop()
            continue
        if sauter:
            sauter = False
            if chaine:  # here-string : son texte est gardé, marqué, pour _motif_segment
                segments[-1].append(ICI + jeton)
            continue
        segments[-1].append(jeton)
        apres = True
    return [s for s in segments if s]


def _segments_grossiers(commande: str, virgules: bool, accolades: bool = False) -> list[list[str]]:
    """Repli quand `shlex` échoue (guillemets mal fermés, syntaxe PowerShell) : espaces seuls."""
    separateurs = re.escape(";|&\n<>()" + ("{}" if accolades else ""))
    morceaux = re.split(f"([{separateurs}]+)", commande)
    segments: list[list[str]] = []
    apres = False
    for k, morceau in enumerate(morceaux):
        if k % 2:  # un opérateur : ses marques
            marques, apres = _marques(morceau, apres)
            segments += marques
            continue
        jetons = morceau.replace("'", "").replace('"', "")
        if virgules:
            jetons = jetons.replace(",", " ")
        if jetons.split():
            segments.append(jetons.split())
            apres = True
    return segments


def _segments(
    commande: str, echappement: bool, virgules: bool = False, accolades: bool = False
) -> list[list[str]]:
    try:
        return _segments_shlex(commande, echappement, virgules, accolades)
    except ValueError:
        return _segments_grossiers(commande, virgules, accolades)


def _variantes(commande: str, outil: str | None = None) -> list[tuple[str, bool, bool, bool]]:
    """Les lectures d'une commande selon l'outil : (texte, échappement, virgules, accolades).

    Bash : l'antislash échappe, l'apostrophe inversée est une substitution (donc un séparateur) ;
    une troisième lecture la garde, pour que le contenu d'un jeton entre guillemets qui en porte
    une soit réanalysé. PowerShell : l'antislash est un caractère ordinaire (chemins Windows),
    l'apostrophe inversée est l'échappement, supprimé avant l'analyse, et la virgule sépare les
    éléments d'une liste d'arguments ; une seconde lecture fait d'une accolade, collée ou non, un
    séparateur, pour lire comme des commandes ce que porte un bloc (`try { … }`, `% { … }`,
    `&{…}`). L'autre lecture garde les accolades : une lecture de plus ne peut qu'ajouter un
    refus. Outil inconnu : toutes les lectures, et on refuse si une seule refuse. Celle à accolades
    vient en tête : un bloc qui cache un changement de dossier est refusé avant qu'une autre
    lecture ne lise les contrôles."""
    texte_ps = re.sub(r"`\r?\n", " ", commande).replace("`", "")
    powershell = [(texte_ps, False, True, True), (texte_ps, False, True, False)]
    if outil == "PowerShell":
        return powershell
    continue_sh = re.sub(r"\\\r?\n", "", commande)  # continuation : antislash puis saut
    textes = (continue_sh.replace("`", " "), continue_sh.replace("`", ";"), continue_sh)
    if outil == "Bash":
        return [(t, True, False, False) for t in textes]
    return powershell + [(t, e, False, False) for t in textes for e in (True, False)]


def _valeur_suivante(args: list[str], i: int) -> str:
    return args[i + 1] if i + 1 < len(args) else ""


def _motif_hooks_git(jeton: str) -> bool:
    return "hookspath" in jeton.lower()


def _vise_garde_fous(arg: str) -> bool:
    """Vrai si `arg` désigne `.githooks` ou `scripts/modele`, ou un chemin en dessous : séparateur
    `/` ou `\\`, préfixe quelconque (`./`, `C:\\x\\`), sans égard à la casse. `scripts` lui-même,
    qui contient `scripts/modele`, n'est visé qu'à la racine (`scripts`, `./scripts`), pas
    `apps/web/scripts`. Une option porteuse d'un chemin (`-Path:x`, `--x=y`) est lue par sa
    valeur."""
    valeur = re.sub(r"^-+[\w-]+[:=]", "", arg) if arg.startswith("-") else arg
    parties = [p for p in re.split(r"[\\/]", valeur.lower()) if p not in ("", ".")]
    for i, partie in enumerate(parties):
        if partie == ".githooks":
            return True
        if partie == "scripts" and parties[i + 1 : i + 2] == ["modele"]:
            return True
    absolu = bool(re.match(r"[\\/~]|[A-Za-z]:", valeur))
    return parties == ["scripts"] and not absolu


def _options_git(args: list[str]) -> tuple[str | None, int, str | None]:
    """Lit les options globales de git. Rend (chemin de -C, indice de la sous-commande, refus)."""
    chemin = None
    i = 0
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if _motif_hooks_git(a):
            return chemin, i, "hooks git détournés (core.hooksPath)"
        if a == "-C":
            chemin = _valeur_suivante(args, i) or chemin
            i += 2
        elif a == "-c":
            valeur = _valeur_suivante(args, i)
            if _motif_hooks_git(valeur):
                return chemin, i, "hooks git détournés (core.hooksPath)"
            if valeur.lower().startswith("alias."):
                return chemin, i, "alias git pouvant masquer un push vers la branche principale"
            i += 2
        elif a in ("--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"):
            if _motif_hooks_git(_valeur_suivante(args, i)):
                return chemin, i, "hooks git détournés (core.hooksPath)"
            i += 2
        else:
            i += 1
    return chemin, i, None


def _sans_hooks(sous: str, args: list[str]) -> bool:
    """Vrai si les options de `args` demandent d'ignorer les hooks (--no-verify, -n de commit)."""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            return False
        if a.startswith("--"):
            nom = a.split("=")[0]
            if len(nom) >= len("--no-ve") and "--no-verify".startswith(nom):
                return True
            if "=" not in a and nom in LONGUES_AVEC_VALEUR:
                i += 1
        elif a.startswith("-") and len(a) > 1:
            for k, c in enumerate(a[1:], start=1):
                if c in COURTES_AVEC_VALEUR:
                    if k == len(a) - 1:
                        i += 1
                    break
                if c == "n" and sous == "commit":
                    return True
        i += 1
    return False


def _destination(refspec: str) -> str:
    r = refspec.lstrip("+")
    dest = r.rsplit(":", 1)[1] if ":" in r else r
    if not dest:
        dest = r.rsplit(":", 1)[0]
    for prefixe in ("refs/heads/", "heads/"):
        if dest.startswith(prefixe):
            return dest[len(prefixe) :]
    return dest


def _abrege(nom: str, long: str) -> bool:
    """git accepte une abréviation non ambiguë d'une option longue : `--al` pour `--all`."""
    return len(nom) >= 4 and nom.startswith("--") and long.startswith(nom)


def _push(args: list[str], chemin: str | None, ctx: Contexte) -> str | None:
    refspecs: list[str] = []
    remote = None
    i = 0
    fin_options = False
    while i < len(args):
        a = args[i]
        if not fin_options and a == "--":
            fin_options = True
        elif not fin_options and a.startswith("-") and a != "-":
            nom = a.split("=")[0]
            if _abrege(nom, "--all") or _abrege(nom, "--mirror"):
                return "push de toutes les branches (--all, --mirror), main comprise"
            if _abrege(nom, "--tags") or _abrege(nom, "--follow-tags"):
                return REFUS_ETIQUETTE
            if _abrege(nom, "--repo"):
                remote = a  # --repo donne le remote : tout argument positionnel est un refspec
            if "=" not in a and (
                nom in PUSH_AVEC_VALEUR or any(_abrege(nom, longue) for longue in PUSH_AVEC_VALEUR)
            ):
                i += 1
                if _abrege(nom, "--repo"):
                    remote = a
        elif remote is None:
            remote = a
        else:
            refspecs.append(a)
        i += 1
    refus = f"push vers {ctx.branche}"
    for refspec in refspecs:
        if refspec == "tag":  # `git push origin tag <nom>` : syntaxe de refs/tags/<nom>
            return REFUS_ETIQUETTE
        dest = _destination(refspec)
        if dest.startswith(("refs/tags/", "tags/")) or DESTINATION_ETIQUETTE.match(dest):
            return REFUS_ETIQUETTE
        if dest == ctx.branche:
            return refus
        if dest in ("HEAD", "@"):
            courante = ctx.courante(chemin)
            if courante is None:
                return REFUS_COURANTE_ILLISIBLE
            if courante == ctx.branche:
                return refus
        elif re.search(r"[*?\[]", dest) and not dest.startswith("refs/tags/"):
            return refus
    if not refspecs:
        courante = ctx.courante(chemin)
        if courante is None:
            return REFUS_COURANTE_ILLISIBLE
        if courante == ctx.branche:
            return refus
    return None


def _git(args: list[str], ctx: Contexte) -> str | None:
    option_c, i, refus = _options_git(args)
    if refus:
        return refus
    if i >= len(args):
        return None
    sous, reste = args[i], args[i + 1 :]
    chemin = ctx.chemin(option_c)
    if sous in SOUS_COMMANDES_HOOKS and _sans_hooks(sous, reste):
        return "commande git sans hooks (--no-verify)"
    if sous == "config":
        lecture = any(a in ("--get", "--get-all", "--list", "-l") for a in reste)
        options = [a for a in reste if a.startswith("-")]
        positions = [a for a in reste if not a.startswith("-")]
        repare = (  # la réparation prescrite par la méthode : exactement cette valeur
            set(options) <= {"--local", "--worktree"}
            and len(positions) == 2
            and positions[0].lower() == "core.hookspath"
            and positions[1] == ".githooks"
        )
        if any(_motif_hooks_git(a) for a in reste) and not lecture and not repare:
            return "hooks git détournés (core.hooksPath)"
        if any(a.lower().startswith("alias.") for a in reste) and not lecture:
            return "alias git pouvant masquer un push vers la branche principale"
    elif _motif_hooks_git(sous) or any(_motif_hooks_git(a) for a in reste):
        return REFUS_HOOKS
    if sous in ("rm", "mv") and any(_vise_garde_fous(a) for a in reste):
        return REFUS_GARDE_FOUS
    if _affiche_identifiants(sous.lower(), reste):
        return REFUS_IDENTIFIANTS
    if sous == "push":
        return _push(reste, chemin, ctx)
    return None


def _gh_merge(args: list[str], ctx: Contexte, depot: bool = False) -> str | None:
    pr = None
    if ctx.depot_par_environnement:
        return REFUS_AUTRE_DEPOT
    if ctx.fusion() != "session":
        return REFUS_MODE
    if any(a.split("=")[0] == "--admin" for a in args):
        return "fusion en contournant les règles de protection (--admin)"
    i = 0
    while i < len(args):
        a = args[i]
        nom = a.split("=")[0]
        if nom in ("-R", "--repo"):
            return REFUS_AUTRE_DEPOT
        if a.startswith("-"):
            if "=" not in a and nom in GH_MERGE_AVEC_VALEUR:
                i += 1
        elif pr is None:
            pr = a
        i += 1
    if depot or (pr is not None and re.match(r"(?i)[a-z][a-z0-9+.-]*://", pr)):
        return REFUS_AUTRE_DEPOT
    # Les contrôles se lisent dans le dossier de la session : après un changement de dossier, la
    # fusion pourrait partir dans un autre dépôt, jugée sur une PR de même numéro.
    if ctx.hors_du_dossier:
        return REFUS_APRES_CD
    if not ctx.verts(pr):
        return "fusion avant que tous les contrôles soient verts"
    return None


def _graphql_opaque(args: list[str], texte: str) -> bool:
    return (
        "$" in texte
        or any(a.startswith("@") or "=@" in a for a in args)
        or any(a == "--input" or a.startswith("--input=") for a in args)
    )


def _gh_api(args: list[str], ctx: Contexte) -> str | None:
    refus = "fusion ou écriture de branche par l'API GitHub, qui contourne la PR"
    methode = None
    champs = False
    point = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-X", "--method"):
            methode = _valeur_suivante(args, i)
            i += 1
        elif a.startswith("--method="):
            methode = a.split("=", 1)[1]
        elif a.startswith("-X") and len(a) > 2:
            methode = a[2:]
        elif a in GH_API_CHAMPS:
            champs = True
            i += 1
        elif a.startswith(("-f", "-F", "--field=", "--raw-field=", "--input=")):
            champs = True
        elif a in GH_API_AVEC_VALEUR:
            i += 1
        elif not a.startswith("-") and point is None:
            point = a
        i += 1
    # Les deux contrôles valent pour tout appel, quel que soit le point d'accès.
    texte = " ".join(args).lower()
    effective = (methode or ("POST" if champs else "GET")).upper()
    ecrit = effective != "GET" and point is not None
    fusion_graphql = "mutation" in texte and bool(GRAPHQL_FUSION.search(texte))
    # Corps qu'on ne lit pas ici (@fichier, --input, variables) : fusion possible.
    opaque = point is not None and "graphql" in point.lower() and _graphql_opaque(args, texte)
    fusion_rest = ecrit and bool(API_FUSION.search(point.lower()))
    if (fusion_graphql or opaque or fusion_rest) and ctx.depot_par_environnement:
        return REFUS_AUTRE_DEPOT  # GH_REPO, GIT_DIR… dans la commande : cible invérifiable
    if (fusion_graphql or opaque) and ctx.fusion() != "session":
        return REFUS_MODE
    if ecrit and API_FUSION.search(point.lower()) and ctx.fusion() != "session":
        return REFUS_MODE
    if (fusion_graphql or opaque or fusion_rest) and ctx.hors_du_dossier:
        return REFUS_APRES_CD
    if ecrit and "/releases" in point.lower():
        return REFUS_ETIQUETTE
    if "mutation" in texte and GRAPHQL_ECRITURE.search(texte):
        return refus
    if ecrit and API_ECRITURE.search(point.lower()):
        return refus
    return None


def _montre_le_jeton(arg: str) -> bool:
    """`--show-token`, `-t`, ou `-t` dans un groupe d'options courtes (`-at`)."""
    if arg.split("=")[0] == "--show-token":
        return True
    return bool(re.fullmatch(r"-[a-z]*t[a-z]*", arg))


def _gh(args: list[str], ctx: Contexte) -> str | None:
    positions = []
    depot = False
    i = 0
    while i < len(args) and len(positions) < 2:
        a = args[i]
        if a.split("=")[0] in ("-R", "--repo"):
            depot = True
            i += 1 if "=" in a else 2
            continue
        if not a.startswith("-"):
            positions.append(i)
        i += 1
    mots = [args[k] for k in positions]
    if mots and mots[0] not in COMMANDES_GH:
        return "commande gh inconnue (alias ou extension), qui pourrait masquer une fusion"
    if mots[:1] == ["alias"] and mots[1:2] in (["set"], ["import"]):
        return "alias gh pouvant masquer une fusion"
    if mots == ["auth", "token"]:
        return "jeton gh exposé (gh auth token), qui permettrait de contourner le garde"
    if mots == ["auth", "git-credential"]:
        return REFUS_IDENTIFIANTS
    if mots == ["auth", "status"] and any(_montre_le_jeton(a) for a in args):
        return (
            "jeton gh exposé (gh auth status --show-token), qui permettrait de contourner le garde"
        )
    if mots == ["pr", "merge"]:
        reste = args[positions[1] + 1 :]
        return _gh_merge(reste, ctx, depot)
    if mots[:1] == ["release"] and len(mots) > 1 and mots[1] not in RELEASE_LECTURE:
        return REFUS_ETIQUETTE
    if mots[:1] == ["api"]:
        return _gh_api(args[positions[0] + 1 :], ctx)
    return None


def _motif_segment(segment: list[str], ctx: Contexte, profondeur: int) -> str | None:
    ici = [jeton[len(ICI) :] for jeton in segment if jeton.startswith(ICI)]
    segment = [jeton for jeton in segment if not jeton.startswith(ICI)]
    # Une substitution `$(…)` ou `…` s'exécute même entre guillemets doubles (Bash), et "$(…)"
    # aussi en PowerShell : le contenu d'un tel jeton est réanalysé comme une commande.
    if profondeur < PROFONDEUR_MAX:
        for jeton in [*segment, *ici]:
            if "$(" in jeton or "`" in jeton:
                avant = ctx.changements
                motif = _motif_commande(jeton.replace("`", ";"), ctx, profondeur + 1)
                if motif:
                    return motif
                # Un `cd` dans "$(…)" : un sous-shell en Bash, la même portée en PowerShell.
                if ctx.changements != avant:
                    ctx.dossier = INCONNU
    if any(CONFIG_PAR_ENVIRONNEMENT.search(jeton) for jeton in segment):
        return REFUS_CONFIG_ENVIRONNEMENT
    segment = _sans_affectation(segment)
    i, enveloppe, dossiers, eclate = _enveloppes(segment)
    # Filet : derrière une enveloppe, un jeton qui ne peut pas nommer une commande (un nombre, un
    # dossier) est la valeur d'une option que la table ignore. Si git ou gh vient plus loin,
    # l'analyse repart de lui, dans un dossier inconnu : l'option pouvait en changer.
    filet = None
    if eclate is None and enveloppe is not None and i < len(segment) and not _mot_de_commande(segment[i]):
        filet = next((k for k in range(i + 1, len(segment)) if _nom(segment[k]) in GIT_GH), None)
    debut = i if filet is None else filet
    if any(_motif_hooks_git(jeton) for jeton in segment[:debut]):
        return REFUS_HOOKS
    if not dossiers and filet is None and eclate is None:
        return _motif_lance(segment[debut:], ici, ctx, profondeur)
    # `env -C DIR`, `sudo -D DIR` : la commande tourne ailleurs, le shell reste où il est.
    sauve = ctx.dossier
    try:
        for dossier in dossiers:
            ctx.aller(dossier)
        if filet is not None:
            ctx.perdre()
        if eclate is not None:
            if profondeur >= PROFONDEUR_MAX:
                return "enveloppe trop imbriquée : commande impossible à analyser"
            return _motif_commande(eclate, ctx, profondeur + 1)
        return _motif_lance(segment[debut:], ici, ctx, profondeur)
    finally:
        ctx.dossier = sauve


def _sans_affectation(segment: list[str]) -> list[str]:
    """Le segment sans le membre de gauche d'une affectation PowerShell : `$x = cmd …`,
    `$x=cmd …`, `$a, $b = cmd …`, `[string]$s = cmd …`, `$x += cmd …` rendent `cmd …`. Un autre
    segment est rendu tel quel. (En Bash, `$x = cmd` lancerait la commande nommée par `$x` : la
    lire comme `cmd` ne fait qu'ajouter des refus.)"""
    i = 0
    while i < len(segment) and GAUCHE_PS.fullmatch(segment[i]):
        i += 1
    m = AFFECTATION_PS.fullmatch(segment[i]) if i < len(segment) else None
    if m is None:
        return segment
    return [m.group(1)] * bool(m.group(1)) + segment[i + 1 :]


def _option_d_enveloppe(enveloppe: str, jeton: str, suivant: str) -> tuple[set[str], str, bool]:
    """L'option `jeton` d'une enveloppe : (ses noms s'il prend une valeur, la valeur, vrai si la
    valeur est le jeton suivant). Une option sans valeur rend un ensemble vide. Une abréviation
    ambiguë d'une option longue rend tous les noms qu'elle peut désigner."""
    courtes, longues = ENVELOPPES_AVEC_VALEUR.get(enveloppe, ("", set()))
    if jeton.startswith("--"):
        nom, egal, valeur = jeton.partition("=")
        noms = {o for o in longues if len(nom) > 2 and o.startswith(nom)}
        if not noms or egal:
            return noms, valeur, False
        return noms, suivant, True
    for k, c in enumerate(jeton[1:], start=1):
        if c in courtes:
            valeur = jeton[k + 1 :]
            return {"-" + c}, valeur or suivant, not valeur
    return set(), "", False


def _enveloppes(segment: list[str]) -> tuple[int, str | None, list[str], str | None]:
    """Lit les assignations et les enveloppes de tête (`env`, `timeout`, `nice`, `sudo`…).

    Rend (indice de la commande, dernière enveloppe vue, dossiers donnés par `env -C` ou
    `sudo -D`, texte de `env -S` à réanalyser comme une commande, ou None)."""
    i = 0
    enveloppe: str | None = None
    duree = False
    dossiers: list[str] = []
    while i < len(segment):
        jeton = segment[i]
        if ASSIGNATION.match(jeton):
            pass
        elif _nom(jeton) in PREFIXES:
            enveloppe = _nom(jeton)
            duree = enveloppe in ENVELOPPES_A_DUREE
        elif enveloppe is not None and jeton.startswith("-"):
            noms, valeur, consomme = _option_d_enveloppe(
                enveloppe, jeton, _valeur_suivante(segment, i)
            )
            if consomme:
                i += 1
            if noms & DOSSIER_D_ENVELOPPE.get(enveloppe, set()):
                dossiers.append(valeur)
            if enveloppe == "env" and noms & ECLATE:
                return i, enveloppe, dossiers, " ".join(["env", valeur, *segment[i + 1 :]])
        elif duree:
            duree = False
        else:
            break
        i += 1
    return i, enveloppe, dossiers, None


def _mot_de_commande(jeton: str) -> bool:
    """Vrai pour ce qui peut nommer une commande derrière une enveloppe : un mot (`python`,
    `Write-Host`), ou un chemin vers git ou gh. Faux pour un nombre, un dossier, un autre chemin."""
    return _nom(jeton) in GIT_GH or bool(re.fullmatch(r"[A-Za-z_][\w.+-]*", jeton))


def _cible_de_cd(args: list[str]) -> str | None:
    """La cible d'un `cd`, ou None quand le garde ne la suit pas : aucune cible (le dossier
    personnel), `-` (le dossier précédent), `~…`, une variable, `+N` ou `-N` d'une pile."""
    utiles = [a for a in args if not re.fullmatch(r"(?i)/d", a)]  # cmd : `cd /d DIR`
    cible = next((a for a in utiles if not a.startswith("-") or a == "-"), None)
    if cible is None or cible == "-" or cible.startswith("~") or re.fullmatch(r"[+-]\d+", cible):
        return None
    if "$" in cible or "%" in cible:
        return None
    return cible


def _motif_lance(segment: list[str], ici: list[str], ctx: Contexte, profondeur: int) -> str | None:
    """La commande d'un segment, ses enveloppes retirées."""
    if not segment:
        return None
    commande, reste = _nom(segment[0]), segment[1:]
    # core.hooksPath dans n'importe quel jeton : seul git (lectures, réparation exacte) en décide.
    if commande != "git" and any(_motif_hooks_git(jeton) for jeton in segment):
        return REFUS_HOOKS
    if commande in EFFACE_OU_DEPLACE and any(_vise_garde_fous(a) for a in reste):
        return REFUS_GARDE_FOUS
    if commande.startswith("git-credential-") and _affiche_identifiants(commande, reste):
        return REFUS_IDENTIFIANTS
    if commande in CHANGE_DOSSIER:
        if commande == "pushd" and "-n" in reste:
            # `pushd -n` ne change que la pile : le dossier reste, une fusion qui suit est refusée.
            ctx.hors_du_dossier = True
            return None
        ctx.aller(_cible_de_cd(reste))
        return None
    if commande in RETOURS_DE_DOSSIER:
        ctx.perdre()
        return None
    if commande == "git":
        return _git(reste, ctx)
    if commande == "gh":
        return _gh(reste, ctx)
    if commande in INTERPRETES and profondeur < PROFONDEUR_MAX:
        return _motif_interprete(commande, reste, ici, ctx, profondeur)
    return None


def _parametres_start_process(nom: str) -> set[str]:
    """Les paramètres de Start-Process que désigne `nom` (en minuscules) : par un alias, par le
    nom entier ou abrégé ; plusieurs pour une abréviation ambiguë, aucun pour un autre mot."""
    if nom in START_PROCESS_ALIAS:
        return {START_PROCESS_ALIAS[nom]}
    if nom in START_PROCESS:
        return {nom}
    return {p for p in START_PROCESS if len(nom) > 1 and p.startswith(nom)}


def _lancement(commande: str, args: list[str]) -> tuple[list[str], list[str]]:
    """Ce que lance Start-Process (ou `start`) : (la commande lancée, les dossiers donnés).

    La commande est `-FilePath`, ou le premier positionnel, suivie de `-ArgumentList` et des autres
    positionnels. Les dossiers sont les valeurs de `-WorkingDirectory`, ou du `/D` de `start` (cmd).
    Avant la commande, toute option est un paramètre de Start-Process ; après elle, une option d'une
    seule lettre (`-n`, `-f`) est un argument de la commande lancée."""
    fichier: str | None = None
    lancee: list[str] = []
    dossiers: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        suivant = _valeur_suivante(args, i)
        if commande == "start" and fichier is None and a.startswith("/"):
            m = re.fullmatch(r"(?is)/d(.*)", a)
            if m:
                dossiers.append(m.group(1) or suivant)
                i += 0 if m.group(1) else 1
            i += 1
            continue
        nom, deux_points, valeur = a.partition(":")
        params: set[str] = set()
        if a.startswith("-") and not a.startswith("--") and (fichier is None or len(nom) > 2):
            params = _parametres_start_process(nom.lower())
        if params:
            if not deux_points and any(START_PROCESS[p] for p in params):
                valeur = suivant
                i += 1
            if "-workingdirectory" in params:
                dossiers.append(valeur)
            if params == {"-filepath"}:
                fichier = valeur
            elif params == {"-argumentlist"}:
                lancee.append(valeur)
        elif fichier is None:
            fichier = a
        else:
            lancee.append(a)
        i += 1
    return ([fichier] if fichier is not None else []) + lancee, dossiers


def _motif_interprete(
    commande: str, reste: list[str], ici: list[str], ctx: Contexte, profondeur: int
) -> str | None:
    """Un interprète (`bash -c`, `cmd /c`, `eval`, Start-Process…) : ses arguments, et la commande
    qu'ils forment, sont réanalysés comme des commandes.

    Chacun part du dossier où tourne l'enfant, et du drapeau d'un changement de dossier tel qu'il
    était en y entrant : le texte de `bash -c` se lit deux fois, comme argument et dans la commande
    formée, et un `cd` lu la première fois ne précède pas une fusion lue la seconde. En sortant, le
    dossier d'avant revient, sauf pour `eval`, `trap` ou `Invoke-Expression`, qui exécutent dans
    le shell même : un `cd` qu'ils font le rend inconnu. Le drapeau reste levé si un candidat l'a
    levé."""
    utiles = list(reste)
    while utiles and (utiles[0].startswith("-") or utiles[0].startswith("/")):
        utiles.pop(0)
    candidats = [*reste, " ".join(utiles)]
    base = utiles
    sauve = ctx.dossier
    avant = ctx.changements
    leve = ctx.hors_du_dossier
    try:
        if commande in LANCEURS:
            base, dossiers = _lancement(commande, reste)
            for dossier in dossiers:  # `-WorkingDirectory` : un changement de dossier
                ctx.aller(dossier)
            candidats.append(" ".join(base))
        enfant, hors = ctx.dossier, ctx.hors_du_dossier
        leve = leve or hors
        # Filet : si la commande formée ne commence pas par git ou gh, mais qu'ils viennent plus
        # loin, l'analyse repart d'eux, dans un dossier inconnu.
        filet = None
        if base and _nom(base[0]) not in GIT_GH:
            filet = next((k for k in range(1, len(base)) if _nom(base[k]) in GIT_GH), None)
        if ici:  # `bash <<< 'cmd'` exécute le texte ; `xargs git commit <<< x` l'ajoute à la fin
            candidats += [*ici, " ".join([*utiles, *ici])]
        for candidat in candidats:
            ctx.dossier, ctx.hors_du_dossier = enfant, hors
            if candidat.strip():
                motif = _motif_commande(candidat, ctx, profondeur + 1)
                if motif:
                    return motif
            leve = leve or ctx.hors_du_dossier
        if filet is not None:
            ctx.dossier, ctx.hors_du_dossier = enfant, hors
            ctx.perdre()
            leve = True
            motif = _motif_commande(" ".join(base[filet:]), ctx, profondeur + 1)
            if motif:
                return motif
    finally:
        ctx.dossier = sauve
        ctx.hors_du_dossier = leve or ctx.hors_du_dossier
        if commande in DANS_LE_SHELL and ctx.changements != avant:
            ctx.dossier = INCONNU
    return None


def _groupes_ouverts(segment: list[str]) -> int:
    """Le nombre de groupes Bash `{` qu'ouvre la tête du segment (`{ cd B`, `then { …`)."""
    n = 0
    for jeton in segment:
        if _nom(jeton) not in PREFIXES:
            break
        n += jeton == "{"
    return n


def _motif_lecture(
    texte: str, echappement: bool, virgules: bool, accolades: bool, ctx: Contexte, profondeur: int
) -> str | None:
    """Les segments d'une lecture, dans l'ordre.

    En Bash, un sous-shell rend le dossier d'avant lui : `( … )` à sa fermeture ; un élément d'un
    pipeline (`a | b`, groupe `{ …; }` compris) ou une commande lancée en fond (`a &`), qui partent
    du dossier du shell. Le dernier élément d'un pipeline qui change de dossier le rend inconnu :
    il tourne dans un sous-shell, sauf sous `shopt -s lastpipe`. En PowerShell (la lecture à
    virgules), parenthèses, blocs et pipelines ne changent pas de portée : le dossier reste celui du
    dernier `cd`. Dans `cmd`, `&` enchaîne dans le même shell : la lecture PowerShell d'un texte
    imbriqué, qui garde le dossier, couvre ce cas."""
    cadres: list[tuple[str | None, bool, str | None]] = []  # ( et { : ce qui revient à la fin
    debut = ctx.dossier  # le dossier du shell au début du pipeline en cours
    tube = False  # le pipeline en cours a un `|`
    for segment in _segments(texte, echappement, virgules, accolades):
        if virgules:
            if segment[0] in MARQUES:
                continue
        elif segment in ([TUBE], [FOND]):
            ctx.dossier = debut
            tube = segment == [TUBE]
            continue
        elif segment in ([SUITE], [FERME]) or segment[0] == "}":
            if tube and ctx.dossier != debut:  # le dernier élément d'un pipeline
                ctx.dossier = INCONNU
            debut, tube = ctx.dossier, False
            if segment != [SUITE]:  # la fin d'un sous-shell ou d'un groupe
                debut, tube, ouvert = cadres.pop() if cadres else (INCONNU, False, INCONNU)
                if segment == [FERME]:
                    ctx.dossier = ouvert
            if segment[0] in MARQUES:
                continue
        elif segment == [OUVRE]:
            cadres.append((debut, tube, ctx.dossier))
            debut, tube = ctx.dossier, False
            continue
        else:
            for _ in range(_groupes_ouverts(segment)):
                cadres.append((debut, tube, ctx.dossier))
                debut, tube = ctx.dossier, False
        motif = _motif_segment(segment, ctx, profondeur)
        if motif:
            return motif
    return None


def _motif_commande(commande: str, ctx: Contexte, profondeur: int = 0) -> str | None:
    """Une commande imbriquée, lue de toutes les façons. Chaque lecture part du dossier et du
    drapeau d'entrée ; à la fin, le dossier d'entrée revient, et le drapeau reste levé si une
    lecture l'a levé."""
    if CONFIG_PAR_ENVIRONNEMENT.search(commande):
        return REFUS_CONFIG_ENVIRONNEMENT
    lecture = ctx.outil if profondeur == 0 else None
    dossier, hors = ctx.dossier, ctx.hors_du_dossier
    leve = hors
    try:
        for texte, echappement, virgules, accolades in _variantes(commande, lecture):
            if CONFIG_PAR_ENVIRONNEMENT.search(texte):
                return REFUS_CONFIG_ENVIRONNEMENT
            ctx.dossier, ctx.hors_du_dossier = dossier, hors
            motif = _motif_lecture(texte, echappement, virgules, accolades, ctx, profondeur)
            if motif:
                return motif
            leve = leve or ctx.hors_du_dossier
    finally:
        ctx.dossier = dossier
        ctx.hors_du_dossier = leve or ctx.hors_du_dossier
    return None


def motif_de_refus(
    commande: str,
    branche: str,
    branche_courante: Callable[[str | None], str | None],
    checks_verts: Callable[[str | None], bool],
    outil: str | None = None,
    fusion: Callable[[str | None], str] = lambda dossier: "edouard",
) -> str | None:
    """La raison du refus de `commande`, ou None si elle est admise.

    `branche_courante` reçoit le chemin d'un `git -C <chemin>` ou d'un `cd` (None : le dossier de
    la session) ; elle n'est jamais appelée pour un dossier que le garde ne sait plus suivre.
    `checks_verts` reçoit l'argument de PR de `gh pr merge`, ou None ; elle lit les contrôles dans
    le dossier de la session.
    `outil` (« Bash » ou « PowerShell ») choisit la lecture ; None les essaie toutes.
    `fusion` reçoit toujours None (le dossier de la session) et rend le mode (« session » ou
    « edouard ») ; elle est appelée au plus une fois, et seulement pour une fusion. Sans autre valeur
    que « session », toute fusion est refusée. Une fusion qui suit un changement de dossier est
    refusée dans les deux modes : ni le mode ni les contrôles d'un autre dossier ne sont lus.
    Aucune exception ne sort d'ici : une commande qu'on ne sait pas analyser est refusée.
    """
    try:
        if CONFIG_PAR_ENVIRONNEMENT.search(commande):
            return REFUS_CONFIG_ENVIRONNEMENT
        ctx = Contexte(branche, branche_courante, checks_verts, outil, fusion)
        ctx.depot_par_environnement = bool(DEPOT_PAR_ENVIRONNEMENT.search(commande))
        for texte, echappement, virgules, accolades in _variantes(commande, outil):
            if CONFIG_PAR_ENVIRONNEMENT.search(texte):
                return REFUS_CONFIG_ENVIRONNEMENT
            # Chaque lecture part du dossier de la session, drapeau baissé : le dossier suivi et
            # le changement de dossier ne passent pas d'une lecture à l'autre.
            ctx.dossier = None
            ctx.hors_du_dossier = False
            motif = _motif_lecture(texte, echappement, virgules, accolades, ctx, 0)
            if motif:
                return motif
    except Exception:  # noqa: BLE001 - fail-closed : jamais d'exception vers l'appelant
        return "commande impossible à analyser"
    return None


def _executer(cmd: list[str], cwd: str) -> subprocess.CompletedProcess | None:
    """Lance `cmd` dans le budget de temps restant ; budget épuisé ou erreur : None."""
    delai = BUDGET if _echeance is None else _echeance - time.monotonic()
    if delai <= 0:
        return None
    try:
        return subprocess.run(
            cmd,
            check=False,
            cwd=cwd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=delai,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def checks_verts_gh(pr: str | None, cwd: str) -> bool:
    """Vrai si et seulement si la PR a des contrôles et qu'ils sont tous `pass` ou `skipping`."""
    gh = shutil.which("gh")
    if gh is None or (pr is not None and pr.startswith("-")):
        return False
    cmd = [gh, "pr", "checks", *([pr] if pr else []), "--json", "bucket"]
    r = _executer(cmd, cwd)
    if r is None or r.returncode != 0:
        return False
    try:
        controles = json.loads(r.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return False
    if not isinstance(controles, list) or not controles:
        return False
    return all(isinstance(c, dict) and c.get("bucket") in ("pass", "skipping") for c in controles)


def fusion_du_depot(branche: str, cwd: str | None) -> str:
    """Le mode de fusion du projet, lu sur GitHub : `.copier-answers.yml` à `ref=<branche>`.

    « session » seulement si une ligne vaut `fusion: session` ; « edouard » dans tous les autres
    cas (gh absent, code non nul, budget épuisé, ligne absente ou autre valeur)."""
    gh = shutil.which("gh")
    if gh is None:
        return "edouard"
    point = "repos/{owner}/{repo}/contents/.copier-answers.yml?ref=" + branche
    cmd = [gh, "api", "-H", "Accept: application/vnd.github.raw+json", point]
    r = _executer(cmd, cwd or ".")
    if r is None or r.returncode != 0:
        return "edouard"
    texte = r.stdout.decode("utf-8", errors="replace")
    return "session" if REPONSE_SESSION.search(texte) else "edouard"


def branche_courante_git(chemin: str | None, cwd: str) -> str | None:
    """La branche courante (`git rev-parse --abbrev-ref HEAD`), ou None si illisible."""
    cmd = ["git", *(["-C", chemin] if chemin else []), "rev-parse", "--abbrev-ref", "HEAD"]
    r = _executer(cmd, cwd)
    if r is None or r.returncode != 0:
        return None
    nom = r.stdout.decode("utf-8", errors="replace").strip()
    return nom or None


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):
        self.exit(EXIT_USAGE, "garde-claude : usage invalide (voir --help)\n")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(prog="garde_claude.py", description="Garde PreToolUse de Claude Code.")
    p.add_argument("--branche", help="branche principale (défaut : reglages.BRANCHE_PRINCIPALE)")
    p.add_argument(
        "--fusion",
        choices=MODES_FUSION,
        help="mode de fusion, qui l'emporte sur la lecture de .copier-answers.yml sur GitHub",
    )
    try:
        args = p.parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    try:
        return _executer_garde(args)
    except Exception:  # noqa: BLE001 - fail-closed : pas de trace, un refus lisible
        _refuser("commande impossible à analyser")
        return 2
    finally:
        global _echeance
        _echeance = None


def _refuser(motif: str) -> None:
    print(
        f"modele-projet : refusé — {motif}. Voir docs/modele/methode.md, « Les garde-fous ».",
        file=sys.stderr,
    )


class CommandeIllisible(Exception):
    """Un champ de commande d'un type que le garde ne sait pas lire."""


def commande_de(entree: dict, stricte: bool = True) -> str | None:
    """La commande du premier champ utilisable de `tool_input` parmi CHAMPS_COMMANDE, ou None.

    Un texte est pris tel quel ; une liste de textes (un argv) est jointe par des espaces. Un
    champ d'un autre type lève CommandeIllisible en lecture stricte (Bash, PowerShell, Monitor,
    dont la commande doit être un texte) ; pour tout autre outil, il est ignoré, et le champ
    suivant est essayé : un outil MCP peut avoir un `input` structuré qui n'est pas une
    commande."""
    for champ in CHAMPS_COMMANDE:
        if champ not in entree:
            continue
        valeur = entree[champ]
        if isinstance(valeur, str):
            return valeur
        if isinstance(valeur, list) and all(isinstance(v, str) for v in valeur):
            return " ".join(valeur)
        if stricte:
            raise CommandeIllisible(champ)
    return None


def _executer_garde(args) -> int:
    global _echeance
    _echeance = time.monotonic() + BUDGET
    try:
        donnees = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
        outil = donnees["tool_name"]
        entree = donnees.get("tool_input") or {}
        cwd = donnees.get("cwd") or "."
        if not isinstance(outil, str) or not isinstance(entree, dict) or not isinstance(cwd, str):
            raise TypeError
    except (ValueError, KeyError, TypeError, AttributeError):
        print("garde-claude : entrée du hook illisible, rien vérifié.", file=sys.stderr)
        return 1
    try:
        commande = commande_de(entree, stricte=outil in LECTURES)
    except CommandeIllisible:
        _refuser("champ de commande d'un type inattendu, impossible à analyser")
        return 2
    if commande is None:  # un outil sans commande (lecture, recherche, MCP) : rien à lancer
        return 0
    branche = args.branche
    if branche is None:
        try:
            from reglages import BRANCHE_PRINCIPALE as branche
        except ImportError:
            print("garde-claude : réglages introuvables et aucun --branche donné.", file=sys.stderr)
            return EXIT_USAGE
    motif = motif_de_refus(
        commande,
        branche,
        lambda chemin: branche_courante_git(chemin, cwd),
        lambda pr: checks_verts_gh(pr, cwd),
        LECTURES.get(outil),
        (lambda dossier: args.fusion) if args.fusion else (lambda dossier: fusion_du_depot(branche, cwd)),
    )
    if motif is None:
        return 0
    _refuser(motif)
    return 2


if __name__ == "__main__":
    sys.exit(main())
