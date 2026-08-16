(function (global) {
    'use strict';

    var initialized = false;
    var partialReloadBound = false;

    function ready(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
            return;
        }
        callback();
    }

    function getSekcja() {
        var sekcjaNode = document.querySelector('[data-sekcja]');
        return sekcjaNode ? String(sekcjaNode.getAttribute('data-sekcja') || '') : '';
    }

    function initSzarzaTooltips() {
        if (typeof global.tippy === 'undefined') {
            return;
        }

        document.querySelectorAll('.szarza-note').forEach(function (element) {
            if (element._tippy) {
                return;
            }

            global.tippy(element, {
                content: function (instance) {
                    return instance.getAttribute('data-note') || 'Brak notatki';
                },
                allowHTML: false,
                maxWidth: 260,
                placement: 'top',
                delay: [150, 50],
                theme: 'light-border',
            });
        });
    }

    function refreshZasypEnhancements() {
        if (getSekcja() !== 'Zasyp') {
            return;
        }

        try {
            if (global.dashboardEtapy && typeof global.dashboardEtapy.startEtapyTimers === 'function') {
                global.dashboardEtapy.startEtapyTimers();
            }
            if (global.dashboardEtapy && typeof global.dashboardEtapy.applyNowMaxToTimeInputs === 'function') {
                global.dashboardEtapy.applyNowMaxToTimeInputs(document);
            }
        } catch (error) {
            if (global.__RP_DEBUG__) {
                console.debug('zasyp timers init failed', error);
            }
        }

        try {
            initSzarzaTooltips();
        } catch (error) {
            if (global.__RP_DEBUG__) {
                console.debug('tippy init failed', error);
            }
        }
    }

    function refresh() {
        if (global.dashboardConfig && typeof global.dashboardConfig.init === 'function') {
            global.dashboardConfig.init();
        }
        if (global.dashboardCardActions && typeof global.dashboardCardActions.init === 'function') {
            global.dashboardCardActions.init();
        }
        if (global.dashboardPolling && typeof global.dashboardPolling.init === 'function') {
            global.dashboardPolling.init();
        }
        if (global.dashboardPageHelpers && typeof global.dashboardPageHelpers.initUpdatePaletaTimers === 'function') {
            global.dashboardPageHelpers.initUpdatePaletaTimers();
        }

        refreshZasypEnhancements();
    }

    function bindPartialReload() {
        if (partialReloadBound) {
            return;
        }
        partialReloadBound = true;

        global.addEventListener('app:partialReload', function () {
            if (global.dashboardPageHelpers && typeof global.dashboardPageHelpers.initUpdatePaletaTimers === 'function') {
                global.dashboardPageHelpers.initUpdatePaletaTimers();
            }
            refreshZasypEnhancements();
        });
    }

    function init() {
        if (initialized) {
            return;
        }
        initialized = true;

        refresh();
        bindPartialReload();
    }

    ready(init);

    global.dashboardBootstrap = {
        init: init,
        refresh: refresh,
    };
})(window);