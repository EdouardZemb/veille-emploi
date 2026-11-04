"""Collecteur d'alertes mail par IMAP.

C'est le canal qui debloque tout le reste : LinkedIn, Indeed, jobs.ch et les
pages carriere sans API ni flux envoient tous des alertes sur recherche
enregistree. On ne va pas chercher les annonces - on lit ce que les sites
transmettent d'eux-memes, par le canal qu'ils ont prevu.

DEUX FACONS DE DELIMITER CE QU'ON LIT, au choix (le sources.yaml de la configuration, bloc
`courriel`, champ `mode`) :

  `libelle`      on ne lit qu'un dossier IMAP, celui du libelle Gmail. Exige
                 qu'un filtre Gmail alimente ce libelle - a creer a la main,
                 l'API Gmail n'expose pas la creation de regles.

  `expediteurs`  on demande au SERVEUR de chercher les messages venant des
                 adresses connues, dans tous les messages. Aucune regle a
                 creer. La recherche est executee par Gmail : seuls les
                 messages correspondants sont transferes ici.

  `union`        les deux, dedupliques. Le libelle sert alors de filet : si un
                 filtre Gmail attrape une source que la liste d'expediteurs ne
                 connait pas encore, elle rentre quand meme.

CE QUE LE MODE NE CHANGE PAS : un mot de passe d'application Gmail donne acces
a la boite ENTIERE, dans les trois cas. Il n'existe aucun moyen de le limiter a
un libelle. La delimitation est donc faite par ce code, pas par Gmail - c'est
vrai du mode `libelle` comme du mode `expediteurs`.

Configuration dans config/.env :
    VEILLE_IMAP_HOTE=imap.gmail.com
    VEILLE_IMAP_UTILISATEUR=...@gmail.com
    VEILLE_IMAP_MOTDEPASSE=<mot de passe d'application, 16 caracteres>
"""

from __future__ import annotations

import email
import email.policy
import imaplib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage
from typing import Iterable

import httpx

from .. import db
from ..models import Offre
from .base import extraire_salaire
from .liens import resoudre
from .parsers import analyser

log = logging.getLogger(__name__)

nom = "courriel"


# --------------------------------------------------------------------------
# Lecture IMAP
# --------------------------------------------------------------------------


def _decoder(valeur: str | None) -> str:
    if not valeur:
        return ""
    try:
        return str(make_header(decode_header(valeur)))
    except Exception:
        return valeur


def _corps(message: EmailMessage) -> tuple[str, str]:
    """Rend (html, texte_brut)."""
    html, texte = "", ""
    if message.is_multipart():
        for partie in message.walk():
            if partie.get_content_maintype() == "multipart":
                continue
            if partie.get_filename():  # piece jointe
                continue
            type_contenu = partie.get_content_type()
            try:
                contenu = partie.get_content()
            except Exception:
                charge = partie.get_payload(decode=True) or b""
                contenu = charge.decode(partie.get_content_charset() or "utf-8", errors="replace")
            if type_contenu == "text/html" and not html:
                html = contenu
            elif type_contenu == "text/plain" and not texte:
                texte = contenu
    else:
        try:
            contenu = message.get_content()
        except Exception:
            contenu = (message.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if message.get_content_type() == "text/html":
            html = contenu
        else:
            texte = contenu
    return html, texte


@dataclass
class Passe:
    """Une recherche : un dossier a ouvrir, un critere a y appliquer."""

    cle: str            # identifie le marqueur d'avancement
    dossier: str
    description: str
    expediteurs: list[str] = field(default_factory=list)  # vide = tout le dossier


class BoiteIMAP:
    def __init__(self) -> None:
        from ..config import charger_sources

        self.hote = os.environ.get("VEILLE_IMAP_HOTE", "imap.gmail.com")
        self.port = int(os.environ.get("VEILLE_IMAP_PORT", "993"))
        self.utilisateur = os.environ.get("VEILLE_IMAP_UTILISATEUR", "")
        self.motdepasse = os.environ.get("VEILLE_IMAP_MOTDEPASSE", "")

        bloc = charger_sources().get("courriel") or {}
        self.mode = os.environ.get("VEILLE_IMAP_MODE") or bloc.get("mode", "union")
        self.libelle = os.environ.get("VEILLE_IMAP_DOSSIER") or bloc.get("libelle", "veille-emploi")
        self.expediteurs = [e.strip() for e in (bloc.get("expediteurs") or []) if e.strip()]

        if self.mode not in ("libelle", "expediteurs", "union"):
            raise RuntimeError(f"mode de collecte mail inconnu : {self.mode}")
        if not self.utilisateur or not self.motdepasse:
            raise RuntimeError(
                "VEILLE_IMAP_UTILISATEUR / VEILLE_IMAP_MOTDEPASSE absents "
                "- voir docs/DEMARRAGE.md, section mot de passe d'application"
            )
        self._cx: imaplib.IMAP4_SSL | None = None
        self._dossier_ouvert = ""

    # -- connexion -------------------------------------------------------
    def __enter__(self) -> "BoiteIMAP":
        self._cx = imaplib.IMAP4_SSL(self.hote, self.port)
        self._cx.login(self.utilisateur, self.motdepasse)
        # Gmail n'annonce X-GM-EXT-1 qu'APRES authentification, et imaplib ne
        # redemande pas les capacites apres le login. Attention : sa methode
        # `capability()` rend la reponse mais ne met PAS a jour l'attribut
        # `capabilities` — il faut le reaffecter soi-meme. Sans cela on croit
        # parler a un serveur ordinaire et on perd la recherche native.
        try:
            typ, donnees = self._cx.capability()
            if typ == "OK" and donnees and donnees[0]:
                brut = donnees[0]
                if isinstance(brut, bytes):
                    brut = brut.decode("ascii", "replace")
                self._cx.capabilities = tuple(brut.upper().split())
        except Exception as exc:
            log.debug("capacites non rafraichies : %s", exc)
        return self

    def __exit__(self, *_: object) -> None:
        if self._cx is not None:
            try:
                if self._dossier_ouvert:
                    self._cx.close()
            except Exception:
                pass
            try:
                self._cx.logout()
            except Exception:
                pass

    @property
    def gmail(self) -> bool:
        """Gmail annonce X-GM-EXT-1 : on peut lui passer une requete native.

        Les capacites peuvent arriver en bytes ou en str selon la version
        d'imaplib et le chemin de decodage : on normalise avant de comparer.
        """
        for capacite in getattr(self._cx, "capabilities", ()) or ():
            if isinstance(capacite, bytes):
                capacite = capacite.decode("ascii", "replace")
            if capacite.upper() == "X-GM-EXT-1":
                return True
        return False

    # -- dossiers --------------------------------------------------------
    def lister_dossiers(self) -> list[tuple[set[str], str]]:
        """[(attributs, nom)] — les attributs portent les roles RFC 6154."""
        if self._cx is None:
            return []
        code, lignes = self._cx.list()
        if code != "OK":
            return []
        resultat = []
        for ligne in lignes or []:
            t = ligne.decode(errors="replace") if isinstance(ligne, bytes) else str(ligne)
            attrs = set(re.findall(r"\\[A-Za-z]+", t.split(")")[0]))
            m = re.search(r'"([^"]+)"\s*$', t)
            if m:
                resultat.append((attrs, m.group(1)))
        return resultat

    def noms_dossiers(self) -> list[str]:
        return [nom for _, nom in self.lister_dossiers()]

    def dossier_tous_les_messages(self) -> str:
        """Le dossier « Tous les messages », trouve par son role et non par son
        nom : il s'appelle « [Gmail]/Tous les messages » en francais,
        « [Gmail]/All Mail » en anglais, autre chose ailleurs."""
        for attrs, nom in self.lister_dossiers():
            if "\\All" in attrs:
                return nom
        for nom in self.noms_dossiers():  # repli par nom, au cas ou
            if re.search(r"\[Gmail\]/(All Mail|Tous les messages)", nom):
                return nom
        return "INBOX"

    # -- plan de collecte ------------------------------------------------
    def passes(self) -> list[Passe]:
        """Les recherches a mener, selon le mode."""
        plan: list[Passe] = []
        dossiers = self.noms_dossiers()

        if self.mode in ("libelle", "union"):
            if self.libelle in dossiers:
                plan.append(Passe("libelle:" + self.libelle, self.libelle,
                                  f"libelle « {self.libelle} »"))
            elif self.mode == "libelle":
                raise RuntimeError(
                    f"Libelle IMAP '{self.libelle}' introuvable. Disponibles : "
                    + ", ".join(dossiers[:25])
                )
            else:
                log.info("libelle « %s » absent : on s'en tient aux expediteurs", self.libelle)

        if self.mode in ("expediteurs", "union"):
            if not self.expediteurs:
                if self.mode == "expediteurs":
                    raise RuntimeError(
                        "mode 'expediteurs' mais aucune adresse dans sources.yaml, bloc courriel"
                    )
            else:
                tous = self.dossier_tous_les_messages()
                plan.append(Passe("expediteurs:" + tous, tous,
                                  f"{len(self.expediteurs)} expediteur(s) dans « {tous} »",
                                  list(self.expediteurs)))
        return plan

    # -- recherche -------------------------------------------------------
    def _ouvrir(self, dossier: str) -> None:
        assert self._cx is not None
        if self._dossier_ouvert == dossier:
            return
        if self._dossier_ouvert:
            try:
                self._cx.close()
            except Exception:
                pass
        code, _ = self._cx.select(f'"{dossier}"', readonly=True)
        if code != "OK":
            raise RuntimeError(f"impossible d'ouvrir le dossier IMAP '{dossier}'")
        self._dossier_ouvert = dossier

    def uidvalidity(self) -> str:
        assert self._cx is not None
        code, donnees = self._cx.status(f'"{self._dossier_ouvert}"', "(UIDVALIDITY)")
        if code != "OK" or not donnees:
            return ""
        m = re.search(rb"UIDVALIDITY (\d+)", donnees[0] or b"")
        return m.group(1).decode() if m else ""

    def _chercher(self, passe: Passe, depuis: str, dernier_uid: str) -> list[bytes]:
        """UID des messages a examiner pour cette passe."""
        assert self._cx is not None
        borne = ["SINCE", depuis]
        if dernier_uid.isdigit():
            borne = [f"{int(dernier_uid) + 1}:*", "SINCE", depuis]

        if not passe.expediteurs:
            code, donnees = self._cx.uid("SEARCH", None, *borne)
            return donnees[0].split() if code == "OK" and donnees and donnees[0] else []

        # Gmail sait tout faire en une requete : from:(a OR b OR c).
        if self.gmail:
            requete = "from:(" + " OR ".join(passe.expediteurs) + ")"
            code, donnees = self._cx.uid("SEARCH", None, "X-GM-RAW", f'"{requete}"', *borne)
            if code == "OK":
                return donnees[0].split() if donnees and donnees[0] else []
            log.warning("X-GM-RAW refuse, retour a une recherche par expediteur")

        # Serveur IMAP quelconque : une recherche par expediteur, puis union.
        # L'imbrication de OR en IMAP devient illisible au-dela de deux termes.
        vus: dict[bytes, None] = {}
        for adresse in passe.expediteurs:
            code, donnees = self._cx.uid("SEARCH", None, "FROM", f'"{adresse}"', *borne)
            if code != "OK" or not donnees or not donnees[0]:
                continue
            for uid in donnees[0].split():
                vus.setdefault(uid, None)
        return sorted(vus, key=lambda u: int(u))

    def messages(self, passe: Passe, jours: int, dernier_uid: str = "") -> Iterable[tuple[str, EmailMessage]]:
        """Messages correspondant a la passe, plus recents que `jours`.

        La date evite de tout relire au premier passage, l'UID evite de
        retraiter ce qui l'a deja ete.
        """
        assert self._cx is not None
        self._ouvrir(passe.dossier)
        depuis = (date.today() - timedelta(days=jours)).strftime("%d-%b-%Y")
        uids = self._chercher(passe, depuis, dernier_uid)
        log.info("IMAP [%s] : %d message(s) a examiner", passe.description, len(uids))

        for uid in uids:
            code, charge = self._cx.uid("FETCH", uid, "(RFC822)")
            if code != "OK" or not charge or not charge[0]:
                continue
            brut = charge[0][1]
            if not isinstance(brut, (bytes, bytearray)):
                continue
            message = email.message_from_bytes(brut, policy=email.policy.default)
            yield uid.decode(), message  # type: ignore[misc]


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------


def _date_message(message: EmailMessage) -> date | None:
    brut = message.get("Date")
    if not brut:
        return None
    try:
        return email.utils.parsedate_to_datetime(brut).date()
    except Exception:
        return None


def convertir(annonce, parseur: str, expediteur: str, recu_le: date | None, client: httpx.Client) -> Offre:
    url = resoudre(annonce.url, client=client) if annonce.url else ""

    texte_pour_salaire = f"{annonce.salaire_texte} {annonce.extrait}"
    devise_defaut = "CHF" if parseur == "jobs_ch" else "EUR"
    smin, smax, devise = extraire_salaire(texte_pour_salaire, devise_par_defaut=devise_defaut)

    return Offre(
        titre=annonce.titre,
        employeur=annonce.employeur,
        lieu=annonce.lieu,
        # Ce n'est PAS la description de l'annonce : c'est ce que le mail en
        # montrait. Le scoring en tiendra compte via `donnees_partielles`.
        description=annonce.extrait,
        url=url or annonce.url,
        source=f"mail:{parseur}",
        date_publication=recu_le,
        salaire_min=smin,
        salaire_max=smax,
        salaire_devise=devise,
        type_contrat=annonce.contrat,
        # Une alerte mail ne contient quasiment jamais le texte complet de
        # l'annonce. On le declare, plutot que de faire semblant de scorer
        # sur un contenu qu'on n'a pas.
        donnees_partielles=len(annonce.extrait) < 400,
    )


def collecter(jours: int = 7) -> Iterable[Offre]:
    try:
        boite = BoiteIMAP()
    except RuntimeError as exc:
        log.warning("Collecte mail en pause : %s", exc)
        return []

    offres: list[Offre] = []

    with httpx.Client(
        timeout=12.0, follow_redirects=True, headers={"User-Agent": "veille-emploi/1.0 (usage personnel)"}
    ) as client:
        try:
            with boite as b:
                try:
                    plan = b.passes()
                except RuntimeError as exc:
                    log.error("collecte mail impossible : %s", exc)
                    return []

                for passe in plan:
                    b._ouvrir(passe.dossier)

                    # Les UID sont propres a un dossier, et ne valent que tant
                    # que l'UIDVALIDITY ne bouge pas. On memorise les deux, et
                    # on repart du debut si le serveur a renumerote.
                    marqueur = db.lire_marqueur(passe.cle)
                    validite = b.uidvalidity()
                    dernier_uid = ""
                    if marqueur:
                        v, _, u = marqueur.partition(":")
                        if v == validite:
                            dernier_uid = u
                        else:
                            log.info("UIDVALIDITY changee sur %s : relecture", passe.dossier)

                    uid_max = dernier_uid
                    for uid, message in b.messages(passe, jours, dernier_uid):
                        expediteur = _decoder(message.get("From"))
                        sujet = _decoder(message.get("Subject"))
                        html, texte = _corps(message)
                        if uid.isdigit() and (not uid_max or int(uid) > int(uid_max or 0)):
                            uid_max = uid
                        if not html and not texte:
                            continue
                        try:
                            parseur, annonces = analyser(html, texte, expediteur, sujet)
                        except Exception:
                            log.exception("parsing impossible : %s", sujet[:70])
                            continue
                        if annonces:
                            log.info(
                                "mail [%s] %s -> %d annonce(s) via %s",
                                uid, sujet[:60], len(annonces), parseur,
                            )
                        recu = _date_message(message)
                        for a in annonces:
                            offres.append(convertir(a, parseur, expediteur, recu, client))

                    if uid_max and uid_max != dernier_uid:
                        db.marquer_etat_collecte(passe.cle, marqueur=f"{validite}:{uid_max}")
        except Exception as exc:
            log.error("collecte mail interrompue : %s", exc)

    return offres
