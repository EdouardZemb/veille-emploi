"""Ouvrir une session en base pour un client de test."""

from __future__ import annotations

from fastapi.testclient import TestClient

from veille import auth

ORIGINE = "http://testserver"


def connecter(client: TestClient) -> str:
    """Ouvre une session « test », pose le cookie et l'en-tete Origin, rend le jeton."""
    jeton = auth.ouvrir_session("test")
    client.cookies.set(auth.nom_cookie(), jeton)
    client.headers["Origin"] = ORIGINE
    return jeton
