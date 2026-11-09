"""La file « À faire », le panneau « Non » et l'onglet « Plus », au téléphone (ADR-0003, §§ 2 et 3).

Même forme que `test_cibles_tactiles.py` : Chromium à la taille d'un téléphone, une session
ouverte par `auth.ouvrir_session`, aucune erreur dans la console. La base est partagée par
toute la session de tests : on ne regarde que les offres de la source `parcours`, et chaque
test qui change un statut a son offre à lui.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

from .test_cibles_tactiles import DOIGT, TELEPHONE

SOURCE = "parcours"
MOTIF = "motif inventé du parcours"
# Un intitulé de 200 caractères sans espace : il ne se coupe que si la page le permet.
LONG = ("Ingénieurqualitélogicielleinventé" * 7)[:200]
# Dans le désordre : la carte montre les deux contributions positives les plus fortes.
EXPLICATION = [
    {"libelle": "Raison inventée faible", "points": 5, "detail": ""},
    {"libelle": "Raison inventée contraire", "points": -10, "detail": ""},
    {"libelle": "Raison inventée forte", "points": 30, "detail": ""},
    {"libelle": "Raison inventée moyenne", "points": 15, "detail": ""},
]
VIDE = {"a_finir": [], "a_voir": [], "a_voir_restantes": 0, "plus_tard": [],
        "sous_le_seuil": 0, "seuil": 45}


@pytest.fixture(scope="module")
def parcours(serveur):
    """Cinq offres inventées en `nouveau`, au-dessus du seuil, dont une à l'intitulé de
    200 caractères ; une sixième, écartée, donne son motif au panneau « Non »."""
    from veille import db, reglages
    from veille.collectors.base import ingerer
    from veille.models import Offre

    assert len(LONG) == 200
    titres = [f"Testeur inventé du parcours {n}" for n in range(1, 5)]
    titres += [LONG, "Offre écartée inventée du parcours"]
    ingerer(
        [
            Offre(
                titre=titre,
                employeur=f"Employeur inventé {n}",
                lieu="Lieu inventé",
                description="Tests automatisés, inventés pour le parcours.",
                url=f"https://exemple.invalid/parcours/{n}",
            )
            for n, titre in enumerate(titres, 1)
        ],
        SOURCE,
    )
    with db.connexion() as cx:
        ids = [r["id"] for r in cx.execute(
            "SELECT id FROM offres WHERE source = ? ORDER BY id", (SOURCE,))]
    assert len(ids) == len(titres)
    # Les critères de l'exemple notent ces offres à leur façon : on fixe le score et
    # l'explication, comme le ferait un recalcul.
    with db.connexion() as cx:
        for offre_id in ids:
            cx.execute("UPDATE offres SET score = ?, explication = ? WHERE id = ?",
                       (reglages.lire_seuil() + 20,
                        json.dumps(EXPLICATION, ensure_ascii=False), offre_id))
    *a_voir, ecartee = ids
    for offre_id in a_voir:
        db.changer_statut(offre_id, "nouveau")
    db.changer_statut(ecartee, "ecartee", motif=MOTIF)
    plus_tard, non, en_ligne, temoin, long = a_voir
    return {"url": serveur, "plus_tard": plus_tard, "non": non, "en_ligne": en_ligne,
            "temoin": temoin, "long": long}


@pytest.fixture
def telephone(navigateur, parcours):
    from veille import auth

    contexte = navigateur.new_context(**TELEPHONE)
    contexte.add_cookies([{"name": auth.nom_cookie(),
                           "value": auth.ouvrir_session("Téléphone"), "url": parcours["url"]}])
    page = contexte.new_page()
    erreurs: list[str] = []
    page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    try:
        yield page
    finally:
        contexte.close()
    assert erreurs == []


def _ouvrir(page, url: str, chemin: str = "/") -> None:
    page.goto(f"{url}{chemin}")
    expect(page.locator("#contenu-a-faire")).not_to_be_empty()


def _carte(page, offre_id: int):
    return page.locator(f'#vue-a-faire .carte-a-voir[data-id="{offre_id}"]')


def _actif(page):
    return page.locator(".onglet.actif")


def test_la_console_s_ouvre_sur_a_faire(telephone, parcours):
    _ouvrir(telephone, parcours["url"])
    expect(telephone.locator("#vue-a-faire")).to_be_visible()
    expect(_actif(telephone)).to_have_attribute("data-vue", "a-faire")
    expect(telephone.locator("#vue-offres")).to_be_hidden()


def test_une_notification_mene_a_a_faire(telephone, parcours):
    """La notification push ouvre `/?filtre=nouveau` (notifications.py) : la file, pas une
    liste filtrée cachée sous « Plus » (décision 6 du plan)."""
    _ouvrir(telephone, parcours["url"], "/?filtre=nouveau")
    expect(telephone.locator("#vue-a-faire")).to_be_visible()
    expect(telephone.locator("#vue-offres")).to_be_hidden()
    expect(_actif(telephone)).to_have_attribute("data-vue", "a-faire")


def test_un_autre_filtre_mene_a_toutes_les_offres(telephone, parcours):
    telephone.goto(f"{parcours['url']}/?filtre=interessante")
    expect(telephone.locator("#vue-offres")).to_be_visible()
    expect(telephone.locator("#vue-a-faire")).to_be_hidden()
    expect(_actif(telephone)).to_have_attribute("data-vue", "plus")
    expect(telephone.locator("#f-statut")).to_have_value("interessante")


def test_plus_mene_aux_anciens_ecrans(telephone, parcours):
    _ouvrir(telephone, parcours["url"])
    telephone.get_by_role("button", name="Plus", exact=True).click()
    expect(telephone.locator("#vue-plus")).to_be_visible()
    telephone.get_by_role("button", name="Toutes les offres").click()
    expect(telephone.locator("#vue-offres .offre").first).to_be_visible()
    expect(telephone.locator("#vue-plus")).to_be_hidden()
    expect(_actif(telephone)).to_have_attribute("data-vue", "plus")

    telephone.get_by_role("button", name="‹ Plus").click()
    expect(telephone.locator("#vue-plus")).to_be_visible()
    expect(telephone.locator("#vue-offres")).to_be_hidden()
    expect(_actif(telephone)).to_have_attribute("data-vue", "plus")


def test_une_carte_a_voir_porte_trois_boutons_du_doigt(telephone, parcours):
    _ouvrir(telephone, parcours["url"])
    expect(_carte(telephone, parcours["temoin"])).to_be_visible()
    cartes = telephone.eval_on_selector_all(
        "#vue-a-faire .carte-a-voir",
        """cs => cs.map(c => [...c.querySelectorAll('.actions button')]
              .map(b => [b.textContent.trim(), b.getBoundingClientRect().height]))""")
    assert cartes
    for boutons in cartes:
        assert [texte for texte, _ in boutons] == ["Je postule", "Plus tard", "Non"]
        assert min(hauteur for _, hauteur in boutons) >= DOIGT


def test_une_carte_a_voir_montre_ses_deux_raisons_les_plus_fortes(telephone, parcours):
    _ouvrir(telephone, parcours["url"])
    carte = _carte(telephone, parcours["temoin"])
    expect(carte).to_be_visible()
    texte = carte.inner_text()
    assert "Employeur inventé 4" in texte
    assert "Lieu inventé" in texte
    assert texte.index("Raison inventée forte") < texte.index("Raison inventée moyenne")
    assert "Raison inventée faible" not in texte
    assert "Raison inventée contraire" not in texte


def test_plus_tard_ne_compte_qu_une_fois(telephone, parcours):
    """Un double toucher : un seul changement de statut, une seule ligne d'historique."""
    from veille import db

    offre_id = parcours["plus_tard"]
    envois: list[str] = []
    telephone.on("request", lambda r: envois.append(r.url)
                 if r.method == "POST" and r.url.endswith("/statut") else None)
    _ouvrir(telephone, parcours["url"])
    _carte(telephone, offre_id).locator('[data-action="plus-tard"]').dblclick()

    expect(telephone.locator(
        f'#vue-a-faire details.plus-tard [data-id="{offre_id}"]')).to_have_count(1)
    expect(_carte(telephone, offre_id)).to_have_count(0)
    assert len(envois) == 1
    offre = db.lire_offre(offre_id)
    assert offre["statut"] == "a_traiter"
    assert [e["type"] for e in offre["evenements"]].count("statut:a_traiter") == 1


def test_non_propose_les_motifs_et_ecarte(telephone, parcours):
    from veille import db

    offre_id = parcours["non"]
    _ouvrir(telephone, parcours["url"])
    _carte(telephone, offre_id).locator('[data-action="non"]').click()
    fenetre = telephone.locator("#fenetre")
    motif = fenetre.get_by_role("button", name=MOTIF, exact=True)
    expect(motif).to_be_visible()

    # Sans motif, rien ne s'écarte.
    fenetre.get_by_role("button", name="Écarter", exact=True).click()
    expect(telephone.locator(".message.erreur")).to_be_visible()
    assert db.lire_offre(offre_id)["statut"] == "nouveau"

    motif.click()
    expect(fenetre.locator("textarea")).to_have_value(MOTIF)
    fenetre.get_by_role("button", name="Écarter", exact=True).click()
    expect(fenetre).to_be_hidden()
    expect(telephone.locator(f'#vue-a-faire [data-id="{offre_id}"]')).to_have_count(0)
    offre = db.lire_offre(offre_id)
    assert offre["statut"] == "ecartee"
    assert offre["motif_ecartement"] == MOTIF


def test_n_est_plus_en_ligne_archive(telephone, parcours):
    from veille import db

    offre_id = parcours["en_ligne"]
    _ouvrir(telephone, parcours["url"])
    _carte(telephone, offre_id).locator('[data-action="non"]').click()
    fenetre = telephone.locator("#fenetre")
    fenetre.get_by_role("button", name="N'est plus en ligne").click()
    expect(fenetre).to_be_hidden()
    expect(telephone.locator(f'#vue-a-faire [data-id="{offre_id}"]')).to_have_count(0)
    assert db.lire_offre(offre_id)["archivee_le"]


def _servir_a_faire(page, corps: dict) -> None:
    page.route("**/api/a-faire", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(corps)))


def test_a_faire_vide_le_dit(telephone, parcours):
    _servir_a_faire(telephone, VIDE)
    telephone.goto(f"{parcours['url']}/")
    expect(telephone.locator("#vue-a-faire")).to_contain_text(
        "Rien à faire pour l'instant : aucune offre au-dessus du seuil de 45.")


def test_les_offres_sous_le_seuil_menent_a_toutes_les_offres(telephone, parcours):
    _servir_a_faire(telephone, {**VIDE, "sous_le_seuil": 3})
    telephone.goto(f"{parcours['url']}/")
    telephone.get_by_role("button", name="Voir les 3 sous le seuil ›").click()
    expect(telephone.locator("#vue-offres")).to_be_visible()
    expect(telephone.locator("#f-statut")).to_have_value("nouveau")
    expect(_actif(telephone)).to_have_attribute("data-vue", "plus")


def test_a_faire_tient_dans_l_ecran(telephone, parcours):
    """Un intitulé très long ne fait pas défiler la file de côté."""
    _ouvrir(telephone, parcours["url"])
    expect(_carte(telephone, parcours["long"])).to_be_visible()
    largeur = telephone.evaluate("document.documentElement.scrollWidth")
    assert largeur <= TELEPHONE["viewport"]["width"]
