"""Contrôle du format des commits : Conventional Commits, en-tête de 100 caractères au plus.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage (un seul mode) :
    commits.py --message FICHIER | --plage BASE..HEAD | --titre TEXTE

Les fusions, les « Revert » et les commits de réécriture (fixup!, squash!, amend!) sont exemptés.
La sortie nomme le commit (SHA court) et la raison, jamais le texte du sujet.

Retour : 0 conforme, 1 au moins un en-tête refusé, 64 erreur d'usage (git en échec compris :
une plage qu'on ne peut pas lire ne passe jamais pour conforme).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)
LONGUEUR_MAX = 100
EXIT_USAGE = 64

EXEMPTIONS = ("Merge ", 'Revert "', "fixup! ", "squash! ", "amend! ")
EXPRESSION = re.compile(r"(?:" + "|".join(TYPES) + r")(?:\([a-z0-9][a-z0-9-]*\))?!?: \S.*")


def entete_du_message(texte: str) -> str:
    """Première ligne qui ne commence pas par « # », sans les espaces de fin."""
    for ligne in texte.split("\n"):
        if not ligne.startswith("#"):
            return ligne.rstrip()
    return ""


def verifier_entete(entete: str) -> str | None:
    """La raison du refus, ou None si l'en-tête est conforme (ou exempté)."""
    if entete.startswith(EXEMPTIONS):
        return None
    if len(entete) > LONGUEUR_MAX:
        return f"l'en-tête dépasse {LONGUEUR_MAX} caractères ({len(entete)})"
    if EXPRESSION.fullmatch(entete) is None:
        return "l'en-tête doit suivre « type(portée): sujet » ; types admis : " + ", ".join(TYPES)
    return None


class ErreurUsage(Exception):
    pass


def _sujets(plage: str) -> list[tuple[str, str]]:
    """Les couples (SHA court, sujet) des commits de la plage, hors fusions."""
    if not plage.strip() or plage.startswith("-"):
        raise ErreurUsage("plage vide ou invalide")
    try:
        r = subprocess.run(
            ["git", "log", "--no-merges", "--format=%h%x09%s", plage, "--"],
            check=False,
            capture_output=True,
        )
    except OSError:
        raise ErreurUsage("git est introuvable") from None
    if r.returncode != 0:
        raise ErreurUsage("échec de git (dépôt ou plage invalide)")
    # Octets bruts, séparés sur « \n » seul : le mode texte ferait d'un « \r » isolé un saut de ligne.
    sortie = r.stdout.decode("utf-8", errors="replace")
    couples = []
    for ligne in sortie.split("\n"):
        if ligne:
            sha, _, sujet = ligne.partition("\t")
            couples.append((sha, sujet.rstrip()))
    return couples


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):
        self.exit(EXIT_USAGE, "commits : usage invalide (voir --help)\n")


def _analyseur() -> argparse.ArgumentParser:
    p = _Analyseur(prog="commits.py", description="Contrôle du format des commits.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--message", metavar="FICHIER", help="message de commit")
    mode.add_argument("--plage", metavar="BASE..HEAD", help="commits d'une plage git")
    mode.add_argument("--titre", metavar="TEXTE", help="titre à contrôler (ex. titre de PR)")
    return p


def _a_controler(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Les couples (étiquette, en-tête) à contrôler."""
    if args.message is not None:
        try:
            with open(args.message, encoding="utf-8-sig", newline=None) as f:
                texte = f.read()
        except (OSError, UnicodeDecodeError):
            raise ErreurUsage("message illisible") from None
        return [("message", entete_du_message(texte.replace("\r", "")))]
    if args.titre is not None:
        return [("titre", args.titre.strip())]
    return _sujets(args.plage)


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    try:
        args = _analyseur().parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    try:
        elements = _a_controler(args)
    except ErreurUsage as e:
        print(f"commits : {e}", file=sys.stderr)
        return EXIT_USAGE
    refus = 0
    for etiquette, entete in elements:
        raison = verifier_entete(entete)
        if raison is not None:
            refus += 1
            print(f"commits : {etiquette} — {raison}", file=sys.stderr)
    if refus:
        print(f"commits : {refus} en-tête(s) refusé(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
