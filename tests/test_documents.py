"""Acces aux documents depuis la console.

Ces fichiers portent son etat civil, ses pretentions salariales et sa
strategie de negociation. Les tests d'isolation ne sont donc pas theoriques :
un chemin mal verifie exposerait tout le compte.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from veille import db, documents
from veille.app import app
from tests.aide_session import connecter


@pytest.fixture
def kit(tmp_path, monkeypatch):
    """Un kit de forme courante, preparation d'entretien comprise."""
    dossier = tmp_path / "kit-exemple"
    dossier.mkdir()
    for nom in (
        "cv.fr.pdf",
        "cv.en.pdf",
        "presentation.ch.en.pdf",
        "annexe-technique.pdf",
        "preparation-entretien.md",
        "strategie-negociation.md",
        "certificat-ctfl.pdf",
    ):
        (dossier / nom).write_bytes(b"contenu factice")
    (dossier / "lettre.md").write_text("Objet : {{titre}}", encoding="utf-8")
    # Bruit a ignorer : fichier cache et extension inconnue.
    (dossier / ".DS_Store").write_bytes(b"x")
    (dossier / "brouillon.sqlite3").write_bytes(b"x")
    monkeypatch.setattr(documents, "CHEMIN_KIT", dossier)
    return dossier


@pytest.fixture
def client(kit, tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    db.initialiser()
    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        yield c


# --------------------------------------------------------------------------
# Listing du kit
# --------------------------------------------------------------------------


def test_le_kit_est_relu_a_chaque_appel(kit):
    """Aucun nom de fichier n'est code en dur : le kit s'enrichira encore."""
    avant = documents.lister_kit()["total"]
    (kit / "nouveau-document.pdf").write_bytes(b"x")
    apres = documents.lister_kit()["total"]
    assert apres == avant + 1
    noms = [d["nom"] for g in documents.lister_kit()["groupes"] for d in g["documents"]]
    assert "nouveau-document.pdf" in noms


def test_les_fichiers_caches_et_inconnus_sont_ignores(kit):
    noms = [d["nom"] for g in documents.lister_kit()["groupes"] for d in g["documents"]]
    assert ".DS_Store" not in noms
    assert "brouillon.sqlite3" not in noms


def test_les_documents_sont_ranges_par_categorie(kit):
    groupes = {g["categorie"]: [d["nom"] for d in g["documents"]]
               for g in documents.lister_kit()["groupes"]}
    assert "cv.fr.pdf" in groupes["CV"]
    assert "preparation-entretien.md" in groupes["Préparation d'entretien"]
    assert "strategie-negociation.md" in groupes["Stratégie"]
    assert "annexe-technique.pdf" in groupes["Annexes et certifications"]


def test_le_contexte_des_pieces_est_lisible(kit):
    documents_plats = {d["nom"]: d for g in documents.lister_kit()["groupes"] for d in g["documents"]}
    assert documents_plats["cv.fr.pdf"]["contexte"] == "français"
    assert documents_plats["presentation.ch.en.pdf"]["contexte"] == "Suisse, anglais"
    assert documents_plats["annexe-technique.pdf"]["contexte"] == ""


def test_kit_absent_explique_quoi_faire(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "CHEMIN_KIT", tmp_path / "nulle-part")
    resultat = documents.lister_kit()
    assert resultat["present"] is False
    assert "VEILLE_KIT" in resultat["message"]


# --------------------------------------------------------------------------
# Isolation des chemins
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nom",
    [
        "../../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "/etc/passwd",
        "subdir/../../secret.pdf",
        "brouillon.sqlite3",      # extension non servie
        "inexistant.pdf",
    ],
)
def test_aucun_chemin_ne_sort_du_kit(kit, nom):
    with pytest.raises(ValueError):
        documents.chemin_kit_sur(nom)


def test_un_lien_symbolique_ne_permet_pas_de_sortir(kit, tmp_path):
    """resolve() suit les liens : un raccourci vers l'exterieur est refuse."""
    secret = tmp_path / "hors-kit.pdf"
    secret.write_bytes(b"secret")
    try:
        (kit / "raccourci.pdf").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("liens symboliques indisponibles")
    with pytest.raises(ValueError):
        documents.chemin_kit_sur("raccourci.pdf")


def test_un_document_legitime_est_bien_resolu(kit):
    chemin = documents.chemin_kit_sur("cv.fr.pdf")
    assert chemin.name == "cv.fr.pdf"
    assert chemin.is_file()


# --------------------------------------------------------------------------
# Routes HTTP
# --------------------------------------------------------------------------


def test_les_documents_exigent_une_session(client):
    client.cookies.clear()
    assert client.get("/api/documents/kit").status_code == 401
    assert client.get("/api/documents/kit/cv.fr.pdf").status_code == 401
    assert client.get("/api/documents/dossiers").status_code == 401


def test_telechargement_en_piece_jointe_par_defaut(client):
    """Un PDF de CV se lit mal dans un onglet de telephone."""
    r = client.get("/api/documents/kit/cv.fr.pdf")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment")
    assert "cv.fr.pdf" in r.headers["content-disposition"]
    assert r.content == b"contenu factice"


def test_apercu_possible_a_la_demande(client):
    r = client.get("/api/documents/kit/preparation-entretien.md?apercu=true")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("inline")


def test_route_de_telechargement_refuse_la_traversee(client):
    for chemin in ("/api/documents/kit/..%2F..%2Fetc%2Fpasswd",
                   "/api/documents/kit/brouillon.sqlite3"):
        assert client.get(chemin).status_code == 404, chemin


# --------------------------------------------------------------------------
# Dossiers generes
# --------------------------------------------------------------------------


def test_un_dossier_genere_apparait_et_se_telecharge(client, kit, tmp_path, monkeypatch):
    from veille import dossier as generateur
    from veille.models import Offre
    from veille.scoring import scorer

    monkeypatch.setattr(generateur, "CHEMIN_KIT", kit)
    monkeypatch.setattr(generateur, "CHEMIN_DOSSIERS", tmp_path / "sortie")

    offre = scorer(Offre(titre="Test Engineer", employeur="Exemplia", lieu="Basel",
                         description="You will own the test strategy with us.", source="test"))
    oid, _ = db.enregistrer_offre(offre)
    resultat = generateur.generer(db.lire_offre(oid))
    db.maj_champs(oid, dossier_chemin=str(resultat.chemin))

    liste = client.get("/api/documents/dossiers").json()["dossiers"]
    assert liste, "le dossier genere doit apparaitre"
    entree = liste[0]
    assert entree["titre"] == "Test Engineer"
    assert entree["offre_id"] == oid

    nom = next(f["nom"] for f in entree["fichiers"] if f["nom"].endswith(".md"))
    r = client.get(f"/api/documents/dossiers/{entree['dossier']}/{nom}")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment")


def test_aucun_chemin_ne_sort_des_dossiers_generes(client, tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    (tmp_path / "sortie").mkdir(exist_ok=True)
    with pytest.raises(ValueError):
        documents.chemin_dossier_sur("../..", "passwd")
    assert client.get("/api/documents/dossiers/..%2F..%2Fetc/passwd").status_code == 404


# --------------------------------------------------------------------------
# Le nom des PDF vient de la configuration
# --------------------------------------------------------------------------


def test_nom_des_pdf(monkeypatch, request, tmp_path):
    from tests.aide_criteres import poser_criteres
    from veille import rendu

    poser_criteres(
        monkeypatch, request, tmp_path,
        lambda brut: brut["profil"].update(nom_fichier="Camille-Exemple"),
    )
    assert (rendu.nom_pour_envoi("lettre-de-motivation.pdf")
            == "Camille-Exemple-Lettre-de-motivation.pdf")


def test_sans_nom_de_fichier_le_prefixe_est_candidature(monkeypatch, request, tmp_path):
    from tests.aide_criteres import poser_criteres
    from veille import rendu

    poser_criteres(
        monkeypatch, request, tmp_path,
        lambda brut: brut["profil"].pop("nom_fichier", None),
    )
    assert (rendu.nom_pour_envoi("lettre-de-motivation.pdf")
            == "Candidature-Lettre-de-motivation.pdf")
