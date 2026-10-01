/**
 * RaportProdukcyjny Service Worker (PWA Offline Engine)
 * Version: 1.1.0-security
 *
 * Security rules:
 * - never cache authenticated/dynamic HTML pages;
 * - never cache API responses;
 * - cache only same-origin /static/ assets;
 * - delete legacy caches that may already contain authenticated pages.
 */

const CACHE_NAME = 'rp-pwa-static-v3';
const LEGACY_CACHE_PREFIXES = ['rp-pwa-'];
const STATIC_ASSETS = [
    '/static/css/style.css',
    '/static/scripts.js',
    '/static/offline_fallback.html',
    '/static/js/offline_scan_buffer.js',
    '/static/js/scanner_i18n.js',
    '/static/js/pwa_init.js',
    '/static/js/dynamic_eval_guard.js',
    '/static/js/print_bridge_browser_guard.js',
    '/static/manifest.json'
];

function isSameOriginStatic(url) {
    return url.origin === self.location.origin && url.pathname.startsWith('/static/');
}

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(STATIC_ASSETS))
            .catch((err) => {
                console.warn('[SW] Some static assets failed to pre-cache', err);
            })
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.map((key) => {
                    const isLegacy = LEGACY_CACHE_PREFIXES.some((prefix) => key.startsWith(prefix));
                    if (key !== CACHE_NAME && isLegacy) {
                        console.log('[SW] Removing legacy cache:', key);
                        return caches.delete(key);
                    }
                    return Promise.resolve(false);
                })
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') {
        return;
    }

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) {
        return;
    }

    const isNavigation = request.mode === 'navigate' || request.headers.get('accept')?.includes('text/html');

    // Dynamic/authenticated HTML is network-only. On connectivity failure we may
    // serve only the static offline shell, never a previously authenticated page.
    if (isNavigation) {
        event.respondWith(
            fetch(request, { cache: 'no-store' })
                .then(async (networkResponse) => {
                    if (networkResponse && [502, 503, 504].includes(networkResponse.status)) {
                        const fallback = await caches.match('/static/offline_fallback.html');
                        if (fallback) return fallback;
                    }
                    return networkResponse;
                })
                .catch(async () => {
                    const fallback = await caches.match('/static/offline_fallback.html');
                    return fallback || Response.error();
                })
        );
        return;
    }

    // API, report downloads and every other dynamic endpoint bypass the cache.
    if (!isSameOriginStatic(url)) {
        return;
    }

    // Same-origin static assets only: stale-while-revalidate.
    event.respondWith(
        caches.match(request).then((cachedResponse) => {
            const refresh = fetch(request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
                        const responseClone = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
                    }
                    return networkResponse;
                })
                .catch(() => null);

            if (cachedResponse) {
                event.waitUntil(refresh);
                return cachedResponse;
            }

            return refresh.then((networkResponse) => networkResponse || Response.error());
        })
    );
});
