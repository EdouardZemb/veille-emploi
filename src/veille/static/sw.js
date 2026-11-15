/* Service worker de la console de veille.
 *
 * Trois roles seulement :
 *   - recevoir les notifications push et les afficher ;
 *   - ouvrir la console au bon endroit quand on tape la notification ;
 *   - renvoyer au serveur l'abonnement que le navigateur a change.
 *
 * Volontairement AUCUN cache hors ligne : les offres changent, et une console
 * qui affiche des donnees perimees serait pire qu'une console indisponible.
 */

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('push', event => {
  let donnees = { titre: 'Veille emploi', corps: 'Nouvelles offres disponibles.', url: '/' };
  if (event.data) {
    try { donnees = { ...donnees, ...event.data.json() }; }
    catch (_) { donnees.corps = event.data.text(); }
  }
  event.waitUntil(
    self.registration.showNotification(donnees.titre, {
      body: donnees.corps,
      icon: '/static/icone-192.png',
      badge: '/static/icone-192.png',
      tag: 'veille-emploi',
      renotify: true,
      data: { url: donnees.url || '/' },
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const cible = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(fenetres => {
      for (const f of fenetres) {
        if ('focus' in f) { f.navigate(cible); return f.focus(); }
      }
      return self.clients.openWindow(cible);
    })
  );
});

// Le navigateur a change l'abonnement (decision 13 du plan du lot 3). Chrome ne le dit
// presque jamais, et l'un ou l'autre abonnement peut manquer : le renvoi a l'ouverture de
// la console reste le remede principal.
self.addEventListener('pushsubscriptionchange', evenement => {
  evenement.waitUntil(renouvelerAbonnement(evenement));
});

// Renvoie le nouvel abonnement, en s'abonnant de nouveau avec la cle de l'ancien s'il n'en
// porte pas (un ArrayBuffer, passe tel quel), puis retire l'ancien s'il differe. Sans l'un ni
// l'autre, rien : l'ouverture suivante repare. Les ecritures portent l'origine de la console
// (Referrer-Policy: same-origin), que le serveur exige.
async function renouvelerAbonnement(evenement) {
  const ancien = evenement.oldSubscription || null;
  let nouveau = evenement.newSubscription || null;
  const cle = ancien && ancien.options && ancien.options.applicationServerKey;
  if (!nouveau && cle) {
    nouveau = await self.registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: cle,
    });
  }
  if (!nouveau) return;
  await fetch('/api/push/abonnement', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(nouveau.toJSON()),
  });
  if (ancien && ancien.endpoint !== nouveau.endpoint) {
    await fetch(`/api/push/abonnement?endpoint=${encodeURIComponent(ancien.endpoint)}`, {
      method: 'DELETE',
      credentials: 'same-origin',
    });
  }
}
