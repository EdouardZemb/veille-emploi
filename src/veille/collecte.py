"""La collecte : chaque source, puis les notifications.

Deux appelants. `veille collecter`, que lance le minuteur systemd du serveur du
tailnet (ou la main d'Edouard), lui passe `print` : sa sortie ne change pas. Le
planificateur de la console en conteneur (planificateur.py), qui n'a pas de
minuteur, garde le journal par defaut.
"""

from __future__ import annotations

import logging
from typing import Callable

from . import config, db, notifications, passkeys

log = logging.getLogger(__name__)


def _journaliser(ligne: str) -> None:
    """La sortie par defaut : une ligne du journal par ligne du compte rendu.
    La ligne vide qui separe le total, a la CLI, n'a rien a faire au journal."""
    if ligne.strip():
        log.info(ligne)


def collecter(
    jours: int = 7,
    sources: set[str] | None = None,
    notifier: bool = True,
    sortie: Callable[[str], None] = _journaliser,
    erreur: Callable[[str], None] = log.warning,
) -> int:
    """Lance les sources demandees (toutes par defaut) ; rend le nombre de nouvelles offres.

    `sortie` recoit le compte rendu, ligne a ligne ; `erreur`, l'echec d'une
    source, qui n'arrete pas les suivantes. La CLI passe la sortie d'erreur.

    Sans configuration designee, elle refuse (`ConfigurationInvalide`) avant de
    toucher a la base : les offres seraient notees par l'exemple.
    """
    config.exiger_designee()
    # Importes ici : les collecteurs tirent IMAP, RSS et HTTP, inutiles a qui
    # importe ce module sans collecter (la console, au demarrage).
    from .collectors import arbeitnow, courriel, france_travail, rss
    from .collectors.base import ingerer

    db.initialiser()
    avant = {o["id"] for o in db.offres_nouvelles_non_vues()}

    retenues = []
    for module, etiquette in (
        (france_travail, "france_travail"),
        (courriel, "courriel"),
        (rss, "rss"),
        (arbeitnow, "arbeitnow"),
    ):
        if sources and etiquette not in sources:
            continue
        retenues.append((module, etiquette))

    total_nouvelles = 0
    for module, etiquette in retenues:
        sortie(f"--- {etiquette} ---")
        try:
            offres = list(
                module.collecter(jours=jours)
                if etiquette in ("france_travail", "courriel")
                else module.collecter()
            )
        except Exception as exc:
            erreur(f"  ECHEC : {exc}")
            db.marquer_etat_collecte(etiquette, resultat=f"echec : {exc}")
            continue
        rapport = ingerer(offres, etiquette)
        total_nouvelles += rapport.nouvelles
        sortie(f"  {rapport.resume()}")
        for e in rapport.erreurs[:5]:
            sortie(f"    ! {e}")

    sortie("")
    sortie(f"Total : {total_nouvelles} nouvelle(s) offre(s)")

    if total_nouvelles and notifier:
        fraiches = [o for o in db.offres_nouvelles_non_vues() if o["id"] not in avant]
        try:
            base_url, _ = passkeys.origine_attendue()
        except passkeys.OrigineInconnue:
            base_url = ""
        notifications.prevenir_nouvelles_offres(fraiches, base_url=base_url)
    return total_nouvelles
