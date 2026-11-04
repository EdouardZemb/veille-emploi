"""Le planificateur : la collecte et la purge sans minuteur systemd.

Un conteneur n'a pas de minuteur : un fil de la console collecte aux heures de
la frequence lue en base, en prod seulement, et purge les sessions et les liens
expires, au demarrage puis toutes les six heures, dans tous les modes
(ADR-0002, section 5). Ici, `tour` est appele a la main, avec des instants
choisis : aucun fil n'attend une vraie minute.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from tests.aide_session import connecter
from veille import auth, collecte, db, planificateur, reglages
from veille.app import app

PARIS = ZoneInfo("Europe/Paris")
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)  # le depart de la fixture `horloge`
APP_JS = Path(__file__).resolve().parents[1] / "src" / "veille" / "static" / "app.js"


def _paris(heure: int, minute: int, jour: int = 2) -> datetime:
    return datetime(2026, 11, jour, heure, minute, tzinfo=PARIS)


@pytest.fixture(autouse=True)
def _base_propre(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    db.initialiser()


def _mode(monkeypatch, mode: str | None) -> None:
    if mode is None:
        monkeypatch.delenv("VEILLE_EMPLOI_ENV", raising=False)
    else:
        monkeypatch.setenv("VEILLE_EMPLOI_ENV", mode)


class _Bouchon:
    """Remplace `collecte.collecter` : compte ses appels, leve si on le lui demande."""

    def __init__(self) -> None:
        self.appels: list[dict] = []
        self.echec: Exception | None = None

    def __call__(self, **kwargs) -> int:
        self.appels.append(kwargs)
        if self.echec is not None:
            raise self.echec
        return 0


@pytest.fixture
def bouchon(monkeypatch):
    b = _Bouchon()
    monkeypatch.setattr(collecte, "collecter", b)
    return b


class _Bloquee:
    """Une collecte qui tient jusqu'a ce qu'on la libere (cinq secondes au plus)."""

    def __init__(self) -> None:
        self.commencee = threading.Event()
        self.liberee = threading.Event()
        self.appels: list[dict] = []

    def __call__(self, **kwargs) -> int:
        self.appels.append(kwargs)
        self.commencee.set()
        self.liberee.wait(5)
        return 0


@pytest.fixture
def bloquee(monkeypatch):
    b = _Bloquee()
    monkeypatch.setattr(collecte, "collecter", b)
    yield b
    b.liberee.set()


# --------------------------------------------------------------------------
# La collecte, en prod seulement, aux heures de la frequence
# --------------------------------------------------------------------------


def test_collecte_a_l_heure_en_prod(monkeypatch, bouchon):
    _mode(monkeypatch, "prod")
    reglages.ecrire_frequence("trois_fois")
    p = planificateur.Planificateur()

    p.tour(_paris(7, 14))
    assert bouchon.appels == []
    p.tour(_paris(7, 15))
    assert len(bouchon.appels) == 1
    p.tour(_paris(7, 16))
    assert len(bouchon.appels) == 1
    # `veille collecter --jours 7`, notifications comprises
    assert bouchon.appels[0]["jours"] == 7
    assert bouchon.appels[0].get("notifier", True) is True


@pytest.mark.parametrize("mode", ["staging", "ci", None])
def test_pas_de_collecte_hors_prod(monkeypatch, bouchon, mode):
    _mode(monkeypatch, mode)

    def interdit(*a):
        raise AssertionError("le planificateur ne lit pas le minuteur systemd")

    monkeypatch.setattr(reglages, "_systemctl", interdit)
    p = planificateur.Planificateur()
    for heure, minute in ((7, 14), (7, 15), (7, 16), (12, 15), (18, 15)):
        p.tour(_paris(heure, minute))
    assert bouchon.appels == []


def test_la_frequence_changee_s_applique(monkeypatch, bouchon):
    _mode(monkeypatch, "prod")
    reglages.ecrire_frequence("trois_fois")
    p = planificateur.Planificateur()
    p.tour(_paris(7, 0))
    p.tour(_paris(7, 15))
    assert len(bouchon.appels) == 1

    reglages.ecrire_frequence("une_fois")
    p.tour(_paris(12, 15))
    assert len(bouchon.appels) == 1
    p.tour(_paris(7, 15, jour=3))
    assert len(bouchon.appels) == 2


def test_une_collecte_qui_echoue_n_arrete_rien(monkeypatch, bouchon, caplog):
    _mode(monkeypatch, "prod")
    reglages.ecrire_frequence("trois_fois")
    bouchon.echec = RuntimeError("boite injoignable")
    p = planificateur.Planificateur()
    p.tour(_paris(7, 0))

    with caplog.at_level(logging.WARNING, logger="veille.planificateur"):
        p.tour(_paris(7, 15))
    assert len(bouchon.appels) == 1
    assert "boite injoignable" in caplog.text

    bouchon.echec = None
    p.tour(_paris(12, 15))
    assert len(bouchon.appels) == 2


def test_une_echeance_manquee_ne_rattrape_qu_une_collecte(monkeypatch, bouchon):
    """Un processus suspendu un jour entier puis reveille ne collecte pas chaque
    echeance manquee : une seule (apres un redemarrage, aucune : on repart de zero)."""
    _mode(monkeypatch, "prod")
    reglages.ecrire_frequence("trois_fois")
    p = planificateur.Planificateur()
    p.tour(_paris(7, 0))

    p.tour(_paris(13, 0, jour=3))
    assert len(bouchon.appels) == 1
    p.tour(_paris(13, 1, jour=3))
    p.tour(_paris(13, 2, jour=3))
    assert len(bouchon.appels) == 1
    p.tour(_paris(18, 15, jour=3))
    assert len(bouchon.appels) == 2


# --------------------------------------------------------------------------
# Une seule collecte a la fois
# --------------------------------------------------------------------------


def test_une_seule_collecte_a_la_fois(monkeypatch, bloquee):
    _mode(monkeypatch, "prod")
    reglages.ecrire_frequence("trois_fois")
    p = planificateur.Planificateur()
    try:
        assert p.collecter_maintenant() is True
        assert bloquee.commencee.wait(5)
        assert p.collecter_maintenant() is False
        # l'echeance tombe pendant la collecte : le fil ne l'attend pas, ne la double pas
        p.tour(_paris(7, 0))
        p.tour(_paris(7, 15))
        assert len(bloquee.appels) == 1
    finally:
        bloquee.liberee.set()
        p.arreter()
    assert p.collecter_maintenant() is True
    p.arreter()
    assert len(bloquee.appels) == 2


# --------------------------------------------------------------------------
# La purge des sessions et des liens expires
# --------------------------------------------------------------------------


def _session(nom: str, expire_le: datetime) -> None:
    db.creer_session(nom, "test", auth._iso(T0 - timedelta(days=1)), auth._iso(expire_le))


def _lien(nom: str, expire_le: datetime) -> None:
    db.creer_lien(nom, "serveur", auth._iso(T0 - timedelta(days=1)), auth._iso(expire_le))


def _restantes() -> tuple[set[str], set[str]]:
    with db.connexion() as cx:
        sessions = {r["empreinte"] for r in cx.execute("SELECT empreinte FROM sessions")}
        liens = {r["empreinte"] for r in cx.execute("SELECT empreinte FROM liens_connexion")}
    return sessions, liens


def test_purger_expires_rend_ses_comptes():
    _session("perimee", T0 - timedelta(seconds=1))
    _session("a-l-instant", T0)
    _session("vivante", T0 + timedelta(seconds=1))
    _lien("perime", T0 - timedelta(hours=2))
    _lien("vivant", T0 + timedelta(hours=2))

    assert db.purger_expires(auth._iso(T0)) == (2, 1)
    assert _restantes() == ({"vivante"}, {"vivant"})
    assert db.purger_expires(auth._iso(T0)) == (0, 0)


@pytest.mark.parametrize("mode", ["prod", "staging", None])
def test_purge_au_demarrage_puis_toutes_les_six_heures(monkeypatch, horloge, bouchon, mode):
    _mode(monkeypatch, mode)
    _session("perimee", T0 - timedelta(seconds=1))
    _lien("perime", T0 - timedelta(minutes=5))
    _session("vivante", T0 + timedelta(days=180))

    p = planificateur.Planificateur()
    p.demarrer()
    p.arreter()
    assert _restantes() == ({"vivante"}, set())

    _session("bientot", T0 + timedelta(hours=1))
    _lien("bientot", T0 + timedelta(hours=1))
    p.tour(T0 + timedelta(hours=5, minutes=59))
    assert _restantes() == ({"vivante", "bientot"}, {"bientot"})
    p.tour(T0 + timedelta(hours=6))
    assert _restantes() == ({"vivante"}, set())


# --------------------------------------------------------------------------
# Le fil
# --------------------------------------------------------------------------


def _fils_du_planificateur() -> list[threading.Thread]:
    return [f for f in threading.enumerate() if f.name == planificateur.NOM_FIL]


def test_le_fil_tourne_et_survit_a_un_tour_en_echec(monkeypatch):
    monkeypatch.setattr(planificateur, "ATTENTE_MAX", timedelta(milliseconds=10))
    p = planificateur.Planificateur()
    deux_tours = threading.Event()
    tours: list[datetime] = []

    def tour(instant: datetime) -> None:
        tours.append(instant)
        if len(tours) == 1:
            raise RuntimeError("tour casse")
        deux_tours.set()

    monkeypatch.setattr(p, "tour", tour)
    p.demarrer()
    try:
        assert deux_tours.wait(5)
    finally:
        p.arreter()
    assert all(not f.is_alive() for f in _fils_du_planificateur())


def test_arreter_rend_la_main_tout_de_suite():
    p = planificateur.Planificateur()
    p.demarrer()
    debut = datetime.now()
    p.arreter()
    assert datetime.now() - debut < timedelta(seconds=1)
    assert _fils_du_planificateur() == []


def test_la_console_demarre_et_arrete_le_planificateur(monkeypatch, horloge):
    _mode(monkeypatch, None)
    _session("perimee", T0 - timedelta(seconds=1))

    with TestClient(app):
        assert _restantes() == (set(), set())
        assert [f.is_alive() for f in _fils_du_planificateur()] == [True]
    assert _fils_du_planificateur() == []


# --------------------------------------------------------------------------
# « Collecter maintenant », depuis Reglages
# --------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        yield c


@pytest.fixture
def systemctl(monkeypatch):
    """Les appels a systemctl, retenus au lieu d'etre lances."""
    lances: list[list[str]] = []
    vrai = subprocess.run

    def run(commande, *a, **k):
        if commande and commande[0] == "systemctl":
            lances.append(list(commande))
            return subprocess.CompletedProcess(commande, 0, "", "")
        return vrai(commande, *a, **k)

    monkeypatch.setattr(subprocess, "run", run)
    return lances


def test_collecter_maintenant_en_conteneur(client, monkeypatch, systemctl, bloquee):
    for mode in ("staging", "ci"):
        _mode(monkeypatch, mode)
        r = client.post("/api/reglages/collecter")
        assert r.status_code == 409
        assert r.json() == {"erreur": "collecte_coupee"}
    assert bloquee.appels == []

    _mode(monkeypatch, "prod")
    r = client.post("/api/reglages/collecter")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert bloquee.commencee.wait(5)
    r = client.post("/api/reglages/collecter")
    assert r.status_code == 409
    assert r.json() == {"erreur": "collecte_en_cours"}
    assert len(bloquee.appels) == 1
    assert systemctl == []


def test_collecter_maintenant_sous_systemd(client, monkeypatch, systemctl, bouchon):
    _mode(monkeypatch, None)

    r = client.post("/api/reglages/collecter")

    assert r.status_code == 200
    assert systemctl == [["systemctl", "--user", "start", "veille-collecte.service"]]
    assert bouchon.appels == []


def test_les_refus_de_collecte_se_lisent_a_l_ecran():
    source = APP_JS.read_text(encoding="utf-8")
    erreurs = source[source.index("const ERREURS_API"):source.index("async function api(")]
    assert 'collecte_coupee: "La collecte est coupée sur cette console."' in erreurs
    assert 'collecte_en_cours: "Une collecte est déjà en cours."' in erreurs
