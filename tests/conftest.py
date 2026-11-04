"""Isolation des tests.

Les chemins de la base et des cles sont lus a l'import
des modules : on les redirige vers un dossier temporaire AVANT toute
importation de `veille`, sinon les tests ecriraient dans la vraie base.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEMPORAIRE = Path(tempfile.mkdtemp(prefix="veille-tests-"))

# Affectes, jamais `setdefault` : la suite tourne aussi sur le serveur, et une
# variable exportee dans le shell l'enverrait sur les vrais fichiers
# (tests/test_isolation.py).
os.environ["VEILLE_DB"] = str(_TEMPORAIRE / "veille.sqlite3")
os.environ["VEILLE_URL"] = "http://testserver"
os.environ["VEILLE_VAPID"] = str(_TEMPORAIRE / "vapid.json")
os.environ["VEILLE_DOSSIERS"] = str(_TEMPORAIRE / "dossiers")
# Un fichier absent : importer `veille.cli` chargerait sinon `config/.env`, et sur
# le serveur ses vraies valeurs entreraient dans toute la suite.
os.environ["VEILLE_ENV"] = str(_TEMPORAIRE / "aucun.env")
# La suite tourne sur l'exemple, jamais sur la configuration d'une instance : sur le
# serveur, `VEILLE_CONFIG` et `VEILLE_KIT` la designent, et un test qui en lirait les
# valeurs casserait a chaque reglage. `VEILLE_CRITERES` et `VEILLE_SOURCES` sont
# retirees : elles l'emporteraient sur `VEILLE_CONFIG`. La configuration reelle se
# verifie hors de la suite, par `veille config verifier` (etape de la CI).
_EXEMPLE = Path(__file__).resolve().parent.parent / "exemple"
os.environ["VEILLE_CONFIG"] = str(_EXEMPLE)
os.environ["VEILLE_KIT"] = str(_EXEMPLE / "gabarits")
for _nom in ("VEILLE_CRITERES", "VEILLE_SOURCES"):
    os.environ.pop(_nom, None)
# Les cookies de session ne doivent pas exiger HTTPS sous le client de test.
os.environ["VEILLE_HTTPS"] = "0"
# Les variables du conteneur ont l'absence pour valeur neutre : une valeur exportee
# (sur le serveur, ou dans un shell de deploiement) ne doit pas entrer dans la suite.
for _nom in ("VEILLE_EMPLOI_ENV", "VEILLE_EMPLOI_URL_PUBLIQUE", "VEILLE_EMPLOI_VERSION"):
    os.environ.pop(_nom, None)


import pytest  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


class _Horloge:
    def __init__(self) -> None:
        self.instant = T0

    def avancer(self, **kwargs) -> None:
        self.instant += timedelta(**kwargs)


@pytest.fixture
def horloge(monkeypatch):
    """Horloge reglable : remplace `veille.auth.maintenant`, part de T0."""
    from veille import auth

    h = _Horloge()
    monkeypatch.setattr(auth, "maintenant", lambda: h.instant)
    return h


@pytest.fixture(autouse=True)
def _remise_a_zero_de_la_connexion():
    """Ni les budgets des limites ni les ceremonies ne passent d'un test a l'autre.

    Sans importer `veille.app` s'il ne l'est pas deja : l'importer ici le
    chargerait avant que les tests qui reglent l'environnement aient parle."""
    import sys

    if "veille.app" in sys.modules:
        sys.modules["veille.app"].LIMITE_AUTH.vider()
        sys.modules["veille.app"].LIMITE_GLOBALE.vider()
    if "veille.passkeys" in sys.modules:
        sys.modules["veille.passkeys"].oublier_ceremonies()
    yield
