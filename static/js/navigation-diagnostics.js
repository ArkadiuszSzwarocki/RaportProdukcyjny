/* Keep only bounded diagnostic categories in this tab; never persist form values or tokens. */
(function () {
    'use strict';
    const config = document.getElementById('navigationDiagnostics');
    if (!config) return;
    const key = 'rp-navigation-diagnostic';
    const owner = config.dataset.owner;
    const started = Date.now();
    let intent = null;
    function view(raw) {
        try {
            const url = new URL(raw, window.location.origin);
            if (url.origin !== window.location.origin) return 'unknown';
            if (url.pathname.includes('/scanner')) return 'scanner';
            if (url.pathname === '/') {
                const section = (url.searchParams.get('sekcja') || 'dashboard').toLowerCase();
                return ['dashboard', 'zasyp', 'workowanie'].includes(section) ? section : 'other';
            }
            if (url.pathname.startsWith('/warehouse-v2')) return 'warehouse';
            if (url.pathname.startsWith('/login')) return 'login';
            return 'other';
        } catch (_) { return 'unknown'; }
    }
    function remember(reason, details) {
        const value = {owner: owner, previous_view: view(window.location.href), reason: reason,
            page_age_ms: Date.now() - started, departed_at: Date.now()};
        for (const name of ['previous_active', 'observed_active', 'observed_eligible']) {
            if (details && typeof details[name] === 'boolean') value[name] = details[name];
        }
        intent = value;
        try { sessionStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* Storage is optional. */ }
    }
    window.recordDashboardNavigation = remember;
    let previous = null;
    try { previous = JSON.parse(sessionStorage.getItem(key) || 'null'); sessionStorage.removeItem(key); } catch (_) { /* Best effort. */ }
    if (view(window.location.href) === 'dashboard') {
        if (!previous || previous.owner !== owner || Date.now() - previous.departed_at > 120000 || Date.now() < previous.departed_at) previous = {};
        const navigation = performance.getEntriesByType('navigation')[0];
        const payload = Object.assign({}, previous, {csrf: config.dataset.csrf, event_id: config.dataset.eventId,
            previous_view: previous.previous_view || (document.referrer ? view(document.referrer) : 'unknown'),
            reason: previous.reason || 'unattributed', navigation_type: navigation ? navigation.type : 'unknown',
            departure_age_ms: previous.departed_at ? Date.now() - previous.departed_at : null});
        delete payload.owner;
        delete payload.departed_at;
        try {
            const body = JSON.stringify(payload);
            if (!navigator.sendBeacon || !navigator.sendBeacon(config.dataset.url, new Blob([body], {type: 'application/json'}))) {
                fetch(config.dataset.url, {method: 'POST', credentials: 'same-origin', keepalive: true,
                    headers: {'Content-Type': 'application/json'}, body: body}).catch(function () {});
            }
        } catch (_) { /* Diagnostics must never block work. */ }
    }
    document.addEventListener('click', function (event) {
        const link = event.target.closest ? event.target.closest('a[href]') : null;
        if (link && !event.defaultPrevented && view(link.href) === 'dashboard') remember('dashboard_link');
    });
    window.addEventListener('pagehide', function () { if (!intent) remember('unattributed'); });
    window.addEventListener('pageshow', function (event) { if (event.persisted) intent = null; });
}());
