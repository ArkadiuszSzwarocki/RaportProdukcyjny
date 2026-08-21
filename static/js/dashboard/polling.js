(function (global) {
    'use strict';

    var initialized = false;
    var state = {
        zwolnienieLastSeen: 0,
        dosypkiLastSeen: 0,
        zasypStartLastSeen: 0,
        zasypMieszanieStartLastSeen: 0,
        zasypDosypkaAddedLastSeen: 0,
        zwolnienieAckLastSeen: 0,
        lastRenderedZasypDosypkaAddedTs: 0,
    };

    function getConfigState() {
        if (!global.dashboardConfig || typeof global.dashboardConfig.getState !== 'function') {
            return null;
        }
        return global.dashboardConfig.getState();
    }

    function isZasypSectionActive() {
        var config = getConfigState();
        var sekcja = String((config && config.sekcja) || '').toLowerCase();
        return sekcja === 'zasyp';
    }

    function persistLocalStorage(key, value) {
        try {
            localStorage.setItem(key, String(value));
        } catch (error) {
        }
    }

    function fetchJson(url) {
        return fetch(url, {
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
            },
        }).then(function (response) {
            if (response.status === 401) {
                if (global.dashboardScheduler) global.dashboardScheduler.stop();
                return {};
            }
            if (!response || !response.ok) {
                return {};
            }
            return response.json().catch(function () {
                return {};
            });
        }).catch(function () {
            // Navigation/session churn can temporarily cancel requests; keep polling quiet.
            return {};
        });
    }

    function readNumber(key, fallback) {
        try {
            var value = Number(localStorage.getItem(key) || fallback || 0);
            return Number.isFinite(value) ? value : (fallback || 0);
        } catch (error) {
            return fallback || 0;
        }
    }

    function syncStateFromWindow() {
        var nowSec = Date.now() / 1000;
        var config = getConfigState();
        var prefix = (config && config.linia) ? config.linia.toLowerCase() : 'agro';

        state.zwolnienieLastSeen = readNumber(prefix + '_zwolnienie_last_seen', nowSec);
        state.dosypkiLastSeen = readNumber(prefix + '_dosypki_last_seen', nowSec);
        state.zasypStartLastSeen = readNumber(prefix + '_zasyp_start_last_seen', nowSec);
        state.zasypMieszanieStartLastSeen = readNumber(prefix + '_zasyp_mieszanie_start_last_seen', nowSec);
        state.zasypDosypkaAddedLastSeen = readNumber(prefix + '_zasyp_dosypka_added_last_seen', nowSec);
        state.zwolnienieAckLastSeen = readNumber(prefix + '_zwolnienie_ack_last_seen', nowSec);

        if (state.zasypDosypkaAddedLastSeen > (nowSec + 5)) {
            state.zasypDosypkaAddedLastSeen = nowSec;
            persistLocalStorage(prefix + '_zasyp_dosypka_added_last_seen', nowSec);
        }
    }

    function addTask(name, intervalMs, callback, runImmediately) {
        if (!global.dashboardScheduler) {
            return;
        }
        global.dashboardScheduler.addTask(name, intervalMs, function () {
            var config = getConfigState();
            var sekcja = String((config && config.sekcja) || '').toLowerCase();
            var isSupported = (sekcja === 'zasyp' || sekcja === 'workowanie' || sekcja === 'dashboard');

            if (!isSupported) {
                return;
            }
            return callback();
        }, {
            runImmediately: runImmediately,
        });
    }

    function initZasypOperatorPolling() {
        var config = getConfigState();
        if (!config || !config.isZasypOperator) {
            return;
        }
        var prefix = (config && config.linia) ? config.linia.toLowerCase() : 'agro';

        addTask('zwolnienie-poll', 4000, function () {
            return fetchJson('/api/zasyp/poll_zwolnienie?linia=' + config.linia + '&last_seen=' + state.zwolnienieLastSeen)
                .then(function (data) {
                    if (!data.new_zwolnienie) {
                        return;
                    }
                    state.zwolnienieLastSeen = Number(data.timestamp || 0) || state.zwolnienieLastSeen;
                    persistLocalStorage(prefix + '_zwolnienie_last_seen', state.zwolnienieLastSeen);
                    if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.showZwolnienieBanner === 'function') {
                        global.dashboardAgroBanners.showZwolnienieBanner(data.audio_url);
                    }
                })
                .catch(function (error) {
                    console.error('Zwolnienie poll err', error);
                });
        }, false);

        if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner === 'function') {
            global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner();
            addTask('dosypki-badge-sync', 5000, function () {
                global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner();
            }, false);
        }

        addTask('dosypki-emergency-poll', 4000, function () {
            return fetchJson('/api/zasyp/poll_dosypki_update?linia=' + config.linia + '&last_seen=' + state.dosypkiLastSeen)
                .then(function (data) {
                    if (!data.new_update) {
                        return;
                    }

                    state.dosypkiLastSeen = Number(data.timestamp || 0) || state.dosypkiLastSeen;
                    persistLocalStorage(prefix + '_dosypki_last_seen', state.dosypkiLastSeen);

                    if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner === 'function') {
                        global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner();
                    }

                    if (typeof global.reloadActiveDosypkiList === 'function') {
                        global.reloadActiveDosypkiList();
                    }

                    return fetchJson('/api/zasyp/poll_dosypka_added?linia=' + config.linia + '&last_seen=0')
                        .then(function (eventData) {
                            if (!eventData || !eventData.new_event) {
                                return;
                            }
                            state.zasypDosypkaAddedLastSeen = Number(eventData.timestamp || 0) || state.zasypDosypkaAddedLastSeen;
                            persistLocalStorage(prefix + '_zasyp_dosypka_added_last_seen', state.zasypDosypkaAddedLastSeen);
                            try {
                                if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.showZasypDosypkaAddedBanner === 'function') {
                                    global.dashboardAgroBanners.showZasypDosypkaAddedBanner(eventData);
                                }
                                state.lastRenderedZasypDosypkaAddedTs = Number(eventData.timestamp || 0) || state.lastRenderedZasypDosypkaAddedTs;
                            } catch (error) {
                                console.error('Emergency showZasypDosypkaAddedBanner err', error);
                            }
                        })
                        .catch(function (error) {
                            console.error('Emergency poll_dosypka_added err', error);
                        });
                })
                .catch(function (error) {
                    console.error('Emergency poll_dosypki_update err', error);
                });
        }, false);

        addTask('dosypka-hard-fallback-poll', 5000, function () {
            return fetchJson('/api/zasyp/poll_dosypka_added?linia=' + config.linia + '&last_seen=0')
                .then(function (eventData) {
                    if (!eventData || !eventData.new_event) {
                        return;
                    }

                    var eventTs = Number((eventData && eventData.timestamp) || 0) || 0;
                    if (eventTs && eventTs <= state.lastRenderedZasypDosypkaAddedTs) {
                        return;
                    }

                    state.zasypDosypkaAddedLastSeen = eventTs || state.zasypDosypkaAddedLastSeen;
                    persistLocalStorage(prefix + '_zasyp_dosypka_added_last_seen', state.zasypDosypkaAddedLastSeen);
                    try {
                        if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.showZasypDosypkaAddedBanner === 'function') {
                            global.dashboardAgroBanners.showZasypDosypkaAddedBanner(eventData);
                        }
                        state.lastRenderedZasypDosypkaAddedTs = eventTs || state.lastRenderedZasypDosypkaAddedTs;
                    } catch (error) {
                        console.error('Hard fallback showZasypDosypkaAddedBanner err', error);
                    }
                })
                .catch(function (error) {
                    console.error('Hard fallback poll_dosypka_added err', error);
                });
        }, false);
    }

    function initDosypkiObserverPolling() {
        var config = getConfigState();
        if (!config || !config.isDosypkiObserver || config.isZasypOperator) {
            return;
        }
        var prefix = (config && config.linia) ? config.linia.toLowerCase() : 'agro';

        if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner === 'function') {
            global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner();
            addTask('dosypki-badge-sync-observer', 5000, function () {
                global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner();
            }, false);
        }

        addTask('dosypki-observer-poll', 4000, function () {
            return fetchJson('/api/zasyp/poll_dosypki_update?linia=' + config.linia + '&last_seen=' + state.dosypkiLastSeen)
                .then(function (data) {
                    if (!data.new_update) {
                        return;
                    }

                    state.dosypkiLastSeen = Number(data.timestamp || 0) || state.dosypkiLastSeen;
                    persistLocalStorage(prefix + '_dosypki_last_seen', state.dosypkiLastSeen);

                    // Always sync badges immediately – regardless of banner lock state.
                    if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner === 'function') {
                        global.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner();
                    }

                    // If the laborant has the dosypka popup open, silently refresh only the popup
                    var container = document.querySelector('.dosypka-popup-container');
                    if (container && typeof global.refreshDosypkaPopup === 'function') {
                        var planId = container.getAttribute('data-plan-id');
                        var szarzaId = container.getAttribute('data-szarza-id');
                        global.refreshDosypkaPopup(planId, szarzaId).catch(function (e) {
                            console.error('refreshDosypkaPopup err', e);
                        });
                        return;
                    }

                    // Skip partial reload if a banner is currently locked
                    if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.isBannerLocked === 'function' && global.dashboardAgroBanners.isBannerLocked()) {
                        return;
                    }

                    if (typeof global.reloadActiveDosypkiList === 'function') {
                        global.reloadActiveDosypkiList();
                    }
                    if (typeof global.performPartialReload === 'function') {
                        global.performPartialReload({ force: false, preserveScroll: true, source: 'dosypki-sync' });
                    }
                })
                .catch(function (error) {
                    console.error('Dosypki poll err', error);
                });
        }, false);
    }

    function initLaborantPolling() {
        var config = getConfigState();
        if (!config || !config.isLaborant) {
            return;
        }
        var prefix = (config && config.linia) ? config.linia.toLowerCase() : 'agro';

        addTask('zasyp-start-poll', 4000, function () {
            return fetchJson('/api/zasyp/poll_etap_start?linia=' + config.linia + '&last_seen=' + state.zasypStartLastSeen)
                .then(function (data) {
                    if (!data.new_start) {
                        return;
                    }
                    state.zasypStartLastSeen = Number(data.timestamp || 0) || state.zasypStartLastSeen;
                    persistLocalStorage(prefix + '_zasyp_start_last_seen', state.zasypStartLastSeen);
                    try {
                        if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.showZasypStartBanner === 'function') {
                            global.dashboardAgroBanners.showZasypStartBanner(data);
                        }
                    } catch (error) {
                        console.error('showZasypStartBanner err', error);
                    }
                })
                .catch(function (error) {
                    console.error('Zasyp start poll err', error);
                });
        }, false);

        addTask('mieszanie-start-poll', 4000, function () {
            return fetchJson('/api/zasyp/poll_mieszanie_start?linia=' + config.linia + '&last_seen=' + state.zasypMieszanieStartLastSeen)
                .then(function (data) {
                    if (!data.new_start) {
                        return;
                    }
                    state.zasypMieszanieStartLastSeen = Number(data.timestamp || 0) || state.zasypMieszanieStartLastSeen;
                    persistLocalStorage(prefix + '_zasyp_mieszanie_start_last_seen', state.zasypMieszanieStartLastSeen);
                    try {
                        if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.showZasypMieszanieStartBanner === 'function') {
                            global.dashboardAgroBanners.showZasypMieszanieStartBanner(data);
                        }
                    } catch (error) {
                        console.error('showZasypMieszanieStartBanner err', error);
                    }
                })
                .catch(function (error) {
                    console.error('Zasyp mieszanie start poll err', error);
                });
        }, false);

        addTask('zwolnienie-ack-poll', 4000, function () {
            return fetchJson('/api/zasyp/poll_zwolnienie_ack?linia=' + config.linia + '&last_seen=' + state.zwolnienieAckLastSeen)
                .then(function (data) {
                    if (!data.new_ack) {
                        return;
                    }
                    state.zwolnienieAckLastSeen = Number(data.timestamp || 0) || state.zwolnienieAckLastSeen;
                    persistLocalStorage(prefix + '_zwolnienie_ack_last_seen', state.zwolnienieAckLastSeen);
                    try {
                        if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.showZwolnienieAckBanner === 'function') {
                            global.dashboardAgroBanners.showZwolnienieAckBanner(data);
                        }
                    } catch (error) {
                        console.error('showZwolnienieAckBanner err', error);
                    }
                })
                .catch(function (error) {
                    console.error('Zwolnienie ack poll err', error);
                });
        }, false);

        // Odświeżanie etapów u laboranta gdy operator doda nową dosypkę
        addTask('laborant-dosypki-update-poll', 5000, function () {
            return fetchJson('/api/zasyp/poll_dosypki_update?linia=' + config.linia + '&last_seen=' + state.dosypkiLastSeen)
                .then(function (data) {
                    if (!data.new_update) {
                        return;
                    }

                    state.dosypkiLastSeen = Number(data.timestamp || 0) || state.dosypkiLastSeen;
                    persistLocalStorage(prefix + '_dosypki_last_seen', state.dosypkiLastSeen);

                    // Jeśli laborant ma otwarty popup dosypki — odśwież tylko popup, nie przeładowuj strony
                    var container = document.querySelector('.dosypka-popup-container');
                    if (container && typeof global.refreshDosypkaPopup === 'function') {
                        var planId = container.getAttribute('data-plan-id');
                        var szarzaId = container.getAttribute('data-szarza-id');
                        global.refreshDosypkaPopup(planId, szarzaId).catch(function (e) {
                            console.error('laborant refreshDosypkaPopup err', e);
                        });
                        return;
                    }

                    // Wykonaj ciche częściowe przeładowanie bez resetowania scrolla i bez wymuszania gdy user pisze
                    if (typeof global.performPartialReload === 'function') {
                        global.performPartialReload({ force: false, preserveScroll: true, source: 'laborant-dosypki-sync' });
                    }
                })
                .catch(function (error) {
                    console.error('Laborant dosypki update poll err', error);
                });
        }, false);
    }

    var sessionLastPallet = 0;

    function initSystemStatePolling() {
        // Handled globally in layout scripts
    }

    function init() {
        if (initialized) return;
        initialized = true;

        var config = getConfigState();
        var sekcja = String((config && config.sekcja) || '').toLowerCase();
        var isSupportedSection = (sekcja === 'zasyp' || sekcja === 'workowanie' || sekcja === 'dashboard');

        if (!isSupportedSection) return;

        syncStateFromWindow();

        if (sekcja === 'zasyp') {
            initZasypOperatorPolling();
            initDosypkiObserverPolling();
            initLaborantPolling();
        }
        
        initSystemStatePolling();
    }

    global.dashboardPolling = {
        init: init,
    };
})(window);