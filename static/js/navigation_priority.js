/* Native menu navigation takes priority over optional background GET reads. */
(function () {
    'use strict';
    if (window.__rpNavigationPriority) return;
    window.__rpNavigationPriority = true;
    window.__rpNavigating = false;
    const pending = new Set();
    const backgroundPaths = new Set([
        '/api/system_state', '/api/notifications', '/api/health', '/api/ping',
        '/warehouse-v2/api/sidebar-badges', '/warehouse-v2/api/live/snapshot',
        '/warehouse-v2/api/orders/picking/active', '/warehouse-v2/api/orders/picking/all',
        '/auth/temporary-masteradmin/status', '/api/agro/pomiary',
        '/api/zasyp/pending_dosypki_badges', '/api/zasyp/poll_zwolnienie',
        '/api/zasyp/poll_dosypki_update', '/api/zasyp/poll_dosypka_added',
        '/api/zasyp/poll_etap_start', '/api/zasyp/poll_mieszanie_start',
        '/api/zasyp/poll_zwolnienie_ack'
    ]);
    const originalFetch = window.fetch;
    window.fetch = function (input, init) {
        const options = init || {};
        let url;
        try { url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.href); }
        catch (_) { return originalFetch.apply(this, arguments); }
        const method = String(options.method || (input && input.method) || 'GET').toUpperCase();
        const background = method === 'GET' && options.silent === true &&
            url.origin === location.origin &&
            (backgroundPaths.has(url.pathname) || url.href === location.href);
        if (!background) return originalFetch.apply(this, arguments);
        if (window.__rpNavigating) return Promise.reject(new DOMException('Navigation in progress', 'AbortError'));
        const controller = new AbortController();
        const signal = options.signal || (input && input.signal);
        const abort = () => controller.abort(signal && signal.reason);
        if (signal) {
            if (signal.aborted) abort();
            else signal.addEventListener('abort', abort, {once: true});
        }
        pending.add(controller);
        return Promise.resolve().then(() => originalFetch.call(this, input, {...options, signal: controller.signal}))
            .finally(() => {
                pending.delete(controller);
                if (signal) signal.removeEventListener('abort', abort);
            });
    };
    let resumeTimer;
    function resume() {
        clearTimeout(resumeTimer);
        if (!window.__rpNavigating) return;
        window.__rpNavigating = false;
        window.dispatchEvent(new Event('rp:navigation-cancelled'));
    }
    document.addEventListener('click', event => {
        if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const link = event.target.closest && event.target.closest('.sidebar a[href]');
        if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
        const rawHref = link.getAttribute('href') || '';
        if (!rawHref || rawHref.startsWith('#')) return;
        const url = new URL(link.href, location.href);
        if (url.origin !== location.origin || !['http:', 'https:'].includes(url.protocol) ||
            (url.pathname === location.pathname && url.search === location.search && url.hash)) return;
        window.__rpNavigating = true;
        for (const controller of pending) controller.abort('navigation');
        window.dispatchEvent(new Event('rp:navigation-start'));
        clearTimeout(resumeTimer);
        // Resume if an unsaved-form confirmation was cancelled or navigation
        // did not complete. Never cancel the native link action or any writes.
        resumeTimer = setTimeout(resume, 10000);
    }, true);
    window.addEventListener('pageshow', resume);
}());
