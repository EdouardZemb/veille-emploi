/* Service worker de la console de veille.
 *
 * Deux roles seulement :
 *   - recevoir les notifications push et les afficher ;
 *   - ouvrir la console au bon endroit quand on tape la notification.
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
