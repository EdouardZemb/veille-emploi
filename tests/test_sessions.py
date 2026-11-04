"""Les sessions en base : jeton hors base, duree, prolongation, cookie."""

from __future__ import annotations

import pytest
from fastapi import Response

from veille import auth, db


@pytest.fixture(autouse=True)
def _base():
    db.initialiser()


def test_le_jeton_n_est_jamais_en_base():
    jeton = auth.ouvrir_session("Android")
    with db.connexion() as cx:
        lignes = [tuple(l) for l in cx.execute("SELECT * FROM sessions")]
    assert jeton not in repr(lignes)
    assert db.session_par_empreinte(auth.empreinte(jeton)) is not None


def test_une_session_dure_180_jours_sans_usage(horloge):
    jeton = auth.ouvrir_session("Android")
    horloge.avancer(days=181)
    assert auth.lire_session(jeton) is None


def test_l_usage_prolonge_la_session(horloge):
    jeton = auth.ouvrir_session("Android")
    horloge.avancer(days=100)
    assert auth.lire_session(jeton)["prolongee"] is True
    horloge.avancer(days=150)  # 250 jours apres l'ouverture, 150 apres le dernier usage
    assert auth.lire_session(jeton) is not None


def test_la_prolongation_s_ecrit_au_plus_une_fois_par_heure(horloge):
    jeton = auth.ouvrir_session("Android")
    horloge.avancer(minutes=10)
    assert auth.lire_session(jeton)["prolongee"] is False
    horloge.avancer(minutes=51)
    assert auth.lire_session(jeton)["prolongee"] is True


def test_un_jeton_inconnu_ne_donne_rien():
    assert auth.lire_session("") is None
    assert auth.lire_session("x" * 43) is None


def test_fermer_la_session_la_retire():
    jeton = auth.ouvrir_session("Android")
    auth.fermer_session(auth.lire_session(jeton)["id"])
    assert auth.lire_session(jeton) is None


def test_le_cookie(monkeypatch):
    monkeypatch.setenv("VEILLE_HTTPS", "1")
    reponse = Response()
    auth.poser_cookie(reponse, "jeton")
    entete = reponse.headers["set-cookie"]
    assert entete.startswith("__Host-veille_session=jeton;")
    for attendu in ("HttpOnly", "Max-Age=15552000", "Path=/", "Secure"):
        assert attendu in entete
    assert "samesite=lax" in entete.lower()


@pytest.mark.parametrize("ua, appareil", [
    ("Mozilla/5.0 (Linux; Android 14; SM-G780G) Chrome/130", "Android"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", "iPhone"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130", "Windows"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)", "Mac"),
    ("Mozilla/5.0 (X11; Linux x86_64)", "Linux"),
    ("", "Appareil"),
])
def test_appareil_depuis(ua, appareil):
    assert auth.appareil_depuis(ua) == appareil


def test_exiger_session_tourne_hors_de_la_boucle():
    """Elle lit et ecrit la base : en `async def`, elle bloquerait la boucle
    d'evenements ; en `def`, FastAPI la fait tourner dans un fil."""
    import inspect

    assert not inspect.iscoroutinefunction(auth.exiger_session)
