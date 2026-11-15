"""`pushsubscriptionchange` dans le service worker (E11, décision 13 du plan du lot 3).

Quand le navigateur change l'abonnement, `sw.js` renvoie le nouveau au serveur, en se réabonnant
avec la clé de l'ancien s'il n'en a pas reçu, puis retire l'ancien s'il diffère ; sans l'un ni
l'autre, il ne fait rien, et la prochaine ouverture de la console répare.

Chrome ne déclenche presque jamais l'événement : il s'éprouve sous Node, dans un harnais qui
charge `sw.js` avec un faux `self` (ses écouteurs notés, `skipWaiting` et `clients.claim`
fournis, `registration.pushManager.subscribe` simulé) et un faux `fetch` qui note ses appels. Les
faux abonnements portent `options.applicationServerKey` en `ArrayBuffer`, comme dans Chrome. Sans
Node, ces tests se sautent, ce que `SUITE_COMPLETE=1` interdit (CI).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import pytest

from tests.sauts import sauter

SW = Path(__file__).resolve().parents[1] / "src" / "veille" / "static" / "sw.js"
ANCIEN = "https://push.exemple.invalid/ancien"
NOUVEAU = "https://push.exemple.invalid/nouveau"
# Celui que rend le `subscribe` simulé.
REABONNE = "https://push.exemple.invalid/reabonne"
# Une clé publique inventée, de 65 octets comme une clé P-256 non compressée.
CLE = [4, *range(1, 65)]


def _node() -> str | None:
    return shutil.which("node") or shutil.which("node.exe")


pytestmark = pytest.mark.skipif(sauter(lambda: _node() is not None), reason="node absent")

HARNAIS = """
const SCENARIO = %(scenario)s;
const ecouteurs = {};
const appels = [];
const subscribes = [];
function abonnement(endpoint, cle) {
  return {
    endpoint,
    options: { userVisibleOnly: true, applicationServerKey: new Uint8Array(cle).buffer },
    toJSON: () => ({ endpoint, expirationTime: null,
                     keys: { p256dh: 'p256dh-' + endpoint, auth: 'auth-' + endpoint } }),
  };
}
const faux = {
  addEventListener: (type, ecouteur) => { ecouteurs[type] = ecouteur; },
  skipWaiting: () => Promise.resolve(),
  clients: { claim: () => Promise.resolve(), matchAll: () => Promise.resolve([]),
             openWindow: () => Promise.resolve(null) },
  registration: {
    showNotification: () => Promise.resolve(),
    pushManager: {
      subscribe: async options => {
        const cle = options.applicationServerKey;
        subscribes.push({ userVisibleOnly: options.userVisibleOnly,
                          type: Object.prototype.toString.call(cle),
                          octets: Array.from(new Uint8Array(cle)) });
        return abonnement(%(reabonne)s, Array.from(new Uint8Array(cle)));
      },
    },
  },
};
const fauxFetch = async (adresse, options = {}) => {
  appels.push({ adresse, methode: options.method || 'GET', credentials: options.credentials || '',
                corps: options.body === undefined ? null : JSON.parse(options.body) });
  return { ok: true, status: 200, json: async () => ({ ok: true }) };
};
new Function('self', 'fetch', %(source)s)(faux, fauxFetch);
(async () => {
  const evenement = {
    oldSubscription: SCENARIO.ancien
      && abonnement(SCENARIO.ancien.endpoint, SCENARIO.ancien.cle),
    newSubscription: SCENARIO.nouveau
      && abonnement(SCENARIO.nouveau.endpoint, SCENARIO.nouveau.cle),
    attente: null,
    waitUntil(promesse) { this.attente = promesse; },
  };
  let issue = 'pas de waitUntil';
  if (ecouteurs.pushsubscriptionchange) {
    ecouteurs.pushsubscriptionchange(evenement);
    if (evenement.attente) {
      try { await evenement.attente; issue = 'ok'; } catch (e) { issue = String(e); }
    }
  }
  console.log(JSON.stringify({ ecouteurs: Object.keys(ecouteurs), issue, appels, subscribes }));
})();
"""


def _changer(ancien: dict | None, nouveau: dict | None) -> dict:
    """Lance `pushsubscriptionchange` avec ces deux abonnements, et rend ce qu'il a fait."""
    harnais = HARNAIS % {
        "scenario": json.dumps({"ancien": ancien, "nouveau": nouveau}),
        "reabonne": json.dumps(REABONNE),
        "source": json.dumps(SW.read_text(encoding="utf-8")),
    }
    r = subprocess.run([_node()], input=harnais, capture_output=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    resultat = json.loads(r.stdout)
    assert "pushsubscriptionchange" in resultat["ecouteurs"]
    assert resultat["issue"] == "ok", resultat["issue"]
    return resultat


def _json(endpoint: str) -> dict:
    return {"endpoint": endpoint, "expirationTime": None,
            "keys": {"p256dh": f"p256dh-{endpoint}", "auth": f"auth-{endpoint}"}}


def _renvoi(endpoint: str) -> dict:
    return {"adresse": "/api/push/abonnement", "methode": "POST", "credentials": "same-origin",
            "corps": _json(endpoint)}


def _retrait(endpoint: str) -> dict:
    return {"adresse": f"/api/push/abonnement?endpoint={quote(endpoint, safe='')}",
            "methode": "DELETE", "credentials": "same-origin", "corps": None}


def test_un_nouvel_abonnement_est_renvoye_puis_l_ancien_retire():
    resultat = _changer({"endpoint": ANCIEN, "cle": CLE}, {"endpoint": NOUVEAU, "cle": CLE})
    assert resultat["appels"] == [_renvoi(NOUVEAU), _retrait(ANCIEN)]
    assert resultat["subscribes"] == []


def test_sans_nouvel_abonnement_le_service_worker_se_reabonne_avec_la_cle_d_avant():
    """La clé de l'ancien, un `ArrayBuffer`, passe telle quelle à `subscribe` : un code qui la
    traiterait en chaîne base64url (`atob`) lèverait."""
    resultat = _changer({"endpoint": ANCIEN, "cle": CLE}, None)
    assert resultat["subscribes"] == [
        {"userVisibleOnly": True, "type": "[object ArrayBuffer]", "octets": CLE}]
    assert resultat["appels"] == [_renvoi(REABONNE), _retrait(ANCIEN)]


def test_le_meme_abonnement_n_est_pas_retire():
    resultat = _changer({"endpoint": NOUVEAU, "cle": CLE}, {"endpoint": NOUVEAU, "cle": CLE})
    assert resultat["appels"] == [_renvoi(NOUVEAU)]


def test_sans_rien_a_renvoyer_le_service_worker_ne_fait_rien():
    resultat = _changer(None, None)
    assert resultat["appels"] == []
    assert resultat["subscribes"] == []
