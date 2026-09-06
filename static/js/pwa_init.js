/**
 * PWA & Service Worker Initializer
 * Registers root service worker and displays offline banner when connectivity drops.
 */

(function () {
    'use strict';

    // Store last visited page for offline resume
    try {
        if (!window.location.pathname.includes('offline_fallback')) {
            localStorage.setItem('rp_last_visited_page', window.location.pathname + window.location.search);
        }
    } catch(e) {}

    // 1. Register Service Worker
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js', { scope: '/' })
                .then((registration) => {
                    console.log('[PWA] Service Worker registered with scope:', registration.scope);
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
            banner.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;background:#dc2626;color:#ffffff;text-align:center;padding:8px 16px;font-size:13px;font-weight:700;z-index:999999;box-shadow:0 2px 10px rgba(0,0,0,0.3);';
            banner.innerHTML = '⚠️ Brak połączenia z serwerem. Aplikacja działa w trybie offline — operacje są bezpiecznie buforowane lokalnie.';
            document.body.prepend(banner);
        }
        return banner;
    }

    function updateConnectivityStatus() {
        const banner = createOfflineBanner();
        if (!navigator.onLine) {
            banner.style.display = 'block';
        } else {
            // Check if server is actually responding via heartbeat
            fetch('/api/health', { method: 'GET', cache: 'no-store' })
                .then((res) => {
                    if (res.ok) {
                        banner.style.display = 'none';
                    } else {
                        banner.style.display = 'block';
                    }
                })
                .catch(() => {
                    banner.style.display = 'block';
                });
        }
    }

    window.addEventListener('online', updateConnectivityStatus);
    window.addEventListener('offline', updateConnectivityStatus);
    window.addEventListener('DOMContentLoaded', updateConnectivityStatus);

    // Periodically check server health every 25 seconds
    setInterval(updateConnectivityStatus, 25000);
})();
