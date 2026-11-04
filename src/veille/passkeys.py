"""Les passkeys : les ceremonies WebAuthn d'inscription et de connexion.

POURQUOI : une passkey ne se devine pas, ne se reutilise pas d'un site a
l'autre et ne passe jamais par la conversation ni par un journal. Voir
docs/decisions/0001-connexion-par-passkeys.md.

Mecanique : chaque ceremonie tire un defi, garde en memoire (un seul
processus uvicorn) sous une cle aleatoire, 5 minutes, pour un seul usage.
L'origine et l'identifiant de la partie de confiance viennent de
`VEILLE_URL`, lue a chaque appel : sans elle, les passkeys sont
indisponibles, jamais devinees.

Tout refus devient `CeremonieInvalide` et va au journal, tronque, sans cle de
ceremonie ni identifiant de passkey.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import webauthn
from webauthn.helpers import bytes_to_base64url, parse_registration_credential_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from . import auth, db

log = logging.getLogger(__name__)

NOM_DU_SITE = "Veille emploi"
IDENTIFIANT_UTILISATEUR = b"edouard"
NOM_UTILISATEUR = "edouard"
DUREE_CEREMONIE = timedelta(minutes=5)
LONGUEUR_JOURNAL = 200

BUT_INSCRIPTION = "inscription"
BUT_CONNEXION = "connexion"


class OrigineInconnue(Exception):
    """`VEILLE_URL` absente ou illisible : les passkeys sont indisponibles."""


class CeremonieInvalide(Exception):
    """Une ceremonie inconnue, expiree ou deja servie, ou une reponse refusee."""


@dataclass
class Inscription:
    lien_id: int
    identifiant: str
    cle_publique: bytes
    compteur: int
    transports: list[str]


# {cle: (but, defi, lien_id, cree_le)}. Un seul processus, mais les routes
# synchrones de FastAPI tournent dans plusieurs fils : d'ou le verrou.
_ceremonies: dict[str, tuple[str, bytes, int | None, datetime]] = {}
_verrou = threading.Lock()


def origine_attendue() -> tuple[str, str]:
    """L'origine normalisee et le `rp_id` (le nom d'hote) de l'adresse publique.

    `VEILLE_EMPLOI_URL_PUBLIQUE` l'emporte si elle est posee et non vide, sinon
    `VEILLE_URL`. Schema http ou https seulement, hote en minuscules, port par
    defaut retire, chemin ignore, identifiants refuses.
    """
    nom = "VEILLE_EMPLOI_URL_PUBLIQUE"
    url = os.environ.get(nom, "").strip()
    if not url:
        nom = "VEILLE_URL"
        url = os.environ.get(nom, "").strip()
    try:
        morceaux = urlsplit(url)
        hote = morceaux.hostname
        port = morceaux.port  # un port illisible leve ValueError
    except ValueError:
        raise OrigineInconnue(f"{nom} n'est pas une adresse lisible") from None
    schema = morceaux.scheme.lower()
    if schema not in ("http", "https") or not hote:
        raise OrigineInconnue(f"{nom} est absente ou n'est pas une adresse http(s)")
    if morceaux.username is not None or morceaux.password is not None:
        raise OrigineInconnue(f"{nom} ne doit pas porter d'identifiants")
    if ":" in hote:
        hote_ecrit = f"[{hote}]"  # IPv6
    else:
        hote_ecrit = hote
    defaut = 443 if schema == "https" else 80
    origine = f"{schema}://{hote_ecrit}" + (f":{port}" if port not in (None, defaut) else "")
    return origine, hote


def oublier_ceremonies() -> None:
    with _verrou:
        _ceremonies.clear()


def _ouvrir(but: str, defi: bytes, lien_id: int | None) -> str:
    """Garde le defi ; les ceremonies expirees sont oubliees au passage."""
    instant = auth.maintenant()
    cle = secrets.token_urlsafe(16)
    with _verrou:
        for expiree in [c for c, (_, _, _, cree_le) in _ceremonies.items()
                        if instant - cree_le > DUREE_CEREMONIE]:
            del _ceremonies[expiree]
        _ceremonies[cle] = (but, defi, lien_id, instant)
    return cle


def _refus(but: str, raison: object) -> CeremonieInvalide:
    """Journalise un refus, sur une ligne, tronque ; rend l'exception a lever."""
    message = " ".join(f"passkeys, {but} refusee : {raison}".split())[:LONGUEUR_JOURNAL]
    log.warning("%s", message)
    return CeremonieInvalide(message)


def _reprendre(cle: str, but: str) -> tuple[bytes, int | None]:
    """Le defi et le lien de la ceremonie, retiree au passage (usage unique)."""
    with _verrou:
        ceremonie = _ceremonies.pop(cle, None) if isinstance(cle, str) else None
    if ceremonie is None:
        raise _refus(but, "ceremonie inconnue ou deja servie")
    but_ceremonie, defi, lien_id, cree_le = ceremonie
    if but_ceremonie != but:
        raise _refus(but, f"ceremonie d'un autre but ({but_ceremonie})")
    if auth.maintenant() - cree_le > DUREE_CEREMONIE:
        raise _refus(but, "ceremonie expiree")
    return defi, lien_id


def _en_dict(options) -> dict:
    return json.loads(webauthn.options_to_json(options))


def options_inscription(lien_id: int) -> tuple[str, dict]:
    """La cle de ceremonie et les options de `navigator.credentials.create()`.

    Le lien n'est pas verifie ici : c'est a la route de le faire.
    """
    _, rp_id = origine_attendue()
    connues = [PublicKeyCredentialDescriptor(id=webauthn.base64url_to_bytes(identifiant))
               for identifiant in db.identifiants_passkeys()]
    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=NOM_DU_SITE,
        user_name=NOM_UTILISATEUR,
        user_id=IDENTIFIANT_UTILISATEUR,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=connues,
    )
    return _ouvrir(BUT_INSCRIPTION, options.challenge, lien_id), _en_dict(options)


def verifier_inscription(cle: str, reponse: dict) -> Inscription:
    """La passkey a enregistrer ; `CeremonieInvalide` si la reponse est refusee."""
    origine, rp_id = origine_attendue()
    defi, lien_id = _reprendre(cle, BUT_INSCRIPTION)
    try:
        credential = parse_registration_credential_json(reponse)
        verifiee = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=defi,
            expected_rp_id=rp_id,
            expected_origin=origine,
            require_user_verification=False,
        )
    except Exception as exc:  # reponse du client : tout echec est un refus, jamais une 500
        raise _refus(BUT_INSCRIPTION, exc) from None
    return Inscription(
        lien_id=lien_id,
        identifiant=bytes_to_base64url(verifiee.credential_id),
        cle_publique=verifiee.credential_public_key,
        compteur=verifiee.sign_count,
        transports=[t.value for t in credential.response.transports or []],
    )


def options_connexion() -> tuple[str, dict]:
    """La cle de ceremonie et les options de `navigator.credentials.get()`.

    Aucune passkey n'est listee : elles sont decouvrables (`residentKey`).
    """
    _, rp_id = origine_attendue()
    options = webauthn.generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return _ouvrir(BUT_CONNEXION, options.challenge, None), _en_dict(options)


def verifier_connexion(cle: str, reponse: dict) -> int:
    """L'id de la passkey qui a signe ; son compteur et `utilisee_le` sont mis a jour.

    Un compteur qui ne monte pas (cle clonee) est refuse par `webauthn`.
    """
    origine, rp_id = origine_attendue()
    defi, _ = _reprendre(cle, BUT_CONNEXION)
    identifiant = reponse.get("id") if isinstance(reponse, dict) else None
    passkey = db.passkey_par_identifiant(identifiant) if isinstance(identifiant, str) else None
    if passkey is None:
        raise _refus(BUT_CONNEXION, "passkey inconnue")
    try:
        verifiee = webauthn.verify_authentication_response(
            credential=reponse,
            expected_challenge=defi,
            expected_rp_id=rp_id,
            expected_origin=origine,
            credential_public_key=passkey["cle_publique"],
            credential_current_sign_count=passkey["compteur"],
            require_user_verification=False,
        )
    except Exception as exc:  # reponse du client : tout echec est un refus, jamais une 500
        raise _refus(BUT_CONNEXION, exc) from None
    # Le compteur se compare a ce qui a ete lu : deux verifications sur la meme
    # lecture ne passent pas toutes les deux.
    if not db.maj_passkey_apres_usage(passkey["id"], verifiee.new_sign_count,
                                      passkey["compteur"], auth._iso(auth.maintenant())):
        raise _refus(BUT_CONNEXION, "compteur deja change")
    return passkey["id"]
