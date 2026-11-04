"""Les appareils : voir ses sessions et ses passkeys, deconnecter une session, creer un lien."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from tests.aide_session import ORIGINE, connecter
from tests.authentificateur import AuthentificateurLogiciel, b64url
from veille import app as console
from veille import auth, db


@pytest.fixture
def client():
    db.initialiser()
    with TestClient(console.app, follow_redirects=False) as c:
        yield c


def test_la_liste_marque_la_session_courante(client):
    connecter(client)
    r = client.get("/api/auth/appareils")
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    assert sessions
    courantes = [s for s in sessions if s["courante"]]
    assert len(courantes) == 1
    assert courantes[0]["appareil"] == "test"
    assert set(courantes[0]) == {"id", "appareil", "cree_le", "vue_le", "courante"}


def test_une_session_expiree_n_est_pas_listee(client, horloge):
    """Pas de purge dans ce lot : la ligne reste en base, mais ne s'affiche plus."""
    ancienne = auth.ouvrir_session("Ancien")
    horloge.avancer(days=100)
    connecter(client)
    horloge.avancer(days=81)  # 181 jours sans usage pour l'ancienne, 81 pour la courante
    id_ancienne = db.session_par_empreinte(auth.empreinte(ancienne))["id"]
    sessions = client.get("/api/auth/appareils").json()["sessions"]
    assert id_ancienne not in {s["id"] for s in sessions}
    assert [s for s in sessions if s["courante"]]
    assert client.delete(f"/api/auth/sessions/{id_ancienne}").status_code == 404


def test_deconnecter_un_autre_appareil(client):
    courant = connecter(client)
    autre = auth.ouvrir_session("Autre")
    id_autre = auth.lire_session(autre)["id"]
    r = client.delete(f"/api/auth/sessions/{id_autre}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert auth.lire_session(autre) is None
    assert auth.lire_session(courant) is not None
    assert client.get("/api/auth/appareils").status_code == 200


def test_deconnecter_la_session_courante_efface_le_cookie(client):
    jeton = connecter(client)
    id_courant = auth.lire_session(jeton)["id"]
    r = client.delete(f"/api/auth/sessions/{id_courant}")
    assert r.status_code == 200
    assert auth.nom_cookie() in r.headers.get("set-cookie", "")
    assert "Max-Age=0" in r.headers["set-cookie"]
    assert auth.lire_session(jeton) is None


def test_une_session_inconnue_donne_404(client):
    connecter(client)
    assert client.delete("/api/auth/sessions/999999").status_code == 404


def _passkey_enregistree(client) -> AuthentificateurLogiciel:
    """Une passkey connue de la base, enregistree par le lien du serveur."""
    client.headers["Origin"] = ORIGINE
    with db.connexion() as cx:
        cx.execute("DELETE FROM passkeys")
    cle = AuthentificateurLogiciel()
    debut = client.post("/api/auth/lien/options", json={"jeton": auth.creer_lien("serveur")}).json()
    reponse = cle.inscrire(debut["options"], ORIGINE)
    r = client.post("/api/auth/lien", json={"cle": debut["cle"], "reponse": reponse})
    assert r.status_code == 200
    client.cookies.clear()
    return cle


def _touche(client, cle: AuthentificateurLogiciel) -> dict:
    """Le corps que le navigateur envoie apres une touche de passkey."""
    debut = client.post("/api/auth/connexion/options").json()
    return {"cle": debut["cle"], "reponse": cle.signer(debut["options"], ORIGINE)}


def _liens_ouverts() -> list[dict]:
    return db.liens_ouverts("0000")


def test_ajouter_un_appareil_exige_une_touche(client):
    connecter(client)
    avant = len(_liens_ouverts())
    # Sans corps : FastAPI refuse (422) ; un corps vide : la ceremonie manque (400).
    assert client.post("/api/auth/lien/creer").status_code == 422
    r = client.post("/api/auth/lien/creer", json={})
    assert r.status_code == 400
    assert r.json() == {"erreur": "connexion_impossible"}
    assert len(_liens_ouverts()) == avant


def test_ajouter_un_appareil_avec_une_touche(client):
    cle = _passkey_enregistree(client)
    connecter(client)
    avant = len(_liens_ouverts())
    cookies = dict(client.cookies)
    r = client.post("/api/auth/lien/creer", json=_touche(client, cle))
    assert r.status_code == 200
    corps = r.json()
    assert set(corps) == {"adresse", "expire_le"}
    assert corps["adresse"].startswith("http://testserver/lien#")
    assert corps["expire_le"]
    # Pas de nouvelle session : la touche ne fait que prouver la presence.
    assert "set-cookie" not in r.headers
    assert dict(client.cookies) == cookies
    jeton = corps["adresse"].split("#", 1)[1]
    lien_id = auth.lien_ouvert(jeton)
    assert lien_id is not None
    liens = {lien["id"]: lien for lien in _liens_ouverts()}
    assert len(liens) == avant + 1
    assert liens[lien_id]["origine"] == "appareil"
    assert liens[lien_id]["expire_le"] == corps["expire_le"]


def test_ajouter_un_appareil_cle_inconnue(client):
    _passkey_enregistree(client)
    connecter(client)
    avant = len(_liens_ouverts())
    r = client.post("/api/auth/lien/creer", json=_touche(client, AuthentificateurLogiciel()))
    assert r.status_code == 400
    assert r.json() == {"erreur": "connexion_impossible"}
    assert len(_liens_ouverts()) == avant


def test_ajouter_un_appareil_ceremonie_rejouee(client):
    cle = _passkey_enregistree(client)
    connecter(client)
    avant = len(_liens_ouverts())
    corps = _touche(client, cle)
    assert client.post("/api/auth/lien/creer", json=corps).status_code == 200
    r = client.post("/api/auth/lien/creer", json=corps)
    assert r.status_code == 400
    assert r.json() == {"erreur": "connexion_impossible"}
    assert len(_liens_ouverts()) == avant + 1


def test_les_appareils_exigent_une_session(client):
    client.headers["Origin"] = "http://testserver"
    assert client.get("/api/auth/appareils").status_code == 401
    assert client.delete("/api/auth/sessions/1").status_code == 401
    assert client.post("/api/auth/lien/creer").status_code == 401


def test_la_liste_montre_les_passkeys_sans_leurs_secrets(client):
    """En lecture seule, pour qu'une passkey inconnue se remarque. Jamais la cle
    publique ni l'identifiant WebAuthn."""
    with db.connexion() as cx:
        cx.execute("DELETE FROM passkeys")
    identifiant = b64url(os.urandom(16))
    cle_publique = os.urandom(32)
    passkey_id = db.enregistrer_passkey(identifiant, cle_publique, 0, ["internal"], "Android",
                                        "2026-11-02T09:00:00+00:00")
    connecter(client)
    r = client.get("/api/auth/appareils")
    assert r.status_code == 200
    assert r.json()["passkeys"] == [{
        "id": passkey_id,
        "appareil": "Android",
        "cree_le": "2026-11-02T09:00:00+00:00",
        "utilisee_le": None,
    }]
    assert identifiant not in r.text
    assert b64url(cle_publique) not in r.text
