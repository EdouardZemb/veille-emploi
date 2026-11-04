"""L'annonce est-elle encore en ligne ?

POURQUOI C'EST DELICAT. Les deux erreurs possibles n'ont pas le meme cout :
garder une annonce morte lui coute un clic ; archiver une annonce vivante la
fait disparaitre de sa vue sans qu'il sache pourquoi — surtout quand les
alertes mail sont le flux principal. Toute la regle decoule de cette asymetrie.

CE QUI PROUVE UN RETRAIT
  - HTTP 404 ou 410 ;
  - HTTP 200 avec une phrase d'expiration ET le titre de l'annonce absent de
    la page. Beaucoup de sites rendent 200 sur une annonce morte : le code
    HTTP ne suffit pas. Mais « si cette offre n'est plus disponible… » est du
    texte de gabarit — si le titre est encore la, la page EST l'annonce.

CE QUI NE PROUVE RIEN
  - 429, 403, 5xx, delai depasse, coupure reseau : on ne sait pas ;
  - une page vide (rendu JavaScript) : on ne sait pas ;
  - une redirection vers l'accueil : un INDICE, qui demande un echec de plus.

ET SURTOUT : ce qu'on n'a pas le droit de sonder n'est JAMAIS archive
automatiquement. LinkedIn declare `Disallow: /` — une part notable des offres
en vient. Aucune requete ne part vers ces domaines, et l'absence de preuve
n'est pas une preuve d'absence.

La politique d'acces est celle de `enrichissement.politique()` : une seule
regle pour tout le projet, liste blanche ET robots.txt lu en direct.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx

from . import db, enrichissement
from .config import normaliser

log = logging.getLogger(__name__)

AGENT = enrichissement.AGENT
DELAI = 25.0

# Il faut DEUX preuves franches, ou TROIS indices, espacees d'au moins ce delai.
# Deux echecs a trente minutes d'intervalle, c'est le meme incident vu deux fois.
ESPACEMENT_MINIMAL = timedelta(hours=20)
ECHECS_POUR_PREUVE = 2
ECHECS_POUR_INDICE = 3

# On ne resonde pas une offre verifiee il y a moins de ca.
FRAICHEUR = timedelta(hours=20)

# Cadence : on est un visiteur, pas un robot d'indexation.
PAUSE_ENTRE_REQUETES = 3.0

# Un statut qu'IL a pose, ou un dossier genere : l'offre fait partie de son
# historique de candidature. On previent, on n'archive pas.
STATUTS_PROTEGES = ("interessante", "a_traiter", "candidature_envoyee")

# Phrases relevees sur de vraies pages d'expiration, en trois langues.
PHRASES_EXPIREES = [
    # francais
    "cette offre n est plus disponible",
    "cette annonce n est plus disponible",
    "cette offre n est plus en ligne",
    "cette annonce n est plus en ligne",
    "offre expiree",
    "annonce expiree",
    "offre cloturee",
    "offre pourvue",
    "poste pourvu",
    "n est plus d actualite",
    "cette offre a ete pourvue",
    "recrutement termine",
    "page introuvable",
    # anglais
    "this job is no longer available",
    "this job posting is no longer available",
    "this position is no longer available",
    "this posting has expired",
    "job expired",
    "no longer accepting applications",
    "this vacancy is closed",
    "position has been filled",
    "job not found",
    "vacancy not found",
    # allemand
    "diese stelle ist nicht mehr verfugbar",
    "dieses inserat ist nicht mehr verfugbar",
    "inserat nicht mehr online",
    "anzeige abgelaufen",
    "stelle besetzt",
    "nicht mehr verfugbar",
]

# Chemins qui designent une page d'accueil ou une liste, pas une annonce.
CHEMINS_GENERIQUES = ("", "/", "/jobs", "/emplois", "/offres", "/search", "/recherche",
                      "/en", "/fr", "/de", "/vacancies", "/stellen")

# En deca, la page n'a pas de contenu exploitable : rendu JavaScript, mur, etc.
LONGUEUR_UTILE = 250

# Mots sans valeur d'identification dans un intitule.
MOTS_VIDES = {
    "de", "du", "la", "le", "les", "et", "des", "une", "aux", "pour", "avec",
    "en", "sur", "par", "chez", "of", "in", "at", "the", "and", "for", "to",
    "mit", "und", "der", "die", "das", "den", "fur", "zur", "im", "am",
}


@dataclass
class Sonde:
    """Ce qu'une requete nous apprend — ou n'apprend pas."""

    verdict: str          # vivante | retiree | indice_retrait | injoignable | interdite
    detail: str
    texte: str = ""       # corps lisible, quand il y en a un
    attendre_s: float = 0.0


@dataclass
class Decision:
    """Ce qu'on en fait."""

    verdict: str
    detail: str
    archivee: bool = False
    protegee: bool = False
    enrichie: bool = False


@dataclass
class Rapport:
    sondees: list[int] = field(default_factory=list)
    archivees: list[int] = field(default_factory=list)
    signalees: list[int] = field(default_factory=list)
    enrichies: list[int] = field(default_factory=list)
    par_verdict: dict[str, int] = field(default_factory=dict)
    non_sondables: int = 0


# --------------------------------------------------------------------------
# La sonde
# --------------------------------------------------------------------------


def _titre_present(texte: str, titre: str) -> bool | None:
    """Le titre de l'annonce est-il encore sur la page ?

    Trois reponses, pas deux : oui, non, et JE NE SAIS PAS. La troisieme a ete
    ajoutee apres un rejeu sur la base, ou plusieurs annonces vivantes etaient
    accusees a tort :

      - « QA Lead » : apres normalisation il ne reste que « lead », parce que
        « qa » fait deux lettres. Trop court pour conclure quoi que ce soit ;
      - une page servie en anglais alors que le titre est stocke en allemand.
        L'annonce est vivante, le titre n'y est simplement pas dans la meme
        langue.

    Rendre False dans ces cas revenait a accuser faute de preuve. On rend None.
    """
    if not titre or not texte:
        return None
    # On filtre les mots vides, pas les mots COURTS : « QA », « IA » et
    # « IT » font deux lettres et sont souvent ce qui identifie un
    # intitule. Les ecarter sur la longueur rendait « QA Lead »
    # invérifiable.
    mots = [m for m in normaliser(titre).split()
            if len(m) > 1 and m not in MOTS_VIDES]
    if len(mots) < 2:
        return None      # trop court pour trancher
    page = normaliser(texte)
    taille = min(3, len(mots))
    for i in range(len(mots) - taille + 1):
        if f" {' '.join(mots[i:i + taille])} " in page:
            return True
    return False


def _attente_demandee(entetes) -> float:
    brut = (entetes or {}).get("Retry-After") or (entetes or {}).get("retry-after")
    try:
        return float(brut)
    except (TypeError, ValueError):
        return 0.0


def sonder(url: str, titre: str = "") -> Sonde:
    """Une seule requete, et ce qu'on peut honnetement en conclure."""
    politique = enrichissement.politique(url)
    if not politique.autorise:
        return Sonde("interdite", politique.raison)

    try:
        with httpx.Client(
            timeout=DELAI,
            follow_redirects=True,
            headers={"User-Agent": AGENT, "Accept": "text/html,*/*"},
        ) as client:
            rep = client.get(url)
    except Exception as exc:
        return Sonde("injoignable", f"{type(exc).__name__} : {exc}"[:120])

    code = int(getattr(rep, "status_code", 0))
    entetes = getattr(rep, "headers", {}) or {}

    if code == 410:
        # 410 Gone : le serveur DECLARE que la ressource a existe et qu'elle
        # est definitivement supprimee. Ce n'est pas une absence constatee,
        # c'est une affirmation — elle se suffit a elle-meme.
        return Sonde("retiree_declaree",
                     "HTTP 410 Gone — le site declare l'annonce definitivement supprimee")
    if code == 404:
        # 404 est MUET sur la cause : route cassee, ressource deplacee, erreur
        # passagere, blocage. On constate, on ne conclut pas seul.
        return Sonde("retiree", "HTTP 404 — la page n'existe plus")
    if code != 200:
        # 429, 403, 5xx : le site refuse ou flanche. On ne conclut pas.
        return Sonde("injoignable", f"HTTP {code}", attendre_s=_attente_demandee(entetes))

    texte = enrichissement.nettoyer_texte(getattr(rep, "text", "") or "")
    plat = normaliser(texte)
    finale = str(getattr(rep, "url", "") or url)

    # ORDRE : du signal le plus SPECIFIQUE au plus general. Trois fois deja
    # dans ce projet, l'inverse a produit un defaut.
    #
    # 1. Le titre de l'annonce est encore sur la page -> la page EST l'annonce,
    #    quelle que soit la phrase de gabarit qu'elle contient par ailleurs
    #    (« si cette offre n'est plus disponible, consultez nos alertes »).
    vu = _titre_present(texte, titre)
    if vu is True:
        return Sonde("vivante", "l'annonce est toujours en ligne", texte=texte)

    # 2. Une phrase d'expiration. Elle passe AVANT le controle de longueur :
    #    une vraie page d'expiration est COURTE — « Cette offre n'est plus
    #    disponible », trois lignes et un pied de page. Tester la longueur
    #    d'abord transformait la seule preuve exploitable en « injoignable »,
    #    et la verification n'aurait jamais rien archive du tout.
    phrase = next((p for p in PHRASES_EXPIREES if f" {p} " in plat), "")
    if phrase:
        return Sonde("retiree", f"HTTP 200 mais la page dit « {phrase} »", texte=texte)

    # 3. Redirection vers une page generique. C'est le SEUL indice qu'on garde :
    #    il est structurel. « Le titre n'est plus sur la page » ne l'est pas —
    #    voir plus bas.
    if finale != url:
        chemin = (urlsplit(finale).path or "/").rstrip("/")
        if chemin.lower() in CHEMINS_GENERIQUES:
            return Sonde("indice_retrait",
                         f"redirigee vers {finale[:70]} — page generique, pas l'annonce",
                         texte=texte)

    # 4. Rien d'exploitable : rendu JavaScript, mur d'acces. On ne conclut pas.
    if len(texte) < LONGUEUR_UTILE:
        return Sonde("injoignable",
                     f"page quasi vide ({len(texte)} caracteres) — rendu JavaScript "
                     "ou mur d'acces : on ne peut rien en conclure")

    # 5. Le titre n'est pas sur la page, ou on n'a pas pu verifier.
    #
    #    ON NE CONCLUT PAS. Le rejeu sur la base a montre que ce cas produit
    #    des accusations fausses en serie : titres courts (« QA Lead ») et
    #    pages servies dans une autre langue que celle de l'alerte. Des offres
    #    ainsi accusees, aucune n'etait retiree.
    raison = ("le titre de l'annonce n'y figure pas — mais la page peut etre "
              "servie dans une autre langue, ou l'intitule avoir ete reformate : "
              "on ne conclut pas"
              if vu is False else
              "titre trop court pour etre cherche de facon fiable")
    return Sonde("injoignable", raison, texte=texte)



# --------------------------------------------------------------------------
# La décision
# --------------------------------------------------------------------------


def verifier_offre(offre_id: int, maintenant: datetime | None = None,
                   enrichir: bool = False) -> Decision:
    """Sonde une offre et met a jour son etat. Archive seulement si c'est du."""
    maintenant = maintenant or datetime.now()
    o = db.lire_offre(offre_id)
    if not o:
        return Decision("inconnue", "offre inconnue")

    url = o["url_canonique"] or o["url"] or ""
    sonde = sonder(url, titre=o["titre"] or "")

    protegee = bool(
        o["statut"] in STATUTS_PROTEGES
        or o["dossier_chemin"]
        or o["archive_protegee"]
    )

    if sonde.verdict == "interdite":
        # Pas de preuve possible, donc pas d'archivage. On l'ecrit noir sur
        # blanc pour qu'il sache que cette offre n'est pas verifiee.
        db.enregistrer_verification(offre_id, "interdite", sonde.detail,
                                    maintenant, avance=False, reinitialise=False)
        return Decision("interdite", sonde.detail, protegee=protegee)

    if sonde.verdict == "vivante":
        db.enregistrer_verification(offre_id, "vivante", sonde.detail,
                                    maintenant, avance=False, reinitialise=True)
        enrichie = False
        if enrichir and o["donnees_partielles"] and sonde.texte:
            rapport = enrichissement.appliquer_texte(
                offre_id, sonde.texte, f"verification sur {enrichissement._domaine(url)}"
            )
            enrichie = rapport.ok
        return Decision("vivante", sonde.detail, enrichie=enrichie)

    if sonde.verdict == "injoignable":
        # Ni avance, ni reset : un site en panne ne condamne pas l'offre et
        # n'efface pas les preuves deja reunies.
        db.enregistrer_verification(offre_id, "injoignable", sonde.detail,
                                    maintenant, avance=False, reinitialise=False)
        if sonde.attendre_s:
            time.sleep(min(sonde.attendre_s, 60))
        return Decision("injoignable", sonde.detail)

    # --- Le 410 credible archive immediatement --------------------------
    if sonde.verdict == "retiree_declaree":
        credible = db.domaine_sert_encore(enrichissement._domaine(url),
                                          maintenant=maintenant)
        if credible:
            db.enregistrer_verification(offre_id, "retiree_declaree", sonde.detail,
                                        maintenant, avance=True, reinitialise=False)
            motif = (f"Retiree — le site declare l'annonce definitivement supprimee "
                     f"(HTTP 410), le {maintenant.strftime('%d/%m/%Y')}")
            if protegee:
                db.signaler_probablement_retiree(offre_id, motif)
                return Decision(sonde.verdict, motif, protegee=True)
            db.archiver(offre_id, motif)
            return Decision(sonde.verdict, motif, archivee=True)
        # Domaine qui ne sert plus rien de vivant : panne plus probable qu'une
        # purge. On garde la preuve, mais on repasse par les deux passes.
        sonde = Sonde("retiree", sonde.detail + " (domaine sans annonce vivante "
                                 "connue : confirmation attendue)")

    # --- retiree ou indice_retrait : on accumule ------------------------
    dernier = o["verifiee_le"]
    if dernier:
        try:
            ecoule = maintenant - datetime.fromisoformat(dernier)
        except ValueError:
            ecoule = ESPACEMENT_MINIMAL
        if ecoule < ESPACEMENT_MINIMAL and o["echecs_verification"]:
            # Trop tot pour que ce soit un second echec independant.
            db.enregistrer_verification(offre_id, sonde.verdict, sonde.detail,
                                        maintenant, avance=False, reinitialise=False)
            return Decision(sonde.verdict, sonde.detail)

    db.enregistrer_verification(offre_id, sonde.verdict, sonde.detail,
                                maintenant, avance=True, reinitialise=False)
    apres = db.lire_offre(offre_id)
    seuil = ECHECS_POUR_PREUVE if sonde.verdict == "retiree" else ECHECS_POUR_INDICE

    if apres["echecs_verification"] < seuil:
        return Decision(sonde.verdict, sonde.detail)

    motif = (f"Constatee absente a {apres['echecs_verification']} verifications "
             f"espacees, la derniere le {maintenant.strftime('%d/%m/%Y')} : {sonde.detail}")

    if protegee:
        # Elle fait partie de son historique de candidature. On previent.
        db.signaler_probablement_retiree(offre_id, motif)
        return Decision(sonde.verdict, motif, protegee=True)

    db.archiver(offre_id, motif)
    return Decision(sonde.verdict, motif, archivee=True)


# --------------------------------------------------------------------------
# La passe
# --------------------------------------------------------------------------


def passe(limite: int = 60, maintenant: datetime | None = None,
          enrichir: bool = True) -> Rapport:
    """Verifie les offres les plus anciennement verifiees, en etalant."""
    maintenant = maintenant or datetime.now()
    r = Rapport()
    limite_fraicheur = (maintenant - FRAICHEUR).isoformat(timespec="seconds")

    with db.connexion() as cx:
        lignes = cx.execute(
            """SELECT id FROM offres
               WHERE archivee_le IS NULL
                 AND (verifiee_le IS NULL OR verifiee_le < ?)
               ORDER BY COALESCE(verifiee_le, '0000') ASC, score DESC
               LIMIT ?""",
            (limite_fraicheur, limite),
        ).fetchall()

    for i, l in enumerate(lignes):
        if i:
            time.sleep(PAUSE_ENTRE_REQUETES)
        d = verifier_offre(l["id"], maintenant=maintenant, enrichir=enrichir)
        r.sondees.append(l["id"])
        r.par_verdict[d.verdict] = r.par_verdict.get(d.verdict, 0) + 1
        if d.verdict == "interdite":
            r.non_sondables += 1
        if d.archivee:
            r.archivees.append(l["id"])
        if d.protegee and d.verdict in ("retiree", "indice_retrait"):
            r.signalees.append(l["id"])
        if d.enrichie:
            r.enrichies.append(l["id"])
    return r
