(function (global) {
    'use strict';
    if (global.rpPerfMonitor) return;
    const CLICK_KEY = 'rp_perf_pending_v2';
    const LOG_KEY = 'rp_perf_log';
    function readLog() {
        try {
            const data = JSON.parse(localStorage.getItem(LOG_KEY) || '[]');
            return Array.isArray(data) ? data : [];
        } catch (_) { return []; }
    }
    function save(entry) {
        try {
            localStorage.setItem(LOG_KEY, JSON.stringify([entry, ...readLog()].slice(0, 50)));
            global.dispatchEvent(new Event('rp:perf-log'));
        } catch (_) { /* Private browsing / full storage must not block navigation. */ }
    }
    let previous = null;
    try {
        previous = JSON.parse(sessionStorage.getItem(CLICK_KEY) || 'null');
        sessionStorage.removeItem(CLICK_KEY);
        // Ignore the former shared cross-tab timestamp.
        localStorage.removeItem('rp_perf_click_timestamp');
    } catch (_) { previous = null; }
    const destination = global.location.pathname + global.location.search;
    // A prevented click must not become a measurement of a later unrelated page.
    if (!previous || previous.target !== destination ||
        !Number.isFinite(previous.time) || Date.now() - previous.time > 120000 ||
        Date.now() < previous.time) previous = null;
    let readyDuration = null;
    function contentReady() {
        if (previous) readyDuration = Math.max(0, Date.now() - previous.time);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', contentReady, {once: true});
    else contentReady();
    function record() {
        if (!previous) return;
        const pending = previous;
        previous = null;
        const nav = global.performance && performance.getEntriesByType('navigation')[0];
        const server = nav && (nav.serverTiming || []).find(item => item.name === 'app');
        const resources = global.performance ? performance.getEntriesByType('resource')
            .filter(item => ['script', 'link', 'css'].includes(item.initiatorType))
            .sort((a, b) => b.duration - a.duration).slice(0, 5)
            .map(item => {
                const url = new URL(item.name, location.href);
                return {url: (url.origin === location.origin ? '' : url.origin) + url.pathname,
                    duration: Math.round(item.duration), type: item.initiatorType};
            }) : [];
        save({
            timestamp: Date.now(), url: destination, from: pending.from,
            total_duration: nav && nav.domContentLoadedEventEnd > 0 ? Math.round(Math.max(0, performance.timeOrigin + nav.domContentLoadedEventEnd - pending.time)) : (readyDuration === null ? Math.max(0, Date.now() - pending.time) : readyDuration),
            full_load: Math.round(nav && nav.loadEventEnd > 0 ? performance.timeOrigin + nav.loadEventEnd - pending.time : Date.now() - pending.time),
            backend: nav ? Math.round(Math.max(0, nav.responseStart - nav.requestStart)) : null,
            frontend: nav ? Math.round(Math.max(0, nav.domContentLoadedEventEnd - nav.responseStart)) : null,
            transfer: nav ? Math.round(Math.max(0, nav.responseEnd - nav.responseStart)) : null,
            server: server ? Math.round(server.duration) : null, resources: resources,
            background: !!pending.background || document.hidden,
            type: 'click_to_load', version: 2
        });
    }
    // Defer only the read of NavigationTiming; elapsed time comes from recorded milestones.
    global.addEventListener('load', () => setTimeout(record, 0), {once: true});
    document.addEventListener('click', function (event) {
        if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const link = event.target.closest && event.target.closest('a[href]');
        if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
        const raw = link.getAttribute('href');
        if (!raw || raw.startsWith('#')) return;
        let url;
        try { url = new URL(link.href, location.href); } catch (_) { return; }
        if (url.origin !== location.origin || !['http:', 'https:'].includes(url.protocol) ||
            (url.pathname === location.pathname && url.search === location.search && url.hash)) return;
        try {
            sessionStorage.setItem(CLICK_KEY, JSON.stringify({time: Date.now(), target: url.pathname + url.search,
                from: destination, background: document.hidden}));
        } catch (_) { /* Optional measurement only. */ }
    });
    global.rpPerfMonitor = {getLog: readLog, clearLog: function () {
        try { localStorage.removeItem(LOG_KEY); } catch (_) {}
        global.dispatchEvent(new Event('rp:perf-log'));
    }};
})(window);
