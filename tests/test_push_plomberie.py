"""Plomberie du push web, eprouvee sans HTTPS ni telephone.

Le push ne pourra etre essaye en vrai que le jour ou les certificats HTTPS du
tailnet seront actifs. Ces tests verifient tout ce qui ne depend pas de ce
jour-la : generation des cles VAPID, chiffrement de la charge pour un
abonnement donne, en-tetes envoyes, et nettoyage des abonnements expires.

On fait tourner un serveur HTTP local qui joue le role du service de push :
pywebpush lui envoie une vraie requete, et on inspecte ce qu'il recoit.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from veille import db, notifications


# --------------------------------------------------------------------------
# Faux service de push
# --------------------------------------------------------------------------


class _ServicePushFactice(HTTPServer):
    """Enregistre les requetes recues et renvoie le code demande."""

    recues: list[dict] = []
    code_reponse: int = 201


class _Gestionnaire(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - impose par BaseHTTPRequestHandler
        taille = int(self.headers.get("Content-Length", 0))
        self.server.recues.append(
            {
                "chemin": self.path,
                "entetes": {k.lower(): v for k, v in self.headers.items()},
                "corps": self.rfile.read(taille),
            }
        )
        self.send_response(self.server.code_reponse)
        self.end_headers()

    def log_message(self, *a):  # silence
        pass


@pytest.fixture
def service_push():
    serveur = _ServicePushFactice(("127.0.0.1", 0), _Gestionnaire)
    serveur.recues = []
    serveur.code_reponse = 201
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def _abonnement_factice(serveur) -> str:
    """Un abonnement avec de VRAIES cles : pywebpush doit pouvoir chiffrer."""
    cle = ec.generate_private_key(ec.SECP256R1())
    point = cle.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    p256dh = base64.urlsafe_b64encode(point).rstrip(b"=").decode()
    auth = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
    hote, port = serveur.server_address
    endpoint = f"http://{hote}:{port}/push/abc123"
    db.enregistrer_abonnement(endpoint, p256dh, auth)
    return endpoint


@pytest.fixture(autouse=True)
def vapid(tmp_path, monkeypatch):
    monkeypatch.setattr(notifications, "CHEMIN_VAPID", tmp_path / "vapid.json")
    db.initialiser()
    for a in db.lister_abonnements():
        db.supprimer_abonnement(a["endpoint"])
    return notifications.generer_vapid("mailto:camille@exemple.invalid")


# --------------------------------------------------------------------------
# Cles VAPID
# --------------------------------------------------------------------------


def test_les_cles_vapid_sont_au_bon_format(vapid):
    """La cle publique est transmise telle quelle au navigateur : sa longueur
    est imposee (point EC non compresse = 65 octets)."""
    publique = base64.urlsafe_b64decode(vapid.publique + "==")
    assert len(publique) == 65
    assert publique[0] == 0x04, "point EC non compresse"
    privee = base64.urlsafe_b64decode(vapid.privee + "==")
    assert len(privee) == 32


def test_les_cles_sont_relues_a_lidentique(vapid):
    relues = notifications.charger_vapid()
    assert (relues.publique, relues.privee) == (vapid.publique, vapid.privee)


def test_le_fichier_de_cles_nest_lisible_que_par_lui(vapid):
    if os.name == "nt":
        pytest.skip("droits POSIX")
    assert oct(notifications.CHEMIN_VAPID.stat().st_mode)[-3:] == "600"


# --------------------------------------------------------------------------
# Envoi reel vers un service factice
# --------------------------------------------------------------------------


def test_le_push_part_chiffre_et_signe(service_push):
    _abonnement_factice(service_push)
    ok, ko = notifications.envoyer_push("Titre", "Corps du message", url="/?filtre=nouveau")
    assert (ok, ko) == (1, 0)
    assert len(service_push.recues) == 1

    requete = service_push.recues[0]
    entetes = requete["entetes"]

    # Signature VAPID : c'est ce qui authentifie le serveur aupres du service.
    assert "authorization" in entetes
    assert entetes["authorization"].lower().startswith("vapid")
    # Chiffrement de bout en bout : le service de push ne doit rien pouvoir lire.
    assert entetes.get("content-encoding") == "aes128gcm"
    assert requete["corps"], "la charge ne doit pas etre vide"
    assert b"Corps du message" not in requete["corps"], "la charge doit etre chiffree"


def test_le_contenu_notifie_est_celui_attendu(service_push, monkeypatch):
    """On verifie la charge AVANT chiffrement, la ou on peut encore la lire."""
    capturees = {}

    def espion(subscription_info, data, **kwargs):
        capturees["data"] = data
        return type("R", (), {"status_code": 201})()

    monkeypatch.setattr("pywebpush.webpush", espion)
    _abonnement_factice(service_push)
    notifications.envoyer_push("2 nouvelles offres", "La mieux placee : X (87 pts)", url="/?filtre=nouveau")

    charge = json.loads(capturees["data"])
    assert charge["titre"] == "2 nouvelles offres"
    assert charge["corps"].startswith("La mieux placee")
    assert charge["url"] == "/?filtre=nouveau"


# --------------------------------------------------------------------------
# Abonnements expires
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", [404, 410])
def test_un_abonnement_expire_est_retire(service_push, code):
    """404/410 : le navigateur a revoque l'abonnement. Le garder ferait
    echouer chaque envoi suivant."""
    endpoint = _abonnement_factice(service_push)
    service_push.code_reponse = code
    ok, ko = notifications.envoyer_push("Titre", "Corps")
    assert (ok, ko) == (0, 1)
    assert endpoint not in [a["endpoint"] for a in db.lister_abonnements()]


def test_une_erreur_passagere_ne_retire_pas_labonnement(service_push):
    """500 : panne du service de push, pas un abonnement mort."""
    endpoint = _abonnement_factice(service_push)
    service_push.code_reponse = 500
    ok, ko = notifications.envoyer_push("Titre", "Corps")
    assert (ok, ko) == (0, 1)
    assert endpoint in [a["endpoint"] for a in db.lister_abonnements()]


def test_sans_abonnement_on_ne_tente_rien(service_push):
    assert notifications.envoyer_push("Titre", "Corps") == (0, 0)


def test_sans_cles_vapid_on_echoue_proprement(monkeypatch, tmp_path, service_push):
    _abonnement_factice(service_push)
    monkeypatch.setattr(notifications, "CHEMIN_VAPID", tmp_path / "absent.json")
    assert notifications.envoyer_push("Titre", "Corps") == (0, 0)
    assert service_push.recues == [], "aucune requete ne doit partir sans cles"
