"""Reglages modifiables depuis la console.

Le changement de mot de passe est le plus important : il se tapait jusqu'ici en
SSH, donc pas depuis un telephone. Il protege cette interface, il doit se
changer dans cette interface.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from tests.sauts import sauter
from veille import db, reglages
from veille.app import app
from tests.aide_session import connecter


def _systemd_utilisateur() -> bool:
    """systemd utilisateur repond-il sur cette machine ? Le poste n'a pas
    `systemctl` ; un runner de CI l'a souvent, mais sans session utilisateur.
    Sur le serveur, il repond et ces tests tournent."""
    if shutil.which("systemctl") is None:
        return False
    try:
        r = subprocess.run(["systemctl", "--user", "show-environment"],
                           capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


@pytest.fixture(autouse=True)
def _base_propre(tmp_path, monkeypatch):
    """Une base par test : le seuil et la frequence vivent en base."""
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    db.initialiser()


@pytest.fixture
def criteres_temporaires(tmp_path, monkeypatch):
    """Copie du vrai fichier : on verifie que les commentaires survivent."""
    from veille import config

    copie = tmp_path / "criteres.yaml"
    shutil.copy(config.CHEMIN_CRITERES, copie)
    monkeypatch.setattr(config, "CHEMIN_CRITERES", copie)
    config.recharger()
    yield copie
    config.recharger()


def _poser_graine(chemin, valeur):
    """Ecrit `seuil_interessant: <valeur>` dans la copie temporaire, quelle que soit
    la valeur du vrai fichier."""
    texte = chemin.read_text(encoding="utf-8")
    nouveau, n = re.subn(r"seuil_interessant:\s*[\d.]+", f"seuil_interessant: {valeur}", texte, count=1)
    assert n == 1
    chemin.write_text(nouveau, encoding="utf-8")


@pytest.fixture
def client():
    db.initialiser()
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        yield c


def test_reglages_exigent_une_session(client):
    client.cookies.clear()
    assert client.get("/api/reglages").status_code == 401


# --------------------------------------------------------------------------
# Seuil
# --------------------------------------------------------------------------


def test_changer_le_seuil(criteres_temporaires):
    reglages.ecrire_seuil(60)
    assert reglages.lire_seuil() == 60


@pytest.mark.parametrize("valeur", [-1, 201])
def test_un_seuil_absurde_est_refuse(criteres_temporaires, valeur):
    with pytest.raises(ValueError):
        reglages.ecrire_seuil(valeur)


def test_le_seuil_passe_par_lapi(client, criteres_temporaires):
    r = client.post("/api/reglages/seuil", json={"valeur": 50})
    assert r.status_code == 200
    assert r.json()["seuil"] == 50
    assert client.post("/api/reglages/seuil", json={"valeur": 999}).status_code == 400


# --------------------------------------------------------------------------
# Frequence
# --------------------------------------------------------------------------


def test_les_frequences_proposees_sont_valides():
    """On ne laisse pas saisir un OnCalendar libre : une expression fausse
    casserait la collecte en silence."""
    for cle, f in reglages.FREQUENCES.items():
        assert f["oncalendar"].startswith("*-*-* "), cle
        assert f["libelle"] and f["detail"], cle


def test_une_frequence_inconnue_est_refusee(client):
    with pytest.raises(ValueError):
        reglages.ecrire_frequence("n_importe_quoi")
    assert client.post("/api/reglages/frequence", json={"cle": "n_importe_quoi"}).status_code == 400


@pytest.mark.skipif(sauter(_systemd_utilisateur), reason="systemd utilisateur absent de cette machine")
def test_lire_la_frequence_ne_casse_pas_sans_unite(monkeypatch, tmp_path):
    monkeypatch.setattr(reglages, "CHEMIN_TIMER", tmp_path / "absent.timer")
    etat = reglages.lire_frequence()
    assert etat["oncalendar"] == ""
    assert etat["choix"]


def test_le_seuil_vit_en_base(criteres_temporaires):
    avant = criteres_temporaires.read_bytes()
    db.initialiser()
    reglages.ecrire_seuil(60)
    assert reglages.lire_seuil() == 60.0
    assert criteres_temporaires.read_bytes() == avant


def test_le_seuil_est_repris_de_criteres(criteres_temporaires):
    _poser_graine(criteres_temporaires, 52)
    from veille import config
    config.recharger()
    db.initialiser()
    reglages.initialiser()
    assert reglages.lire_seuil() == 52.0
    reglages.ecrire_seuil(60)
    reglages.initialiser()
    assert reglages.lire_seuil() == 60.0


def test_le_seuil_retombe_sur_criteres_sans_base_amorcee(criteres_temporaires):
    # la graine du clone peut avoir ete changee depuis le telephone (ancien
    # ecrivain) : le test pose sa propre valeur, il ne depend pas du depot
    _poser_graine(criteres_temporaires, 47)
    from veille import config
    config.recharger()
    db.initialiser()
    assert reglages.lire_seuil() == 47.0


def test_frequence_indisponible_sans_systemctl(client, monkeypatch):
    monkeypatch.delenv("VEILLE_EMPLOI_ENV", raising=False)

    def absent(*a):
        raise FileNotFoundError("systemctl")

    monkeypatch.setattr(reglages, "_systemctl", absent)
    etat = reglages.lire_frequence()
    assert etat["etat"] == "indisponible"
    assert etat["mode"] == "systemd"
    assert etat["raison"]
    assert client.get("/api/reglages").status_code == 200


def test_frequence_en_base_en_conteneur(monkeypatch):
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "prod")

    def interdit(*a):
        raise AssertionError("systemctl ne doit pas etre appele")

    monkeypatch.setattr(reglages, "_systemctl", interdit)
    db.initialiser()
    etat = reglages.lire_frequence()
    assert etat["cle"] == "trois_fois"
    assert etat["mode"] == "conteneur"
    assert etat["etat"] == "ok"
    assert etat["actif"] is True
    reglages.ecrire_frequence("une_fois")
    assert reglages.lire_frequence()["cle"] == "une_fois"


def test_la_collecte_n_est_active_qu_en_prod(monkeypatch):
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "staging")
    db.initialiser()
    assert reglages.lire_frequence()["actif"] is False


PARIS = ZoneInfo("Europe/Paris")


@pytest.mark.parametrize("cle, depart, attendu", [
    ("trois_fois", (2026, 11, 2, 6, 0), (2026, 11, 2, 7, 15)),
    ("trois_fois", (2026, 11, 2, 7, 15), (2026, 11, 2, 12, 15)),
    ("trois_fois", (2026, 11, 2, 18, 20), (2026, 11, 3, 7, 15)),
    ("toutes_les_deux_heures", (2026, 11, 2, 21, 16), (2026, 11, 3, 7, 15)),
])
def test_prochain_passage(cle, depart, attendu):
    instant = datetime(*depart, tzinfo=PARIS)
    assert reglages.prochain_passage(cle, instant) == datetime(*attendu, tzinfo=PARIS)


def test_prochain_passage_accepte_l_utc():
    instant = datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc)  # 06:00 a Paris
    rendu = reglages.prochain_passage("trois_fois", instant)
    assert rendu.utcoffset() is not None
    assert rendu.astimezone(PARIS) == datetime(2026, 11, 2, 7, 15, tzinfo=PARIS)


def test_prochain_passage_au_changement_d_heure():
    instant = datetime(2026, 10, 24, 8, 0, tzinfo=PARIS)
    rendu = reglages.prochain_passage("une_fois", instant)
    assert rendu == datetime(2026, 10, 25, 7, 15, tzinfo=PARIS)
    assert rendu.astimezone(timezone.utc) == datetime(2026, 10, 25, 6, 15, tzinfo=timezone.utc)


def test_chaque_frequence_a_des_heures_coherentes():
    for f in reglages.FREQUENCES.values():
        heures = ",".join(f"{h:02d}" for h, _ in f["heures"])
        assert f["oncalendar"] == f"*-*-* {heures}:15:00"


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


def test_letat_des_sources_dit_ce_qui_manque(monkeypatch):
    monkeypatch.delenv("FT_CLIENT_ID", raising=False)
    monkeypatch.delenv("VEILLE_IMAP_MOTDEPASSE", raising=False)
    par_cle = {s["cle"]: s for s in reglages.etat_sources()}
    assert par_cle["france_travail"]["pret"] is False
    assert "FT_CLIENT_ID" in par_cle["france_travail"]["manque"]
    assert par_cle["courriel"]["pret"] is False
    assert par_cle["arbeitnow"]["pret"] is True


def test_letat_des_sources_reconnait_les_identifiants(monkeypatch):
    monkeypatch.setenv("FT_CLIENT_ID", "x")
    monkeypatch.setenv("FT_CLIENT_SECRET", "y")
    par_cle = {s["cle"]: s for s in reglages.etat_sources()}
    assert par_cle["france_travail"]["pret"] is True
    assert par_cle["france_travail"]["manque"] == ""
