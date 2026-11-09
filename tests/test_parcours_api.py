"""Les routes en lecture du parcours : « À faire », « Candidatures », motifs fréquents."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from veille import db, reglages
from veille.app import app
from veille.models import Offre
from veille.scoring import scorer

from tests.aide_session import connecter


@pytest.fixture(scope="module")
def client():
    db.initialiser()
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def connecte(client):
    connecter(client)
    return client


def _offre(statut="nouveau", score=None, **champs) -> int:
    jeton = uuid.uuid4().hex
    offre = scorer(
        Offre(
            titre=f"Poste inventé {jeton}",
            employeur=f"Société inventée {jeton[:8]}",
            lieu="Basel, Switzerland",
            description="Description inventée.",
            url=f"https://offres.exemple.invalid/parcours/{jeton}",
            source="test",
        )
    )
    offre_id, _ = db.enregistrer_offre(offre)
    if statut != "nouveau":
        db.changer_statut(offre_id, statut, motif=champs.pop("motif", None))
    if score is not None:
        with db.connexion() as cx:
            cx.execute("UPDATE offres SET score = ? WHERE id = ?", (score, offre_id))
    if champs:
        db.maj_champs(offre_id, **champs)
    return offre_id


def _ids(liste):
    return {o["id"] for o in liste}


def test_les_routes_du_parcours_exigent_la_session(client):
    client.cookies.clear()
    for chemin in ("/api/a-faire", "/api/candidatures", "/api/motifs"):
        assert client.get(chemin).status_code == 401


def test_a_faire_range_chaque_offre_dans_son_groupe(connecte):
    s = reglages.lire_seuil()
    haute = _offre(score=s + 10)
    basse = _offre(score=s - 10)
    a_traiter = _offre("a_traiter", score=s + 5)
    interessante = _offre("interessante", score=s + 5)
    r = connecte.get("/api/a-faire")
    assert r.status_code == 200
    d = r.json()
    assert d["seuil"] == s
    assert haute in _ids(d["a_voir"])
    assert basse not in _ids(d["a_voir"])
    assert d["sous_le_seuil"] >= 1
    assert a_traiter in _ids(d["plus_tard"])
    fini = {o["id"]: o for o in d["a_finir"]}
    assert fini[interessante]["raison"] == "a_preparer"


def test_une_candidature_archivee_reste_suivie(connecte):
    s = reglages.lire_seuil()
    hier = (date.today() - timedelta(days=1)).isoformat()
    envoyee = _offre("candidature_envoyee", score=s + 5)
    db.maj_champs(envoyee, date_relance_due=hier)
    db.archiver(envoyee, "retirée du site")
    nouvelle = _offre(score=s + 10)
    db.archiver(nouvelle, "retirée du site")
    d = connecte.get("/api/a-faire").json()
    fini = {o["id"]: o for o in d["a_finir"]}
    assert fini[envoyee]["raison"] == "relance_due"
    assert nouvelle not in _ids(d["a_voir"])
    assert envoyee in _ids(connecte.get("/api/candidatures").json()["envoyee"])


def test_candidatures_groupe_les_trois_etats(connecte):
    a = _offre("interessante", score=50)
    b = _offre("reponse_recue", score=50)
    c = _offre("entretien", score=50)
    e = _offre("refus", score=50)
    d = connecte.get("/api/candidatures").json()
    assert a in _ids(d["je_postule"])
    assert b in _ids(d["envoyee"])
    assert c in _ids(d["entretien"])
    tous = _ids(d["je_postule"]) | _ids(d["envoyee"]) | _ids(d["entretien"])
    assert e not in tous


def test_les_motifs_frequents_sans_les_automatiques(connecte):
    for _ in range(3):
        _offre("ecartee", motif="motif inventé A")
    for _ in range(2):
        _offre("ecartee", motif="motif inventé B")
    _offre("ecartee", motif=db.PREFIXE_AUTOMATIQUE + "motif inventé C")
    motifs = connecte.get("/api/motifs?limite=20").json()["motifs"]
    assert motifs.index("motif inventé A") < motifs.index("motif inventé B")
    assert not any(m.startswith(db.PREFIXE_AUTOMATIQUE) for m in motifs)
    assert len(connecte.get("/api/motifs?limite=0").json()["motifs"]) <= 1


def test_la_limite_des_motifs_est_bornee(connecte):
    assert len(connecte.get("/api/motifs?limite=99").json()["motifs"]) <= 20


def test_l_offre_porte_son_etat(connecte):
    i = _offre("interessante", score=50)
    assert connecte.get(f"/api/offres/{i}").json()["etat"] == "je_postule"
    offres = connecte.get("/api/offres").json()["offres"]
    assert offres and all("etat" in o for o in offres)
