"""Les instantanes : les deux commandes que le mecanisme de sauvegarde du modele appelle.

    veille instantane creer <dossier>     copie coherente de /donnees, appli en marche
    veille instantane verifier <dossier>  l'instantane est-il restaurable ?

Un instantane a la forme de `/donnees` : `veille.sqlite3`, `dossiers/`, `kit/`,
`vapid.json` (s'il existe) et `instantane.json`, ecrit en dernier.

ATTENTION : rien ici n'appelle `db.initialiser()` ni `db.connexion()`. Dans le
conteneur de verification, `VEILLE_DB` pointe DANS l'instantane : migrer ou passer
la base en WAL modifierait ce que la restauration remettra en service.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config, notifications

FORMAT = 1
MARQUEUR = "instantane.json"
BASE = "veille.sqlite3"

# Codes de sortie de `verifier` (contrat du modele)
SAIN = 0
MALSAIN = 2
USAGE = 64


class InstantaneIncomplet(Exception):
    """L'instantane n'a pas pu etre pris en entier."""


def _copier_dossier(source: Path, cible: Path) -> None:
    """Copie un dossier (fichiers et dossiers seulement) ; absent : un dossier vide."""
    if not source.exists():
        cible.mkdir()
        return
    if not source.is_dir():
        raise InstantaneIncomplet(f"{source} n'est pas un dossier.")
    # symlinks=False : on suit les liens et on copie des fichiers ordinaires
    shutil.copytree(source, cible, symlinks=False)


def _copier_base(source: Path, cible: Path) -> None:
    if not source.is_file():
        raise InstantaneIncomplet(f"La base {source} est introuvable.")
    # Un chemin existant est verifie avant : connect() creerait une base vide.
    src = sqlite3.connect(source, timeout=30)
    try:
        dst = sqlite3.connect(cible)
        try:
            src.backup(dst)
            # La copie n'a pas besoin de -wal ni de -shm : un dossier propre.
            dst.execute("PRAGMA journal_mode=DELETE")
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()


def _vider(dossier: Path) -> None:
    for p in dossier.iterdir():
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)


def creer(dossier: Path) -> None:
    """Prend l'instantane dans `dossier` (absent, ou present et vide)."""
    dossier = Path(dossier)
    cree_par_nous = False
    try:
        if dossier.exists():
            if not dossier.is_dir() or any(dossier.iterdir()):
                raise InstantaneIncomplet(
                    f"Le dossier {dossier} existe et n'est pas vide : rien n'est ecrase."
                )
        else:
            # le parent doit exister : pas de mkdir -p
            dossier.mkdir()
            cree_par_nous = True
    except OSError as e:
        raise InstantaneIncomplet(f"Le dossier {dossier} est inutilisable : {e}") from e

    try:
        _copier_base(config.CHEMIN_DB, dossier / BASE)
        _copier_dossier(config.CHEMIN_DOSSIERS, dossier / "dossiers")
        _copier_dossier(config.CHEMIN_KIT, dossier / "kit")
        if notifications.CHEMIN_VAPID.is_file():
            shutil.copyfile(notifications.CHEMIN_VAPID, dossier / "vapid.json")
        marqueur = {
            "format": FORMAT,
            "version": config.version(),
            "cree_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (dossier / MARQUEUR).write_text(json.dumps(marqueur), encoding="utf-8")
    except Exception as e:
        # On retire ce qu'on a cree, jamais un dossier qui existait deja.
        try:
            if cree_par_nous:
                shutil.rmtree(dossier, ignore_errors=True)
            else:
                _vider(dossier)
        except OSError:
            pass
        if isinstance(e, InstantaneIncomplet):
            raise
        raise InstantaneIncomplet(f"Instantane incomplet : {e}") from e


def _marqueur_valide(dossier: Path) -> str | None:
    """None si le marqueur est bon, sinon la raison."""
    chemin = dossier / MARQUEUR
    if not chemin.is_file():
        return "le marqueur instantane.json est absent"
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "le marqueur instantane.json est illisible"
    f = donnees.get("format") if isinstance(donnees, dict) else None
    # type(f) is int : True == 1 ne doit pas passer
    if type(f) is not int or f != FORMAT:
        return "le format de l'instantane est inconnu"
    return None


def _base_saine(base: Path) -> str | None:
    """None si `integrity_check` rend `ok`, sinon la raison. N'ecrit jamais."""
    if not base.is_file():
        return "la base veille.sqlite3 est absente"
    # immutable=1 : ni -wal ni -shm ne sont crees a cote de la base verifiee.
    uri = base.resolve().as_uri() + "?mode=ro&immutable=1"
    try:
        cx = sqlite3.connect(uri, uri=True)
        try:
            lignes = cx.execute("PRAGMA integrity_check").fetchall()
        finally:
            cx.close()
    except (sqlite3.DatabaseError, OSError) as e:
        return f"la base est illisible ({e})"
    if lignes != [("ok",)]:
        return "la base est corrompue"
    return None


def verifier(dossier: Path) -> int:
    """0 si l'instantane est conforme, 2 sinon, 64 si `dossier` n'est pas un dossier."""
    dossier = Path(dossier)
    if not dossier.is_dir():
        print(f"Usage : {dossier} n'est pas un dossier.")
        return USAGE
    try:
        raison = _marqueur_valide(dossier) or _base_saine(dossier / BASE)
        if raison is None:
            for nom in ("dossiers", "kit"):
                if not (dossier / nom).is_dir():
                    raison = f"le dossier {nom}/ est absent"
                    break
    except Exception as e:
        # un controle qui n'a pas pu tourner n'est jamais "sain"
        raison = f"la vérification n'a pas pu aller au bout ({type(e).__name__})"
    if raison:
        print(f"Instantané malsain : {raison}.")
        return MALSAIN
    print("Instantané sain.")
    return SAIN
