(function (global) {
    'use strict';

    if (global.dashboardAgroBanners) {
        return;
    }

    var initialized = false;
    var state = {
        zwolnienieLastSeen: 0,
        dosypkiLastSeen: 0,
        zasypStartLastSeen: 0,
        zasypMieszanieStartLastSeen: 0,
        zasypDosypkaAddedLastSeen: 0,
        zwolnienieAckLastSeen: 0,
        zasypDosypkaDismissedTs: 0,
        agroBannerLockUntil: 0,
        lastRenderedZasypStartTs: 0,
        lastRenderedZasypMieszanieStartTs: 0,
        lastRenderedZasypDosypkaAddedTs: 0,
        lastRenderedZasypStartKey: '',
        lastRenderedZasypMieszanieStartKey: '',
        lastRenderedZasypDosypkaAddedKey: '',
        activeAudioInstances: [],
        activeSpeechFallback: {
            key: '',
            active: false,
        },
    };

    function ready(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
            return;
        }
        callback();
    }

    function getSekcja() {
        var configNode = document.getElementById('dashboard-config');
        var configSekcja = configNode ? String(configNode.getAttribute('data-sekcja') || '') : '';
        if (configSekcja) {
            return configSekcja;
        }

        try {
            var params = new URLSearchParams(global.location.search);
            if (params.has('sekcja')) {
                return String(params.get('sekcja') || '');
            }
        } catch (error) {
        }

        var sekcjaNode = document.querySelector('[data-sekcja]');
        return sekcjaNode ? String(sekcjaNode.getAttribute('data-sekcja') || '') : '';
    }

    function getConfigState() {
        if (!global.dashboardConfig || typeof global.dashboardConfig.getState !== 'function') {
            return null;
        }
        return global.dashboardConfig.getState();
    }

    function isAgroZasypPage() {
        var config = getConfigState();
        var sekcja = String(getSekcja() || '').toLowerCase();
        var linia = String(config && config.linia || '').toUpperCase();
        return ['AGRO', 'PSD'].includes(linia) && sekcja === 'zasyp';
    }

    function getCurrentDateIso() {
        var dateInput = document.getElementById('current-date-iso');
        if (dateInput && dateInput.value) {
            return String(dateInput.value);
        }

        try {
            var params = new URLSearchParams(global.location.search);
            if (params.has('data')) {
                return String(params.get('data') || '');
            }
        } catch (error) {
        }

        return new Date().toISOString().slice(0, 10);
    }

    function persist(key, value) {
        try {
            localStorage.setItem(key, String(value));
        } catch (error) {
        }
    }

    function loadSoundScript() {
        try {
            if (document.getElementById('zwolnienie-sound-script')) {
                return;
            }
            var script = document.createElement('script');
            script.id = 'zwolnienie-sound-script';
            script.src = '/static/js/zwolnienie_sound.js';
            script.defer = true;
            document.head.appendChild(script);
        } catch (error) {
            console.warn('Failed to load zwolnienie sound script', error);
        }
    }

    function hydrateState() {
        try {
            state.zwolnienieLastSeen = Number(localStorage.getItem('agro_zwolnienie_last_seen') || '0') || 0;
            state.zasypStartLastSeen = Number(localStorage.getItem('agro_zasyp_start_last_seen') || '0') || 0;
            state.zasypMieszanieStartLastSeen = Number(localStorage.getItem('agro_zasyp_mieszanie_start_last_seen') || '0') || 0;
            state.dosypkiLastSeen = Number(localStorage.getItem('agro_dosypki_last_seen') || '0') || 0;
            state.zasypDosypkaAddedLastSeen = Number(localStorage.getItem('agro_zasyp_dosypka_added_last_seen') || '0') || 0;
            state.zwolnienieAckLastSeen = Number(localStorage.getItem('agro_zwolnienie_ack_last_seen') || '0') || 0;
            state.zasypDosypkaDismissedTs = Number(localStorage.getItem('agro_zasyp_dosypka_dismissed_ts') || '0') || 0;

            var dosypkaSchemaKey = 'agro_zasyp_dosypka_added_last_seen_schema';
            var dosypkaSchemaVersion = 'v2';
            if (String(localStorage.getItem(dosypkaSchemaKey) || '') !== dosypkaSchemaVersion) {
                state.zasypDosypkaAddedLastSeen = 0;
                persist('agro_zasyp_dosypka_added_last_seen', 0);
                persist(dosypkaSchemaKey, dosypkaSchemaVersion);
            }
        } catch (error) {
            state.zwolnienieLastSeen = 0;
            state.dosypkiLastSeen = 0;
            state.zasypStartLastSeen = 0;
            state.zasypMieszanieStartLastSeen = 0;
            state.zasypDosypkaAddedLastSeen = 0;
            state.zasypDosypkaDismissedTs = 0;
        }

        try {
            var nowTsInit = Date.now() / 1000;
            if (Number(state.zasypDosypkaAddedLastSeen || 0) > (nowTsInit + 5)) {
                state.zasypDosypkaAddedLastSeen = Math.max(0, nowTsInit - 10);
                persist('agro_zasyp_dosypka_added_last_seen', state.zasypDosypkaAddedLastSeen);
            }
            if (Number(state.zasypDosypkaDismissedTs || 0) > (nowTsInit + 5)) {
                state.zasypDosypkaDismissedTs = 0;
                persist('agro_zasyp_dosypka_dismissed_ts', 0);
            }
        } catch (error) {
        }

        try {
            var nowTs = Date.now() / 1000;
            if (!state.zasypStartLastSeen || state.zasypStartLastSeen < (nowTs - 30)) {
                state.zasypStartLastSeen = nowTs;
                persist('agro_zasyp_start_last_seen', state.zasypStartLastSeen);
            }
            if (!state.zasypMieszanieStartLastSeen || state.zasypMieszanieStartLastSeen < (nowTs - 30)) {
                state.zasypMieszanieStartLastSeen = nowTs;
                persist('agro_zasyp_mieszanie_start_last_seen', state.zasypMieszanieStartLastSeen);
            }
            if (!state.zasypDosypkaAddedLastSeen) {
                state.zasypDosypkaAddedLastSeen = Math.max(0, nowTs - 180);
                persist('agro_zasyp_dosypka_added_last_seen', state.zasypDosypkaAddedLastSeen);
            }
        } catch (error) {
        }
    }

    function _setAgroBannerLock(ms) {
        try {
            var until = Date.now() + Number(ms || 0);
            if (until > state.agroBannerLockUntil) {
                state.agroBannerLockUntil = until;
            }
        } catch (error) {
        }
    }

    function _isAgroBannerLocked() {
        try {
            var dosypkaBanner = document.getElementById('zasyp-dosypka-added-banner');
            if (dosypkaBanner && dosypkaBanner.style.display !== 'none') {
                return true;
            }
            var startBanner = document.getElementById('zasyp-start-banner');
            if (startBanner && startBanner.style.display !== 'none') {
                return true;
            }
            var mieszanieBanner = document.getElementById('zasyp-mieszanie-start-banner');
            if (mieszanieBanner && mieszanieBanner.style.display !== 'none') {
                return true;
            }
            var zwolnienieBanner = document.getElementById('zwolnienie-banner');
            if (zwolnienieBanner && zwolnienieBanner.style.display && zwolnienieBanner.style.display !== 'none') {
                return true;
            }
            return Date.now() < Number(state.agroBannerLockUntil || 0);
        } catch (error) {
            return false;
        }
    }

    function _buildAgroEventKey(prefix, eventTs, text, audioFilename) {
        try {
            var normalizedPrefix = String(prefix || 'event');
            var normalizedTs = Number(eventTs || 0) || 0;
            var normalizedText = String(text || '').trim();
            var normalizedAudioFilename = String(audioFilename || '').trim();
            return normalizedPrefix + '|' + String(normalizedTs) + '|' + normalizedText + '|' + normalizedAudioFilename;
        } catch (error) {
            return String(prefix || 'event') + '|0||';
        }
    }

    function _buildAgroSpeechKey(prefix, text, audioFilename) {
        try {
            var normalizedPrefix = String(prefix || 'event');
            var normalizedText = String(text || '').trim();
            var normalizedAudioFilename = String(audioFilename || '').trim();
            return normalizedPrefix + '|' + normalizedText + '|' + normalizedAudioFilename;
        } catch (error) {
            return String(prefix || 'event') + '||';
        }
    }

    function _isSameActiveFallbackSpeech(speechKey) {
        try {
            var key = String(speechKey || '').trim();
            if (!key) {
                return false;
            }
            if (String(state.activeSpeechFallback.key || '') !== key) {
                return false;
            }
            if (state.activeSpeechFallback.active) {
                return true;
            }
            if ('speechSynthesis' in global) {
                return Boolean(global.speechSynthesis.speaking || global.speechSynthesis.pending);
            }
        } catch (error) {
        }
        return false;
    }

    function _registerAgroBannerAudioInstance(audio) {
        try {
            if (!audio) {
                return;
            }
            state.activeAudioInstances.push(audio);
            var cleanup = function () {
                try {
                    state.activeAudioInstances = state.activeAudioInstances.filter(function (item) {
                        return item !== audio;
                    });
                } catch (error) {
                }
            };
            audio.addEventListener('ended', cleanup);
            audio.addEventListener('error', cleanup);
        } catch (error) {
        }
    }

    function _stopAgroBannerMedia() {
        try {
            state.activeAudioInstances.forEach(function (audio) {
                try {
                    audio.pause();
                    audio.currentTime = 0;
                } catch (error) {
                }
            });
            state.activeAudioInstances = [];
        } catch (error) {
        }
        try {
            state.activeSpeechFallback.active = false;
            state.activeSpeechFallback.key = '';
            if ('speechSynthesis' in global) {
                global.speechSynthesis.cancel();
            }
        } catch (error) {
        }
    }

    function _markDosypkaEventDismissed(ts) {
        try {
            var timestamp = Number(ts || 0) || 0;
            if (timestamp <= 0) {
                return;
            }
            if (timestamp > Number(state.zasypDosypkaDismissedTs || 0)) {
                state.zasypDosypkaDismissedTs = timestamp;
                persist('agro_zasyp_dosypka_dismissed_ts', state.zasypDosypkaDismissedTs);
            }
            if (timestamp > Number(state.zasypDosypkaAddedLastSeen || 0)) {
                state.zasypDosypkaAddedLastSeen = timestamp;
                persist('agro_zasyp_dosypka_added_last_seen', state.zasypDosypkaAddedLastSeen);
            }

            try {
                var config = getConfigState();
                var linia = (config && config.linia) || 'PSD';
                fetch('/api/zasyp/ack_dosypka_added', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json',
                    },
                    body: JSON.stringify({ linia: linia, timestamp: timestamp }),
                }).catch(function (error) {
                    console.warn('ack_dosypka_added failed', error);
                });
            } catch (error) {
            }
        } catch (error) {
        }
    }

    function _updateDosypkiActionBadge(planId, delta) {
        try {
            if (!planId) {
                return;
            }
            var trigger = document.querySelector('.btn-with-badge[data-plan-id="' + String(planId) + '"]');
            if (!trigger) {
                return;
            }
            var badge = trigger.querySelector('.action-badge');
            var current = badge ? (parseInt(badge.textContent, 10) || 0) : 0;
            var next = Math.max(0, current + (parseInt(delta, 10) || 0));
            if (next <= 0) {
                if (badge) {
                    try {
                        badge.remove();
                    } catch (error) {
                    }
                }
                return;
            }
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'action-badge';
                trigger.appendChild(badge);
            }
            badge.textContent = String(next);
        } catch (error) {
        }
    }

    function _setDosypkiActionBadgeAbsolute(planId, value) {
        try {
            if (!planId) {
                return;
            }
            var trigger = document.querySelector('.btn-with-badge[data-plan-id="' + String(planId) + '"]');
            if (!trigger) {
                return;
            }
            var badge = trigger.querySelector('.action-badge');
            var next = Math.max(0, parseInt(value, 10) || 0);
            if (next <= 0) {
                if (badge) {
                    try {
                        badge.remove();
                    } catch (error) {
                    }
                }
                return;
            }
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'action-badge';
                trigger.appendChild(badge);
            }
            badge.textContent = String(next);
        } catch (error) {
        }
    }

    function _syncDosypkiBadgesAndFallbackBanner() {
        if (!isAgroZasypPage()) {
            return;
        }

        try {
            var config = getConfigState();
            var linia = (config && config.linia) || 'PSD';
            fetch('/api/zasyp/pending_dosypki_badges?linia=' + encodeURIComponent(linia) + '&data=' + encodeURIComponent(getCurrentDateIso()) + '&_=' + Date.now(), {
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (!data || !data.success) {
                        return;
                    }

                    var counts = (data.counts && typeof data.counts === 'object') ? data.counts : {};
                    document.querySelectorAll('.btn-with-badge[data-plan-id]').forEach(function (button) {
                        try {
                            var planId = String(button.getAttribute('data-plan-id') || '');
                            if (!planId) {
                                return;
                            }
                            _setDosypkiActionBadgeAbsolute(planId, counts[planId] || 0);
                        } catch (error) {
                        }
                    });
                })
                .catch(function (error) {
                    console.error('Dosypki badge sync err', error);
                });
        } catch (error) {
            console.error('Dosypki badge sync setup err', error);
        }
    }

    function _ensureAgroBannerPulseStyle() {
        try {
            if (document.getElementById('agro-banner-pulse-style')) {
                return;
            }
            var style = document.createElement('style');
            style.id = 'agro-banner-pulse-style';
            style.textContent = '' +
                '@keyframes agroPulseSign {' +
                '  0% { transform: scale(1); opacity: 0.95; box-shadow: 0 0 0 0 rgba(239,68,68,0.45); }' +
                '  50% { transform: scale(1.16); opacity: 1; box-shadow: 0 0 0 22px rgba(239,68,68,0); }' +
                '  100% { transform: scale(1); opacity: 0.95; box-shadow: 0 0 0 0 rgba(239,68,68,0); }' +
                '}' +
                '.agro-banner-pulse-sign {' +
                '  width: 72px; height: 72px; min-width: 72px; border-radius: 999px;' +
                '  display: flex; align-items: center; justify-content: center;' +
                '  font-size: 44px; font-weight: 900; line-height: 1;' +
                '  border: 3px solid rgba(0,0,0,0.08); background: #ffffff;' +
                '  animation: agroPulseSign 1.3s ease-in-out infinite;' +
                '}';
            document.head.appendChild(style);
        } catch (error) {
        }
    }

    function _buildAgroPulseSign(symbol, background, border, color) {
        _ensureAgroBannerPulseStyle();
        var normalizedSymbol = symbol || '!';
        var normalizedBackground = background || '#ffffff';
        var normalizedBorder = border || '#ef4444';
        var normalizedColor = color || '#b91c1c';
        return '<div class="agro-banner-pulse-sign" aria-hidden="true" style="background:' + normalizedBackground + ';border-color:' + normalizedBorder + ';color:' + normalizedColor + ';">' + normalizedSymbol + '</div>';
    }

    function closeZwolnienieBanner() {
        var banner = document.getElementById('zwolnienie-banner');
        _stopAgroBannerMedia();
        if (banner) {
            banner.style.display = 'none';
        }
    }

    function ackZwolnienieBanner() {
        try {
            var config = getConfigState();
            var linia = (config && config.linia) || 'AGRO';
            fetch('/api/zasyp/ack_zwolnienie', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({ linia: linia })
            }).catch(function(err){
                console.warn('ack_zwolnienie failed', err);
            });
        } catch (error) {
            console.error('ackZwolnienieBanner error', error);
        }
    }

    function sendZwolnienieMieszalnika() {
        fetch('/api/zasyp/zwolnij_mieszalnik', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ linia: 'AGRO' }),
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (data.success) {
                    global.alert('Sygnał został wystrzelony pomyślnie!');
                    state.zwolnienieLastSeen = data.timestamp;
                    persist('agro_zwolnienie_last_seen', state.zwolnienieLastSeen);
                    return;
                }
                global.alert('Błąd podczas wysyłania sygnału.');
            })
            .catch(function (error) {
                global.alert('Błąd sieci: ' + error);
            });
    }

    function showZwolnienieBanner(audioUrl) {
        var banner = document.getElementById('zwolnienie-banner');
        if (!banner) {
            return;
        }

        banner.style.display = 'flex';

        try {
            var localCandidates = [
                '/static/sounds/doorbell.m4a',
                '/static/sounds/Nagrywanie%20(5).m4a',
                '/static/sounds/Nagrywanie (5).m4a',
            ];
            try {
                if (audioUrl) {
                    localCandidates.unshift(audioUrl);
                }
            } catch (error) {
            }
            var externalFallback = 'https://actions.google.com/sounds/v1/household/doorbell_1.ogg';

            (function tryPlayCandidates(candidates, extFallback) {
                var index = 0;
                var played = false;

                function next() {
                    if (index >= candidates.length) {
                        if (!played) {
                            if (typeof global.playZwolnienieSound === 'function') {
                                try {
                                    global.playZwolnienieSound();
                                    return;
                                } catch (error) {
                                    console.warn('playZwolnienieSound fallback failed:', error);
                                }
                            }
                            if (extFallback) {
                                try {
                                    var fallbackAudio = new Audio(extFallback);
                                    fallbackAudio.play().catch(function (error) {
                                        console.warn('external fallback play failed', error);
                                    });
                                } catch (error) {
                                    console.warn('external fallback error', error);
                                }
                            }
                        }
                        return;
                    }

                    var url = candidates[index++];
                    try {
                        console.debug('[zwolnienie] trying audio candidate:', url);
                        var audio = new Audio(url);
                        _registerAgroBannerAudioInstance(audio);
                        var promise = audio.play();
                        if (promise && typeof promise.then === 'function') {
                            promise.then(function () {
                                played = true;
                                console.debug('[zwolnienie] played', url);
                            }).catch(function (error) {
                                console.warn('[zwolnienie] play failed for', url, error);
                                next();
                            });
                            return;
                        }

                        played = true;
                        console.debug('[zwolnienie] assumed play (no promise) for', url);
                    } catch (error) {
                        console.warn('[zwolnienie] audio exception for', url, error);
                        next();
                    }
                }

                next();
            })(localCandidates, externalFallback);
        } catch (error) {
            console.error('Critical audio error:', error);
        }

        global.setTimeout(function () {
            if (banner) {
                banner.style.display = 'none';
            }
        }, 30000);
    }

    function _buildSoundCandidates(data, expectedPrefix, extraCandidates) {
        var candidates = [];
        try {
            var audioUrl = data && data.audio_url ? String(data.audio_url) : '';
            if (audioUrl && (!expectedPrefix || audioUrl.indexOf(expectedPrefix) !== -1)) {
                candidates.push(audioUrl);
            }
        } catch (error) {
        }
        try {
            var audioFilename = data && data.audio_filename ? String(data.audio_filename) : '';
            if (audioFilename && (!expectedPrefix || audioFilename.indexOf(expectedPrefix) === 0)) {
                candidates.push('/static/sounds/' + encodeURIComponent(audioFilename) + '?v=' + Date.now());
            }
        } catch (error) {
        }
        (extraCandidates || []).forEach(function (url) {
            if (url && candidates.indexOf(url) === -1) {
                candidates.push(url);
            }
        });
        return candidates;
    }

    function _tryPlayUrlWithRetry(url, maxRetries, delayMs) {
        return new Promise(function (resolve, reject) {
            var retries = Number(maxRetries || 1);
            var delay = Number(delayMs || 0);
            var attempt = 0;

            function run() {
                attempt += 1;
                try {
                    var separator = url.indexOf('?') === -1 ? '?' : '&';
                    var urlWithBust = url + separator + 'r=' + attempt + '_' + Date.now();
                    var audio = new Audio(urlWithBust);
                    _registerAgroBannerAudioInstance(audio);
                    audio.volume = 1.0;
                    var promise = audio.play();
                    if (promise && typeof promise.then === 'function') {
                        promise.then(function () {
                            resolve(true);
                        }).catch(function (error) {
                            if (attempt < retries) {
                                global.setTimeout(run, delay);
                                return;
                            }
                            reject(error);
                        });
                        return;
                    }
                    resolve(true);
                } catch (error) {
                    if (attempt < retries) {
                        global.setTimeout(run, delay);
                        return;
                    }
                    reject(error);
                }
            }

            run();
        });
    }

    function _playCandidatesWithRetry(candidates, retriesPerCandidate, delayMs) {
        return new Promise(function (resolve, reject) {
            var list = Array.isArray(candidates) ? candidates.filter(Boolean) : [];
            if (!list.length) {
                reject('no-candidates');
                return;
            }

            var index = 0;
            function next() {
                if (index >= list.length) {
                    reject('all-failed');
                    return;
                }

                var url = list[index++];
                _tryPlayUrlWithRetry(url, retriesPerCandidate, delayMs)
                    .then(function () {
                        resolve(true);
                    })
                    .catch(function () {
                        next();
                    });
            }

            next();
        });
    }

    function _pickPreferredPolishVoice() {
        if (!('speechSynthesis' in global) || typeof global.speechSynthesis.getVoices !== 'function') {
            return null;
        }
        var voices = global.speechSynthesis.getVoices() || [];
        if (!voices.length) {
            return null;
        }

        var preferredNames = [
            'Google polski',
            'Google Polish',
            'Microsoft Paulina Online',
            'Microsoft Zofia Online',
            'Paulina',
            'Zofia',
            'Marek',
        ];

        for (var index = 0; index < preferredNames.length; index += 1) {
            var nameNeedle = preferredNames[index].toLowerCase();
            var found = voices.find(function (voice) {
                return String(voice.name || '').toLowerCase().indexOf(nameNeedle) !== -1;
            });
            if (found) {
                return found;
            }
        }

        var polish = voices.find(function (voice) {
            return String(voice.lang || '').toLowerCase().indexOf('pl') === 0;
        });
        return polish || voices[0] || null;
    }

    function _speakPolishFallback(text, speechKey) {
        if (!text || !('speechSynthesis' in global) || typeof SpeechSynthesisUtterance === 'undefined') {
            return Promise.reject('no-speech');
        }

        var resolvedKey = String(speechKey || '').trim();
        if (_isSameActiveFallbackSpeech(resolvedKey)) {
            return Promise.resolve(true);
        }

        return new Promise(function (resolve, reject) {
            try {
                var utterance = new SpeechSynthesisUtterance(String(text));
                utterance.lang = 'pl-PL';
                utterance.rate = 0.95;
                utterance.pitch = 1.0;
                utterance.volume = 1.0;

                var voice = _pickPreferredPolishVoice();
                if (voice) {
                    utterance.voice = voice;
                }

                var done = false;
                utterance.onend = function () {
                    if (!done) {
                        done = true;
                        state.activeSpeechFallback.active = false;
                        if (String(state.activeSpeechFallback.key || '') === resolvedKey) {
                            state.activeSpeechFallback.key = '';
                        }
                        resolve(true);
                    }
                };
                utterance.onerror = function (error) {
                    if (!done) {
                        done = true;
                        state.activeSpeechFallback.active = false;
                        if (String(state.activeSpeechFallback.key || '') === resolvedKey) {
                            state.activeSpeechFallback.key = '';
                        }
                        reject(error);
                    }
                };

                if (!resolvedKey || String(state.activeSpeechFallback.key || '') !== resolvedKey) {
                    global.speechSynthesis.cancel();
                }
                state.activeSpeechFallback.key = resolvedKey;
                state.activeSpeechFallback.active = true;
                global.speechSynthesis.speak(utterance);
            } catch (error) {
                state.activeSpeechFallback.active = false;
                if (String(state.activeSpeechFallback.key || '') === resolvedKey) {
                    state.activeSpeechFallback.key = '';
                }
                reject(error);
            }
        });
    }

    function showZasypStartBanner(data) {
        try {
            var eventTs = Number((data && data.timestamp) || 0) || 0;
            var eventKey = _buildAgroEventKey('zasyp_start', eventTs, data && data.tts_text, data && data.audio_filename);
            var speechKey = _buildAgroSpeechKey('zasyp_start', data && data.tts_text, data && data.audio_filename);
            if (eventKey && eventKey === state.lastRenderedZasypStartKey) {
                _setAgroBannerLock(6000);
                return;
            }
            if (eventTs && eventTs <= state.lastRenderedZasypStartTs) {
                _setAgroBannerLock(6000);
                return;
            }
            if (eventTs) {
                state.lastRenderedZasypStartTs = eventTs;
            }
            state.lastRenderedZasypStartKey = eventKey;
            _setAgroBannerLock(50000);
            var existing = document.getElementById('zasyp-start-banner');
            if (existing) {
                _stopAgroBannerMedia();
                try {
                    existing.remove();
                } catch (error) {
                }
            }

            var product = data.produkt || '';
            var szarza = (data.szarza_nr !== undefined && data.szarza_nr !== null) ? data.szarza_nr : '';
            var message = '<div style="font-weight:700; margin-bottom:6px;">OPERATOR ROZPOCZĄŁ NAWAŻANIE</div>' +
                '<div style="font-size:0.95em;">' + (product ? product : '') + (szarza ? (' — SZARŻA NR ' + szarza) : '') + '</div>';

            var banner = document.createElement('div');
            banner.id = 'zasyp-start-banner';
            banner.setAttribute('role', 'status');
            banner.style.position = 'fixed';
            banner.style.left = '50%';
            banner.style.transform = 'translateX(-50%)';
            banner.style.top = '80px';
            banner.style.zIndex = 99999;
            banner.style.minWidth = '320px';
            banner.style.maxWidth = '720px';
            banner.style.background = '#fff7ed';
            banner.style.border = '1px solid #f6bd56';
            banner.style.boxShadow = '0 8px 30px rgba(0,0,0,0.12)';
            banner.style.padding = '14px 16px';
            banner.style.borderRadius = '10px';
            banner.style.fontFamily = 'inherit';

            banner.innerHTML = '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">' +
                _buildAgroPulseSign('!', '#fff7ed', '#f59e0b', '#b45309') +
                '<div style="flex:1">' + message + '</div>' +
                '<div style="margin-left:8px"><button id="zasyp-start-dismiss" style="background:#f1f2f6;border:none;padding:6px 10px;border-radius:8px;cursor:pointer">OK</button></div>' +
                '</div>';

            document.body.appendChild(banner);
            try {
                document.getElementById('zasyp-start-dismiss').addEventListener('click', function () {
                    _stopAgroBannerMedia();
                    try {
                        banner.remove();
                    } catch (error) {
                    }
                });
            } catch (error) {
            }

            var candidates = _buildSoundCandidates(data, 'zasyp_start_', ['/static/sounds/doorbell.m4a']);
            _playCandidatesWithRetry(candidates, 6, 300).catch(function () {
                _speakPolishFallback(data.tts_text, speechKey).catch(function () {
                    try {
                        if (typeof global.playZwolnienieSound === 'function') {
                            global.playZwolnienieSound();
                        }
                    } catch (error) {
                    }
                });
            });

            global.setTimeout(function () {
                try {
                    banner.remove();
                } catch (error) {
                }
            }, 45000);
        } catch (error) {
            console.error('showZasypStartBanner error', error);
        }
    }

    function showZasypMieszanieStartBanner(data) {
        try {
            var eventTs = Number((data && data.timestamp) || 0) || 0;
            var eventKey = _buildAgroEventKey('zasyp_mieszanie_start', eventTs, data && data.tts_text, data && data.audio_filename);
            var speechKey = _buildAgroSpeechKey('zasyp_mieszanie_start', data && data.tts_text, data && data.audio_filename);
            if (eventKey && eventKey === state.lastRenderedZasypMieszanieStartKey) {
                _setAgroBannerLock(6000);
                return;
            }
            if (eventTs && eventTs <= state.lastRenderedZasypMieszanieStartTs) {
                _setAgroBannerLock(6000);
                return;
            }
            if (eventTs) {
                state.lastRenderedZasypMieszanieStartTs = eventTs;
            }
            state.lastRenderedZasypMieszanieStartKey = eventKey;
            _setAgroBannerLock(50000);
            var existing = document.getElementById('zasyp-mieszanie-start-banner');
            if (existing) {
                _stopAgroBannerMedia();
                try {
                    existing.remove();
                } catch (error) {
                }
            }

            var product = data.produkt || '';
            var szarza = (data.szarza_nr !== undefined && data.szarza_nr !== null) ? data.szarza_nr : '';
            var title = data.banner_title || 'OPERATOR ROZPOCZĄŁ MIESZANIE';
            var etapInfo = (data.etap_nr !== undefined && data.etap_nr !== null) ? (' — ETAP ' + data.etap_nr) : '';
            var message = '<div style="font-weight:700; margin-bottom:6px;">' + title + etapInfo + '</div>' +
                '<div style="font-size:0.95em;">' + (product ? product : '') + (szarza ? (' — SZARŻA NR ' + szarza) : '') + '</div>';

            var banner = document.createElement('div');
            banner.id = 'zasyp-mieszanie-start-banner';
            banner.setAttribute('role', 'status');
            banner.style.position = 'fixed';
            banner.style.left = '50%';
            banner.style.transform = 'translateX(-50%)';
            banner.style.top = '140px';
            banner.style.zIndex = 99999;
            banner.style.minWidth = '320px';
            banner.style.maxWidth = '720px';
            banner.style.background = '#ecfeff';
            banner.style.border = '1px solid #67e8f9';
            banner.style.boxShadow = '0 8px 30px rgba(0,0,0,0.12)';
            banner.style.padding = '14px 16px';
            banner.style.borderRadius = '10px';
            banner.style.fontFamily = 'inherit';

            banner.innerHTML = '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">' +
                _buildAgroPulseSign('!', '#ecfeff', '#06b6d4', '#0e7490') +
                '<div style="flex:1">' + message + '</div>' +
                '<div style="margin-left:8px"><button id="zasyp-mieszanie-start-dismiss" style="background:#f1f2f6;border:none;padding:6px 10px;border-radius:8px;cursor:pointer">OK</button></div>' +
                '</div>';

            document.body.appendChild(banner);
            try {
                document.getElementById('zasyp-mieszanie-start-dismiss').addEventListener('click', function () {
                    _stopAgroBannerMedia();
                    try {
                        banner.remove();
                    } catch (error) {
                    }
                });
            } catch (error) {
            }

            var candidates = _buildSoundCandidates(data, 'zasyp_mieszanie_start_', ['/static/sounds/doorbell.m4a']);
            _playCandidatesWithRetry(candidates, 6, 300).catch(function () {
                _speakPolishFallback(data.tts_text, speechKey).catch(function () {
                    try {
                        if (typeof global.playZwolnienieSound === 'function') {
                            global.playZwolnienieSound();
                        }
                    } catch (error) {
                    }
                });
            });

            global.setTimeout(function () {
                try {
                    banner.remove();
                } catch (error) {
                }
            }, 45000);
        } catch (error) {
            console.error('showZasypMieszanieStartBanner error', error);
        }
    }

    function showZwolnienieAckBanner(data) {
        try {
            var eventTs = Number((data && data.timestamp) || 0) || 0;
            if (eventTs && eventTs <= state.zwolnienieAckLastSeen) {
                return;
            }
            state.zwolnienieAckLastSeen = eventTs;
            persist('agro_zwolnienie_ack_last_seen', state.zwolnienieAckLastSeen);

            var existing = document.getElementById('zwolnienie-ack-banner');
            if (existing) {
                try { existing.remove(); } catch(e){}
            }

            var banner = document.createElement('div');
            banner.id = 'zwolnienie-ack-banner';
            banner.style.position = 'fixed';
            banner.style.left = '50%';
            banner.style.transform = 'translateX(-50%)';
            banner.style.top = '260px';
            banner.style.zIndex = 99999;
            banner.style.minWidth = '320px';
            banner.style.background = '#f0fdf4';
            banner.style.border = '1px solid #86efac';
            banner.style.boxShadow = '0 8px 30px rgba(0,0,0,0.12)';
            banner.style.padding = '14px 16px';
            banner.style.borderRadius = '10px';

            banner.innerHTML = '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">' +
                _buildAgroPulseSign('✓', '#f0fdf4', '#22c55e', '#15803d') +
                '<div style="flex:1"><div style="font-weight:700;">POTWIERDZENIE ZWOLNIENIA</div><div style="font-size:0.9em;">Operator potwierdził zwolnienie mieszalnika.</div></div>' +
                '<div style="margin-left:8px"><button id="zwolnienie-ack-dismiss" style="background:#f1f2f6;border:none;padding:6px 10px;border-radius:8px;cursor:pointer">OK</button></div>' +
                '</div>';

            document.body.appendChild(banner);
            document.getElementById('zwolnienie-ack-dismiss').addEventListener('click', function(){
                _stopAgroBannerMedia();
                banner.remove();
            });

            _speakPolishFallback("Operator potwierdził zwolnienie mieszalnika.", "zwolnienie_ack_tts");

            global.setTimeout(function(){
                try { banner.remove(); } catch(e){}
            }, 30000);
        } catch (error) {
            console.error('showZwolnienieAckBanner error', error);
        }
    }

    function showZasypDosypkaAddedBanner(data) {
        if (!isAgroZasypPage()) {
            return;
        }
        try {
            var eventTs = Number((data && data.timestamp) || 0) || 0;
            var eventKey = _buildAgroEventKey('zasyp_dosypka_added', eventTs, data && data.tts_text, data && data.audio_filename);
            var speechKey = _buildAgroSpeechKey('zasyp_dosypka_added', data && data.tts_text, data && data.audio_filename);
            if (eventKey && eventKey === state.lastRenderedZasypDosypkaAddedKey) {
                _setAgroBannerLock(6000);
                return;
            }
            if (eventTs && eventTs <= Number(state.zasypDosypkaDismissedTs || 0)) {
                if (eventTs > state.lastRenderedZasypDosypkaAddedTs) {
                    state.lastRenderedZasypDosypkaAddedTs = eventTs;
                }
                state.lastRenderedZasypDosypkaAddedKey = eventKey;
                return;
            }
            if (eventTs && eventTs <= state.lastRenderedZasypDosypkaAddedTs) {
                _setAgroBannerLock(6000);
                return;
            }
            if (eventTs) {
                state.lastRenderedZasypDosypkaAddedTs = eventTs;
            }
            state.lastRenderedZasypDosypkaAddedKey = eventKey;
            _setAgroBannerLock(70000);
            var existing = document.getElementById('zasyp-dosypka-added-banner');
            if (existing) {
                _stopAgroBannerMedia();
                try {
                    existing.remove();
                } catch (error) {
                }
            }

            var product = data.produkt || '';
            var szarza = (data.szarza_nr !== undefined && data.szarza_nr !== null) ? data.szarza_nr : '';
            var count = (data.dosypki_count !== undefined && data.dosypki_count !== null) ? data.dosypki_count : '';
            var title = data.banner_title || 'LABORANT DODAŁ SKŁADNIKI DOSYPKI';
            var message = '<div style="font-weight:700; margin-bottom:6px;">' + title + '</div>' +
                '<div style="font-size:0.95em; margin-bottom:4px;">• Laborant dodał do listy składniki dosypki.</div>' +
                '<div style="font-size:0.92em;">' + (product ? ('Produkt: ' + product) : '') + (count ? (' — Pozycje: ' + count) : '') + (szarza ? (' — SZARŻA NR ' + szarza) : '') + '</div>';

            var banner = document.createElement('div');
            banner.id = 'zasyp-dosypka-added-banner';
            banner.setAttribute('role', 'status');
            banner.style.position = 'fixed';
            banner.style.left = '50%';
            banner.style.transform = 'translateX(-50%)';
            banner.style.top = '200px';
            banner.style.zIndex = 99999;
            banner.style.minWidth = '320px';
            banner.style.maxWidth = '720px';
            banner.style.background = '#fef9c3';
            banner.style.border = '1px solid #facc15';
            banner.style.boxShadow = '0 8px 30px rgba(0,0,0,0.12)';
            banner.style.padding = '14px 16px';
            banner.style.borderRadius = '10px';
            banner.style.fontFamily = 'inherit';

            banner.innerHTML = '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">' +
                _buildAgroPulseSign('!', '#fef9c3', '#facc15', '#a16207') +
                '<div style="flex:1">' + message + '</div>' +
                '<div style="margin-left:8px"><button id="zasyp-dosypka-added-dismiss" style="background:#f1f2f6;border:none;padding:6px 10px;border-radius:8px;cursor:pointer">OK</button></div>' +
                '</div>';

            document.body.appendChild(banner);
            try {
                document.getElementById('zasyp-dosypka-added-dismiss').addEventListener('click', function () {
                    _stopAgroBannerMedia();
                    _markDosypkaEventDismissed(eventTs);
                    try {
                        banner.remove();
                    } catch (error) {
                    }
                    state.agroBannerLockUntil = 0;
                });
            } catch (error) {
            }

            var candidates = _buildSoundCandidates(data, 'zasyp_dosypka_added_', ['/static/sounds/doorbell.m4a']);
            _playCandidatesWithRetry(candidates, 6, 300).catch(function () {
                _speakPolishFallback(data.tts_text, speechKey).catch(function () {
                    try {
                        if (typeof global.playZwolnienieSound === 'function') {
                            global.playZwolnienieSound();
                        }
                    } catch (error) {
                    }
                });
            });
        } catch (error) {
            console.error('showZasypDosypkaAddedBanner error', error);
        }
    }

    function handleDocumentClick(event) {
        if (event.target && event.target.id === 'zwolnienie-banner-close') {
            event.preventDefault();
            ackZwolnienieBanner();
            closeZwolnienieBanner();
        }
    }

    function init() {
        if (initialized) {
            return;
        }
        initialized = true;

        _ensureAgroBannerPulseStyle();
        document.addEventListener('click', handleDocumentClick, false);

        if (!isAgroZasypPage()) {
            return;
        }

        hydrateState();
        loadSoundScript();
    }

    function showLaborantZasypBanner() {
        try {
            var existing = document.getElementById('laborant-zasyp-banner');
            if (existing) {
                return;
            }

            var banner = document.createElement('div');
            banner.id = 'laborant-zasyp-banner';
            banner.setAttribute('role', 'status');
            banner.style.position = 'fixed';
            banner.style.left = '50%';
            banner.style.transform = 'translateX(-50%)';
            banner.style.top = '100px';
            banner.style.zIndex = 99999;
            banner.style.minWidth = '320px';
            banner.style.maxWidth = '720px';
            banner.style.background = '#eff6ff';
            banner.style.border = '1px solid #3b82f6';
            banner.style.boxShadow = '0 8px 30px rgba(0,0,0,0.12)';
            banner.style.padding = '14px 16px';
            banner.style.borderRadius = '10px';
            banner.style.fontFamily = 'inherit';

            banner.innerHTML = '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">' +
                _buildAgroPulseSign('i', '#eff6ff', '#3b82f6', '#1d4ed8') +
                '<div style="flex:1"><div style="font-weight:700; margin-bottom:6px;">OPERATOR ZATWIERDZIŁ NOWY ZASYP</div><div style="font-size:0.95em;">Możesz teraz dodać składniki dosypki.</div></div>' +
                '<div style="margin-left:8px"><button id="laborant-zasyp-dismiss" style="background:#f1f2f6;border:none;padding:6px 10px;border-radius:8px;cursor:pointer">OK</button></div>' +
                '</div>';

            document.body.appendChild(banner);
            try {
                document.getElementById('laborant-zasyp-dismiss').addEventListener('click', function () {
                    try { banner.remove(); } catch (error) {}
                });
            } catch (error) {}
            
            // Play a standard notification sound
            try {
                var audio = new Audio('/static/sounds/doorbell.m4a');
                audio.play().catch(function(){});
            } catch (error) {}
            
            // Note: INTENTIONALLY NO TIMEOUT so it hangs until dismissed by Laborant
        } catch (error) {
            console.error('showLaborantZasypBanner error', error);
        }
    }

    global.dashboardAgroBanners = {
        init: init,
        stopMedia: _stopAgroBannerMedia,
        isBannerLocked: _isAgroBannerLocked,
        syncDosypkiBadgesAndFallbackBanner: _syncDosypkiBadgesAndFallbackBanner,
        sendZwolnienieMieszalnika: sendZwolnienieMieszalnika,
        closeZwolnienieBanner: closeZwolnienieBanner,
        showZwolnienieBanner: showZwolnienieBanner,
        showZwolnienieAckBanner: showZwolnienieAckBanner,
        showZasypStartBanner: showZasypStartBanner,
        showZasypMieszanieStartBanner: showZasypMieszanieStartBanner,
        showZasypDosypkaAddedBanner: showZasypDosypkaAddedBanner,
        showLaborantZasypBanner: showLaborantZasypBanner,
    };

    ready(init);
})(window);