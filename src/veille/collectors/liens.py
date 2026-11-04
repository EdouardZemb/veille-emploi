"""Resolution des liens de suivi contenus dans les alertes mail.

Les alertes LinkedIn / Indeed / jobs.ch n'envoient jamais l'URL de l'annonce :
elles envoient un redirecteur qui trace le clic. Deux alertes differentes vers
la MEME annonce portent deux redirecteurs differents. Sans resolution, la
deduplication ne marche pas.

Trois strategies, de la moins chere a la plus chere :

1. Extraction locale : beaucoup de redirecteurs portent l'URL finale dans un
   parametre (`url=`, `u=`, `target=`...). Gratuit, instantane, hors ligne.
2. Reconstruction par identifiant : LinkedIn et Indeed exposent l'identifiant
   de l'offre dans le lien ; on reconstruit l'URL canonique sans requete.
3. Requete HEAD en dernier recours, en suivant les redirections.

Le point 3 est une simple requete HTTP vers un lien que le site a lui-meme
envoye a Edouard, au rythme d'un mail recu. Ce n'est pas du parcours de
catalogue : aucune page de resultats n'est explore.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

from ..models import canoniser_url

log = logging.getLogger(__name__)

# Parametres qui, dans un redirecteur, contiennent l'URL de destination.
_PARAMS_DESTINATION = ("url", "u", "target", "dest", "destination", "redirect", "r", "link", "to")

# Hotes connus comme redirecteurs : on tente la resolution reseau pour eux.
_REDIRECTEURS = (
    "linkedin.com/comm/",
    "click.linkedin.com",
    "www.linkedin.com/e/",
    "indeed.com/rc/clk",
    "click.appcast.io",
    "email.jobs.ch",
    "links.jobs.ch",
    "click.jobup.ch",
    "t.email",
    "sendgrid.net",
    "mandrillapp.com",
    "list-manage.com",
)

_RE_LINKEDIN_ID = re.compile(r"(?:jobs/view/|jobPosting[:/]|currentJobId=|/jobs/(?:view/)?)(\d{6,})")
_RE_INDEED_JK = re.compile(r"[?&]jk=([0-9a-f]{10,20})")


def _depuis_parametre(url: str) -> str | None:
    """Extrait l'URL finale si elle est portee par un parametre du redirecteur."""
    q = parse_qs(urlsplit(url).query)
    for cle in _PARAMS_DESTINATION:
        for variante in (cle, cle.upper()):
            if variante in q and q[variante]:
                candidat = unquote(q[variante][0])
                if candidat.startswith(("http://", "https://")):
                    return candidat
    return None


def _par_identifiant(url: str) -> str | None:
    """Reconstruit l'URL canonique a partir d'un identifiant d'offre connu."""
    m = _RE_LINKEDIN_ID.search(url)
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}/"
    m = _RE_INDEED_JK.search(url)
    if m:
        hote = "fr.indeed.com" if ".fr" in url or "indeed.fr" in url else "www.indeed.com"
        return f"https://{hote}/viewjob?jk={m.group(1)}"
    return None


def _est_redirecteur(url: str) -> bool:
    bas = url.lower()
    return any(marqueur in bas for marqueur in _REDIRECTEURS)


def resoudre(url: str, client: httpx.Client | None = None, autoriser_reseau: bool = True) -> str:
    """Retourne l'URL reelle de l'annonce, canonisee.

    N'echoue jamais : en cas de probleme on rend l'URL d'origine nettoyee, et
    la deduplication se rabattra sur titre+employeur.
    """
    if not url:
        return ""

    for strategie in (_depuis_parametre, _par_identifiant):
        trouve = strategie(url)
        if trouve:
            # Un parametre peut lui-meme contenir un redirecteur : on repasse.
            suivant = _par_identifiant(trouve)
            return canoniser_url(suivant or trouve)

    if not autoriser_reseau or not _est_redirecteur(url):
        return canoniser_url(url)

    propre = client is None
    cli = client or httpx.Client(
        timeout=12.0,
        follow_redirects=True,
        headers={"User-Agent": "veille-emploi/1.0 (usage personnel)"},
    )
    try:
        rep = cli.head(url)
        if rep.status_code >= 400 or not str(rep.url):
            rep = cli.get(url)
        finale = str(rep.url)
        # La page d'arrivee peut encore contenir l'identifiant sous une autre forme.
        return canoniser_url(_par_identifiant(finale) or finale)
    except Exception as exc:  # reseau, TLS, boucle de redirection...
        log.debug("resolution impossible pour %s : %s", url[:80], exc)
        return canoniser_url(url)
    finally:
        if propre:
            cli.close()
