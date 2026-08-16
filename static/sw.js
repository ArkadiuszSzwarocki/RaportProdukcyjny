// AgroMES Service Worker v2 — PWA + Web Push Notifications
const CACHE_NAME = 'agromes-v2';

const CACHE_ASSETS = [
  '/static/css/style.css',
  '/static/scripts.js',
  '/static/fonts/MaterialIcons-Regular.woff2',
  '/static/agro_logo.png'
];

self.addEventListener('install', (e) => {
  console.log('[SW] Install');
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(CACHE_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  console.log('[SW] Activate');
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
    ))
  );
  e.waitUntil(clients.claim());
});

self.addEventListener('fetch', (e) => {
  // Ignorujemy API zapytań (smartFetch obsłuży błędy offline za pomocą localStorage)
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('/api/')) return;

  e.respondWith(
    fetch(e.request).then(response => {
      // Jeśli to HTML lub static resource, aktualizujemy cache (Network First)
      if (response && response.status === 200) {
        const resClone = response.clone();
        caches.open(CACHE_NAME).then(cache => {
          cache.put(e.request, resClone);
        });
      }
      return response;
    }).catch(() => {
      // Offline fallback
      return caches.match(e.request).then(cachedResponse => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return new Response('<b>Brak zasięgu WiFi. Sprawdź połączenie i odśwież stronę.</b>', { 
            status: 200, 
            headers: {'Content-Type': 'text/html; charset=utf-8'}
        });
      });
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
