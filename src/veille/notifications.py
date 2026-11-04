"""Notifications : push web (canal principal) et mail (repli).

PUSH WEB
  Exige HTTPS, donc `tailscale serve` avec un certificat du tailnet. Les cles
  VAPID sont generees a l'installation et stockees dans config/vapid.json.
  Sur la plupart des telephones, le push fonctionne de facon fiable des que
  la PWA est installee.

MAIL DE REPLI
  Utilise le serveur SMTP configure, par defaut celui de Gmail.
  Sert quand le push echoue (abonnement expire, telephone hors ligne trop
  longtemps) et pour le recapitulatif quotidien.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from . import db
from .config import RACINE

log = logging.getLogger(__name__)

CHEMIN_VAPID = Path(os.environ.get("VEILLE_VAPID", RACINE / "config" / "vapid.json"))


# --------------------------------------------------------------------------
# Cles VAPID
# --------------------------------------------------------------------------


@dataclass
class ClesVapid:
    publique: str
    privee: str
    sujet: str


SUJET_SANS_ORIGINE = "mailto:proprietaire@exemple.invalid"


def sujet_par_defaut(repli: str = SUJET_SANS_ORIGINE) -> str:
    """Le sujet VAPID d'une console qui n'en a pas : son origine publique.

    Le sujet part avec chaque push : jamais l'adresse de quelqu'un. Sans origine
    publique lisible (`VEILLE_EMPLOI_URL_PUBLIQUE`, sinon `VEILLE_URL`), `repli`.
    """
    from . import passkeys

    try:
        return passkeys.origine_attendue()[0]
    except passkeys.OrigineInconnue:
        return repli


def charger_vapid() -> ClesVapid | None:
    """Les cles du fichier. Un fichier existant garde son sujet, jamais reecrit."""
    if not CHEMIN_VAPID.exists():
        return None
    d = json.loads(CHEMIN_VAPID.read_text(encoding="utf-8"))
    return ClesVapid(d["publique"], d["privee"], d.get("sujet") or sujet_par_defaut())


def generer_vapid(sujet: str | None = None) -> ClesVapid:
    """Genere une paire de cles VAPID au format attendu par pywebpush."""
    if sujet is None:
        sujet = sujet_par_defaut()
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    cle = ec.generate_private_key(ec.SECP256R1())

    def b64(donnees: bytes) -> str:
        return base64.urlsafe_b64encode(donnees).rstrip(b"=").decode()

    prive = b64(cle.private_numbers().private_value.to_bytes(32, "big"))
    public = b64(
        cle.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )
    cles = ClesVapid(public, prive, sujet)
    CHEMIN_VAPID.parent.mkdir(parents=True, exist_ok=True)
    CHEMIN_VAPID.write_text(
        json.dumps({"publique": public, "privee": prive, "sujet": sujet}, indent=2), encoding="utf-8"
    )
    CHEMIN_VAPID.chmod(0o600)
    return cles


# --------------------------------------------------------------------------
# Push
# --------------------------------------------------------------------------


def envoyer_push(titre: str, corps: str, url: str = "/") -> tuple[int, int]:
    """Envoie a tous les abonnements. Rend (reussites, echecs)."""
    cles = charger_vapid()
    if not cles:
        log.warning("push impossible : pas de cles VAPID (lance `veille init-push`)")
        return 0, 0

    abonnements = db.lister_abonnements()
    if not abonnements:
        log.info("push : aucun appareil abonne")
        return 0, 0

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        log.error("pywebpush absent")
        return 0, len(abonnements)

    charge = json.dumps({"titre": titre, "corps": corps, "url": url})
    ok, ko = 0, 0
    for ab in abonnements:
        try:
            webpush(
                subscription_info={
                    "endpoint": ab["endpoint"],
                    "keys": {"p256dh": ab["p256dh"], "auth": ab["auth"]},
                },
                data=charge,
                vapid_private_key=cles.privee,
                vapid_claims={"sub": cles.sujet},
                timeout=15,
            )
            ok += 1
        except WebPushException as exc:
            statut = getattr(exc.response, "status_code", None)
            # Le corps de la reponse dit POURQUOI. Sans lui, un echec de push
            # est indiscernable d'un autre : abonnement mort, jeton VAPID
            # refuse, charge trop grosse, quota. On le journalise toujours.
            corps = ""
            try:
                corps = (exc.response.text or "").strip()[:300]
            except Exception:
                pass
            if statut in (404, 410):
                db.supprimer_abonnement(ab["endpoint"])
                log.info(
                    "abonnement push expire (HTTP %s), retire : %s | %s",
                    statut, ab["endpoint"][:60], corps,
                )
            else:
                log.error("push echoue (HTTP %s) : %s | %s", statut, exc, corps)
            ko += 1
        except Exception as exc:
            log.error("push echoue : %s", exc)
            ko += 1
    return ok, ko


# --------------------------------------------------------------------------
# Mail de repli
# --------------------------------------------------------------------------


def _reglages_smtp() -> tuple[str, int, str, str]:
    """(hote, port, utilisateur, motdepasse) pour le repli mail.

    ATTENTION, PIEGE DEJA RENCONTRE : un relais local peut accepter tout ce
    qu'on lui remet et n'acheminer rien : *aucun* message ne sort de la
    machine. Un repli pointe sur 127.0.0.1:25 echouait donc en silence - or le
    repli existe precisement pour les cas ou le push ne passe pas.

    On sort donc par le SMTP de Gmail, en 587 comme en 465, avec le MEME mot
    de passe d'application que l'IMAP : une seule chose a renseigner, une
    seule chose a revoquer.
    """
    hote = os.environ.get("VEILLE_SMTP_HOTE", "smtp.gmail.com")
    port = int(os.environ.get("VEILLE_SMTP_PORT", "587"))
    utilisateur = os.environ.get("VEILLE_SMTP_UTILISATEUR") or os.environ.get(
        "VEILLE_IMAP_UTILISATEUR", ""
    )
    motdepasse = os.environ.get("VEILLE_SMTP_MOTDEPASSE") or os.environ.get(
        "VEILLE_IMAP_MOTDEPASSE", ""
    )
    return hote, port, utilisateur, motdepasse


def envoyer_mail(sujet: str, corps: str, destinataire: str | None = None) -> bool:
    dest = destinataire or os.environ.get("VEILLE_MAIL_DESTINATAIRE", "")
    if not dest:
        log.warning("mail de repli : VEILLE_MAIL_DESTINATAIRE non configure")
        return False

    hote, port, utilisateur, motdepasse = _reglages_smtp()
    if not utilisateur and hote.endswith("gmail.com"):
        log.warning(
            "mail de repli impossible : aucun identifiant SMTP. Renseigne "
            "VEILLE_IMAP_UTILISATEUR / VEILLE_IMAP_MOTDEPASSE dans config/.env"
        )
        return False

    message = EmailMessage()
    message["Subject"] = sujet
    # Gmail refuse un expediteur qui n'est pas le compte authentifie.
    message["From"] = utilisateur or os.environ.get(
        "VEILLE_MAIL_EXPEDITEUR", f"veille-emploi@{os.uname().nodename}"
    )
    message["To"] = dest
    message.set_content(corps)

    try:
        if port == 465:
            serveur: smtplib.SMTP = smtplib.SMTP_SSL(hote, port, timeout=25)
        else:
            serveur = smtplib.SMTP(hote, port, timeout=25)
            if port != 25:
                serveur.starttls()
        with serveur:
            if utilisateur:
                serveur.login(utilisateur, motdepasse)
            serveur.send_message(message)
        log.info("mail de repli remis a %s via %s:%d", dest, hote, port)
        return True
    except Exception as exc:
        log.error("mail de repli echoue (%s:%d) : %s", hote, port, exc)
        return False


# --------------------------------------------------------------------------
# Composition du message de veille
# --------------------------------------------------------------------------


def prevenir_nouvelles_offres(nouvelles: list[dict[str, Any]], base_url: str = "") -> None:
    """Notifie les offres qui valent le derangement.

    On ne notifie pas tout : seulement ce qui depasse le seuil "interessant",
    sinon le telephone sonne pour rien et la notification perd son sens.
    """
    from . import reglages

    seuil = reglages.lire_seuil()
    dignes = [o for o in nouvelles if o.get("score", 0) >= seuil]
    if not dignes:
        log.info("%d nouvelle(s) offre(s), aucune au-dessus du seuil de %g", len(nouvelles), seuil)
        return

    meilleure = max(dignes, key=lambda o: o.get("score", 0))
    if len(dignes) == 1:
        titre = "1 nouvelle offre"
        corps = f"{meilleure['titre']} - {meilleure.get('employeur') or 'employeur inconnu'} ({meilleure['score']:g} pts)"
    else:
        titre = f"{len(dignes)} nouvelles offres"
        corps = f"La mieux placee : {meilleure['titre']} ({meilleure['score']:g} pts)"

    ok, ko = envoyer_push(titre, corps, url="/?filtre=nouveau")
    log.info("push : %d envoye(s), %d echec(s)", ok, ko)

    # Repli mail : seulement si aucun push n'est parti. Couvre l'appareil hors
    # ligne, les permissions de notification revoquees sans y penser, et le
    # telephone laisse de cote.
    if ok:
        db.marquer_etat_collecte("notification", resultat=f"push vers {ok} appareil(s)")
        return

    lignes = [
        f"- [{o['score']:g}] {o['titre']} | {o.get('employeur') or '?'} | {o.get('lieu') or '?'}"
        f"\n  {o.get('url') or 'lien indisponible'}"
        for o in sorted(dignes, key=lambda x: -x.get("score", 0))
    ]
    remis = envoyer_mail(
        f"[Veille emploi] {titre}",
        "\n".join(lignes) + (f"\n\nConsole : {base_url}" if base_url else ""),
    )
    if remis:
        db.marquer_etat_collecte("notification", resultat="repli mail (aucun appareil joignable)")
    else:
        # Les deux canaux sont tombes : il faut que ca se voie dans `veille etat`,
        # pas seulement dans un journal que personne ne lit.
        log.error(
            "AUCUNE NOTIFICATION REMISE pour %d offre(s) au-dessus du seuil "
            "- ni push, ni mail. Verifie config/.env et le HTTPS du tailnet.",
            len(dignes),
        )
        db.marquer_etat_collecte(
            "notification", resultat=f"ECHEC TOTAL : {len(dignes)} offre(s) non signalee(s)"
        )
