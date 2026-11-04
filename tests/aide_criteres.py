"""Poser, le temps d'un test, un fichier de critères dérivé de la configuration par défaut."""

from __future__ import annotations

import copy

import yaml

from veille import config


def poser_criteres(monkeypatch, request, tmp_path, modifier=None):
    """Écrit une copie des critères par défaut, modifiée par `modifier(brut)`, et la désigne.

    Le cache de `charger_criteres` est vidé avant et après le test.
    """
    brut = copy.deepcopy(config.charger_criteres().brut)
    if modifier is not None:
        modifier(brut)
    chemin = tmp_path / "criteres.yaml"
    chemin.write_text(yaml.safe_dump(brut, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(config, "CHEMIN_CRITERES", chemin)
    config.recharger()
    request.addfinalizer(config.recharger)
    return chemin
