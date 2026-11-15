"""Les routes en lecture du parcours : « À faire », « Candidatures », motifs fréquents."""

from __future__ import annotations

import inspect
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from veille import app as app_module
from veille import db, reglages
from veille.app import app
from veille.models import Offre
from veille.scoring import scorer

from tests.aide_session import connecter


@pytest.fixture(autouse=True)
def _base_propre(tmp_path, monkeypatch):
    """Une base neuve par test : les offres ne restent pas pour les autres fichiers."""
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    db.initialiser()


@pytest.fixture
def client(_base_propre):
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
    """21 motifs distincts : la limite demandée est ramenée entre 1 et 20."""
    for n in range(21):
        _offre("ecartee", motif=f"motif inventé {n:02d}")
    assert len(connecte.get("/api/motifs?limite=99").json()["motifs"]) == 20
    assert len(connecte.get("/api/motifs?limite=0").json()["motifs"]) == 1


def test_l_offre_porte_son_etat(connecte):
    i = _offre("interessante", score=50)
    assert connecte.get(f"/api/offres/{i}").json()["etat"] == "je_postule"
    offres = connecte.get("/api/offres").json()["offres"]
    assert offres and all("etat" in o for o in offres)


_STATUTS_DES_FILTRES = {
    "a_voir": ("nouveau", "a_traiter"),
    "je_postule": ("interessante",),
    "envoyee": ("candidature_envoyee", "relance_envoyee", "reponse_recue"),
    "entretien": ("entretien",),
    "close": ("ecartee", "refus", "accepte"),
    "mise_de_cote": ("differee",),
}
_TOUS_LES_STATUTS = (
    "nouveau", "a_traiter", "interessante", "candidature_envoyee", "relance_envoyee",
    "reponse_recue", "entretien", "ecartee", "refus", "accepte", "differee",
)


def _une_offre_par_statut() -> dict[str, int]:
    return {
        s: _offre(s, motif="motif inventé" if s in ("ecartee", "refus") else None)
        for s in _TOUS_LES_STATUTS
    }


@pytest.mark.parametrize("filtre", list(_STATUTS_DES_FILTRES))
def test_le_filtre_d_etat_rend_les_offres_de_cet_etat(connecte, filtre):
    par_statut = _une_offre_par_statut()
    attendus = {par_statut[s] for s in _STATUTS_DES_FILTRES[filtre]}
    offres = connecte.get(f"/api/offres?etat={filtre}&limite=500").json()["offres"]
    assert _ids(offres) == attendus
    assert all(o["etat"] == filtre for o in offres)


def test_sans_etat_la_liste_rend_les_offres_en_cours(connecte):
    par_statut = _une_offre_par_statut()
    ids = _ids(connecte.get("/api/offres?limite=500").json()["offres"])
    for s in ("ecartee", "refus", "accepte", "differee"):
        assert par_statut[s] not in ids
    for s in ("nouveau", "a_traiter", "interessante", "candidature_envoyee",
              "relance_envoyee", "reponse_recue", "entretien"):
        assert par_statut[s] in ids


def test_un_etat_vide_vaut_aucun_etat(connecte):
    _une_offre_par_statut()
    sans = _ids(connecte.get("/api/offres?limite=500").json()["offres"])
    vide = _ids(connecte.get("/api/offres?etat=&limite=500").json()["offres"])
    assert vide == sans and sans


def test_inclure_ecartees_rend_toujours_tout(connecte):
    par_statut = _une_offre_par_statut()
    ids = _ids(connecte.get("/api/offres?inclure_ecartees=true&limite=500").json()["offres"])
    assert ids == set(par_statut.values()) and len(ids) == 11


def _chez(employeur: str, statut: str, **champs) -> int:
    """Une offre inventée d'un employeur donné (`maj_champs` ne touche pas l'employeur)."""
    offre_id = _offre(statut, **champs)
    with db.connexion() as cx:
        cx.execute("UPDATE offres SET employeur = ? WHERE id = ?", (employeur, offre_id))
    return offre_id


def test_une_recherche_sans_etat_trouve_les_closes_mais_pas_les_archivees(connecte):
    employeur = "Employeur inventé commun"
    refusee = _chez(employeur, "refus")
    de_cote = _chez(employeur, "differee")
    en_cours = _chez(employeur, "interessante")
    archivee = _chez(employeur, "ecartee", motif="motif inventé")
    db.archiver(archivee, "annonce retirée")
    _chez("Autre employeur inventé", "interessante")
    r = connecte.get(
        "/api/offres", params={"recherche": employeur, "inclure_ecartees": "true"}
    ).json()
    assert _ids(r["offres"]) == {refusee, de_cote, en_cours}
    assert r["total"] == 3


def test_etat_et_statut_se_combinent(connecte):
    par_statut = _une_offre_par_statut()
    r = connecte.get("/api/offres?etat=envoyee&statut=reponse_recue").json()
    assert _ids(r["offres"]) == {par_statut["reponse_recue"]}
    assert r["total"] == 1
    r = connecte.get("/api/offres?etat=close&statut=interessante").json()
    assert r["offres"] == [] and r["total"] == 0


def test_un_statut_seul_garde_son_sens(connecte):
    par_statut = _une_offre_par_statut()
    r = connecte.get("/api/offres?statut=refus").json()
    assert _ids(r["offres"]) == {par_statut["refus"]}
    r = connecte.get("/api/offres?statut=ecartee").json()
    assert _ids(r["offres"]) == {par_statut["ecartee"]}


def test_un_etat_inconnu_rend_400(connecte):
    reponse = connecte.get("/api/offres?etat=plus_tard")
    assert reponse.status_code == 400
    assert "état inconnu" in reponse.text


def test_une_archivee_reste_hors_du_filtre(connecte):
    archivee = _offre("ecartee", motif="motif inventé")
    gardee = _offre("refus")
    db.archiver(archivee, "annonce retirée")
    ids = _ids(connecte.get("/api/offres?etat=close").json()["offres"])
    assert ids == {gardee}


def test_la_liste_dit_son_vrai_nombre(connecte):
    _une_offre_par_statut()
    r = connecte.get("/api/offres?etat=close&limite=2").json()
    assert len(r["offres"]) == 2 and r["total"] == 3
    r = connecte.get("/api/offres?etat=close").json()
    assert len(r["offres"]) == 3 and r["total"] == 3
    r = connecte.get("/api/offres?etat=entretien").json()
    assert len(r["offres"]) == 1 and r["total"] == 1


def test_le_lien_d_entree_porte_l_etat_demande(connecte):
    for adresse, attendu in (
        ("/?filtre=a_traiter", "a_voir"),
        ("/?filtre=differee", "mise_de_cote"),
        ("/", ""),
        ("/?filtre=nouveau", ""),
        ("/?filtre=inconnu", ""),
    ):
        page = connecte.get(adresse).text
        assert f'data-etat-demande="{attendu}"' in page, adresse


def test_les_routes_retirees_n_existent_plus(connecte):
    """« Générer le dossier » (`POST /api/offres/{id}/dossier`) et la liste des relances ont
    quitté l'API : la préparation et « Candidatures » les remplacent."""
    chemins = {(m, r.path) for r in app.routes for m in getattr(r, "methods", ())}
    assert ("POST", "/api/offres/{offre_id}/dossier") not in chemins
    assert not any(chemin.endswith("/api/relances") for _, chemin in chemins)
    offre_id = _offre()
    assert connecte.post(f"/api/offres/{offre_id}/dossier").status_code != 200
    assert connecte.get("/api/relances").status_code != 200


def test_les_parametres_retires_ne_sont_plus_lus():
    """Un paramètre inconnu est ignoré sans erreur : seule la signature prouve qu'il est parti."""
    lus = set(inspect.signature(app_module.api_offres).parameters)
    assert not lus & {"verification", "tri", "a_documenter"}
    lus = set(inspect.signature(db.lister_offres).parameters)
    assert not lus & {"verification", "tri"}
    lus = set(inspect.signature(db.compter_offres).parameters)
    assert "verification" not in lus


def test_la_liste_ne_porte_plus_le_compte_a_documenter(connecte):
    _offre()
    assert set(connecte.get("/api/offres").json()) == {"offres", "total"}


def test_la_liste_est_triee_par_score_puis_par_collecte_recente(connecte):
    """Seul ordre de la liste, depuis que `tri` est parti : le score, puis la collecte la plus
    récente."""
    faible = _offre(score=50)
    ancienne = _offre(score=80)
    recente = _offre(score=80)
    with db.connexion() as cx:
        for offre_id, jour in ((faible, "2026-03-01"), (ancienne, "2026-01-01"),
                               (recente, "2026-02-01")):
            cx.execute("UPDATE offres SET date_collecte = ? WHERE id = ?", (jour, offre_id))
    ids = [o["id"] for o in connecte.get("/api/offres").json()["offres"]]
    assert ids == [recente, ancienne, faible]
