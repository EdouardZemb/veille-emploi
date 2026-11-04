"""Le planificateur : la collecte et la purge, sans minuteur systemd.

Un conteneur n'a pas de minuteur : un fil de la console en tient lieu
(ADR-0002, section 5). Il tourne dans tous les modes :

- il purge les sessions et les liens expires, au demarrage puis toutes les
  six heures, y compris sur la console du tailnet (mode systemd) ;
- en `prod` seulement, il collecte aux heures de la frequence lue en base, qu'il
  relit a chaque reveil : un changement fait dans Reglages s'applique dans la
  minute. Sur le serveur du tailnet, c'est toujours `veille-collecte.timer`.

Une seule collecte a la fois, celle du fil ou celle du bouton « Collecter
maintenant ». Une erreur est journalisee ; elle n'arrete ni le fil ni la console.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable

from . import auth, collecte, config, db, reglages

log = logging.getLogger(__name__)

NOM_FIL = "veille-planificateur"
# Le fil se reveille au moins une fois par minute : une collecte part au plus
# une minute apres son heure, et `arreter()` le reveille aussitot.
ATTENTE_MAX = timedelta(minutes=1)
INTERVALLE_PURGE = timedelta(hours=6)
# Ce qu'`arreter()` accorde a chaque fil avant de rendre la main.
ATTENTE_ARRET = 2.0
JOURS = 7  # `veille collecter --jours 7`


class Planificateur:
    def __init__(self, horloge: Callable[[], datetime] | None = None) -> None:
        # Sans horloge donnee, `auth.maintenant` est relue a chaque fois : les
        # tests la remplacent apres la creation de PLANIFICATEUR.
        self._horloge = horloge
        self._verrou = threading.Lock()  # tenu pendant une collecte
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None
        self._fil_collecte: threading.Thread | None = None
        self._derniere_purge: datetime | None = None
        # L'instant de la derniere collecte du fil (ou du demarrage) : l'echeance
        # suivante se calcule depuis lui, la meme n'est donc jamais collectee
        # deux fois. Un redemarrage repart de son propre instant : une echeance
        # tombee pendant l'arret n'est pas rattrapee (un processus suspendu puis
        # reveille, lui, en rattrape une).
        self._repere: datetime | None = None

    def _maintenant(self) -> datetime:
        return (self._horloge or auth.maintenant)()

    # ----------------------------------------------------------------------
    # Le fil
    # ----------------------------------------------------------------------

    def demarrer(self) -> None:
        """Une purge tout de suite (avant la premiere requete), puis le fil."""
        instant = self._maintenant()
        self._purger(instant)
        if self._fil is not None and self._fil.is_alive() and not self._arret.is_set():
            return
        self._repere = instant
        self._arret = threading.Event()
        self._fil = threading.Thread(
            target=self._boucle, args=(self._arret,), name=NOM_FIL, daemon=True
        )
        self._fil.start()

    def arreter(self) -> None:
        """Reveille le fil et l'attend un instant ; de meme pour une collecte lancee a la main.

        Une collecte encore en cours est abandonnee a la sortie du processus
        (fil `daemon`) : sa transaction en cours n'est pas ecrite.
        """
        self._arret.set()
        for fil in (self._fil, self._fil_collecte):
            if fil is None or fil is threading.current_thread():
                continue
            fil.join(ATTENTE_ARRET)
            if fil.is_alive():
                log.warning("%s tourne encore a l'arret : une collecte est en cours", fil.name)

    def _boucle(self, arret: threading.Event) -> None:
        while not arret.wait(ATTENTE_MAX.total_seconds()):
            try:
                self.tour(self._maintenant())
            except Exception:
                log.exception("le tour du planificateur a echoue")

    # ----------------------------------------------------------------------
    # Un reveil
    # ----------------------------------------------------------------------

    def tour(self, instant: datetime) -> None:
        """Ce que fait le fil a chaque reveil : purger, puis collecter, chacun a son heure."""
        if self._derniere_purge is None or instant - self._derniere_purge >= INTERVALLE_PURGE:
            self._purger(instant)
        if config.environnement() != "prod":
            return
        if self._repere is None:
            self._repere = instant
        cle = reglages.lire_frequence()["cle"]
        if reglages.prochain_passage(cle, self._repere) > instant:
            return
        self._repere = instant
        if not self._verrou.acquire(blocking=False):
            log.info("collecte de %s sautee : une collecte est deja en cours",
                     instant.astimezone(reglages.PARIS).strftime("%H:%M"))
            return
        try:
            self._collecter()
        finally:
            self._verrou.release()

    def _purger(self, instant: datetime) -> None:
        self._derniere_purge = instant
        try:
            sessions, liens = db.purger_expires(auth._iso(instant))
        except Exception:
            log.exception("la purge des sessions et des liens expires a echoue")
            return
        if sessions or liens:
            log.info("purge : %d session(s) et %d lien(s) expires", sessions, liens)

    def _collecter(self) -> None:
        """Une collecte ; le verrou est deja tenu par l'appelant."""
        try:
            collecte.collecter(jours=JOURS)
        except config.ConfigurationInvalide as exc:
            log.warning("collecte sautee : %s", exc)
        except Exception as exc:
            log.exception("la collecte a echoue : %s", exc)

    # ----------------------------------------------------------------------
    # « Collecter maintenant »
    # ----------------------------------------------------------------------

    def collecter_maintenant(self) -> bool:
        """Lance une collecte dans un fil a part ; faux si une collecte tourne deja."""
        if not self._verrou.acquire(blocking=False):
            return False
        self._fil_collecte = threading.Thread(
            target=self._collecte_a_la_main, name="veille-collecte", daemon=True
        )
        try:
            self._fil_collecte.start()
        except BaseException:
            self._verrou.release()
            raise
        return True

    def _collecte_a_la_main(self) -> None:
        try:
            self._collecter()
        finally:
            self._verrou.release()


PLANIFICATEUR = Planificateur()
