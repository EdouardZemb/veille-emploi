"""Tests des parseurs d'alertes mail.

Les echantillons reproduisent la structure reelle des alertes : des tableaux
imbriques, un lien de suivi qui masque l'URL, et l'employeur/le lieu dans des
cellules voisines. Ce sont les deux pieges du parsing d'alertes.
"""

from __future__ import annotations

import pytest

from veille.collectors.base import extraire_salaire
from veille.collectors.liens import resoudre
from veille.collectors.parsers import analyser, choisir

# --------------------------------------------------------------------------
# Echantillons
# --------------------------------------------------------------------------

MAIL_LINKEDIN = """
<html><body>
<table><tr><td>
  <table><tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=AbC%3D&refId=xyz&midToken=zz">
      Test Automation Engineer
    </a>
    <p>Exemplia</p>
    <p>Basel, Basel-Stadt, Switzerland</p>
  </td></tr></table>
  <table><tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4099999999/?trackingId=QqQ">
      Senior QA Engineer (m/w/d)
    </a>
    <p>Fictivia</p>
    <p>Basel, Switzerland</p>
  </td></tr></table>
  <a href="https://www.linkedin.com/comm/jobs/search/?keywords=qa">Voir toutes les offres</a>
  <a href="https://www.linkedin.com/e/unsubscribe/abc">Se desabonner</a>
</td></tr></table>
</body></html>
"""

MAIL_INDEED = """
<html><body>
<table><tr><td>
  <a href="https://fr.indeed.com/rc/clk?jk=a1b2c3d4e5f6a7b8&fccid=zz&vjs=3">Ingenieur QA H/F</a>
  <div>Entreprise Exemple SA - Mulhouse (68)</div>
  <div>44 000 EUR - 55 000 EUR par an</div>
  <div>CDI</div>
</td></tr>
<tr><td>
  <a href="https://fr.indeed.com/rc/clk?jk=ffffeeee11112222">Testeur logiciel</a>
  <div>Conseil Exemple - Mulhouse (68)</div>
</td></tr></table>
<a href="https://fr.indeed.com/alert/unsubscribe?token=x">Se desabonner</a>
</body></html>
"""

MAIL_JOBSCH = """
<html><body>
<table><tr><td>
  <a href="https://www.jobs.ch/fr/vacancies/detail/12345678/?source=alert">
    Software Test Engineer 80-100%
  </a>
  <div>Assurances Exemple</div>
  <div>Basel</div>
  <div>CHF 100'000 - 115'000</div>
</td></tr></table>
</body></html>
"""

MAIL_CARRIERE = """
<html><body>
<p>Nouvelles offres correspondant a votre alerte :</p>
<table><tr><td>
  <a href="https://careers.logistique-exemple.invalid/job/1234567/it-quality-engineer">IT Quality Engineer</a>
  <div>Logistique Exemple SA</div>
  <div>Basel, Switzerland</div>
</td></tr></table>
<a href="https://careers.logistique-exemple.invalid/jobs">Voir toutes nos offres</a>
<a href="https://www.facebook.com/logistique-exemple">Facebook</a>
</body></html>
"""


# --------------------------------------------------------------------------
# Choix du parseur
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expediteur,sujet,attendu",
    [
        ("jobs-listings@linkedin.com", "5 nouvelles offres pour Test Engineer", "linkedin"),
        ("alert@indeed.com", "Nouvelles offres", "indeed"),
        ("noreply@jobs.ch", "Ihr Job-Abo", "jobs_ch"),
        ("careers@logistique-exemple.invalid", "New job matching your alert", "generique"),
    ],
)
def test_choix_du_parseur(expediteur, sujet, attendu):
    assert choisir(expediteur, sujet).cle == attendu


# --------------------------------------------------------------------------
# LinkedIn
# --------------------------------------------------------------------------


def test_linkedin_extrait_les_annonces_et_ignore_le_bruit():
    cle, annonces = analyser(MAIL_LINKEDIN, "", "jobs-listings@linkedin.com", "nouvelles offres")
    assert cle == "linkedin"
    assert len(annonces) == 2, [a.titre for a in annonces]
    titres = {a.titre for a in annonces}
    assert "Test Automation Engineer" in titres
    assert not any("desabonner" in t.lower() or "voir toutes" in t.lower() for t in titres)


def test_linkedin_trouve_employeur_et_lieu():
    _, annonces = analyser(MAIL_LINKEDIN, "", "jobs-listings@linkedin.com", "offres")
    a = next(x for x in annonces if x.titre == "Test Automation Engineer")
    assert a.employeur == "Exemplia"
    assert "Basel" in a.lieu


def test_linkedin_lien_de_suivi_resolu_en_url_canonique():
    """Deux liens de suivi differents vers la meme offre doivent converger."""
    a = resoudre(
        "https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=AAA&midToken=x",
        autoriser_reseau=False,
    )
    b = resoudre(
        "https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=BBB&refId=y",
        autoriser_reseau=False,
    )
    assert a == b
    assert "4012345678" in a
    assert "trackingid" not in a.lower()


# --------------------------------------------------------------------------
# Indeed
# --------------------------------------------------------------------------


def test_indeed_extrait_titre_employeur_lieu_et_salaire():
    cle, annonces = analyser(MAIL_INDEED, "", "alert@indeed.com", "nouvelles offres")
    assert cle == "indeed"
    assert len(annonces) == 2
    a = annonces[0]
    assert a.titre == "Ingenieur QA H/F"
    assert "Entreprise Exemple SA" in a.employeur or "Entreprise Exemple SA" in a.extrait
    assert "EUR" in a.salaire_texte or "000" in a.salaire_texte


def test_indeed_resolution_par_identifiant():
    u = resoudre("https://fr.indeed.com/rc/clk?jk=a1b2c3d4e5f6a7b8&fccid=zz", autoriser_reseau=False)
    assert "jk=a1b2c3d4e5f6a7b8" in u
    assert "fccid" not in u


# --------------------------------------------------------------------------
# jobs.ch
# --------------------------------------------------------------------------


def test_jobsch_extrait_et_marque_la_suisse():
    cle, annonces = analyser(MAIL_JOBSCH, "", "noreply@jobs.ch", "Job-Abo")
    assert cle == "jobs_ch"
    assert len(annonces) == 1
    a = annonces[0]
    assert "Software Test Engineer" in a.titre
    assert a.lieu  # jamais vide : "Suisse" par defaut
    assert "CHF" in a.salaire_texte


def test_jobsch_salaire_chf_avec_apostrophe_suisse():
    smin, smax, devise = extraire_salaire("CHF 100'000 - 115'000", devise_par_defaut="CHF")
    assert smin == 100000
    assert smax == 115000
    assert devise == "CHF"


# --------------------------------------------------------------------------
# Generique (pages carriere d'employeurs directs)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,attendu",
    [
        # Vraies fiches : un segment metier, suivi de quelque chose
        ("https://careers.logistique-exemple.invalid/job/1234567/it-quality-engineer", True),
        ("https://careers.exemplia.invalid/global/en/job/202512345/Test-Engineer", True),
        # Pages carriere a slug, SANS identifiant numerique : le cas qui
        # faisait rater les employeurs sans API ni flux.
        ("https://www.fictivia.invalid/careers/senior-test-engineer", True),
        ("https://jobs.assurances-exemple.invalid/stellen/qualitaetsingenieur", True),
        ("https://www.banque-mutuelle-exemple.invalid/offres/ingenieur-qa-strasbourg", True),
        # Tout en parametres
        ("https://recrutement.exemple.fr/recherche?jobId=98765", True),
        # Liens de navigation : segment metier SANS rien apres
        ("https://careers.logistique-exemple.invalid/jobs", False),
        ("https://www.fictivia.invalid/careers", False),
        ("https://careers.exemplia.invalid/global/en/careers/", False),
        # Liens sans rapport
        ("https://www.exemple.fr/a-propos/equipe", False),
        ("https://www.exemple.fr/", False),
    ],
)
def test_generique_distingue_fiche_et_navigation(url, attendu):
    from veille.collectors.parsers.generique import _ressemble_a_une_fiche

    assert _ressemble_a_une_fiche(url) is attendu, url


@pytest.mark.parametrize(
    "url,ignore",
    [
        ("https://www.facebook.com/logistique-exemple", True),
        ("https://x.com/exemplia", True),
        ("https://careers.logistique-exemple.invalid/unsubscribe?token=x", True),
        ("https://cdn.exemple.fr/logo.png", True),
        # Regression : sans ancrage, le motif "x.com" rejetait ces domaines,
        # qui peuvent parfaitement heberger une page carriere.
        ("https://careers.linux.com/job/123/engineer", False),
        ("https://jobs.phoenix.com/careers/test-engineer", False),
        ("https://netflix.com/careers/senior-qa", False),
    ],
)
def test_generique_nignore_que_les_vrais_liens_de_service(url, ignore):
    from veille.collectors.parsers.generique import _a_ignorer

    assert _a_ignorer(url) is ignore, url


def test_generique_trouve_loffre_et_ecarte_les_liens_de_navigation():
    cle, annonces = analyser(MAIL_CARRIERE, "", "careers@logistique-exemple.invalid", "New job alert")
    assert cle == "generique"
    assert len(annonces) == 1
    a = annonces[0]
    assert a.titre == "IT Quality Engineer"
    assert "Logistique Exemple SA" in a.employeur
    assert "Basel" in a.lieu


# --------------------------------------------------------------------------
# Extraction de salaire : les pieges
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texte,smin,smax",
    [
        ("Salaire : 44 000 EUR - 55 000 EUR par an", 44000, 55000),
        ("Remuneration entre 46000 et 50000 euros", 46000, 50000),
        ("CHF 100'000 a 115'000", 100000, 115000),
        ("Salaire annuel de 58 000 EUR", 58000, 58000),
    ],
)
def test_extraction_salaire(texte, smin, smax):
    a, b, _ = extraire_salaire(texte)
    assert (a, b) == (smin, smax)


@pytest.mark.parametrize(
    "texte",
    [
        "Reference de l'offre 2024001234",
        "Appelez le 01 23 45 67 89",
        "Code postal 68200 Mulhouse",
        "Nous sommes 15000 collaborateurs",
    ],
)
def test_extraction_salaire_ne_se_trompe_pas(texte):
    """Un nombre sans contexte de salaire ne doit jamais devenir un salaire."""
    assert extraire_salaire(texte) == (None, None, None)
