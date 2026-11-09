"""La file « À faire », le panneau « Non », la fiche par état et les onglets « Candidatures » et
« Plus », au téléphone (ADR-0003, §§ 2 à 4).

Même forme que `test_cibles_tactiles.py` : Chromium à la taille d'un téléphone, une session
ouverte par `auth.ouvrir_session`, aucune erreur dans la console. La base est partagée par
toute la session de tests : on ne regarde que les offres de la source `parcours`, et chaque
test qui change un statut a son offre à lui.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from playwright.sync_api import expect

from .test_cibles_tactiles import DOIGT, TELEPHONE

SOURCE = "parcours"
MOTIF = "motif inventé du parcours"
# Un intitulé de 200 caractères sans espace : il ne se coupe que si la page le permet.
LONG = ("Ingénieurqualitélogicielleinventé" * 7)[:200]
LONGUE = ("Candidatureinventéetrèslongue" * 8)[:200]
# Les deux offres du double « Non ».
PREMIERE = "Première offre inventée du panneau Non"
SECONDE = "Seconde offre inventée du panneau Non"
# Dans le désordre : la carte montre les deux contributions positives les plus fortes.
EXPLICATION = [
    {"libelle": "Raison inventée faible", "points": 5, "detail": ""},
    {"libelle": "Raison inventée contraire", "points": -10, "detail": ""},
    {"libelle": "Raison inventée forte", "points": 30, "detail": ""},
    {"libelle": "Raison inventée moyenne", "points": 15, "detail": ""},
]
VIDE = {"a_finir": [], "a_voir": [], "a_voir_restantes": 0, "plus_tard": [],
        "sous_le_seuil": 0, "seuil": 45}
# Les offres de la fiche et de « Candidatures », et le statut que reçoit chacune. Les tests
# de la file n'y touchent pas ; un test qui change un statut a la sienne.
FICHES = {
    "parcours": "nouveau",
    "a_voir": "nouveau",
    "plus_tard": "a_traiter",
    "de_cote": "differee",
    "a_preparer": "interessante",
    "pret": "interessante",
    "envoyee": "candidature_envoyee",
    "revenir": "relance_envoyee",
    "entretien": "entretien",
    "close": "ecartee",
    "generer": "interessante",
    # Elle garde la date de relance de son envoi : la fixture la pose, comme `changer_statut`
    # la laisse quand une réponse arrive.
    "reponse": "reponse_recue",
    # Écartée, puis refusée : le motif de l'écartement reste en base (la fixture la refuse).
    "refus": "ecartee",
    "recharge": "candidature_envoyee",
}


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


@pytest.fixture(scope="module")
def fiches(parcours, tmp_path_factory):
    """Une offre inventée par entrée de `FICHES`, créée après celles de la file. « pret » a
    un dossier : un dossier temporaire, comme le test du parcours le pose (décision 7)."""
    from veille import db, reglages
    from veille.collectors.base import ingerer
    from veille.models import Offre

    adresses = {cle: f"https://exemple.invalid/parcours/{n}" for n, cle in enumerate(FICHES, 11)}
    ingerer(
        [
            Offre(
                titre=f"Candidature inventée du parcours, {cle}",
                employeur=f"Employeur inventé {cle}",
                lieu="Lieu inventé",
                description="Tests automatisés, inventés pour la fiche.",
                url=adresse,
            )
            for cle, adresse in adresses.items()
        ],
        SOURCE,
    )
    ids = {}
    with db.connexion() as cx:
        for cle, adresse in adresses.items():
            ids[cle] = cx.execute("SELECT id FROM offres WHERE url = ?", (adresse,)).fetchone()["id"]
            cx.execute("UPDATE offres SET score = ?, explication = ? WHERE id = ?",
                       (reglages.lire_seuil() + 20,
                        json.dumps(EXPLICATION, ensure_ascii=False), ids[cle]))
    for cle, statut in FICHES.items():
        db.changer_statut(ids[cle], statut, motif=MOTIF if statut == "ecartee" else None)
    db.maj_champs(ids["pret"], dossier_chemin=str(tmp_path_factory.mktemp("dossier-pret")))
    db.maj_champs(ids["reponse"], date_relance_due=(date.today() + timedelta(days=10)).isoformat())
    db.changer_statut(ids["refus"], "refus")
    return ids


def _inventer(titres: list[str], chemin: str, statut: str) -> list[int]:
    """Des offres inventées de la source `parcours`, au-dessus du seuil, dans `statut`."""
    from veille import db, reglages
    from veille.collectors.base import ingerer
    from veille.models import Offre

    adresses = [f"https://exemple.invalid/parcours/{chemin}/{n}" for n in range(1, len(titres) + 1)]
    ingerer(
        [
            Offre(
                titre=titre,
                employeur=f"Employeur inventé {chemin} {n}",
                lieu="Lieu inventé",
                description="Tests automatisés, inventés pour le parcours.",
                url=adresse,
            )
            for n, (titre, adresse) in enumerate(zip(titres, adresses), 1)
        ],
        SOURCE,
    )
    ids = []
    with db.connexion() as cx:
        for adresse in adresses:
            offre_id = cx.execute("SELECT id FROM offres WHERE url = ?", (adresse,)).fetchone()["id"]
            cx.execute("UPDATE offres SET score = ?, explication = ? WHERE id = ?",
                       (reglages.lire_seuil() + 20,
                        json.dumps(EXPLICATION, ensure_ascii=False), offre_id))
            ids.append(offre_id)
    for offre_id in ids:
        db.changer_statut(offre_id, statut)
    return ids


@pytest.fixture(scope="module")
def deux_non(parcours):
    """Deux offres à voir, pour deux « Non » de suite."""
    return _inventer([PREMIERE, SECONDE], "non", "nouveau")


@pytest.fixture(scope="module")
def longue_candidature(parcours):
    """Une candidature envoyée à l'intitulé de 200 caractères sans espace."""
    (offre_id,) = _inventer([LONGUE], "longue", "candidature_envoyee")
    return offre_id


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


def test_non_nomme_l_offre_et_ecarte_la_bonne(telephone, parcours, deux_non):
    """« Non » sur une offre, puis sur une autre, et les motifs fréquents qui arrivent dans le
    désordre : le panneau nomme la seconde, et « Écarter » écarte la seconde. Chaque réponse
    porte un motif à elle, pour savoir laquelle a rempli le panneau."""
    from veille import db

    premiere, seconde = deux_non
    retenues: list = []
    telephone.route("**/api/motifs*", lambda route: retenues.append(route))
    _ouvrir(telephone, parcours["url"])
    _carte(telephone, premiere).locator('[data-action="non"]').click()
    # Le panneau de la première, s'il s'est ouvert, se referme.
    telephone.keyboard.press("Escape")
    _carte(telephone, seconde).locator('[data-action="non"]').click()
    for _ in range(100):
        if len(retenues) == 2:
            break
        telephone.wait_for_timeout(50)
    assert len(retenues) == 2

    def motifs(texte: str) -> dict:
        return {"status": 200, "content_type": "application/json",
                "body": json.dumps({"motifs": [texte]}, ensure_ascii=False)}

    fenetre = telephone.locator("#fenetre")
    retenues[1].fulfill(**motifs("motif inventé de la seconde"))
    expect(fenetre).to_contain_text(SECONDE)
    expect(fenetre.get_by_role("button", name="motif inventé de la seconde")).to_be_visible()
    with telephone.expect_response("**/api/motifs*"):
        retenues[0].fulfill(**motifs("motif inventé de la première"))

    fenetre.get_by_role("button", name="motif inventé de la seconde").click()
    expect(fenetre.locator("textarea")).to_have_value("motif inventé de la seconde")
    fenetre.get_by_role("button", name="Écarter", exact=True).click()
    expect(fenetre).to_be_hidden()
    assert db.lire_offre(seconde)["statut"] == "ecartee"
    assert db.lire_offre(seconde)["motif_ecartement"] == "motif inventé de la seconde"
    assert db.lire_offre(premiere)["statut"] == "nouveau"
    expect(fenetre.get_by_role("button", name="motif inventé de la première")).to_have_count(0)
    assert PREMIERE not in fenetre.inner_text()


def test_le_panneau_non_se_touche_du_doigt(telephone, parcours):
    """Les motifs fréquents, « Écarter », « N'est plus en ligne », « Annuler » et « Fermer »."""
    _ouvrir(telephone, parcours["url"])
    _carte(telephone, parcours["temoin"]).locator('[data-action="non"]').click()
    fenetre = telephone.locator("#fenetre")
    expect(fenetre).to_contain_text("Testeur inventé du parcours 4")
    expect(fenetre.get_by_role("button", name=MOTIF, exact=True)).to_be_visible()
    mesures = fenetre.locator("button").evaluate_all(
        "bs => bs.map(b => [b.textContent.trim(), b.getBoundingClientRect().height])")
    textes = [texte for texte, _ in mesures]
    for attendu in (MOTIF, "Écarter", "N'est plus en ligne", "Annuler", "Fermer"):
        assert attendu in textes
    for texte, hauteur in mesures:
        assert hauteur >= DOIGT, (texte, hauteur)
    fenetre.get_by_role("button", name="Annuler").click()
    expect(fenetre).to_be_hidden()


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


def test_les_cibles_de_a_faire_se_touchent_du_doigt(telephone, parcours):
    """Une ligne d'« À finir », « Voir les N autres… », « Voir les M sous le seuil » et le
    volet « Plus tard » (ADR-0003, § 7). Plus de 50 offres au-dessus du seuil ne se créent
    pas ici : la file est servie."""
    plus_tard = {"id": parcours["temoin"], "titre": "Offre inventée remise à plus tard",
                 "employeur": "Employeur inventé", "lieu": "Lieu inventé", "score": 65,
                 "statut": "a_traiter", "explication": EXPLICATION}
    a_finir = {"id": parcours["temoin"], "titre": "Offre inventée à finir",
               "employeur": "Employeur inventé", "raison": "a_preparer"}
    _servir_a_faire(telephone, {**VIDE, "a_finir": [a_finir], "plus_tard": [plus_tard],
                                "a_voir_restantes": 3, "sous_le_seuil": 2})
    telephone.goto(f"{parcours['url']}/")
    expect(telephone.locator("#vue-a-faire .ligne-a-finir")).to_be_visible()
    mesures = telephone.locator(
        "#vue-a-faire .ligne-a-finir, #vue-a-faire .vers-toutes button, "
        "#vue-a-faire details.plus-tard > summary").evaluate_all(
        "es => es.map(e => [e.textContent.trim(), e.getBoundingClientRect().height])")
    textes = [" ".join(texte.split()) for texte, _ in mesures]
    assert textes == ["Dossier à préparer Offre inventée à finir Employeur inventé",
                      "Voir les 3 autres au-dessus du seuil ›", "Voir les 2 sous le seuil ›",
                      "Plus tard (1)"]
    for texte, hauteur in mesures:
        assert hauteur >= DOIGT, (texte, hauteur)


# ---------------------------------------------------------------------------
# La fiche par état et l'onglet « Candidatures » (ADR-0003, § 4)
# ---------------------------------------------------------------------------


def _fiche(page, offre_id: int):
    return page.locator(f'#fenetre .offre.fiche[data-id="{offre_id}"]')


def _fermer(page) -> None:
    page.locator("#fenetre").get_by_role("button", name="Fermer").click()
    expect(page.locator("#fenetre")).to_be_hidden()


def _ouvrir_candidatures(page, url: str) -> None:
    _ouvrir(page, url)
    page.locator('.onglet[data-vue="candidatures"]').click()
    expect(page.locator("#contenu-candidatures")).not_to_be_empty()


def _ligne_candidature(page, groupe: str, offre_id: int):
    return page.locator(f'#vue-candidatures [data-groupe="{groupe}"] '
                        f'button.offre[data-action="fiche"][data-id="{offre_id}"]')


def _actions(fiche) -> list[str]:
    return fiche.locator(".ligne-actions [data-action]").evaluate_all(
        "es => es.map(e => e.dataset.action)")


def _statut_ecrit(page):
    return page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/statut"))


def test_le_parcours_de_la_file_a_l_entretien(telephone, parcours, fiches, tmp_path):
    """De la carte « À voir » à l'entretien, chaque geste sur la fiche de l'état atteint."""
    from veille import db

    offre_id = fiches["parcours"]
    _ouvrir(telephone, parcours["url"])
    _carte(telephone, offre_id).locator('[data-action="postuler"]').click()
    fiche = _fiche(telephone, offre_id)
    expect(fiche.locator(".etat-fiche")).to_have_text("Je postule")
    expect(fiche.locator('[data-action="dossier"]')).to_have_count(1)
    assert db.lire_offre(offre_id)["statut"] == "interessante"

    # La génération est testée en Python ; ici, le dossier est simulé (décision 7 du plan).
    db.maj_champs(offre_id, dossier_chemin=str(tmp_path))
    _fermer(telephone)
    telephone.locator('.onglet[data-vue="a-faire"]').click()
    ligne = telephone.locator(f'#vue-a-faire .ligne-a-finir[data-id="{offre_id}"]')
    expect(ligne).to_contain_text("Dossier prêt à envoyer")
    ligne.click()
    expect(fiche.locator('[data-action="envoyee"]')).to_have_count(1)

    fiche.locator('[data-action="envoyee"]').click()
    with _statut_ecrit(telephone):
        telephone.locator("#fenetre").get_by_role("button", name="LinkedIn", exact=True).click()
    assert db.lire_offre(offre_id)["statut"] == "candidature_envoyee"

    telephone.locator('.onglet[data-vue="candidatures"]').click()
    _ligne_candidature(telephone, "envoyee", offre_id).click()
    with _statut_ecrit(telephone):
        fiche.locator('[data-action="reponse"][data-statut="entretien"]').click()
    expect(fiche.locator('[data-action="entretien"]')).to_have_count(1)
    expect(fiche.locator(".etat-fiche")).to_have_text("Entretien")
    assert db.lire_offre(offre_id)["statut"] == "entretien"


def test_la_fiche_ne_montre_que_les_actions_de_son_etat(telephone, parcours, fiches):
    offre_id = fiches["envoyee"]
    _ouvrir_candidatures(telephone, parcours["url"])
    _ligne_candidature(telephone, "envoyee", offre_id).click()
    fiche = _fiche(telephone, offre_id)
    expect(fiche.locator('[data-action="relance"]')).to_have_count(1)
    expect(fiche.locator('[data-action="reponse"]')).to_have_count(3)
    expect(fiche.locator('[data-action="postuler"]')).to_have_count(0)
    expect(fiche.locator('[data-action="dossier"]')).to_have_count(0)
    statuts = fiche.locator('[data-action="reponse"]').evaluate_all(
        "bs => bs.map(b => b.dataset.statut)")
    assert statuts == ["entretien", "refus", "accepte"]


def test_chaque_etat_a_sa_ligne_d_actions(telephone, parcours, fiches):
    """Le tableau de la fiche (ADR-0003, § 4), statut par statut ; « Revenir à « À voir » »
    est dans « Autres actions », hors de l'état « À voir »."""
    from veille import db

    attendu = {
        "a_voir": ("À voir", ["postuler", "plus-tard", "non"], False),
        "de_cote": ("Mise de côté", ["postuler", "plus-tard", "non"], True),
        "plus_tard": ("Plus tard", ["postuler", "non"], False),
        "a_preparer": ("Je postule", ["dossier"], True),
        "pret": ("Je postule", ["envoyee", "dossier"], True),
        "envoyee": ("Envoyée", ["relance", "reponse", "reponse", "reponse"], True),
        "entretien": ("Entretien", ["entretien", "reponse", "reponse"], True),
        "close": ("Close", [], True),
    }
    _ouvrir(telephone, parcours["url"])
    for cle, (libelle, actions, revenir) in attendu.items():
        offre_id = fiches[cle]
        telephone.evaluate("id => ouvrirFiche(id)", offre_id)
        fiche = _fiche(telephone, offre_id)
        expect(fiche.locator(".etat-fiche")).to_have_text(libelle)
        assert _actions(fiche) == actions, cle
        expect(fiche.locator('[data-action="revenir"]')).to_have_count(1 if revenir else 0)

    telephone.evaluate("id => ouvrirFiche(id)", fiches["pret"])
    expect(_fiche(telephone, fiches["pret"]).locator(".ligne-actions a[download]")).to_have_attribute(
        "href", f"/api/offres/{fiches['pret']}/dossier/archive")
    telephone.evaluate("id => ouvrirFiche(id)", fiches["envoyee"])
    relance = db.lire_offre(fiches["envoyee"])["date_relance_due"]
    expect(_fiche(telephone, fiches["envoyee"]).locator(".ligne-actions")).to_contain_text(relance)
    telephone.evaluate("id => ouvrirFiche(id)", fiches["close"])
    expect(_fiche(telephone, fiches["close"]).locator(".ligne-actions")).to_contain_text(MOTIF)


def test_les_boutons_de_la_fiche_se_touchent_du_doigt(telephone, parcours, fiches):
    _ouvrir(telephone, parcours["url"])
    for cle in ("a_voir", "pret", "envoyee", "entretien"):
        telephone.evaluate("id => ouvrirFiche(id)", fiches[cle])
        fiche = _fiche(telephone, fiches[cle])
        expect(fiche).to_be_visible()
        cibles = fiche.locator(".ligne-actions button, .ligne-actions a, .lien-annonce, summary")
        mesures = cibles.evaluate_all(
            "es => es.map(e => [e.textContent.trim(), e.getBoundingClientRect().height])")
        assert len(mesures) >= 5, cle
        for texte, hauteur in mesures:
            assert hauteur >= DOIGT, (cle, texte, hauteur)


def test_candidatures_groupent_les_offres_par_etat(telephone, parcours, fiches):
    from veille import db

    _ouvrir_candidatures(telephone, parcours["url"])
    titres = telephone.locator("#vue-candidatures .titre-groupe").all_text_contents()
    assert titres == ["Je postule", "Envoyée", "Entretien"]
    expect(_ligne_candidature(telephone, "je_postule", fiches["pret"])).to_contain_text(
        "dossier prêt")
    expect(_ligne_candidature(telephone, "je_postule", fiches["a_preparer"])).to_contain_text(
        "à préparer")
    relance = db.lire_offre(fiches["envoyee"])["date_relance_due"]
    expect(_ligne_candidature(telephone, "envoyee", fiches["envoyee"])).to_contain_text(
        f"relance le {relance}")
    expect(_ligne_candidature(telephone, "entretien", fiches["entretien"])).to_be_visible()
    for cle in ("a_voir", "plus_tard", "de_cote", "close"):
        expect(telephone.locator(f'#vue-candidatures [data-id="{fiches[cle]}"]')).to_have_count(0)


def test_candidatures_vides_le_dit(telephone, parcours):
    telephone.route("**/api/candidatures", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"je_postule": [], "envoyee": [], "entretien": []})))
    _ouvrir(telephone, parcours["url"])
    telephone.locator('.onglet[data-vue="candidatures"]').click()
    expect(telephone.locator("#vue-candidatures")).to_contain_text("Aucune candidature en cours.")
    expect(_actif(telephone)).to_have_attribute("data-vue", "candidatures")


def test_revenir_puis_plus_tard_rouvrent_la_fiche(telephone, parcours, fiches):
    from veille import db

    offre_id = fiches["revenir"]
    _ouvrir_candidatures(telephone, parcours["url"])
    _ligne_candidature(telephone, "envoyee", offre_id).click()
    fiche = _fiche(telephone, offre_id)
    fiche.locator("summary", has_text="Autres actions").click()
    with _statut_ecrit(telephone):
        fiche.get_by_role("button", name="Revenir à « À voir »").click()
    expect(fiche.locator(".etat-fiche")).to_have_text("À voir")
    assert _actions(fiche) == ["postuler", "plus-tard", "non"]
    assert db.lire_offre(offre_id)["statut"] == "nouveau"

    with _statut_ecrit(telephone):
        fiche.locator('.ligne-actions [data-action="plus-tard"]').click()
    expect(fiche.locator('.ligne-actions [data-action="plus-tard"]')).to_have_count(0)
    expect(fiche.locator(".etat-fiche")).to_have_text("Plus tard")
    assert _actions(fiche) == ["postuler", "non"]
    assert db.lire_offre(offre_id)["statut"] == "a_traiter"


def test_les_notes_s_enregistrent_depuis_la_fiche(telephone, parcours, fiches):
    from veille import db

    offre_id = fiches["pret"]
    note = "Note inventée du parcours"
    _ouvrir_candidatures(telephone, parcours["url"])
    _ligne_candidature(telephone, "je_postule", offre_id).click()
    fiche = _fiche(telephone, offre_id)
    fiche.locator("summary", has_text="Notes").click()
    fiche.locator("textarea").fill(note)
    with telephone.expect_response(lambda r: r.request.method == "POST"
                                   and r.url.endswith(f"/api/offres/{offre_id}")):
        fiche.get_by_role("button", name="Enregistrer").click()
    expect(telephone.locator(".message", has_text="Notes enregistrées.")).to_be_visible()
    # Rouverte, la fiche garde ouvert le volet des notes, et les montre.
    expect(fiche.locator('details[data-repli="notes"]')).to_have_attribute("open", "")
    expect(fiche.locator("textarea")).to_have_value(note)
    assert db.lire_offre(offre_id)["notes"] == note


def test_la_fiche_tient_dans_l_ecran(telephone, parcours):
    """L'intitulé de 200 caractères ne fait défiler de côté ni la page ni la fenêtre."""
    _ouvrir(telephone, parcours["url"])
    _carte(telephone, parcours["long"]).locator('[data-action="fiche"]').click()
    fiche = _fiche(telephone, parcours["long"])
    expect(fiche.locator(".offre-titre")).to_have_text(LONG)
    largeur = telephone.evaluate("document.documentElement.scrollWidth")
    assert largeur <= TELEPHONE["viewport"]["width"]
    # La fenêtre défile pour son compte : la page ne verrait pas son débordement.
    assert telephone.eval_on_selector("#fenetre", "f => f.scrollWidth <= f.clientWidth")


def test_generer_le_dossier_recharge_a_finir(telephone, parcours, fiches, tmp_path):
    """Derrière la fenêtre du dossier, « À finir » ne dit plus « Dossier à préparer ». La
    génération est simulée (décision 7 du plan) : la route pose le dossier en base, puis
    répond comme `api_generer_dossier`."""
    from veille import db

    offre_id = fiches["generer"]

    def generer(route):
        db.maj_champs(offre_id, dossier_chemin=str(tmp_path))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "ok": True, "dossier": tmp_path.name, "fichiers": [], "gabarit_lettre": None,
            "kit_provisoire": False, "avertissements": [], "completude": None,
            "pieces_envoi": [], "archive": f"/api/offres/{offre_id}/dossier/archive",
            "archive_complete": f"/api/offres/{offre_id}/dossier/archive?complet=true"}))

    telephone.route(f"**/api/offres/{offre_id}/dossier", generer)
    _ouvrir(telephone, parcours["url"])
    ligne = telephone.locator(f'#vue-a-faire .ligne-a-finir[data-id="{offre_id}"]')
    expect(ligne).to_contain_text("Dossier à préparer")
    ligne.click()
    _fiche(telephone, offre_id).locator('[data-action="dossier"]').click()
    expect(telephone.locator("#fenetre h2")).to_have_text("Dossier genere")
    expect(ligne).to_contain_text("Dossier prêt à envoyer")


def test_une_reponse_recue_ne_montre_pas_de_relance(telephone, parcours, fiches):
    """Sa relance n'est jamais due (`db.relances_dues`) : ni « Candidatures » ni sa fiche ne
    la datent, même si la date de l'envoi reste en base."""
    from veille import db

    offre_id = fiches["reponse"]
    relance = db.lire_offre(offre_id)["date_relance_due"]
    assert relance
    _ouvrir_candidatures(telephone, parcours["url"])
    ligne = _ligne_candidature(telephone, "envoyee", offre_id)
    expect(ligne).to_be_visible()
    expect(ligne).not_to_contain_text(relance)
    ligne.click()
    fiche = _fiche(telephone, offre_id)
    expect(fiche.locator(".etat-fiche")).to_have_text("Envoyée")
    expect(fiche.locator(".ligne-actions")).not_to_contain_text(relance)


def test_une_close_ne_montre_que_le_motif_d_un_ecartement(telephone, parcours, fiches):
    """Écartée puis refusée, l'offre garde son ancien motif en base : sa fiche ne le montre
    pas (une écartée le montre, `test_chaque_etat_a_sa_ligne_d_actions`)."""
    from veille import db

    offre_id = fiches["refus"]
    assert db.lire_offre(offre_id)["motif_ecartement"] == MOTIF
    _ouvrir(telephone, parcours["url"])
    telephone.evaluate("id => ouvrirFiche(id)", offre_id)
    fiche = _fiche(telephone, offre_id)
    expect(fiche.locator(".etat-fiche")).to_have_text("Close")
    expect(fiche).not_to_contain_text(MOTIF)


def test_une_fiche_qui_ne_se_recharge_pas_se_ferme(telephone, parcours, fiches):
    """Le statut est écrit, puis la fiche ne se recharge pas (une réponse illisible, comme
    la page d'erreur d'un intermédiaire) : elle se ferme, un message le dit, et rien ne
    reste à toucher sur une fiche périmée, où un second toucher réécrirait le statut."""
    from veille import db

    offre_id = fiches["recharge"]
    envois: list[str] = []
    telephone.on("request", lambda r: envois.append(r.url)
                 if r.method == "POST" and r.url.endswith("/statut") else None)
    _ouvrir(telephone, parcours["url"])
    telephone.evaluate("id => ouvrirFiche(id)", offre_id)
    fiche = _fiche(telephone, offre_id)
    expect(fiche).to_be_visible()
    telephone.route(f"**/api/offres/{offre_id}", lambda route: route.fulfill(
        status=200, content_type="text/html", body="<p>panne inventée</p>")
        if route.request.method == "GET" else route.continue_())
    with _statut_ecrit(telephone):
        fiche.locator('[data-action="reponse"][data-statut="refus"]').click()
    expect(telephone.locator("#fenetre")).to_be_hidden()
    expect(telephone.locator(".message.erreur")).to_contain_text("fiche")
    assert len(envois) == 1
    assert db.lire_offre(offre_id)["statut"] == "refus"


def test_candidatures_se_touchent_du_doigt_et_tiennent_dans_l_ecran(
        telephone, parcours, fiches, longue_candidature):
    """Chaque ligne de « Candidatures » fait 44 px, et un intitulé de 200 caractères sans
    espace ne fait pas défiler l'écran de côté (ADR-0003, § 7)."""
    _ouvrir_candidatures(telephone, parcours["url"])
    expect(_ligne_candidature(telephone, "envoyee", longue_candidature)).to_contain_text(LONGUE)
    hauteurs = telephone.locator("#vue-candidatures .ligne-candidature").evaluate_all(
        "es => es.map(e => e.getBoundingClientRect().height)")
    assert len(hauteurs) >= 5
    assert min(hauteurs) >= DOIGT
    assert telephone.evaluate("document.documentElement.scrollWidth") <= TELEPHONE["viewport"]["width"]


def test_plus_se_touche_du_doigt_et_tient_dans_l_ecran(telephone, parcours):
    """Les lignes de « Plus », et « ‹ Plus » sur un ancien écran (ADR-0003, § 7)."""
    _ouvrir(telephone, parcours["url"])
    telephone.get_by_role("button", name="Plus", exact=True).click()
    expect(telephone.locator("#vue-plus")).to_be_visible()
    hauteurs = telephone.locator("#vue-plus .lien-plus").evaluate_all(
        "es => es.map(e => e.getBoundingClientRect().height)")
    assert len(hauteurs) == 7
    assert min(hauteurs) >= DOIGT
    assert telephone.evaluate("document.documentElement.scrollWidth") <= TELEPHONE["viewport"]["width"]

    telephone.get_by_role("button", name="Toutes les offres").click()
    retour = telephone.locator("#vue-offres .retour-plus")
    expect(retour).to_be_visible()
    assert retour.evaluate("e => e.getBoundingClientRect().height") >= DOIGT
