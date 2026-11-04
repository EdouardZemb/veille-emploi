"""Le parcours de connexion dans un vrai Chromium, avec un authentificateur virtuel.

Comme tests/conftest.py : les chemins et l'origine sont lus a l'import de
`veille`, on les affecte AVANT toute importation. L'origine est
http://localhost:<port> : WebAuthn exige un contexte securise, et `localhost` en est un.
"""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
import urllib.request
from pathlib import Path


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_TEMPORAIRE = Path(tempfile.mkdtemp(prefix="veille-navigateur-"))
PORT = _port_libre()
URL = f"http://localhost:{PORT}"

# Affectes, jamais `setdefault` (voir tests/conftest.py).
os.environ["VEILLE_DB"] = str(_TEMPORAIRE / "veille.sqlite3")
os.environ["VEILLE_URL"] = URL
os.environ["VEILLE_VAPID"] = str(_TEMPORAIRE / "vapid.json")
os.environ["VEILLE_DOSSIERS"] = str(_TEMPORAIRE / "dossiers")
# Le cookie de session ne doit pas etre `Secure` sur http.
os.environ["VEILLE_HTTPS"] = "0"

import pytest  # noqa: E402
import uvicorn  # noqa: E402


@pytest.fixture(scope="session")
def serveur():
    from veille.app import app

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    srv = uvicorn.Server(config)
    fil = threading.Thread(target=srv.run, daemon=True)
    fil.start()
    try:
        limite = time.monotonic() + 20
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/sante", timeout=1) as r:
                    if r.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() > limite:
                raise RuntimeError("le serveur n'a pas demarre")
            time.sleep(0.1)
        yield URL
    finally:
        srv.should_exit = True
        fil.join(timeout=10)


@pytest.fixture(scope="session")
def navigateur():
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        b = pw.chromium.launch()
        try:
            yield b
        finally:
            b.close()
    finally:
        pw.stop()


def appareil(navigateur):
    """Un appareil : un contexte neuf, avec son authentificateur WebAuthn virtuel."""
    contexte = navigateur.new_context()
    page = contexte.new_page()
    cdp = contexte.new_cdp_session(page)
    cdp.send("WebAuthn.enable")
    cdp.send(
        "WebAuthn.addVirtualAuthenticator",
        {
            "options": {
                "protocol": "ctap2",
                "transport": "internal",
                "hasResidentKey": True,
                "hasUserVerification": True,
                "isUserVerified": True,
                "automaticPresenceSimulation": True,
            }
        },
    )
    return page
