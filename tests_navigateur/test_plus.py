"""« Plus », Mes critères, le Bilan et les pastilles, au téléphone (ADR-0003, § 6 ; décisions 6
à 10 du plan du lot 3).

Même forme que `test_parcours_candidature.py` : Chromium à la taille d'un téléphone, une session
ouverte par `auth.ouvrir_session`, aucune erreur dans la console hors de `console_attendue`. Les
offres sont inventées par `_inventer`, sous le chemin `plus` (décision 18). La base est partagée
par toute la session de tests : un test ne compte que ses offres, ou des réponses simulées. Une
réponse simulée a la forme de la vraie : la route est appelée en Python, puis sa réponse est
restreinte aux offres du test, ou ses nombres remplacés.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from .test_cibles_tactiles import DOIGT, TELEPHONE
# `console_attendue` est une fixture : importée, elle sert à la fixture `telephone` d'ici.
from .test_parcours_candidature import LONG, _inventer, _ouvrir, console_attendue

# La dernière visite des archivées, dans le stockage local : la même clé qu'avant le lot.
CLE_VISITE = "veille:archive-vue-le"
ECRANS = ["Toutes les offres", "Mes critères", "Bilan", "Documents", "Réglages"]
TITRES_BILAN = ["Entonnoir", "Par canal de candidature", "Par famille de métier",
                "Rendement des sources", "Motifs d'écartement : ce que le score rate"]
RAPPEL = ("Les critères se changent dans la configuration de l'instance (criteres.yaml), qui "
          "arrive par le déploiement. « Recalculer tous les scores » les applique ensuite aux "
          "offres déjà collectées.")
MOTIF_CLOSE = "Motif inventé de l'écartement, au Bilan"
MOTIF_ANCIEN = "Motif inventé d'un ancien écartement, au Bilan"
MOTIF_DE_COTE = "Motif inventé de la mise de côté, au Bilan"
MOTIF_ARCHIVE = "Motif inventé de l'archivage, au Bilan"
# Les réponses de `api_rescorer` et de `api_valider_classement`, à leurs clés.
RESCORE = {"ok": True, "offres_recalculees": 12, "nouvellement_ecartees": 0,
           "remises_dans_le_flux": 0, "nouvellement_differees": 0}
SANS_PROPOSITION = {"offre_id": 990001, "titre": "Offre inventée sans proposition",
                    "employeur": "Employeur inventé", "score": 30}

# Les routes simulées : une adresse à requête se route par une expression régulière.
CLASSEMENT = re.compile(r"/api/classement$")
VALIDER = re.compile(r"/api/classement/valider$")
ARCHIVE = re.compile(r"/api/archive(\?.*)?$")
ENTONNOIR = re.compile(r"/api/entonnoir$")
RESCORER = re.compile(r"/api/rescorer$")


def _filtre(etat: str):
    return re.compile(rf"/api/offres\?etat={etat}$")


@pytest.fixture(scope="module")
def plus(serveur):
    """Les offres inventées du Bilan : des closes, des mises de côté et des archivées. Un test
    qui change une offre a la sienne (`remise`, `a_remettre`)."""
    from veille import db

    ecartee, refus, acceptee, longue = _inventer(
        ["Close inventée du Bilan, une", "Close inventée du Bilan, deux",
         "Close inventée du Bilan, trois", LONG],
        "plus/closes", "ecartee")
    db.changer_statut(ecartee, "ecartee", motif=MOTIF_CLOSE)
    db.changer_statut(longue, "ecartee", motif=MOTIF_CLOSE)
    # Écartée, puis refusée : le motif de l'écartement reste en base.
    db.changer_statut(refus, "ecartee", motif=MOTIF_ANCIEN)
    db.changer_statut(refus, "refus")
    db.changer_statut(acceptee, "accepte")
    de_cote, remise = _inventer(["Offre inventée mise de côté", "Offre inventée remise à plus tard"],
                                "plus/de-cote", "differee")
    for offre_id in (de_cote, remise):
        db.changer_statut(offre_id, "differee", motif=MOTIF_DE_COTE)
    archivees = _inventer(["Archivée inventée 1", "Archivée inventée 2", "Archivée inventée à remettre"],
                          "plus/archivees", "ecartee")
    for offre_id in archivees:
        db.changer_statut(offre_id, "ecartee", motif=MOTIF_CLOSE)
        db.archiver(offre_id, MOTIF_ARCHIVE)
    *gardees, a_remettre = archivees
    return {"ecartee": ecartee, "refus": refus, "acceptee": acceptee, "longue": longue,
            "de_cote": de_cote, "remise": remise, "archivees": gardees, "a_remettre": a_remettre}


@pytest.fixture
def telephone(navigateur, serveur, console_attendue):
    from veille import auth

    contexte = navigateur.new_context(**TELEPHONE)
    contexte.add_cookies([{"name": auth.nom_cookie(),
                           "value": auth.ouvrir_session("Téléphone"), "url": serveur}])
    page = contexte.new_page()
    erreurs: list[str] = []
    page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    try:
        yield page
    finally:
        contexte.close()
    assert [e for e in erreurs if not any(f in e for f in console_attendue)] == []


# ---------------------------------------------------------------------------
# Les réponses simulées, à la forme des vraies
# ---------------------------------------------------------------------------


def _servir(page, motif, corps, status: int = 200) -> None:
    """Simule une route : `corps` est la réponse, ou une fonction de la requête qui la rend."""
    def repondre(route):
        valeur = corps(route.request) if callable(corps) else corps
        route.fulfill(status=status, content_type="application/json", body=json.dumps(valeur))
    page.route(motif, repondre)


def _propositions(n: int) -> list[dict]:
    from veille.classement import Proposition

    return [Proposition(offre_id=990100 + k, titre=f"Proposition inventée {k}",
                        employeur=f"Employeur inventé {k}", score=50, famille="famille_inventee",
                        libelle="Famille inventée", confiance=0.8,
                        preuves=[f"preuve inventée {k}"]).as_dict()
            for k in range(1, n + 1)]


def _classement(propositions: list[dict], sans_proposition: tuple = ()) -> dict:
    from veille.app import api_classement

    return {**api_classement(), "sans_famille": len(propositions) + len(sans_proposition),
            "propositions": propositions, "sans_proposition": list(sans_proposition)}


def _archive(ids=(), nouvelles: int | None = None) -> dict:
    """`/api/archive` restreinte aux archivées `ids` ; `nouvelles` vaut leur nombre, ou celui donné."""
    from veille.app import api_offres_archivees

    d = api_offres_archivees(limite=100_000)
    offres = [o for o in d["offres"] if o["id"] in ids]
    return {**d, "offres": offres, "nouvelles": len(offres) if nouvelles is None else nouvelles}


def _offres(etat: str, ids=(), total: int | None = None) -> dict:
    """`/api/offres?etat=` restreinte aux offres `ids` ; `total` vaut leur nombre, ou celui donné."""
    from veille.app import api_offres

    d = api_offres(etat=etat, limite=100_000)
    offres = [o for o in d["offres"] if o["id"] in ids]
    return {**d, "offres": offres, "total": len(offres) if total is None else total}


def _entonnoir(motifs: int = 1) -> dict:
    """L'entonnoir, ses listes non vides : `tableau()` ne rend rien d'une liste vide."""
    from veille.app import api_entonnoir

    return {**api_entonnoir(),
            "par_canal": [{"canal": "canal inventé", "envoyees": 2, "reponses": 1, "taux_reponse": 50}],
            "par_famille": [{"famille": "famille inventée", "envoyees": 2, "reponses": 1,
                             "taux_reponse": 50}],
            "par_source": [{"source": "source inventée", "collectees": 5, "retenues": 3,
                            "candidatures": 2}],
            "motifs_ecartement": [{"motif": f"motif inventé {k}", "n": 2, "score_moyen": 40.0}
                                  for k in range(1, motifs + 1)]}


# ---------------------------------------------------------------------------
# Les gestes
# ---------------------------------------------------------------------------


def _onglet_plus(page):
    # Le nom d'un bouton comprend le texte de sa pastille : « Plus » devient « Plus 2 ».
    return page.locator('.onglet[data-vue="plus"]')


def _ouvrir_plus(page, url: str) -> None:
    _ouvrir(page, url)
    _onglet_plus(page).click()
    expect(page.locator("#vue-plus")).to_be_visible()


def _ouvrir_criteres(page, url: str) -> None:
    _ouvrir_plus(page, url)
    page.locator('.lien-plus[data-vue="criteres"]').click()
    expect(page.locator("#contenu-criteres .bloc").first).to_be_visible()


def _ouvrir_bilan(page, url: str) -> None:
    _ouvrir_plus(page, url)
    page.locator('.lien-plus[data-vue="bilan"]').click()
    expect(_liste(page, "mises-de-cote")).to_be_visible()


def _liste(page, nom: str):
    return page.locator(f'#contenu-bilan details[data-liste="{nom}"]')


def _resume(page, nom: str):
    return _liste(page, nom).locator(":scope > summary")


def _deplier(page, nom: str) -> None:
    _resume(page, nom).click()
    expect(_liste(page, nom)).to_have_attribute("open", "")


def _ligne(page, nom: str, offre_id: int):
    return _liste(page, nom).locator(f'.offre[data-id="{offre_id}"]')


def _fiche(page, offre_id: int):
    return page.locator(f'#fenetre .offre.fiche[data-id="{offre_id}"]')


def _ouvertes(page) -> list[bool]:
    return page.locator("#contenu-bilan details[data-liste]").evaluate_all("ds => ds.map(d => d.open)")


def _laisser_passer(page) -> None:
    """Laisse finir ce que les réponses reçues déclenchent : une absence ne s'attend pas."""
    page.evaluate("() => new Promise(r => setTimeout(r, 150))")


def _cibles_du_doigt(page, vue: str) -> None:
    mesures = page.locator(vue).locator("button, summary, a, label").evaluate_all(
        """es => es.filter(e => e.getClientRects().length)
                   .map(e => [e.textContent.trim().slice(0, 60), e.getBoundingClientRect().height])""")
    assert mesures
    for texte, hauteur in mesures:
        assert hauteur >= DOIGT, (texte, hauteur)


def _tient_dans_l_ecran(page) -> None:
    assert page.evaluate("document.documentElement.scrollWidth") <= TELEPHONE["viewport"]["width"]


# ---------------------------------------------------------------------------
# « Plus » et ses pastilles
# ---------------------------------------------------------------------------


def test_plus_liste_ses_ecrans(telephone, serveur):
    _ouvrir_plus(telephone, serveur)
    noms = telephone.locator("#vue-plus .lien-plus").evaluate_all(
        """es => es.map(e => {
            const copie = e.cloneNode(true);
            copie.querySelectorAll('.pastille').forEach(p => p.remove());
            return copie.textContent.trim();
        })""")
    assert noms == ECRANS


def test_la_pastille_de_plus_ne_compte_que_les_offres_a_classer(telephone, serveur):
    corps = {2: _classement(_propositions(2)), 0: _classement([])}
    nombre = {"propositions": 2}
    _servir(telephone, CLASSEMENT, lambda requete: corps[nombre["propositions"]])
    _servir(telephone, ARCHIVE, _archive(nouvelles=3))
    _ouvrir(telephone, serveur)
    expect(telephone.locator("#pastille-plus")).to_have_text("2")
    expect(telephone.locator("#pastille-plus")).to_be_visible()
    expect(telephone.locator("#pastille-criteres")).to_have_text("2")
    expect(telephone.locator("#pastille-bilan")).to_have_text("3")

    # L'onglet, sa pastille pleine ; l'ouverture de « Plus » recompte.
    nombre["propositions"] = 0
    _onglet_plus(telephone).click()
    expect(telephone.locator("#vue-plus")).to_be_visible()
    expect(telephone.locator("#pastille-plus")).to_be_empty()
    expect(telephone.locator("#pastille-plus")).to_be_hidden()
    expect(telephone.locator("#pastille-criteres")).to_be_empty()
    expect(telephone.locator("#pastille-bilan")).to_have_text("3")


def test_une_panne_des_pastilles_ne_dit_rien(telephone, serveur, console_attendue):
    console_attendue.append("500")
    panne = {"detail": "panne inventée"}
    _servir(telephone, CLASSEMENT, panne, status=500)
    _servir(telephone, ARCHIVE, panne, status=500)
    with telephone.expect_response(CLASSEMENT), telephone.expect_response(ARCHIVE):
        _ouvrir(telephone, serveur)
    _laisser_passer(telephone)
    for pastille in ("#pastille-plus", "#pastille-criteres", "#pastille-bilan"):
        expect(telephone.locator(pastille)).to_be_empty()
    expect(telephone.locator("#messages")).to_be_empty()


# ---------------------------------------------------------------------------
# Mes critères (décision 10)
# ---------------------------------------------------------------------------


def test_mes_criteres_rassemble_le_classement_le_recalcul_et_le_rappel(telephone, serveur):
    (proposition,) = _propositions(1)
    _servir(telephone, CLASSEMENT, _classement([proposition]))
    _servir(telephone, RESCORER, RESCORE)
    _ouvrir_criteres(telephone, serveur)

    blocs = telephone.locator("#contenu-criteres > .bloc")
    expect(blocs).to_have_count(3)
    ligne = blocs.nth(0).locator(".preuves li").filter(has_text=proposition["titre"])
    expect(ligne).to_contain_text(proposition["libelle"])
    expect(ligne).to_contain_text(proposition["preuves"][0])
    expect(ligne.locator("input.classer")).to_be_checked()
    recalculer = blocs.nth(1).get_by_role("button", name="Recalculer tous les scores")
    expect(recalculer).to_be_visible()
    expect(blocs.nth(2)).to_have_text(RAPPEL)

    with telephone.expect_request(lambda r: r.method == "POST" and RESCORER.search(r.url)):
        recalculer.click()
    expect(telephone.locator("#messages")).to_contain_text("12 offre(s) recalculée(s)")


def test_valider_un_classement_recalcule_les_pastilles(telephone, serveur):
    propositions = _propositions(2)
    corps = {"avant": _classement(propositions), "apres": _classement([])}
    moment = {"cle": "avant"}
    recues: list = []

    def valider(requete):
        recues.append(requete.post_data_json)
        moment["cle"] = "apres"
        return {"ok": True, "validees": len(propositions)}

    _servir(telephone, CLASSEMENT, lambda requete: corps[moment["cle"]])
    _servir(telephone, VALIDER, valider)
    _ouvrir_criteres(telephone, serveur)
    expect(telephone.locator("#pastille-plus")).to_have_text("2")
    expect(telephone.locator("#pastille-criteres")).to_have_text("2")

    telephone.get_by_role("button", name="Valider les cochées et rescorer").click()
    expect(telephone.locator("#pastille-plus")).to_be_empty()
    expect(telephone.locator("#pastille-criteres")).to_be_empty()
    expect(telephone.locator("#contenu-criteres")).to_contain_text("Aucune proposition")
    assert recues == [{"decisions": [{"offre_id": p["offre_id"], "famille": p["famille"]}
                                     for p in propositions]}]


# ---------------------------------------------------------------------------
# Le Bilan (décisions 7 et 8)
# ---------------------------------------------------------------------------


def test_le_bilan_montre_l_entonnoir_puis_trois_listes_repliees(telephone, serveur, plus):
    _servir(telephone, ENTONNOIR, _entonnoir())
    _servir(telephone, ARCHIVE, _archive(plus["archivees"][:1]))
    _servir(telephone, _filtre("close"), _offres("close", [plus["ecartee"], plus["acceptee"]]))
    _servir(telephone, _filtre("mise_de_cote"), _offres("mise_de_cote", [plus["de_cote"]]))
    _ouvrir_bilan(telephone, serveur)

    titres = telephone.locator("#contenu-bilan .bloc h2").all_text_contents()
    assert [t.strip() for t in titres] == TITRES_BILAN
    entonnoir = telephone.locator("#contenu-bilan .bloc").first
    for libelle in ("offres collectées", "réponses", "taux de réponse"):
        expect(entonnoir).to_contain_text(libelle)
    entetes = telephone.locator("#contenu-bilan th").all_text_contents()
    assert {"Envoyées", "Réponses", "Collectées"} <= set(entetes)

    # Puis les trois listes, sous l'entonnoir, repliées.
    assert telephone.evaluate("""() => {
        const blocs = document.querySelectorAll('#contenu-bilan .bloc');
        const liste = document.querySelector('#contenu-bilan details[data-liste]');
        return Boolean(blocs[blocs.length - 1].compareDocumentPosition(liste)
                       & Node.DOCUMENT_POSITION_FOLLOWING);
    }""")
    assert telephone.locator("#contenu-bilan details[data-liste]").evaluate_all(
        "ds => ds.map(d => d.dataset.liste)") == ["archivees", "closes", "mises-de-cote"]
    assert _ouvertes(telephone) == [False, False, False]
    resumes = telephone.locator("#contenu-bilan details[data-liste] > summary").all_text_contents()
    assert [" ".join(r.split()) for r in resumes] == ["Archivées (1)", "Closes (2)",
                                                      "Mises de côté (1)"]


def test_le_conseil_des_trente_motifs_renvoie_a_la_configuration(telephone, serveur):
    """Passé 30 motifs d'écartement, le conseil renvoie à la configuration de l'instance, qui
    arrive par le déploiement, et ne nomme plus `VEILLE_CONFIG` (décision 10)."""
    _servir(telephone, ENTONNOIR, _entonnoir(motifs=30))
    _ouvrir_bilan(telephone, serveur)
    conseil = telephone.locator("#contenu-bilan .bloc").filter(has_text="30 motifs")
    expect(conseil).to_contain_text("criteres.yaml")
    expect(conseil).to_contain_text("configuration de l'instance, qui arrive par le déploiement")
    expect(telephone.locator("#contenu-bilan")).not_to_contain_text("VEILLE_CONFIG")


def test_une_liste_plafonnee_le_dit(telephone, serveur, plus):
    _servir(telephone, ARCHIVE, _archive(plus["archivees"][:2], nouvelles=250))
    _servir(telephone, _filtre("close"),
            _offres("close", [plus["ecartee"], plus["acceptee"]], total=250))
    _servir(telephone, _filtre("mise_de_cote"), _offres("mise_de_cote"))
    _ouvrir_bilan(telephone, serveur)
    expect(_resume(telephone, "closes")).to_have_text("Closes (250, les 2 premières, par score)")
    expect(_resume(telephone, "archivees")).to_have_text(
        "Archivées (250, les 2 dernières archivées)")
    expect(_resume(telephone, "mises-de-cote")).to_have_text("Mises de côté (0)")


def test_une_close_montre_son_motif(telephone, serveur, plus):
    _ouvrir_bilan(telephone, serveur)
    _deplier(telephone, "closes")
    ecartee = _ligne(telephone, "closes", plus["ecartee"])
    expect(ecartee).to_contain_text(MOTIF_CLOSE)
    expect(ecartee).to_contain_text("Close")
    refus = _ligne(telephone, "closes", plus["refus"])
    expect(refus).to_contain_text("Refus")
    # Le motif d'un ancien écartement ne dit plus rien (comme sur la fiche).
    expect(refus).not_to_contain_text(MOTIF_ANCIEN)
    expect(_ligne(telephone, "closes", plus["acceptee"])).to_contain_text("Acceptée")

    _deplier(telephone, "mises-de-cote")
    de_cote = _ligne(telephone, "mises-de-cote", plus["de_cote"])
    expect(de_cote).to_contain_text(MOTIF_DE_COTE)
    expect(de_cote).to_contain_text("Mise de côté")


def test_une_ligne_du_bilan_ouvre_la_fiche(telephone, serveur, plus):
    _ouvrir_bilan(telephone, serveur)
    _deplier(telephone, "closes")
    _ligne(telephone, "closes", plus["ecartee"]).click()
    fiche = _fiche(telephone, plus["ecartee"])
    expect(fiche).to_be_visible()
    expect(fiche.locator(".etat-fiche")).to_have_text("Close")


def test_une_liste_depliee_reste_ouverte_quand_le_bilan_se_recharge(telephone, serveur, plus):
    """Un geste fait dans une fiche ouverte depuis le Bilan le recharge (`rafraichir`) : la liste
    dépliée le reste, les autres restent repliées (réponse 7)."""
    from veille import db

    offre_id = plus["remise"]
    _ouvrir_bilan(telephone, serveur)
    _deplier(telephone, "mises-de-cote")
    _ligne(telephone, "mises-de-cote", offre_id).click()
    fiche = _fiche(telephone, offre_id)
    expect(fiche.locator(".etat-fiche")).to_have_text("Mise de côté")
    fiche.locator('.ligne-actions [data-action="plus-tard"]').click()
    expect(fiche.locator(".etat-fiche")).to_have_text("Plus tard")

    expect(_ligne(telephone, "mises-de-cote", offre_id)).to_have_count(0)
    expect(_liste(telephone, "mises-de-cote")).to_have_attribute("open", "")
    assert _ouvertes(telephone) == [False, False, True]
    assert db.lire_offre(offre_id)["statut"] == "a_traiter"


def test_remettre_dans_le_flux_desarchive_pour_de_bon(telephone, serveur, plus):
    """Point d'attention 5 : elle quitte les archivées, ne repart jamais seule à l'archive, et,
    close, reste close (réponse 26)."""
    from veille import db

    offre_id = plus["a_remettre"]
    _ouvrir_bilan(telephone, serveur)
    _deplier(telephone, "archivees")
    archivee = _liste(telephone, "archivees").locator(f'article.offre.archivee[data-id="{offre_id}"]')
    expect(archivee).to_contain_text(MOTIF_ARCHIVE)
    with telephone.expect_response(lambda r: r.request.method == "POST"
                                   and r.url.endswith(f"/api/offres/{offre_id}/desarchiver")):
        archivee.get_by_role("button", name="Remettre dans le flux").click()

    expect(archivee).to_have_count(0)
    expect(_liste(telephone, "archivees")).to_have_attribute("open", "")
    expect(_ligne(telephone, "closes", offre_id)).to_have_count(1)
    offre = db.lire_offre(offre_id)
    assert offre["archivee_le"] is None
    assert offre["archive_protegee"] == 1
    assert offre["statut"] == "ecartee"


def test_un_bilan_ouvert_sans_deplier_les_archivees_garde_la_pastille(telephone, serveur, plus):
    _servir(telephone, ARCHIVE, _archive(plus["archivees"], nouvelles=2))
    _ouvrir(telephone, serveur)
    assert telephone.evaluate(f"() => localStorage.getItem('{CLE_VISITE}')") is None
    _onglet_plus(telephone).click()
    telephone.locator('.lien-plus[data-vue="bilan"]').click()
    expect(_liste(telephone, "archivees")).to_be_visible()
    _laisser_passer(telephone)

    assert telephone.evaluate(f"() => localStorage.getItem('{CLE_VISITE}')") is None
    assert _ouvertes(telephone)[0] is False
    expect(telephone.locator("#pastille-bilan")).to_have_text("2")


def test_deplier_les_archivees_eteint_la_pastille_du_bilan(telephone, serveur, plus):
    avant = _archive(plus["archivees"], nouvelles=2)
    apres = _archive(plus["archivees"], nouvelles=0)
    _servir(telephone, ARCHIVE, lambda requete: apres if "depuis=" in requete.url else avant)
    _ouvrir_bilan(telephone, serveur)
    expect(telephone.locator("#pastille-bilan")).to_have_text("2")

    _deplier(telephone, "archivees")
    telephone.wait_for_function(f"() => localStorage.getItem('{CLE_VISITE}') !== null")
    expect(telephone.locator("#pastille-bilan")).to_be_empty()

    # La visite marquée, la liste compte toujours toutes les archivées : le Bilan appelle
    # `/api/archive` sans `depuis` (décision 8).
    telephone.locator("#vue-bilan .retour-plus").click()
    with telephone.expect_request(lambda r: ARCHIVE.search(r.url)
                                  and "limite=" not in r.url) as requete:
        telephone.locator('.lien-plus[data-vue="bilan"]').click()
    assert "depuis=" not in requete.value.url


def test_la_derniere_visite_d_avant_le_lot_est_reprise(telephone, serveur):
    """La pastille d'un téléphone ne repart pas de zéro : la clé d'avant le lot est relue."""
    visite = "2026-10-01T08:00:00.000Z"
    telephone.add_init_script(
        f"try {{ localStorage.setItem('{CLE_VISITE}', '{visite}'); }} catch (e) {{}}")
    with telephone.expect_request(lambda r: "/api/archive?" in r.url
                                  and "limite=1" in r.url) as requete:
        _ouvrir(telephone, serveur)
    assert parse_qs(urlsplit(requete.value.url).query)["depuis"] == [visite]


def test_mes_criteres_et_le_bilan_se_touchent_du_doigt_et_tiennent_dans_l_ecran(
        telephone, serveur, plus):
    _servir(telephone, CLASSEMENT, _classement(_propositions(1), (SANS_PROPOSITION,)))
    _servir(telephone, _filtre("close"), _offres("close", [plus["longue"], plus["ecartee"]]))
    _ouvrir_criteres(telephone, serveur)
    expect(telephone.locator("#contenu-criteres input.classer")).to_have_count(1)
    _cibles_du_doigt(telephone, "#vue-criteres")
    _tient_dans_l_ecran(telephone)

    telephone.locator("#vue-criteres .retour-plus").click()
    telephone.locator('.lien-plus[data-vue="bilan"]').click()
    expect(_liste(telephone, "closes")).to_be_visible()
    for nom in ("archivees", "closes", "mises-de-cote"):
        _deplier(telephone, nom)
    expect(_ligne(telephone, "closes", plus["longue"])).to_contain_text(LONG)
    expect(_liste(telephone, "archivees").locator("article.offre.archivee").first).to_be_visible()
    _cibles_du_doigt(telephone, "#vue-bilan")
    _tient_dans_l_ecran(telephone)
