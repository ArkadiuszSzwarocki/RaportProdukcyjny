/**
 * Watchdog Error Tracker
 * Captures JavaScript errors, unhandled promise rejections, and true UI freezes.
 * Dispatches via same-origin endpoint to prevent Mixed Content (HTTPS) & CORS blocks.
 */
(function() {
    'use strict';

    // Prefer same-origin proxy to eliminate HTTPS mixed content and CORS issues
    const PROXY_ENDPOINT = '/api/watchdog/log';
    const DIRECT_ENDPOINT = 'http://192.168.0.57:3005/api/log';

    const recentErrors = new Set();
    let lastFreezeReport = 0;
    const ERROR_DEBOUNCE_MS = 5000;
    const FREEZE_DEBOUNCE_MS = 15000;

    function sendToWatchdog(type, details, file, line) {
        try {
            const errorKey = `${type}_${file || ''}_${line || ''}_${String(details || '').slice(0, 50)}`;
            if (recentErrors.has(errorKey)) {
                return;
            }
            recentErrors.add(errorKey);
            setTimeout(() => recentErrors.delete(errorKey), ERROR_DEBOUNCE_MS);

            const payload = {
                app_name: 'RaportProdukcyjny',
                error_type: type || 'JS Error',
                details: details ? String(details) : 'Brak szczegółów',
                file_path: file ? String(file) : '',
                line_num: line !== undefined && line !== null ? String(line) : ''
            };

            const jsonPayload = JSON.stringify(payload);

            // 1. Try same-origin proxy (works seamlessly under HTTPS and HTTP)
            fetch(PROXY_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: jsonPayload,
                keepalive: true
            }).catch(() => {
                // 2. Direct fallback only if we are on plain HTTP (browser blocks mixed content on HTTPS)
                if (window.location.protocol === 'http:') {
                    fetch(DIRECT_ENDPOINT, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: jsonPayload,
                        keepalive: true
                    }).catch(() => {});
                }
            });
        } catch (_) {}
    }

    // 1. Classic JavaScript errors
    window.addEventListener('error', function(event) {
        if (!event) return;
        const message = event.message || 'Unknown script error';
        const filename = event.filename || '';
        const lineno = event.lineno || '';
        sendToWatchdog('JS Error', message, filename, lineno);
    });

    // 2. Unhandled promise rejections (network failures, async API errors)
    window.addEventListener('unhandledrejection', function(event) {
        if (!event) return;
        const reason = event.reason;
        let details = 'Unknown promise rejection';
        if (reason) {
            details = reason.stack || reason.message || String(reason);
        }
        sendToWatchdog('Unhandled Promise', details, window.location.pathname, '');
    });

    // 3. Intelligent UI Freeze / Main-thread lag detection
    document.addEventListener('click', function(event) {
        const target = event.target;
        if (!target) return;

        // Skip navigation links and form submissions that naturally unload/reload the document
        const link = target.closest('a');
        if (link && link.getAttribute('href') && !link.getAttribute('href').startsWith('#') && !link.getAttribute('href').startsWith('javascript:')) {
            return;
        }
        if (target.closest('button[type="submit"]') || target.closest('form')) {
            return;
        }

        const clickTime = performance.now();
        let targetDescriptor = target.tagName || 'ELEMENT';
        if (target.id) targetDescriptor += '#' + target.id;
        if (target.className && typeof target.className === 'string') {
            targetDescriptor += '.' + target.className.trim().split(/\s+/).slice(0, 3).join('.');
        }

        setTimeout(() => {
            const now = performance.now();
            const delay = now - clickTime - 500;
            // Only report significant lags (> 250ms) and debounce reports to once every 15s
            if (delay > 250 && (now - lastFreezeReport > FREEZE_DEBOUNCE_MS)) {
                lastFreezeReport = now;
                sendToWatchdog(
                    'UI Freeze (Zwiecha)',
                    `Główny wątek zablokowany na ${Math.round(delay)}ms po kliknięciu w ${targetDescriptor}`,
                    window.location.pathname,
                    ''
                );
            }
        }, 500);
    }, { capture: true, passive: true });

    // Expose utility globally for manual logging if needed
    window.reportWatchdogError = sendToWatchdog;
})();
