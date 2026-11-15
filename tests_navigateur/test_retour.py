"""Le retour d'Android, au téléphone (E10 ; décision 15 du plan du lot 3).

Chaque vue et chaque fenêtre entrent dans l'historique. Le retour ferme la fenêtre ouverte, quoi
qu'elle montre ; sans fenêtre, il revient à la vue d'avant ; depuis « À faire », il quitte la
console.

Même forme que `test_plus.py` : Chromium à la taille d'un téléphone, une session ouverte par
`auth.ouvrir_session`, aucune erreur dans la console hors de `console_attendue`. Les offres sont
inventées par `_inventer`, sous le chemin `retour` (décision 18) : un test ne lit que les siennes.
`/preparer` et le mot de relance sont simulés : la console des tests sert l'exemple, et refuse ces
gestes par un 409.

Le retour d'Android est ici `page.go_back()`. Il rend `None` pour une entrée posée par
`pushState`, comme quand rien ne précède : sa valeur ne prouve rien, et chaque test lit la vue
montrée. Le retour qui quitte la console part d'un autre document, `/sante`. Playwright ne saute
aucune entrée : ce que Chrome fait au téléphone d'une entrée poussée sans geste se vérifie au
staging (réponse 15).
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from .test_cibles_tactiles import TELEPHONE
# `console_attendue` est une fixture : importée, elle sert à la fixture `telephone` d'ici.
from .test_parcours_candidature import (_etape, _inventer, _ouvrir, _simuler_preparation,
                                        console_attendue)

SANTE = "/sante"
ANNONCE = "https://exemple.invalid/parcours/retour/annonce-inventee"
RAISON_TEXTE = "Raison inventée du retour : ce site interdit la lecture automatique."
TEXTE_RELANCE = "Texte inventé du mot de relance, à relire avant de l'envoyer."
# Une entrée qui porte encore la fenêtre : la fermeture la retire par un retour, qui prend un
# instant. Cinq secondes au plus pour le voir arriver : un délai de garde, pas une attente fixe.
GARDE_MS = 5000
# Ce qui ne doit pas arriver ne s'attend pas : on relit après ce délai. Chromium restaure le
# défilement d'une entrée à la première image après son `popstate` (4 ms, sondé le 15/11/2026),
# et un second retour lancé par erreur arrive dans le même temps.
RELIRE_APRES_MS = 300
# Assez de candidatures pour que « Candidatures » défile, au téléphone.
A_DEFILER = 30

# Le `popstate` du retour que lance la fermeture de la fenêtre, guetté avant le geste.
GUETTER_LE_RETOUR = """() => { window.retourVu = new Promise(r =>
    addEventListener('popstate', () => r(true), { once: true })); }"""
RETOUR_VU = f"""() => Promise.race([window.retourVu,
    new Promise(r => setTimeout(() => r(false), {GARDE_MS}))])"""


# Les trois ordres d'une fenêtre rouverte aussitôt (« Outils et cas limites », `history.back()`),
# sur la fiche ouverte. A : fermée puis rouverte dans la même tâche, avant l'événement `close`.
# B : rouverte après l'événement `close`, avant le `popstate` du retour qu'il lance. Chacun dit si
# la fenêtre s'est rouverte avant ce `popstate` (`avant`), sans quoi il ne serait que l'ordre C,
# puis l'attend (`vu`) : un `go_back` lancé avant lui partirait d'une autre entrée.
def _rouvrir(attendre_close: bool) -> str:
    attente = ("await new Promise(r => f.addEventListener('close', r, { once: true }));"
               if attendre_close else "")
    return f"""async () => {{
        const f = document.querySelector('#fenetre');
        let deja = false;
        const retour = new Promise(r => addEventListener('popstate', () => {{ deja = true; r(true); }},
                                                         {{ once: true }}));
        f.close();
        {attente}
        const avant = !deja;
        ouvrirFenetre();
        const vu = await Promise.race([retour, new Promise(r => setTimeout(() => r(false), {GARDE_MS}))]);
        return {{ avant, vu }};
    }}"""


ROUVRIR = {"A": _rouvrir(attendre_close=False), "B": _rouvrir(attendre_close=True)}

# Un bouton touché deux fois dans la même tâche, avant le `popstate` du premier retour : rend le
# nombre de `popstate`, compté jusqu'à `RELIRE_APRES_MS` après le premier.
DEUX_TOUCHERS = f"""async selecteur => {{
    let retours = 0;
    const premier = new Promise(r => addEventListener('popstate', () => {{ retours += 1; r(); }}));
    const bouton = document.querySelector(selecteur);
    bouton.click();
    bouton.click();
    await Promise.race([premier, new Promise(r => setTimeout(r, {GARDE_MS}))]);
    await new Promise(r => setTimeout(r, {RELIRE_APRES_MS}));
    return retours;
}}"""

# « Fermer », puis un onglet touché après l'événement `close`, qui lance le retour, et avant le
# `popstate` de ce retour : rend vrai si ce `popstate` est arrivé.
ONGLET_PENDANT_LA_FERMETURE = f"""async onglet => {{
    const f = document.querySelector('#fenetre');
    const retour = new Promise(r => addEventListener('popstate', () => r(true), {{ once: true }}));
    f.querySelector('form button').click();
    await new Promise(r => f.addEventListener('close', r, {{ once: true }}));
    document.querySelector(`.onglet[data-vue="${{onglet}}"]`).click();
    return Promise.race([retour, new Promise(r => setTimeout(() => r(false), {GARDE_MS}))]);
}}"""

# Chaque appel de `fetch`, noté au moment où il part : un rechargement de la vue appelle l'API
# dans la tâche même du `popstate` qui ferme la fenêtre. La fenêtre vue fermée, la liste est donc
# complète, sans délai à laisser passer.
NOTER_LES_APPELS = """(() => {
    const fetchVrai = window.fetch;
    window.appelsApi = [];
    window.fetch = function (adresse) {
        window.appelsApi.push(String(adresse));
        return fetchVrai.apply(window, arguments);
    };
})();"""

# La seconde fenêtre, ouverte depuis la fiche (réponse 14) : l'offre, le groupe de « Candidatures »
# d'où s'ouvre sa fiche (None : depuis « À faire »), le geste de la fiche, et ce que la fenêtre
# montre ensuite.
SECONDES = {
    "relance": ("envoyee", "envoyee", "relance", "#texte-relance"),
    "canal": ("sans_dossier", "je_postule", "envoyee", "[data-canal]"),
    "non": ("une", None, "non", "#motif-non"),
}


@pytest.fixture(scope="module")
def retour(serveur):
    """Les offres inventées du retour : deux à voir, que les tests ouvrent sans les changer ; une
    à voir, que « Je postule » prépare ; une envoyée et une « Je postule » sans dossier, que montre
    « Candidatures »."""
    une, deux, postuler = _inventer(
        ["Offre inventée du retour, une", "Offre inventée du retour, deux",
         "Offre inventée du retour, à préparer"], "retour/a-voir", "nouveau")
    (envoyee,) = _inventer(["Candidature inventée du retour, envoyée"], "retour/envoyee",
                           "candidature_envoyee")
    (sans_dossier,) = _inventer(["Candidature inventée du retour, sans dossier"],
                                "retour/sans-dossier", "interessante")
    return {"une": une, "deux": deux, "postuler": postuler, "envoyee": envoyee,
            "sans_dossier": sans_dossier}


@pytest.fixture(scope="module")
def a_defiler(serveur):
    """Assez de candidatures envoyées pour que « Candidatures » défile au téléphone."""
    return _inventer([f"Candidature inventée du retour, à défiler {n}"
                      for n in range(1, A_DEFILER + 1)], "retour/defiler", "candidature_envoyee")


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
# Les gestes
# ---------------------------------------------------------------------------


def _depuis_sante(page, url: str) -> None:
    """La console ouverte après `/sante` : le retour qui la quitte y mène."""
    page.goto(f"{url}{SANTE}")
    _ouvrir(page, url)


def _vue(page, nom: str):
    return page.locator(f"#vue-{nom}")


def _fenetre(page):
    return page.locator("#fenetre")


def _fiche(page, offre_id: int):
    return page.locator(f'#fenetre .offre.fiche[data-id="{offre_id}"]')


def _ouvrir_fiche_depuis_a_faire(page, offre_id: int) -> None:
    page.locator(f'#vue-a-faire .carte-a-voir[data-id="{offre_id}"] [data-action="fiche"]').click()
    expect(_fiche(page, offre_id)).to_be_visible()


def _ouvrir_fiche_depuis_candidatures(page, groupe: str, offre_id: int) -> None:
    page.locator('.onglet[data-vue="candidatures"]').click()
    page.locator(f'#vue-candidatures [data-groupe="{groupe}"] '
                 f'button.offre[data-id="{offre_id}"]').click()
    expect(_fiche(page, offre_id)).to_be_visible()


def _sur(page, nom: str) -> None:
    """La vue `nom` montrée, sans fenêtre. La vue d'abord : sur `/sante`, une fenêtre absente
    passerait pour fermée."""
    expect(_vue(page, nom)).to_be_visible()
    expect(_fenetre(page)).to_be_hidden()


def _a_quitte_la_console(page, url: str) -> None:
    expect(page).to_have_url(f"{url}{SANTE}")


def _fermer_puis_attendre_le_retour(page, geste) -> None:
    """`geste` ferme la fenêtre, puis on attend le retour que lance sa fermeture : un `go_back`
    lancé avant lui partirait encore de l'entrée de la fenêtre."""
    page.evaluate(GUETTER_LE_RETOUR)
    geste()
    expect(_fenetre(page)).to_be_hidden()
    assert page.evaluate(RETOUR_VU), "la fermeture de la fenêtre n'a lancé aucun retour"


def _fermer(page) -> None:
    _fenetre(page).get_by_role("button", name="Fermer", exact=True).click()


def _defilement(page) -> int:
    return page.evaluate("() => scrollY")


def _defilement_relu(page) -> int:
    """Le défilement, relu `RELIRE_APRES_MS` plus tard : Chromium l'aurait restauré d'ici là."""
    return page.evaluate("ms => new Promise(r => setTimeout(() => r(scrollY), ms))", RELIRE_APRES_MS)


def _ligne_a_defiler(page, a_defiler: list[int]):
    """La dernière de ces candidatures dans « Candidatures », et son id : `A_DEFILER` lignes au
    moins sous le haut de la vue. La liste s'écrit d'un coup : l'une d'elles là, toutes y sont."""
    envoyees = '#vue-candidatures [data-groupe="envoyee"] button.offre'
    expect(page.locator(f'{envoyees}[data-id="{a_defiler[0]}"]')).to_have_count(1)
    ids = page.locator(envoyees).evaluate_all(
        "bs => bs.map(b => Number(b.dataset.id))")
    derniere = [offre_id for offre_id in ids if offre_id in set(a_defiler)][-1]
    return page.locator(f'#vue-candidatures button.offre[data-id="{derniere}"]'), derniere


def _servir_relance(page, offre_id: int) -> None:
    """Le mot de relance, au corps de la route : ses six clés, que lit `ouvrirRelance`."""
    from veille.relance import Relance

    corps = json.dumps(Relance(texte=TEXTE_RELANCE).as_dict(), ensure_ascii=False)
    page.route(re.compile(rf"/api/offres/{offre_id}/relance$"), lambda route: route.fulfill(
        status=200, content_type="application/json", body=corps))


# ---------------------------------------------------------------------------
# Le retour ferme la fenêtre, quoi qu'elle montre
# ---------------------------------------------------------------------------


def test_le_retour_ferme_la_fiche(telephone, serveur, retour):
    """Le second retour quitte la vue : l'événement `close`, parti après le `popstate`, ne lance
    pas de retour de plus."""
    _depuis_sante(telephone, serveur)
    _ouvrir_fiche_depuis_a_faire(telephone, retour["une"])

    telephone.go_back()
    _sur(telephone, "a-faire")
    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


def test_le_retour_ferme_le_panneau_non(telephone, serveur, retour):
    _depuis_sante(telephone, serveur)
    _ouvrir_fiche_depuis_a_faire(telephone, retour["une"])
    _fiche(telephone, retour["une"]).locator('.ligne-actions [data-action="non"]').click()
    expect(_fenetre(telephone).locator("#motif-non")).to_be_visible()

    telephone.go_back()
    _sur(telephone, "a-faire")
    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


def test_le_retour_ferme_une_etape_de_la_preparation(telephone, serveur, retour):
    offre_id = retour["postuler"]
    _simuler_preparation(telephone, offre_id, [_etape("texte", message=RAISON_TEXTE, url=ANNONCE)])
    _depuis_sante(telephone, serveur)
    _ouvrir_fiche_depuis_a_faire(telephone, offre_id)
    _fiche(telephone, offre_id).locator('.ligne-actions [data-action="postuler"]').click()
    expect(_fenetre(telephone).locator("h2")).to_have_text("Il manque le texte de l'annonce")

    telephone.go_back()
    _sur(telephone, "a-faire")
    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


@pytest.mark.parametrize("seconde", list(SECONDES))
def test_une_fenetre_ouverte_depuis_la_fiche_ne_pousse_rien(telephone, serveur, retour, seconde):
    """Réponse 14 : la fiche pousse une entrée, la fenêtre qu'elle ouvre n'en pousse pas. Une
    entrée de trop laisserait la vue de la fiche au premier retour. Seule une fermeture qui ne
    traverse pas l'historique la laisse voir, « Fermer » ici : sous un `go_back`, le `close` qui
    suit l'absorberait (« Outils et cas limites », `showModal()`)."""
    cle, groupe, action, montre = SECONDES[seconde]
    offre_id = retour[cle]
    if seconde == "relance":
        _servir_relance(telephone, offre_id)
    _depuis_sante(telephone, serveur)
    if groupe:
        _ouvrir_fiche_depuis_candidatures(telephone, groupe, offre_id)
    else:
        _ouvrir_fiche_depuis_a_faire(telephone, offre_id)
    _fiche(telephone, offre_id).locator(f'.ligne-actions [data-action="{action}"]').click()
    expect(_fenetre(telephone).locator(montre).first).to_be_visible()
    if seconde == "relance":
        expect(_fenetre(telephone).locator(montre)).to_have_value(TEXTE_RELANCE)
    elif seconde == "canal":
        expect(_fenetre(telephone).locator(montre)).to_have_count(6)

    _fermer_puis_attendre_le_retour(telephone, lambda: _fermer(telephone))
    telephone.go_back()
    if groupe:
        # La vue d'avant celle de la fiche : « À faire », sous « Candidatures ».
        _sur(telephone, "a-faire")
        telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


# ---------------------------------------------------------------------------
# Sans fenêtre, le retour revient à la vue d'avant ; depuis « À faire », il quitte la console
# ---------------------------------------------------------------------------


def test_le_retour_revient_a_la_vue_d_avant(telephone, serveur):
    _depuis_sante(telephone, serveur)
    telephone.locator('.onglet[data-vue="plus"]').click()
    expect(_vue(telephone, "plus")).to_be_visible()
    telephone.locator('.lien-plus[data-vue="bilan"]').click()
    expect(_vue(telephone, "bilan")).to_be_visible()

    telephone.go_back()
    _sur(telephone, "plus")
    telephone.go_back()
    _sur(telephone, "a-faire")
    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


def test_le_retour_depuis_a_faire_quitte_la_console(telephone, serveur):
    _depuis_sante(telephone, serveur)
    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


def test_l_onglet_a_faire_revient_a_la_racine(telephone, serveur):
    """L'onglet « À faire » revient à la première entrée : le retour depuis lui quitte la console,
    quel que soit le chemin pris avant."""
    _depuis_sante(telephone, serveur)
    telephone.locator('.onglet[data-vue="candidatures"]').click()
    expect(_vue(telephone, "candidatures")).to_be_visible()
    telephone.locator('.onglet[data-vue="plus"]').click()
    expect(_vue(telephone, "plus")).to_be_visible()
    telephone.locator('.lien-plus[data-vue="offres"]:not([data-chercher])').click()
    expect(_vue(telephone, "offres")).to_be_visible()
    telephone.locator('.onglet[data-vue="a-faire"]').click()
    _sur(telephone, "a-faire")

    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


def test_chercher_une_offre_revenue_par_le_retour_garde_le_curseur(telephone, serveur):
    """« Chercher une offre » depuis « Plus » ouvert sur Toutes les offres : la vue d'avant se
    rejoint par le retour, sans entrée de plus, et le curseur est dans la recherche (décision 5)."""
    telephone.goto(f"{serveur}/?filtre=interessante")
    expect(_vue(telephone, "offres")).to_be_visible()
    telephone.locator("#vue-offres .retour-plus").click()
    expect(_vue(telephone, "plus")).to_be_visible()
    telephone.get_by_role("button", name="Chercher une offre").click()
    expect(_vue(telephone, "offres")).to_be_visible()
    expect(telephone.locator("#f-recherche")).to_be_focused()

    telephone.go_back()
    _sur(telephone, "a-faire")


# ---------------------------------------------------------------------------
# Le défilement : la vue revenue s'ouvre en haut, celle sous une fenêtre ne bouge pas
# ---------------------------------------------------------------------------


def test_une_vue_revenue_par_le_retour_s_ouvre_en_haut(telephone, serveur, a_defiler):
    """Décision 15 : revenue par le retour, une vue se recharge et s'ouvre en haut, comme par son
    onglet. Chromium restaurerait le défilement de son entrée à la première image après le
    `popstate`, par-dessus le `scrollTo(0, 0)` d'`afficherVue`."""
    _ouvrir(telephone, serveur)
    telephone.locator('.onglet[data-vue="candidatures"]').click()
    expect(_ligne_a_defiler(telephone, a_defiler)[0]).to_be_visible()
    telephone.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
    assert _defilement(telephone) > 500
    telephone.locator('.onglet[data-vue="plus"]').click()
    _sur(telephone, "plus")
    # Les listes d'avant, marquées : la vue rechargée les remplace.
    telephone.evaluate("""() => document.querySelectorAll('#contenu-candidatures .liste')
                                 .forEach(l => { l.dataset.ancienne = '1'; })""")

    telephone.go_back()
    _sur(telephone, "candidatures")
    expect(telephone.locator("#contenu-candidatures .liste").first).to_be_visible()
    expect(telephone.locator("#contenu-candidatures [data-ancienne]")).to_have_count(0)
    assert _defilement(telephone) == 0
    assert _defilement_relu(telephone) == 0


def test_la_vue_sous_une_fenetre_fermee_par_le_retour_garde_son_defilement(telephone, serveur,
                                                                          a_defiler):
    """La fiche ouverte au bas de « Candidatures » : le retour la ferme, et la vue reste où elle
    était, sans se recharger ni remonter."""
    _ouvrir(telephone, serveur)
    telephone.locator('.onglet[data-vue="candidatures"]').click()
    ligne, offre_id = _ligne_a_defiler(telephone, a_defiler)
    ligne.click()
    expect(_fiche(telephone, offre_id)).to_be_visible()
    avant = _defilement(telephone)
    assert avant > 500

    telephone.go_back()
    _sur(telephone, "candidatures")
    assert _defilement(telephone) == avant
    assert _defilement_relu(telephone) == avant


# ---------------------------------------------------------------------------
# Un seul retour à la fois
# ---------------------------------------------------------------------------


def test_deux_touchers_sur_plus_ne_reculent_que_d_une_vue(telephone, serveur):
    """« ‹ Plus » rejoint la vue d'avant par un retour, qui arrive un instant plus tard. Touché deux
    fois d'ici là, il en lancerait deux, et dépasserait « Plus » : Chromium compte le second depuis
    l'entrée où mène le premier."""
    _depuis_sante(telephone, serveur)
    telephone.locator('.onglet[data-vue="plus"]').click()
    telephone.locator('.lien-plus[data-vue="bilan"]').click()
    expect(_vue(telephone, "bilan")).to_be_visible()

    assert telephone.evaluate(DEUX_TOUCHERS, "#vue-bilan .retour-plus") == 1
    _sur(telephone, "plus")
    telephone.go_back()
    _sur(telephone, "a-faire")
    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


def test_un_onglet_touche_pendant_le_retour_de_la_fermeture_attend(telephone, serveur, retour):
    """« Fermer » lance un retour, qui retire l'entrée de la fenêtre. Un onglet touché avant qu'il
    n'arrive pousserait sa vue au-dessus de cette entrée, que le retour reprendrait : la console
    montrerait une vue sous l'entrée d'une autre. Le toucher attend : il ne fait rien."""
    _depuis_sante(telephone, serveur)
    _ouvrir_fiche_depuis_a_faire(telephone, retour["une"])

    assert telephone.evaluate(ONGLET_PENDANT_LA_FERMETURE, "candidatures")
    _sur(telephone, "a-faire")
    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


def test_un_retour_qui_ne_mene_nulle_part_ne_fige_pas_les_onglets(telephone, serveur):
    """Un retour sans entrée à ce pas ne donne aucun `popstate` : la première entrée oubliée
    (Chrome ne garde qu'une cinquantaine d'entrées), l'onglet « À faire » ne mène nulle part. Le
    retour en cours n'attend pas sans fin : les onglets répondent de nouveau."""
    _ouvrir(telephone, serveur)
    telephone.locator('.onglet[data-vue="candidatures"]').click()
    _sur(telephone, "candidatures")
    # Une profondeur plus grande que l'historique : la première entrée n'y est plus.
    telephone.evaluate("() => history.replaceState({ ...history.state, profondeur: 99 }, '')")
    telephone.locator('.onglet[data-vue="a-faire"]').click()
    telephone.wait_for_function("() => !retourEnCours", timeout=GARDE_MS)

    telephone.locator('.onglet[data-vue="plus"]').click()
    _sur(telephone, "plus")


# ---------------------------------------------------------------------------
# La fenêtre fermée sans traverser l'historique retire son entrée (point d'attention 1)
# ---------------------------------------------------------------------------


def test_fermer_la_fenetre_retire_son_entree(telephone, serveur, retour):
    _ouvrir(telephone, serveur)
    _ouvrir_fiche_depuis_candidatures(telephone, "envoyee", retour["envoyee"])
    _fermer_puis_attendre_le_retour(telephone, lambda: _fermer(telephone))

    telephone.go_back()
    _sur(telephone, "a-faire")


def test_echap_ferme_la_fenetre_et_retire_son_entree(telephone, serveur, retour):
    """Échap ferme la fenêtre comme le retour d'Android quand Chrome la ferme lui-même : par
    `cancel` puis `close`, sans traverser l'historique. Une entrée laissée par la fenêtre
    laisserait « Candidatures » au retour."""
    _ouvrir(telephone, serveur)
    _ouvrir_fiche_depuis_candidatures(telephone, "envoyee", retour["envoyee"])
    _fermer_puis_attendre_le_retour(telephone, lambda: telephone.keyboard.press("Escape"))

    telephone.go_back()
    _sur(telephone, "a-faire")


@pytest.mark.parametrize("ordre", ["A", "B", "C"])
def test_une_fenetre_rouverte_aussitot_se_ferme_au_retour(telephone, serveur, retour, ordre):
    """La fenêtre fermée, puis rouverte avant que le retour lancé par sa fermeture n'arrive (A, B),
    ou après (C). En B, sans remède, le retour atterrit sur l'entrée de la vue, la fenêtre ouverte,
    et le retour suivant quitterait la console."""
    _depuis_sante(telephone, serveur)
    _ouvrir_fiche_depuis_a_faire(telephone, retour["une"])
    if ordre == "C":
        _fermer_puis_attendre_le_retour(telephone, lambda: _fermer(telephone))
        _ouvrir_fiche_depuis_a_faire(telephone, retour["deux"])
    else:
        assert telephone.evaluate(ROUVRIR[ordre]) == {"avant": True, "vu": True}
    expect(_fenetre(telephone)).to_be_visible()

    telephone.go_back()
    _sur(telephone, "a-faire")
    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


# ---------------------------------------------------------------------------
# Les entrées dans la console : un lien d'entrée, un rechargement
# ---------------------------------------------------------------------------


def test_un_lien_d_entree_vers_toutes_les_offres_revient_a_a_faire(telephone, serveur):
    """Point d'attention 4 : Toutes les offres est posée au-dessus d'« À faire », et l'adresse
    redevient `/`. Playwright ne saute aucune entrée : ce que fait Chrome au téléphone, qui peut
    sauter « À faire », se vérifie au staging (réponse 15)."""
    telephone.goto(f"{serveur}/?filtre=interessante")
    _sur(telephone, "offres")
    expect(telephone).to_have_url(f"{serveur}/")

    telephone.go_back()
    _sur(telephone, "a-faire")
    expect(telephone.locator("#contenu-a-faire")).not_to_be_empty()


def test_un_rechargement_garde_la_vue(telephone, serveur):
    _ouvrir(telephone, serveur)
    telephone.locator('.onglet[data-vue="plus"]').click()
    telephone.locator('.lien-plus[data-vue="bilan"]').click()
    expect(telephone.locator("#contenu-bilan details[data-liste]").first).to_be_visible()

    telephone.reload()
    _sur(telephone, "bilan")
    expect(telephone.locator("#contenu-bilan details[data-liste]").first).to_be_visible()
    telephone.go_back()
    _sur(telephone, "plus")


def test_un_rechargement_fenetre_ouverte_ne_laisse_pas_d_entree_morte(telephone, serveur, retour):
    """Rechargée la fenêtre ouverte, la page montre la vue sans fenêtre, puis retire l'entrée de la
    fenêtre par un retour, qu'on attend : aucun retour ne tombe ensuite dans le vide."""
    _depuis_sante(telephone, serveur)
    _ouvrir_fiche_depuis_candidatures(telephone, "envoyee", retour["envoyee"])

    telephone.reload()
    _sur(telephone, "candidatures")
    telephone.wait_for_function("() => history.state !== null && !history.state.fenetre",
                                timeout=GARDE_MS)
    telephone.go_back()
    _sur(telephone, "a-faire")
    telephone.go_back()
    _a_quitte_la_console(telephone, serveur)


def test_une_vue_inconnue_au_rechargement_montre_a_faire(telephone, serveur):
    """Une entrée laissée par une version d'avant, dont la vue aurait changé de nom : le
    rechargement montre « À faire », chargée, plutôt qu'une console vide."""
    _ouvrir(telephone, serveur)
    telephone.evaluate("""() => history.replaceState(
        { vue: 'vue-inconnue', precedente: null, profondeur: 0 }, '', '/')""")

    telephone.reload()
    _sur(telephone, "a-faire")
    expect(telephone.locator("#contenu-a-faire")).not_to_be_empty()
    expect(telephone.locator(".onglet.actif")).to_have_attribute("data-vue", "a-faire")


def test_la_vue_sous_une_fenetre_fermee_ne_se_recharge_pas(telephone, serveur, retour):
    """Le retour ferme la fiche ouverte depuis « À faire » : « À faire » reste telle quelle, sans
    nouvel appel à `/api/a-faire`."""
    telephone.add_init_script(NOTER_LES_APPELS)
    _ouvrir(telephone, serveur)
    _ouvrir_fiche_depuis_a_faire(telephone, retour["une"])
    telephone.evaluate("() => { window.appelsApi.length = 0; }")

    telephone.go_back()
    _sur(telephone, "a-faire")
    appels = telephone.evaluate("() => window.appelsApi")
    assert [a for a in appels if urlsplit(a).path == "/api/a-faire"] == []
