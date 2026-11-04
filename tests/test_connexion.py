"""La connexion par passkey et par lien : les routes, l'origine et le debit.

Les reponses WebAuthn viennent de l'authentificateur logiciel : de vraies
signatures, verifiees par `webauthn`, a travers les routes de la console.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.aide_session import ORIGINE, connecter
from tests.authentificateur import AuthentificateurLogiciel
from veille import app as console
from veille import auth, db, passkeys


@pytest.fixture
def client():
    db.initialiser()
    # La base sert a toute la suite : chaque test part sans passkey.
    with db.connexion() as cx:
        cx.execute("DELETE FROM passkeys")
    with TestClient(console.app, follow_redirects=False) as c:
        c.headers["Origin"] = ORIGINE
        yield c
    passkeys.oublier_ceremonies()


def options_lien(client: TestClient, jeton: str):
    return client.post("/api/auth/lien/options", json={"jeton": jeton})


def inscrire(client: TestClient, cle_logicielle: AuthentificateurLogiciel, jeton: str | None = None):
    """Le parcours du lien : options, `create()`, puis l'envoi de la reponse."""
    debut = options_lien(client, jeton or auth.creer_lien("serveur")).json()
    reponse = cle_logicielle.inscrire(debut["options"], ORIGINE)
    return client.post("/api/auth/lien", json={"cle": debut["cle"], "reponse": reponse})


def se_connecter(client: TestClient, cle_logicielle: AuthentificateurLogiciel):
    debut = client.post("/api/auth/connexion/options").json()
    reponse = cle_logicielle.signer(debut["options"], ORIGINE)
    return client.post("/api/auth/connexion", json={"cle": debut["cle"], "reponse": reponse})


# --------------------------------------------------------------------------
# Le lien, puis la passkey
# --------------------------------------------------------------------------


def test_un_lien_ouvre_l_enregistrement_puis_la_session(client):
    assert client.get("/").status_code == 303
    r = inscrire(client, AuthentificateurLogiciel())
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert auth.nom_cookie() in r.cookies
    assert client.get("/").status_code == 200
    assert db.compter_passkeys() == 1


def test_un_lien_ne_sert_qu_une_fois(client):
    jeton = auth.creer_lien("serveur")
    assert inscrire(client, AuthentificateurLogiciel(), jeton).status_code == 200
    r = options_lien(client, jeton)
    assert r.status_code == 400
    assert r.json() == {"erreur": "lien_invalide"}


def test_le_double_appui_n_enregistre_qu_une_passkey(client):
    jeton = auth.creer_lien("serveur")
    # Deux appuis : deux ceremonies pour le meme lien, que les options ne consomment pas.
    premier = options_lien(client, jeton).json()
    second = options_lien(client, jeton).json()
    reponse_1 = AuthentificateurLogiciel().inscrire(premier["options"], ORIGINE)
    reponse_2 = AuthentificateurLogiciel().inscrire(second["options"], ORIGINE)
    r1 = client.post("/api/auth/lien", json={"cle": premier["cle"], "reponse": reponse_1})
    r2 =client.post("/api/auth/lien", json={"cle": second["cle"], "reponse": reponse_2})
    assert r1.status_code == 200
    assert r2.status_code == 400
    assert r2.json() == {"erreur": "lien_invalide"}
    assert auth.nom_cookie() not in r2.cookies
    assert db.compter_passkeys() == 1


def test_une_passkey_deja_enregistree_donne_lien_invalide(client):
    """Le meme identifiant, par un second lien : un refus, jamais une 500."""
    cle_logicielle = AuthentificateurLogiciel()
    assert inscrire(client, cle_logicielle).status_code == 200
    client.cookies.clear()
    r = inscrire(client, cle_logicielle)
    assert r.status_code == 400
    assert r.json() == {"erreur": "lien_invalide"}
    assert auth.nom_cookie() not in r.cookies
    assert db.compter_passkeys() == 1


def test_une_reponse_mal_formee_ne_dit_que_le_code(client):
    debut = options_lien(client, auth.creer_lien("serveur")).json()
    r = client.post("/api/auth/lien", json={"cle": debut["cle"], "reponse": {"id": "<x>"}})
    assert r.status_code == 400
    assert r.json() == {"erreur": "lien_invalide"}


# --------------------------------------------------------------------------
# La connexion
# --------------------------------------------------------------------------


def test_la_connexion_par_passkey(client):
    cle_logicielle = AuthentificateurLogiciel()
    assert inscrire(client, cle_logicielle).status_code == 200
    client.cookies.clear()
    assert client.get("/").status_code == 303
    r = se_connecter(client, cle_logicielle)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert client.get("/").status_code == 200


def test_une_passkey_inconnue_donne_connexion_impossible(client):
    assert inscrire(client, AuthentificateurLogiciel()).status_code == 200
    client.cookies.clear()
    r = se_connecter(client, AuthentificateurLogiciel())
    assert r.status_code == 400
    assert r.json() == {"erreur": "connexion_impossible"}
    assert auth.nom_cookie() not in r.cookies


def test_sans_veille_url_la_connexion_est_indisponible(client, monkeypatch):
    jeton = auth.creer_lien("serveur")
    monkeypatch.delenv("VEILLE_URL", raising=False)
    for r in (client.post("/api/auth/connexion/options"), options_lien(client, jeton)):
        assert r.status_code == 503
        assert r.json() == {"erreur": "origine_inconnue"}


def test_un_lien_qui_expire_pendant_la_ceremonie(client, horloge):
    """Les options sont prises quand le lien vaut encore ; il expire avant la reponse
    (la ceremonie, elle, dure 5 minutes) : rien n'est enregistre."""
    jeton = auth.creer_lien("serveur")
    horloge.avancer(hours=23, minutes=58)
    debut = options_lien(client, jeton).json()
    reponse = AuthentificateurLogiciel().inscrire(debut["options"], ORIGINE)
    horloge.avancer(minutes=3)
    r = client.post("/api/auth/lien", json={"cle": debut["cle"], "reponse": reponse})
    assert r.status_code == 400
    assert r.json() == {"erreur": "lien_invalide"}
    assert db.compter_passkeys() == 0
    assert auth.nom_cookie() not in r.cookies


# --------------------------------------------------------------------------
# L'origine
# --------------------------------------------------------------------------


def test_une_origine_etrangere_est_refusee(client):
    connecter(client)
    r = client.post("/api/offres/1/statut", json={"statut": "ecartee"},
                    headers={"Origin": "https://ailleurs.example"})
    assert r.status_code == 403
    assert r.json() == {"erreur": "origine"}


def test_une_requete_sans_origine_est_refusee(client):
    del client.headers["Origin"]
    r = client.post("/api/auth/connexion/options")
    assert r.status_code == 403
    assert r.json() == {"erreur": "origine"}


def test_une_lecture_ne_demande_pas_d_origine(client):
    connecter(client)
    del client.headers["Origin"]
    assert client.get("/api/offres").status_code == 200


def test_sans_veille_url_une_ecriture_hors_connexion_est_refusee(client, monkeypatch):
    """L'origine attendue est inconnue : le controle n'a pas pu tourner, rien ne passe."""
    connecter(client)
    monkeypatch.delenv("VEILLE_URL", raising=False)
    r = client.post("/api/offres/1/statut", json={"statut": "ecartee"})
    assert r.status_code == 403
    assert r.json() == {"erreur": "origine"}


@pytest.mark.parametrize("entetes", [{"Origin": "https://ailleurs.example"}, {"Origin": ""}],
                         ids=["etrangere", "absente"])
def test_la_deconnexion_exige_aussi_l_origine(client, entetes):
    """Toute ecriture, pas seulement sous /api/ : une page etrangere ne ferme pas la session."""
    jeton = connecter(client)
    if not entetes["Origin"]:
        del client.headers["Origin"]
        entetes = {}
    r = client.post("/deconnexion", headers=entetes)
    assert r.status_code == 403
    assert r.json() == {"erreur": "origine"}
    assert auth.lire_session(jeton) is not None


def test_la_deconnexion_de_la_console_elle_meme_passe(client):
    jeton = connecter(client)
    r = client.post("/deconnexion")
    assert r.status_code == 303
    assert auth.lire_session(jeton) is None


# --------------------------------------------------------------------------
# Le debit
# --------------------------------------------------------------------------


def test_au_dela_de_20_demandes_par_minute(client):
    statuts = [client.post("/api/auth/connexion/options").status_code for _ in range(20)]
    assert statuts == [200] * 20
    r = client.post("/api/auth/connexion/options")
    assert r.status_code == 429
    assert r.json() == {"erreur": "trop_de_demandes"}


def test_un_client_qui_martele_ne_bloque_pas_les_autres(client, horloge):
    """Les demandes refusees pour le client ne touchent pas le plafond global."""
    haut = {"CF-Connecting-IP": "203.0.113.7"}
    statuts = [client.post("/api/auth/connexion/options", headers=haut).status_code
               for _ in range(230)]
    assert statuts == [200] * 20 + [429] * 210
    r = client.post("/api/auth/connexion/options", headers={"CF-Connecting-IP": "203.0.113.8"})
    assert r.status_code == 200


def test_le_plafond_global_bloque_tous_les_clients(client, horloge):
    for i in range(10):
        for _ in range(20):
            r = client.post("/api/auth/connexion/options",
                            headers={"CF-Connecting-IP": f"203.0.113.{i}"})
            assert r.status_code == 200
    r = client.post("/api/auth/connexion/options", headers={"CF-Connecting-IP": "203.0.113.99"})
    assert r.status_code == 429


def test_une_demande_refusee_par_le_plafond_ne_compte_pas_pour_le_client(client, horloge):
    for i in range(10):
        for _ in range(20):
            client.post("/api/auth/connexion/options",
                        headers={"CF-Connecting-IP": f"203.0.113.{i}"})
    neuf = {"CF-Connecting-IP": "203.0.113.99"}
    assert client.post("/api/auth/connexion/options", headers=neuf).status_code == 429
    assert console.LIMITE_AUTH.nombre_de_cles() == 10
    horloge.avancer(seconds=61)
    assert client.post("/api/auth/connexion/options", headers=neuf).status_code == 200


def _attributs(entete: str) -> list[str]:
    return [a.strip().lower() for a in entete.split(";")]


def test_le_cookie_host_sous_https(client, monkeypatch):
    monkeypatch.setenv("VEILLE_HTTPS", "1")
    assert auth.nom_cookie() == "__Host-veille_session"
    r = inscrire(client, AuthentificateurLogiciel())
    assert r.status_code == 200, r.text
    entete = r.headers["set-cookie"]
    assert entete.startswith("__Host-veille_session=")
    attributs = _attributs(entete)
    for attendu in ("httponly", "path=/", "samesite=lax", "secure"):
        assert attendu in attributs
    assert not any(a.startswith("domain") for a in attributs)
    jeton = entete.split("=", 1)[1].split(";", 1)[0]
    # httpx n'enverrait pas un cookie Secure sur http://testserver : on l'envoie a la main.
    client.cookies.clear()
    assert client.get("/", headers={"Cookie": f"__Host-veille_session={jeton}"}).status_code == 200
    assert client.get("/").status_code == 303


def test_la_deconnexion_efface_le_cookie_host(client, monkeypatch):
    """Sans `Secure` ni `Path=/`, le navigateur ignore l'effacement d'un cookie `__Host-`."""
    monkeypatch.setenv("VEILLE_HTTPS", "1")
    jeton = connecter(client)
    client.cookies.clear()
    r = client.post("/deconnexion", headers={"Cookie": f"__Host-veille_session={jeton}"})
    assert r.status_code == 303
    entete = r.headers["set-cookie"]
    assert entete.startswith("__Host-veille_session=")
    attributs = _attributs(entete)
    assert "secure" in attributs and "path=/" in attributs
    assert not any(a.startswith("domain") for a in attributs)
    assert "max-age=0" in attributs
    assert auth.lire_session(jeton) is None


def test_l_api_efface_le_cookie_host_de_la_session_courante(client, monkeypatch):
    monkeypatch.setenv("VEILLE_HTTPS", "1")
    jeton = auth.ouvrir_session("test")
    courante = auth.lire_session(jeton)["id"]
    r = client.delete(f"/api/auth/sessions/{courante}",
                      headers={"Cookie": f"__Host-veille_session={jeton}"})
    assert r.status_code == 200
    assert r.headers["set-cookie"].startswith("__Host-veille_session=")
    attributs = _attributs(r.headers["set-cookie"])
    assert "secure" in attributs and "path=/" in attributs


def test_une_requete_refusee_pour_l_origine_ne_compte_pas(client):
    """L'origine passe avant la limite : une page etrangere n'use pas le budget."""
    for _ in range(25):
        r = client.post("/api/auth/connexion/options",
                        headers={"Origin": "https://ailleurs.example"})
        assert r.status_code == 403
    assert client.post("/api/auth/connexion/options").status_code == 200


def test_le_budget_anonyme_ne_bloque_pas_une_session_ouverte(client):
    """Seules les quatre routes anonymes comptent : qui use le budget n'enferme
    pas dehors une session deja ouverte."""
    for _ in range(20):
        assert client.post("/api/auth/connexion/options").status_code == 200
    assert client.post("/api/auth/connexion/options").status_code == 429
    connecter(client)
    autre = auth.lire_session(auth.ouvrir_session("Autre"))["id"]
    assert client.get("/api/auth/appareils").status_code == 200
    # Budget anonyme use : c'est l'obtention des options (connexion/options) qui est
    # bloquee ; lien/creer n'est jamais limite, il repond 400 faute de touche, pas 429.
    assert client.post("/api/auth/lien/creer", json={}).status_code == 400
    assert client.delete(f"/api/auth/sessions/{autre}").status_code == 200


def test_une_lecture_n_use_pas_le_budget(client):
    connecter(client)
    for _ in range(25):
        assert client.get("/api/auth/appareils").status_code == 200
    statuts = [client.post("/api/auth/connexion/options").status_code for _ in range(20)]
    assert statuts == [200] * 20


# --------------------------------------------------------------------------
# Les pages
# --------------------------------------------------------------------------


def test_les_pages_de_connexion(client):
    r = client.get("/connexion")
    assert r.status_code == 200
    assert 'id="btn-passkey"' in r.text
    assert 'id="message"' in r.text
    assert "connexion.js" in r.text
    r = client.get("/lien")
    assert r.status_code == 200
    assert 'id="btn-enregistrer"' in r.text
    assert 'id="message"' in r.text
    assert "connexion.js" in r.text


@pytest.mark.parametrize("etat, attendu", [
    ("sans_origine", "La connexion est indisponible"),
    ("sans_passkey", "veille lien"),
    ("avec_passkey", "Se connecter avec une passkey"),
])
def test_page_connexion_trois_etats(client, monkeypatch, etat, attendu):
    if etat == "sans_origine":
        monkeypatch.delenv("VEILLE_URL")
    if etat == "avec_passkey":
        inscrire(client, AuthentificateurLogiciel())
        client.cookies.clear()
    r = client.get("/connexion")
    assert r.status_code == 200
    assert attendu in r.text
    assert ("Aucune passkey" in r.text) == (etat == "sans_passkey")
    assert ("La connexion est indisponible" in r.text) == (etat == "sans_origine")


def test_lien_creer_sans_origine(client, monkeypatch):
    connecter(client)
    monkeypatch.delenv("VEILLE_URL")
    r = client.post("/api/auth/lien/creer")
    assert r.status_code == 503
    assert r.json() == {"erreur": "origine_inconnue"}
