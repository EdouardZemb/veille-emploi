"""Console de recherche d'emploi - application web.

Une seule page : voir, trier, declencher, piloter. L'API JSON derriere sert la
page et, accessoirement, permet de scripter depuis un terminal.

Exposition : sur le serveur du tailnet, uvicorn ecoute sur 127.0.0.1, derriere
`tailscale serve`. Dans son conteneur (ADR-0002), la console ecoute sur
0.0.0.0:8460 ; le port n'est publie que sur la boucle locale de l'hote, et
l'acces public passe par le tunnel commun.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import auth, config, db, documents, dossier, enrichissement, factice, notifications, passkeys, reglages
from .config import CHEMIN_DOSSIERS, CHEMIN_KIT, charger_criteres, recharger
from .debit import LimiteDebit, cle_client
from .models import STATUTS
from .planificateur import PLANIFICATEUR

log = logging.getLogger(__name__)

ICI = Path(__file__).resolve().parent

@asynccontextmanager
async def cycle_de_vie(_: FastAPI):
    config.exiger_configuration()  # en prod, sans configuration : pas de console
    db.initialiser()
    reglages.initialiser()
    try:
        passkeys.origine_attendue()
    except passkeys.OrigineInconnue:
        log.error("VEILLE_URL n'est pas definie - la connexion par passkey est indisponible.")
    else:
        if db.compter_passkeys() == 0:
            log.warning(
                "AUCUNE PASSKEY - lance : veille lien, puis ouvre le lien sur ton telephone"
            )
    mode = config.environnement()
    if mode is not None:
        # en conteneur, les cles des notifications naissent ici (`veille init` n'y passe pas)
        if not notifications.CHEMIN_VAPID.exists():
            # le sujet VAPID part avec chaque push : l'origine publique, jamais une adresse reelle
            notifications.generer_vapid(
                sujet=notifications.sujet_par_defaut())
        if mode == "staging":
            factice.charger_au_demarrage()
    PLANIFICATEUR.demarrer()  # purge tout de suite, puis le fil (planificateur.py)
    try:
        yield
    finally:
        PLANIFICATEUR.arreter()


app = FastAPI(title="Veille emploi", docs_url=None, redoc_url=None, lifespan=cycle_de_vie)
app.mount("/static", StaticFiles(directory=ICI / "static"), name="static")
gabarits = Jinja2Templates(directory=str(ICI / "templates"))

# 20 demandes par minute et par client pour les quatre routes qu'on appelle sans
# session, plus un plafond global de 200 : derriere le tunnel ou `tailscale
# serve`, tout arrive de la meme adresse, le client se lit dans
# `CF-Connecting-IP` (voir debit.py). Les routes a session ne comptent pas : qui
# use le budget bloque la connexion et l'ajout d'un appareil, jamais une
# session deja ouverte.
LIMITE_AUTH = LimiteDebit(20, timedelta(minutes=1))
LIMITE_GLOBALE = LimiteDebit(200, timedelta(minutes=1))
ROUTES_ANONYMES = frozenset({
    "/api/auth/lien/options",
    "/api/auth/lien",
    "/api/auth/connexion/options",
    "/api/auth/connexion",
})

METHODES_ECRITURE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _erreur(statut: int, code: str) -> JSONResponse:
    return JSONResponse({"erreur": code}, status_code=statut)


def _refus_sans_configuration() -> JSONResponse | None:
    """Le refus des routes qui noteraient des offres : sans configuration designee,
    elles le feraient avec l'exemple. None quand une configuration est designee."""
    if config.config_designee():
        return None
    return _erreur(409, "configuration_non_designee")


def _sert_l_exemple_par_oubli() -> bool:
    """Une console sans conteneur sert une instance : si rien n'est désigné, elle sert
    l'exemple par oubli de VEILLE_CONFIG. Le staging et la CI le servent par contrat."""
    return config.environnement() is None and not config.config_designee()


def _refus_sans_configuration_hors_conteneur() -> JSONResponse | None:
    """Le refus des gestes sur une offre (générer un dossier ou une relance, la recalculer,
    affiner sa lettre) quand la console sert l'exemple par oubli : ils emploieraient ses
    critères, ses gabarits et sa consigne, au nom de Camille Exemple. Le staging et la CI les
    gardent ; les lectures restent ouvertes. None sinon."""
    if _sert_l_exemple_par_oubli():
        return _erreur(409, "configuration_non_designee")
    return None


# --------------------------------------------------------------------------
# Cookie, debit et origine, autour de chaque requete
#
# Starlette enveloppe chaque middleware autour des precedents : le DERNIER
# declare voit la requete le premier. L'origine est declaree apres le debit
# pour passer avant lui : une page etrangere n'use pas le budget.
# --------------------------------------------------------------------------


@app.middleware("http")
async def reposer_le_cookie(request: Request, suite):
    """Une session prolongee pendant la requete repose son cookie (180 jours de
    plus), quelle que soit la route. Sauf si la reponse pose deja le cookie :
    une session fermee l'efface, une session ouverte pose le sien."""
    reponse = await suite(request)
    jeton = auth.cookie_a_reposer(request)
    if jeton and not any(entete.startswith(f"{auth.nom_cookie()}=")
                         for entete in reponse.headers.getlist("set-cookie")):
        auth.poser_cookie(reponse, jeton)
    return reponse


@app.middleware("http")
async def limiter_le_debit(request: Request, suite):
    if request.method == "POST" and request.url.path in ROUTES_ANONYMES:
        cle = cle_client(request)
        # Une demande refusee ne compte nulle part : le client d'abord (refuse, il
        # ne touche pas le plafond global), puis le global, et le client n'est
        # compte qu'une fois les deux acceptes. Deux verrous distincts : une course
        # entre `disponible` et `enregistrer` peut laisser passer une demande de plus.
        if not LIMITE_AUTH.disponible(cle) or not LIMITE_GLOBALE.autoriser():
            return _erreur(429, "trop_de_demandes")
        LIMITE_AUTH.enregistrer(cle)
    return await suite(request)


@app.middleware("http")
async def controler_l_origine(request: Request, suite):
    """Toute ecriture vient de la console elle-meme, en-tete absent compris :
    l'API, et aussi `POST /deconnexion`."""
    chemin = request.url.path
    if request.method in METHODES_ECRITURE:
        try:
            attendue, _ = passkeys.origine_attendue()
        except passkeys.OrigineInconnue:
            # Le controle n'a pas pu tourner : rien ne passe. La connexion le dit
            # (503, que sa page traduit) ; le reste de l'API refuse l'origine.
            if chemin.startswith("/api/auth/"):
                return _erreur(503, "origine_inconnue")
            return _erreur(403, "origine")
        if request.headers.get("origin") != attendue:
            return _erreur(403, "origine")
    return await suite(request)


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; "
       "frame-ancestors 'none'; form-action 'self'")


# Declare en dernier : il voit la requete le premier et enveloppe tout, refus de
# l'origine (403) et du debit (429) compris.
@app.middleware("http")
async def en_tetes_de_securite(request: Request, suite):
    reponse = await suite(request)
    # setdefault : une route qui pose sa propre CSP, plus stricte, n'est pas ecrasee.
    reponse.headers.setdefault("Content-Security-Policy", CSP)
    # same-origin et non no-referrer : sous no-referrer, Chromium envoie `Origin: null` avec un
    # formulaire du meme site, et controler_l_origine refuse POST /deconnexion. same-origin
    # n'envoie jamais l'adresse a un autre site.
    reponse.headers.setdefault("Referrer-Policy", "same-origin")
    return reponse


@app.exception_handler(passkeys.OrigineInconnue)
async def origine_inconnue(_request: Request, _exc: passkeys.OrigineInconnue):
    return _erreur(503, "origine_inconnue")


# --------------------------------------------------------------------------
# Connexion
# --------------------------------------------------------------------------



def empreinte_statique(nom: str) -> str:
    """Suffixe d'URL derive du contenu du fichier.

    Sans lui, le navigateur — et surtout la PWA installee — continue de servir
    l'ancienne feuille de style apres une mise a jour. Vu a l'ecran : les
    nouveaux reperes s'affichaient en texte brut parce que le CSS datait.
    """
    from hashlib import blake2s

    chemin = Path(__file__).resolve().parent / "static" / nom
    try:
        return blake2s(chemin.read_bytes(), digest_size=6).hexdigest()
    except OSError:
        return "0"


@app.get("/connexion", response_class=HTMLResponse)
def page_connexion(request: Request, erreur: str = ""):
    if auth.session_courante(request):
        return RedirectResponse("/", status_code=303)
    try:
        passkeys.origine_attendue()
        origine_connue = True
    except passkeys.OrigineInconnue:
        origine_connue = False
    # Signature Starlette actuelle : (request, nom, contexte).
    return gabarits.TemplateResponse(
        request,
        "connexion.html",
        {
            "erreur": erreur,
            "nb_passkeys": db.compter_passkeys(),
            "origine_connue": origine_connue,
            "v_js": empreinte_statique("connexion.js"),
        },
    )


@app.get("/lien", response_class=HTMLResponse)
def page_lien(request: Request):
    """La page d'un lien de connexion, sans session. Le jeton est dans le
    fragment : il n'arrive jamais ici, seulement dans le corps de
    `POST /api/auth/lien/options`."""
    return gabarits.TemplateResponse(
        request, "lien.html", {"v_js": empreinte_statique("connexion.js")}
    )


@app.post("/deconnexion")
def deconnexion(request: Request):
    session = auth.session_courante(request)
    if session is not None:
        auth.fermer_session(session["id"])
    reponse = RedirectResponse("/connexion", status_code=303)
    auth.effacer_cookie(reponse)
    return reponse


# --------------------------------------------------------------------------
# Passkeys : le lien enregistre une passkey, la passkey ouvre une session
#
# Le texte d'un refus (`CeremonieInvalide`) ne part jamais au client : il
# porte la raison, en partie fournie par le client. Seuls les codes fixes
# sortent ; la raison est deja au journal (passkeys.py).
# --------------------------------------------------------------------------


class DemandeLien(BaseModel):
    jeton: str = ""


class ReponseCeremonie(BaseModel):
    cle: str = ""
    reponse: Any = None


def _appareil(request: Request) -> str:
    return auth.appareil_depuis(request.headers.get("user-agent", ""))


def _session_ouverte(appareil: str) -> JSONResponse:
    reponse = JSONResponse({"ok": True})
    auth.poser_cookie(reponse, auth.ouvrir_session(appareil))
    return reponse


@app.post("/api/auth/lien/options")
def api_lien_options(corps: DemandeLien):
    """Le lien est verifie, pas consomme : un double appui ouvre deux
    ceremonies, et seule la premiere inscription verifiee le consomme."""
    lien_id = auth.lien_ouvert(corps.jeton)
    if lien_id is None:
        return _erreur(400, "lien_invalide")
    cle, options = passkeys.options_inscription(lien_id)
    return {"cle": cle, "options": options}


@app.post("/api/auth/lien")
def api_lien(request: Request, corps: ReponseCeremonie):
    """L'inscription est verifiee, PUIS le lien consomme : un lien deja servi
    n'enregistre rien et n'ouvre aucune session."""
    try:
        inscription = passkeys.verifier_inscription(corps.cle, corps.reponse)
    except passkeys.CeremonieInvalide:
        return _erreur(400, "lien_invalide")
    if not auth.consommer_lien(inscription.lien_id):
        log.warning("passkeys, inscription refusee : lien deja consomme")
        return _erreur(400, "lien_invalide")
    appareil = _appareil(request)
    try:
        db.enregistrer_passkey(
            inscription.identifiant,
            inscription.cle_publique,
            inscription.compteur,
            inscription.transports,
            appareil,
            auth._iso(auth.maintenant()),
        )
    except sqlite3.IntegrityError:
        # Le meme identifiant deja en base : un refus, jamais une 500.
        log.warning("passkeys, inscription refusee : passkey deja enregistree")
        return _erreur(400, "lien_invalide")
    return _session_ouverte(appareil)


@app.post("/api/auth/connexion/options")
def api_connexion_options():
    cle, options = passkeys.options_connexion()
    return {"cle": cle, "options": options}


@app.post("/api/auth/connexion")
def api_connexion(request: Request, corps: ReponseCeremonie):
    try:
        passkeys.verifier_connexion(corps.cle, corps.reponse)
    except passkeys.CeremonieInvalide:
        return _erreur(400, "connexion_impossible")
    return _session_ouverte(_appareil(request))


# --------------------------------------------------------------------------
# Appareils : les sessions ouvertes, et un lien pour en ajouter un
# --------------------------------------------------------------------------


def _sessions_ouvertes() -> list[dict]:
    return db.lister_sessions(auth._iso(auth.maintenant()))


@app.get("/api/auth/appareils")
def api_appareils(session: dict = Depends(auth.exiger_session)):
    """Les sessions ouvertes, et les passkeys en lecture seule : une passkey
    inconnue doit se remarquer. Elle se retire sur le serveur
    (`veille passkeys --retirer`), jamais d'ici."""
    return {
        "sessions": [
            {
                "id": s["id"],
                "appareil": s["appareil"],
                "cree_le": s["cree_le"],
                "vue_le": s["vue_le"],
                "courante": s["id"] == session["id"],
            }
            for s in _sessions_ouvertes()
        ],
        # Ni la cle publique ni l'identifiant WebAuthn.
        "passkeys": [
            {
                "id": p["id"],
                "appareil": p["appareil"],
                "cree_le": p["cree_le"],
                "utilisee_le": p["utilisee_le"],
            }
            for p in db.lister_passkeys()
        ],
    }


@app.delete("/api/auth/sessions/{session_id}")
def api_deconnecter(session_id: int, session: dict = Depends(auth.exiger_session)):
    if all(s["id"] != session_id for s in _sessions_ouvertes()):
        return _erreur(404, "inconnue")
    auth.fermer_session(session_id)
    reponse = JSONResponse({"ok": True})
    if session_id == session["id"]:
        auth.effacer_cookie(reponse)
    return reponse


@app.post("/api/auth/lien/creer", dependencies=[Depends(auth.exiger_session)])
def api_lien_creer(corps: ReponseCeremonie):
    """Une session volee ne suffit pas a enregistrer une passkey de plus : il
    faut une touche de passkey fraiche (la ceremonie de connexion, a usage
    unique, valable cinq minutes). Aucune session n'est ouverte ici."""
    origine, _rp_id = passkeys.origine_attendue()  # OrigineInconnue -> 503
    try:
        passkeys.verifier_connexion(corps.cle, corps.reponse)
    except passkeys.CeremonieInvalide:
        return _erreur(400, "connexion_impossible")
    jeton = auth.creer_lien("appareil")
    lien_id = auth.lien_ouvert(jeton)
    expire_le = next(
        (lien["expire_le"] for lien in db.liens_ouverts(auth._iso(auth.maintenant()))
         if lien["id"] == lien_id),
        None,
    )
    return {"adresse": f"{origine}/lien#{jeton}", "expire_le": expire_le}


# --------------------------------------------------------------------------
# Page principale
# --------------------------------------------------------------------------


def _atout_mis_en_avant(criteres) -> dict[str, str] | None:
    """L'atout que la console met en avant, `{cle, libelle, titre, bouton, bouton_titre}`, ou None.

    C'est `atouts.<a>.mis_en_avant` de `criteres.yaml` (un seul atout au plus ;
    s'il y en a plusieurs, le premier). Le JavaScript ne connait aucune cle.
    """
    for cle, atout in criteres.atouts.items():
        info = (atout or {}).get("mis_en_avant")
        if isinstance(info, dict):
            return {
                "cle": cle,
                "libelle": str(info.get("libelle") or atout.get("libelle") or cle),
                "titre": str(info.get("titre") or ""),
                # le bouton de filtre de la barre : son texte, sinon celui de l'etiquette
                "bouton": str(info.get("bouton") or info.get("libelle") or atout.get("libelle") or cle),
                "bouton_titre": str(info.get("bouton_titre") or info.get("titre") or ""),
            }
    return None


@app.get("/", response_class=HTMLResponse)
def console(request: Request):
    if not auth.session_courante(request):
        return RedirectResponse("/connexion", status_code=303)
    criteres = charger_criteres()
    cles = notifications.charger_vapid()
    return gabarits.TemplateResponse(
        request,
        "index.html",
        {
            "statuts": STATUTS,
            "v_css": empreinte_statique("style.css"),
            "v_js": empreinte_statique("app.js"),
            "familles": {k: v.get("libelle", k) for k, v in criteres.familles.items()},
            "zones": {k: v.get("libelle", k) for k, v in criteres.zones.items()},
            "atouts": {k: v.get("libelle", k) for k, v in criteres.atouts.items()},
            "seuil_interessant": reglages.lire_seuil(),
            "cle_vapid": cles.publique if cles else "",
            "atout_mis_en_avant": _atout_mis_en_avant(criteres),
            "sert_l_exemple": _sert_l_exemple_par_oubli(),
        },
    )


# --------------------------------------------------------------------------
# API - offres
# --------------------------------------------------------------------------


@app.get("/api/offres", dependencies=[Depends(auth.exiger_session)])
def api_offres(
    statut: str | None = None,
    zone: str | None = None,
    famille: str | None = None,
    atout: str | None = None,
    source: str | None = None,
    recherche: str | None = None,
    inclure_ecartees: bool = False,
    verification: str | None = None,
    tri: str | None = None,
    a_documenter: bool = False,
    limite: int = 200,
):
    from . import completude as _completude

    offres = db.lister_offres(
            verification=verification,
            tri=tri,
            statut=statut,
            zone=zone,
            famille=famille,
            atout=atout,
            source=source,
            recherche=recherche,
            inclure_ecartees=inclure_ecartees,
            limite=limite,
    )
    # La complétude voyage AVEC l'offre, mais dans sa propre clé : les deux axes
    # ne se rencontrent jamais dans un meme nombre.
    for o in offres:
        o["completude"] = _completude.evaluer(o).as_dict()

    # « A documenter » : fort potentiel, information trop mince. C'est le
    # croisement des DEUX axes — et il ne peut se calculer qu'ici, une fois la
    # complétude attachee. Le compte voyage avec la liste pour que le bouton
    # puisse l'afficher sans une requete de plus.
    seuil_score = reglages.lire_seuil()

    def a_travailler(o):
        return (o["score"] >= seuil_score
                and not o["completude"]["suffisant_pour_dossier"]
                and o["statut"] not in ("ecartee", "differee"))

    compte = sum(1 for o in offres if a_travailler(o))
    if a_documenter:
        offres = [o for o in offres if a_travailler(o)]
    return {"offres": offres, "a_documenter": compte}


@app.get("/api/affinement", dependencies=[Depends(auth.exiger_session)])
def api_affinement_etat():
    """L'affinement est-il utilisable, et qu'est-ce qui partirait ?"""
    from . import affinement

    d = affinement.disponible()
    return {"possible": d.possible, "raison": d.raison, "ce_qui_part": d.ce_qui_part}


@app.post("/api/offres/{offre_id}/affiner", dependencies=[Depends(auth.exiger_session)])
def api_affiner(offre_id: int):
    """Retravaille la lettre DEJA assemblee. Sur demande, jamais automatique.

    La version assemblee n'est pas ecrasee : elle reste sur le disque sous
    `lettre-de-motivation.md`, et la proposition est ecrite a cote. Il doit
    pouvoir revenir en un geste sur un texte qu'il ne reconnait pas.
    """
    from pathlib import Path as _P

    from . import affinement

    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    offre = db.lire_offre(offre_id)
    if not offre:
        raise HTTPException(404, "offre inconnue")
    if not offre.get("dossier_chemin"):
        raise HTTPException(400, "genere d'abord le dossier")
    base = _P(offre["dossier_chemin"])
    source = base / "lettre-de-motivation.md"
    if not source.exists():
        raise HTTPException(404, "lettre introuvable")

    r = affinement.affiner(source.read_text(encoding="utf-8"),
                           offre.get("description") or "")
    if r.ok:
        (base / "lettre-affinee.md").write_text(r.texte, encoding="utf-8")
        db.journaliser(offre_id, "lettre_affinee", "proposition enregistree")
    return r.as_dict()


@app.post("/api/offres/{offre_id}/affiner/appliquer", dependencies=[Depends(auth.exiger_session)])
def api_appliquer_affinement(offre_id: int):
    """Il a relu et il garde la proposition : elle devient la lettre."""
    from pathlib import Path as _P

    from . import dossier as _dossier

    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    offre = db.lire_offre(offre_id)
    if not offre or not offre.get("dossier_chemin"):
        raise HTTPException(404, "aucun dossier")
    base = _P(offre["dossier_chemin"])
    proposition = base / "lettre-affinee.md"
    if not proposition.exists():
        raise HTTPException(404, "aucune proposition a appliquer")
    from . import lettre as _lettre

    # L'ETAT COURANT ENTRE DANS L'HISTORIQUE AVANT D'ETRE REMPLACE. Le nom du
    # fichier d'historique dit QUOI — `003-20261010T2148-assemblee.md` — ce que
    # `lettre-assemblee.md` ne faisait plus des la deuxieme application : il
    # recevait la version COURANTE, donc apres deux affinements il contenait le
    # premier affinement, et « retour a la version assemblee » restaurait un
    # texte produit par un modele.
    courante = _lettre.lire(base)
    _lettre.historiser(base, courante.etat)

    # `lettre-assemblee.md` est garde pour la compatibilite, mais N'EST PLUS
    # ECRASE : il conserve la premiere assemblee, celle que son nom promet.
    ancienne = base / "lettre-assemblee.md"
    if not ancienne.exists():
        ancienne.write_text(
            (base / "lettre-de-motivation.md").read_text(encoding="utf-8"),
            encoding="utf-8")

    (base / "lettre-de-motivation.md").write_text(
        proposition.read_text(encoding="utf-8"), encoding="utf-8")
    _lettre.historiser(base, "affinee")
    resultat = _dossier.regenerer_pdf(base)
    db.journaliser(offre_id, "lettre_affinee_appliquee", "")
    return {"ok": True, "pdf": resultat}


@app.post("/api/offres/{offre_id}/affiner/annuler", dependencies=[Depends(auth.exiger_session)])
def api_annuler_affinement(offre_id: int):
    """Retour a la version assemblee, en un geste."""
    from pathlib import Path as _P

    from . import dossier as _dossier

    # Le PDF refait porterait le prefixe de l'exemple (`rendu.prefixe()`).
    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    offre = db.lire_offre(offre_id)
    if not offre or not offre.get("dossier_chemin"):
        raise HTTPException(404, "aucun dossier")
    from . import lettre as _lettre

    base = _P(offre["dossier_chemin"])

    # LA VERSION ASSEMBLEE, VRAIMENT. On demande a l'historique la derniere
    # version etiquetee `assemblee`, et on ne se rabat sur
    # `lettre-assemblee.md` que faute d'historique — dossier genere avant.
    v = _lettre.derniere_version(base, "assemblee")
    if v is not None:
        contenu = _lettre.texte_de_version(base, v.numero)
        origine = f"historique {v.fichier}"
    else:
        assemblee = base / "lettre-assemblee.md"
        if not assemblee.exists():
            raise HTTPException(404, "aucune version assemblee conservee")
        contenu = assemblee.read_text(encoding="utf-8")
        origine = "lettre-assemblee.md"

    # Ce qu'on remplace entre d'abord dans l'historique : un retour arriere est
    # une NOUVELLE VERSION, jamais une suppression.
    _lettre.historiser(base, "avant-retour-arriere")
    (base / "lettre-de-motivation.md").write_text(contenu, encoding="utf-8")
    _lettre.historiser(base, "assemblee-restauree")
    resultat = _dossier.regenerer_pdf(base)
    db.journaliser(offre_id, "lettre_assemblee_restauree", origine)
    return {"ok": True, "pdf": resultat, "origine": origine}


@app.get("/api/archive", dependencies=[Depends(auth.exiger_session)])
def api_offres_archivees(depuis: str | None = None, limite: int = 200):
    """Les offres retirees du site.

    Rien n'est supprime : elles gardent leur score, leur explication et leurs
    notes. `nouvelles` compte ce qui est parti a l'archive depuis sa derniere
    visite — une archive automatique ne doit jamais etre invisible.
    """
    return {
        "offres": db.lister_archivees(limite=limite),
        "nouvelles": db.compter_archivees_depuis(depuis),
    }


@app.post("/api/offres/{offre_id}/desarchiver", dependencies=[Depends(auth.exiger_session)])
def api_desarchiver(offre_id: int):
    """Il la ressort. On ne la rearchivera JAMAIS automatiquement."""
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    db.desarchiver(offre_id)
    return {"ok": True, "offre": db.lire_offre(offre_id)}


@app.post("/api/offres/{offre_id}/verifier", dependencies=[Depends(auth.exiger_session)])
def api_verifier_offre(offre_id: int):
    """Verification a la demande, declenchee par lui, sur UNE offre."""
    from . import verification

    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    d = verification.verifier_offre(offre_id, enrichir=True)
    return {
        "verdict": d.verdict, "detail": d.detail, "archivee": d.archivee,
        "protegee": d.protegee, "enrichie": d.enrichie,
        "offre": db.lire_offre(offre_id),
    }


@app.post("/api/offres/{offre_id}/constat", dependencies=[Depends(auth.exiger_session)])
def api_constat(offre_id: int, en_ligne: bool = False):
    """Son constat a lui, en un appel, dans les deux sens.

    `en_ligne=false` archive immediatement : il a regarde, ca vaut preuve.
    `en_ligne=true` la ressort et la protege d'un rearchivage automatique.
    C'est la reponse aux offres qu'on n'a pas le droit de sonder — et le
    geste doit tenir en UN clic depuis la liste, y compris sur telephone.
    """
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    db.marquer_verifiee_par_edouard(offre_id, encore_en_ligne=en_ligne)
    return {"ok": True, "offre": db.lire_offre(offre_id)}


@app.get("/api/offres/{offre_id}", dependencies=[Depends(auth.exiger_session)])
def api_offre(offre_id: int):
    o = db.lire_offre(offre_id)
    if not o:
        raise HTTPException(404, "offre inconnue")
    return o


class ChangementStatut(BaseModel):
    statut: str
    motif: str | None = None
    canal: str | None = None


@app.post("/api/offres/{offre_id}/statut", dependencies=[Depends(auth.exiger_session)])
def api_statut(offre_id: int, corps: ChangementStatut):
    if corps.statut not in STATUTS:
        raise HTTPException(400, f"statut inconnu : {corps.statut}")
    if corps.statut == "ecartee" and not (corps.motif or "").strip():
        # Les motifs d'ecartement sont la donnee qui dira ce que le scoring
        # rate : on refuse d'ecarter sans motif.
        raise HTTPException(400, "un motif est obligatoire pour ecarter une offre")
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    db.changer_statut(offre_id, corps.statut, motif=corps.motif, canal=corps.canal)
    return {"ok": True, "offre": db.lire_offre(offre_id)}


class MiseAJour(BaseModel):
    notes: str | None = None
    vue: int | None = None
    date_relance_due: str | None = None
    canal_candidature: str | None = None
    # Memorises par offre : il ne doit pas ressaisir ce qu'il a deja trouve.
    contact_nom: str | None = None
    contact_civilite: str | None = None
    adresse_entreprise: str | None = None
    reference_annonce: str | None = None


@app.post("/api/offres/{offre_id}", dependencies=[Depends(auth.exiger_session)])
def api_maj(offre_id: int, corps: MiseAJour):
    champs = {k: v for k, v in corps.model_dump().items() if v is not None}
    db.maj_champs(offre_id, **champs)
    return {"ok": True}


# --------------------------------------------------------------------------
# API - dossier de candidature
# --------------------------------------------------------------------------


@app.get("/api/offres/{offre_id}/reference", dependencies=[Depends(auth.exiger_session)])
def api_reference(offre_id: int):
    """La reference enregistree, et celle que l'annonce permet de proposer.

    La console PREREMPLIT le champ avec la proposition et montre la phrase
    d'ou elle vient. Elle n'ecrit rien : c'est lui qui enregistre.
    """
    offre = db.lire_offre(offre_id)
    if not offre:
        raise HTTPException(404, "offre inconnue")
    proposition, preuve = dossier.deduire_reference(offre)
    return {"enregistree": offre.get("reference_annonce") or "",
            "proposition": proposition, "preuve": preuve}


@app.get("/api/offres/{offre_id}/completude", dependencies=[Depends(auth.exiger_session)])
def api_completude(offre_id: int):
    """Ce qu'on sait de ce poste — SANS rapport avec le score de correspondance."""
    from . import completude

    offre = db.lire_offre(offre_id)
    if not offre:
        raise HTTPException(404, "offre inconnue")
    return completude.evaluer(offre).as_dict()


@app.get("/api/offres/{offre_id}/entretien", dependencies=[Depends(auth.exiger_session)])
def api_entretien(offre_id: int):
    """Ce qu'on va lui demander en entretien, et pourquoi on le pense.

    Ne part chez personne. Chaque point porte son ancrage : une phrase de
    l'annonce, ou une ligne de son fichier 17. `ancrages_douteux` doit rester
    vide — s'il ne l'est pas, c'est que quelque chose a ete reformule, et
    l'ecran le dit.
    """
    from . import entretien

    offre = db.lire_offre(offre_id)
    if not offre:
        raise HTTPException(404, "offre inconnue")

    pieces: list[str] = []
    chemin = offre.get("dossier_chemin")
    if chemin:
        d = Path(chemin)
        if d.exists():
            pieces = sorted(f.name for f in d.iterdir() if f.is_file())

    prep = entretien.preparer(offre, pieces=pieces)
    corps = prep.as_dict()
    fichier = entretien.fichier_kit()
    corps["ancrages_douteux"] = entretien.verifier_ancrages(
        prep, offre, fichier.read_text(encoding="utf-8") if fichier else "")
    corps["dossier_genere"] = bool(pieces)
    return corps


@app.post("/api/offres/{offre_id}/dossier", dependencies=[Depends(auth.exiger_session)])
def api_dossier(offre_id: int, forcer: bool = False):
    """Genere le dossier — en prevenant AVANT si l'information est trop mince.

    Sans ce garde-fou, il peut sortir une lettre depuis un extrait de trois
    lignes : le resultat est creux et rien ne l'avertit. On refuse d'abord, en
    disant ce qui manque et comment le combler, et `forcer=true` passe outre si
    c'est son choix.
    """
    from . import completude

    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    offre = db.lire_offre(offre_id)
    if not offre:
        raise HTTPException(404, "offre inconnue")

    bilan = completude.evaluer(offre)
    if not bilan.suffisant_pour_dossier and not forcer:
        return {"ok": False, "raison": "completude_insuffisante", "completude": bilan.as_dict()}

    resultat = dossier.generer(offre)
    db.maj_champs(offre_id, dossier_chemin=str(resultat.chemin))
    db.journaliser(offre_id, "dossier_genere", resultat.gabarit_lettre)
    return {
        "ok": True,
        "dossier": resultat.chemin.name,
        "fichiers": resultat.fichiers,
        "gabarit_lettre": resultat.gabarit_lettre,
        "kit_provisoire": resultat.kit_provisoire,
        "avertissements": resultat.avertissements,
        "archive": f"/api/offres/{offre_id}/dossier/archive",
        "completude": bilan.as_dict(),
        "pieces_envoi": resultat.pieces_envoi,
        "archive_complete": f"/api/offres/{offre_id}/dossier/archive?complet=true",
    }


@app.get("/api/offres/{offre_id}/dossier/archive", dependencies=[Depends(auth.exiger_session)])
def api_archive(offre_id: int, complet: bool = False):
    offre = db.lire_offre(offre_id)
    if not offre or not offre.get("dossier_chemin"):
        raise HTTPException(404, "aucun dossier genere pour cette offre")
    repertoire = Path(offre["dossier_chemin"])
    # Par defaut on sert le paquet D'ENVOI : celui qui ne contient que les
    # pieces destinees au recruteur, sous les noms qu'il verra. Le dossier
    # complet — avec sa note de preparation — se demande explicitement.
    from . import rendu

    # Aucun repli sur l'ancien nom `<dossier>.zip` : ces paquets-la
    # contenaient la fiche de preparation d'entretien. Mieux vaut un 404 qui
    # invite a regenerer qu'un paquet qui emporte son score chez un recruteur.
    noms = ([f"{repertoire.name}-DOSSIER-COMPLET.zip"] if complet
            else [f"{rendu.prefixe()}-candidature.zip"])
    for nom in noms:
        archive = repertoire / nom
        if archive.exists():
            return FileResponse(archive, filename=archive.name,
                                media_type="application/zip")
    raise HTTPException(404, "archive introuvable")


@app.get("/api/offres/{offre_id}/dossier/{nom_fichier}", dependencies=[Depends(auth.exiger_session)])
def api_fichier_dossier(offre_id: int, nom_fichier: str):
    offre = db.lire_offre(offre_id)
    if not offre or not offre.get("dossier_chemin"):
        raise HTTPException(404, "aucun dossier genere")
    base = Path(offre["dossier_chemin"]).resolve()
    cible = (base / nom_fichier).resolve()
    # Barriere anti-traversee : le fichier demande doit rester dans le dossier.
    if not str(cible).startswith(str(base)) or not cible.is_file():
        raise HTTPException(404, "fichier introuvable")
    return FileResponse(cible, filename=cible.name)


# --------------------------------------------------------------------------
# API - texte complet de l'annonce
# --------------------------------------------------------------------------


@app.get("/api/offres/{offre_id}/enrichissement", dependencies=[Depends(auth.exiger_session)])
def api_politique_enrichissement(offre_id: int):
    """Ce qu'on a le droit de faire sur cette annonce, et pourquoi."""
    offre = db.lire_offre(offre_id)
    if not offre:
        raise HTTPException(404, "offre inconnue")
    p = enrichissement.politique(offre.get("url_canonique") or offre.get("url") or "")
    possible, message = enrichissement.verifier_cadence()
    return {
        "politique": p.as_dict(),
        "cadence_ok": possible,
        "cadence_message": message,
        "deja_enrichie": bool(offre.get("enrichi_le")),
        "enrichi_le": offre.get("enrichi_le"),
        "enrichi_par": offre.get("enrichi_par"),
        "url": offre.get("url_canonique") or offre.get("url") or "",
    }


@app.post("/api/offres/{offre_id}/enrichir", dependencies=[Depends(auth.exiger_session)])
def api_enrichir(offre_id: int):
    """Recuperation automatique — uniquement sur les sources qui l'autorisent.

    Cette route n'est appelee que par un geste de sa part. Rien dans le
    minuteur de collecte ne doit y toucher.
    """
    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    offre = db.lire_offre(offre_id)
    if not offre:
        raise HTTPException(404, "offre inconnue")
    url = offre.get("url_canonique") or offre.get("url") or ""

    p = enrichissement.politique(url)
    if not p.autorise:
        raise HTTPException(403, f"{p.raison}. {p.conseil}".strip())

    texte, message = enrichissement.recuperer(url)
    if not texte:
        return {"ok": False, "message": message, "politique": p.as_dict()}
    return enrichissement.appliquer_texte(offre_id, texte, f"recupere sur {p.domaine}").as_dict()


class TexteAnnonce(BaseModel):
    texte: str


@app.post("/api/offres/{offre_id}/texte", dependencies=[Depends(auth.exiger_session)])
def api_coller_texte(offre_id: int, corps: TexteAnnonce):
    """Le texte colle a la main : couverture totale, zero requete automatisee."""
    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    rapport = enrichissement.appliquer_texte(offre_id, corps.texte, "colle a la main")
    if not rapport.ok:
        raise HTTPException(400, rapport.message)
    return rapport.as_dict()


@app.post("/api/offres/{offre_id}/texte/annuler", dependencies=[Depends(auth.exiger_session)])
def api_annuler_texte(offre_id: int):
    """Revient a l'extrait d'origine apres un collage rate.

    L'extrait vient de la source, le collage vient de lui : on garde les deux,
    et il ne doit jamais perdre l'original.
    """
    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    if not db.annuler_texte_complet(offre_id):
        raise HTTPException(400, "aucun texte complet a annuler pour cette offre")
    # On rescore sur l'extrait retrouve.
    db.rescorer_offre(offre_id)
    return {"ok": True, "message": "Extrait d'origine retabli, offre rescoree."}


# --------------------------------------------------------------------------
# API - les exigences relevees dans le texte colle
#
# Le modele PROPOSE. Edouard valide. Le scoring deterministe recalcule.
# Aucune route ici ne donne de points : elles deposent, valident ou oublient.
# --------------------------------------------------------------------------


class ValidationExigences(BaseModel):
    attributs: list[str] = []


@app.get("/api/exigences", dependencies=[Depends(auth.exiger_session)])
def api_exigences_etat():
    """Le releve est-il utilisable, et qu'est-ce qui partirait ?"""
    from . import exigences

    d = exigences.disponible()
    return {"possible": d.possible, "raison": d.raison,
            "ce_qui_part": exigences.ce_qui_part(),
            "attributs": {k: {"libelle": v["libelle"], "valeurs": list(v["valeurs"]),
                              "agit_sur_le_score": v["agit_sur_le_score"]}
                          for k, v in exigences.ATTRIBUTS.items()}}


@app.get("/api/offres/{offre_id}/exigences", dependencies=[Depends(auth.exiger_session)])
def api_exigences_de(offre_id: int):
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    toutes = db.exigences_de(offre_id, validees_seulement=False)
    return {
        "validees": [e for e in toutes if e["validee_le"]],
        "propositions": [e for e in toutes if not e["validee_le"]],
    }


@app.post("/api/offres/{offre_id}/exigences/relever",
          dependencies=[Depends(auth.exiger_session)])
def api_relever_exigences(offre_id: int):
    """Releve les exigences du texte DEJA enregistre. Ne change aucun score.

    Le texte part chez le tiers ; c'est dit dans la console avant le clic.
    """
    from . import exigences

    offre = db.lire_offre(offre_id)
    if not offre:
        raise HTTPException(404, "offre inconnue")

    releve = exigences.proposer(offre.get("description") or "")
    if releve.ok and releve.propositions:
        db.enregistrer_propositions(
            offre_id, [e.as_dict() for e in releve.propositions], par="modele")
        db.journaliser(offre_id, "exigences_proposees",
                       ", ".join(e.attribut for e in releve.propositions))
    return releve.as_dict()


@app.post("/api/offres/{offre_id}/exigences/valider",
          dependencies=[Depends(auth.exiger_session)])
def api_valider_exigences(offre_id: int, corps: ValidationExigences):
    """SA decision. C'est le seul geste qui ouvre une exigence au scoring."""
    from . import exigences

    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    inconnus = [a for a in corps.attributs if a not in exigences.ATTRIBUTS]
    if inconnus:
        raise HTTPException(400, f"attribut inconnu : {', '.join(inconnus)}")

    n = db.valider_exigences(offre_id, corps.attributs)
    db.journaliser(offre_id, "exigences_validees", ", ".join(corps.attributs))
    offre = db.lire_offre(offre_id)
    return {"ok": True, "validees": n, "score": offre["score"],
            "explication": offre.get("explication") or []}


@app.post("/api/offres/{offre_id}/exigences/oublier",
          dependencies=[Depends(auth.exiger_session)])
def api_oublier_exigences(offre_id: int):
    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    db.oublier_exigences(offre_id)
    db.journaliser(offre_id, "exigences_oubliees", "")
    return {"ok": True, "score": db.lire_offre(offre_id)["score"]}


# --------------------------------------------------------------------------
# API - les offres qu'aucun motif n'a su classer
#
# Une proposition n'est qu'une proposition : c'est la validation qui ecrit, et
# la famille validee survit ensuite aux rescorages.
# --------------------------------------------------------------------------


class ValidationFamille(BaseModel):
    offre_id: int
    famille: str


class ValidationFamilles(BaseModel):
    decisions: list[ValidationFamille] = []


@app.get("/api/classement", dependencies=[Depends(auth.exiger_session)])
def api_classement(toutes: bool = False):
    """Les offres sans famille, et la famille proposee quand il y en a une."""
    from . import classement

    sans = db.offres_sans_famille(actives_seulement=not toutes)
    propositions = classement.proposer_pour(sans)
    classees = {p.offre_id for p in propositions}
    return {
        "sans_famille": len(sans),
        "propositions": [p.as_dict() for p in propositions],
        "sans_proposition": [
            {"offre_id": o["id"], "titre": o["titre"],
             "employeur": o.get("employeur") or "", "score": o["score"]}
            for o in sans if o["id"] not in classees
        ],
    }


@app.post("/api/classement/valider", dependencies=[Depends(auth.exiger_session)])
def api_valider_classement(corps: ValidationFamilles):
    """Valide un lot. Chaque famille doit exister dans criteres.yaml."""
    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    familles = charger_criteres().familles
    inconnues = sorted({d.famille for d in corps.decisions if d.famille not in familles})
    if inconnues:
        raise HTTPException(400, f"famille inconnue : {', '.join(inconnues)}")
    for d in corps.decisions:
        if db.lire_offre(d.offre_id):
            db.valider_famille(d.offre_id, d.famille)
    return {"ok": True, "validees": len(corps.decisions)}


# --------------------------------------------------------------------------
# API - le mot de relance
# --------------------------------------------------------------------------


@app.get("/api/offres/{offre_id}/relance", dependencies=[Depends(auth.exiger_session)])
def api_relance(offre_id: int):
    """Le texte de relance, assemble depuis un gabarit et des faits enregistres."""
    from . import relance as relance_mod

    refus = _refus_sans_configuration_hors_conteneur()
    if refus is not None:
        return refus
    offre = db.lire_offre(offre_id)
    if not offre:
        raise HTTPException(404, "offre inconnue")
    return relance_mod.preparer(offre).as_dict()


@app.post("/api/offres/{offre_id}/relance/envoyee",
          dependencies=[Depends(auth.exiger_session)])
def api_relance_envoyee(offre_id: int):
    """Marquage manuel : la console n'envoie rien, elle enregistre qu'il l'a fait."""
    if not db.lire_offre(offre_id):
        raise HTTPException(404, "offre inconnue")
    db.changer_statut(offre_id, "relance_envoyee")
    db.journaliser(offre_id, "relance_envoyee", "")
    return {"ok": True}


# --------------------------------------------------------------------------
# API - ses documents
#
# Ils portent son etat civil, ses pretentions et sa strategie de negociation :
# chaque route exige une session, et aucun chemin n'est servi sans verification
# de containment.
# --------------------------------------------------------------------------


@app.get("/api/documents/kit", dependencies=[Depends(auth.exiger_session)])
def api_kit():
    return documents.lister_kit()


@app.get("/api/documents/kit/{nom}", dependencies=[Depends(auth.exiger_session)])
def api_kit_fichier(nom: str, apercu: bool = False):
    try:
        chemin = documents.chemin_kit_sur(nom)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    # Telechargement par defaut : un PDF de CV se lit mal dans un onglet de
    # telephone. L'apercu reste possible a la demande.
    disposition = "inline" if apercu else "attachment"
    return FileResponse(
        chemin,
        filename=chemin.name,
        headers={"Content-Disposition": f'{disposition}; filename="{chemin.name}"'},
    )


@app.get("/api/documents/dossiers", dependencies=[Depends(auth.exiger_session)])
def api_dossiers():
    return {"dossiers": documents.lister_dossiers()}


@app.get("/api/documents/dossiers/{dossier}/{nom}", dependencies=[Depends(auth.exiger_session)])
def api_dossier_fichier(dossier: str, nom: str, apercu: bool = False):
    try:
        chemin = documents.chemin_dossier_sur(dossier, nom)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    disposition = "inline" if apercu else "attachment"
    return FileResponse(
        chemin,
        filename=chemin.name,
        headers={"Content-Disposition": f'{disposition}; filename="{chemin.name}"'},
    )


# --------------------------------------------------------------------------
# API - reglages
# --------------------------------------------------------------------------


@app.get("/api/reglages", dependencies=[Depends(auth.exiger_session)])
def api_reglages():
    return {
        "seuil": reglages.lire_seuil(),
        "frequence": reglages.lire_frequence(),
        "sources": reglages.etat_sources(),
        "emplacement_kit": str(CHEMIN_KIT),
        "emplacement_base": str(db.CHEMIN_DB),
    }


class NouveauSeuil(BaseModel):
    valeur: float


@app.post("/api/reglages/seuil", dependencies=[Depends(auth.exiger_session)])
def api_changer_seuil(corps: NouveauSeuil):
    try:
        reglages.ecrire_seuil(corps.valeur)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "seuil": reglages.lire_seuil()}


class NouvelleFrequence(BaseModel):
    cle: str


@app.post("/api/reglages/frequence", dependencies=[Depends(auth.exiger_session)])
def api_changer_frequence(corps: NouvelleFrequence):
    try:
        return {"ok": True, "frequence": reglages.ecrire_frequence(corps.cle)}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/reglages/collecter", dependencies=[Depends(auth.exiger_session)])
def api_collecter_maintenant():
    """Declenche une collecte sans attendre son heure.

    En conteneur, le planificateur la lance, en prod seulement (le staging ne
    collecte pas). Sur le serveur du tailnet, c'est le service systemd.
    """
    environnement = config.environnement()
    # L'environnement d'abord : en staging, c'est « la collecte est coupee » qu'il faut dire.
    if environnement is not None and environnement != "prod":
        return _erreur(409, "collecte_coupee")
    refus = _refus_sans_configuration()
    if refus is not None:
        return refus
    if environnement is not None:
        if not PLANIFICATEUR.collecter_maintenant():
            return _erreur(409, "collecte_en_cours")
        return {"ok": True, "message": "Collecte lancée. Rafraîchis dans une minute."}

    import subprocess

    resultat = subprocess.run(
        ["systemctl", "--user", "start", "veille-collecte.service"],
        capture_output=True, text=True, timeout=30,
    )
    if resultat.returncode != 0:
        raise HTTPException(500, resultat.stderr[:200] or "démarrage impossible")
    return {"ok": True, "message": "Collecte lancée. Rafraîchis dans une minute."}


# --------------------------------------------------------------------------
# API - pilotage
# --------------------------------------------------------------------------


@app.get("/api/entonnoir", dependencies=[Depends(auth.exiger_session)])
def api_entonnoir():
    return db.entonnoir()


@app.get("/api/relances", dependencies=[Depends(auth.exiger_session)])
def api_relances():
    return {"relances": db.relances_dues()}


@app.post("/api/rescorer", dependencies=[Depends(auth.exiger_session)])
def api_rescorer():
    refus = _refus_sans_configuration()
    if refus is not None:
        return refus
    recharger()
    recalculees, ecartees, remises, differees = db.rescorer_tout()
    return {
        "ok": True,
        "offres_recalculees": recalculees,
        "nouvellement_ecartees": ecartees,
        "remises_dans_le_flux": remises,
        "nouvellement_differees": differees,
    }


# --------------------------------------------------------------------------
# API - notifications push
# --------------------------------------------------------------------------


class Abonnement(BaseModel):
    endpoint: str
    keys: dict[str, str]


@app.post("/api/push/abonnement", dependencies=[Depends(auth.exiger_session)])
def api_abonnement(corps: Abonnement):
    db.enregistrer_abonnement(corps.endpoint, corps.keys.get("p256dh", ""), corps.keys.get("auth", ""))
    return {"ok": True}


@app.delete("/api/push/abonnement", dependencies=[Depends(auth.exiger_session)])
def api_desabonnement(endpoint: str):
    db.supprimer_abonnement(endpoint)
    return {"ok": True}


@app.post("/api/push/test", dependencies=[Depends(auth.exiger_session)])
def api_push_test():
    ok, ko = notifications.envoyer_push(
        "Veille emploi", "Notification de test - le push fonctionne.", url="/"
    )
    return {"envoyes": ok, "echecs": ko}


# --------------------------------------------------------------------------
# PWA
# --------------------------------------------------------------------------


@app.get("/manifest.webmanifest")
def manifeste():
    return JSONResponse(
        {
            "name": "Veille emploi",
            "short_name": "Veille",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#11151c",
            "theme_color": "#11151c",
            "icons": [
                {"src": "/static/icone-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icone-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        }
    )


@app.get("/sw.js")
def service_worker():
    # Servi a la racine pour que sa portee couvre toute la console.
    return FileResponse(ICI / "static" / "sw.js", media_type="application/javascript")


@app.get("/sante")
def sante():
    # Contrat du modele : lu a chaque requete, jamais a l'import.
    corps = {
        "statut": "ok",
        "environnement": config.environnement() or "local",
        "version": config.version(),
        "revision": os.environ.get("REVISION", "").strip() or "inconnue",
        # `exemple` : rien de designe, la console sert l'exemple ; `montee` : une instance.
        "configuration": "montee" if config.config_designee() else "exemple",
    }
    if not db.base_ouverte():
        corps["statut"] = "ko"
        return JSONResponse(corps, status_code=503)
    return corps
