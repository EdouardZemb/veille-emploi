"""Vérifier qu'une annonce est encore en ligne — et ne jamais archiver à tort.

**Le coût des deux erreurs n'est pas le même.** Garder une annonce morte lui
coûte un clic. Archiver une annonce vivante la fait disparaître de sa vue sans
qu'il sache pourquoi — surtout quand les alertes mail sont le flux principal.

Toute la règle découle de cette asymétrie :

1. un code HTTP ne prouve rien — beaucoup de sites rendent **200 avec une page
   d'expiration** ;
2. une phrase d'expiration ne prouve rien non plus si le titre de l'annonce est
   **encore sur la page** : c'est du texte de gabarit, pas un retrait ;
3. **injoignable ≠ retirée.** Délai dépassé, 429, 503, coupure réseau, blocage
   robot : on ne sait pas, donc on ne conclut pas ;
4. une redirection vers l'accueil est un **indice**, pas une preuve ;
5. il faut **plusieurs échecs consécutifs espacés**, jamais un seul ;
6. ce qu'on n'a pas le droit de sonder n'est **jamais** archivé automatiquement.

C'est la cinquième fois qu'on écrit le test avant la règle pour cette famille de
pièges. Les quatre précédentes sont dans `tests/test_pretraitement.py`.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta

import pytest

from veille import db, verification
from veille.models import Offre
from veille.scoring import scorer
from tests.aide_session import connecter

MAINTENANT = datetime(2026, 9, 29, 12, 0, 0)
PLUS_TARD = MAINTENANT + timedelta(hours=26)
ENCORE_PLUS_TARD = PLUS_TARD + timedelta(hours=26)


@pytest.fixture(autouse=True)
def base(monkeypatch):
    db.initialiser()
    with db.connexion() as cx:
        cx.execute("DELETE FROM offres WHERE source = 'test:verif'")
    # La politique d'acces est posee ici, comme dans tests/test_enrichissement.py :
    # l'exemple livre l'enrichissement desactive, et une sonde n'y partirait jamais.
    from veille import enrichissement

    monkeypatch.setattr(enrichissement, "charger_sources", lambda: {
        "enrichissement": {
            "actif": True,
            "delai_entre_requetes_s": 20,
            "plafond_quotidien": 30,
            "domaines_interdits": ["linkedin.com", "indeed.com"],
            "domaines_autorises": ["jobs.ch", "arbeitnow.com"],
        }
    })


_compteur = itertools.count()


def _offre(url: str = "https://jobs.ch/en/vacancies/detail/test-1", **kw) -> int:
    """Chaque offre a son PROPRE intitule et son propre employeur.

    La deduplication se fait sur l'empreinte titre+employeur autant que sur
    l'URL : sans identite distincte, deux appels retombent sur la meme ligne et
    le test compare une offre a elle-meme. Troisieme fois que ce piege se
    referme aujourd'hui — il est desormais nomme dans les deux fichiers.
    """
    n = next(_compteur)
    champs = dict(
        titre=f"Ingenieur Recette WMS {n}",
        employeur=f"Societe Test Verification {n}",
        lieu="Mulhouse",
        description="Poste de recette en environnement logistique.",
        url=url,
        source="test:verif",
    )
    champs.update(kw)
    oid, _ = db.enregistrer_offre(scorer(Offre(**champs)))
    return oid


class Reponse:
    """Une reponse HTTP factice, avec son URL finale apres redirections."""

    def __init__(self, code=200, texte="", url=None, entetes=None):
        self.status_code = code
        self.text = texte
        self.url = url or "https://jobs.ch/en/vacancies/detail/test-1"
        self.headers = entetes or {}


def _servir(monkeypatch, reponse):
    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, **kw):
            if isinstance(reponse, Exception):
                raise reponse
            return reponse

    monkeypatch.setattr(verification.httpx, "Client", lambda *a, **k: Client())


PAGE_VIVANTE = (
    "Ingenieur Recette WMS\n"
    "Societe Test Verification, Mulhouse\n"
    "Vous pilotez la recette d'un logiciel de gestion d'entrepot en environnement "
    "logistique. Vous redigez les plans de test et les rapports de recette. "
    "Formation superieure, anglais professionnel. Poste en CDI." * 3
)

PAGE_EXPIREE = (
    "Cette offre n'est plus disponible.\n"
    "Consultez nos offres similaires ou creez une alerte emploi.\n"
    "jobs.ch — le portail de l'emploi"
)


# --------------------------------------------------------------------------
# 1. Ce qui prouve un retrait
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code,verdict", [(404, "retiree"), (410, "retiree_declaree")])
def test_404_et_410_prouvent_le_retrait_mais_pas_de_la_meme_facon(
        monkeypatch, code, verdict):
    """Les deux prouvent un retrait, avec deux degres de certitude.

    410 Gone est une DECLARATION : le serveur affirme que la ressource a
    existe et qu'elle est definitivement supprimee. 404 est un CONSTAT muet
    sur la cause. Le verdict le dit, et le traitement en decoule : archivage
    immediat pour l'un, deux passes espacees pour l'autre.
    """
    _servir(monkeypatch, Reponse(code=code))
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/test-1")
    assert s.verdict == verdict, s
    assert str(code) in s.detail


def test_une_page_dexpiration_en_200_prouve_le_retrait(monkeypatch):
    """LE cas que le code HTTP ne voit pas."""
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_EXPIREE))
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/test-1",
                            titre="Ingenieur Recette WMS")
    assert s.verdict == "retiree", s
    assert "plus disponible" in s.detail.lower(), s.detail


def test_la_phrase_dexpiration_ne_compte_pas_si_lannonce_est_encore_la(monkeypatch):
    """« Si cette offre n'est plus disponible, consultez… » est du gabarit.

    Le plus specifique d'abord : si le titre de l'annonce est encore sur la
    page, la page EST l'annonce, quoi qu'elle raconte par ailleurs.
    """
    page = PAGE_VIVANTE + "\nSi cette offre n'est plus disponible, consultez nos alertes."
    _servir(monkeypatch, Reponse(code=200, texte=page))
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/test-1",
                            titre="Ingenieur Recette WMS")
    assert s.verdict == "vivante", s


def test_une_page_vivante_est_vivante(monkeypatch):
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_VIVANTE))
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/test-1",
                            titre="Ingenieur Recette WMS")
    assert s.verdict == "vivante", s
    assert s.texte, "le corps sert aussi a enrichir l'offre"


# --------------------------------------------------------------------------
# 2. Ce qui ne prouve RIEN — le cœur du garde-fou
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504, 403])
def test_ces_codes_ne_concluent_pas(monkeypatch, code):
    _servir(monkeypatch, Reponse(code=code))
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/test-1")
    assert s.verdict == "injoignable", f"HTTP {code} rendu {s.verdict}"


def test_un_429_fait_attendre_le_temps_demande(monkeypatch):
    _servir(monkeypatch, Reponse(code=429, entetes={"Retry-After": "120"}))
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/test-1")
    assert s.verdict == "injoignable"
    assert s.attendre_s == 120, s.attendre_s


@pytest.mark.parametrize("panne", [
    TimeoutError("delai depasse"),
    OSError("reseau coupe"),
    ConnectionError("connexion refusee"),
])
def test_une_panne_reseau_ne_conclut_pas(monkeypatch, panne):
    _servir(monkeypatch, panne)
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/test-1")
    assert s.verdict == "injoignable", s


def test_une_redirection_vers_laccueil_est_un_indice_pas_une_preuve(monkeypatch):
    _servir(monkeypatch, Reponse(code=200, texte="Trouvez votre prochain emploi",
                                 url="https://jobs.ch/"))
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/test-1",
                            titre="Ingenieur Recette WMS")
    assert s.verdict == "indice_retrait", s


def test_une_page_vide_ne_conclut_pas(monkeypatch):
    """Rendu JavaScript : la page arrive vide. On ne sait pas."""
    _servir(monkeypatch, Reponse(code=200, texte="<html><body>Chargement…</body></html>"))
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/test-1",
                            titre="Ingenieur Recette WMS")
    assert s.verdict == "injoignable", s


# --------------------------------------------------------------------------
# 3. Ce qu'on n'a pas le droit de sonder
# --------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs/view/4000000001",
    "https://fr.indeed.com/viewjob?jk=abc",
    "https://un-site-inconnu.example/offre/1",
])
def test_aucune_requete_ne_part_vers_un_site_interdit(monkeypatch, url):
    def interdit(*a, **k):
        raise AssertionError("aucune requete ne doit partir")

    monkeypatch.setattr(verification.httpx, "Client", interdit)
    s = verification.sonder(url)
    assert s.verdict == "interdite", s


def test_une_offre_non_sondable_nest_jamais_archivee():
    """Une part notable des offres est dans ce cas."""
    oid = _offre(url="https://www.linkedin.com/jobs/view/4000000001")
    for quand in (MAINTENANT, PLUS_TARD, ENCORE_PLUS_TARD):
        d = verification.verifier_offre(oid, maintenant=quand)
        assert d.verdict == "interdite"
        assert not d.archivee, "une offre non sondable ne peut pas etre archivee"
    o = db.lire_offre(oid)
    assert not o["archivee_le"]
    assert o["verdict_verification"] == "interdite"


# --------------------------------------------------------------------------
# 4. Il faut plusieurs échecs, espacés
# --------------------------------------------------------------------------


def test_un_seul_echec_narchive_jamais(monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    d = verification.verifier_offre(oid, maintenant=MAINTENANT)
    assert d.verdict == "retiree"
    assert not d.archivee, "un seul 404 ne suffit pas"
    assert db.lire_offre(oid)["echecs_verification"] == 1


def test_deux_echecs_trop_rapproches_narchivent_pas(monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    d = verification.verifier_offre(oid, maintenant=MAINTENANT + timedelta(minutes=30))
    assert not d.archivee, "deux echecs a 30 minutes d'intervalle ne prouvent rien"


def test_deux_echecs_espaces_archivent(monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    d = verification.verifier_offre(oid, maintenant=PLUS_TARD)
    assert d.archivee, d
    o = db.lire_offre(oid)
    assert o["archivee_le"]
    assert "404" in o["archive_motif"] or "introuvable" in o["archive_motif"].lower()
    assert o["disparue_le"], "la date de disparition est une donnee en soi"


def test_un_indice_seul_demande_un_echec_de_plus(monkeypatch):
    """Une redirection est plus faible qu'un 404 : trois, pas deux."""
    _servir(monkeypatch, Reponse(code=200, texte="Trouvez votre emploi",
                                 url="https://jobs.ch/"))
    oid = _offre()
    assert not verification.verifier_offre(oid, maintenant=MAINTENANT).archivee
    assert not verification.verifier_offre(oid, maintenant=PLUS_TARD).archivee
    assert verification.verifier_offre(oid, maintenant=ENCORE_PLUS_TARD).archivee


def test_une_page_vivante_remet_le_compteur_a_zero(monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_VIVANTE))
    verification.verifier_offre(oid, maintenant=PLUS_TARD)
    assert db.lire_offre(oid)["echecs_verification"] == 0
    _servir(monkeypatch, Reponse(code=404))
    d = verification.verifier_offre(oid, maintenant=ENCORE_PLUS_TARD)
    assert not d.archivee, "le compteur repart de zero apres une page vivante"


def test_un_injoignable_ne_fait_ni_avancer_ni_reculer(monkeypatch):
    """Un site en panne ne doit ni condamner l'offre, ni effacer les preuves."""
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    _servir(monkeypatch, Reponse(code=503))
    verification.verifier_offre(oid, maintenant=PLUS_TARD)
    assert db.lire_offre(oid)["echecs_verification"] == 1, "ni avance, ni reset"
    _servir(monkeypatch, Reponse(code=404))
    assert verification.verifier_offre(oid, maintenant=ENCORE_PLUS_TARD).archivee


# --------------------------------------------------------------------------
# 5. Les offres qui comptent ne sont jamais archivées
# --------------------------------------------------------------------------


@pytest.mark.parametrize("statut", ["interessante", "a_traiter", "candidature_envoyee"])
def test_une_offre_triee_a_la_main_nest_jamais_archivee(monkeypatch, statut):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    db.changer_statut(oid, statut)
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    d = verification.verifier_offre(oid, maintenant=PLUS_TARD)
    assert not d.archivee, f"{statut} ne doit jamais partir a l'archive"
    o = db.lire_offre(oid)
    assert not o["archivee_le"]
    assert o["probablement_retiree"], "mais il doit etre prevenu"


def test_une_offre_avec_dossier_genere_nest_jamais_archivee(monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    with db.connexion() as cx:
        cx.execute("UPDATE offres SET dossier_chemin = ? WHERE id = ?", ("/tmp/x", oid))
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    d = verification.verifier_offre(oid, maintenant=PLUS_TARD)
    assert not d.archivee
    assert db.lire_offre(oid)["probablement_retiree"]


# --------------------------------------------------------------------------
# 6. Réversibilité
# --------------------------------------------------------------------------


def test_desarchiver_rend_loffre_et_empeche_le_rearchivage(monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    verification.verifier_offre(oid, maintenant=PLUS_TARD)
    assert db.lire_offre(oid)["archivee_le"]

    db.desarchiver(oid)
    o = db.lire_offre(oid)
    assert not o["archivee_le"]
    assert o["archive_protegee"], "il vient de dire qu'il la veut : on n'y revient pas"

    d = verification.verifier_offre(oid, maintenant=ENCORE_PLUS_TARD)
    assert not d.archivee, "ne jamais rearchiver ce qu'il vient de ressortir"


def test_larchive_ne_supprime_rien(monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    verification.verifier_offre(oid, maintenant=PLUS_TARD)
    o = db.lire_offre(oid)
    assert o["titre"] and o["description"] and o["explication"]
    assert o["score"] is not None


# --------------------------------------------------------------------------
# 7. Une page qui revient enrichit l'offre — au lieu de la condamner
# --------------------------------------------------------------------------


def test_une_page_vivante_enrichit_une_offre_qui_navait_quun_extrait(monkeypatch):
    """On telecharge la page de toute facon : s'en servir est gratuit.

    Presque aucune annonce de son gisement reel n'arrive avec une
    description complete. Chaque page lue est une occasion de la completer.
    """
    oid = _offre(description="Voir l'annonce.", donnees_partielles=True)
    avant = db.lire_offre(oid)
    assert avant["donnees_partielles"]

    page = (PAGE_VIVANTE + "\nRemuneration entre 46000 et 50000 euros selon profil.")
    _servir(monkeypatch, Reponse(code=200, texte=page))
    d = verification.verifier_offre(oid, maintenant=MAINTENANT, enrichir=True)
    assert d.verdict == "vivante"

    apres = db.lire_offre(oid)
    assert not apres["donnees_partielles"], "la page lue devait completer l'offre"
    assert apres["salaire_min"] == 46000
    assert apres["score"] > avant["score"]


# --------------------------------------------------------------------------
# 8. La passe complète : cadence et priorités
# --------------------------------------------------------------------------


def test_la_passe_ne_sonde_pas_deux_fois_la_meme_offre_le_meme_jour(monkeypatch):
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_VIVANTE))
    oid = _offre()
    r1 = verification.passe(limite=50, maintenant=MAINTENANT)
    assert oid in r1.sondees
    r2 = verification.passe(limite=50, maintenant=MAINTENANT + timedelta(hours=2))
    assert oid not in r2.sondees, "inutile de resonder quelques heures apres"


def test_la_passe_saute_les_offres_deja_archivees(monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    verification.verifier_offre(oid, maintenant=PLUS_TARD)
    r = verification.passe(limite=50, maintenant=ENCORE_PLUS_TARD)
    assert oid not in r.sondees


# --------------------------------------------------------------------------
# 9. Les routes HTTP
#
# Un test qui appelle la fonction ne dit pas que la page repond. On a deja
# livre une page en 500 pendant que l'API repondait 200.
# --------------------------------------------------------------------------


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from veille.app import app

    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        yield c


def test_la_page_principale_repond(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'data-vue="archive"' in r.text, "l'onglet Archive doit etre dans la page"


def test_larchive_repond_meme_vide(client):
    r = client.get("/api/archive")
    assert r.status_code == 200
    charge = r.json()
    assert "offres" in charge and "nouvelles" in charge


def test_desarchiver_par_lapi(client, monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    verification.verifier_offre(oid, maintenant=PLUS_TARD)
    assert any(o["id"] == oid for o in client.get("/api/archive").json()["offres"])

    r = client.post(f"/api/offres/{oid}/desarchiver")
    assert r.status_code == 200
    assert not any(o["id"] == oid for o in client.get("/api/archive").json()["offres"])
    assert db.lire_offre(oid)["archive_protegee"]


def test_marquer_retiree_a_la_main(client):
    """Le seul moyen honnete d'archiver une offre LinkedIn : son constat."""
    oid = _offre(url="https://www.linkedin.com/jobs/view/4000000001")
    r = client.post(f"/api/offres/{oid}/constat?en_ligne=false")
    assert r.status_code == 200
    o = db.lire_offre(oid)
    assert o["archivee_le"]
    assert "edouard" in o["archive_motif"].lower()
    assert o["verifiee_par"] == "edouard"


def test_son_constat_est_reversible_en_un_appel(client):
    """« Reversible aussitot, avec la meme facilite » : le meme bouton, inverse."""
    oid = _offre(url="https://www.linkedin.com/jobs/view/4000000001")
    client.post(f"/api/offres/{oid}/constat?en_ligne=false")
    assert db.lire_offre(oid)["archivee_le"]

    client.post(f"/api/offres/{oid}/constat?en_ligne=true")
    o = db.lire_offre(oid)
    assert not o["archivee_le"]
    assert o["archive_protegee"], "il vient de dire qu'elle est en ligne"
    assert o["verdict_verification"] == "vivante"


def test_les_trois_etats_sont_distinguables(client, monkeypatch):
    """Verifiee automatiquement, verifiee par lui, jamais verifiee.

    Trois choses differentes : l'interface doit pouvoir les separer, donc la
    base doit les distinguer.
    """
    jamais = _offre(url="https://jobs.ch/en/vacancies/detail/jamais")
    assert db.lire_offre(jamais)["verifiee_le"] is None

    _servir(monkeypatch, Reponse(code=200, texte=PAGE_VIVANTE))
    auto = _offre(url="https://jobs.ch/en/vacancies/detail/auto")
    verification.verifier_offre(auto, maintenant=MAINTENANT)
    assert db.lire_offre(auto)["verifiee_par"] == "auto"

    main = _offre(url="https://www.linkedin.com/jobs/view/1")
    client.post(f"/api/offres/{main}/constat?en_ligne=true")
    assert db.lire_offre(main)["verifiee_par"] == "edouard"


def test_on_peut_isoler_ce_qui_na_jamais_ete_verifie(client, monkeypatch):
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_VIVANTE))
    vu = _offre(url="https://jobs.ch/en/vacancies/detail/vu")
    verification.verifier_offre(vu, maintenant=MAINTENANT)
    jamais = _offre(url="https://jobs.ch/en/vacancies/detail/pas-vu")

    ids = [o["id"] for o in
           client.get("/api/offres?verification=jamais&limite=500").json()["offres"]]
    assert jamais in ids and vu not in ids


def test_le_tri_par_verification_met_les_jamais_vues_en_tete(client, monkeypatch):
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_VIVANTE))
    vu = _offre(url="https://jobs.ch/en/vacancies/detail/deja-vu")
    verification.verifier_offre(vu, maintenant=MAINTENANT)
    jamais = _offre(url="https://jobs.ch/en/vacancies/detail/jamais-vu")

    ids = [o["id"] for o in
           client.get("/api/offres?tri=verification&limite=500").json()["offres"]]
    assert ids.index(jamais) < ids.index(vu)


def test_verifier_une_offre_interdite_le_dit_sans_requete(client, monkeypatch):
    def interdit(*a, **k):
        raise AssertionError("aucune requete ne doit partir")

    monkeypatch.setattr(verification.httpx, "Client", interdit)
    oid = _offre(url="https://www.linkedin.com/jobs/view/4000000001")
    r = client.post(f"/api/offres/{oid}/verifier")
    assert r.status_code == 200
    assert r.json()["verdict"] == "interdite"
    assert not r.json()["archivee"]


def test_une_offre_archivee_ne_remonte_pas_dans_la_liste_active(client, monkeypatch):
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre()
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    verification.verifier_offre(oid, maintenant=PLUS_TARD)
    actives = client.get("/api/offres?limite=500").json()["offres"]
    assert not any(o["id"] == oid for o in actives)


# --------------------------------------------------------------------------
# 10. « Le titre n'est plus sur la page » ne prouve rien
#
# Trouve au rejeu sur la base : plusieurs offres accusees a tort, pour deux
# raisons systematiques, et aucune n'etait un retrait.
#
#  - TITRE COURT. « QA Lead » : apres normalisation il reste « lead » (« qa »
#    fait deux lettres et tombe). Le controle exigeait trois mots consecutifs,
#    n'en trouvait pas assez, et repondait « titre absent » la ou la reponse
#    honnete etait « je ne peux pas savoir ».
#  - PAGE TRADUITE. Le titre est stocke en allemand depuis l'alerte, la page
#    sondee est la version anglaise du meme site. L'annonce est vivante.
#
# Conclusion tiree : « titre absent d'une page lisible » ne redescend plus a
# `indice_retrait`. Ce verdict est reserve a la redirection vers une page
# generique, qui est structurelle et pas textuelle.
# --------------------------------------------------------------------------


PAGE_ARBEITNOW = (
    "QA Lead – Exemplia – Hamburg | Arbeitnow\n"
    "Popular Locations Categories Blog About\n"
    "Jobs with Visa Sponsorship. Exemplia is looking for a QA Lead to join the "
    "team in Hamburg. You will own the quality of our products end to end, "
    "define the test strategy and work with engineering on release quality. "
    "We offer a competitive package and a hybrid setup." * 2
)

PAGE_TRADUITE = (
    "Test Automation Specialist (Warehouse Management Software) (m/f) "
    "- Job Offer at Exemple Logistik AG - jobs.ch\n"
    "Exemple Logistik AG, Pratteln (BL). Save. Apply.\n"
    "You are responsible for the test automation of our warehouse management "
    "software. You maintain the test suites and document results "
    "according to our quality management system." * 2
)


def test_un_titre_court_ne_fait_pas_accuser_la_page(monkeypatch):
    """« QA Lead » : deux mots, dont un de deux lettres."""
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_ARBEITNOW))
    s = verification.sonder("https://arbeitnow.com/jobs/companies/exemplia/qa-lead-hamburg-100001",
                            titre="QA Lead")
    assert s.verdict != "indice_retrait", (
        f"accusee a tort alors que le titre est sur la page : {s}"
    )


def test_un_titre_de_deux_mots_significatifs_est_reconnu(monkeypatch):
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_ARBEITNOW))
    s = verification.sonder("https://arbeitnow.com/x", titre="QA Lead")
    assert s.verdict == "vivante", s


def test_une_page_traduite_nest_pas_un_retrait(monkeypatch):
    """Titre stocke en allemand, page servie en anglais : l'annonce est vivante."""
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_TRADUITE))
    s = verification.sonder(
        "https://jobs.ch/en/vacancies/detail/abc",
        titre="Fachspezialist Testautomatisierung (Lagerverwaltungssoftware) (m/w)",
    )
    assert s.verdict != "indice_retrait", f"accusee a tort : {s}"
    assert s.verdict == "injoignable", s


def test_un_titre_absent_ne_descend_jamais_a_indice(monkeypatch):
    """La regle generale, pas seulement les deux cas observes."""
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_VIVANTE))
    s = verification.sonder("https://jobs.ch/x", titre="Un intitule totalement different ici")
    assert s.verdict == "injoignable", s


def test_la_redirection_reste_le_seul_indice(monkeypatch):
    """Elle, on la garde : elle est structurelle, pas textuelle."""
    _servir(monkeypatch, Reponse(code=200, texte="Trouvez votre emploi",
                                 url="https://jobs.ch/"))
    s = verification.sonder("https://jobs.ch/en/vacancies/detail/x", titre="Test Manager")
    assert s.verdict == "indice_retrait", s


# --------------------------------------------------------------------------
# 11. Les DEUX chemins vers l'archivage font la meme chose
#
# Constate par Edouard a l'ecran : « je clique sur "elle n'y est plus,
# archiver" et quand je reviens sur la page principale l'offre est toujours
# presente ; il faut cliquer sur Obsolete pour qu'elle disparaisse ».
#
# Cause : la route `/retiree` avait ete renommee `/constat`, le JS appelait
# toujours l'ancienne, et `fetch` ne leve rien sur un 404. Plusieurs offres
# concernees, une action definitivement perdue.
#
# Ces tests verrouillent l'invariant cote serveur ; `tests/test_javascript.py`
# verrouille que le JS appelle bien des routes existantes.
# --------------------------------------------------------------------------


def test_archiver_sort_loffre_du_fil_du_premier_coup(client):
    oid = _offre(url="https://www.linkedin.com/jobs/view/900001")
    assert any(o["id"] == oid for o in
               client.get("/api/offres?limite=500").json()["offres"])

    r = client.post(f"/api/offres/{oid}/constat?en_ligne=false")
    assert r.status_code == 200

    fil = client.get("/api/offres?limite=500").json()["offres"]
    assert not any(o["id"] == oid for o in fil), "un seul clic doit suffire"

    archive = client.get("/api/archive").json()["offres"]
    ligne = next(o for o in archive if o["id"] == oid)
    assert "edouard" in ligne["archive_motif"].lower()


def test_le_retour_arriere_aussi_du_premier_coup(client):
    oid = _offre(url="https://www.linkedin.com/jobs/view/900002")
    client.post(f"/api/offres/{oid}/constat?en_ligne=false")
    client.post(f"/api/offres/{oid}/desarchiver")

    fil = client.get("/api/offres?limite=500").json()["offres"]
    assert any(o["id"] == oid for o in fil), "elle doit revenir sans second clic"
    assert not any(o["id"] == oid for o in client.get("/api/archive").json()["offres"])


def test_les_deux_chemins_ecrivent_le_meme_etat(client):
    """Le bouton de la carte et celui de la fiche doivent etre indiscernables."""
    a = _offre(url="https://www.linkedin.com/jobs/view/900003")
    b = _offre(url="https://www.linkedin.com/jobs/view/900004")

    client.post(f"/api/offres/{a}/constat?en_ligne=false")   # bouton de la carte
    client.post(f"/api/offres/{b}/constat?en_ligne=false")   # bouton de la fiche

    ea, eb = db.lire_offre(a), db.lire_offre(b)
    for champ in ("verifiee_par", "verdict_verification", "archive_motif",
                  "probablement_retiree", "echecs_verification"):
        assert ea[champ] == eb[champ], f"{champ} differe entre les deux chemins"
    assert ea["archivee_le"] and eb["archivee_le"]


def test_une_route_dactions_inexistante_serait_visible(client):
    """Si une route disparait, l'appel doit echouer FRANCHEMENT, pas en silence."""
    oid = _offre(url="https://www.linkedin.com/jobs/view/900005")
    assert client.post(f"/api/offres/{oid}/retiree").status_code == 404
    assert db.lire_offre(oid)["archivee_le"] is None


def test_marquer_interessante_sort_bien_loffre_des_nouveautes(client):
    """L'autre action a deux chemins : verifier qu'elle n'a pas la meme derive."""
    oid = _offre(url="https://www.linkedin.com/jobs/view/900006")
    r = client.post(f"/api/offres/{oid}/statut", json={"statut": "interessante"})
    assert r.status_code == 200
    assert db.lire_offre(oid)["statut"] == "interessante"
    assert any(o["id"] == oid and o["statut"] == "interessante"
               for o in client.get("/api/offres?limite=500").json()["offres"])


# --------------------------------------------------------------------------
# 12. Le 410 archive en UNE passe — et lui seul
#
# Remarque d'Edouard, techniquement juste : « les annonces ou la verification
# donne un 410, tu peux les archiver sans attendre. Peut-etre pas les 404,
# parce que ca peut etre une autre raison, mais les 410, oui. »
#
# 410 Gone est une DECLARATION du serveur : la ressource a existe, elle est
# definitivement supprimee, et il le dit. 404 est MUET sur la cause — route
# cassee, ressource deplacee, erreur passagere, blocage. La difference de
# traitement suit exactement cette difference de nature.
#
# Tout le reste garde la regle des deux passes espacees de 20 h.
# --------------------------------------------------------------------------


def _domaine_deja_vivant(monkeypatch, url="https://jobs.ch/en/vacancies/detail/vivante"):
    """Le domaine a repondu « vivante » recemment : il n'est pas en panne.

    C'est la condition du garde-fou anti-panne : un domaine qui ne sert QUE des
    410 est suspect ; un domaine qui sert encore des annonces vivantes dit la
    verite quand il annonce un retrait.
    """
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_VIVANTE))
    temoin = _offre(url=url)
    verification.verifier_offre(temoin, maintenant=MAINTENANT)
    return temoin


def test_un_410_archive_des_la_premiere_passe(monkeypatch):
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=410))
    oid = _offre(url="https://jobs.ch/en/vacancies/detail/partie")
    d = verification.verifier_offre(oid, maintenant=MAINTENANT)
    assert d.archivee, f"un 410 est une declaration, pas un constat : {d}"
    o = db.lire_offre(oid)
    assert o["archivee_le"]
    assert "410" in o["archive_motif"]
    assert "definitiv" in o["archive_motif"].lower(), o["archive_motif"]


def test_un_404_attend_toujours_la_seconde_passe(monkeypatch):
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=404))
    oid = _offre(url="https://jobs.ch/en/vacancies/detail/404")
    assert not verification.verifier_offre(oid, maintenant=MAINTENANT).archivee
    assert verification.verifier_offre(oid, maintenant=PLUS_TARD).archivee


def test_une_page_dexpiration_en_200_attend_toujours(monkeypatch):
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=200, texte=PAGE_EXPIREE))
    oid = _offre(url="https://jobs.ch/en/vacancies/detail/expiree")
    d = verification.verifier_offre(oid, maintenant=MAINTENANT)
    assert not d.archivee, "une page d'expiration n'est pas une declaration du serveur"
    assert verification.verifier_offre(oid, maintenant=PLUS_TARD).archivee


def test_une_redirection_attend_toujours_trois_passes(monkeypatch):
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=200, texte="Trouvez votre emploi",
                                 url="https://jobs.ch/"))
    oid = _offre(url="https://jobs.ch/en/vacancies/detail/redirigee")
    assert not verification.verifier_offre(oid, maintenant=MAINTENANT).archivee
    assert not verification.verifier_offre(oid, maintenant=PLUS_TARD).archivee
    assert verification.verifier_offre(oid, maintenant=ENCORE_PLUS_TARD).archivee


@pytest.mark.parametrize("code", [429, 503, 500, 403])
def test_une_panne_ne_compte_jamais_comme_une_absence(monkeypatch, code):
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=code))
    oid = _offre(url="https://jobs.ch/en/vacancies/detail/panne")
    d = verification.verifier_offre(oid, maintenant=MAINTENANT)
    assert not d.archivee
    assert db.lire_offre(oid)["echecs_verification"] == 0


# --- Les protections restent absolues -----------------------------------


@pytest.mark.parametrize("statut", ["interessante", "a_traiter", "candidature_envoyee"])
def test_un_410_narchive_jamais_une_offre_triee(monkeypatch, statut):
    """La regle qui protege son historique de candidature ne souffre aucune
    exception — 410 ou pas."""
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=410))
    oid = _offre(url=f"https://jobs.ch/en/vacancies/detail/protegee-{statut}")
    db.changer_statut(oid, statut)
    d = verification.verifier_offre(oid, maintenant=MAINTENANT)
    assert not d.archivee, f"{statut} ne part jamais a l'archive"
    o = db.lire_offre(oid)
    assert not o["archivee_le"]
    assert o["probablement_retiree"], "mais il doit etre prevenu"


def test_un_410_narchive_pas_une_offre_avec_dossier(monkeypatch):
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=410))
    oid = _offre(url="https://jobs.ch/en/vacancies/detail/avec-dossier")
    with db.connexion() as cx:
        cx.execute("UPDATE offres SET dossier_chemin = ? WHERE id = ?", ("/tmp/x", oid))
    assert not verification.verifier_offre(oid, maintenant=MAINTENANT).archivee
    assert db.lire_offre(oid)["probablement_retiree"]


# Les protections elles-memes, sur trois passes : une offre triee ou avec
# dossier ne part jamais a l'archive sur un 410, a aucune passe.


@pytest.mark.parametrize("statut", ["interessante", "a_traiter", "candidature_envoyee"])
def test_un_410_laisse_a_labri_une_offre_triee(monkeypatch, statut):
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=410))
    oid = _offre(url=f"https://jobs.ch/en/vacancies/detail/abri-{statut}")
    db.changer_statut(oid, statut)
    for moment in (MAINTENANT, PLUS_TARD, ENCORE_PLUS_TARD):
        assert not verification.verifier_offre(oid, maintenant=moment).archivee, statut
        assert not db.lire_offre(oid)["archivee_le"], statut


def test_un_410_laisse_a_labri_une_offre_avec_dossier(monkeypatch):
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=410))
    oid = _offre(url="https://jobs.ch/en/vacancies/detail/abri-dossier")
    with db.connexion() as cx:
        cx.execute("UPDATE offres SET dossier_chemin = ? WHERE id = ?", ("/tmp/x", oid))
    for moment in (MAINTENANT, PLUS_TARD, ENCORE_PLUS_TARD):
        assert not verification.verifier_offre(oid, maintenant=moment).archivee
        assert not db.lire_offre(oid)["archivee_le"]


def test_un_410_ne_rearchive_pas_ce_quil_vient_de_ressortir(monkeypatch):
    """Un 410 peut mentir. Sa decision a lui reste definitive."""
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=410))
    oid = _offre(url="https://jobs.ch/en/vacancies/detail/ressortie")
    verification.verifier_offre(oid, maintenant=MAINTENANT)
    assert db.lire_offre(oid)["archivee_le"]

    db.desarchiver(oid)
    d = verification.verifier_offre(oid, maintenant=PLUS_TARD)
    assert not d.archivee, "ne jamais rearchiver ce qu'il vient de ressortir"


# --- Le garde-fou anti-panne de domaine ---------------------------------


def test_un_domaine_qui_ne_sert_que_des_410_nest_pas_cru_sur_parole(monkeypatch):
    """Si un domaine entier bascule en 410, c'est plus probablement une panne
    qu'une purge. On retombe alors sur la regle des deux passes."""
    _servir(monkeypatch, Reponse(code=410))
    oid = _offre(url="https://arbeitnow.com/jobs/companies/x/panne-generale")
    d = verification.verifier_offre(oid, maintenant=MAINTENANT)
    assert not d.archivee, (
        "aucune annonce vivante connue sur ce domaine : le 410 n'est pas credible"
    )
    assert db.lire_offre(oid)["echecs_verification"] == 1, "la preuve est gardee"


def test_la_fenetre_du_domaine_se_compte_depuis_l_heure_de_la_verification():
    """Les sept jours se comptent depuis l'instant que la vérification reçoit,
    pas depuis l'horloge du poste. Comptés depuis l'horloge, les cas du 410,
    figés au 29/09/2026, ont échoué à partir du 06/10, sans que la règle ait
    changé (issue #3)."""
    temoin = _offre(url="https://horloge.exemple.invalid/offre/vivante")
    db.enregistrer_verification(temoin, "vivante", "en ligne", MAINTENANT,
                                avance=False, reinitialise=True)
    domaine = "horloge.exemple.invalid"
    assert db.domaine_sert_encore(domaine, maintenant=MAINTENANT + timedelta(days=6))
    assert not db.domaine_sert_encore(domaine, maintenant=MAINTENANT + timedelta(days=8))


def test_le_410_redevient_immediat_des_que_le_domaine_repond(monkeypatch):
    _servir(monkeypatch, Reponse(code=410))
    oid = _offre(url="https://arbeitnow.com/jobs/companies/x/attente")
    assert not verification.verifier_offre(oid, maintenant=MAINTENANT).archivee

    _domaine_deja_vivant(monkeypatch, "https://arbeitnow.com/jobs/companies/y/vivante")
    _servir(monkeypatch, Reponse(code=410))
    autre = _offre(url="https://arbeitnow.com/jobs/companies/z/partie")
    assert verification.verifier_offre(autre, maintenant=MAINTENANT).archivee


def test_le_motif_distingue_les_deux_regimes(monkeypatch):
    """L'archive doit dire POURQUOI, et avec quel degre de certitude."""
    _domaine_deja_vivant(monkeypatch)
    _servir(monkeypatch, Reponse(code=410))
    a = _offre(url="https://jobs.ch/en/vacancies/detail/motif-410")
    verification.verifier_offre(a, maintenant=MAINTENANT)

    _servir(monkeypatch, Reponse(code=404))
    b = _offre(url="https://jobs.ch/en/vacancies/detail/motif-404")
    verification.verifier_offre(b, maintenant=MAINTENANT)
    verification.verifier_offre(b, maintenant=PLUS_TARD)

    m410 = db.lire_offre(a)["archive_motif"]
    m404 = db.lire_offre(b)["archive_motif"]
    assert m410 != m404
    assert "410" in m410 and "declare" in m410.lower()
    assert "verification" in m404.lower() and "410" not in m404
