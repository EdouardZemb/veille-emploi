"""Une variable d'environnement inconnue doit echouer, pas etre ignoree.

Ce fichier existe a cause d'un incident precis. En deboguant, j'ai pose
`VEILLE_BASE=/tmp/x.sqlite` pour isoler un script de la vraie base. Le nom
exact est `VEILLE_DB`. Personne ne lit `VEILLE_BASE` : le script a tourne sur
la BASE REELLE d'Edouard et y a ecrit une offre de test.

La faute de frappe rejouera — c'est certain. Ce qui ne doit plus se produire,
c'est qu'un nom inconnu ne fasse RIEN. Poser une variable exprime une
intention ; l'ignorer en silence trahit cette intention exactement au moment
ou l'on se croit protege.
"""

from __future__ import annotations

import pytest

from veille import config


def test_le_nom_exact_est_accepte():
    assert config.variables_inconnues({"VEILLE_DB": "/tmp/x"}) == []


def test_le_nom_qui_a_cause_lincident_est_refuse():
    inconnues = config.variables_inconnues({"VEILLE_BASE": "/tmp/x"})
    assert inconnues, "VEILLE_BASE doit etre refusee"
    nom, proche = inconnues[0]
    assert nom == "VEILLE_BASE"
    assert proche == "VEILLE_DB", f"la suggestion doit guider, pas juste refuser : {proche!r}"


def test_lerreur_nomme_la_variable_et_explique_le_risque():
    with pytest.raises(config.VariableInconnue) as exc:
        config.verifier_environnement({"VEILLE_BASE": "/tmp/x"})
    message = str(exc.value)
    assert "VEILLE_BASE" in message
    assert "VEILLE_DB" in message, "la suggestion doit figurer dans le message"
    assert "VRAIE base" in message, "le risque doit etre dit, pas seulement l'erreur"


@pytest.mark.parametrize("nom", [
    "VEILLE_DATABASE", "VEILLE_SQLITE", "VEILLE_CHEMIN_DB",
    "VEILLE_IMAP_PASSWORD", "VEILLE_MDP", "FT_CLIENT", "FT_SECRET",
])
def test_les_variantes_plausibles_sont_toutes_refusees(nom):
    assert config.variables_inconnues({nom: "x"}), f"{nom} devrait etre refusee"


@pytest.mark.parametrize("nom", sorted(config.VARIABLES_CONNUES))
def test_toute_variable_declaree_est_acceptee(nom):
    assert config.variables_inconnues({nom: "x"}) == []


def test_les_variables_etrangeres_au_projet_sont_ignorees():
    """On ne surveille que nos prefixes : PATH, HOME, LANG ne nous regardent pas."""
    assert config.variables_inconnues({"PATH": "/usr/bin", "HOME": "/home/camille",
                                       "PYTHONPATH": "src"}) == []


def test_toute_variable_lue_dans_le_code_est_declaree():
    """Le garde-fou doit suivre le code, sinon il bloquera une vraie variable.

    Si quelqu'un ajoute `os.environ.get("VEILLE_NOUVEAU")` sans l'inscrire dans
    VARIABLES_CONNUES, le programme refuserait de demarrer chez Edouard. Ce
    test attrape l'oubli ici.
    """
    import re
    from pathlib import Path

    racine = Path(config.__file__).resolve().parent
    lues = set()
    for fichier in racine.rglob("*.py"):
        lues |= set(re.findall(r'"((?:VEILLE|FT)_[A-Z_]+)"',
                               fichier.read_text(encoding="utf-8")))
    manquantes = lues - set(config.VARIABLES_CONNUES)
    assert not manquantes, (
        f"variables lues par le code mais absentes de VARIABLES_CONNUES : {sorted(manquantes)}"
    )


def test_les_variables_du_deploiement_sont_connues():
    assert config.variables_inconnues({
        "VEILLE_EMPLOI_ENV": "prod",
        "VEILLE_EMPLOI_VERSION": "1.2.3",
        "VEILLE_EMPLOI_URL_PUBLIQUE": "https://x.invalid",
    }) == []


@pytest.mark.parametrize("valeur, attendu", [
    (None, None),
    ("", None),
    (" prod ", "prod"),
])
def test_environnement(monkeypatch, valeur, attendu):
    if valeur is None:
        monkeypatch.delenv("VEILLE_EMPLOI_ENV", raising=False)
    else:
        monkeypatch.setenv("VEILLE_EMPLOI_ENV", valeur)
    assert config.environnement() == attendu
