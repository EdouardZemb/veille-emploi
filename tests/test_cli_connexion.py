"""Les commandes `veille lien` et `veille passkeys`, la ligne de `veille etat`, et le mot
de passe qui n'existe plus."""

from __future__ import annotations

import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from tests.authentificateur import b64url
from veille import auth, cli, config, db

CREEE_LE = "2026-11-02T09:00:00+00:00"


def _sans_passkey() -> None:
    db.initialiser()
    # La base sert a toute la suite : chaque test part sans passkey.
    with db.connexion() as cx:
        cx.execute("DELETE FROM passkeys")


def _passkey(appareil: str, utilisee_le: str | None = None) -> tuple[int, str]:
    """Une passkey en base, sans ceremonie ; rend son id et son identifiant WebAuthn."""
    identifiant = b64url(os.urandom(16))
    passkey_id = db.enregistrer_passkey(identifiant, os.urandom(32), 0, ["internal"], appareil,
                                        CREEE_LE)
    if utilisee_le:
        db.maj_passkey_apres_usage(passkey_id, 1, 0, utilisee_le)
    return passkey_id, identifiant


def test_veille_lien_affiche_une_adresse_valable(capsys):
    db.initialiser()
    assert cli.principal(["lien"]) == 0
    sortie = capsys.readouterr().out
    adresses = [l for l in sortie.splitlines() if l.startswith("http://testserver/lien#")]
    assert len(adresses) == 1
    jeton = adresses[0].split("#", 1)[1]
    assert auth.lien_ouvert(jeton) is not None


def test_veille_lien_sans_veille_url_echoue(capsys, monkeypatch):
    monkeypatch.delenv("VEILLE_URL")
    assert cli.principal(["lien"]) == 1
    sortie = capsys.readouterr()
    assert "VEILLE_URL" in sortie.out + sortie.err


def test_veille_etat_dit_la_connexion(capsys, monkeypatch):
    db.initialiser()
    with db.connexion() as cx:
        cx.execute("DELETE FROM passkeys")
    assert cli.principal(["etat"]) == 0
    assert "Connexion : 0 passkey, origine http://testserver" in capsys.readouterr().out
    monkeypatch.delenv("VEILLE_URL")
    assert cli.principal(["etat"]) == 0
    assert "Connexion : indisponible, VEILLE_URL n'est pas définie" in capsys.readouterr().out


def test_le_mot_de_passe_n_existe_plus():
    from veille import app as console

    with TestClient(console.app, follow_redirects=False) as c:
        # L'origine de la console : sans elle, l'ecriture serait refusee avant la route.
        r = c.post("/connexion", data={"motdepasse": "x"}, headers={"Origin": "http://testserver"})
        assert r.status_code == 405
    with pytest.raises(SystemExit) as exc:
        cli.principal(["motdepasse"])
    assert exc.value.code == 2
    assert "VEILLE_AUTH" not in config.VARIABLES_CONNUES


# --------------------------------------------------------------------------
# `veille passkeys` : voir, et retirer celle d'un appareil perdu
# --------------------------------------------------------------------------


def _ligne(sortie: str, passkey_id: int) -> str:
    return next(l for l in sortie.splitlines() if l.split()[:1] == [str(passkey_id)])


def test_veille_passkeys_les_liste_sans_leurs_secrets(capsys):
    _sans_passkey()
    android, id_android = _passkey("Android", utilisee_le="2026-11-03T08:00:00+00:00")
    windows, id_windows = _passkey("Windows")
    assert cli.principal(["passkeys"]) == 0
    sortie = capsys.readouterr().out
    ligne = _ligne(sortie, android)
    for attendu in ("Android", CREEE_LE, "2026-11-03T08:00:00+00:00"):
        assert attendu in ligne
    ligne = _ligne(sortie, windows)
    assert "Windows" in ligne and CREEE_LE in ligne and "jamais" in ligne
    assert id_android not in sortie and id_windows not in sortie


def test_veille_passkeys_sans_passkey(capsys):
    _sans_passkey()
    assert cli.principal(["passkeys"]) == 0
    assert "veille lien" in capsys.readouterr().out


def test_retirer_une_passkey_ferme_toutes_les_sessions(capsys):
    """Celui qui a ajoute sa passkey avec un cookie vole a aussi une session."""
    _sans_passkey()
    perdue, _ = _passkey("Android")
    gardee, _ = _passkey("Windows")
    jetons = [auth.ouvrir_session("Android"), auth.ouvrir_session("Windows")]
    assert cli.principal(["passkeys", "--retirer", str(perdue)]) == 0
    assert [p["id"] for p in db.lister_passkeys()] == [gardee]
    assert all(auth.lire_session(jeton) is None for jeton in jetons)
    assert f"Passkey {perdue} retirée" in capsys.readouterr().out


def test_retirer_un_id_inconnu_echoue_sans_rien_toucher(capsys):
    _sans_passkey()
    gardee, _ = _passkey("Android")
    jeton = auth.ouvrir_session("Android")
    assert cli.principal(["passkeys", "--retirer", "999999"]) == 1
    sortie = capsys.readouterr()
    assert "999999" in sortie.err
    assert "veille passkeys" in sortie.err
    assert [p["id"] for p in db.lister_passkeys()] == [gardee]
    assert auth.lire_session(jeton) is not None


def test_retirer_une_passkey_tout_ou_rien():
    """Un echec entre la suppression de la passkey et celle des sessions ne laisse rien
    de fait : la passkey est toujours la, les sessions aussi, et une relance marche."""
    _sans_passkey()
    perdue, _ = _passkey("Android")
    jeton = auth.ouvrir_session("Android")
    with db.connexion() as cx:
        cx.execute("CREATE TRIGGER sessions_intouchables BEFORE DELETE ON sessions"
                   " BEGIN SELECT RAISE(ABORT, 'sessions intouchables'); END")
    try:
        with pytest.raises(sqlite3.Error):
            auth.retirer_passkey(perdue)
        assert [p["id"] for p in db.lister_passkeys()] == [perdue]
        assert auth.lire_session(jeton) is not None
    finally:
        with db.connexion() as cx:
            cx.execute("DROP TRIGGER sessions_intouchables")
    assert auth.retirer_passkey(perdue) is True
    assert auth.lire_session(jeton) is None
