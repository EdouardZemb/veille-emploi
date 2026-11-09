"""Le parcours complet : enregistrer, quitter, se reconnecter, ajouter un appareil."""

from __future__ import annotations

from .conftest import appareil


def test_parcours_complet(serveur, navigateur):
    from veille import auth, db

    url = serveur
    page = appareil(navigateur)
    # La CSP ne bloque rien : le navigateur ecrit chaque violation dans la console.
    messages: list[str] = []
    page.on("console", lambda m: messages.append(m.text))
    page.on("pageerror", lambda e: messages.append(str(e)))

    # 1. Le lien du serveur enregistre la premiere passkey.
    page.goto(f"{url}/lien#{auth.creer_lien('serveur')}")
    page.click("#btn-enregistrer")
    page.wait_for_url(f"{url}/")

    # 2. On quitte, puis la passkey rouvre la console.
    page.click("form[action='/deconnexion'] button")
    page.wait_for_url(f"{url}/connexion")
    page.click("#btn-passkey")
    page.wait_for_url(f"{url}/")

    # 3. Les Reglages montrent la passkey, puis on cree un lien pour un second appareil.
    page.click('button.onglet[data-vue="plus"]')
    page.click('button.lien-plus[data-vue="reglages"]')
    page.wait_for_selector("#liste-passkeys .ligne-passkey")
    assert page.locator("#liste-passkeys .ligne-passkey").count() == 1
    # Pas de feuille de partage : on veut le champ en lecture seule.
    page.evaluate(
        "() => { delete navigator.share; "
        "Object.defineProperty(navigator, 'share', {value: undefined, configurable: true}); }"
    )
    # Le bouton demande une nouvelle touche : l'authentificateur virtuel la donne.
    page.click("#btn-ajouter-appareil")
    page.wait_for_selector("#adresse-lien")
    adresse = page.input_value("#adresse-lien")
    assert "/lien#" in adresse

    # 4. Le second appareil, avec son propre authentificateur, s'enregistre.
    second = appareil(navigateur)
    second.goto(adresse)
    second.click("#btn-enregistrer")
    second.wait_for_url(f"{url}/")

    assert db.compter_passkeys() == 2
    # Le parcours a charge /lien, /, puis /connexion apres la deconnexion.
    violations = [m for m in messages if "Content Security Policy" in m]
    assert violations == []


def test_une_passkey_deja_sur_l_appareil_renvoie_a_la_connexion(serveur, navigateur):
    """Un second lien ouvert sur un appareil qui a deja sa passkey : `create()`
    leve `InvalidStateError` (excludeCredentials), la page renvoie a /connexion."""
    from veille import auth

    url = serveur
    page = appareil(navigateur)
    page.goto(f"{url}/lien#{auth.creer_lien('serveur')}")
    page.click("#btn-enregistrer")
    page.wait_for_url(f"{url}/")

    page.goto(f"{url}/lien#{auth.creer_lien('serveur')}")
    page.click("#btn-enregistrer")
    message = page.locator("#message")
    message.wait_for(state="visible")
    assert ("Cet appareil a déjà une passkey. "
            "Connecte-toi depuis la page de connexion.") in message.inner_text()
    assert message.locator("a[href='/connexion']").count() == 1
