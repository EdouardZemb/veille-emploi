"""Authentification par passkeys, sessions gardees en base.

POURQUOI : le tailnet n'est pas prive pour toi seul. D'autres appareils y sont,
et d'autres personnes peuvent le rejoindre pour d'autres projets. Sans ce
verrou, ta recherche d'emploi - candidatures, pretentions salariales, notes sur des
employeurs - serait lisible par tout appareil du reseau.

Mecanique : une passkey ouvre une session, un lien a usage unique en
enregistre une. Session gardee en base : le cookie porte un jeton au hasard, la
base n'en garde que l'empreinte. 180 jours, prolongee a l'usage,
`SameSite=Lax`, `Secure` des que la console est servie en HTTPS.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response, status

from . import db

NOM_BASE_COOKIE = "veille_session"
DUREE_SESSION = timedelta(days=180)
INTERVALLE_PROLONGATION = timedelta(hours=1)
DUREE_LIEN = timedelta(hours=24)
ORIGINES_LIEN = ("serveur", "appareil")

# --------------------------------------------------------------------------
# Sessions en base : le jeton part au client, la base n'en garde que l'empreinte
# --------------------------------------------------------------------------


def maintenant() -> datetime:
    """L'instant courant, en UTC (les tests le remplacent)."""
    return datetime.now(timezone.utc)


def _iso(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).isoformat(timespec="seconds")


def empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def appareil_depuis(user_agent: str) -> str:
    """Un nom lisible pour la liste des appareils. L'ordre compte."""
    ua = user_agent.lower()
    for marque, nom in (("android", "Android"), ("iphone", "iPhone"), ("ipad", "iPad"),
                        ("windows", "Windows"), ("macintosh", "Mac"), ("linux", "Linux")):
        if marque in ua:
            return nom
    return "Appareil"


def ouvrir_session(appareil: str) -> str:
    jeton = secrets.token_urlsafe(32)
    instant = maintenant()
    db.creer_session(empreinte(jeton), appareil, _iso(instant), _iso(instant + DUREE_SESSION))
    return jeton


def lire_session(jeton: str) -> dict | None:
    if not jeton:
        return None
    ligne = db.session_par_empreinte(empreinte(jeton))
    if ligne is None:
        return None
    instant = maintenant()
    if datetime.fromisoformat(ligne["expire_le"]) <= instant:
        return None
    prolongee = instant - datetime.fromisoformat(ligne["vue_le"]) > INTERVALLE_PROLONGATION
    if prolongee:
        ligne["vue_le"] = _iso(instant)
        ligne["expire_le"] = _iso(instant + DUREE_SESSION)
        db.prolonger_session(ligne["id"], ligne["vue_le"], ligne["expire_le"])
    ligne["prolongee"] = prolongee
    return ligne


def fermer_session(session_id: int) -> None:
    db.supprimer_session(session_id)


def retirer_passkey(passkey_id: int) -> bool:
    """Retire une passkey et ferme TOUTES les sessions ; faux si l'id est inconnu.

    Toutes : celui qui a ajoute sa passkey avec un cookie vole a aussi une
    session, et rien ne dit laquelle. Fermer une session ne retire pas la
    passkey de l'appareil : elle en rouvrirait une.
    """
    return db.retirer_passkey_et_sessions(passkey_id)


def _secure() -> bool:
    """Le cookie est `Secure` ; ce meme predicat decide du prefixe `__Host-`."""
    return os.environ.get("VEILLE_HTTPS", "1") == "1"


def nom_cookie() -> str:
    """`__Host-veille_session` sous HTTPS, `veille_session` sinon.

    Le prefixe `__Host-` exige `Secure`, `Path=/` et pas de `Domain` : un
    navigateur rejette le cookie qui le porte sans `Secure`."""
    return ("__Host-" if _secure() else "") + NOM_BASE_COOKIE


def poser_cookie(reponse: Response, jeton: str) -> None:
    reponse.set_cookie(
        nom_cookie(),
        jeton,
        max_age=int(DUREE_SESSION.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=_secure(),
        path="/",
    )


def effacer_cookie(reponse: Response) -> None:
    """Efface le cookie avec le nom et les attributs de `poser_cookie` : un
    effacement sans `Secure` ni `Path=/` est ignore pour un cookie `__Host-`."""
    reponse.delete_cookie(
        nom_cookie(),
        httponly=True,
        samesite="lax",
        secure=_secure(),
        path="/",
    )


def session_courante(request: Request) -> dict | None:
    """La session en base portee par le cookie de la requete, sinon None.

    Une session prolongee laisse son jeton dans `request.state` : le middleware
    `reposer_le_cookie` (app.py) repose le cookie sur la reponse, quelle que
    soit la route, page comprise, et meme si elle rend sa propre `Response`.
    """
    jeton = request.cookies.get(nom_cookie(), "")
    session = lire_session(jeton)
    if session is not None and session["prolongee"]:
        request.state.cookie_a_reposer = jeton
    return session


def cookie_a_reposer(request: Request) -> str | None:
    """Le jeton d'une session prolongee pendant cette requete, sinon None."""
    return getattr(request.state, "cookie_a_reposer", None)


def exiger_session(request: Request) -> dict:
    """Dependance FastAPI a poser sur toute route non publique.

    En `def` : elle lit et ecrit la base, FastAPI la fait tourner dans un fil.
    """
    session = session_courante(request)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session requise")
    return session


# --------------------------------------------------------------------------
# Liens de connexion : 24 heures, un seul usage
# --------------------------------------------------------------------------


def creer_lien(origine: str) -> str:
    if origine not in ORIGINES_LIEN:
        raise ValueError(f"origine de lien inconnue : {origine!r}")
    jeton = secrets.token_urlsafe(32)
    instant = maintenant()
    db.creer_lien(empreinte(jeton), origine, _iso(instant), _iso(instant + DUREE_LIEN))
    return jeton


def lien_ouvert(jeton: str) -> int | None:
    """L'id du lien ouvert qui porte ce jeton, sinon None.

    Chaque lien ouvert est compare, sans rien chercher en SQL : le temps de
    reponse ne dit pas si une empreinte existe.
    """
    if not jeton:
        return None
    calculee = empreinte(jeton)
    trouve = None
    for lien in db.liens_ouverts(_iso(maintenant())):
        if hmac.compare_digest(calculee, lien["empreinte"]):
            trouve = lien["id"]
    return trouve


def consommer_lien(lien_id: int) -> bool:
    return db.consommer_lien(lien_id, _iso(maintenant()))
