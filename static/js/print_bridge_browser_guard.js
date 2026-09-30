/* Security guard: raw ZPL must only leave the application through the
 * authenticated server-side print client. Browser code must never post
 * directly to a printer bridge, because that would either require exposing
 * the bridge credential to JavaScript or relying on an unauthenticated bridge.
 */
(function () {
    'use strict';

    if (typeof window.fetch !== 'function') return;
    if (window.__printBridgeBrowserGuardInstalled) return;

    const guardedFetchBase = window.fetch.bind(window);

    function isDirectPrinterBridgeRequest(input) {
        let rawUrl = '';
        try {
            rawUrl = (input && typeof input === 'object' && input.url)
                ? String(input.url)
                : String(input || '');
            const target = new URL(rawUrl, window.location.href);
            if (target.origin === window.location.origin) return false;

            const path = String(target.pathname || '').replace(/\/+$/, '').toLowerCase();
            return path === '/drukuj-zpl' || path.endsWith('/drukuj-zpl');
        } catch (e) {
            return false;
        }
    }

    window.fetch = function guardedPrinterBridgeFetch(input, init) {
        if (isDirectPrinterBridgeRequest(input)) {
            return Promise.reject(new TypeError(
                'Bezpośredni dostęp przeglądarki do mostka drukarek jest wyłączony. Użyj serwerowego API druku.'
            ));
        }
        return guardedFetchBase(input, init);
    };

    Object.defineProperty(window, '__printBridgeBrowserGuardInstalled', {
        configurable: false,
        enumerable: false,
        writable: false,
        value: true
    });
})();
