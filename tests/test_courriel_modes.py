"""Les trois façons de délimiter ce qu'on lit dans la boîte mail.

Écrits sans mot de passe d'application : un faux serveur IMAP joue les
réponses de Gmail. L'objectif est qu'au jour où le mot de passe arrive, la
mécanique soit déjà éprouvée et qu'il ne reste que la connexion à vérifier.
"""

from __future__ import annotations

import pytest

from veille import config
from veille.collectors import courriel


# --------------------------------------------------------------------------
# Faux serveur
# --------------------------------------------------------------------------


class FauxIMAP:
    """Rejoue les reponses d'un serveur, et retient ce qu'on lui a demande."""

    def __init__(self, dossiers=None, gmail=True, uids=None):
        self._capacites_reelles = (b"IMAP4REV1", b"X-GM-EXT-1") if gmail else (b"IMAP4REV1",)
        self.capabilities = self._capacites_reelles
        self._dossiers = dossiers if dossiers is not None else [
            rb'(\HasNoChildren) "/" "INBOX"',
            rb'(\HasNoChildren \All) "/" "[Gmail]/Tous les messages"',
            rb'(\HasNoChildren \Sent) "/" "[Gmail]/Messages envoy&AOk-s"',
            rb'(\HasNoChildren) "/" "veille-emploi"',
        ]
        self._uids = uids or {}
        self.recherches: list[tuple] = []
        self.ouverts: list[str] = []

    def login(self, *a):
        # Comme Gmail : avant authentification, X-GM-EXT-1 n'est pas annonce.
        self.capabilities = (b"IMAP4REV1",)
        return "OK", [b""]

    def capability(self):
        """Gmail n'annonce X-GM-EXT-1 qu'apres authentification."""
        self.capability_appelee = True
        return "OK", [b" ".join(self._capacites_reelles)]

    def list(self):
        return "OK", self._dossiers

    def select(self, dossier, readonly=False):
        self.ouverts.append(dossier.strip('"'))
        return "OK", [b"1"]

    def status(self, dossier, quoi):
        return "OK", [b'"x" (UIDVALIDITY 42)']

    def uid(self, commande, *args):
        if commande == "SEARCH":
            self.recherches.append(args)
            dossier = self.ouverts[-1] if self.ouverts else ""
            return "OK", [b" ".join(self._uids.get(dossier, []))]
        if commande == "FETCH":
            return "OK", [(b"1 (RFC822 {10}", b"From: a@b\r\n\r\nx")]
        return "OK", [b""]

    def close(self):
        return "OK", [b""]

    def logout(self):
        return "OK", [b""]


@pytest.fixture
def boite(monkeypatch):
    """Fabrique une BoiteIMAP branchee sur le faux serveur."""
    monkeypatch.setenv("VEILLE_IMAP_UTILISATEUR", "moi@gmail.com")
    monkeypatch.setenv("VEILLE_IMAP_MOTDEPASSE", "secret")
    monkeypatch.delenv("VEILLE_IMAP_MODE", raising=False)
    monkeypatch.delenv("VEILLE_IMAP_DOSSIER", raising=False)

    def fabriquer(mode="union", expediteurs=("jobs.ch", "alert@indeed.com"),
                  libelle="veille-emploi", faux=None):
        monkeypatch.setattr(config, "charger_sources", lambda: {
            "courriel": {"mode": mode, "libelle": libelle, "expediteurs": list(expediteurs)}
        })
        b = courriel.BoiteIMAP()
        b._cx = faux or FauxIMAP()
        return b

    return fabriquer


# --------------------------------------------------------------------------
# Découverte des dossiers
# --------------------------------------------------------------------------


def test_le_dossier_tous_les_messages_est_trouve_par_son_role(boite):
    """Il s'appelle « Tous les messages » en français, « All Mail » en anglais :
    on le reconnaît à son attribut \\All, jamais à son nom."""
    b = boite()
    assert b.dossier_tous_les_messages() == "[Gmail]/Tous les messages"


def test_repli_sur_inbox_si_aucun_role_all(boite):
    faux = FauxIMAP(dossiers=[rb'(\HasNoChildren) "/" "INBOX"'])
    b = boite(faux=faux)
    assert b.dossier_tous_les_messages() == "INBOX"


# --------------------------------------------------------------------------
# Les trois modes
# --------------------------------------------------------------------------


def test_mode_libelle_ne_lit_que_le_dossier_du_libelle(boite):
    plan = boite(mode="libelle").passes()
    assert len(plan) == 1
    assert plan[0].dossier == "veille-emploi"
    assert plan[0].expediteurs == []


def test_mode_expediteurs_cherche_dans_tous_les_messages(boite):
    plan = boite(mode="expediteurs").passes()
    assert len(plan) == 1
    assert plan[0].dossier == "[Gmail]/Tous les messages"
    assert "jobs.ch" in plan[0].expediteurs


def test_mode_union_fait_les_deux(boite):
    plan = boite(mode="union").passes()
    assert len(plan) == 2
    assert {p.dossier for p in plan} == {"veille-emploi", "[Gmail]/Tous les messages"}


def test_union_se_passe_du_libelle_sil_nexiste_pas(boite):
    """Le filet est facultatif : sans filtre Gmail, la collecte marche quand même."""
    faux = FauxIMAP(dossiers=[
        rb'(\HasNoChildren) "/" "INBOX"',
        rb'(\HasNoChildren \All) "/" "[Gmail]/Tous les messages"',
    ])
    plan = boite(mode="union", faux=faux).passes()
    assert len(plan) == 1
    assert plan[0].expediteurs


def test_mode_libelle_refuse_de_deviner_si_le_libelle_manque(boite):
    faux = FauxIMAP(dossiers=[rb'(\HasNoChildren) "/" "INBOX"'])
    with pytest.raises(RuntimeError, match="introuvable"):
        boite(mode="libelle", faux=faux).passes()


def test_mode_expediteurs_sans_adresse_est_refuse(boite):
    with pytest.raises(RuntimeError, match="aucune adresse"):
        boite(mode="expediteurs", expediteurs=()).passes()


def test_un_mode_inconnu_est_refuse(boite):
    with pytest.raises(RuntimeError, match="mode de collecte"):
        boite(mode="n_importe_quoi")


# --------------------------------------------------------------------------
# La recherche elle-même
# --------------------------------------------------------------------------


def test_gmail_recoit_une_seule_requete_native(boite):
    """from:(a OR b OR c) en une fois, execute par le serveur."""
    faux = FauxIMAP(gmail=True)
    b = boite(mode="expediteurs", expediteurs=("jobs.ch", "alert@indeed.com"), faux=faux)
    passe = b.passes()[0]
    b._ouvrir(passe.dossier)
    b._chercher(passe, "01-Sep-2026", "")
    args = faux.recherches[-1]
    assert "X-GM-RAW" in args
    requete = next(a for a in args if "from:" in str(a))
    assert "jobs.ch" in requete and "alert@indeed.com" in requete and " OR " in requete


def test_serveur_ordinaire_fait_une_recherche_par_expediteur(boite):
    """L'imbrication de OR en IMAP devient illisible : on unit les resultats."""
    faux = FauxIMAP(gmail=False)
    b = boite(mode="expediteurs", expediteurs=("jobs.ch", "alert@indeed.com"), faux=faux)
    passe = b.passes()[0]
    b._ouvrir(passe.dossier)
    b._chercher(passe, "01-Sep-2026", "")
    assert len(faux.recherches) == 2
    assert all("FROM" in r for r in faux.recherches)


def test_la_recherche_est_bornee_dans_le_temps(boite):
    faux = FauxIMAP()
    b = boite(mode="expediteurs", faux=faux)
    passe = b.passes()[0]
    b._ouvrir(passe.dossier)
    b._chercher(passe, "01-Sep-2026", "")
    assert "SINCE" in faux.recherches[-1]


def test_le_marqueur_reprend_apres_le_dernier_uid(boite):
    faux = FauxIMAP()
    b = boite(mode="expediteurs", faux=faux)
    passe = b.passes()[0]
    b._ouvrir(passe.dossier)
    b._chercher(passe, "01-Sep-2026", "1200")
    assert any("1201:*" in str(a) for a in faux.recherches[-1])


def test_lunion_des_uids_dedoublonne(boite):
    """Un message venant de deux expediteurs cherches ne doit compter qu'une fois."""
    faux = FauxIMAP(gmail=False)
    faux._uids["[Gmail]/Tous les messages"] = [b"3", b"7", b"3"]
    b = boite(mode="expediteurs", expediteurs=("a.com", "b.com"), faux=faux)
    passe = b.passes()[0]
    b._ouvrir(passe.dossier)
    uids = b._chercher(passe, "01-Sep-2026", "")
    assert uids == [b"3", b"7"]


# --------------------------------------------------------------------------
# Marqueurs par dossier
# --------------------------------------------------------------------------


def test_chaque_passe_a_son_propre_marqueur(boite):
    """Les UID sont propres a un dossier : un marqueur commun ferait sauter
    des messages ou en relirait."""
    cles = {p.cle for p in boite(mode="union").passes()}
    assert len(cles) == 2
    assert any("libelle:" in c for c in cles)
    assert any("expediteurs:" in c for c in cles)


def test_luidvalidity_est_relevee(boite):
    b = boite(mode="expediteurs")
    b._ouvrir("[Gmail]/Tous les messages")
    assert b.uidvalidity() == "42"


# --------------------------------------------------------------------------
# Capacites du serveur
# --------------------------------------------------------------------------


def test_les_capacites_sont_redemandees_apres_authentification(boite, monkeypatch):
    """Regression mesuree sur la vraie boite : Gmail n'annonce X-GM-EXT-1
    qu'APRES le login, et imaplib ne redemande pas. Sans ce rafraichissement on
    croit parler a un serveur ordinaire et on perd la recherche native."""
    faux = FauxIMAP(gmail=True)
    monkeypatch.setattr(courriel.imaplib, "IMAP4_SSL", lambda *a, **k: faux)
    b = boite(faux=faux)
    with b:
        assert getattr(faux, "capability_appelee", False), "capability() doit etre appelee"
        assert b.gmail, "X-GM-EXT-1 doit etre vu apres rafraichissement"


def test_sans_rafraichissement_la_capacite_serait_invisible(boite, monkeypatch):
    """Ce que faisait le code avant : imaplib ne redemande pas les capacites,
    et Gmail ne les annonce qu'apres authentification."""
    faux = FauxIMAP(gmail=True)
    monkeypatch.setattr(courriel.imaplib, "IMAP4_SSL", lambda *a, **k: faux)
    b = boite(faux=faux)
    b._cx = faux
    faux.login()                      # comme imaplib : pas de CAPABILITY ensuite
    assert not b.gmail, "sans rafraichissement, la capacite reste invisible"
