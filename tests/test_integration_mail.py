"""Chaine complete du canal mail, de l'octet brut a la base.

Ce canal est celui qui debloque LinkedIn, Indeed, jobs.ch et les pages
carriere. Il ne pourra etre eprouve sur de vraies alertes que le jour ou le
mot de passe d'application sera pose. Ces tests le font des maintenant, sur des
messages construits a l'identique : en-tetes, multipart texte+HTML, encodage
quoted-printable, tableaux imbriques, liens de suivi.

L'objectif est qu'au premier vrai mail, rien ne reste a decouvrir.
"""

from __future__ import annotations

import email
import email.policy
from email.message import EmailMessage

import httpx
import pytest

from veille import db
from veille.collectors.base import ingerer
from veille.collectors.courriel import _corps, _decoder, convertir
from veille.collectors.parsers import analyser


def _mail(expediteur: str, sujet: str, html: str, texte: str = "Version texte.") -> EmailMessage:
    """Construit un mail multipart realiste, puis le relit depuis ses octets.

    Le passage par les octets est important : c'est ce que fait IMAP, et c'est
    la que se jouent les encodages (accents, quoted-printable, en-tetes MIME).
    """
    m = EmailMessage()
    m["From"] = expediteur
    m["To"] = "camille@exemple.invalid"
    m["Subject"] = sujet
    m["Date"] = "Sat, 27 Sep 2026 07:15:00 +0200"
    m.set_content(texte)
    m.add_alternative(html, subtype="html")
    return email.message_from_bytes(m.as_bytes(), policy=email.policy.default)


HTML_LINKEDIN = """
<html><body><table><tr><td>
  <table><tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=AbC%3D&midToken=x">
      Test Automation Engineer (Accessibility)</a>
    <p>Exemplia</p><p>Bâle, Bâle-Ville, Suisse</p>
    <p>Appium, WCAG audits of our mobile apps. 100'000 - 115'000 CHF</p>
  </td></tr></table>
  <table><tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4099999999/?trackingId=QqQ">
      Ingénieur QA — astreinte week-end</a>
    <p>Une société</p><p>Strasbourg, France</p>
    <p>Astreinte une semaine sur quatre. Travail le week-end.</p>
  </td></tr></table>
  <a href="https://www.linkedin.com/e/unsubscribe/zz">Se désabonner</a>
</td></tr></table></body></html>
"""

HTML_INDEED = """
<html><body><table><tr><td>
  <a href="https://fr.indeed.com/rc/clk?jk=a1b2c3d4e5f6a7b8&fccid=z">Ingénieur QA H/F</a>
  <div>Entreprise Exemple SA - Mulhouse (68)</div>
  <div>44 000 EUR - 55 000 EUR par an</div><div>CDI</div>
</td></tr></table></body></html>
"""

HTML_CARRIERE = """
<html><body>
<p>Nouvelles offres correspondant à votre alerte :</p>
<table><tr><td>
  <a href="https://careers.logistique-exemple.invalid/job/1234567/digital-accessibility-specialist">Digital Accessibility Specialist</a>
  <div>Logistique Exemple SA</div><div>Basel, Switzerland</div>
</td></tr></table>
<a href="https://careers.logistique-exemple.invalid/jobs">Voir toutes nos offres</a>
</body></html>
"""


@pytest.fixture(autouse=True)
def base_vierge(monkeypatch, tmp_path):
    """Chaque test repart d'une base propre, isolee de la vraie."""
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    db.initialiser()


def _ingerer(message: EmailMessage) -> list:
    """Reproduit exactement ce que fait le collecteur, sans IMAP."""
    expediteur, sujet = _decoder(message.get("From")), _decoder(message.get("Subject"))
    html, texte = _corps(message)
    parseur, annonces = analyser(html, texte, expediteur, sujet)
    # Aucun appel reseau ici : les liens LinkedIn et Indeed portent leur
    # identifiant, donc `liens.resoudre` les reconstruit hors ligne. Si un
    # test se met a ralentir, c'est qu'un lien est tombe dans la branche
    # reseau - et c'est un signal, pas un detail.
    with httpx.Client() as client:
        return [convertir(a, parseur, expediteur, None, client) for a in annonces]


# --------------------------------------------------------------------------
# Decodage
# --------------------------------------------------------------------------


def test_les_accents_survivent_au_passage_par_les_octets():
    m = _mail("jobs-listings@linkedin.com", "Offres pour vous", HTML_LINKEDIN)
    html, _ = _corps(m)
    assert "Bâle" in html
    assert "Ingénieur" in html


def test_un_sujet_encode_mime_est_decode():
    m = EmailMessage()
    m["From"] = "jobs-listings@linkedin.com"
    m["Subject"] = "5 nouvelles offres « Testeur » pour vous"
    m.set_content("x")
    relu = email.message_from_bytes(m.as_bytes(), policy=email.policy.default)
    assert "Testeur" in _decoder(relu.get("Subject"))


# --------------------------------------------------------------------------
# LinkedIn, de bout en bout
# --------------------------------------------------------------------------


def test_alerte_linkedin_jusquen_base(monkeypatch):
    offres = _ingerer(_mail("jobs-listings@linkedin.com", "Offres pour vous", HTML_LINKEDIN))
    assert len(offres) == 2

    rapport = ingerer(offres, "mail:linkedin")
    assert rapport.nouvelles == 2
    assert not rapport.erreurs

    # L'offre avec astreinte ET week-end part directement au rebut, avec motif.
    ecartees = db.lister_offres(statut="ecartee", limite=10)
    assert len(ecartees) == 1
    assert "astreinte" in ecartees[0]["motif_ecartement"].lower() \
        or "week-end" in ecartees[0]["motif_ecartement"].lower()

    # L'autre reste dans le flux, avec son atout rare.
    actives = db.lister_offres(limite=10)
    assert len(actives) == 1
    retenue = actives[0]
    assert retenue["titre"].startswith("Test Automation Engineer")
    assert retenue["employeur"] == "Exemplia"
    assert "accessibilite" in retenue["atouts"], "‘WCAG audits’ doit declencher son atout rare"
    assert retenue["salaire_devise"] == "CHF"
    assert retenue["score"] > 50


def test_le_lien_de_suivi_devient_une_url_canonique():
    offres = _ingerer(_mail("jobs-listings@linkedin.com", "Offres", HTML_LINKEDIN))
    url = offres[0].url_canonique
    assert "4012345678" in url
    assert "trackingid" not in url.lower()
    assert "midtoken" not in url.lower()


def test_la_meme_alerte_recue_deux_fois_ne_cree_pas_de_doublon():
    """Gmail peut re-livrer, et les alertes se chevauchent d'un jour a l'autre."""
    premier = ingerer(_ingerer(_mail("jobs-listings@linkedin.com", "Offres", HTML_LINKEDIN)), "mail:linkedin")
    second = ingerer(_ingerer(_mail("jobs-listings@linkedin.com", "Offres", HTML_LINKEDIN)), "mail:linkedin")
    assert premier.nouvelles == 2
    assert second.nouvelles == 0


def test_une_offre_ecartee_a_la_main_ne_remonte_jamais():
    ingerer(_ingerer(_mail("jobs-listings@linkedin.com", "Offres", HTML_LINKEDIN)), "mail:linkedin")
    oid = db.lister_offres(limite=1)[0]["id"]
    db.changer_statut(oid, "ecartee", motif="deja postule en mai")

    # Le meme mail revient le lendemain.
    ingerer(_ingerer(_mail("jobs-listings@linkedin.com", "Offres", HTML_LINKEDIN)), "mail:linkedin")
    assert oid not in [o["id"] for o in db.lister_offres(limite=20)]
    assert db.lire_offre(oid)["motif_ecartement"] == "deja postule en mai"


# --------------------------------------------------------------------------
# Indeed et pages carriere
# --------------------------------------------------------------------------


def test_alerte_indeed_salaire_et_contrat():
    offres = _ingerer(_mail("alert@indeed.com", "Nouvelles offres", HTML_INDEED))
    assert len(offres) == 1
    o = offres[0]
    assert o.titre == "Ingénieur QA H/F"
    assert (o.salaire_min, o.salaire_max) == (44000, 55000)
    assert o.salaire_devise == "EUR"


def test_alerte_page_carriere_sans_api_ni_flux():
    """Le cas qui justifie tout le canal mail : un employeur sans API ni RSS."""
    offres = _ingerer(_mail("careers@logistique-exemple.invalid", "New job alert", HTML_CARRIERE))
    assert len(offres) == 1
    o = offres[0]
    assert o.titre == "Digital Accessibility Specialist"
    assert "Logistique Exemple SA" in o.employeur
    assert "Basel" in o.lieu

    ingerer(offres, "mail:generique")
    enregistree = db.lister_offres(limite=1)[0]
    assert "accessibilite" in enregistree["atouts"]
    assert enregistree["zone"] == "zone_proche"


# --------------------------------------------------------------------------
# Donnees partielles
# --------------------------------------------------------------------------


def test_un_mail_sans_extrait_est_marque_donnees_partielles():
    html = """<html><body><table><tr><td>
      <a href="https://www.linkedin.com/comm/jobs/view/4011111111/">Test Engineer</a>
      <p>Fictivia</p><p>Basel</p>
    </td></tr></table></body></html>"""
    offres = _ingerer(_mail("jobs-listings@linkedin.com", "Offres", html))
    assert offres[0].donnees_partielles
    ingerer(offres, "mail:linkedin")
    o = db.lister_offres(limite=1)[0]
    assert o["donnees_partielles"]
    detail = " ".join(c["detail"] for c in o["explication"])
    assert "extrait" in detail.lower(), "l'explication doit le dire, pas faire semblant"


# --------------------------------------------------------------------------
# Robustesse
# --------------------------------------------------------------------------


def test_un_mail_vide_ne_casse_rien():
    offres = _ingerer(_mail("careers@exemple.fr", "Rien", "<html><body></body></html>"))
    assert offres == []
    assert ingerer(offres, "mail:generique").nouvelles == 0


def test_un_html_casse_ne_casse_rien():
    """Les alertes mail sont souvent du HTML mal forme : lxml doit le reparer."""
    html = "<html><body><table><tr><td><a href='https://careers.exemple.fr/job/123'>Test Engineer"
    offres = _ingerer(_mail("careers@exemple.fr", "Alerte", html))
    assert len(offres) == 1
    assert offres[0].titre == "Test Engineer"


def test_le_rendement_par_source_est_correct():
    ingerer(_ingerer(_mail("jobs-listings@linkedin.com", "Offres", HTML_LINKEDIN)), "mail:linkedin")
    ingerer(_ingerer(_mail("alert@indeed.com", "Offres", HTML_INDEED)), "mail:indeed")
    sources = {s["source"]: s for s in db.entonnoir()["par_source"]}
    assert sources["mail:linkedin"]["collectees"] == 2
    assert sources["mail:linkedin"]["retenues"] == 1   # une ecartee d'office
    assert sources["mail:indeed"]["collectees"] == 1
