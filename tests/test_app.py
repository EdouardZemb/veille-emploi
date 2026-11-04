"""Tests de bout en bout de la console.

Ils existent parce qu'une erreur d'appel a Jinja2 avait rendu la page
principale inaccessible alors que toute l'API repondait correctement : les
tests unitaires ne voyaient rien, seul un appel HTTP reel le montrait.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from veille import auth, db
from veille.app import app
from veille.models import Offre
from veille.scoring import scorer

from tests.aide_session import connecter


@pytest.fixture(scope="module")
def client():
    db.initialiser()
    offre = scorer(
        Offre(
            titre="Test Automation Engineer",
            employeur="Exemplia",
            lieu="Basel, Switzerland",
            description="Playwright, CI/CD. English speaking team.",
            url="https://example.invalid/jobs/view/1",
            source="test",
            salaire_min=125000,
            salaire_max=140000,
            salaire_devise="CHF",
            type_contrat="CDI",
        )
    )
    db.enregistrer_offre(offre)
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def connecte(client):
    connecter(client)
    return client


# --------------------------------------------------------------------------
# Verrou
# --------------------------------------------------------------------------


def test_racine_redirige_vers_la_connexion_sans_session(client):
    client.cookies.clear()
    r = client.get("/")
    assert r.status_code == 303
    assert r.headers["location"] == "/connexion"


def test_api_refuse_sans_session(client):
    client.cookies.clear()
    assert client.get("/api/offres").status_code == 401
    assert client.get("/api/entonnoir").status_code == 401


def test_page_de_connexion_saffiche(client):
    client.cookies.clear()
    r = client.get("/connexion")
    assert r.status_code == 200
    assert "Veille emploi" in r.text


def test_une_session_en_base_ouvre_la_console(client):
    client.cookies.clear()
    connecter(client)
    assert client.get("/").status_code == 200


def test_une_session_fermee_ne_passe_plus(client):
    client.cookies.clear()
    jeton = connecter(client)
    assert client.get("/api/offres").status_code == 200
    auth.fermer_session(auth.lire_session(jeton)["id"])
    assert client.get("/api/offres").status_code == 401


def test_la_deconnexion_ferme_la_session_en_base(client):
    client.cookies.clear()
    jeton = connecter(client)
    r = client.post("/deconnexion")
    assert r.status_code == 303
    assert r.headers["location"] == "/connexion"
    assert db.session_par_empreinte(auth.empreinte(jeton)) is None


def test_une_session_prolongee_repose_le_cookie(client, horloge):
    client.cookies.clear()
    connecter(client)
    horloge.avancer(hours=2)
    r = client.get("/api/offres")
    assert r.status_code == 200
    assert r.headers.get("set-cookie", "").startswith(f"{auth.nom_cookie()}=")


def _cookies_de_session(reponse) -> list[str]:
    return [c for c in reponse.headers.get_list("set-cookie")
            if c.startswith(f"{auth.nom_cookie()}=")]


def test_le_lendemain_la_page_repose_le_cookie(client, horloge):
    """Le vrai parcours : l'application rouvre `/` le lendemain, puis appelle l'API.

    `/` lit la session et la prolonge en base : c'est elle qui doit reposer le
    cookie, sinon il expire au bout de 180 jours malgre l'usage."""
    client.cookies.clear()
    jeton = connecter(client)
    horloge.avancer(days=1)
    r = client.get("/")
    assert r.status_code == 200
    cookies = _cookies_de_session(r)
    assert len(cookies) == 1
    assert cookies[0].startswith(f"{auth.nom_cookie()}={jeton};")
    assert "Max-Age=15552000" in cookies[0]
    # La prolongation est ecrite : les appels suivants n'ont rien de plus a faire.
    r = client.get("/api/offres")
    assert r.status_code == 200
    assert _cookies_de_session(r) == []


def test_une_route_qui_rend_sa_reponse_repose_aussi_le_cookie(client, horloge):
    client.cookies.clear()
    jeton = connecter(client)
    autre = auth.lire_session(auth.ouvrir_session("Autre"))["id"]
    horloge.avancer(days=1)
    r = client.delete(f"/api/auth/sessions/{autre}")
    assert r.status_code == 200
    cookies = _cookies_de_session(r)
    assert len(cookies) == 1
    assert cookies[0].startswith(f"{auth.nom_cookie()}={jeton};")


@pytest.mark.parametrize("fermer", [
    lambda c, session_id: c.post("/deconnexion"),
    lambda c, session_id: c.delete(f"/api/auth/sessions/{session_id}"),
], ids=["deconnexion", "appareils"])
def test_une_session_fermee_ne_se_voit_pas_reposer_son_cookie(client, horloge, fermer):
    """Prolongee puis fermee dans la meme requete : le cookie s'efface, rien d'autre."""
    client.cookies.clear()
    jeton = connecter(client)
    session_id = auth.lire_session(jeton)["id"]
    horloge.avancer(days=1)
    r = fermer(client, session_id)
    cookies = _cookies_de_session(r)
    assert len(cookies) == 1
    assert "Max-Age=0" in cookies[0]
    assert db.session_par_empreinte(auth.empreinte(jeton)) is None


# --------------------------------------------------------------------------
# Page principale
# --------------------------------------------------------------------------


def test_la_console_saffiche_une_fois_connecte(connecte):
    """Regression : cette page rendait 500 (appel Jinja2 a l'ancienne
    signature) alors que toute l'API repondait normalement."""
    r = connecte.get("/")
    assert r.status_code == 200, r.text[:400]
    assert "Veille emploi" in r.text
    assert 'id="liste-offres"' in r.text


def test_la_console_liste_les_offres(connecte):
    d = connecte.get("/api/offres").json()
    assert d["offres"]
    o = d["offres"][0]
    assert o["titre"] == "Test Automation Engineer"
    assert o["explication"], "l'explication du score doit accompagner l'offre"


# --------------------------------------------------------------------------
# Tri
# --------------------------------------------------------------------------


def test_ecarter_exige_un_motif(connecte):
    oid = connecte.get("/api/offres").json()["offres"][0]["id"]
    r = connecte.post(f"/api/offres/{oid}/statut", json={"statut": "ecartee"})
    assert r.status_code == 400


def test_offre_ecartee_ne_remonte_jamais(connecte):
    oid = connecte.get("/api/offres").json()["offres"][0]["id"]
    r = connecte.post(
        f"/api/offres/{oid}/statut", json={"statut": "ecartee", "motif": "trop junior"}
    )
    assert r.status_code == 200
    restantes = [o["id"] for o in connecte.get("/api/offres").json()["offres"]]
    assert oid not in restantes
    avec = [o["id"] for o in connecte.get("/api/offres?inclure_ecartees=true").json()["offres"]]
    assert oid in avec


def test_statut_inconnu_refuse(connecte):
    oid = connecte.get("/api/offres?inclure_ecartees=true").json()["offres"][0]["id"]
    assert connecte.post(f"/api/offres/{oid}/statut", json={"statut": "n_importe_quoi"}).status_code == 400


# --------------------------------------------------------------------------
# Dossier de candidature
# --------------------------------------------------------------------------


def test_generation_du_dossier(connecte):
    oid = connecte.get("/api/offres?inclure_ecartees=true").json()["offres"][0]["id"]
    d = connecte.post(f"/api/offres/{oid}/dossier").json()
    assert "fiche-offre.md" in d["fichiers"]
    assert d["kit_provisoire"] is True
    assert any("provisoire" in a.lower() for a in d["avertissements"])
    archive = connecte.get(f"/api/offres/{oid}/dossier/archive")
    assert archive.status_code == 200
    assert archive.content[:2] == b"PK"


def test_dossier_refuse_de_sortir_de_son_repertoire(connecte):
    oid = connecte.get("/api/offres?inclure_ecartees=true").json()["offres"][0]["id"]
    connecte.post(f"/api/offres/{oid}/dossier")
    r = connecte.get(f"/api/offres/{oid}/dossier/..%2F..%2F..%2Fetc%2Fpasswd")
    assert r.status_code == 404


# --------------------------------------------------------------------------
# PWA et pilotage
# --------------------------------------------------------------------------


def test_le_manifeste_et_le_service_worker_sont_servis(client):
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200
    assert m.json()["display"] == "standalone"
    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "showNotification" in sw.text


def test_entonnoir(connecte):
    e = connecte.get("/api/entonnoir").json()
    assert "par_statut" in e and "par_source" in e
    assert e["total"] >= 1


# --------------------------------------------------------------------------
# Sante : le contrat du modele (M-0003)
# --------------------------------------------------------------------------


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; "
       "frame-ancestors 'none'; form-action 'self'")


@pytest.mark.parametrize("chemin", ["/connexion", "/sante", "/api/offres", "/static/app.js"])
def test_les_en_tetes_de_securite(client, chemin):
    client.cookies.clear()
    connecter(client)
    r = client.get(chemin)
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["referrer-policy"] == "same-origin"


def test_un_refus_porte_aussi_les_en_tetes(client, horloge):
    """Le 403 de l'origine et le 429 du debit sont enveloppes par le middleware."""
    r = client.post("/api/auth/connexion/options", headers={"Origin": "https://ailleurs.example"})
    assert r.status_code == 403
    assert r.headers["content-security-policy"] == CSP
    for _ in range(21):
        r = client.post("/api/auth/connexion/options", headers={"Origin": "http://testserver"})
    assert r.status_code == 429
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["referrer-policy"] == "same-origin"


def test_sante_au_contrat(client, monkeypatch):
    monkeypatch.setenv("VEILLE_EMPLOI_ENV", "staging")
    monkeypatch.setenv("VEILLE_EMPLOI_VERSION", "1.2.3")
    monkeypatch.setenv("REVISION", "abc123")
    r = client.get("/sante")
    assert r.status_code == 200
    assert r.json() == {
        "statut": "ok",
        "environnement": "staging",
        "version": "1.2.3",
        "revision": "abc123",
        "configuration": "montee",
    }


def test_sante_nue(client, monkeypatch):
    for nom in ("VEILLE_EMPLOI_ENV", "VEILLE_EMPLOI_VERSION", "REVISION"):
        monkeypatch.delenv(nom, raising=False)
    r = client.get("/sante")
    assert r.status_code == 200
    assert r.json() == {
        "statut": "ok",
        "environnement": "local",
        "version": "dev",
        "revision": "inconnue",
        "configuration": "montee",
    }


def test_sante_base_perdue(client, monkeypatch):
    monkeypatch.setattr(db, "base_ouverte", lambda: False)
    r = client.get("/sante")
    assert r.status_code == 503
    corps = r.json()
    assert corps["statut"] == "ko"
    assert set(corps) == {"statut", "environnement", "version", "revision", "configuration"}


def test_sante_sans_session_ni_origine():
    # Un client neuf : ni cookie, ni en-tete Origin.
    with TestClient(app, follow_redirects=False) as neuf:
        r = neuf.get("/sante")
    assert "origin" not in r.request.headers
    assert r.status_code == 200


def test_atout_mis_en_avant_expose(connecte, monkeypatch, request, tmp_path):
    """La console reçoit la clé, le libellé et le titre configurés, pas une constante du JS."""
    import html
    import json
    import re

    from tests.aide_criteres import poser_criteres

    def modifier(brut):
        for atout in brut["atouts"].values():
            atout.pop("mis_en_avant", None)
        brut["atouts"]["outils_test"]["mis_en_avant"] = {
            "libelle": "Libellé du test", "titre": "Titre du test"}

    poser_criteres(monkeypatch, request, tmp_path, modifier)
    page = connecte.get("/").text
    brut = re.search(r"data-atout='([^']*)'", page).group(1)
    assert json.loads(html.unescape(brut)) == {
        "cle": "outils_test", "libelle": "Libellé du test", "titre": "Titre du test",
        # sans texte propre, le bouton reprend ceux de l'étiquette
        "bouton": "Libellé du test", "bouton_titre": "Titre du test"}


def test_aucun_atout_mis_en_avant(connecte, monkeypatch, request, tmp_path):
    from tests.aide_criteres import poser_criteres

    def modifier(brut):
        for atout in brut["atouts"].values():
            atout.pop("mis_en_avant", None)

    poser_criteres(monkeypatch, request, tmp_path, modifier)
    assert "data-atout='null'" in connecte.get("/").text


def test_le_bouton_de_l_atout_vient_de_la_configuration(connecte, monkeypatch, request, tmp_path):
    """Le texte et l'infobulle du bouton sont ceux de l'atout mis en avant, pas du gabarit."""
    import html
    import re
    from pathlib import Path

    from tests.aide_criteres import poser_criteres

    gabarit = (Path(__file__).resolve().parents[1] / "src" / "veille" / "templates"
               / "index.html").read_text(encoding="utf-8")
    assert "Accessibilité" not in gabarit
    assert "accessibilité numérique" not in gabarit

    def modifier(brut):
        for atout in brut["atouts"].values():
            atout.pop("mis_en_avant", None)
        brut["atouts"]["outils_test"]["mis_en_avant"] = {
            "libelle": "Étiquette inventée", "titre": "Titre inventé",
            "bouton": "Bouton inventé", "bouton_titre": "Infobulle inventée"}

    poser_criteres(monkeypatch, request, tmp_path, modifier)
    page = html.unescape(connecte.get("/").text)
    bouton = re.search(r'<button id="btn-atout"[^>]*>(.*?)</button>', page, re.S)
    assert 'title="Infobulle inventée"' in bouton.group(0)
    assert bouton.group(1).strip() == "Bouton inventé"
    assert " hidden" not in bouton.group(0).split(">")[0]


def test_sans_atout_mis_en_avant_le_bouton_est_cache(connecte, monkeypatch, request, tmp_path):
    import re

    from tests.aide_criteres import poser_criteres

    def modifier(brut):
        for atout in brut["atouts"].values():
            atout.pop("mis_en_avant", None)

    poser_criteres(monkeypatch, request, tmp_path, modifier)
    ouvrante = re.search(r'<button id="btn-atout"[^>]*>', connecte.get("/").text).group(0)
    assert " hidden" in ouvrante


def test_l_exemple_donne_au_bouton_le_libelle_et_le_titre_de_son_atout(connecte):
    """L'atout mis en avant de l'exemple n'a ni `bouton` ni `bouton_titre` : le
    bouton reprend son `libelle` et son `titre`."""
    import html
    import re

    from veille.config import charger_criteres

    infos = [a["mis_en_avant"] for a in charger_criteres().atouts.values()
             if a.get("mis_en_avant")]
    assert len(infos) == 1
    assert "bouton" not in infos[0] and "bouton_titre" not in infos[0]
    page = html.unescape(connecte.get("/").text)
    bouton = re.search(r'<button id="btn-atout"[^>]*>(.*?)</button>', page, re.S)
    assert bouton.group(1).strip() == "Accessibilité"
    assert "title=\"Offres qui demandent des tests d'accessibilité numérique\"" in bouton.group(0)
    assert " hidden" not in bouton.group(0).split(">")[0]
