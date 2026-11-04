"""Les liens de connexion : jeton hors base, 24 heures, un seul usage."""

from __future__ import annotations

import base64
import hmac

import pytest

from veille import auth, db


@pytest.fixture(autouse=True)
def _base():
    db.initialiser()


def base64url_to_bytes(texte: str) -> bytes:
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


def test_un_lien_fait_au_moins_128_bits():
    assert len(base64url_to_bytes(auth.creer_lien("serveur"))) >= 16


def test_le_jeton_du_lien_n_est_jamais_en_base():
    jeton = auth.creer_lien("serveur")
    with db.connexion() as cx:
        assert jeton not in repr([tuple(l) for l in cx.execute("SELECT * FROM liens_connexion")])


def test_un_lien_vaut_24_heures(horloge):
    jeton = auth.creer_lien("serveur")
    horloge.avancer(hours=23, minutes=59)
    assert auth.lien_ouvert(jeton) is not None
    horloge.avancer(minutes=2)
    assert auth.lien_ouvert(jeton) is None


def test_un_lien_ne_sert_qu_une_fois():
    lien = auth.lien_ouvert(auth.creer_lien("appareil"))
    assert auth.consommer_lien(lien) is True
    assert auth.consommer_lien(lien) is False


def test_un_lien_expire_ne_se_consomme_pas(horloge):
    lien = auth.lien_ouvert(auth.creer_lien("appareil"))
    horloge.avancer(hours=24, minutes=1)
    assert auth.consommer_lien(lien) is False


def test_une_origine_inconnue_est_refusee():
    with pytest.raises(ValueError):
        auth.creer_lien("ailleurs")


def test_la_comparaison_est_en_temps_constant(monkeypatch):
    appels = []
    vraie = hmac.compare_digest
    monkeypatch.setattr(auth.hmac, "compare_digest", lambda a, b: appels.append(1) or vraie(a, b))
    auth.lien_ouvert(auth.creer_lien("serveur"))
    assert appels
