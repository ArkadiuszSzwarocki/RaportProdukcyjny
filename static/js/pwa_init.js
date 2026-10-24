/**
 * PWA & Service Worker Initializer
 * Registers the root service worker, publishes the current user scope and
 * displays an offline banner when connectivity drops.
 */

(function () {
    'use strict';

    function currentOfflineUserId() {
        const raw = window.__RP_OFFLINE_USER_ID;
        const candidate = String(raw == null ? '' : raw).trim();
        return /^\d+$/.test(candidate) ? candidate : null;
    }

    // Store last visited page for offline resume. Keep the legacy key for the
    // static fallback UI and a user-scoped copy for future migrations.
    try {
        if (!window.location.pathname.includes('offline_fallback')) {
            const lastPage = window.location.pathname + window.location.search;
            localStorage.setItem('rp_last_visited_page', lastPage);
            const userId = currentOfflineUserId();
            if (userId) {
                localStorage.setItem(`rp_last_visited_page:${userId}`, lastPage);
                localStorage.setItem('rp_offline_active_user', userId);
            }
        }
    } catch(e) {}

    function publishOfflineUser(registration) {
        const payload = {
            type: 'RP_SET_OFFLINE_USER',
            userId: currentOfflineUserId()
        };
        const worker = registration && (registration.active || registration.waiting || registration.installing);
        if (worker) worker.postMessage(payload);
    }

    // 1. Register Service Worker
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js', { scope: '/' })
                .then((registration) => {
                    console.log('[PWA] Service Worker registered with scope:', registration.scope);
                    publishOfflineUser(registration);
                    return navigator.serviceWorker.ready;
                })
                .then((registration) => {
                    publishOfflineUser(registration);
                })
                .catch((error) => {
                    console.warn('[PWA] Service Worker registration failed:', error);
                });
        });
    }

    // 2. Connectivity & Server Status Banner
    function createOfflineBanner() {
        let banner = document.getElementById('pwa-offline-top-banner');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'pwa-offline-top-banner';
            banner.style.cssText = 'display:none;min-width:0;flex:1;color:#ffffff;font-size:12px;font-weight:700;padding:0 8px;';
            banner.setAttribute('role', 'status');
            banner.textContent = '⚠️ Offline — brak połączenia z serwerem';
            banner.title = 'Sprawdź połączenie. Operacja jest przyjęta dopiero po potwierdzeniu przez serwer.';
            const bar = document.querySelector('.top-bar');
            if (bar) {
                bar.insertBefore(banner, bar.querySelector('.top-bar-right'));
            } else document.body.prepend(banner);
        }
        return banner;
    }

    let connectivityCheckRunning = false;
    let connectivityGeneration = 0;
    let failedConnectivityChecks = 0;
    let connectivityRetryTimer = null;
    let connectivityController = null;

    function showConnectivityStatus(offline, message) {
        const banner = createOfflineBanner();
        banner.textContent = message || '⚠️ Offline — brak połączenia z serwerem';
        banner.style.display = offline || message ? 'block' : 'none';
        const bar = document.querySelector('.top-bar');
        if (bar) bar.classList.toggle('connection-offline', offline);
    }

    function clearConnectivityRetry() {
        if (connectivityRetryTimer !== null) {
            clearTimeout(connectivityRetryTimer);
            connectivityRetryTimer = null;
        }
    }

    function updateConnectivityStatus() {
        if (window.__rpNavigating) return Promise.resolve();
        if (navigator.onLine === false) {
            connectivityGeneration++;
            connectivityCheckRunning = false;
            failedConnectivityChecks = 0;
            clearConnectivityRetry();
            if (connectivityController) connectivityController.abort();
            showConnectivityStatus(true);
            return Promise.resolve();
        }
        if (connectivityCheckRunning) return Promise.resolve();
        clearConnectivityRetry();
        connectivityCheckRunning = true;
        const generation = ++connectivityGeneration;
        const controller = typeof AbortController === 'function' ? new AbortController() : null;
        connectivityController = controller;
        let timeout;
        const deadline = new Promise((resolve, reject) => {
            timeout = setTimeout(() => {
                if (controller) controller.abort();
                reject(new Error('Connectivity check timed out'));
            }, 8000);
        });
        const request = Promise.resolve().then(() => fetch('/api/ping', {
            // Anonymous liveness avoids session/role DB checks and ignores Set-Cookie.
            method: 'GET', cache: 'no-store', credentials: 'omit',
            silent: true,
            headers: { 'Accept': 'application/json' },
            ...(controller ? {signal: controller.signal} : {})
        }));
        return Promise.race([request, deadline])
            .then(res => {
                if (generation !== connectivityGeneration) return;
                failedConnectivityChecks = 0;
                if (res.ok) {
                    showConnectivityStatus(false);
                } else if (res.status === 401 || res.status === 403) {
                    showConnectivityStatus(false, 'Serwer odpowiada — sprawdź sesję i uprawnienia.');
                } else {
                    showConnectivityStatus(false, `Serwer odpowiada, ale test działania zgłasza błąd (HTTP ${res.status}).`);
                }
            })
            .catch(() => {
                if (window.__rpNavigating || generation !== connectivityGeneration) return;
                failedConnectivityChecks++;
                if (failedConnectivityChecks >= 2) {
                    showConnectivityStatus(true);
                } else {
                    showConnectivityStatus(false, 'Chwilowy problem z połączeniem — sprawdzam ponownie…');
                    connectivityRetryTimer = setTimeout(() => {
                        connectivityRetryTimer = null;
                        updateConnectivityStatus();
                    }, 2000);
                }
            })
            .finally(() => {
                clearTimeout(timeout);
                if (generation === connectivityGeneration) {
                    connectivityCheckRunning = false;
                    connectivityController = null;
                }
            });
    }

    window.addEventListener('online', updateConnectivityStatus);
    window.addEventListener('offline', updateConnectivityStatus);
    window.addEventListener('DOMContentLoaded', updateConnectivityStatus);

    // Check server connectivity, independently of database readiness, every 25 seconds
    setInterval(() => {
        if (!document.hidden) updateConnectivityStatus();
    }, 25000);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) updateConnectivityStatus();
    });
})();
