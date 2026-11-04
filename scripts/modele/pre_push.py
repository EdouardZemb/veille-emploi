"""Refus de tout envoi (création, mise à jour, suppression) vers la branche principale.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : pre_push.py [--branche NOM]  (lit sur l'entrée standard les lignes du hook pre-push :
    « <réf locale> <sha local> <réf distante> <sha distant> »)

Retour : 0 rien refusé, 1 au moins un envoi refusé, 64 erreur d'usage (branche inconnue).
"""

from __future__ import annotations

import argparse
import sys

EXIT_USAGE = 64


def refs_refusees(entree: str, branche: str) -> list[str]:
    """Les références distantes visées par l'entrée du hook qui sont la branche principale."""
    cible = f"refs/heads/{branche}"
    refus = []
    for ligne in entree.split("\n"):
        champs = ligne.split()
        if not champs:
            continue
        if len(champs) < 4:
            raise ValueError("ligne d'entrée mal formée")
        if champs[2] == cible and champs[2] not in refus:
            refus.append(champs[2])
    return refus


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):
        self.exit(EXIT_USAGE, "pre-push : usage invalide (voir --help)\n")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(prog="pre_push.py", description="Refuse l'envoi vers la branche principale.")
    p.add_argument("--branche", help="branche principale (défaut : reglages.BRANCHE_PRINCIPALE)")
    try:
        args = p.parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    branche = args.branche
    if branche is None:
        try:
            from reglages import BRANCHE_PRINCIPALE as branche
        except ImportError:
            print("pre-push : réglages introuvables et aucun --branche donné.", file=sys.stderr)
            return EXIT_USAGE
    entree = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        refus = refs_refusees(entree, branche)
    except ValueError:
        print("pre-push : ligne d'entrée mal formée, envoi refusé", file=sys.stderr)
        return 1
    for ref in refus:
        print(
            f"pre-push : envoi refusé vers {ref} — passer par une PR "
            "(docs/modele/methode.md, « Les garde-fous »).",
            file=sys.stderr,
        )
    return 1 if refus else 0


if __name__ == "__main__":
    sys.exit(main())
