"""Signaux de la CI (hook SessionStart) : ce qui est rouge sur GitHub au démarrage d'une session.

Trois lectures par `gh`, lancées ensemble, dans un budget total de BUDGET secondes :
- les exécutions de la branche principale : la plus récente de chaque workflow, sur 7 jours, hors
  événements de PR (`pull_request…`) ;
- les PR ouvertes dont un contrôle est rouge ;
- les workflows désactivés.

Ce qu'un fork peut écrire (le titre d'une PR, le nom d'un workflow absent de la copie) n'est pas
recopié : il entrerait dans le contexte de Claude.

Le script écrit sur la sortie standard un seul objet JSON (`systemMessage` pour l'utilisateur,
`additionalContext` pour Claude) et rend toujours 0 : il ne bloque jamais une session, exception
comprise. Le texte tient en PLAFOND caractères. Une lecture impossible est dite, jamais passée
sous silence.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : signaux.py [--branche NOM]  (défaut : reglages.BRANCHE_PRINCIPALE)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

BUDGET = 10.0  # secondes, pour tous les sous-processus d'une invocation (délai du hook : 30)
# `datetime.UTC` n'existe qu'à partir de Python 3.11.
UTC = timezone(timedelta(0))
FENETRE = timedelta(days=7)
ATTENTE = timedelta(hours=1)
MAX_ELEMENTS = 20
MAX_LIGNE = 300  # caractères par ligne
PLAFOND = 10_000  # caractères pour le texte entier : la limite documentée des hooks
CONCLUSIONS_ROUGES = {"failure", "cancelled", "timed_out", "startup_failure", "action_required"}
STATUTS_EN_ATTENTE = {"queued", "waiting", "pending", "requested"}
ETATS_DESACTIVES = {"disabled_inactivity": "inactivité", "disabled_manually": "à la main"}
MAX_NOMS = 3
PREFIXE_PR = "pull_request"  # pull_request, pull_request_target, pull_request_review…
PREFIXE_DYNAMIQUE = "dynamic/"  # les workflows de GitHub, comme « Dependabot Updates »

CHAMPS_RUNS = "workflowName,event,status,conclusion,createdAt,url"


def _borner(ligne: str) -> str:
    return ligne if len(ligne) <= MAX_LIGNE else ligne[: MAX_LIGNE - 1] + "…"


def _date(texte: str) -> datetime:
    # strptime lit le « Z » final, que fromisoformat ne lit pas avant Python 3.11.
    return datetime.strptime(texte, "%Y-%m-%dT%H:%M:%S%z")


def _affiche(quand: datetime) -> str:
    return quand.astimezone(UTC).strftime("%d/%m %H:%M UTC")


def executions_rouges(runs: list[dict], maintenant: datetime) -> tuple[list[str], int]:
    """Les lignes rouges, et le nombre de workflows vus dans la fenêtre.

    Seule la plus récente exécution de chaque workflow compte : un rouge suivi d'un vert est
    réparé."""
    derniers: dict[str, tuple[datetime, dict]] = {}
    for r in runs:
        quand = _date(r["createdAt"])
        if maintenant - quand > FENETRE:
            continue
        if str(r.get("event") or "").startswith(PREFIXE_PR):
            # Une exécution de PR a sa propre lecture. Pour un fork, elle prend le fichier de
            # workflow du fork : son nom, que n'importe qui écrit, entrerait dans le contexte de
            # Claude.
            continue
        nom = r["workflowName"]
        if nom not in derniers or quand > derniers[nom][0]:
            derniers[nom] = (quand, r)
    lignes = []
    for nom, (quand, r) in derniers.items():
        detail = f"{nom} ({r.get('event', '?')}, {_affiche(quand)}) {r.get('url', '')}"
        if r.get("status") == "completed" and r.get("conclusion") in CONCLUSIONS_ROUGES:
            lignes.append(_borner(f"- rouge : {detail}"))
        elif r.get("status") in STATUTS_EN_ATTENTE and maintenant - quand > ATTENTE:
            lignes.append(_borner(f"- en attente depuis plus d'une heure : {detail}"))
    return lignes, len(derniers)


def _controle_rouge(c: dict) -> str | None:
    """Le nom d'un contrôle rouge (CheckRun ou StatusContext), sinon None."""
    if c.get("__typename") == "StatusContext":
        return c.get("context", "?") if c.get("state") in ("FAILURE", "ERROR") else None
    conclusion = str(c.get("conclusion") or "").lower()
    return c.get("name", "?") if conclusion in CONCLUSIONS_ROUGES else None


def prs_rouges(prs: list[dict]) -> list[str]:
    lignes = []
    for p in prs:
        noms = [n for n in map(_controle_rouge, p.get("statusCheckRollup") or []) if n]
        if not noms:
            continue
        if p.get("isCrossRepository") is not False:
            # Le titre et les noms viennent d'un fork : n'importe qui les écrit, et ils entreraient
            # dans le contexte de Claude. On ne les recopie pas. Absent ou nul, le champ vaut fork.
            lignes.append(_borner(f"- PR #{p['number']} (fork) : contrôle rouge {p.get('url', '')}"))
            continue
        liste = ", ".join(noms[:MAX_NOMS]) + (", …" if len(noms) > MAX_NOMS else "")
        lignes.append(
            _borner(
                f"- PR #{p['number']} « {p['title']} » : contrôle rouge ({liste}) {p.get('url', '')}"
            )
        )
    return lignes


def _workflow_du_depot(racine: str, chemin: str) -> bool:
    """Vrai si `chemin` est un workflow de GitHub (`dynamic/…`) ou un fichier de la copie.

    Un chemin absolu, ou qui sort de la racine, ne compte pas."""
    if chemin.startswith(PREFIXE_DYNAMIQUE):
        return True
    base = os.path.realpath(racine)
    cible = os.path.realpath(os.path.join(base, chemin))
    try:
        dedans = os.path.commonpath([base, cible]) == base
    except ValueError:  # deux lecteurs différents, sous Windows
        return False
    return dedans and os.path.isfile(cible)


def workflows_desactives(workflows: list[dict], racine: str) -> list[str]:
    """Les workflows désactivés. Seul un workflow du dépôt est nommé : un autre (celui d'un fork)
    a un nom que n'importe qui écrit."""
    lignes = []
    for w in workflows:
        etat = ETATS_DESACTIVES.get(w.get("state"))
        if etat is None:
            continue
        if _workflow_du_depot(racine, str(w.get("path") or "")):
            lignes.append(_borner(f"- désactivé : {w['name']} ({etat})"))
        else:
            lignes.append(_borner(f"- désactivé : un workflow absent de cette copie ({etat})"))
    return lignes


def _tuer(proc: subprocess.Popen) -> None:
    """Arrête `gh` et ses enfants sans attendre leurs tuyaux : un enfant orphelin les garderait
    ouverts (sous Windows, `gh.cmd` lance un enfant que `kill` n'atteint pas)."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                check=False,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        proc.kill()
    except OSError:
        pass
    for tuyau in (proc.stdout, proc.stderr):
        try:
            if tuyau:
                tuyau.close()
        except OSError:
            pass


def lire(args: list[str], cwd: str, echeance: float) -> tuple[list | None, str]:
    """La liste JSON rendue par `gh <args>`, ou None et le motif de l'échec."""
    gh = shutil.which("gh")
    if gh is None:
        return None, "gh absent"
    delai = echeance - time.monotonic()
    if delai <= 0:
        return None, "délai dépassé"
    try:
        proc = subprocess.Popen(
            [gh, *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, ValueError):
        return None, "erreur de gh"
    try:
        sortie, _ = proc.communicate(timeout=delai)
    except subprocess.TimeoutExpired:
        _tuer(proc)
        return None, "délai dépassé"
    except (OSError, subprocess.SubprocessError, ValueError):
        _tuer(proc)
        return None, "erreur de gh"
    if proc.returncode != 0:
        return None, "erreur de gh"
    try:
        donnees = json.loads(sortie.decode("utf-8", errors="replace"))
    except ValueError:
        return None, "réponse illisible"
    if not isinstance(donnees, list):
        return None, "réponse illisible"
    return donnees, ""


def _compte(n: int, singulier: str, pluriel: str) -> str:
    """`0 PR ouverte`, `1 PR ouverte`, `2 PR ouvertes` : le pluriel à partir de deux."""
    return f"{n} {singulier if n < 2 else pluriel}"


def composer(branche: str, runs, prs, workflows, maintenant: datetime, racine: str = ".") -> str:
    """Le texte du message ; chaque lecture est le couple (liste ou None, motif) de `lire`.

    Les chemins des workflows se lisent dans `racine`. Le texte ne dépasse pas PLAFOND."""
    lignes: list[str] = []
    comptes: list[str] = []  # ceux des lectures faites seulement
    if runs[0] is not None:
        rouges, nb_workflows = executions_rouges(runs[0], maintenant)
        lignes += rouges
        comptes.append(
            _compte(nb_workflows, "workflow exécuté en 7 jours", "workflows exécutés en 7 jours")
        )
    if prs[0] is not None:
        lignes += prs_rouges(prs[0])
        comptes.append(_compte(len(prs[0]), "PR ouverte", "PR ouvertes"))
    if workflows[0] is not None:
        lignes += workflows_desactives(workflows[0], racine)

    manquantes: dict[str, list[str]] = {}
    for nom, (donnees, motif) in (
        ("exécutions", runs),
        ("PR ouvertes", prs),
        ("workflows", workflows),
    ):
        if donnees is None:
            manquantes.setdefault(motif, []).append(nom)
    rien_de_lu = sum(map(len, manquantes.values())) == 3

    if rien_de_lu and len(manquantes) == 1:
        (motif,) = manquantes
        texte = f"signaux de la CI : non lus ({motif})"
    elif not lignes and not manquantes:
        texte = f"signaux de la CI : rien de rouge ({', '.join(comptes)})"
    elif not lignes and not rien_de_lu:
        lus = f" ({', '.join(comptes)})" if comptes else ""
        groupes = ", ".join(f"{', '.join(noms)} ({motif})" for motif, noms in manquantes.items())
        texte = f"signaux de la CI : rien de rouge dans ce qui a été lu{lus} ; non lues : {groupes}"
    else:
        sortie = [f"signaux de la CI (branche {branche}) :", *lignes[:MAX_ELEMENTS]]
        if len(lignes) > MAX_ELEMENTS:
            sortie.append(f"… et {len(lignes) - MAX_ELEMENTS} de plus")
        if manquantes:
            groupes = "; ".join(
                f"{', '.join(noms)} ({motif})" for motif, noms in manquantes.items()
            )
            sortie.append(f"- non lues : {groupes}")
        texte = "\n".join(sortie)
    return texte if len(texte) <= PLAFOND else texte[: PLAFOND - 1] + "…"


def sortie_hook(texte: str) -> str:
    return json.dumps(
        {
            "systemMessage": texte,
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": texte},
        },
        ensure_ascii=True,
    )


def _racine_du_depot(echeance: float) -> str:
    """La racine du dépôt où le script se trouve, sinon le dossier courant."""
    delai = echeance - time.monotonic()
    if delai > 0:
        try:
            r = subprocess.run(
                ["git", "-C", os.path.dirname(os.path.abspath(__file__)), "rev-parse", "--show-toplevel"],
                check=False,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=delai,
            )
            racine = r.stdout.decode("utf-8", errors="replace").strip()
            if r.returncode == 0 and racine:
                return racine
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return "."


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):
        raise ValueError(message)  # jamais de sortie ni de SystemExit : main rend toujours son JSON


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        echeance = time.monotonic() + BUDGET
        p = _Analyseur(description=__doc__, add_help=False)
        p.add_argument("--branche", help="branche principale (défaut : reglages.BRANCHE_PRINCIPALE)")
        args, _ = p.parse_known_args(argv)
        branche = args.branche
        if branche is None:
            import reglages

            branche = reglages.BRANCHE_PRINCIPALE
        cwd = _racine_du_depot(echeance)
        lectures = [
            ["run", "list", "--branch", branche, "--limit", "100", "--json", CHAMPS_RUNS],
            ["pr", "list", "--state", "open", "--limit", "50", "--json",
             "number,title,url,statusCheckRollup,isCrossRepository"],
            ["workflow", "list", "--all", "--json", "name,state,path"],
        ]  # fmt: skip
        with ThreadPoolExecutor(max_workers=3) as pool:
            futurs = [pool.submit(lire, a, cwd, echeance) for a in lectures]
            runs, prs, workflows = (f.result() for f in futurs)
        texte = composer(branche, runs, prs, workflows, datetime.now(UTC), racine=cwd)
    except Exception:  # noqa: BLE001 - jamais d'exception vers la session
        texte = "signaux de la CI : non lus (erreur interne)"
    print(sortie_hook(texte))
    return 0


if __name__ == "__main__":
    sys.exit(main())
