/**
 * RaportProdukcyjny Service Worker (PWA Offline Engine)
 * Version: 2.0.0-user-scoped
 *
 * Offline model:
 * - static assets are cached globally;
 * - successful authenticated HTML pages are cached in a cache partitioned by
 *   user id, so the same user's visited screens remain available offline;
 * - API responses and downloads are never cached;
 * - logout/anonymous responses clear the active offline user scope;
 * - legacy caches that were not user-scoped are removed on activation.
 */

const STATIC_CACHE_NAME = 'rp-pwa-static-v4';
const PAGE_CACHE_PREFIX = 'rp-pwa-pages-v2-user-';
const META_CACHE_NAME = 'rp-pwa-meta-v2';
const ACTIVE_USER_META_URL = '/__rp_offline_meta__/active-user';

const STATIC_ASSETS = [
    '/static/css/style.css',
    '/static/scripts.js',
    '/static/offline_fallback.html',
    '/static/js/offline_store.js',
    '/static/js/offline_scan_buffer.js',
    '/static/js/scanner_i18n.js',
    '/static/js/pwa_init.js',
    '/static/js/dynamic_eval_guard.js',
    '/static/js/print_bridge_browser_guard.js',
    '/static/manifest.json'
];

function normalizeUserId(value) {
    const candidate = String(value == null ? '' : value).trim();
    return /^\d+$/.test(candidate) ? candidate : '';
}

function isSameOriginStatic(url) {
    return url.origin === self.location.origin && url.pathname.startsWith('/static/');
}

function pageCacheName(userId) {
    return PAGE_CACHE_PREFIX + userId;
}

async function setActiveUser(userId) {
    const normalized = normalizeUserId(userId);
    const cache = await caches.open(META_CACHE_NAME);
    const metaRequest = new Request(new URL(ACTIVE_USER_META_URL, self.location.origin).toString());
    if (!normalized) {
        await cache.delete(metaRequest);
        return '';
    }
    await cache.put(
        metaRequest,
        new Response(normalized, {
            headers: { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' }
        })
    );
    return normalized;
}

async function getActiveUser() {
    try {
        const cache = await caches.open(META_CACHE_NAME);
        const metaRequest = new Request(new URL(ACTIVE_USER_META_URL, self.location.origin).toString());
        const response = await cache.match(metaRequest);
        if (!response) return '';
        return normalizeUserId(await response.text());
    } catch (e) {
        return '';
    }
}

async function getOfflineFallback() {
    const cache = await caches.open(STATIC_CACHE_NAME);
    return cache.match('/static/offline_fallback.html');
}

async function getCachedNavigation(request) {
    const userId = await getActiveUser();
    if (!userId) return null;
    const cache = await caches.open(pageCacheName(userId));
    return cache.match(request);
}

async function cacheNavigationForUser(request, response, userId) {
    const normalized = normalizeUserId(userId);
    if (!normalized || !response || !response.ok) return;
    const contentType = String(response.headers.get('Content-Type') || '').toLowerCase();
    if (!contentType.includes('text/html')) return;

    try {
        const cache = await caches.open(pageCacheName(normalized));
        await cache.put(request, response.clone());
    } catch (error) {
        console.warn('[SW] Failed to store user-scoped offline page:', error);
    }
}

async function navigationResponse(request) {
    try {
        const networkResponse = await fetch(request, { cache: 'no-store' });

        if (networkResponse && [502, 503, 504].includes(networkResponse.status)) {
            const cachedPage = await getCachedNavigation(request);
            if (cachedPage) return cachedPage;
            return (await getOfflineFallback()) || networkResponse;
        }

        const responseOwner = String(networkResponse.headers.get('X-RP-Offline-User') || '').trim();
        const userId = normalizeUserId(responseOwner);

        if (userId) {
            await setActiveUser(userId);
            await cacheNavigationForUser(request, networkResponse, userId);
        } else {
            // A successful anonymous response (login/logout/public page) closes
            // the prior user's offline scope. Its cache may remain on disk for
            // that owner, but cannot be selected by another logged-in user.
            await setActiveUser(null);
        }

        return networkResponse;
    } catch (error) {
        const cachedPage = await getCachedNavigation(request);
        if (cachedPage) {
            console.log('[SW] Serving cached page for active offline user:', request.url);
            return cachedPage;
        }
        return (await getOfflineFallback()) || Response.error();
    }
}

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(STATIC_CACHE_NAME)
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
                    const keep = key === STATIC_CACHE_NAME ||
                        key === META_CACHE_NAME ||
                        key.startsWith(PAGE_CACHE_PREFIX);
                    const isOurOldCache = key.startsWith('rp-pwa-');
                    if (!keep && isOurOldCache) {
                        console.log('[SW] Removing legacy/unscoped cache:', key);
                        return caches.delete(key);
                    }
                    return Promise.resolve(false);
                })
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('message', (event) => {
    const data = event.data || {};
    if (data.type !== 'RP_SET_OFFLINE_USER') return;
    event.waitUntil((async () => {
        const requestedUser = normalizeUserId(data.userId);
        if (!requestedUser) {
            await setActiveUser(null);
            return;
        }
        if (requestedUser === await getActiveUser()) return;
        // A stale tab must not switch the browser back to another user's pages.
        // Only the current server session can establish a different owner.
        try {
            const response = await fetch(new URL('/', self.location.origin).toString(), {
                method: 'HEAD', credentials: 'same-origin', cache: 'no-store'
            });
            const serverOwner = normalizeUserId(response.headers.get('X-RP-Offline-User'));
            if (response.ok && serverOwner === requestedUser) await setActiveUser(serverOwner);
        } catch (error) {
            // Offline messages can retain the existing owner, never replace it.
        }
    })());
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;

    const isNavigation = request.mode === 'navigate' || request.headers.get('accept')?.includes('text/html');
    if (isNavigation) {
        event.respondWith(navigationResponse(request));
        return;
    }

    // API responses, reports, downloads and every other dynamic endpoint bypass
    // Cache Storage completely. Mutation persistence is handled by IndexedDB.
    if (!isSameOriginStatic(url)) return;

    // Same-origin static assets only: stale-while-revalidate.
    event.respondWith(
        caches.match(request).then((cachedResponse) => {
            const refresh = fetch(request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
                        const responseClone = networkResponse.clone();
                        caches.open(STATIC_CACHE_NAME).then((cache) => cache.put(request, responseClone));
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
