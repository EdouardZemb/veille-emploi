"""Tests des deux canaux de notification.

Ils existent parce que le repli mail pointait initialement sur un relais local
qui acceptait tous les messages et n'en faisait sortir aucun. Le repli echouait en silence,
precisement dans le cas ou il doit servir.
"""

from __future__ import annotations

import smtplib

import pytest

from veille import db, notifications


@pytest.fixture(autouse=True)
def base_prete():
    db.initialiser()


# --------------------------------------------------------------------------
# Reglages SMTP
# --------------------------------------------------------------------------


def test_le_repli_ne_pointe_jamais_sur_le_mta_local_par_defaut(monkeypatch):
    """Regression : 127.0.0.1:25 n'achemine rien hors de la machine."""
    for cle in (
        "VEILLE_SMTP_HOTE", "VEILLE_SMTP_PORT",
        "VEILLE_SMTP_UTILISATEUR", "VEILLE_SMTP_MOTDEPASSE",
    ):
        monkeypatch.delenv(cle, raising=False)
    hote, port, _, _ = notifications._reglages_smtp()
    assert hote not in ("127.0.0.1", "localhost")
    assert port != 25


def test_les_identifiants_imap_servent_au_smtp(monkeypatch):
    """Un seul mot de passe d'application a renseigner, un seul a revoquer."""
    monkeypatch.delenv("VEILLE_SMTP_UTILISATEUR", raising=False)
    monkeypatch.delenv("VEILLE_SMTP_MOTDEPASSE", raising=False)
    monkeypatch.setenv("VEILLE_IMAP_UTILISATEUR", "moi@gmail.com")
    monkeypatch.setenv("VEILLE_IMAP_MOTDEPASSE", "abcd efgh ijkl mnop")
    _, _, utilisateur, motdepasse = notifications._reglages_smtp()
    assert utilisateur == "moi@gmail.com"
    assert motdepasse == "abcd efgh ijkl mnop"


def test_un_smtp_explicite_a_la_priorite(monkeypatch):
    monkeypatch.setenv("VEILLE_IMAP_UTILISATEUR", "imap@gmail.com")
    monkeypatch.setenv("VEILLE_SMTP_UTILISATEUR", "smtp@autre.fr")
    monkeypatch.setenv("VEILLE_SMTP_HOTE", "smtp.autre.fr")
    hote, _, utilisateur, _ = notifications._reglages_smtp()
    assert (hote, utilisateur) == ("smtp.autre.fr", "smtp@autre.fr")


# --------------------------------------------------------------------------
# Envoi
# --------------------------------------------------------------------------


class _SMTPFactice:
    """Remplace smtplib pour observer ce qui aurait ete envoye."""

    dernier: "_SMTPFactice | None" = None

    def __init__(self, hote, port, timeout=None):
        self.hote, self.port = hote, port
        self.starttls_appele = False
        self.identifiants = None
        self.message = None
        _SMTPFactice.dernier = self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self, *a, **k):
        self.starttls_appele = True

    def login(self, u, m):
        self.identifiants = (u, m)

    def send_message(self, message):
        self.message = message


def test_envoi_authentifie_avec_starttls(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _SMTPFactice)
    monkeypatch.setenv("VEILLE_SMTP_HOTE", "smtp.gmail.com")
    monkeypatch.setenv("VEILLE_SMTP_PORT", "587")
    monkeypatch.setenv("VEILLE_IMAP_UTILISATEUR", "moi@gmail.com")
    monkeypatch.setenv("VEILLE_IMAP_MOTDEPASSE", "secret")
    monkeypatch.setenv("VEILLE_MAIL_DESTINATAIRE", "moi@gmail.com")

    assert notifications.envoyer_mail("Sujet", "Corps") is True
    envoi = _SMTPFactice.dernier
    assert envoi.starttls_appele, "STARTTLS obligatoire sur le port 587"
    assert envoi.identifiants == ("moi@gmail.com", "secret")
    # Gmail refuse un expediteur different du compte authentifie.
    assert envoi.message["From"] == "moi@gmail.com"


def test_sans_destinataire_on_ne_tente_rien(monkeypatch):
    monkeypatch.delenv("VEILLE_MAIL_DESTINATAIRE", raising=False)
    assert notifications.envoyer_mail("Sujet", "Corps") is False


def test_echec_smtp_ne_leve_pas(monkeypatch):
    def explose(*a, **k):
        raise OSError("reseau coupe")

    monkeypatch.setattr(smtplib, "SMTP", explose)
    monkeypatch.setenv("VEILLE_IMAP_UTILISATEUR", "moi@gmail.com")
    monkeypatch.setenv("VEILLE_IMAP_MOTDEPASSE", "secret")
    monkeypatch.setenv("VEILLE_MAIL_DESTINATAIRE", "moi@gmail.com")
    assert notifications.envoyer_mail("Sujet", "Corps") is False


# --------------------------------------------------------------------------
# Choix du canal
# --------------------------------------------------------------------------


def _offre(score: float) -> dict:
    return {"id": 1, "titre": "Test Engineer", "employeur": "Exemplia", "lieu": "Basel", "score": score, "url": "u"}


def test_rien_ne_part_sous_le_seuil(monkeypatch):
    appels = []
    monkeypatch.setattr(notifications, "envoyer_push", lambda *a, **k: appels.append("push") or (1, 0))
    monkeypatch.setattr(notifications, "envoyer_mail", lambda *a, **k: appels.append("mail") or True)
    notifications.prevenir_nouvelles_offres([_offre(10)])
    assert appels == [], "une offre sous le seuil ne doit pas faire sonner le telephone"


def test_le_mail_ne_part_que_si_aucun_push_nest_passe(monkeypatch):
    appels = []
    monkeypatch.setattr(notifications, "envoyer_push", lambda *a, **k: (1, 0))
    monkeypatch.setattr(notifications, "envoyer_mail", lambda *a, **k: appels.append("mail") or True)
    notifications.prevenir_nouvelles_offres([_offre(80)])
    assert appels == [], "le push a marche : pas de doublon par mail"


def test_le_mail_prend_le_relais_quand_le_push_echoue(monkeypatch):
    appels = []
    monkeypatch.setattr(notifications, "envoyer_push", lambda *a, **k: (0, 1))
    monkeypatch.setattr(notifications, "envoyer_mail", lambda *a, **k: appels.append("mail") or True)
    notifications.prevenir_nouvelles_offres([_offre(80)])
    assert appels == ["mail"]


def test_echec_des_deux_canaux_est_consigne(monkeypatch):
    """Il faut que ca se voie dans `veille etat`, pas seulement dans un journal."""
    monkeypatch.setattr(notifications, "envoyer_push", lambda *a, **k: (0, 0))
    monkeypatch.setattr(notifications, "envoyer_mail", lambda *a, **k: False)
    notifications.prevenir_nouvelles_offres([_offre(80)])
    with db.connexion() as cx:
        ligne = cx.execute(
            "SELECT dernier_resultat FROM etat_collecte WHERE source = 'notification'"
        ).fetchone()
    assert ligne is not None
    assert "ECHEC" in ligne["dernier_resultat"]


# --------------------------------------------------------------------------
# Abonnements push
# --------------------------------------------------------------------------


def test_abonnement_enregistre_puis_retire():
    db.enregistrer_abonnement("https://fcm.example/abc", "cle-p256dh", "cle-auth")
    assert any(a["endpoint"] == "https://fcm.example/abc" for a in db.lister_abonnements())
    # Le meme appareil qui se reabonne ne doit pas creer de doublon.
    db.enregistrer_abonnement("https://fcm.example/abc", "nouvelle-cle", "cle-auth")
    correspondants = [a for a in db.lister_abonnements() if a["endpoint"] == "https://fcm.example/abc"]
    assert len(correspondants) == 1
    assert correspondants[0]["p256dh"] == "nouvelle-cle"
    db.supprimer_abonnement("https://fcm.example/abc")
    assert not any(a["endpoint"] == "https://fcm.example/abc" for a in db.lister_abonnements())


# --------------------------------------------------------------------------
# Le sujet VAPID par défaut n'est l'adresse de personne
# --------------------------------------------------------------------------


def test_sujet_vapid_par_defaut(monkeypatch, tmp_path):
    monkeypatch.setattr(notifications, "CHEMIN_VAPID", tmp_path / "vapid.json")
    monkeypatch.delenv("VEILLE_EMPLOI_URL_PUBLIQUE", raising=False)
    monkeypatch.delenv("VEILLE_URL", raising=False)
    assert notifications.sujet_par_defaut() == "mailto:proprietaire@exemple.invalid"
    assert notifications.generer_vapid().sujet == "mailto:proprietaire@exemple.invalid"

    monkeypatch.setenv("VEILLE_URL", "https://console.exemple.invalid")
    assert notifications.sujet_par_defaut() == "https://console.exemple.invalid"


def test_un_vapid_json_existant_garde_son_sujet(monkeypatch, tmp_path):
    chemin = tmp_path / "vapid.json"
    chemin.write_text(
        '{"publique": "p", "privee": "q", "sujet": "mailto:ancien@exemple.invalid"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(notifications, "CHEMIN_VAPID", chemin)
    assert notifications.charger_vapid().sujet == "mailto:ancien@exemple.invalid"
    # un fichier sans sujet prend le sujet par défaut, sans être réécrit
    chemin.write_text('{"publique": "p", "privee": "q"}', encoding="utf-8")
    octets, mtime = chemin.read_bytes(), chemin.stat().st_mtime_ns
    monkeypatch.delenv("VEILLE_EMPLOI_URL_PUBLIQUE", raising=False)
    monkeypatch.delenv("VEILLE_URL", raising=False)
    assert notifications.charger_vapid().sujet == "mailto:proprietaire@exemple.invalid"
    assert chemin.read_bytes() == octets
    assert chemin.stat().st_mtime_ns == mtime
