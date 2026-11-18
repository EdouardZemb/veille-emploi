"""Reglages modifiables depuis la console.

Le changement de mot de passe est le plus important : il se tapait jusqu'ici en
SSH, donc pas depuis un telephone. Il protege cette interface, il doit se
changer dans cette interface.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from veille import db, reglages
from veille.app import app
from tests.aide_session import connecter

APP_JS = Path(__file__).resolve().parents[1] / "src" / "veille" / "static" / "app.js"


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
    """On ne laisse pas saisir d'heures libres : chaque frequence porte les siennes, non vides,
    croissantes et dans la journee, que le planificateur lit."""
    for cle, f in reglages.FREQUENCES.items():
        assert f["libelle"] and f["detail"], cle
        heures = f["heures"]
        assert heures, cle
        assert all(a < b for a, b in zip(heures, heures[1:])), cle
        assert all(0 <= h <= 23 and 0 <= m <= 59 for h, m in heures), cle


def test_une_frequence_inconnue_est_refusee(client):
    with pytest.raises(ValueError):
        reglages.ecrire_frequence("n_importe_quoi")
    assert client.post("/api/reglages/frequence", json={"cle": "n_importe_quoi"}).status_code == 400


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


@pytest.mark.parametrize("mode", [None, "staging", "prod"])
def test_la_frequence_vit_en_base_dans_tous_les_modes(monkeypatch, mode):
    """Le mode local se conduit comme le staging : la frequence en base, la collecte inactive
    (seule la prod collecte)."""
    if mode is None:
        monkeypatch.delenv("VEILLE_EMPLOI_ENV", raising=False)
    else:
        monkeypatch.setenv("VEILLE_EMPLOI_ENV", mode)
    db.initialiser()
    etat = reglages.lire_frequence()
    assert etat["cle"] == "trois_fois"
    assert etat["actif"] is (mode == "prod")
    reglages.ecrire_frequence("une_fois")
    etat = reglages.lire_frequence()
    assert etat["cle"] == "une_fois"
    assert db.lire_reglage("frequence") == "une_fois"
    assert etat["actif"] is (mode == "prod")


def test_la_frequence_rend_ses_seules_cles(client, monkeypatch):
    monkeypatch.delenv("VEILLE_EMPLOI_ENV", raising=False)
    cles = {"cle", "prochain_passage", "actif", "choix"}
    etat = reglages.lire_frequence()
    assert set(etat) == cles
    for choix in etat["choix"]:
        assert set(choix) == {"cle", "libelle", "detail"}, choix
    r = client.get("/api/reglages")
    assert r.status_code == 200
    assert set(r.json()["frequence"]) == cles


def test_reglages_ne_montre_plus_la_frequence_de_l_unite():
    source = APP_JS.read_text(encoding="utf-8")
    for reste in ("oncalendar", "Fréquence indisponible", "Réglage personnalisé"):
        assert reste not in source, reste


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


def test_le_libelle_de_chaque_frequence_dit_ses_heures():
    """Le libelle est ce qu'Edouard lit : il enumere les heures de sa frequence, ou dit la
    premiere et la derniere (« 7h à 21h »)."""
    for cle, f in reglages.FREQUENCES.items():
        heures = f["heures"]
        enumerees = {(int(h), int(m)) for h, m in re.findall(r"(\d{1,2})h(\d{2})", f["libelle"])}
        if enumerees:
            assert enumerees == set(heures), cle
            continue
        plage = re.search(r"(\d{1,2})h à (\d{1,2})h", f["libelle"])
        assert plage, cle
        assert (int(plage[1]), int(plage[2])) == (heures[0][0], heures[-1][0]), cle


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
