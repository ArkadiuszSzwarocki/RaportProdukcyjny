

// A simple, offline-first service worker
const CACHE_NAME = 'mleczna-droga-cache-v2.0'; // API calls are now excluded from cache
const urlsToCache = [
  '/',
  '/index.html',
  // Main JS bundle is typically named index.js or similar, adjust if needed
  // We don't know the exact name of the bundled JS, so we rely on dynamic caching.
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('ServiceWorker: Caching app shell');
        return cache.addAll(urlsToCache);
      })
      .catch(error => {
        console.error('ServiceWorker: Failed to pre-cache app shell.', error);
      })
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;

  // Ignore non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Bypass cache for API calls - ALWAYS fetch from network
  if (request.url.includes('/api/') || request.url.includes(':3002')) {
    event.respondWith(fetch(request));
    return;
  }

  // Bypass cache for heartbeat checks or specific external domains
  if (request.url.includes('google.com')) {
    event.respondWith(fetch(request));
    return;
  }
  
  // Stale-While-Revalidate strategy
  event.respondWith(
    caches.open(CACHE_NAME).then(cache => {
      return cache.match(request).then(cachedResponse => {
        // Fetch from network in the background
        const fetchPromise = fetch(request).then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            cache.put(request, networkResponse.clone());
          }
          return networkResponse;
        }).catch(err => {
            console.warn(`ServiceWorker: Network fetch failed for ${request.url}.`, err);
            // If network fails, and we didn't have a cached response,
            // we might need a fallback. For navigation, it's crucial.
            if (request.mode === 'navigate' && !cachedResponse) {
                return caches.match('/index.html');
            }
        });

        // Return cached response immediately if available, otherwise wait for network
        return cachedResponse || fetchPromise;
      });
    })
  );
});


self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            console.log('ServiceWorker: Deleting old cache', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});