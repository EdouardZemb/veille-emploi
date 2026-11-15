"""Au téléphone, chaque cible se touche du doigt, et les onglets restent visibles.

Les mesures se font dans Chromium, à la taille d'un téléphone : seules les règles
`@media (max-width:640px)` de `style.css` disent ce que voit la console installée.
La session est ouverte par `auth.ouvrir_session`, sans passkey : le parcours de
connexion compte les passkeys de la base, partagée par toute la session de tests.
"""

from __future__ import annotations

import pytest

TELEPHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}
# La cible tactile minimale, en pixels CSS.
DOIGT = 44


@pytest.fixture(scope="module")
def offres(serveur):
    """Douze offres inventées : assez pour faire défiler la liste. Les critères de
    l'exemple les écartent ; on les remet dans le flux, comme le ferait Edouard."""
    from veille import db
    from veille.collectors.base import ingerer
    from veille.models import Offre

    ingerer(
        [
            Offre(
                titre=f"Ingénieur qualité logicielle confirmé, poste inventé {n}",
                employeur="Employeur inventé",
                lieu="Lieu inventé",
                description="Tests automatisés et qualité logicielle.",
                url=f"https://exemple.invalid/offre/{n}",
            )
            for n in range(1, 13)
        ],
        "essai",
    )
    with db.connexion() as cx:
        ids = [r["id"] for r in cx.execute("SELECT id FROM offres WHERE source = 'essai'")]
    for offre_id in ids:
        db.changer_statut(offre_id, "interessante")
    return serveur


@pytest.fixture
def telephone(navigateur, offres):
    from veille import auth

    contexte = navigateur.new_context(**TELEPHONE)
    contexte.add_cookies([{"name": auth.nom_cookie(),
                           "value": auth.ouvrir_session("Téléphone"), "url": offres}])
    page = contexte.new_page()
    erreurs: list[str] = []
    page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.goto(f"{offres}/")
    # La console s'ouvre sur « À faire » : la liste des offres est sous « Plus ».
    page.click('.onglet[data-vue="plus"]')
    page.click('.lien-plus[data-vue="offres"]:not([data-chercher])')
    page.wait_for_selector("#liste-offres .ligne-offre")
    yield page
    assert erreurs == []
    contexte.close()


def _boite(page, selecteur: str) -> dict:
    return page.eval_on_selector(selecteur, "e => e.getBoundingClientRect().toJSON()")


def test_les_onglets_ne_glissent_pas_sous_la_barre(telephone):
    """Une fois la page défilée, les onglets restent entiers, juste sous la barre."""
    telephone.evaluate("window.scrollTo(0, 800)")
    barre = _boite(telephone, ".barre")
    onglets = _boite(telephone, ".onglets")
    assert telephone.evaluate("window.scrollY") > 0
    assert abs(onglets["top"] - barre["bottom"]) < 1


def test_les_lignes_des_offres_se_touchent_du_doigt(telephone):
    # `#liste-offres` : les lignes du Bilan, cachées, mesureraient 0 px.
    hauteurs = telephone.eval_on_selector_all(
        "#liste-offres .ligne-offre",
        "bs => bs.map(b => b.getBoundingClientRect().height)")
    assert hauteurs
    assert min(hauteurs) >= DOIGT


def test_les_boutons_de_la_barre_se_touchent_du_doigt(telephone):
    for selecteur in ("#btn-push", "form[action='/deconnexion'] button"):
        assert _boite(telephone, selecteur)["height"] >= DOIGT, selecteur


def test_les_filtres_se_touchent_du_doigt(telephone):
    """Les trois champs de Toutes les offres, et la bascule de l'atout mis en avant."""
    for selecteur in ("#f-recherche", "#f-etat", "#f-famille", "#btn-atout"):
        assert _boite(telephone, selecteur)["height"] >= DOIGT, selecteur


def test_les_filtres_tiennent_dans_l_ecran(telephone):
    """La famille au libellé le plus long, choisie, ne fait pas défiler la page de côté : un
    sélecteur ne descendait pas sous la largeur de sa plus longue option. Les libellés de
    l'exemple tiennent dans l'écran ; ceux d'une instance, non lus ici, peuvent ne pas tenir :
    une famille inventée, plus large que l'écran, en tient lieu."""
    telephone.eval_on_selector("#f-famille", """s => s.add(new Option(
        'Famille inventée au libellé bien plus large que l’écran du téléphone, sans fin', 'inventee'))""")
    valeur = telephone.eval_on_selector("#f-famille", """s => [...s.options].reduce(
        (a, o) => (o.textContent.trim().length > a.textContent.trim().length ? o : a)).value""")
    assert valeur == "inventee"
    telephone.select_option("#f-famille", valeur)
    largeur = telephone.evaluate("document.documentElement.scrollWidth")
    assert largeur <= TELEPHONE["viewport"]["width"]


def test_un_lien_de_telechargement_se_touche_du_doigt(telephone):
    """La ligne d'un fichier, telle que `ligneFichier` la construit (Documents)."""
    telephone.evaluate("""() => {
        const ul = document.createElement('ul');
        ul.className = 'fichiers';
        ul.innerHTML = '<li class="fichier"><a href="#" download>cv.pdf</a>'
          + '<span class="menu">12 Ko · 01/11/2026</span></li>';
        document.querySelector('#vue-offres').prepend(ul);
    }""")
    assert _boite(telephone, ".fichier a")["height"] >= DOIGT


def test_les_compteurs_et_les_titres_ont_leurs_finitions(telephone):
    """Des chiffres de largeur égale dans les compteurs ; des titres équilibrés."""
    style = "([s, p]) => getComputedStyle(document.querySelector(s))[p]"
    assert "tabular-nums" in telephone.evaluate(style, ["#pastille-plus", "fontVariantNumeric"])
    assert "balance" in telephone.evaluate(style, [".offre-titre", "textWrap"])
    assert "pretty" in telephone.evaluate(style, ["#resume-offres", "textWrap"])


def test_un_message_s_efface_avant_de_partir(telephone):
    """Le message prend la classe `sortie`, qui l'efface, puis quitte la page. Un
    observateur note chaque étape : l'attente de Playwright raterait les 150 ms."""
    telephone.evaluate("""() => {
        window.etapes = [];
        new MutationObserver(ms => ms.forEach(m => {
            if (m.type === 'attributes') window.etapes.push([m.target.className, performance.now()]);
            m.removedNodes.forEach(n => window.etapes.push(['retiré', performance.now()]));
        })).observe(document.querySelector('#messages'),
                    {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});
        message('Essai inventé');
    }""")
    telephone.wait_for_selector(".message", state="detached", timeout=6000)
    etapes = telephone.evaluate("window.etapes")
    assert [nom for nom, _ in etapes] == ["message sortie", "retiré"]
    assert etapes[1][1] - etapes[0][1] >= 100
