// AgroMES Service Worker v2 — PWA + Web Push Notifications
const CACHE_NAME = 'agromes-v2';

self.addEventListener('install', (e) => {
  console.log('[SW] Install');
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  console.log('[SW] Activate');
  e.waitUntil(clients.claim());
});

self.addEventListener('fetch', (e) => {
  // Minimal fetch pass-through for PWA requirements
  e.respondWith(
    fetch(e.request).catch(() => {
      return new Response('Brak połączenia z siecią', { status: 503 });
    })
  );
});

// =====================================================
// WEB PUSH — odbieranie powiadomień w tle
// Działa nawet gdy ekran telefonu jest wyłączony!
// =====================================================
self.addEventListener('push', function(event) {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'AgroMES', body: event.data ? event.data.text() : '' };
  }

  const title   = data.title  || 'AgroMES';
  const body    = data.body   || '';
  const url     = data.url    || '/';
  const icon    = data.icon   || '/static/agro_logo.png';
  const badge   = '/static/favicon.ico';

  const options = {
    body:              body,
    icon:              icon,
    badge:             badge,
    data:              { url: url },
    requireInteraction: false,
    vibrate:           [200, 100, 200],   // wibracja na Androidzie
    // sound:          url_do_pliku_mp3,   // iOS nie obsługuje, Android tak
    tag:               'agromes-push',     // grupuje powiadomienia
    renotify:          true,              // ponawia dźwięk przy tym samym tag
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// =====================================================
// Kliknięcie powiadomienia → otwiera właściwy widok
// =====================================================
self.addEventListener('notificationclick', function(event) {
  event.notification.close();

  const targetUrl = (event.notification.data && event.notification.data.url)
    ? event.notification.data.url
    : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
      // Jeśli aplikacja jest już otwarta — przełącz na nią i przejdź do URL
      for (const client of clientList) {
        if ('focus' in client) {
          client.focus();
          if ('navigate' in client) {
            client.navigate(targetUrl);
          }
          return;
        }
      }
      // Jeśli nie ma otwartego okna — otwórz nowe
      return clients.openWindow(targetUrl);
    })
  );
});
