/**
 * RaportProdukcyjny Service Worker (PWA Offline Engine)
 * Version: 1.0.0
 * Provides robust offline navigation, static asset caching, and offline fallback.
 */

const CACHE_NAME = 'rp-pwa-v1';
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/scripts.js',
    '/static/offline_fallback.html',
    '/static/js/offline_scan_buffer.js',
    '/static/js/scanner_i18n.js',
    '/static/js/pwa_init.js',
    '/static/manifest.json'
];

// 1. INSTALL: Pre-cache essential core assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] Pre-caching static assets');
            return cache.addAll(STATIC_ASSETS).catch((err) => {
                console.warn('[SW] Some assets failed to pre-cache', err);
            });
        }).then(() => self.skipWaiting())
    );
});

// 2. ACTIVATE: Clean up old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) {
                        console.log('[SW] Removing old cache:', key);
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// 3. FETCH: Strategy based on request type
self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);

    // Skip non-GET requests and API data writes (they are handled by offline_scan_buffer.js)
    if (request.method !== 'GET') {
        return;
    }

    // Skip API routes from caching to avoid stale responses, except when network fails
    const isApiRequest = url.pathname.startsWith('/api/');

    if (isApiRequest) {
        return;
    }

    // HTML Page Navigation: Network-First with Cache Fallback
    if (request.mode === 'navigate' || request.headers.get('accept')?.includes('text/html')) {
        event.respondWith(
            fetch(request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const responseClone = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, responseClone);
                        });
                    }
                    return networkResponse;
                })
                .catch(async () => {
                    console.log('[SW] Network failed, attempting cache retrieval for:', request.url);
                    const cachedResponse = await caches.match(request);
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    // If page is not in cache, serve offline fallback
                    return caches.match('/static/offline_fallback.html');
                })
        );
        return;
    }

    // Static Assets (CSS, JS, Fonts, Images): Cache-First / Stale-While-Revalidate
    event.respondWith(
        caches.match(request).then((cachedResponse) => {
            if (cachedResponse) {
                // Fetch in background to update cache for next time
                fetch(request).then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, networkResponse));
                    }
                }).catch(() => {});
                return cachedResponse;
            }

            return fetch(request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const responseClone = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(request, responseClone);
                    });
                }
                return networkResponse;
            });
        })
    );
});
