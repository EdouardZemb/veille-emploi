"""La limite de debit : un compteur, une fenetre glissante."""

from __future__ import annotations

from datetime import timedelta

from starlette.requests import Request

from veille.debit import LimiteDebit, cle_client


def test_la_fenetre_se_rouvre_apres_une_minute(horloge):
    limite = LimiteDebit(20, timedelta(minutes=1))
    assert [limite.autoriser() for _ in range(20)] == [True] * 20
    assert limite.autoriser() is False
    horloge.avancer(seconds=61)
    assert limite.autoriser() is True


def test_vider_rouvre_la_fenetre(horloge):
    limite = LimiteDebit(2, timedelta(minutes=1))
    assert limite.autoriser() and limite.autoriser()
    assert limite.autoriser() is False
    limite.vider()
    assert limite.autoriser() is True


def test_deux_clients_ont_chacun_leur_budget(horloge):
    limite = LimiteDebit(20, timedelta(minutes=1))
    assert [limite.autoriser("a") for _ in range(20)] == [True] * 20
    assert limite.autoriser("a") is False
    assert limite.autoriser("b") is True


def test_le_plafond_global(horloge):
    limite = LimiteDebit(200, timedelta(minutes=1))
    assert all(limite.autoriser() for _ in range(200))
    assert limite.autoriser() is False


def _requete(*entetes, client=("192.0.2.10", 1)):
    return Request({"type": "http", "client": client,
                    "headers": [(k.lower().encode(), v.encode()) for k, v in entetes]})


def test_une_ipv6_compte_pour_son_slash_64():
    def cle(adresse):
        return cle_client(_requete(client=(adresse, 1)))

    assert cle("2001:db8::1") == cle("2001:db8::2") == "2001:db8::/64"
    assert cle("2001:db8:0:1::1") != cle("2001:db8::1")


def test_cle_client():
    assert cle_client(_requete(("CF-Connecting-IP", "203.0.113.7"))) == "203.0.113.7"
    assert cle_client(_requete(("CF-Connecting-IP", "  203.0.113.7 "))) == "203.0.113.7"
    assert cle_client(_requete()) == "192.0.2.10"
    assert cle_client(_requete(("CF-Connecting-IP", ""))) == "192.0.2.10"
    assert cle_client(_requete(("CF-Connecting-IP", "pas-une-ip"))) == "pas-une-ip"
    assert cle_client(_requete(client=None)) == ""


def test_la_memoire_reste_bornee(horloge):
    limite = LimiteDebit(20, timedelta(minutes=1))
    for i in range(50):
        limite.autoriser(f"ancien-{i}")
    assert limite.nombre_de_cles() == 50
    horloge.avancer(seconds=61)
    limite.autoriser("nouveau")
    assert limite.nombre_de_cles() == 1


def test_une_cle_dont_la_fenetre_s_est_videe_repart_a_neuf(horloge):
    limite = LimiteDebit(1, timedelta(minutes=1))
    assert limite.autoriser("a") is True
    horloge.avancer(seconds=30)
    assert limite.autoriser("a") is False
    horloge.avancer(seconds=31)
    assert limite.autoriser("a") is True
    assert limite.nombre_de_cles() == 1


def test_une_cle_opaque_est_tronquee():
    assert len(cle_client(_requete(("CF-Connecting-IP", "x" * 500)))) == 64


def test_une_ipv6_mappee_vaut_son_ipv4():
    assert cle_client(_requete(("CF-Connecting-IP", "::ffff:203.0.113.7"))) == "203.0.113.7"


def test_une_demande_refusee_ne_compte_pas_et_ne_cree_pas_de_cle(horloge):
    limite = LimiteDebit(1, timedelta(minutes=1))
    assert limite.disponible("a") is True
    assert limite.nombre_de_cles() == 0
    limite.enregistrer("a")
    assert limite.disponible("a") is False
    assert limite.disponible("a") is False
    assert limite.nombre_de_cles() == 1


def test_un_balayage_garde_la_cle_active(horloge):
    limite = LimiteDebit(3, timedelta(minutes=1))
    limite.autoriser("x")            # amorce l'horloge du balayage
    horloge.avancer(seconds=1)
    limite.autoriser("a")
    horloge.avancer(seconds=39)
    limite.autoriser("a")
    horloge.avancer(seconds=10)
    limite.autoriser("a")
    horloge.avancer(seconds=11)      # une fenetre depuis le premier balayage
    limite.autoriser("y")            # declenche le balayage
    assert limite.nombre_de_cles() == 2  # "a" (active) et "y" ; "x" est partie
    assert "a" in limite._acceptees
