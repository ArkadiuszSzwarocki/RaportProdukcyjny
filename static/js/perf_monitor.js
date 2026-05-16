(function(global) {
    'use strict';

    const STORAGE_KEY_CLICK = 'rp_perf_click_timestamp';
    const STORAGE_KEY_LOG = 'rp_perf_log';
    const MAX_LOG_SIZE = 50;

    function init() {
        // 1. Measure previous navigation if exists
        const clickTime = localStorage.getItem(STORAGE_KEY_CLICK);
        if (clickTime) {
            localStorage.removeItem(STORAGE_KEY_CLICK);
            
            // Wait for the window to be fully loaded to get accurate performance metrics
            window.addEventListener('load', function() {
                setTimeout(function() {
                    const now = Date.now();
                    let duration = now - parseInt(clickTime, 10);
                    
                    // Sanity check: if duration is > 2 minutes, it's likely a stale click or hibernated tab
                    if (duration > 120000) duration = 0; 

                    let backendTime = 0;
                    let frontendTime = 0;
                    if (global.performance && global.performance.getEntriesByType) {
                        const nav = global.performance.getEntriesByType('navigation')[0];
                        if (nav && nav.loadEventEnd > 0) {
                            backendTime = Math.round(nav.responseStart - nav.requestStart);
                            frontendTime = Math.round(nav.loadEventEnd - nav.responseStart);
                        } else if (nav) {
                            // Fallback if loadEventEnd is still 0
                            backendTime = Math.round(nav.responseStart - nav.requestStart);
                            frontendTime = Math.round(performance.now() - nav.responseStart);
                        }
                    }

                    if (duration > 0 || backendTime > 0) {
                        saveToLog({
                            timestamp: now,
                            url: global.location.pathname + global.location.search,
                            total_duration: duration,
                            backend: Math.max(0, backendTime),
                            frontend: Math.max(0, frontendTime),
                            type: 'click_to_load'
                        });
                    }
                }, 100);
            });
        }

        // 2. Intercept clicks to track next navigation and sidebar actions
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a');
            const btn = e.target.closest('button');
            const navItem = e.target.closest('.nav-item, .nav-sub-item');

            if (navItem) {
                // Log navigation item click
                saveToLog({
                    timestamp: Date.now(),
                    url: global.location.pathname,
                    action: 'MENU_CLICK',
                    detail: navItem.textContent.trim().substring(0, 30),
                    type: 'interaction'
                });
            }

            if (!link) return;

            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript:') || link.getAttribute('target') === '_blank') {
                return;
            }

            // Only track internal links
            if (href.indexOf('http') === 0 && !href.includes(global.location.host)) {
                return;
            }

            localStorage.setItem(STORAGE_KEY_CLICK, Date.now().toString());
        }, true);
    }

    function saveToLog(entry) {
        let log = [];
        try {
            log = JSON.parse(localStorage.getItem(STORAGE_KEY_LOG) || '[]');
        } catch (e) {
            log = [];
        }

        // Avoid too many interaction logs if they are identical
        if (entry.type === 'interaction' && log.length > 0 && log[0].detail === entry.detail && (entry.timestamp - log[0].timestamp < 1000)) {
            return;
        }

        log.unshift(entry);
        if (log.length > MAX_LOG_SIZE) {
            log = log.slice(0, MAX_LOG_SIZE);
        }

        localStorage.setItem(STORAGE_KEY_LOG, JSON.stringify(log));
    }

    // Initialize as soon as possible
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    global.rpPerfMonitor = {
        getLog: function() {
            try {
                return JSON.parse(localStorage.getItem(STORAGE_KEY_LOG) || '[]');
            } catch (e) { return []; }
        },
        clearLog: function() {
            localStorage.removeItem(STORAGE_KEY_LOG);
        }
    };
})(window);
