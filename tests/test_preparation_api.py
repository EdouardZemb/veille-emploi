"""La route de la préparation, et les pièces servies sous leur nom d'envoi (lot 2, tâche 3)."""

from __future__ import annotations

import shutil
import tempfile
import threading
import uuid
import zipfile
from email.message import Message
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veille import app as module_app
from veille import db, documents, dossier, entretien, lettre, preparation, rendu
from veille.app import app
from veille.models import Offre
from veille.scoring import scorer

from tests.aide_session import ORIGINE, connecter

TEXTE_400 = ("Mission inventée pour la préparation, sans aucune valeur réelle. " * 7)[:400]


@pytest.fixture(autouse=True)
def _base_propre(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    # Un dossier court : le nom d'un dossier de candidature est long, et sous Windows le chemin
    # d'un zip dépasserait MAX_PATH sous le dossier temporaire de pytest.
    court = Path(tempfile.mkdtemp(prefix="vp"))
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", court)
    db.initialiser()
    yield
    shutil.rmtree(court, ignore_errors=True)


@pytest.fixture
def client(_base_propre):
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def connecte(client):
    connecter(client)
    return client


def _offre(statut="nouveau", description=TEXTE_400, **champs) -> int:
    jeton = uuid.uuid4().hex
    offre = scorer(
        Offre(
            titre=f"Poste inventé {jeton}",
            employeur=f"Société inventée {jeton[:8]}",
            lieu="Basel, Switzerland",
            description=description,
            url=f"https://offres.exemple.invalid/preparer/{jeton}",
            source="test",
        )
    )
    offre_id, _ = db.enregistrer_offre(offre)
    if statut != "nouveau":
        db.changer_statut(offre_id, statut)
    if champs:
        db.maj_champs(offre_id, **champs)
    return offre_id


def _preparer(client, offre_id, **corps):
    return client.post(f"/api/offres/{offre_id}/preparer", json=corps)


def test_preparer_exige_la_session(client):
    client.cookies.clear()
    r = client.post("/api/offres/1/preparer", json={}, headers={"Origin": ORIGINE})
    assert r.status_code == 401


def test_preparer_rend_le_dossier_pret(connecte):
    offre_id = _offre()
    r = _preparer(connecte, offre_id, forcer=True)
    assert r.status_code == 200
    d = r.json()
    assert d["etape"] == "pret"
    assert d["genere"] is True
    offre = db.lire_offre(offre_id)
    assert d["dossier"]["nom"] == offre["dossier_chemin"].replace("\\", "/").split("/")[-1]
    assert offre["statut"] == "interessante"


def test_le_texte_colle_d_un_extrait_mene_au_dossier_pret(connecte):
    offre_id = _offre(description="Court.", donnees_partielles=1)
    r = _preparer(connecte, offre_id)
    assert r.status_code == 200
    d = r.json()
    assert d["etape"] == "texte"
    assert d["url"].startswith("https://offres.exemple.invalid/")
    r = _preparer(connecte, offre_id, texte=TEXTE_400, forcer=True)
    assert r.json()["etape"] == "pret"
    assert db.lire_offre(offre_id)["description"] == TEXTE_400


def test_preparer_une_offre_inconnue_rend_404(connecte):
    assert _preparer(connecte, 987654).status_code == 404


def test_preparer_une_offre_envoyee_rend_409(connecte):
    offre_id = _offre("candidature_envoyee")
    r = _preparer(connecte, offre_id)
    assert r.status_code == 409
    assert r.json() == {"erreur": "etat_incompatible"}
    assert db.lire_offre(offre_id)["statut"] == "candidature_envoyee"


def test_deux_preparations_de_la_meme_offre_ne_se_chevauchent_pas(connecte, monkeypatch):
    offre_id = _offre()
    entre, libere = threading.Event(), threading.Event()
    appels = []

    def faux(offre, **_):
        appels.append(offre)
        entre.set()
        assert libere.wait(timeout=5)
        return preparation.Etape("texte", message="x")

    monkeypatch.setattr(preparation, "preparer", faux)
    premier = {}

    def lancer():
        premier["r"] = _preparer(connecte, offre_id)

    fil = threading.Thread(target=lancer)
    fil.start()
    try:
        assert entre.wait(timeout=5)
        r = _preparer(connecte, offre_id)
        assert r.status_code == 409
        assert r.json() == {"erreur": "preparation_en_cours"}
    finally:
        libere.set()
        fil.join(timeout=5)
    assert not fil.is_alive()
    assert premier["r"].status_code == 200
    assert _preparer(connecte, offre_id).status_code == 200
    assert len(appels) == 2


def test_la_garde_se_libere_apres_une_erreur(connecte, monkeypatch):
    offre_id = _offre()

    def casse(*_, **__):
        raise preparation.EtatIncompatible

    monkeypatch.setattr(preparation, "preparer", casse)
    assert _preparer(connecte, offre_id).status_code == 409
    monkeypatch.setattr(preparation, "preparer", lambda *_, **__: preparation.Etape("texte"))
    assert _preparer(connecte, offre_id).status_code == 200


def test_preparer_refuse_sans_configuration_designee(connecte, monkeypatch):
    offre_id = _offre()
    monkeypatch.setattr(module_app, "_sert_l_exemple_par_oubli", lambda: True)
    r = _preparer(connecte, offre_id, forcer=True)
    assert r.status_code == 409
    assert r.json() == {"erreur": "configuration_non_designee"}
    assert db.lire_offre(offre_id)["statut"] == "nouveau"


def _nom_telecharge(reponse) -> str:
    message = Message()
    message["Content-Disposition"] = reponse.headers["content-disposition"]
    return message.get_filename()


def _offre_prete_avec_cv(connecte):
    offre_id = _offre()
    assert _preparer(connecte, offre_id, forcer=True).json()["etape"] == "pret"
    repertoire = dossier.chemin_du_dossier(db.lire_offre(offre_id))
    (repertoire / "cv.fr.pdf").write_bytes(b"%PDF-1.4 invente")
    return offre_id


def test_une_piece_se_telecharge_sous_son_nom_d_envoi(connecte, monkeypatch):
    offre_id = _offre_prete_avec_cv(connecte)
    url = f"/api/offres/{offre_id}/dossier/cv.fr.pdf?pour_envoi=true"
    r = connecte.get(url)
    assert r.status_code == 200
    assert _nom_telecharge(r) == rendu.nom_pour_envoi("cv.fr.pdf")
    assert _nom_telecharge(r) != "cv.fr.pdf"
    monkeypatch.setattr(rendu, "prefixe", lambda: "Éloïse-Inventée")
    r = connecte.get(url)
    assert "filename*=" in r.headers["content-disposition"]
    assert _nom_telecharge(r) == rendu.nom_pour_envoi("cv.fr.pdf")
    assert _nom_telecharge(r).startswith("Éloïse-Inventée")


def test_sans_pour_envoi_une_piece_garde_son_nom(connecte):
    offre_id = _offre_prete_avec_cv(connecte)
    r = connecte.get(f"/api/offres/{offre_id}/dossier/cv.fr.pdf")
    assert r.status_code == 200
    assert _nom_telecharge(r) == "cv.fr.pdf"


# --------------------------------------------------------------------------
# La note du destinataire, sur le vrai `generer`
# --------------------------------------------------------------------------

DESTINATAIRE = {
    "contact_nom": "Alex Inventé",
    "contact_civilite": "Madame",
    "adresse_entreprise": "1 rue Inventée\n68000 Exempleville",
    "reference_annonce": "REF-INVENTEE-7",
}
AUTRE_NOM = "Dominique Inventée"


def _repertoire(offre_id) -> Path:
    return dossier.chemin_du_dossier(db.lire_offre(offre_id))


def _paquet(repertoire: Path) -> Path:
    return repertoire / f"{rendu.prefixe()}-candidature.zip"


def test_preparer_note_le_destinataire_de_la_lettre(connecte, monkeypatch):
    """La note suit chaque génération, et ne part jamais : ni dans les paquets, ni parmi les
    pièces, ni dans *Plus › Documents*."""
    monkeypatch.setattr(documents, "CHEMIN_DOSSIERS", dossier.CHEMIN_DOSSIERS)
    offre_id = _offre(**DESTINATAIRE)
    d = _preparer(connecte, offre_id, forcer=True).json()
    assert d["etape"] == "pret"
    repertoire = _repertoire(offre_id)
    assert dossier.lire_note_destinataire(repertoire) == DESTINATAIRE
    assert d["dossier"]["destinataire_lettre"] == DESTINATAIRE
    assert d["dossier"]["destinataire"] == DESTINATAIRE
    assert d["dossier"]["avertissements"] == []
    paquets = sorted(repertoire.glob("*.zip"))
    assert len(paquets) == 2
    for paquet in paquets:
        with zipfile.ZipFile(paquet) as z:
            assert not [n for n in z.namelist() if n.endswith(".json")], paquet.name
    assert lettre.NOM_DESTINATAIRE not in [p["fichier"] for p in d["dossier"]["pieces"]]
    [ligne] = [x for x in documents.lister_dossiers() if x["dossier"] == repertoire.name]
    assert ligne["fichiers"]
    assert lettre.NOM_DESTINATAIRE not in [f["nom"] for f in ligne["fichiers"]]
    r = connecte.get(f"/api/documents/dossiers/{repertoire.name}/{lettre.NOM_DESTINATAIRE}")
    assert r.status_code == 404


def test_un_destinataire_enregistre_sans_regenerer_se_dit_sur_dossier_pret(connecte):
    """Un destinataire enregistré après la génération, sans régénérer (la vue détaillée), se dit
    sur « Dossier prêt », qui montre toujours celui de la lettre."""
    offre_id = _offre("interessante", **DESTINATAIRE)
    assert _preparer(connecte, offre_id, forcer=True).json()["etape"] == "pret"
    assert dossier.lire_note_destinataire(_repertoire(offre_id)) == DESTINATAIRE
    r = connecte.post(f"/api/offres/{offre_id}", json={"contact_nom": AUTRE_NOM})
    assert r.status_code == 200
    d = _preparer(connecte, offre_id).json()
    assert d["etape"] == "pret"
    assert d["genere"] is False
    assert d["dossier"]["destinataire_lettre"] == DESTINATAIRE
    assert d["dossier"]["destinataire"] == {**DESTINATAIRE, "contact_nom": AUTRE_NOM}
    assert d["avertissements"][-1].startswith("Un autre destinataire est enregistré")


def test_une_generation_en_echec_n_ecrit_pas_de_note(connecte, monkeypatch):
    """Le vrai `generer` casse après avoir réécrit la lettre (dans la note d'entretien) : la
    lettre est neuve, le paquet d'envoi l'ancien, et la note de la génération d'avant est
    partie, sans qu'une neuve soit écrite. La lettre d'avant est dans l'historique."""
    offre_id = _offre(**DESTINATAIRE)
    assert _preparer(connecte, offre_id, forcer=True).json()["etape"] == "pret"
    repertoire = _repertoire(offre_id)
    assert dossier.lire_note_destinataire(repertoire) == DESTINATAIRE
    (repertoire / lettre.NOM_LETTRE).write_text("Lettre inventée d'avant.", encoding="utf-8")
    paquet_avant = _paquet(repertoire).read_bytes()
    db.maj_champs(offre_id, contact_nom=AUTRE_NOM)

    def casse(*_, **__):
        raise RuntimeError("panne inventée de la note d'entretien")

    monkeypatch.setattr(entretien, "preparer", casse)
    d = _preparer(connecte, offre_id, regenerer=True).json()
    assert d["etape"] == "echec"
    assert d["message"] == "panne inventée de la note d'entretien"
    assert _repertoire(offre_id) == repertoire
    assert (repertoire / lettre.NOM_LETTRE).read_text(encoding="utf-8") != "Lettre inventée d'avant."
    assert _paquet(repertoire).read_bytes() == paquet_avant
    assert not (repertoire / lettre.NOM_DESTINATAIRE).exists()
    [version] = lettre.versions(repertoire)
    assert lettre.texte_de_version(repertoire, version.numero) == "Lettre inventée d'avant."
    # Revenu sur « Dossier prêt » : aucun destinataire affirmé, aucun écart inventé.
    d = _preparer(connecte, offre_id).json()
    assert d["etape"] == "pret"
    assert d["dossier"]["destinataire_lettre"] is None
    assert d["dossier"]["destinataire"]["contact_nom"] == AUTRE_NOM
    assert d["avertissements"] == []
