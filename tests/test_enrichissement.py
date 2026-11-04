"""Lecture du texte complet d'une annonce.

Les refus comptent plus que les réussites : c'est le compte LinkedIn d'Édouard
qui est en jeu, et la règle doit tenir **par construction**, pas par précaution.
"""

from __future__ import annotations

import json
import time

import pytest

from veille import db, enrichissement
from veille.models import Offre
from veille.scoring import scorer


@pytest.fixture(autouse=True)
def base(monkeypatch):
    db.initialiser()
    enrichissement._ROBOTS.clear()
    # ATTENTION : `marquer_etat_collecte` avec une chaine vide NE remet PAS le
    # marqueur a zero — son COALESCE conserve l'ancienne valeur, ce qui est
    # voulu pour les collecteurs. Ici on veut vraiment repartir de zero.
    with db.connexion() as cx:
        cx.execute("DELETE FROM etat_collecte WHERE source = ?", (enrichissement.CLE_CADENCE,))
        cx.execute("DELETE FROM offres WHERE source = 'test:enrichissement'")
    monkeypatch.setattr(enrichissement, "charger_sources", lambda: {
        "enrichissement": {
            "actif": True,
            "delai_entre_requetes_s": 20,
            "plafond_quotidien": 30,
            "domaines_interdits": ["linkedin.com", "indeed.com"],
            "domaines_autorises": ["jobs.ch", "arbeitnow.com"],
        }
    })


def _robots(monkeypatch, contenu="User-agent: *\nDisallow:\n"):
    """Sert un robots.txt sans toucher au reseau."""
    class Rep:
        status_code = 200
        text = contenu

    monkeypatch.setattr(enrichissement.httpx, "get", lambda *a, **k: Rep())


# --------------------------------------------------------------------------
# Les refus
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/4000000001",
        "https://linkedin.com/jobs/view/123",
        "https://fr.indeed.com/viewjob?jk=abc",
    ],
)
def test_linkedin_et_indeed_sont_refuses_sans_meme_une_requete(url, monkeypatch):
    """Leur robots.txt l'interdit. Le refus ne doit dependre d'aucun appel."""
    def interdit(*a, **k):
        raise AssertionError("aucune requete ne doit partir vers un domaine interdit")

    monkeypatch.setattr(enrichissement.httpx, "get", interdit)
    p = enrichissement.politique(url)
    assert not p.autorise
    assert "interdit" in p.raison.lower()
    assert "colle" in p.conseil.lower(), "le refus doit proposer l'alternative"


def test_un_domaine_hors_liste_blanche_est_refuse(monkeypatch):
    monkeypatch.setattr(enrichissement.httpx, "get",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("pas de requete")))
    p = enrichissement.politique("https://exemple-inconnu.fr/offre/123")
    assert not p.autorise
    assert "liste blanche" in p.raison


def test_le_robots_txt_prime_sur_la_liste_blanche(monkeypatch):
    """La liste blanche dit ce qu'on a etudie ; le robots.txt dit ce que le
    site autorise aujourd'hui. Une politique peut changer apres notre etude."""
    _robots(monkeypatch, "User-agent: *\nDisallow: /\n")
    p = enrichissement.politique("https://jobs.ch/en/vacancies/detail/abc")
    assert not p.autorise
    assert "robots.txt" in p.raison


def test_un_robots_txt_illisible_fait_sabstenir(monkeypatch):
    def echoue(*a, **k):
        raise OSError("reseau coupe")

    monkeypatch.setattr(enrichissement.httpx, "get", echoue)
    p = enrichissement.politique("https://jobs.ch/en/vacancies/detail/abc")
    assert not p.autorise
    assert "doute" in p.raison


def test_un_domaine_autorise_passe(monkeypatch):
    _robots(monkeypatch)
    p = enrichissement.politique("https://jobs.ch/en/vacancies/detail/abc")
    assert p.autorise


def test_lenrichissement_peut_etre_coupe_globalement(monkeypatch):
    monkeypatch.setattr(enrichissement, "charger_sources",
                        lambda: {"enrichissement": {"actif": False}})
    assert not enrichissement.politique("https://jobs.ch/x").autorise


# --------------------------------------------------------------------------
# La cadence
# --------------------------------------------------------------------------


def test_deux_recuperations_de_suite_sont_espacees():
    """Pas de rafale s'il marque dix offres d'affilee."""
    db.marquer_etat_collecte(
        enrichissement.CLE_CADENCE,
        marqueur=json.dumps({"jour": enrichissement.date.today().isoformat(),
                             "compte": 1, "dernier": time.time()}),
    )
    possible, message = enrichissement.verifier_cadence()
    assert not possible
    assert "attends" in message


def test_le_plafond_quotidien_arrete_tout():
    db.marquer_etat_collecte(
        enrichissement.CLE_CADENCE,
        marqueur=json.dumps({"jour": enrichissement.date.today().isoformat(),
                             "compte": 30, "dernier": 0}),
    )
    possible, message = enrichissement.verifier_cadence()
    assert not possible
    assert "plafond" in message


def test_le_compteur_repart_chaque_jour():
    db.marquer_etat_collecte(
        enrichissement.CLE_CADENCE,
        marqueur=json.dumps({"jour": "2020-01-01", "compte": 99, "dernier": 0}),
    )
    assert enrichissement.verifier_cadence()[0]


# --------------------------------------------------------------------------
# Nettoyage du collage
# --------------------------------------------------------------------------


def test_un_collage_html_est_nettoye():
    """Il colle depuis un site, avec la mise en forme. Il ne doit rien nettoyer."""
    brut = ("<div><script>var x=1;</script><h1>Test Engineer</h1>"
            "<p>Astreinte une semaine sur quatre.</p><footer>Mentions</footer></div>")
    propre = enrichissement.nettoyer_texte(brut)
    assert "Test Engineer" in propre
    assert "Astreinte une semaine sur quatre." in propre
    assert "var x" not in propre
    assert "Mentions" not in propre


def test_le_texte_brut_passe_tel_quel():
    propre = enrichissement.nettoyer_texte("Test Engineer\n\nAstreinte le week-end.")
    assert "Astreinte le week-end." in propre


def test_le_texte_est_plafonne():
    assert len(enrichissement.nettoyer_texte("a" * 50000)) == enrichissement.LONGUEUR_MAX


# --------------------------------------------------------------------------
# Ce que l'enrichissement change — le cœur de l'affaire
# --------------------------------------------------------------------------


def _offre_partielle() -> int:
    # La premiere famille de l'exemple : sur un extrait, l'offre part au-dessus
    # du seuil.
    o = scorer(Offre(
        titre="Test Automation Engineer",
        employeur="Societe Test Enrichissement",
        lieu="Mulhouse",
        description="Rejoignez notre equipe.",     # extrait pauvre
        url="https://jobs.ch/en/vacancies/detail/abc",
        source="test:enrichissement",
        donnees_partielles=True,
    ))
    oid, _ = db.enregistrer_offre(o)
    return oid


def test_le_texte_complet_fait_apparaitre_un_critere_eliminatoire():
    """LE cas le plus utile : une offre qui semblait parfaite et qui demande
    des astreintes le week-end."""
    oid = _offre_partielle()
    avant = db.lire_offre(oid)
    assert avant["score"] >= 45, "l'offre doit partir au-dessus du seuil"

    r = enrichissement.appliquer_texte(
        oid,
        "Test Manager chez nous. Vous participerez a une astreinte une semaine "
        "sur quatre, ainsi qu'au travail le week-end selon les besoins du service. "
        "Poste base a Mulhouse, equipe de dix personnes, environnement stimulant.",
        "colle a la main",
    )
    assert r.ok
    assert r.alerte_eliminatoire, "le changement doit etre SIGNALE, pas silencieux"
    # Les DEUX criteres sont dans le texte : l'alerte doit les nommer tous.
    assert "astreinte" in r.alerte_eliminatoire.lower()
    assert "week-end" in r.alerte_eliminatoire.lower()

    apres = db.lire_offre(oid)
    assert apres["rejete_auto"]
    assert apres["statut"] == "ecartee"
    assert not apres["donnees_partielles"], "ce n'est plus un extrait"


def test_le_salaire_absent_est_retrouve_dans_le_texte():
    oid = _offre_partielle()
    r = enrichissement.appliquer_texte(
        oid,
        "Test Manager a Mulhouse. Nous proposons une remuneration entre 46000 et "
        "50000 euros selon profil. Equipe de dix personnes, beaux projets, "
        "environnement stimulant et bienveillant pour progresser. Le poste est "
        "a pourvoir des que possible, en CDI, au sein d'une equipe deja "
        "constituee qui travaille sur des sujets varies.",
        "colle a la main",
    )
    assert r.ok
    assert "46" in r.salaire_trouve
    apres = db.lire_offre(oid)
    assert apres["salaire_min"] == 46000


def test_une_decision_manuelle_nest_jamais_ecrasee():
    """Le moteur peut revenir sur SES decisions, jamais sur les siennes."""
    oid = _offre_partielle()
    db.changer_statut(oid, "interessante")
    enrichissement.appliquer_texte(
        oid,
        "Poste interessant. Astreinte une semaine sur quatre et travail le "
        "week-end. Base a Mulhouse dans une equipe de dix personnes motivees. Le poste est a pourvoir des que possible, en CDI, au sein d'une equipe deja constituee. Vous travaillerez avec les equipes metier et technique sur des sujets varies.",
        "colle a la main",
    )
    apres = db.lire_offre(oid)
    assert apres["statut"] == "interessante", "son tri l'emporte"
    assert apres["rejete_auto"], "mais le scoring dit quand meme ce qu'il pense"


def test_lorigine_est_tracee():
    oid = _offre_partielle()
    enrichissement.appliquer_texte(oid, "x" * 400, "recupere sur jobs.ch")
    o = db.lire_offre(oid)
    assert o["enrichi_par"] == "recupere sur jobs.ch"
    assert o["enrichi_le"]
    assert any(e["type"] == "texte_complet" for e in o["evenements"])


def test_un_texte_trop_court_est_refuse():
    oid = _offre_partielle()
    r = enrichissement.appliquer_texte(oid, "trop court", "colle a la main")
    assert not r.ok
    assert "fragment" in r.message


# --------------------------------------------------------------------------
# Récupération : l'échec doit être dit
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,attendu",
    [(410, "retiree"), (404, "n'existe plus"), (403, "HTTP 403")],
)
def test_un_echec_de_recuperation_est_annonce(monkeypatch, code, attendu):
    class Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url):
            return type("R", (), {"status_code": code, "text": ""})()

    monkeypatch.setattr(enrichissement.httpx, "Client", lambda *a, **k: Client())
    texte, message = enrichissement.recuperer("https://jobs.ch/x")
    assert texte == ""
    assert attendu in message


def test_une_page_vide_le_dit_au_lieu_de_faire_semblant(monkeypatch):
    """Beaucoup d'annonces sont rendues en JavaScript : la page arrive vide.
    Il faut le dire, pas laisser croire que l'annonce est pauvre."""
    class Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url):
            return type("R", (), {"status_code": 200, "text": "<html><body>Chargement…</body></html>"})()

    monkeypatch.setattr(enrichissement.httpx, "Client", lambda *a, **k: Client())
    texte, message = enrichissement.recuperer("https://jobs.ch/x")
    assert texte == ""
    assert "javascript" in message.lower()
    assert "colle" in message.lower()
