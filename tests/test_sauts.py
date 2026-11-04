"""Un saut faute de dependance systeme, et la suite qui le refuse."""

from __future__ import annotations

from tests.sauts import sauter


def test_un_test_se_saute_faute_de_sa_dependance(monkeypatch):
    monkeypatch.delenv("SUITE_COMPLETE", raising=False)
    assert sauter(lambda: False)
    assert not sauter(lambda: True)


def test_une_suite_declaree_complete_ne_saute_rien(monkeypatch):
    """La CI et le serveur ont tout : une dependance perdue y echoue, au lieu
    de se sauter en silence derriere une ligne de `-rs` que personne ne lit."""
    monkeypatch.setenv("SUITE_COMPLETE", "1")

    def jamais_appelee() -> bool:
        raise AssertionError("une suite complete ne sonde pas la dependance")

    assert not sauter(jamais_appelee)
