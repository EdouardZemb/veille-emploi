"""Les passkeys : les ceremonies WebAuthn, eprouvees par un authentificateur logiciel."""

from __future__ import annotations

import logging

import pytest

from tests.authentificateur import AuthentificateurLogiciel, b64url
from veille import auth, db, passkeys

ORIGINE = "http://localhost:8460"


@pytest.fixture(autouse=True)
def _ceremonies(monkeypatch):
    monkeypatch.setenv("VEILLE_URL", ORIGINE)
    db.initialiser()
    # La base sert a toute la suite : chaque test part sans passkey.
    with db.connexion() as cx:
        cx.execute("DELETE FROM passkeys")
    passkeys.oublier_ceremonies()
    yield
    passkeys.oublier_ceremonies()


def inscrire_une_passkey(auth_logiciel: AuthentificateurLogiciel) -> int:
    lien = auth.lien_ouvert(auth.creer_lien("serveur"))
    cle, options = passkeys.options_inscription(lien)
    inscription = passkeys.verifier_inscription(cle, auth_logiciel.inscrire(options, ORIGINE))
    assert inscription.lien_id == lien
    return db.enregistrer_passkey(inscription.identifiant, inscription.cle_publique,
                                  inscription.compteur, inscription.transports, "Android",
                                  auth._iso(auth.maintenant()))


def se_connecter(auth_logiciel: AuthentificateurLogiciel) -> int:
    cle, options = passkeys.options_connexion()
    return passkeys.verifier_connexion(cle, auth_logiciel.signer(options, ORIGINE))


@pytest.mark.parametrize("url, attendu", [
    ("https://console.exemple.invalid:8443/",
     ("https://console.exemple.invalid:8443", "console.exemple.invalid")),
    ("https://app.exemple.invalid/chemin",
     ("https://app.exemple.invalid", "app.exemple.invalid")),
    ("http://localhost:8460", ("http://localhost:8460", "localhost")),
])
def test_origine_depuis_veille_url(monkeypatch, url, attendu):
    monkeypatch.setenv("VEILLE_URL", url)
    assert passkeys.origine_attendue() == attendu


@pytest.mark.parametrize("valeur", [None, "", "pas-une-adresse", "http://localhost:port"])
def test_sans_veille_url_les_passkeys_sont_indisponibles(monkeypatch, valeur):
    if valeur is None:
        monkeypatch.delenv("VEILLE_URL", raising=False)
    else:
        monkeypatch.setenv("VEILLE_URL", valeur)
    with pytest.raises(passkeys.OrigineInconnue):
        passkeys.options_connexion()
    with pytest.raises(passkeys.OrigineInconnue):
        passkeys.options_inscription(lien_id=1)


def test_les_options_d_inscription():
    _, options = passkeys.options_inscription(lien_id=1)
    assert options["rp"] == {"id": "localhost", "name": "Veille emploi"}
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "preferred"
    assert options["user"]["name"] == "edouard"
    assert options["user"]["id"] == b64url(b"edouard")


def test_inscription_puis_connexion():
    cle_logicielle = AuthentificateurLogiciel()
    passkey = inscrire_une_passkey(cle_logicielle)
    cle, options = passkeys.options_connexion()
    reponse = cle_logicielle.signer(options, "http://localhost:8460")
    assert passkeys.verifier_connexion(cle, reponse) == passkey
    ligne = db.passkey_par_identifiant(reponse["id"])
    assert ligne["compteur"] == 1
    assert ligne["utilisee_le"] is not None
    assert ligne["transports"] == ["internal"]
    assert db.compter_passkeys() == 1


def test_les_options_d_inscription_excluent_les_passkeys_connues():
    inscrire_une_passkey(AuthentificateurLogiciel())
    _, options = passkeys.options_inscription(lien_id=2)
    assert len(options["excludeCredentials"]) == 1
    assert options["excludeCredentials"][0]["id"] == db.identifiants_passkeys()[0]


def test_une_ceremonie_ne_sert_qu_une_fois():
    cle_logicielle = AuthentificateurLogiciel()
    inscrire_une_passkey(cle_logicielle)
    cle, options = passkeys.options_connexion()
    passkeys.verifier_connexion(cle, cle_logicielle.signer(options, ORIGINE))
    with pytest.raises(passkeys.CeremonieInvalide):
        passkeys.verifier_connexion(cle, cle_logicielle.signer(options, ORIGINE))


def test_une_ceremonie_expire_apres_5_minutes(horloge):
    cle_logicielle = AuthentificateurLogiciel()
    inscrire_une_passkey(cle_logicielle)
    cle_tot, options_tot = passkeys.options_connexion()
    cle_tard, options_tard = passkeys.options_connexion()
    horloge.avancer(minutes=4)
    passkeys.verifier_connexion(cle_tot, cle_logicielle.signer(options_tot, ORIGINE))
    horloge.avancer(minutes=2)
    with pytest.raises(passkeys.CeremonieInvalide):
        passkeys.verifier_connexion(cle_tard, cle_logicielle.signer(options_tard, ORIGINE))


def test_une_autre_origine_est_refusee():
    lien = auth.lien_ouvert(auth.creer_lien("serveur"))
    cle, options = passkeys.options_inscription(lien)
    reponse = AuthentificateurLogiciel().inscrire(options, "https://ailleurs.example")
    with pytest.raises(passkeys.CeremonieInvalide):
        passkeys.verifier_inscription(cle, reponse)


def test_une_passkey_inconnue_est_refusee():
    inscrire_une_passkey(AuthentificateurLogiciel())
    cle, options = passkeys.options_connexion()
    with pytest.raises(passkeys.CeremonieInvalide):
        passkeys.verifier_connexion(cle, AuthentificateurLogiciel().signer(options, ORIGINE))


def test_une_autre_cle_sous_l_identifiant_d_une_passkey_connue_est_refusee():
    """L'identifiant se lit dans la reponse : il ne prouve rien, la signature si."""
    connue = AuthentificateurLogiciel()
    inscrire_une_passkey(connue)
    usurpatrice = AuthentificateurLogiciel()
    usurpatrice.identifiant = connue.identifiant
    cle, options = passkeys.options_connexion()
    reponse = usurpatrice.signer(options, ORIGINE)
    assert db.passkey_par_identifiant(reponse["id"]) is not None
    with pytest.raises(passkeys.CeremonieInvalide):
        passkeys.verifier_connexion(cle, reponse)
    # La vraie cle, sous le meme identifiant, passe toujours.
    assert se_connecter(connue)


def test_une_cle_clonee_est_refusee():
    cle_logicielle = AuthentificateurLogiciel()
    inscrire_une_passkey(cle_logicielle)
    se_connecter(cle_logicielle)
    se_connecter(cle_logicielle)
    cle_logicielle.compteur = 1
    with pytest.raises(passkeys.CeremonieInvalide):
        se_connecter(cle_logicielle)


def test_le_compteur_s_ecrit_une_seule_fois(monkeypatch):
    """Deux verifications sur la meme lecture du compteur : la seconde est refusee."""
    cle_logicielle = AuthentificateurLogiciel()
    passkey_id = inscrire_une_passkey(cle_logicielle)
    lue = db.passkey_par_identifiant(b64url(cle_logicielle.identifiant))
    assert lue["compteur"] == 0
    assert se_connecter(cle_logicielle) == passkey_id
    # La seconde verification a lu la ligne avant la premiere ecriture.
    monkeypatch.setattr(passkeys.db, "passkey_par_identifiant", lambda _identifiant: dict(lue))
    with pytest.raises(passkeys.CeremonieInvalide):
        se_connecter(cle_logicielle)
    monkeypatch.undo()  # le meme module `db` : la lecture suivante doit etre la vraie
    assert db.passkey_par_identifiant(b64url(cle_logicielle.identifiant))["compteur"] == 1


def test_un_compteur_qui_reste_a_zero_n_empeche_pas_de_se_connecter():
    """Les passkeys synchronisees (Google, Apple) annoncent toujours 0."""
    cle_logicielle = AuthentificateurLogiciel()
    passkey_id = inscrire_une_passkey(cle_logicielle)
    for _ in range(2):
        cle_logicielle.compteur = -1  # signer() l'incremente : la reponse porte 0
        assert se_connecter(cle_logicielle) == passkey_id


def test_une_ceremonie_d_inscription_ne_sert_pas_a_la_connexion():
    cle_logicielle = AuthentificateurLogiciel()
    inscrire_une_passkey(cle_logicielle)
    cle, options = passkeys.options_inscription(lien_id=1)
    # Le bon defi et le bon rp_id : seul le but de la ceremonie est faux.
    reponse = cle_logicielle.signer({"challenge": options["challenge"], "rpId": "localhost"},
                                    ORIGINE)
    with pytest.raises(passkeys.CeremonieInvalide):
        passkeys.verifier_connexion(cle, reponse)


def _sans(dictionnaire: dict, cle: str) -> dict:
    return {k: v for k, v in dictionnaire.items() if k != cle}


@pytest.mark.parametrize("abimer", [
    lambda r: [],
    lambda r: {},
    lambda r: {**r, "id": 42},
    lambda r: {**r, "response": "texte"},
    lambda r: {**r, "response": _sans(r["response"], "signature")},
    lambda r: {**r, "response": {**r["response"], "userHandle": "A"}},
    lambda r: {**r, "response": {**r["response"], "authenticatorData": "A"}},
])
def test_une_reponse_de_connexion_mal_formee_est_refusee(abimer):
    cle_logicielle = AuthentificateurLogiciel()
    inscrire_une_passkey(cle_logicielle)
    cle, options = passkeys.options_connexion()
    with pytest.raises(passkeys.CeremonieInvalide):
        passkeys.verifier_connexion(cle, abimer(cle_logicielle.signer(options, ORIGINE)))


@pytest.mark.parametrize("abimer", [
    lambda r: [],
    lambda r: {},
    lambda r: {**r, "response": _sans(r["response"], "attestationObject")},
    lambda r: {**r, "response": {**r["response"], "attestationObject": "A"}},
])
def test_une_reponse_d_inscription_mal_formee_est_refusee(abimer):
    cle, options = passkeys.options_inscription(lien_id=1)
    with pytest.raises(passkeys.CeremonieInvalide):
        passkeys.verifier_inscription(cle, abimer(AuthentificateurLogiciel().inscrire(options,
                                                                                      ORIGINE)))


def test_un_refus_va_au_journal_tronque_sans_cle_ni_identifiant(caplog):
    cle_logicielle = AuthentificateurLogiciel()
    inscrire_une_passkey(cle_logicielle)
    cle, options = passkeys.options_connexion()
    reponse = cle_logicielle.signer(options, "https://ailleurs.example/" + "x" * 500)
    with caplog.at_level(logging.WARNING, logger="veille.passkeys"):
        with pytest.raises(passkeys.CeremonieInvalide):
            passkeys.verifier_connexion(cle, reponse)
    messages = [r.getMessage() for r in caplog.records if r.name == "veille.passkeys"]
    assert messages
    for message in messages:
        assert len(message) <= 200
        assert cle not in message
        assert reponse["id"] not in message


@pytest.mark.parametrize("url, attendu", [
    ("https://Console.Exemple.invalid:443/chemin?q=1",
     ("https://console.exemple.invalid", "console.exemple.invalid")),
    ("http://hote.invalid:80", ("http://hote.invalid", "hote.invalid")),
    ("http://hote.invalid:8460/", ("http://hote.invalid:8460", "hote.invalid")),
])
def test_origine_normalisee(monkeypatch, url, attendu):
    monkeypatch.delenv("VEILLE_EMPLOI_URL_PUBLIQUE", raising=False)
    monkeypatch.setenv("VEILLE_URL", url)
    assert passkeys.origine_attendue() == attendu


@pytest.mark.parametrize("url", [
    "ftp://hote.invalid", "https://moi@hote.invalid", "hote.invalid", "https://",
])
def test_origine_refusee(monkeypatch, url):
    monkeypatch.delenv("VEILLE_EMPLOI_URL_PUBLIQUE", raising=False)
    monkeypatch.setenv("VEILLE_URL", url)
    with pytest.raises(passkeys.OrigineInconnue):
        passkeys.origine_attendue()


def test_l_url_publique_l_emporte(monkeypatch):
    monkeypatch.setenv("VEILLE_URL", "http://autre.invalid")
    monkeypatch.setenv("VEILLE_EMPLOI_URL_PUBLIQUE", "https://public.invalid")
    assert passkeys.origine_attendue() == ("https://public.invalid", "public.invalid")
    monkeypatch.setenv("VEILLE_EMPLOI_URL_PUBLIQUE", "")
    assert passkeys.origine_attendue() == ("http://autre.invalid", "autre.invalid")
