"""Un authentificateur WebAuthn logiciel, pour les tests.

Il fait de vraies signatures ES256, que `webauthn` verifie : la cryptographie
des passkeys est eprouvee sur le poste et sur le serveur, sans navigateur.
La cle privee est tiree au vol, a chaque instance : aucun secret versionne.

Tout ce qui part vers le serveur est en base64url sans remplissage, comme
le rend `PublicKeyCredential.toJSON()` dans un navigateur.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

# Drapeaux des donnees d'authentificateur : UP (0x01), UV (0x04), AT (0x40).
DRAPEAUX_INSCRIPTION = 0x45
DRAPEAUX_CONNEXION = 0x05


def b64url(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode("ascii")


class AuthentificateurLogiciel:
    """Une passkey de plateforme : une cle P-256, un identifiant, un compteur."""

    def __init__(self) -> None:
        self.cle = ec.generate_private_key(ec.SECP256R1())
        self.identifiant = os.urandom(16)
        self.compteur = 0

    def _donnees_auth(self, rp_id: str, drapeaux: int, avec_cle: bool) -> bytes:
        donnees = (hashlib.sha256(rp_id.encode()).digest() + bytes([drapeaux])
                   + self.compteur.to_bytes(4, "big"))
        if avec_cle:
            publique = self.cle.public_key().public_numbers()
            cose = {1: 2, 3: -7, -1: 1,
                    -2: publique.x.to_bytes(32, "big"), -3: publique.y.to_bytes(32, "big")}
            donnees += (bytes(16) + len(self.identifiant).to_bytes(2, "big") + self.identifiant
                        + cbor2.dumps(cose))
        return donnees

    @staticmethod
    def _donnees_client(type_: str, options: dict, origine: str) -> bytes:
        return json.dumps({"type": type_, "challenge": options["challenge"], "origin": origine,
                           "crossOrigin": False}).encode()

    def _squelette(self, reponse: dict) -> dict:
        return {
            "id": b64url(self.identifiant),
            "rawId": b64url(self.identifiant),
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": reponse,
        }

    def inscrire(self, options: dict, origine: str) -> dict:
        """La reponse de `navigator.credentials.create()` a ces options."""
        donnees = self._donnees_auth(options["rp"]["id"], DRAPEAUX_INSCRIPTION, avec_cle=True)
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": donnees})
        return self._squelette({
            "clientDataJSON": b64url(self._donnees_client("webauthn.create", options, origine)),
            "attestationObject": b64url(attestation),
            "transports": ["internal"],
        })

    def signer(self, options: dict, origine: str) -> dict:
        """La reponse de `navigator.credentials.get()` a ces options."""
        self.compteur += 1
        donnees = self._donnees_auth(options["rpId"], DRAPEAUX_CONNEXION, avec_cle=False)
        client = self._donnees_client("webauthn.get", options, origine)
        signature = self.cle.sign(donnees + hashlib.sha256(client).digest(),
                                  ec.ECDSA(hashes.SHA256()))
        return self._squelette({
            "clientDataJSON": b64url(client),
            "authenticatorData": b64url(donnees),
            "signature": b64url(signature),
            "userHandle": b64url(b"edouard"),
        })
