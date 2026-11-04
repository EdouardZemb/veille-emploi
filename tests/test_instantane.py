"""Les commandes de sauvegarde du modele : `veille instantane creer|verifier`."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from veille import config, instantane, notifications

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def source(tmp_path, monkeypatch):
    """Des donnees vivantes : base en WAL, un dossier, une piece de kit, des cles."""
    s = tmp_path / "src"
    (s / "dossiers" / "offre-1").mkdir(parents=True)
    (s / "dossiers" / "offre-1" / "lettre.md").write_text("Bonjour", encoding="utf-8")
    (s / "kit").mkdir()
    (s / "kit" / "cv.md").write_text("CV", encoding="utf-8")
    (s / "vapid.json").write_text('{"publique": "p", "privee": "q"}', encoding="utf-8")
    cx = sqlite3.connect(s / "veille.sqlite3")
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute("CREATE TABLE offres (id INTEGER PRIMARY KEY, titre TEXT)")
    cx.execute("INSERT INTO offres (titre) VALUES ('Courtier')")
    cx.commit()
    # la connexion reste ouverte : la base est vivante, son -wal existe
    monkeypatch.setattr(config, "CHEMIN_DB", s / "veille.sqlite3")
    monkeypatch.setattr(config, "CHEMIN_DOSSIERS", s / "dossiers")
    monkeypatch.setattr(config, "CHEMIN_KIT", s / "kit")
    monkeypatch.setattr(notifications, "CHEMIN_VAPID", s / "vapid.json")
    yield s
    cx.close()


def _empreintes(d: Path) -> dict[str, str]:
    return {
        str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(d.rglob("*"))
        if p.is_file()
    }


def _liste(d: Path) -> list[str]:
    return sorted(str(p.relative_to(d)) for p in d.rglob("*"))


def test_creer_a_la_forme_de_donnees(source, tmp_path):
    d = tmp_path / "inst"
    instantane.creer(d)
    assert sorted(p.name for p in d.iterdir()) == [
        "dossiers", "instantane.json", "kit", "vapid.json", "veille.sqlite3"
    ]
    cx = sqlite3.connect(d / "veille.sqlite3")
    assert cx.execute("SELECT titre FROM offres").fetchall() == [("Courtier",)]
    assert cx.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    cx.close()
    assert (d / "dossiers" / "offre-1" / "lettre.md").read_text(encoding="utf-8") == "Bonjour"
    assert (d / "kit" / "cv.md").read_text(encoding="utf-8") == "CV"
    marqueur = json.loads((d / "instantane.json").read_text(encoding="utf-8"))
    assert marqueur["format"] == 1
    assert marqueur["version"] and marqueur["cree_le"]
    assert instantane.verifier(d) == 0


def test_creer_accepte_un_dossier_vide(source, tmp_path):
    d = tmp_path / "inst"
    d.mkdir()
    instantane.creer(d)
    assert instantane.verifier(d) == 0


def test_creer_sans_dossiers_ni_kit_ni_cles(source, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHEMIN_DOSSIERS", tmp_path / "absent1")
    monkeypatch.setattr(config, "CHEMIN_KIT", tmp_path / "absent2")
    monkeypatch.setattr(notifications, "CHEMIN_VAPID", tmp_path / "absent3.json")
    d = tmp_path / "inst"
    instantane.creer(d)
    assert (d / "dossiers").is_dir() and (d / "kit").is_dir()
    assert not (d / "vapid.json").exists()
    assert instantane.verifier(d) == 0


def test_creer_sans_base_echoue_et_ne_laisse_rien(source, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHEMIN_DB", tmp_path / "absente.sqlite3")
    d = tmp_path / "inst"
    with pytest.raises(instantane.InstantaneIncomplet):
        instantane.creer(d)
    assert not d.exists()


def test_creer_pendant_une_ecriture(source, tmp_path):
    cx = sqlite3.connect(source / "veille.sqlite3", timeout=30, check_same_thread=False)
    cx.execute("PRAGMA journal_mode=WAL")
    arret = threading.Event()
    demarre = threading.Event()

    def ecrire():
        i = 0
        while not arret.is_set():
            cx.execute("INSERT INTO offres (titre) VALUES (?)", (f"o{i}",))
            cx.commit()
            i += 1
            demarre.set()

    fil = threading.Thread(target=ecrire, daemon=True)
    fil.start()
    assert demarre.wait(10)
    try:
        avant = sqlite3.connect(source / "veille.sqlite3").execute(
            "SELECT count(*) FROM offres"
        ).fetchone()[0]
        d = tmp_path / "inst"
        instantane.creer(d)
    finally:
        arret.set()
        fil.join(timeout=15)
    assert not fil.is_alive()
    cx.close()
    copie = sqlite3.connect(d / "veille.sqlite3")
    assert copie.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert copie.execute("SELECT count(*) FROM offres").fetchone()[0] >= avant
    copie.close()
    assert not (d / "veille.sqlite3-wal").exists()
    assert not (d / "veille.sqlite3-shm").exists()


def test_creer_refuse_un_dossier_non_vide(source, tmp_path):
    d = tmp_path / "inst"
    d.mkdir()
    (d / "x.txt").write_text("a garder", encoding="utf-8")
    with pytest.raises(instantane.InstantaneIncomplet):
        instantane.creer(d)
    assert _liste(d) == ["x.txt"]
    assert (d / "x.txt").read_text(encoding="utf-8") == "a garder"


def test_verifier_sain(source, tmp_path):
    d = tmp_path / "inst"
    instantane.creer(d)
    assert instantane.verifier(d) == 0


def test_verifier_sans_marqueur(source, tmp_path):
    d = tmp_path / "inst"
    instantane.creer(d)
    (d / "instantane.json").unlink()
    assert instantane.verifier(d) == 2


def test_verifier_marqueur_illisible_ou_autre_format(source, tmp_path):
    d = tmp_path / "inst"
    instantane.creer(d)
    (d / "instantane.json").write_text("pas du json", encoding="utf-8")
    assert instantane.verifier(d) == 2
    (d / "instantane.json").write_text('{"format": 2}', encoding="utf-8")
    assert instantane.verifier(d) == 2
    (d / "instantane.json").write_text('{"format": true}', encoding="utf-8")
    assert instantane.verifier(d) == 2


def test_verifier_sans_base_ou_sans_dossiers(source, tmp_path):
    d = tmp_path / "inst"
    instantane.creer(d)
    (d / "kit" / "cv.md").unlink()
    (d / "kit").rmdir()
    assert instantane.verifier(d) == 2
    (d / "kit").mkdir()
    assert instantane.verifier(d) == 0
    (d / "veille.sqlite3").unlink()
    assert instantane.verifier(d) == 2


def test_verifier_base_corrompue(source, tmp_path):
    d = tmp_path / "inst"
    instantane.creer(d)
    base = d / "veille.sqlite3"
    octets = bytearray(base.read_bytes())
    milieu = len(octets) // 2
    octets[milieu:milieu + 2048] = b"\xff" * 2048
    base.write_bytes(bytes(octets))
    assert instantane.verifier(d) == 2


def test_verifier_exception_inattendue_rend_2(source, tmp_path, monkeypatch):
    d = tmp_path / "inst"
    instantane.creer(d)

    def casse(base):
        raise RuntimeError("boum")

    monkeypatch.setattr(instantane, "_base_saine", casse)
    assert instantane.verifier(d) == 2


def test_verifier_usage(source, tmp_path):
    assert instantane.verifier(tmp_path / "absent") == 64
    fichier = tmp_path / "f.txt"
    fichier.write_text("x", encoding="utf-8")
    assert instantane.verifier(fichier) == 64


def test_verifier_ne_modifie_rien(source, tmp_path):
    d = tmp_path / "inst"
    instantane.creer(d)
    avant, liste = _empreintes(d), _liste(d)
    assert instantane.verifier(d) == 0
    assert _empreintes(d) == avant
    assert _liste(d) == liste


def _cli(args, env):
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "veille.cli", *args],
        capture_output=True, text=True, timeout=120, env=env,
        cwd=str(RACINE), encoding="utf-8",
    )


def test_la_cli(source, tmp_path):
    """Comme dans le conteneur : les chemins de donnees visent le dossier verifie."""
    base_env = dict(os.environ)
    base_env["PYTHONPATH"] = str(RACINE / "src")
    env_creer = {
        **base_env,
        "VEILLE_DB": str(source / "veille.sqlite3"),
        "VEILLE_DOSSIERS": str(source / "dossiers"),
        "VEILLE_KIT": str(source / "kit"),
        "VEILLE_VAPID": str(source / "vapid.json"),
    }
    d = tmp_path / "inst"
    r = _cli(["instantane", "creer", str(d)], env_creer)
    assert r.returncode == 0, r.stderr
    avant, liste = _empreintes(d), _liste(d)

    env_verifier = {
        **base_env,
        "VEILLE_DB": str(d / "veille.sqlite3"),
        "VEILLE_DOSSIERS": str(d / "dossiers"),
        "VEILLE_KIT": str(d / "kit"),
        "VEILLE_VAPID": str(d / "vapid.json"),
    }
    r = _cli(["instantane", "verifier", str(d)], env_verifier)
    assert r.returncode == 0, r.stderr + r.stdout
    assert _empreintes(d) == avant
    assert _liste(d) == liste

    # un instantane abime : 2 ; un dossier absent : 64
    (d / "instantane.json").unlink()
    assert _cli(["instantane", "verifier", str(d)], env_verifier).returncode == 2
    assert _cli(["instantane", "verifier", str(tmp_path / "non")], env_verifier).returncode == 64


@pytest.mark.parametrize("args", [
    ["instantane", "verifier"],
    ["instantane", "verifier", "a", "b"],
    ["instantane", "creer"],
    ["instantane"],
    ["instantane", "inconnu", "x"],
    ["instantane", "--foo"],
    ["instantane", "-h"],
    ["-v", "instantane", "--foo"],
])
def test_la_cli_usage_rend_64(source, tmp_path, args):
    env = {**os.environ, "PYTHONPATH": str(RACINE / "src")}
    assert _cli(args, env).returncode == 64


def test_la_cli_creer_non_vide_rend_1(source, tmp_path):
    d = tmp_path / "inst"
    d.mkdir()
    (d / "x").write_text("a", encoding="utf-8")
    env = {
        **os.environ, "PYTHONPATH": str(RACINE / "src"),
        "VEILLE_DB": str(source / "veille.sqlite3"),
    }
    assert _cli(["instantane", "creer", str(d)], env).returncode == 1
