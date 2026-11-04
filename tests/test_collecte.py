"""La collecte, sortie de `veille collecter` pour que le planificateur la lance.

Deux appelants : la CLI (le minuteur systemd du serveur du tailnet, ou la main
d'Edouard), qui lui passe `print` et dont la sortie ne change pas ; le
planificateur de la console en conteneur, qui garde le journal par defaut.
Aucune source ne sort sur le reseau ici : les quatre sont remplacees.
"""

from __future__ import annotations

import argparse
import logging

import pytest

from veille import cli, collecte, db, notifications
from veille.collectors import arbeitnow, base, courriel, france_travail, rss


@pytest.fixture(autouse=True)
def _base_propre(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    db.initialiser()


@pytest.fixture
def appels(monkeypatch):
    """Les quatre sources, factices : le courriel echoue, les autres ne rendent rien."""
    vus: dict[str, dict] = {}

    def factice(nom: str, echec: Exception | None = None):
        def collecter(**kwargs):
            vus[nom] = kwargs
            if echec is not None:
                raise echec
            return []
        return collecter

    monkeypatch.setattr(france_travail, "collecter", factice("france_travail"))
    monkeypatch.setattr(courriel, "collecter",
                        factice("courriel", RuntimeError("IMAP injoignable")))
    monkeypatch.setattr(rss, "collecter", factice("rss"))
    monkeypatch.setattr(arbeitnow, "collecter", factice("arbeitnow"))
    return vus


@pytest.fixture
def deux_nouvelles(monkeypatch):
    """Chaque source passee rend deux nouvelles offres, sans rien ecrire en base."""
    monkeypatch.setattr(base, "ingerer",
                        lambda offres, source: base.Rapport(source, collectees=2, nouvelles=2))


def test_la_cli_garde_sa_sortie(appels, capsys):
    rc = cli.cmd_collecter(argparse.Namespace(jours=3, source=None, sans_notification=True))

    assert rc == 0
    sortie, erreurs = capsys.readouterr()
    assert sortie.splitlines() == [
        "--- france_travail ---",
        "  0 vues, 0 nouvelles",
        "--- courriel ---",
        "--- rss ---",
        "  0 vues, 0 nouvelles",
        "--- arbeitnow ---",
        "  0 vues, 0 nouvelles",
        "",
        "Total : 0 nouvelle(s) offre(s)",
    ]
    assert erreurs == "  ECHEC : IMAP injoignable\n"
    assert appels == {"france_travail": {"jours": 3}, "courriel": {"jours": 3},
                      "rss": {}, "arbeitnow": {}}


def test_la_cli_passe_les_sources_demandees(appels, capsys):
    cli.cmd_collecter(argparse.Namespace(jours=7, source=["rss"], sans_notification=True))

    assert set(appels) == {"rss"}
    assert capsys.readouterr().out.splitlines()[0] == "--- rss ---"


def test_collecter_rend_le_nombre_de_nouvelles(appels, deux_nouvelles):
    lignes: list[str] = []

    n = collecte.collecter(sources={"rss", "arbeitnow"}, notifier=False, sortie=lignes.append)

    assert n == 4
    assert lignes == [
        "--- rss ---",
        "  2 vues, 2 nouvelles",
        "--- arbeitnow ---",
        "  2 vues, 2 nouvelles",
        "",
        "Total : 4 nouvelle(s) offre(s)",
    ]


def test_par_defaut_la_collecte_parle_au_journal(appels, caplog):
    with caplog.at_level(logging.INFO, logger="veille.collecte"):
        collecte.collecter(sources={"courriel", "rss"}, notifier=False)

    par_message = {r.getMessage(): r.levelno for r in caplog.records}
    assert par_message["--- rss ---"] == logging.INFO
    assert par_message["  ECHEC : IMAP injoignable"] == logging.WARNING


def test_le_journal_n_a_ni_ligne_vide_ni_saut_de_ligne(appels, caplog):
    """Une ligne du journal (`docker logs`) par message : la ligne vide qui
    separe le total, a la CLI, n'y entre pas, et le total ne commence pas par
    un saut de ligne qui couperait sa ligne en deux."""
    with caplog.at_level(logging.INFO, logger="veille.collecte"):
        collecte.collecter(sources={"rss"}, notifier=False)

    messages = [r.getMessage() for r in caplog.records if r.name == "veille.collecte"]
    assert "Total : 0 nouvelle(s) offre(s)" in messages
    assert [m for m in messages if not m.strip() or "\n" in m] == []


@pytest.fixture
def prevenues(monkeypatch, deux_nouvelles):
    """Les offres fraiches et l'adresse que recoivent les notifications."""
    lectures = iter([[{"id": 1, "score": 90}], [{"id": 1, "score": 90}, {"id": 2, "score": 80}]])
    monkeypatch.setattr(db, "offres_nouvelles_non_vues", lambda: next(lectures))
    recues: list[tuple[list, str]] = []
    monkeypatch.setattr(notifications, "prevenir_nouvelles_offres",
                        lambda fraiches, base_url="": recues.append((fraiches, base_url)))
    return recues


def test_les_notifications_suivent_l_origine_normalisee(appels, prevenues, monkeypatch):
    monkeypatch.setenv("VEILLE_EMPLOI_URL_PUBLIQUE", "https://Veille.Exemple.test:443/chemin")

    collecte.collecter(sources={"rss"}, sortie=lambda _: None)

    assert prevenues == [([{"id": 2, "score": 80}], "https://veille.exemple.test")]


def test_sans_origine_les_notifications_partent_sans_adresse(appels, prevenues, monkeypatch):
    monkeypatch.delenv("VEILLE_EMPLOI_URL_PUBLIQUE", raising=False)
    monkeypatch.delenv("VEILLE_URL", raising=False)

    collecte.collecter(sources={"rss"}, sortie=lambda _: None)

    assert prevenues == [([{"id": 2, "score": 80}], "")]


def test_sans_notification_rien_ne_part(appels, prevenues):
    collecte.collecter(sources={"rss"}, notifier=False, sortie=lambda _: None)

    assert prevenues == []
