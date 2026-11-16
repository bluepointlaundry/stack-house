/* Stack House service worker: shows push notifications and opens the app when one is tapped. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data && event.data.text() }; }
  const urgent = !!data.urgent;
  event.waitUntil((async () => {
    await self.registration.showNotification(data.title || 'Stack House', {
      body: data.body || '',
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/badge-96.png',
      tag: data.tag || undefined,
      data: { url: data.url || '/' },
      requireInteraction: urgent,
      vibrate: urgent ? [300, 120, 300, 120, 300] : [120],
    });
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    windows.forEach((c) => c.postMessage({ type: 'refresh' }));
  })());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || '/', self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        client.postMessage({ type: 'open', url });
        return client.focus();
      }
    }
    return self.clients.openWindow(url);
  })());
});
