"""« Plus », Toutes les offres et ses trois filtres, Mes critères, le Bilan, les pastilles, puis
Réglages, l'en-tête et le push côté client, au téléphone (ADR-0003, § 6 ; décisions 2 à 12 et 20
du plan du lot 3).

Même forme que `test_parcours_candidature.py` : Chromium à la taille d'un téléphone, une session
ouverte par `auth.ouvrir_session`, aucune erreur dans la console hors de `console_attendue`. Les
offres sont inventées par `_inventer`, sous le chemin `plus` (décision 18). La base est partagée
par toute la session de tests : un test ne compte que ses offres, ou des réponses simulées. Une
réponse simulée a la forme de la vraie : la route est appelée en Python, puis sa réponse est
restreinte aux offres du test, ou ses nombres remplacés.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from playwright.sync_api import expect

from .test_cibles_tactiles import DOIGT, TELEPHONE
# `console_attendue` est une fixture : importée, elle sert à la fixture `telephone` d'ici.
from .test_parcours_candidature import LONG, VIDE, _inventer, _ouvrir, console_attendue

# La dernière visite des archivées, dans le stockage local : la même clé qu'avant le lot.
CLE_VISITE = "veille:archive-vue-le"
ECRANS = ["Chercher une offre", "Toutes les offres", "Mes critères", "Bilan", "Documents",
          "Réglages"]
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
# Toutes les offres : l'employeur commun aux trois offres du rappel (point d'attention 6), la
# portée d'une recherche sans état (décision 4), et ce qui a quitté l'écran avec l'ancien panneau.
EMPLOYEUR_RAPPEL = "Employeur inventé qui rappelle"
PORTEE = "La recherche porte sur toutes les offres, closes et mises de côté comprises."
RETIRES = ["#btn-filtres", "#compte-filtres", "#btn-documenter", "#compte-documenter",
           "#puces-filtres", "#panneau-filtres", "#f-statut", "#f-zone", "#f-atout",
           "#f-verification", "#f-tri", "#f-ecartees", "#btn-rescorer"]
PARAMETRES_RETIRES = {"statut", "zone", "inclure_ecartees", "a_documenter", "verification", "tri"}

# Les routes simulées : une adresse à requête se route par une expression régulière.
CLASSEMENT = re.compile(r"/api/classement$")
VALIDER = re.compile(r"/api/classement/valider$")
ARCHIVE = re.compile(r"/api/archive(\?.*)?$")
ENTONNOIR = re.compile(r"/api/entonnoir$")
RESCORER = re.compile(r"/api/rescorer$")
A_FAIRE = re.compile(r"/api/a-faire$")
# Toutes les offres demande toujours `/api/offres?…`, sans paramètre compris ; une fiche, jamais.
TOUTES = re.compile(r"/api/offres\?")


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


@pytest.fixture(scope="module")
def toutes(serveur):
    """Les offres inventées de Toutes les offres : une ligne à voir, les deux réponses hors
    d'ordre, un intitulé long, une candidature sans dossier (que son test envoie), et trois
    offres d'un même employeur, une refusée, une mise de côté et une en cours."""
    from veille import db

    ligne, perimee, a_jour, longue = _inventer(
        ["Offre inventée de Toutes les offres", "Offre inventée A, la réponse périmée",
         "Offre inventée B, la réponse à jour", LONG], "plus/toutes", "nouveau")
    (sans_dossier,) = _inventer(["Candidature inventée sans dossier"], "plus/sans-dossier",
                                "interessante")
    refusee, de_cote, en_cours = _inventer(
        ["Offre inventée du rappel, refusée", "Offre inventée du rappel, mise de côté",
         "Offre inventée du rappel, en cours"], "plus/rappel", "nouveau")
    db.changer_statut(refusee, "refus")
    db.changer_statut(de_cote, "differee", motif=MOTIF_DE_COTE)
    with db.connexion() as cx:
        cx.execute("UPDATE offres SET employeur = ? WHERE id IN (?, ?, ?)",
                   (EMPLOYEUR_RAPPEL, refusee, de_cote, en_cours))
    return {"ligne": ligne, "perimee": perimee, "a_jour": a_jour, "longue": longue,
            "sans_dossier": sans_dossier, "refusee": refusee, "de_cote": de_cote,
            "en_cours": en_cours}


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


def _laisser_passer(page, ms: int = 150) -> None:
    """Laisse finir ce que les réponses reçues déclenchent : une absence ne s'attend pas."""
    page.evaluate("ms => new Promise(r => setTimeout(r, ms))", ms)


def _parametres(url: str) -> dict[str, list[str]] | None:
    """Les paramètres d'une demande de Toutes les offres, ou None pour une autre adresse."""
    morceaux = urlsplit(url)
    return parse_qs(morceaux.query) if morceaux.path == "/api/offres" else None


def _demande_offres(condition=lambda parametres: True):
    """Reconnaît une demande (ou sa réponse) de Toutes les offres dont les paramètres
    remplissent `condition`."""
    def voir(r) -> bool:
        parametres = _parametres(r.url)
        return parametres is not None and condition(parametres)
    return voir


def _ouvrir_toutes(page, url: str) -> None:
    _ouvrir_plus(page, url)
    with page.expect_response(_demande_offres()):
        page.locator('.lien-plus[data-vue="offres"]:not([data-chercher])').click()
    expect(page.locator("#vue-offres")).to_be_visible()
    expect(page.locator("#resume-offres")).not_to_be_empty()


def _chercher(page, texte: str):
    """Tape une recherche d'un coup, et rend la réponse qui la suit, le délai passé."""
    with page.expect_response(_demande_offres(lambda p: p.get("recherche") == [texte])) as reponse:
        page.locator("#f-recherche").fill(texte)
    return reponse.value


def _lignes_toutes(page):
    return page.locator("#liste-offres .ligne-offre")


def _ligne_toutes(page, offre_id: int):
    return page.locator(f'#liste-offres .ligne-offre[data-id="{offre_id}"]')


def _ids_toutes(page) -> list[int]:
    return _lignes_toutes(page).evaluate_all("es => es.map(e => Number(e.dataset.id))")


def _cibles_du_doigt(page, vue: str) -> None:
    mesures = page.locator(vue).locator("button, summary, a, label").evaluate_all(
        """es => es.filter(e => e.getClientRects().length)
                   .map(e => [e.textContent.trim().slice(0, 60), e.getBoundingClientRect().height])""")
    assert mesures
    for texte, hauteur in mesures:
        assert hauteur >= DOIGT, (texte, hauteur)


def _tient_dans_l_ecran(page) -> None:
    largeur = page.evaluate("document.documentElement.scrollWidth")
    assert largeur <= TELEPHONE["viewport"]["width"], largeur


# Une police large, posée dès le chargement : Verdana sous Windows, DejaVu Sans (ou la police sans
# empattement par défaut) sous le runner Linux de la CI, dont les polices sont plus larges que
# celles de Windows.
POLICE_LARGE = """document.addEventListener('DOMContentLoaded', () => {
    const style = document.createElement('style');
    style.textContent = '*{font-family:Verdana,"DejaVu Sans",sans-serif !important}';
    document.head.append(style);
});"""


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
# Toutes les offres et ses trois filtres (décisions 2 à 6)
# ---------------------------------------------------------------------------


def test_chercher_une_offre_ouvre_la_recherche(telephone, serveur):
    """« Chercher une offre » ouvre Toutes les offres, le curseur dans la recherche (décision 5)."""
    _ouvrir_plus(telephone, serveur)
    telephone.get_by_role("button", name="Chercher une offre").click()
    expect(telephone.locator("#vue-offres")).to_be_visible()
    expect(telephone.locator("#f-recherche")).to_be_focused()
    assert telephone.evaluate("document.activeElement.id") == "f-recherche"


def test_toutes_les_offres_n_a_que_trois_filtres_et_la_bascule(telephone, serveur):
    _ouvrir_toutes(telephone, serveur)
    champs = telephone.locator("#vue-offres").locator("input, select, textarea").evaluate_all(
        "es => es.map(e => e.id)")
    assert champs == ["f-recherche", "f-etat", "f-famille"]
    recherche = telephone.locator("#f-recherche")
    expect(recherche).to_have_attribute("type", "search")
    expect(recherche).to_have_attribute("aria-label", "Chercher une offre")
    # L'exemple a un atout mis en avant : la bascule se voit.
    expect(telephone.locator("#btn-atout")).to_be_visible()
    for selecteur in RETIRES:
        expect(telephone.locator(selecteur)).to_have_count(0)


def test_les_options_d_etat_sont_les_cinq_et_les_mises_de_cote(telephone, serveur):
    from veille import etats

    _ouvrir_toutes(telephone, serveur)
    options = telephone.locator("#f-etat option")
    assert options.evaluate_all("os => os.map(o => o.value)") == ["", *etats.ETATS_FILTRABLES]
    assert [t.strip() for t in options.all_text_contents()] == [
        "En cours", "À voir", "Je postule", "Envoyée", "Entretien", "Close", "Mises de côté"]


def test_le_filtre_d_etat_part_au_serveur(telephone, serveur, plus):
    _ouvrir_toutes(telephone, serveur)
    with telephone.expect_response(_demande_offres(lambda p: p.get("etat") == ["close"])) as rep:
        telephone.locator("#f-etat").select_option("close")
    assert not PARAMETRES_RETIRES & set(_parametres(rep.value.url))
    # Une close du Bilan dans la liste : la liste est celle de la réponse.
    expect(_ligne_toutes(telephone, plus["ecartee"])).to_be_visible()
    etats_lus = _lignes_toutes(telephone).locator(".etat-ligne").all_text_contents()
    assert etats_lus
    assert {e.strip() for e in etats_lus} == {"Close"}


def test_une_ligne_porte_titre_employeur_score_et_etat_et_ouvre_la_fiche(telephone, serveur,
                                                                         toutes):
    from veille import db

    offre_id = toutes["ligne"]
    offre = db.lire_offre(offre_id)
    _ouvrir_toutes(telephone, serveur)
    _chercher(telephone, offre["titre"])
    ligne = _ligne_toutes(telephone, offre_id)
    expect(ligne.locator(".offre-titre")).to_have_text(offre["titre"])
    expect(ligne).to_contain_text(offre["employeur"])
    expect(ligne.locator(".score")).to_have_text(f"{offre['score']:g}")
    expect(ligne.locator(".etat-ligne")).to_have_text("À voir")

    ligne.click()
    fiche = _fiche(telephone, offre_id)
    expect(fiche).to_be_visible()
    expect(fiche.locator(".etat-fiche")).to_have_text("À voir")


def test_la_recherche_n_envoie_qu_une_requete_par_pause(telephone, serveur):
    """Le délai de la recherche (280 ms de calme) : une frappe rapide n'envoie qu'une demande."""
    _ouvrir_toutes(telephone, serveur)
    recherches: list = []

    def noter(requete) -> None:
        parametres = _parametres(requete.url)
        if parametres is not None:
            recherches.append(parametres.get("recherche"))

    telephone.on("request", noter)
    with telephone.expect_request(_demande_offres(lambda p: p.get("recherche") == ["abc"])):
        telephone.locator("#f-recherche").press_sequentially("abc", delay=40)
    _laisser_passer(telephone, 600)
    assert ["a"] not in recherches
    assert ["ab"] not in recherches
    assert recherches.count(["abc"]) == 1


def test_une_reponse_perimee_ne_remplace_pas_la_liste(telephone, serveur, toutes):
    """Point d'attention 3 : la réponse à « ab », arrivée après celle à « abc », ne remplace
    pas la liste."""
    perimee = _offres("a_voir", [toutes["perimee"]])
    a_jour = _offres("a_voir", [toutes["a_jour"]])
    retenues: list = []

    def repondre(route) -> None:
        recherche = _parametres(route.request.url).get("recherche")
        if recherche == ["ab"]:
            retenues.append(route)
        elif recherche == ["abc"]:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(a_jour))
        else:
            route.continue_()

    telephone.route(TOUTES, repondre)
    _ouvrir_toutes(telephone, serveur)
    champ = telephone.locator("#f-recherche")
    with telephone.expect_request(_demande_offres(lambda p: p.get("recherche") == ["ab"])):
        champ.fill("ab")
    with telephone.expect_response(_demande_offres(lambda p: p.get("recherche") == ["abc"])):
        champ.fill("abc")
    expect(_ligne_toutes(telephone, toutes["a_jour"])).to_be_visible()
    assert len(retenues) == 1

    with telephone.expect_response(_demande_offres(lambda p: p.get("recherche") == ["ab"])):
        retenues[0].fulfill(status=200, content_type="application/json",
                            body=json.dumps(perimee))
    _laisser_passer(telephone)
    assert _ids_toutes(telephone) == [toutes["a_jour"]]


def test_les_filtres_actifs_se_disent_et_s_effacent(telephone, serveur, toutes):
    _servir(telephone, TOUTES, _offres("a_voir", [toutes["ligne"]]))
    _ouvrir_toutes(telephone, serveur)
    famille = telephone.locator("#f-famille option").nth(1)
    cle, libelle = famille.get_attribute("value"), famille.text_content().strip()
    _chercher(telephone, "recherche inventée")
    with telephone.expect_response(_demande_offres(lambda p: p.get("etat") == ["close"])):
        telephone.locator("#f-etat").select_option("close")
    with telephone.expect_response(_demande_offres(lambda p: p.get("famille") == [cle])):
        telephone.locator("#f-famille").select_option(cle)
    resume = telephone.locator("#resume-offres")
    expect(resume).to_contain_text(
        f"Avec recherche : recherche inventée, état : Close et famille : {libelle}.")

    with telephone.expect_request(_demande_offres()) as demande:
        resume.get_by_role("button", name="Effacer les filtres").click()
    assert _parametres(demande.value.url) == {}
    for champ in ("#f-recherche", "#f-etat", "#f-famille"):
        expect(telephone.locator(champ)).to_have_value("")
    expect(resume).not_to_contain_text("Avec")
    expect(resume.get_by_role("button", name="Effacer les filtres")).to_have_count(0)


def test_une_recherche_sans_etat_porte_sur_toutes_les_offres(telephone, serveur, toutes):
    """Point d'attention 6 : un recruteur rappelle pour une offre refusée ; sa recherche la
    trouve sans qu'on choisisse d'état (réponse 21)."""
    _ouvrir_toutes(telephone, serveur)
    parametres = _parametres(_chercher(telephone, EMPLOYEUR_RAPPEL).url)
    assert parametres.get("inclure_ecartees") == ["true"]
    assert "etat" not in parametres
    expect(_lignes_toutes(telephone)).to_have_count(3)
    for cle in ("refusee", "de_cote", "en_cours"):
        expect(_ligne_toutes(telephone, toutes[cle])).to_be_visible()
    expect(telephone.locator("#resume-offres")).to_contain_text(PORTEE)


@pytest.mark.parametrize("chemin", ["lien_d_etat", "lien_puis_candidatures", "sous_le_seuil"])
def test_chercher_une_offre_ne_garde_pas_l_etat_d_avant(telephone, serveur, toutes, chemin):
    """Point d'attention 6 : un état posé plus tôt, par un lien d'entrée ou par « Voir les N sous
    le seuil », ne reste pas dans « Chercher une offre » : la recherche trouve l'offre refusée
    sans qu'on choisisse d'état. Toutes les offres rejointe par le retour (la vue d'avant), ou
    par une entrée de plus (`lien_puis_candidatures`)."""
    if chemin == "sous_le_seuil":
        _servir(telephone, A_FAIRE, {**VIDE, "sous_le_seuil": 3})
        _ouvrir(telephone, serveur)
        telephone.get_by_role("button", name="Voir les 3 sous le seuil ›").click()
    else:
        telephone.goto(f"{serveur}/?filtre=interessante")
    expect(telephone.locator("#vue-offres")).to_be_visible()
    expect(telephone.locator("#f-etat")).not_to_have_value("")
    if chemin == "lien_puis_candidatures":
        telephone.locator('.onglet[data-vue="candidatures"]').click()
        expect(telephone.locator("#vue-candidatures")).to_be_visible()
        _onglet_plus(telephone).click()
    else:
        telephone.locator("#vue-offres .retour-plus").click()
    expect(telephone.locator("#vue-plus")).to_be_visible()

    telephone.get_by_role("button", name="Chercher une offre").click()
    expect(telephone.locator("#vue-offres")).to_be_visible()
    expect(telephone.locator("#f-recherche")).to_be_focused()
    expect(telephone.locator("#f-etat")).to_have_value("")
    parametres = _parametres(_chercher(telephone, EMPLOYEUR_RAPPEL).url)
    assert parametres.get("inclure_ecartees") == ["true"]
    assert "etat" not in parametres
    expect(_ligne_toutes(telephone, toutes["refusee"])).to_be_visible()


def test_une_recherche_avec_un_etat_reste_dans_cet_etat(telephone, serveur, toutes):
    _ouvrir_toutes(telephone, serveur)
    _chercher(telephone, EMPLOYEUR_RAPPEL)
    expect(_lignes_toutes(telephone)).to_have_count(3)
    with telephone.expect_response(_demande_offres(lambda p: p.get("etat") == ["close"])) as rep:
        telephone.locator("#f-etat").select_option("close")
    assert _parametres(rep.value.url) == {"recherche": [EMPLOYEUR_RAPPEL], "etat": ["close"]}
    expect(_lignes_toutes(telephone)).to_have_count(1)
    expect(_ligne_toutes(telephone, toutes["refusee"])).to_be_visible()
    expect(telephone.locator("#resume-offres")).not_to_contain_text(PORTEE)

    # La recherche effacée, puis l'état : la liste « En cours », sans `inclure_ecartees`.
    with telephone.expect_request(_demande_offres(lambda p: "recherche" not in p)) as demande:
        telephone.locator("#f-recherche").fill("")
    assert _parametres(demande.value.url) == {"etat": ["close"]}
    with telephone.expect_request(_demande_offres(lambda p: "etat" not in p)) as demande:
        telephone.locator("#f-etat").select_option("")
    assert _parametres(demande.value.url) == {}


def test_une_liste_plafonnee_le_dit_dans_le_resume(telephone, serveur, toutes):
    _servir(telephone, TOUTES, _offres("a_voir", [toutes["ligne"], toutes["a_jour"]], total=250))
    _ouvrir_toutes(telephone, serveur)
    resume = telephone.locator("#resume-offres")
    expect(resume).to_contain_text("250 offre(s), dont 2 au-dessus du seuil de")
    expect(resume).to_contain_text("Les 2 premières, par score.")


def test_sans_filtre_une_liste_vide_dit_ou_sont_les_closes(telephone, serveur):
    _servir(telephone, TOUTES, _offres("a_voir"))
    _ouvrir_toutes(telephone, serveur)
    resume = telephone.locator("#resume-offres")
    expect(resume).to_have_text(
        "Aucune offre en cours. Les closes et les mises de côté se voient par le filtre d'état.")
    expect(_lignes_toutes(telephone)).to_have_count(0)

    with telephone.expect_response(_demande_offres(lambda p: p.get("etat") == ["close"])):
        telephone.locator("#f-etat").select_option("close")
    expect(resume).to_contain_text("Aucune offre avec état : Close.")
    expect(resume.get_by_role("button", name="Effacer les filtres")).to_be_visible()


def test_la_fiche_je_postule_sans_dossier_dit_je_l_ai_envoyee(telephone, serveur, toutes):
    """Point d'attention 7 : une candidature faite sans dossier, par un formulaire en ligne,
    se dit envoyée depuis la fiche « Je postule » (décision 20)."""
    from veille import db

    offre_id = toutes["sans_dossier"]
    _ouvrir(telephone, serveur)
    telephone.evaluate("id => ouvrirFiche(id)", offre_id)
    fiche = _fiche(telephone, offre_id)
    expect(fiche.locator(".etat-fiche")).to_have_text("Je postule")
    assert fiche.locator(".ligne-actions [data-action]").evaluate_all(
        "es => es.map(e => [e.dataset.action, e.textContent.trim(), e.classList.contains('discret')])"
    ) == [["preparer", "Préparer ma candidature", False], ["envoyee", "Je l'ai envoyée", True]]

    fiche.locator('[data-action="envoyee"]').click()
    fenetre = telephone.locator("#fenetre")
    expect(fenetre.locator("[data-canal]")).to_have_count(6)
    with telephone.expect_response(lambda r: r.request.method == "POST"
                                   and r.url.endswith(f"/api/offres/{offre_id}/statut")):
        fenetre.get_by_role("button", name="LinkedIn", exact=True).click()
    offre = db.lire_offre(offre_id)
    assert offre["statut"] == "candidature_envoyee"
    assert offre["canal_candidature"] == "LinkedIn"


def test_la_bascule_de_l_atout_filtre_sur_l_atout_mis_en_avant(telephone, serveur):
    _ouvrir_toutes(telephone, serveur)
    atout = telephone.evaluate("() => JSON.parse(document.body.dataset.atout)")
    bascule = telephone.locator("#btn-atout")
    resume = telephone.locator("#resume-offres")
    expect(bascule).to_have_attribute("aria-pressed", "false")
    with telephone.expect_request(_demande_offres(lambda p: p.get("atout") == [atout["cle"]])):
        bascule.click()
    expect(bascule).to_have_attribute("aria-pressed", "true")
    expect(resume).to_contain_text(f"atout : {atout['libelle']}")

    with telephone.expect_request(_demande_offres(lambda p: "atout" not in p)):
        bascule.click()
    expect(bascule).to_have_attribute("aria-pressed", "false")
    expect(resume).not_to_contain_text("atout :")


@pytest.mark.parametrize("mis_en_avant", [True, False], ids=["mis_en_avant", "atout_invente"])
def test_un_lien_d_atout_reste_valide(telephone, serveur, mis_en_avant):
    """Point d'attention 4 : un ancien lien `?atout=` filtre Toutes les offres. L'atout mis en
    avant se nomme par son libellé, la bascule enfoncée ; un autre, par sa clé (décision 3)."""
    _ouvrir(telephone, serveur)
    atout = telephone.evaluate("() => JSON.parse(document.body.dataset.atout)")
    cle, nom = (atout["cle"], atout["libelle"]) if mis_en_avant else ("atout_invente",) * 2
    with telephone.expect_request(_demande_offres(lambda p: p.get("atout") == [cle])):
        telephone.goto(f"{serveur}/?atout={cle}")
    expect(telephone.locator("#vue-offres")).to_be_visible()
    resume = telephone.locator("#resume-offres")
    bascule = telephone.locator("#btn-atout")
    expect(resume).to_contain_text(f"atout : {nom}")
    expect(bascule).to_have_attribute("aria-pressed", "true" if mis_en_avant else "false")

    with telephone.expect_request(_demande_offres(lambda p: "atout" not in p)):
        resume.get_by_role("button", name="Effacer les filtres").click()
    expect(resume).not_to_contain_text("atout :")
    expect(bascule).to_have_attribute("aria-pressed", "false")


def test_un_lien_d_etat_ouvre_toutes_les_offres_filtree(telephone, serveur):
    with telephone.expect_request(_demande_offres(lambda p: p.get("etat") == ["mise_de_cote"])):
        telephone.goto(f"{serveur}/?filtre=differee")
    expect(telephone.locator("#vue-offres")).to_be_visible()
    expect(telephone.locator("#f-etat")).to_have_value("mise_de_cote")
    expect(telephone.locator("#resume-offres")).to_contain_text("état : Mises de côté")


def test_toutes_les_offres_se_touche_du_doigt_et_tient_dans_l_ecran(telephone, serveur, toutes):
    _servir(telephone, TOUTES, _offres("a_voir", [toutes["longue"], toutes["ligne"]]))
    _ouvrir_toutes(telephone, serveur)
    expect(_ligne_toutes(telephone, toutes["longue"])).to_contain_text(LONG)
    # Les lignes, la bascule et « ‹ Plus » ; puis les trois champs.
    _cibles_du_doigt(telephone, "#vue-offres")
    assert _lignes_toutes(telephone).count() == 2
    champs = telephone.locator("#vue-offres").locator("input, select").evaluate_all(
        "es => es.map(e => [e.id, e.getBoundingClientRect().height])")
    assert [nom for nom, _ in champs] == ["f-recherche", "f-etat", "f-famille"]
    for nom, hauteur in champs:
        assert hauteur >= DOIGT, (nom, hauteur)
    _tient_dans_l_ecran(telephone)


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


@pytest.mark.parametrize("nombre", [1, 3])
def test_mes_criteres_dit_le_nombre_que_compte_la_pastille(telephone, serveur, nombre):
    """La pastille compte les propositions ; Mes critères dit ce nombre en clair, sous son titre,
    qui compte aussi les offres sans aucune proposition."""
    _servir(telephone, CLASSEMENT, _classement(_propositions(nombre), (SANS_PROPOSITION,)))
    _ouvrir_criteres(telephone, serveur)
    pastille = telephone.locator("#pastille-criteres")
    expect(pastille).to_have_text(str(nombre))
    pluriel = "s" if nombre > 1 else ""
    expect(telephone.locator("#contenu-criteres .compte-propositions")).to_have_text(
        f"{pastille.text_content()} proposition{pluriel} à valider")
    expect(telephone.locator("#contenu-criteres h2").first).to_have_text(
        f"Offres sans famille — {nombre + 1}")


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


def test_deplier_les_archivees_eteint_la_pastille_sous_l_heure_du_serveur(telephone, serveur):
    """`archivee_le` est à l'heure locale du serveur (Paris dans le conteneur), pas en UTC. La
    visite est le `archivee_le` de la plus récente archivée montrée : les deux horloges ne se
    comparent jamais. La vraie route, sans simulation : une archivée inventée, archivée une heure
    en avant de l'UTC, comme Paris en hiver. Puis « ‹ Plus » recompte (`rafraichir()`), et la
    pastille reste éteinte."""
    from veille import db

    (offre_id,) = _inventer(["Archivée inventée à l'heure du serveur"], "plus/heure-serveur",
                            "ecartee")
    db.archiver(offre_id, MOTIF_ARCHIVE)
    heure_du_serveur = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    with db.connexion() as cx:
        cx.execute("UPDATE offres SET archivee_le = ? WHERE id = ?",
                   (heure_du_serveur.isoformat(timespec="seconds"), offre_id))
    pastille = telephone.locator("#pastille-bilan")
    _ouvrir_bilan(telephone, serveur)
    expect(pastille).not_to_be_empty()

    _deplier(telephone, "archivees")
    telephone.wait_for_function(f"() => localStorage.getItem('{CLE_VISITE}') !== null")
    expect(pastille).to_be_empty()

    with telephone.expect_response(lambda r: "/api/archive?" in r.url and "limite=1" in r.url):
        telephone.locator("#vue-bilan .retour-plus").click()
    expect(telephone.locator("#vue-plus")).to_be_visible()
    _laisser_passer(telephone)
    expect(pastille).to_be_empty()


def test_deplier_des_archivees_vides_garde_la_visite(telephone, serveur):
    """Sans archivée montrée, le dépliage ne change pas la visite enregistrée."""
    visite = "2026-10-01T08:00:00.000Z"
    telephone.add_init_script(
        f"try {{ localStorage.setItem('{CLE_VISITE}', '{visite}'); }} catch (e) {{}}")
    _servir(telephone, ARCHIVE, _archive(nouvelles=0))
    _ouvrir_bilan(telephone, serveur)
    _deplier(telephone, "archivees")
    _laisser_passer(telephone)
    assert telephone.evaluate(f"() => localStorage.getItem('{CLE_VISITE}')") == visite


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
    expect(_liste(telephone, "mises-de-cote")).to_be_visible()
    # Mesurée avant les dépliages : une régression de largeur se dit comme telle, et non comme un
    # clic qui expire sur un résumé décalé.
    _tient_dans_l_ecran(telephone)
    for nom in ("archivees", "closes", "mises-de-cote"):
        _deplier(telephone, nom)
    expect(_ligne(telephone, "closes", plus["longue"])).to_contain_text(LONG)
    expect(_liste(telephone, "archivees").locator("article.offre.archivee").first).to_be_visible()
    _cibles_du_doigt(telephone, "#vue-bilan")
    _tient_dans_l_ecran(telephone)


def test_le_bilan_tient_dans_l_ecran_sous_une_police_large(telephone, serveur, plus):
    """Sous la police du runner Linux, plus large que celles de Windows, le tableau « Rendement des
    sources » faisait défiler le Bilan de côté (405 px pour 390), et un clic sur le dernier résumé
    tombait une ligne trop haut. Verdana, sous Windows, en est proche."""
    telephone.add_init_script(POLICE_LARGE)
    _servir(telephone, ENTONNOIR, _entonnoir())
    _servir(telephone, _filtre("close"), _offres("close", [plus["longue"], plus["ecartee"]]))
    _ouvrir_bilan(telephone, serveur)
    assert "Verdana" in telephone.evaluate(
        "getComputedStyle(document.querySelector('#contenu-bilan th')).fontFamily")
    expect(telephone.locator("#contenu-bilan table")).to_have_count(4)
    _tient_dans_l_ecran(telephone)
    # Plus strict que la page : un tableau ne déborde pas de son bloc, même quand la marge de la
    # vue cache le débordement au défilement.
    for titre, largeur, place in telephone.evaluate("""() =>
            [...document.querySelectorAll('#contenu-bilan table')].map(t => {
                const bloc = t.closest('.bloc');
                const style = getComputedStyle(bloc);
                return [bloc.querySelector('h2').textContent, t.getBoundingClientRect().width,
                        bloc.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)];
            })"""):
        assert largeur <= place + 0.5, (titre, largeur, place)

    for nom in ("archivees", "closes", "mises-de-cote"):
        _deplier(telephone, nom)
    expect(_ligne(telephone, "closes", plus["longue"])).to_contain_text(LONG)
    _tient_dans_l_ecran(telephone)


# ---------------------------------------------------------------------------
# Réglages, l'en-tête et le push côté client (E11 ; décisions 11 et 12)
# ---------------------------------------------------------------------------

# Les cinq cas de Réglages (`ETATS_PUSH`), mot pour mot, la raison d'un navigateur sans push et
# la phrase de la réparation.
INDISPONIBLE = "Les notifications ne sont pas disponibles sur cet appareil."
SANS_PUSH_WEB = "Ce navigateur ne gère pas le push web."
BLOQUEES = ("Les notifications sont bloquées pour la console sur cet appareil. Autorise-les dans "
            "les réglages d'Android (Applications › Veille emploi › Notifications) ou dans ceux du "
            "site, dans Chrome, puis touche « Activer les notifications ».")
INACTIVES = "Cet appareil ne reçoit pas les notifications."
ACTIVES = "Cet appareil reçoit les notifications."
REPARATION = ("Le premier essai n'était pas parti : l'abonnement de cet appareil vient d'être "
              "refait, et la notification d'essai est partie.")
TOUJOURS_PAS = "la notification d'essai n'est pas partie, même avec un nouvel abonnement"
SANS_SERVICE_WORKER = "le service worker de la console ne s'est pas enregistré"
# L'échec d'un `fetch` (« Failed to fetch » sous Chrome), en français.
CAUSE_RESEAU = "la console n'a pas pu être jointe"
ACTIVER = "Activer les notifications"
ESSAYER = "Envoyer une notification d'essai"
# Les réponses de `api_push_test`, à ses clés.
ESSAI_PARTI = {"envoyes": 1, "echecs": 0}
ESSAI_PERDU = {"envoyes": 0, "echecs": 1}
PANNE_RENVOI = "Panne inventée du renvoi"
PANNE_RETRAIT = "Panne inventée du retrait"
REFUS_PUSH = "Refus inventé du service push"
# Un abonnement à la clé illisible : `options.applicationServerKey` à `null`, ou pas d'`options`.
CLE_NULLE = "nulle"
SANS_OPTIONS = "sans-options"
# Une autre clé publique inventée, de 65 octets comme une clé P-256 non compressée : celle d'une
# paire VAPID d'avant, quand le `vapid.json` a été refait.
AUTRE_CLE = base64.urlsafe_b64encode(bytes([4, *range(1, 65)])).rstrip(b"=").decode()

ABONNEMENT_PUSH = re.compile(r"/api/push/abonnement(\?.*)?$")
ESSAI_PUSH = re.compile(r"/api/push/test$")
REGLAGES = re.compile(r"/api/reglages$")
RENVOI = "POST /api/push/abonnement"
ESSAI = "POST /api/push/test"

# Le push du navigateur, simulé avant `app.js` : la permission, `requestPermission`, et
# `getSubscription` et `subscribe` sur `PushManager.prototype`. Les abonnements sont inventés, et
# suivent l'état comme dans Chrome : `getSubscription` rend celui que `subscribe` vient de rendre,
# et `null` après son `unsubscribe` ; `subscribe` refuse (`InvalidStateError`) tant qu'un abonnement
# d'une autre clé reste. Leur `options.applicationServerKey` est un `ArrayBuffer`, jamais la chaîne
# base64url de la page. `journal` note, dans l'ordre, les demandes de permission, les `subscribe`,
# les `unsubscribe` et chaque appel de `/api/push/…`, que `page.route` simule.
FAUX_PUSH = """({permission, accordee, cle, subscribeRejete, sansPush}) => {
    const etat = window.__push = {permission, demandes: 0, journal: [], abonnements: [], cles: [],
                                  courant: null};
    const noter = evenement => etat.journal.push(evenement);
    Object.defineProperty(Notification, 'permission', {configurable: true, get: () => etat.permission});
    Notification.requestPermission = async () => {
        etat.demandes += 1;
        noter('requestPermission');
        etat.permission = accordee;
        return accordee;
    };
    const fetchVrai = window.fetch;
    window.fetch = function (entree, options) {
        const adresse = new URL(typeof entree === 'string' ? entree : entree.url, location.href);
        if (adresse.pathname.startsWith('/api/push/')) {
            const methode = ((options && options.method) || 'GET').toUpperCase();
            noter(`${methode} ${adresse.pathname}${adresse.search}`);
        }
        return fetchVrai.apply(this, arguments);
    };
    if (sansPush) { delete window.PushManager; return; }
    const octets = b64 => Uint8Array.from(
        atob(b64.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - b64.length % 4) % 4)),
        c => c.charCodeAt(0));
    const inventer = cleRecue => {
        const n = etat.abonnements.length + 1;
        const endpoint = `https://push.exemple.invalid/abonnement-${n}`;
        const json = {endpoint, expirationTime: null,
                      keys: {p256dh: `p256dh-invente-${n}`, auth: `auth-invente-${n}`}};
        etat.abonnements.push(json);
        const abonnement = {
            endpoint,
            options: {userVisibleOnly: true,
                      applicationServerKey: cleRecue && Uint8Array.from(cleRecue).buffer},
            toJSON: () => json,
            unsubscribe: async () => {
                noter('unsubscribe');
                if (etat.courant === abonnement) etat.courant = null;
                return true;
            },
        };
        return abonnement;
    };
    if (cle === 'nulle') etat.courant = inventer(null);
    else if (cle === 'sans-options') delete (etat.courant = inventer(null)).options;
    else if (cle) etat.courant = inventer(octets(cle));
    PushManager.prototype.getSubscription = async function () { return etat.courant; };
    PushManager.prototype.subscribe = async function (options) {
        const recue = new Uint8Array(options.applicationServerKey);
        noter('subscribe');
        etat.cles.push({userVisibleOnly: options.userVisibleOnly, octets: Array.from(recue)});
        if (subscribeRejete) throw new DOMException(subscribeRejete, 'AbortError');
        const actuelle = etat.courant && etat.courant.options
            && etat.courant.options.applicationServerKey;
        if (actuelle && Array.from(new Uint8Array(actuelle)).join() !== Array.from(recue).join()) {
            const refus = 'A subscription with a different applicationServerKey already exists.';
            throw new DOMException(refus, 'InvalidStateError');
        }
        etat.courant = inventer(recue);
        return etat.courant;
    };
}"""

# `navigator.serviceWorker.ready` retenu jusqu'à `window.__libererReady()`, qui le libère avec le
# vrai : l'enregistrement de `/sw.js`, une fois son service worker actif.
READY_RETENU = """(() => {
    const lire = Object.getOwnPropertyDescriptor(ServiceWorkerContainer.prototype, 'ready').get;
    let liberer;
    const retenue = new Promise(r => { liberer = r; });
    window.__libererReady = () => liberer(lire.call(navigator.serviceWorker));
    Object.defineProperty(ServiceWorkerContainer.prototype, 'ready',
                          {configurable: true, get() { return retenue; }});
})();"""

REGISTER_REJETE = """ServiceWorkerContainer.prototype.register =
    () => Promise.reject(new TypeError('Enregistrement inventé impossible'));"""

# Le premier `register` de la page (celui de l'ouverture) échoue, les suivants passent.
REGISTER_REJETE_UNE_FOIS = """(() => {
    const vrai = ServiceWorkerContainer.prototype.register;
    let appels = 0;
    ServiceWorkerContainer.prototype.register = function (...args) {
        appels += 1;
        return appels === 1 ? Promise.reject(new TypeError('Enregistrement inventé impossible'))
                            : vrai.apply(this, args);
    };
})();"""


@pytest.fixture(scope="module")
def cles_push(serveur):
    """La paire VAPID de la console, que la page lit à chaque rendu (`data-vapid`). Créée si elle
    manque, le fichier reste pour la session : les tests suivants voient une console qui a sa clé,
    et leur Chromium, sans permission accordée, n'y abonne rien."""
    from veille import notifications

    if not notifications.CHEMIN_VAPID.exists():
        notifications.generer_vapid("mailto:camille@exemple.invalid")
    return notifications.charger_vapid()


def _octets(cle: str) -> list[int]:
    return list(base64.urlsafe_b64decode(cle + "=" * (-len(cle) % 4)))


def _chemin(url: str) -> str:
    morceaux = urlsplit(url)
    return morceaux.path + (f"?{morceaux.query}" if morceaux.query else "")


def simuler_push(page, permission: str, abonnement: str | None, *, accordee: str | None = None,
                 essais: tuple = (ESSAI_PARTI,), renvoi: int = 200, retrait: int = 200,
                 retenir: dict | None = None, subscribe_rejete: bool = False,
                 sans_push: bool = False) -> list:
    """Simule le push du navigateur (`FAUX_PUSH`) et les trois routes du push, avant `app.js`.

    `abonnement` est la clé, en base64url, de l'abonnement que l'appareil garde, `CLE_NULLE` ou
    `SANS_OPTIONS` pour une clé illisible, ou None. Rend la liste des demandes reçues par les
    routes, `(méthode, chemin, corps)`. L'essai rend `essais` dans l'ordre, puis le dernier ; le
    `POST` de l'abonnement répond `renvoi`, son `DELETE` `retrait`. `retenir` associe une demande
    (`RENVOI`, `ESSAI`) à une liste : sa réponse y attend, une fonction qui l'envoie. Aucun
    abonnement inventé n'entre dans la base commune à la session."""
    requetes: list = []
    reponses = list(essais)

    def repondre(route, statut: int, corps: dict) -> None:
        def envoyer() -> None:
            route.fulfill(status=statut, content_type="application/json", body=json.dumps(corps))
        demande = f"{route.request.method} {urlsplit(route.request.url).path}"
        if retenir and demande in retenir:
            retenir[demande].append(envoyer)
        else:
            envoyer()

    def abonner(route) -> None:
        requete = route.request
        requetes.append((requete.method, _chemin(requete.url),
                         requete.post_data_json if requete.post_data else None))
        if requete.method == "POST":
            statut, panne = renvoi, PANNE_RENVOI
        else:
            statut, panne = retrait, PANNE_RETRAIT
        repondre(route, statut, {"ok": True} if statut == 200 else {"detail": panne})

    def essayer(route) -> None:
        requetes.append((route.request.method, _chemin(route.request.url), None))
        repondre(route, 200, reponses.pop(0) if len(reponses) > 1 else reponses[0])

    page.route(ABONNEMENT_PUSH, abonner)
    page.route(ESSAI_PUSH, essayer)
    parametres = {"permission": permission, "accordee": accordee or permission, "cle": abonnement,
                  "subscribeRejete": REFUS_PUSH if subscribe_rejete else "",
                  "sansPush": sans_push}
    page.add_init_script(f"({FAUX_PUSH})({json.dumps(parametres)});")
    return requetes


def _journal(page) -> list[str]:
    return page.evaluate("() => window.__push.journal")


def _abonnements(page) -> list[dict]:
    """Les abonnements inventés, dans l'ordre : leur `toJSON()`."""
    return page.evaluate("() => window.__push.abonnements")


def _subscribes(page) -> list[dict]:
    """Ce que chaque `subscribe` a reçu : `userVisibleOnly` et les octets de la clé."""
    return page.evaluate("() => window.__push.cles")


def _ouvrir_reglages(page, url: str) -> None:
    _ouvrir_plus(page, url)
    page.locator('.lien-plus[data-vue="reglages"]').click()
    expect(page.locator("#vue-reglages")).to_be_visible()


def _etat_push(page):
    return page.locator("#etat-push")


def _bouton_push(page):
    return page.locator("#btn-push")


def _quitter(page):
    return page.locator("#vue-reglages form[action='/deconnexion'] button")


def _en_erreur(cause: str) -> str:
    return (f"Cet appareil n'a pas pu s'abonner aux notifications : {cause}. "
            "Touche « Activer les notifications » pour réessayer.")


def _toucher_le_bouton(page) -> None:
    """Touche le bouton du push, puis attend la fin du geste : le bouton, éteint pendant, se
    rallume."""
    _bouton_push(page).click()
    expect(_bouton_push(page)).to_be_enabled()
    _laisser_passer(page)


def test_l_en_tete_ne_garde_que_le_titre(telephone, serveur):
    _ouvrir(telephone, serveur)
    barre = telephone.locator(".barre")
    expect(barre).to_have_text("Veille emploi")
    expect(barre.locator("button")).to_have_count(0)
    expect(barre.locator("form")).to_have_count(0)


def test_reglages_porte_notifications_en_tete_et_quitter_au_pied(telephone, serveur):
    _ouvrir_reglages(telephone, serveur)
    expect(telephone.locator("#contenu-reglages .bloc").first).to_be_visible()
    enfants = telephone.locator("#vue-reglages > *").evaluate_all(
        "es => es.map(e => e.id || e.className)")
    assert enfants == ["retour-plus", "bloc-notifications", "contenu-reglages", "bloc-quitter"]
    bloc = telephone.locator("#bloc-notifications")
    expect(bloc.locator("h2")).to_have_text("Notifications")
    expect(bloc.locator("#etat-push")).to_be_visible()
    expect(bloc.locator("#btn-push")).to_be_visible()
    formulaire = telephone.locator("#bloc-quitter form")
    expect(formulaire).to_have_attribute("action", "/deconnexion")
    expect(formulaire).to_have_attribute("method", "post")
    expect(_quitter(telephone)).to_have_text("Quitter")
    expect(_quitter(telephone)).to_be_visible()


def test_quitter_ferme_la_session(telephone, serveur):
    _ouvrir_reglages(telephone, serveur)
    _quitter(telephone).click()
    telephone.wait_for_url(f"{serveur}/connexion")
    telephone.goto(f"{serveur}/")
    expect(telephone).to_have_url(f"{serveur}/connexion")


def test_quitter_marche_meme_si_les_reglages_echouent(telephone, serveur, console_attendue):
    """« Quitter » est écrit dans la page, hors de ce que `chargerReglages` réécrit
    (décision 11)."""
    console_attendue.append("500")
    _servir(telephone, REGLAGES, {"detail": "Panne inventée des réglages"}, status=500)
    with telephone.expect_response(REGLAGES):
        _ouvrir_reglages(telephone, serveur)
    expect(telephone.locator("#contenu-reglages .bloc")).to_have_count(0)
    expect(_quitter(telephone)).to_be_visible()
    _quitter(telephone).click()
    telephone.wait_for_url(f"{serveur}/connexion")


def test_a_l_ouverture_l_abonnement_existant_est_renvoye(telephone, serveur, cles_push):
    """Point d'attention 2 : l'abonnement que l'appareil garde, fait avec la clé de la page, est
    renvoyé tel quel, sans se refaire : les clés se comparent sur leurs octets."""
    requetes = simuler_push(telephone, "granted", cles_push.publique)
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    expect(_bouton_push(telephone)).to_have_text(ESSAYER)
    _laisser_passer(telephone)
    assert _journal(telephone) == [RENVOI]
    (garde,) = _abonnements(telephone)
    assert requetes == [("POST", "/api/push/abonnement", garde)]
    assert telephone.evaluate("() => window.__push.demandes") == 0


def test_sans_abonnement_l_ouverture_se_reabonne(telephone, serveur, cles_push):
    """Point d'attention 2 : la permission gardée, l'abonnement perdu (`getSubscription` rend
    `null`) ; l'ouverture se réabonne, avec la clé de la page."""
    requetes = simuler_push(telephone, "granted", None)
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    _laisser_passer(telephone)
    assert _journal(telephone) == ["subscribe", RENVOI]
    (recu,) = _subscribes(telephone)
    assert recu["userVisibleOnly"] is True
    assert len(recu["octets"]) == 65
    assert recu["octets"] == _octets(cles_push.publique)
    (nouveau,) = _abonnements(telephone)
    assert requetes == [("POST", "/api/push/abonnement", nouveau)]


def test_un_abonnement_d_une_autre_cle_se_refait(telephone, serveur, cles_push):
    """Réponse 22 : un abonnement fait avec une autre clé VAPID se refait avec celle de la page,
    puis l'ancien est retiré de la base, qu'un push en 403 ne retirerait jamais."""
    requetes = simuler_push(telephone, "granted", AUTRE_CLE)
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    _laisser_passer(telephone)
    ancien, nouveau = _abonnements(telephone)
    retrait = f"/api/push/abonnement?endpoint={quote(ancien['endpoint'], safe='')}"
    assert _journal(telephone) == ["unsubscribe", "subscribe", RENVOI, f"DELETE {retrait}"]
    assert [r["octets"] for r in _subscribes(telephone)] == [_octets(cles_push.publique)]
    assert requetes == [("POST", "/api/push/abonnement", nouveau), ("DELETE", retrait, None)]


def test_un_essai_qui_ne_part_pas_refait_l_abonnement(telephone, serveur, cles_push):
    """Réponse R3, point d'attention 2 : Chrome garde un abonnement que le service push a rejeté ;
    le renvoi le remet en base, et l'essai, qui ne part pas, le refait, puis se relance une fois."""
    requetes = simuler_push(telephone, "granted", cles_push.publique,
                            essais=(ESSAI_PERDU, ESSAI_PARTI))
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    _toucher_le_bouton(telephone)
    expect(_etat_push(telephone)).to_have_text(f"{ACTIVES} {REPARATION}")
    expect(_bouton_push(telephone)).to_have_text(ESSAYER)
    assert _journal(telephone) == [RENVOI, ESSAI, "unsubscribe", "subscribe", RENVOI, ESSAI]
    assert [r["octets"] for r in _subscribes(telephone)] == [_octets(cles_push.publique)]
    garde, nouveau = _abonnements(telephone)
    assert [corps for methode, _, corps in requetes if methode == "POST" and corps] == [garde,
                                                                                        nouveau]


def test_un_essai_qui_ne_part_toujours_pas_se_dit_en_erreur(telephone, serveur, cles_push):
    """Réponse R3 : le second essai, après le nouvel abonnement, ne part pas non plus ; il ne se
    relance pas une troisième fois, et Réglages le dit en erreur."""
    simuler_push(telephone, "granted", cles_push.publique, essais=(ESSAI_PERDU,))
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    _toucher_le_bouton(telephone)
    expect(_etat_push(telephone)).to_have_text(_en_erreur(TOUJOURS_PAS))
    expect(_bouton_push(telephone)).to_have_text(ACTIVER)
    assert _journal(telephone) == [RENVOI, ESSAI, "unsubscribe", "subscribe", RENVOI, ESSAI]


def test_un_essai_parti_avec_un_echec_ne_repare_rien(telephone, serveur, cles_push):
    """Décision 12 : la condition porte sur `envoyes`, jamais sur `echecs` ; un essai parti vers
    cet appareil, et refusé par un autre abonnement, ne désabonne pas un téléphone qui reçoit."""
    requetes = simuler_push(telephone, "granted", cles_push.publique,
                            essais=({"envoyes": 1, "echecs": 1},))
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    _toucher_le_bouton(telephone)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    assert _journal(telephone) == [RENVOI, ESSAI]
    (garde,) = _abonnements(telephone)
    assert requetes == [("POST", "/api/push/abonnement", garde), ("POST", "/api/push/test", None)]


def test_activer_les_notifications_refait_un_abonnement_rejete(telephone, serveur, cles_push):
    """Réponse R3, précision 1 : l'essai qui finit « Activer les notifications » lit sa réponse
    comme celui du bouton d'essai, et refait l'abonnement rejeté que `subscribe` a rendu."""
    requetes = simuler_push(telephone, "default", None, accordee="granted",
                            essais=(ESSAI_PERDU, ESSAI_PARTI))
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(INACTIVES)
    expect(_bouton_push(telephone)).to_have_text(ACTIVER)
    _toucher_le_bouton(telephone)
    expect(_etat_push(telephone)).to_have_text(f"{ACTIVES} {REPARATION}")
    assert _journal(telephone) == ["requestPermission", "subscribe", RENVOI, ESSAI,
                                   "unsubscribe", "subscribe", RENVOI, ESSAI]
    assert [r["octets"] for r in _subscribes(telephone)] == [_octets(cles_push.publique)] * 2
    premier, nouveau = _abonnements(telephone)
    assert [corps for methode, _, corps in requetes if methode == "POST" and corps] == [premier,
                                                                                        nouveau]


def test_activer_des_notifications_refusees_le_dit_dans_reglages(telephone, serveur, cles_push):
    """Décision 12 : les refus d'`activerPush` reprennent les phrases de Réglages."""
    requetes = simuler_push(telephone, "default", None, accordee="denied")
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(INACTIVES)
    _toucher_le_bouton(telephone)
    expect(_etat_push(telephone)).to_have_text(BLOQUEES)
    expect(_bouton_push(telephone)).to_have_text(ACTIVER)
    assert _journal(telephone) == ["requestPermission"]
    assert requetes == []


def test_le_reabonnement_attend_le_service_worker_actif(telephone, serveur, cles_push):
    """Chrome rejette un `subscribe` sans service worker actif : le réabonnement attend
    `navigator.serviceWorker.ready`."""
    telephone.add_init_script(READY_RETENU)
    simuler_push(telephone, "granted", None)
    _ouvrir_reglages(telephone, serveur)
    _laisser_passer(telephone, 500)
    assert "subscribe" not in _journal(telephone)
    # Le réabonnement en cours ne prétend rien : aucune phrase, le bouton éteint.
    expect(_etat_push(telephone)).to_have_text("")
    expect(_bouton_push(telephone)).to_be_disabled()

    telephone.evaluate("() => window.__libererReady()")
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    expect(_bouton_push(telephone)).to_be_enabled()
    _laisser_passer(telephone)
    assert _journal(telephone) == ["subscribe", RENVOI]


def test_sans_permission_l_ouverture_ne_demande_rien(telephone, serveur, cles_push):
    """Sans geste, Chrome refuse ou ignore la demande de permission : l'ouverture n'en fait
    aucune (réponse 11)."""
    requetes = simuler_push(telephone, "default", None)
    _ouvrir_reglages(telephone, serveur)
    _laisser_passer(telephone, 300)
    expect(_etat_push(telephone)).to_have_text(INACTIVES)
    expect(_bouton_push(telephone)).to_have_text(ACTIVER)
    assert telephone.evaluate("() => window.__push.demandes") == 0
    assert _journal(telephone) == []
    assert requetes == []


def test_des_notifications_bloquees_se_disent(telephone, serveur, cles_push):
    requetes = simuler_push(telephone, "denied", None)
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(BLOQUEES)
    expect(_bouton_push(telephone)).to_have_text(ACTIVER)
    _laisser_passer(telephone)
    assert _journal(telephone) == []
    assert requetes == []


def test_sans_push_reglages_dit_indisponible(telephone, serveur, cles_push):
    requetes = simuler_push(telephone, "granted", None, sans_push=True)
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(f"{INDISPONIBLE} {SANS_PUSH_WEB}")
    expect(_bouton_push(telephone)).to_be_disabled()
    _laisser_passer(telephone)
    assert _journal(telephone) == []
    assert requetes == []


@pytest.mark.parametrize("panne", ["renvoi_500", "renvoi_coupe", "subscribe_rejete",
                                   "register_rejete"])
def test_un_renvoi_en_echec_se_dit_dans_reglages(telephone, serveur, cles_push, console_attendue,
                                                 panne):
    """Un renvoi refusé par le serveur ou coupé (la console hors ligne), un refus du service push,
    un enregistrement impossible : Réglages le dit en erreur, avec sa cause, en français, et
    propose de réessayer."""
    if panne == "renvoi_500":
        console_attendue.append("500")
        simuler_push(telephone, "granted", cles_push.publique, renvoi=500)
        cause = PANNE_RENVOI
    elif panne == "renvoi_coupe":
        console_attendue.append("net::ERR_FAILED")
        simuler_push(telephone, "granted", cles_push.publique)
        # Posée après celle de `simuler_push`, cette route passe avant elle.
        telephone.route(ABONNEMENT_PUSH, lambda route: route.abort())
        cause = CAUSE_RESEAU
    elif panne == "subscribe_rejete":
        simuler_push(telephone, "granted", None, subscribe_rejete=True)
        cause = REFUS_PUSH
    else:
        telephone.add_init_script(REGISTER_REJETE)
        simuler_push(telephone, "granted", cles_push.publique)
        cause = SANS_SERVICE_WORKER
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(_en_erreur(cause))
    expect(_etat_push(telephone)).not_to_contain_text("Failed to fetch")
    expect(_bouton_push(telephone)).to_have_text(ACTIVER)


def test_la_cause_d_un_echec_se_dit_en_francais(telephone, serveur):
    """L'échec d'un `fetch` se dit « la console n'a pas pu être jointe » ; une erreur sans message,
    « cause inconnue » ; une autre garde son message, sans point final."""
    _ouvrir(telephone, serveur)
    assert telephone.evaluate("() => causeDe(new TypeError('Failed to fetch'))") == CAUSE_RESEAU
    assert telephone.evaluate("() => causeDe(new Error())") == "cause inconnue"
    assert telephone.evaluate("() => causeDe(new TypeError())") == "cause inconnue"
    assert telephone.evaluate("() => causeDe(new TypeError('x inventé.'))") == "x inventé"


def test_activer_les_notifications_abonne_puis_envoie_un_essai(telephone, serveur, cles_push):
    requetes = simuler_push(telephone, "default", None, accordee="granted")
    _ouvrir_reglages(telephone, serveur)
    expect(_bouton_push(telephone)).to_have_text(ACTIVER)
    _toucher_le_bouton(telephone)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    expect(_bouton_push(telephone)).to_have_text(ESSAYER)
    assert _journal(telephone) == ["requestPermission", "subscribe", RENVOI, ESSAI]
    (nouveau,) = _abonnements(telephone)
    assert requetes == [("POST", "/api/push/abonnement", nouveau),
                        ("POST", "/api/push/test", None)]


def _revenir_sur_reglages(page) -> None:
    """Quitte Réglages pour « Plus », puis y revient : `chargerReglages` repasse."""
    with page.expect_response(REGLAGES):
        page.locator("#vue-reglages .retour-plus").click()
        page.locator('.lien-plus[data-vue="reglages"]').click()


def test_pendant_le_renvoi_de_l_ouverture_le_bouton_est_eteint(telephone, serveur, cles_push):
    """Tant que le renvoi de l'ouverture n'a pas répondu, Réglages ne dit pas « ne reçoit pas »,
    et « Activer » ne lance pas un second geste."""
    attente: list = []
    simuler_push(telephone, "granted", cles_push.publique, retenir={RENVOI: attente})
    with telephone.expect_request(lambda r: r.method == "POST" and ABONNEMENT_PUSH.search(r.url)):
        _ouvrir_reglages(telephone, serveur)
    expect(_bouton_push(telephone)).to_be_disabled()
    expect(_etat_push(telephone)).to_have_text("")
    _revenir_sur_reglages(telephone)
    expect(_bouton_push(telephone)).to_be_disabled()
    expect(_etat_push(telephone)).to_have_text("")

    attente.pop()()
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    expect(_bouton_push(telephone)).to_be_enabled()
    assert _journal(telephone) == [RENVOI]


def test_un_second_toucher_pendant_un_geste_ne_lance_rien(telephone, serveur, cles_push):
    """Réglages rechargé pendant « Activer les notifications » ne rallume pas le bouton : un
    second toucher ne lance pas un geste concurrent, qui pourrait se désabonner pendant que le
    premier dit « reçoit »."""
    attente: list = []
    simuler_push(telephone, "default", None, accordee="granted", retenir={ESSAI: attente})
    _ouvrir_reglages(telephone, serveur)
    with telephone.expect_request(lambda r: ESSAI_PUSH.search(r.url)):
        _bouton_push(telephone).click()
    _revenir_sur_reglages(telephone)
    expect(_bouton_push(telephone)).to_be_disabled()
    _bouton_push(telephone).click(force=True)
    _laisser_passer(telephone)

    attente.pop()()
    expect(_bouton_push(telephone)).to_be_enabled()
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    _laisser_passer(telephone)
    assert attente == []
    assert _journal(telephone) == ["requestPermission", "subscribe", RENVOI, ESSAI]


def test_un_rechargement_de_reglages_pendant_un_geste_ne_rallume_pas_le_bouton(telephone, serveur,
                                                                                cles_push):
    """`rafraichir()`, Réglages ouvert, repasse par `chargerReglages` pendant l'essai : le bouton
    reste éteint jusqu'à la fin du geste."""
    attente: list = []
    simuler_push(telephone, "granted", cles_push.publique, retenir={ESSAI: attente})
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    with telephone.expect_request(lambda r: ESSAI_PUSH.search(r.url)):
        _bouton_push(telephone).click()
    with telephone.expect_response(REGLAGES):
        telephone.evaluate("() => rafraichir()")
    expect(_bouton_push(telephone)).to_be_disabled()

    attente.pop()()
    expect(_bouton_push(telephone)).to_be_enabled()
    expect(_etat_push(telephone)).to_have_text(ACTIVES)


def test_un_retrait_en_echec_ne_dit_pas_d_erreur(telephone, serveur, cles_push, console_attendue):
    """Le `DELETE` de l'ancien abonnement refusé, l'appareil reste abonné avec la clé de la page :
    la ligne morte est tolérée (décision 12, seconde limite)."""
    console_attendue.append("500")
    simuler_push(telephone, "granted", AUTRE_CLE, retrait=500)
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    _laisser_passer(telephone)
    ancien, _ = _abonnements(telephone)
    retrait = f"/api/push/abonnement?endpoint={quote(ancien['endpoint'], safe='')}"
    assert _journal(telephone) == ["unsubscribe", "subscribe", RENVOI, f"DELETE {retrait}"]
    expect(telephone.locator("#messages")).to_be_empty()


def test_activer_refait_un_abonnement_d_une_autre_cle(telephone, serveur, cles_push):
    """L'ouverture a échoué avant de refaire l'abonnement d'une autre clé (`register` refusé) :
    « Activer les notifications » le refait, `unsubscribe` d'abord, sans quoi Chrome refuse le
    `subscribe` (`InvalidStateError`)."""
    telephone.add_init_script(REGISTER_REJETE_UNE_FOIS)
    requetes = simuler_push(telephone, "granted", AUTRE_CLE)
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(_en_erreur(SANS_SERVICE_WORKER))
    assert _journal(telephone) == []

    _toucher_le_bouton(telephone)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    ancien, nouveau = _abonnements(telephone)
    retrait = f"/api/push/abonnement?endpoint={quote(ancien['endpoint'], safe='')}"
    assert _journal(telephone) == ["requestPermission", "unsubscribe", "subscribe", RENVOI,
                                   f"DELETE {retrait}", ESSAI]
    assert [r["octets"] for r in _subscribes(telephone)] == [_octets(cles_push.publique)]
    assert ("POST", "/api/push/abonnement", nouveau) in requetes


@pytest.mark.parametrize("illisible", [CLE_NULLE, SANS_OPTIONS])
def test_un_abonnement_a_la_cle_illisible_est_renvoye_tel_quel(telephone, serveur, cles_push,
                                                               illisible):
    """Sans clé lisible, l'abonnement se renvoie tel quel, sans se refaire à chaque ouverture :
    l'essai détectera un abonnement rejeté."""
    requetes = simuler_push(telephone, "granted", illisible)
    _ouvrir_reglages(telephone, serveur)
    expect(_etat_push(telephone)).to_have_text(ACTIVES)
    _laisser_passer(telephone)
    assert _journal(telephone) == [RENVOI]
    (garde,) = _abonnements(telephone)
    assert requetes == [("POST", "/api/push/abonnement", garde)]


def test_reglages_se_touche_du_doigt_et_tient_dans_l_ecran(telephone, serveur, cles_push):
    """Mesuré aussi sous une police large : celle du runner Linux de la CI est plus large que
    celles de Windows, et une vue qui déborde de côté y décale les clics. La police large se pose
    au rechargement, qui garde Réglages (décision 15). Rouvrir `/` ne la reposerait pas sur
    « À faire » : Chromium garde `history.state` d'une navigation vers l'adresse courante."""
    simuler_push(telephone, "granted", cles_push.publique)
    _ouvrir_reglages(telephone, serveur)
    for police_large in (False, True):
        if police_large:
            telephone.add_init_script(POLICE_LARGE)
            telephone.reload()
            expect(telephone.locator("#vue-reglages")).to_be_visible()
        expect(_bouton_push(telephone)).to_have_text(ESSAYER)
        expect(telephone.locator("#liste-appareils .ligne-appareil").first).to_be_visible()
        expect(telephone.locator("#liste-passkeys")).not_to_be_empty()
        if police_large:
            assert "Verdana" in telephone.evaluate(
                "getComputedStyle(document.querySelector('#contenu-reglages')).fontFamily")
        _cibles_du_doigt(telephone, "#vue-reglages")
        _tient_dans_l_ecran(telephone)
