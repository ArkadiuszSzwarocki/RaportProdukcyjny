/* static/scripts.js - Globalna logika aplikacji */

(function () {
    'use strict';

    // --- Stałe konfiguracyjne ---
    const DEFAULT_REFRESH_INTERVAL_MS = 60_000; // Domyślne auto-odświeżanie co 60s
    const SLOW_REFRESH_INTERVAL_MS = 180_000; // Spokojniejsze odświeżanie dla Zasyp/Workowanie co 3 min
    const MIN_VALID_CHARS = 50; // Walidacja opisu awarii
    const ACTIVE_BG = '#d32f2f';
    const INACTIVE_BG = 'gray';

    function getCurrentSection() {
        try {
            const dayTile = document.querySelector('.day-tile[data-sekcja]');
            if (dayTile) {
                return String(dayTile.getAttribute('data-sekcja') || '').trim();
            }

            const params = new URLSearchParams(window.location.search);
            return String(params.get('sekcja') || '').trim();
        } catch (e) {
            return '';
        }
    }

    function getRefreshIntervalMs() {
        const section = getCurrentSection().toLowerCase();
        const path = window.location.pathname.toLowerCase();
        
        if (section === 'zasyp' || section === 'workowanie' || section === 'magazyn' || path.includes('/magazyn')) {
            return SLOW_REFRESH_INTERVAL_MS;
        }
        return DEFAULT_REFRESH_INTERVAL_MS;
    }

    // --- ZACHOWYWANIE POZYCJI PRZEWIJANIA (Scroll Preservation) ---
    // Ta funkcja działa na każdej podstronie systemu
    function initScrollPreservation() {
        const scrollKey = 'system_scroll_pos';

        // 1. Jeśli mamy zapisaną pozycję, przewiń do niej
        const savedPos = localStorage.getItem(scrollKey);
        if (savedPos) {
            window.scrollTo(0, parseInt(savedPos));
            localStorage.removeItem(scrollKey); // Czyścimy po użyciu
        }

        // 2. Nasłuchuj wysyłania formularzy (każde kliknięcie przycisku "Zapisz", strzałek itp.)
        document.addEventListener('submit', function (e) {
            if (e.target.tagName === 'FORM') {
                localStorage.setItem(scrollKey, window.scrollY);
            }
        });
    }

    // --- Elementy DOM (Dashboard - Awarie) ---
    const czasInput = document.getElementById('czasStart');
    const poleTekstowe = document.getElementById('opisProblemu');
    const licznik = document.getElementById('licznikZnakow');
    const przycisk = document.getElementById('btnZglos');

    // --- Elementy DOM (HR - Obecność) ---
    const selectTyp = document.getElementById('selectTyp');
    const inputPowod = document.getElementById('inputPowod');

    // --- Funkcje pomocnicze ---
    function getCzystaTresc(tekst) {
        return (tekst || '').replace(/[^a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]/g, '');
    }

    function ustawStanPrzycisku(liczbaZnakow) {
        if (!licznik || !przycisk) return;

        licznik.innerText = `Liczba ważnych znaków: ${liczbaZnakow} / ${MIN_VALID_CHARS}`;

        if (liczbaZnakow >= MIN_VALID_CHARS) {
            licznik.style.color = 'green';
            przycisk.disabled = false;
            przycisk.style.background = ACTIVE_BG;
            przycisk.style.cursor = 'pointer';
            przycisk.innerText = 'ZGŁOŚ PROBLEM';
        } else {
            licznik.style.color = 'red';
            przycisk.disabled = true;
            przycisk.style.background = INACTIVE_BG;
            przycisk.style.cursor = 'not-allowed';
            przycisk.innerText = `ZGŁOŚ PROBLEM (Brakuje ${MIN_VALID_CHARS - liczbaZnakow})`;
        }
    }

    function aktualizujWalidacje() {
        if (!poleTekstowe) return;
        const czysta = getCzystaTresc(poleTekstowe.value);
        ustawStanPrzycisku(czysta.length);
    }

    function inicjujGodzine() {
        if (!czasInput) return;
        const now = new Date();
        const godz = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        czasInput.value = `${godz}:${min}`;
    }

    function initSelectTypListener() {
        if (!selectTyp || !inputPowod) return;
        selectTyp.addEventListener('change', function () {
            const wymagane = this.value === 'Nadgodziny';
            inputPowod.required = wymagane;
            inputPowod.classList.toggle('input-required', wymagane);
            inputPowod.placeholder = wymagane ? 'WPISZ POWÓD (Wymagane!)' : 'Powód...';
        });
    }

    // --- Ochrona przed auto-reloadem po ustawieniu skip_open_stop ---
    function skipOpenStopActive() {
        try {
            const v = sessionStorage.getItem('skip_open_stop');
            if (v !== '1') return false;
            const key = 'skip_open_stop_ts';
            const now = Date.now();
            const ts = parseInt(sessionStorage.getItem(key) || '0', 10);
            if (!ts) { sessionStorage.setItem(key, String(now)); return true; }
            // zachowaj odstęp ochronny 5s od momentu pierwszego zauważenia flagi
            return (now - ts) < 5000;
        } catch (e) {
            return false;
        }
    }

    function hasFocusedEditableElement() {
        const active = document.activeElement;

        // --- PREVENT REFRESH IF BULK CHECKBOXES ARE SELECTED ---
        // If there are checked checkboxes for bulk actions (like planista_bulk), we must not reload and lose them.
        const checkedCheckboxes = document.querySelectorAll('input[type="checkbox"]:checked');
        if (checkedCheckboxes.length > 0) return true;

        if (!active) return false;

        // Minor/simple inputs do not block auto-refresh if focus/value is preserved
        if (active.name === 'waga_palety' || active.name === 'tonaz' || active.id === 'move_to_date_work') {
            return false;
        }

        if (active.matches && active.matches('input, textarea, select')) return true;
        return !!(active.closest && active.closest('[contenteditable="true"]'));
    }

    function hasBlockingOverlayOpen() {
        return !!(
            document.hidden ||
            document.body.classList.contains('slide-over-open') ||
            document.body.classList.contains('sidebar-open') ||
            document.querySelector('.quick-popup.open, .drawer.open, .bottom-sheet.open, .fullscreen-modal.open, .wizard-modal') ||
            document.querySelector('.modal.show, .modal-premium[open], dialog[open], #manualModal[style*="display: flex"]') ||
            // --- NEW: Block refresh if a Select2 or standard select dropdown is open ---
            document.querySelector('.select2-container--open') ||
            // --- NEW: Block refresh if standard dropdown menus (.show) are open ---
            document.querySelector('.dropdown-menu.show') ||
            // --- NEW: Block refresh if the language or notifications menu is open ---
            document.querySelector('#languageMenu.open') ||
            document.querySelector('#languageMenu[style*="display: flex"]') ||
            document.querySelector('#notificationsMenu[style*="display: block"]') ||
            document.querySelector('#notificationsMenu[aria-hidden="false"]')
        );
    }

    function captureExpandedDetails() {
        try {
            // Capture both old details- format and new expanded-content format
            const oldDetails = Array.from(document.querySelectorAll('[id^="details-"]'))
                .filter(el => el.style.display !== 'none' && getComputedStyle(el).display !== 'none')
                .map(el => el.id);
            
            const newDetails = Array.from(document.querySelectorAll('.expanded-content.show'))
                .map(el => el.id);

            return [...oldDetails, ...newDetails];
        } catch (e) {
            return [];
        }
    }

    function restoreExpandedDetails(expandedIds) {
        if (!Array.isArray(expandedIds) || expandedIds.length === 0) return;
        expandedIds.forEach(function (id) {
            const el = document.getElementById(id);
            if (!el) return;
            
            if (id.startsWith('details-')) {
                el.style.display = 'block';
            } else {
                // New table structure (Agro)
                el.classList.add('show');
                const parent = el.previousElementSibling;
                if (parent && parent.classList.contains('expandable-row')) {
                    parent.classList.add('expanded');
                }
            }
        });
    }

    function hasActiveSearch() {
        try {
            // Check for search inputs that might have user-entered text
            const searchInputs = document.querySelectorAll('input[id*="Search" i], input[id*="filter" i], .inventory-search-input');
            for (let input of searchInputs) {
                if (input.value && input.value.trim().length > 0) {
                    // Only block if the input is actually visible (not a hidden config input)
                    if (input.offsetWidth > 0 || input.offsetHeight > 0) {
                        return true;
                    }
                }
            }
        } catch (e) {}
        return false;
    }

    function showRefreshIndicator(message) {
        try {
            const text = message || 'Dane odświeżone';
            let indicator = document.getElementById('refreshIndicator');
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'refreshIndicator';
                indicator.className = 'refresh-indicator';
                document.body.appendChild(indicator);
            }

            if (indicator._hideTimer) {
                clearTimeout(indicator._hideTimer);
            }

            indicator.textContent = text;
            indicator.classList.add('show');
            indicator._hideTimer = setTimeout(function () {
                indicator.classList.remove('show');
            }, 1800);
        } catch (e) {
            console.warn('showRefreshIndicator failed', e);
        }
    }

    // Bezpieczny alert używający showQuickPopup gdy dostępny, z fallbackiem na natywny alert
    function safeAlert(title, message) {
        try {
            if (typeof showQuickPopup === 'function') {
                try {
                    var html = '<div class="p-10">' + (message || '') + '</div>';
                    showQuickPopup(title || '', html);
                    return;
                } catch (e) {
                    // fallthrough to native alert
                }
            }
            var text = (title ? title + "\n\n" : '') + (message || '');
            alert(text);
        } catch (e) {
            try { alert((message || title) || ''); } catch (ee) { /* ignore */ }
        }
    }

    // Format and sanitize error-like values for display
    function formatError(err) {
        try {
            if (!err && err !== 0) return '';
            // If it's an Error object
            if (typeof err === 'object') {
                if (err.message) return String(err.message);
                // try JSON stringify fallback
                try { return JSON.stringify(err); } catch (e) { return String(err); }
            }
            // If it's already a string, try to parse JSON to extract message
            var s = String(err);
            // Try to detect JSON blob and extract .message
            if (/^\s*[{\[]/.test(s)) {
                try {
                    var parsed = JSON.parse(s);
                    if (parsed && parsed.message) return String(parsed.message);
                    // If parsed is object, return a short stringified version
                    return JSON.stringify(parsed);
                } catch (e) {
                    // fallthrough to unescape unicode sequences
                }
            }
            // Decode \uXXXX sequences
            try {
                return s.replace(/\\u([0-9a-fA-F]{4})/g, function (match, grp) { return String.fromCharCode(parseInt(grp, 16)); });
            } catch (e) { return s; }
        } catch (e) {
            try { return String(err); } catch (ee) { return 'Błąd'; }
        }
    }

    // Sanitize HTML content passed to showQuickPopup: extract JSON.message or decode unicode escapes
    function sanitizePopupContent(content) {
        try {
            if (!content || typeof content !== 'string') return content;
            // If content contains a JSON object with message property, extract it
            var jsonMatch = content.match(/\{\s*"message"[\s\S]*?\}/);
            if (jsonMatch) {
                try {
                    var parsed = JSON.parse(jsonMatch[0]);
                    var msg = parsed.message || JSON.stringify(parsed);
                    // Replace the JSON blob in content with the plain message
                    return content.replace(jsonMatch[0], String(msg));
                } catch (e) {
                    // ignore and fallthrough
                }
            }
            // Decode unicode escapes like \u00f3
            var decoded = content.replace(/\\u([0-9a-fA-F]{4})/g, function (m, g) { return String.fromCharCode(parseInt(g, 16)); });
            return decoded;
        } catch (e) { return content; }
    }

    function shouldSkipAutoRefresh() {
        if (skipOpenStopActive()) return true;
        if (hasFocusedEditableElement()) return true;
        if (hasBlockingOverlayOpen()) return true;
        if (hasActiveSearch()) return true;

        // Check for any expanded rows in tables (this indicates user is looking at details)
        const visibleDetails = Array.from(document.querySelectorAll('.expanded-content.show, .details-row')).some(el => {
            if (el.classList.contains('expanded-content')) return true;
            return el.style.display !== 'none' && getComputedStyle(el).display !== 'none';
        });
        if (visibleDetails) return true;

        // Wyłącz auto-refresh na stronach z formularzami (data-no-autorefresh)
        try {
            const main = document.getElementById('mainContent');
            if (main && main.querySelector('[data-no-autorefresh]')) return true;
        } catch (e) {}
        return false;
    }

    // --- INTELLIGENT POLLING (Smart Refresh) ---
    let lastKnownSystemState = null;
    let smartPollingTimer = null;

    async function checkSystemState() {
        if (partialReloadInFlight) return;
        if (shouldSkipAutoRefresh()) return;

        try {
            const linia = getCurrentSection() || 'PSD';
            const resp = await fetch(`/api/system_state?linia=${encodeURIComponent(linia)}`, { 
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                silent: true
            });
            if (resp.status === 401) {
                console.warn('[SmartPolling] Session expired (401), stopping.');
                stopSmartPolling();
                return;
            }
            if (!resp.ok) return;
            const data = await resp.json();
            if (!data.success || !data.state) return;

            const newState = data.state;

            if (lastKnownSystemState) {
                // Check if anything significant changed
                const changed = (
                    newState.last_move !== lastKnownSystemState.last_move ||
                    newState.last_plan !== lastKnownSystemState.last_plan ||
                    newState.last_notif !== lastKnownSystemState.last_notif ||
                    newState.last_station_change !== lastKnownSystemState.last_station_change
                );

                if (changed) {
                    console.info('[SmartPolling] Change detected, reloading...', newState);
                    performPartialReload({ source: 'smart-polling' });
                }
            }
            lastKnownSystemState = newState;
        } catch (e) {
            console.warn('[SmartPolling] Fetch failed', e);
        }
    }

    function stopSmartPolling() {
        if (smartPollingTimer) { clearInterval(smartPollingTimer); smartPollingTimer = null; }
    }

    function startSmartPolling() {
        stopSmartPolling();
        // Poll every 10 seconds (cheap check)
        smartPollingTimer = setInterval(checkSystemState, 10000);
        // Initial check
        checkSystemState();
    }

    // --- INICJALIZACJA ---
    document.addEventListener('DOMContentLoaded', function () {
        // Uruchomienie mechanizmu scrolla
        initScrollPreservation();

        // Uruchomienie inteligentnego odpytywania
        startSmartPolling();

        // Uruchomienie logiki Dashboardu (jeśli elementy istnieją)
        inicjujGodzine();
        initSelectTypListener();
        if (poleTekstowe) {
            poleTekstowe.addEventListener('input', aktualizujWalidacje);
            aktualizujWalidacje();
        }

        // top-submenu handlers removed: now using standard data-slide behavior

        // handle browser back/forward to re-fetch content
        window.addEventListener('popstate', function (ev) {
            try { if (ev.state && ev.state.url) { fetch(ev.state.url, { credentials: 'same-origin' }).then(r => r.text()).then(t => { const tmp = document.createElement('div'); tmp.innerHTML = t; const nm = tmp.querySelector('#mainContent'); const cm = document.getElementById('mainContent'); if (nm && cm) cm.innerHTML = nm.innerHTML; }); } } catch (e) { }
        });

        // Ensure date input is interactive even if a backdrop/quick-popup is present:
        try {
            var dateInput = document.querySelector('input[name="data"]');
            if (dateInput) {
                var restoreDateClicks = function (ev) {
                    try {
                        var hasOpenOverlay = false;
                        var qb = document.getElementById('quickBackdrop');
                        var qp = document.getElementById('quickPopup');
                        var sb = document.getElementById('selectBackdrop');
                        var sm = document.getElementById('selectModal');
                        if (qb && qb.classList.contains('show')) hasOpenOverlay = true;
                        if (qp && qp.classList.contains('open')) hasOpenOverlay = true;
                        if (sb && sb.classList.contains('active')) hasOpenOverlay = true;
                        if (sm && sm.classList.contains('active')) hasOpenOverlay = true;
                        if (document.body.classList.contains('modal-open') || document.body.classList.contains('slide-over-open')) hasOpenOverlay = true;

                        // Do not touch anything when overlays are already closed.
                        if (!hasOpenOverlay) return;

                        if (window.createQuickPopup && window.createQuickPopup._lastInst) {
                            try { window.createQuickPopup._lastInst.close(); } catch (e) { }
                        }
                        if (qb) { qb.classList.remove('show'); qb.setAttribute('aria-hidden', 'true'); }
                        if (qp) { qp.classList.remove('open'); qp.setAttribute('aria-hidden', 'true'); }
                        if (sb) { sb.classList.remove('active'); }
                        if (sm) { sm.classList.remove('active'); }
                        // Remove any body-level modal classes that may block clicks
                        try { document.body.classList.remove('modal-open', 'slide-over-open'); } catch (e) { }
                    } catch (e) { /* ignore */ }
                };
                dateInput.addEventListener('focus', restoreDateClicks);
            }
        } catch (e) { /* ignore */ }

        // Modal management removed — modale są wyłączone w całej aplikacji.
        // Wrap global showQuickPopup to sanitize content (decode JSON/unicode) if present
        try {
            if (window.showQuickPopup && !window.__showQuickPopupWrapped) {
                var __origShowQuickPopup = window.showQuickPopup;
                window.showQuickPopup = function (title, content) {
                    try { content = sanitizePopupContent(content); } catch (e) { /* ignore */ }
                    return __origShowQuickPopup(title, content);
                };
                window.__showQuickPopupWrapped = true;
            }
        } catch (e) { /* ignore */ }
    });

    // Global click delegation: any element with `data-slide` or `data-slide-html` opens slide-over
    document.addEventListener('click', function (e) {
        try {
            var el = e.target.closest && e.target.closest('[data-slide], [data-slide-html], .slide-link');
            if (!el) {
                // also intercept anchors that point to API page endpoints (convention: urls containing '/api/' and '_page' or modal-like names)
                var a = e.target.closest && e.target.closest('a[href]');
                if (a) {
                    var href = a.getAttribute('href') || '';
                    if (href.indexOf('/api/') !== -1 && (href.indexOf('_page') !== -1 || href.indexOf('dodaj') !== -1 || href.indexOf('edytuj') !== -1 || href.indexOf('confirm_delete') !== -1 || href.indexOf('przywroc') !== -1)) {
                        el = a;
                    }
                }
            }
            if (!el) return;
            // prevent default navigation
            e.preventDefault();
            var url = el.getAttribute('data-slide') || el.getAttribute('href');
            var html = el.getAttribute('data-slide-html');
            // allow per-element opt-out via `data-allow-backdrop="false"`
            var allowAttr = el.getAttribute && el.getAttribute('data-allow-backdrop');
            var allowBackdrop = allowAttr === 'false' ? false : true;
            if (html) { showSlideOver(html, { isHtml: true, backdrop: true, allowBackdropClose: allowBackdrop }); return; }
            if (!url || url === '#' || url.indexOf('javascript:') === 0) { showSlideOver('<div class="p-10">Brak docelowego adresu</div>', { isHtml: true }); return; }
            showSlideOver(url, { backdrop: true, allowBackdropClose: allowBackdrop, transient: false });
        } catch (err) { console.error('Click delegation error:', err); }
    }, false);

    let partialReloadInFlight = false;

    // Auto-refresh: odśwież tylko zawartość główną, bez resetowania całej aplikacji.
    let autoRefreshTimer = null;

    function startAutoRefresh() {
        // Legacy auto-refresh replaced by startSmartPolling
        // This function is now a no-op or wrapper for smart polling
        startSmartPolling();
    }

    function stopAutoRefresh() {
        stopSmartPolling();
    }

    // Start immediately
    startAutoRefresh();

    // Pause auto-refresh when the page is hidden to avoid keeping sessions alive via polling
    document.addEventListener('visibilitychange', function () {
        try {
            if (document.hidden) {
                stopAutoRefresh();
            } else {
                // restart with possibly updated interval
                startAutoRefresh();
            }
        } catch (e) { console.warn('visibilitychange handler failed', e); }
    });

    // The beforeunload session beacon has been removed due to unreliable behavior during internal navigation.
    // Inactive sessions will now safely rely on the server-side 40-minute enforceable timeout in middleware.py 
    // and explicit user logouts.

    // Avoid closing session when user clicks a download link or navigates within app intentionally.
    document.addEventListener('click', function (ev) {
        try {
            const a = ev.target.closest && ev.target.closest('a');
            if (!a) return;
            const href = a.getAttribute('href') || '';
            const isDownloadLink = href.indexOf('/admin/ustawienia/backups/download') === 0 || a.hasAttribute('download') || (a.target && a.target !== '_self');
            if (isDownloadLink) {
                window._skipSessionClose = true;
                setTimeout(function () { window._skipSessionClose = false; }, 15000);
            }
        } catch (e) { }
    }, false);

    // Partial reload: fetch current page and replace main content silently
    async function performPartialReload(options) {
        options = options || {};
        try {
            // Check if we should skip reload due to user interaction (modals, search, focus)
            // unless 'force' is specified.
            if (!options.force && typeof shouldSkipAutoRefresh === 'function' && shouldSkipAutoRefresh()) {
                console.info('[partialReload] Skipped due to active user interaction');
                return;
            }

            partialReloadInFlight = true;
            // Save current scroll position before reloading
            const scrollKey = 'system_scroll_pos';
            if (options.preserveScroll !== false) {
                localStorage.setItem(scrollKey, window.scrollY);
            }

            const expandedDetails = captureExpandedDetails();

            // --- Focus and Input value preservation ---
            let focusedElementInfo = null;
            const active = document.activeElement;
            if (active && active.tagName && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT')) {
                let selector = '';
                if (active.id) {
                    selector = '#' + active.id;
                } else if (active.name) {
                    selector = `${active.tagName.toLowerCase()}[name="${active.name}"]`;
                }
                
                if (selector) {
                    focusedElementInfo = {
                        selector: selector,
                        value: active.value,
                        selectionStart: active.selectionStart,
                        selectionEnd: active.selectionEnd
                    };
                }
            }

            const resp = await fetch(window.location.href, { credentials: 'same-origin', cache: 'no-store', headers: { 'Cache-Control': 'no-cache' }, silent: true });
            if (!resp.ok) return;
            const txt = await resp.text();
            const tmp = document.createElement('div'); tmp.innerHTML = txt;
            const newMain = tmp.querySelector('#mainContent');
            const curMain = document.getElementById('mainContent');
            if (newMain && curMain) {
                // Suppress document-level click handlers during partial reload.
                // Some inline scripts executed below may trigger programmatic
                // clicks (e.g. a.click()) which would otherwise bubble and
                // close UI elements like dropdowns. We set a short-lived flag
                // to ignore those synthetic clicks.
                try { window.__partialReloadSuppressClick = true; } catch (e) { }

                // Clear any existing event listeners by replacing entire content
                curMain.innerHTML = newMain.innerHTML;

                // Re-initialize any inline scripts (but NOT external scripts to avoid double-loading)
                newMain.querySelectorAll('script:not([src])').forEach(s => {
                    try {
                        if (s.textContent) {
                            const scriptCode = s.textContent;
                            // Execute in global scope
                            window.eval(scriptCode);
                        }
                    } catch (e) { console.warn('exec partial script failed', e); }
                });

                // Clear suppression shortly after inline scripts executed
                try { setTimeout(function () { try { window.__partialReloadSuppressClick = false; } catch (e) { } }, 300); } catch (e) { }

                // Restore focused element and its value/cursor selection
                if (focusedElementInfo) {
                    try {
                        const restored = curMain.querySelector(focusedElementInfo.selector);
                        if (restored) {
                            restored.value = focusedElementInfo.value;
                            restored.focus();
                            if (typeof restored.setSelectionRange === 'function' && restored.selectionStart !== null) {
                                restored.setSelectionRange(restored.selectionStart, restored.selectionEnd);
                            }
                        }
                    } catch (err) {
                        console.warn('Restore focus failed', err);
                    }
                }

                // Restore scroll position after content update
                setTimeout(() => {
                    if (options.preserveScroll !== false) {
                        const savedPos = localStorage.getItem(scrollKey);
                        if (savedPos) {
                            window.scrollTo(0, parseInt(savedPos));
                            localStorage.removeItem(scrollKey);
                        }
                    }
                    restoreExpandedDetails(expandedDetails);
                }, 50);

                // call update timer function if available
                try {
                    if (window.dashboardPageHelpers && typeof window.dashboardPageHelpers.updatePaletaTimers === 'function') {
                        window.dashboardPageHelpers.updatePaletaTimers();
                    }
                } catch (e) { }

                // Dispatch event so other parts of app know content changed
                try { window.dispatchEvent(new CustomEvent('app:partialReload')); } catch (e) { }

                if (options.source === 'auto-refresh') {
                    showRefreshIndicator('Dane odświeżone');
                }

                console.info('[partialReload] Content updated successfully');
                return;
            }
            console.warn('[partialReload] Could not find #mainContent, refresh skipped');
        } catch (e) {
            console.error('performPartialReload failed', e);
        } finally {
            partialReloadInFlight = false;
        }
    }

    // Expose to window for external scripts
    window.performPartialReload = performPartialReload;

    // AJAX form interception on production dashboards to prevent full-page reload
    document.addEventListener('submit', function (e) {
        const form = e.target;

        // Start zlecenia uses dedicated confirmation/checklist flow and flash messages.
        // Skip generic AJAX interception to avoid swallowing backend validation feedback.
        let actionPath = '';
        try {
            actionPath = new URL(form.action || '', window.location.origin).pathname.toLowerCase();
        } catch (err) {
            actionPath = String(form.getAttribute('action') || '').toLowerCase();
        }
        if (actionPath.includes('/start_zlecenie/')) return;
        
        // Only intercept forms inside #mainContent
        if (!form.closest('#mainContent')) return;
        
        // Don't intercept slide-over, explicitly non-ajax, or custom dashboard-submit forms
        if (form.hasAttribute('data-slide') || form.getAttribute('data-ajax') === 'false' || form.hasAttribute('data-dashboard-submit')) return;
        
        // Only POST forms without a blank/new target
        if (form.method && form.method.toLowerCase() !== 'post') return;
        if (form.target && form.target !== '_self') return;
        
        // Check if we are in a production section
        const section = getCurrentSection().toLowerCase();
        const path = window.location.pathname.toLowerCase();
        const isSupported = (section === 'zasyp' || section === 'workowanie' || section === 'magazyn' || path.includes('/magazyn') || path.includes('/dashboard'));
        if (!isSupported) return;
        
        // Handle confirmation dialogs
        if (form.hasAttribute('data-confirm-msg') || form.hasAttribute('data-confirm')) {
            const msg = form.getAttribute('data-confirm-msg') || form.getAttribute('data-confirm');
            if (!confirm(msg)) {
                e.preventDefault();
                return;
            }
        }
        
        e.preventDefault();
        e.stopPropagation();
        
        const url = form.action || window.location.href;
        const formData = new FormData(form);
        
        // Disable submit buttons to prevent double-clicks
        const submitBtns = form.querySelectorAll('button[type="submit"], input[type="submit"]');
        submitBtns.forEach(btn => btn.disabled = true);
        
        // Fetch silently
        fetch(url, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(async function (response) {
            if (response.status === 401) {
                window.location.reload();
                return;
            }
            
            let json = null;
            const contentType = response.headers.get('content-type') || '';
            if (contentType.indexOf('application/json') !== -1) {
                try {
                    json = await response.json();
                } catch (err) {}
            }
            
            if (json && json.success === false) {
                alert(json.message || 'Błąd operacji');
                submitBtns.forEach(btn => btn.disabled = false);
                return;
            }
            
            // Do a silent partial reload to pull the new data
            await performPartialReload({ force: true, preserveScroll: true, source: 'form-ajax' });
            
            if (typeof window.showToast === 'function') {
                window.showToast('Zapisano!', 'success');
            }
        })
        .catch(function (error) {
            console.error('AJAX submit failed', error);
            alert('Błąd sieci podczas zapisywania');
            submitBtns.forEach(btn => btn.disabled = false);
        });
    }, true); // Use capturing phase to intercept before other handlers

    // --- Global spinner for slow navigations / long fetches ---
    let _spinnerTimer = null;
    let _spinnerVisible = false;

    function _showSpinnerNow() {
        try {
            const el = document.getElementById('globalSpinner');
            if (!el) return;
            el.style.display = 'flex';
            el.classList.add('overlay-active');
            el.setAttribute('aria-hidden', 'false');
            document.body.classList.add('spinner-active');
            _spinnerVisible = true;
        } catch (e) { /* ignore */ }
    }

    let _safetyTimer = null;

    function _showSpinnerNow() {
        if (!_spinnerTimer) return;
        _spinnerVisible = true;
        const el = document.getElementById('globalSpinner');
        if (el) { 
            el.style.display = 'flex'; 
            el.classList.add('overlay-active');
            el.setAttribute('aria-hidden', 'false'); 
        }
        document.body.classList.add('spinner-active');
        
        // Safety timeout: force close after 10s if something hangs
        if (_safetyTimer) clearTimeout(_safetyTimer);
        _safetyTimer = setTimeout(endGlobalSpinnerWatcher, 10000);
    }

    function startGlobalSpinnerWatcher() {
        if (_spinnerTimer) return;
        _spinnerTimer = setTimeout(_showSpinnerNow, 800); // Wait 800ms before showing
    }

    function endGlobalSpinnerWatcher() {
        if (_spinnerTimer) { clearTimeout(_spinnerTimer); _spinnerTimer = null; }
        if (_safetyTimer) { clearTimeout(_safetyTimer); _safetyTimer = null; }
        if (_spinnerVisible) {
            try {
                const el = document.getElementById('globalSpinner');
                if (el) { el.style.display = 'none'; el.classList.remove('overlay-active'); el.setAttribute('aria-hidden', 'true'); }
                document.body.classList.remove('spinner-active');
            } catch (e) { }
            _spinnerVisible = false;
        }
    }

    // Override global fetch to show spinner for long requests
    if (window.fetch) {
        const _origFetch = window.fetch.bind(window);
        // Expose original fetch for explicit background tasks
        window._origFetch = _origFetch;
        
        window.fetch = function () {
            const args = Array.prototype.slice.call(arguments);
            const opts = args[1] || {};
            const isSilent = opts.silent === true;
            
            if (!isSilent) {
                try { startGlobalSpinnerWatcher(); } catch (e) { }
            }
            
            const p = _origFetch.apply(this, arguments);
            
            if (!isSilent) {
                try { 
                    Promise.resolve(p)
                        .finally(() => endGlobalSpinnerWatcher())
                        .catch(() => { /* handled by the caller */ }); 
                } catch (e) { 
                    endGlobalSpinnerWatcher(); 
                }
            }
            return p;
        };
    }

        // Start spinner on form submit (only for full-page POSTs)
        document.addEventListener('submit', function (e) { 
            const form = e.target;
            if (form.hasAttribute('data-slide') || form.hasAttribute('data-ajax')) return;
            try { 
                window._skipSessionClose = true; 
                setTimeout(function () { window._skipSessionClose = false; }, 15000);
                startGlobalSpinnerWatcher(); 
            } catch (e) { } 
        }, true);

        document.addEventListener('click', function (e) {
            try {
                const a = e.target.closest && e.target.closest('a[href]');
                if (!a) return;
                const href = a.getAttribute('href') || '';
                // Skip AJAX, modals, and internal anchors
                if (href.indexOf('#') === 0 || href.indexOf('javascript:') === 0) return;
                if (a.target && a.target !== '' && a.target !== '_self') return;
                if (a.hasAttribute('data-slide') || a.hasAttribute('data-slide-html') || a.classList.contains('btn-action')) return;
                
                startGlobalSpinnerWatcher();
            } catch (e) { }
        }, true);

    // Ensure spinner is removed on page show/load
    window.addEventListener('pageshow', endGlobalSpinnerWatcher);
    window.addEventListener('load', endGlobalSpinnerWatcher);
    document.addEventListener('DOMContentLoaded', function () { try { endGlobalSpinnerWatcher(); } catch (e) { } });

    /* ================= Additional popups: toast, drawer, bottom-sheet, popover, fullscreen, wizard ================= */

    function showToast(message, type, sticky = false, onClick = null) {
        try {
            type = type || 'info';
            const container = document.getElementById('toastContainer') || (function () { const c = document.createElement('div'); c.id = 'toastContainer'; document.body.appendChild(c); return c; })();
            const t = document.createElement('div'); t.className = 'toast toast-' + type; 
            
            if (sticky) {
                t.innerHTML = `<div style="display:flex; justify-content:space-between; align-items:center; gap:12px;">
                    <div style="flex:1;">${message}</div>
                    <button style="background:rgba(255,255,255,0.2);border:none;color:inherit;cursor:pointer;border-radius:4px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:bold;" aria-label="Zamknij">✕</button>
                </div>`;
                t.querySelector('button').addEventListener('click', (e) => {
                    e.stopPropagation();
                    t.classList.remove('show'); 
                    setTimeout(() => t.remove(), 300);
                    if (typeof onClick === 'function') onClick();
                });
            } else {
                t.innerText = message;
            }
            
            container.appendChild(t);
            setTimeout(() => { t.classList.add('show'); }, 10);
            
            if (!sticky) {
                setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 3500);
            }
        } catch (e) { console.warn('showToast', e); }
    }

    function showDrawer(html, opts) {
        opts = opts || {};
        const side = opts.side === 'left' ? 'left' : 'right';
        let bd = document.querySelector('.slide-over-backdrop'); if (!bd) { bd = document.createElement('div'); bd.className = 'slide-over-backdrop'; document.body.appendChild(bd); }
        const d = document.createElement('div'); d.className = 'drawer drawer-' + side; d.innerHTML = `<div class="drawer-body">${html}</div><button class="drawer-close" aria-label="Zamknij">✕</button>`;
        document.body.appendChild(d); document.body.classList.add('slide-over-open'); if (bd) bd.classList.add('show');
        requestAnimationFrame(() => d.classList.add('open'));
        d.querySelector('.drawer-close').addEventListener('click', () => { d.classList.remove('open'); if (bd) bd.classList.remove('show'); setTimeout(() => { d.remove(); if (bd && !document.querySelector('.drawer')) bd.remove(); document.body.classList.remove('slide-over-open'); }, 260); });
        if (bd) bd.addEventListener('click', () => { d.querySelector('.drawer-close').click(); });
    }

    function showBottomSheet(html, opts) {
        opts = opts || {};
        let bd = document.querySelector('.slide-over-backdrop'); if (!bd) { bd = document.createElement('div'); bd.className = 'slide-over-backdrop'; document.body.appendChild(bd); }
        const s = document.createElement('div'); s.className = 'bottom-sheet'; s.innerHTML = `<div class="bs-handle"></div><div class="bs-body">${html}</div><button class="bs-close" aria-label="Zamknij">Zamknij</button>`;
        document.body.appendChild(s); document.body.classList.add('slide-over-open'); if (bd) bd.classList.add('show'); requestAnimationFrame(() => s.classList.add('open'));
        s.querySelector('.bs-close').addEventListener('click', () => { s.classList.remove('open'); if (bd) bd.classList.remove('show'); setTimeout(() => { s.remove(); if (bd && !document.querySelector('.bottom-sheet')) bd.remove(); document.body.classList.remove('slide-over-open'); }, 260); });
        if (bd) bd.addEventListener('click', () => s.querySelector('.bs-close').click());
    }

    function showPopover(el, html) {
        try {
            // el: DOM element or selector
            const target = (typeof el === 'string') ? document.querySelector(el) : el;
            if (!target) return;
            const p = document.createElement('div'); p.className = 'mini-popover'; p.innerHTML = html + '<button class="mini-close">✕</button>';
            document.body.appendChild(p);
            const r = target.getBoundingClientRect();
            p.style.top = (r.bottom + window.scrollY + 8) + 'px';
            p.style.left = (r.left + window.scrollX) + 'px';
            requestAnimationFrame(() => p.classList.add('show'));
            p.querySelector('.mini-close').addEventListener('click', () => p.remove());
            setTimeout(() => { document.addEventListener('click', function _f(e) { if (!p.contains(e.target) && e.target !== target) { p.remove(); document.removeEventListener('click', _f); } }); }, 10);
        } catch (e) { console.warn('showPopover', e); }
    }

    function showFullscreenModal(html) {
        const bd = document.createElement('div'); bd.className = 'slide-over-backdrop'; document.body.appendChild(bd);
        const f = document.createElement('div'); f.className = 'fullscreen-modal'; f.innerHTML = `<div class='fs-body'>${html}</div><button class='fs-close'>Zamknij</button>`;
        document.body.appendChild(f); document.body.classList.add('slide-over-open'); requestAnimationFrame(() => f.classList.add('open')); bd.classList.add('show');
        f.querySelector('.fs-close').addEventListener('click', () => { f.classList.remove('open'); bd.classList.remove('show'); setTimeout(() => { f.remove(); bd.remove(); document.body.classList.remove('slide-over-open'); }, 300); });
    }

    function showWizard(steps) {
        // steps: array of HTML strings
        let idx = 0;
        const bd = document.createElement('div'); bd.className = 'slide-over-backdrop'; document.body.appendChild(bd);
        const w = document.createElement('div'); w.className = 'wizard-modal'; w.innerHTML = `<div class='wiz-body'></div><div class='wiz-actions'><button class='wiz-prev'>Wstecz</button><button class='wiz-next'>Dalej</button></div>`;
        document.body.appendChild(w); document.body.classList.add('slide-over-open'); bd.classList.add('show');
        function render() { w.querySelector('.wiz-body').innerHTML = steps[idx] || ''; w.querySelector('.wiz-prev').disabled = idx === 0; w.querySelector('.wiz-next').innerText = (idx === steps.length - 1) ? 'Zakończ' : 'Dalej'; }
        w.querySelector('.wiz-prev').addEventListener('click', () => { if (idx > 0) { idx--; render(); } });
        w.querySelector('.wiz-next').addEventListener('click', () => { if (idx < steps.length - 1) { idx++; render(); } else { w.remove(); bd.remove(); document.body.classList.remove('slide-over-open'); } });
        render();
    }

    // expose
    window.showToast = showToast;
    window.showDrawer = showDrawer;
    window.showBottomSheet = showBottomSheet;
    window.showPopover = showPopover;
    window.showFullscreenModal = showFullscreenModal;
    window.showWizard = showWizard;

    // --- Preprint UI: add button and modal for reserve/reprint flow ---
    (function initPreprintUI() {
        function isPreprintContextAllowed() {
            const cfg = document.getElementById('dashboard-config');
            if (!cfg) return false;
            const section = String(cfg.getAttribute('data-sekcja') || '').trim().toUpperCase();
            const linia = String(cfg.getAttribute('data-linia') || '').trim().toUpperCase();
            const role = String(cfg.getAttribute('data-current-role') || '').trim().toLowerCase();
            const allowedRoles = ['magazynier', 'lider', 'admin', 'masteradmin', 'zarzad'];
            return section === 'MAGAZYN' && (linia === 'PSD' || linia === 'AGRO') && allowedRoles.includes(role);
        }

        function bindPreprintButton(btn) {
            if (!btn || btn.dataset.preprintBound === '1') return;
            if (!isPreprintContextAllowed()) return;
            btn.dataset.preprintBound = '1';
            btn.setAttribute('type', 'button');
            btn.addEventListener('click', openPreprintModal);
        }

        function ensureButton() {
            const existingBtn = document.getElementById('preprint_pallets_btn');
            if (!isPreprintContextAllowed()) {
                if (existingBtn) {
                    existingBtn.remove();
                }
                return;
            }

            if (existingBtn) {
                bindPreprintButton(existingBtn);
                return;
            }

            const main = document.querySelector('.logistyka-container') || document.getElementById('mainContent') || document.querySelector('.magazyn-container') || document.querySelector('.warehouse-page');
            if (!main) return;
            const headerRow = main.querySelector('div[style*="display: flex; justify-content: space-between"]') || main.querySelector('.page-header') || main.querySelector('header') || main.querySelector('.page-toolbar') || main.querySelector('.toolbar');
            if (!headerRow) return;

            const btn = document.createElement('button');
            btn.id = 'preprint_pallets_btn';
            btn.className = 'btn-action';
            btn.style.background = '#0f172a';
            btn.style.color = '#fff';
            btn.style.borderRadius = '8px';
            btn.style.padding = '8px 12px';
            btn.style.fontWeight = '800';
            btn.style.marginLeft = '8px';
            btn.textContent = 'Pre-druk etykiet';
            headerRow.appendChild(btn);
            bindPreprintButton(btn);
        }

        function boot() {
            try {
                ensureButton();
            } catch (e) {
                console.warn('initPreprintUI failed', e);
            }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', boot);
        } else {
            boot();
        }

        async function loadPreprintPrinters(selectEl, liniaValue) {
            if (!selectEl) return;

            const current = (selectEl.value || 'auto').trim();
            selectEl.innerHTML = '<option value="auto">Automatycznie (domyslna)</option>';

            try {
                const linia = String(liniaValue || 'PSD').toUpperCase();
                const resp = await fetch('/magazyn-dostawy/api/active-printers?linia=' + encodeURIComponent(linia), {
                    credentials: 'same-origin'
                });

                if (resp.status === 401) {
                    window.location.href = '/login';
                    return;
                }

                let j = null;
                try { j = await resp.json(); } catch (e) { j = null; }
                const printers = (j && j.success && Array.isArray(j.printers)) ? j.printers : [];

                for (const p of printers) {
                    const option = document.createElement('option');
                    const selectionValue = String(
                        p.selection_value ||
                        ((p.id !== null && p.id !== undefined) ? ('db:' + p.id) : (p.ip ? ('net:' + p.ip) : 'auto'))
                    );
                    option.value = selectionValue;
                    if (p.id !== null && p.id !== undefined) {
                        option.dataset.printerId = String(p.id);
                    }
                    if (p.ip) {
                        option.dataset.printerIp = String(p.ip);
                    }
                    if (p.nazwa) {
                        option.dataset.printerName = String(p.nazwa);
                    }
                    const ipTxt = p.ip ? ` (${p.ip})` : '';
                    const locTxt = p.lokalizacja ? ` - ${p.lokalizacja}` : '';
                    const sourceTxt = (p.source === 'network') ? ' [siec]' : '';
                    option.textContent = `${p.nazwa || 'Drukarka'}${ipTxt}${locTxt}${sourceTxt}`;
                    selectEl.appendChild(option);
                }

                const hasCurrent = Array.from(selectEl.options || []).some(opt => opt.value === current);
                if (current && (current === 'auto' || hasCurrent)) {
                    selectEl.value = current;
                }
            } catch (e) {
                console.warn('loadPreprintPrinters failed', e);
            }
        }

        function openPreprintModal() {
            const html = `
                <div style="display:flex;flex-direction:column;gap:10px;">
                  <label>Liczba etykiet:</label>
                  <input id="preprint_count" type="number" min="1" value="1" style="width:100%;padding:8px;border:1px solid #e2e8f0;border-radius:8px;">
                  <label>Linia:</label>
                  <select id="preprint_linia" style="width:100%;padding:8px;border:1px solid #e2e8f0;border-radius:8px;"><option value="PSD">PSD</option><option value="AGRO">AGRO</option></select>
                  <label>Drukarka:</label>
                  <select id="preprint_printer" style="width:100%;padding:8px;border:1px solid #e2e8f0;border-radius:8px;"><option value="auto">Automatycznie (domyslna)</option></select>
                  <div style="font-size:12px;color:#475569;line-height:1.35;">Wybierz drukarke sieciowa lub pozostaw automatyczna.</div>
                  <label style="display:flex;gap:8px;align-items:flex-start;">
                    <input id="preprint_existing_only" type="checkbox" style="margin-top:2px;">
                                        <span>Drukuj dla już istniejących palet (bez rezerwacji nowych)</span>
                  </label>
                  <label style="display:flex;gap:8px;align-items:flex-start;">
                    <input id="preprint_only_pending" type="checkbox" checked style="margin-top:2px;">
                    <span>Tylko palety oczekujące (do zatwierdzenia)</span>
                  </label>
                                    <div style="font-size:12px;color:#475569;line-height:1.35;">Gdy opcja powyzej jest odznaczona, system rezerwuje etykiety dla przyszlych palet.</div>
                  <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:8px;">
                    <button class="btn-action" id="preprint_cancel" style="background:#fff;border:1px solid #cbd5e1;color:#1e293b;">Anuluj</button>
                    <button class="btn-action" id="preprint_confirm" style="background:#10b981;color:#fff;">Przygotuj etykiety</button>
                  </div>
                  <div id="preprint_result" style="margin-top:8px;max-height:40vh;overflow:auto;"></div>
                </div>`;

            const inst = createQuickPopup('Predruk etykiet', html);
            setTimeout(() => {
                const cancel = document.getElementById('preprint_cancel');
                const confirm = document.getElementById('preprint_confirm');
                const liniaSelect = document.getElementById('preprint_linia');
                const printerSelect = document.getElementById('preprint_printer');
                const existingOnly = document.getElementById('preprint_existing_only');
                const onlyPending = document.getElementById('preprint_only_pending');

                const refreshModeUI = function() {
                    const existingMode = !!(existingOnly && existingOnly.checked);
                    if (confirm) confirm.textContent = existingMode ? 'Pobierz etykiety' : 'Zarezerwuj etykiety';
                    if (onlyPending) onlyPending.disabled = !existingMode;
                };

                if (cancel) cancel.addEventListener('click', () => inst.close());
                if (confirm) confirm.addEventListener('click', () => doPreprint(inst));
                if (existingOnly) existingOnly.addEventListener('change', refreshModeUI);

                if (liniaSelect && printerSelect) {
                    const loadForSelectedLine = function() {
                        loadPreprintPrinters(printerSelect, liniaSelect.value);
                    };
                    liniaSelect.addEventListener('change', loadForSelectedLine);
                    loadForSelectedLine();
                }

                refreshModeUI();
            }, 50);
        }

        async function doPreprint(inst) {
            let confirmBtn = null;
            let confirmBtnPrevText = '';
            let existingModeForBtn = false;
            try {
                const countEl = document.getElementById('preprint_count');
                const liniaEl = document.getElementById('preprint_linia');
                const printerEl = document.getElementById('preprint_printer');
                const existingOnlyEl = document.getElementById('preprint_existing_only');
                const onlyPendingEl = document.getElementById('preprint_only_pending');
                const resultEl = document.getElementById('preprint_result');

                const count = parseInt((countEl && countEl.value) || '0', 10) || 0;
                const linia = ((liniaEl && liniaEl.value) || 'PSD').toUpperCase();
                const selectedPrinterValue = String((printerEl && printerEl.value) || 'auto').trim();
                const selectedPrinterOption = (printerEl && printerEl.selectedOptions && printerEl.selectedOptions.length)
                    ? printerEl.selectedOptions[0]
                    : null;
                let selectedPrinterId = selectedPrinterOption && selectedPrinterOption.dataset
                    ? String(selectedPrinterOption.dataset.printerId || '').trim()
                    : '';
                let selectedPrinterIp = selectedPrinterOption && selectedPrinterOption.dataset
                    ? String(selectedPrinterOption.dataset.printerIp || '').trim()
                    : '';
                let selectedPrinterName = selectedPrinterOption && selectedPrinterOption.dataset
                    ? String(selectedPrinterOption.dataset.printerName || '').trim()
                    : '';

                if (!selectedPrinterId && selectedPrinterValue.startsWith('db:')) {
                    selectedPrinterId = selectedPrinterValue.slice(3).trim();
                }
                if (!selectedPrinterIp && selectedPrinterValue.startsWith('net:')) {
                    selectedPrinterIp = selectedPrinterValue.slice(4).trim();
                }
                const existingOnly = !!(existingOnlyEl && existingOnlyEl.checked);
                const onlyPending = !!(onlyPendingEl && onlyPendingEl.checked);
                existingModeForBtn = existingOnly;

                if (count <= 0) {
                    showToast('Liczba musi być >= 1', 'warning');
                    return;
                }

                confirmBtn = document.getElementById('preprint_confirm');
                if (confirmBtn) {
                    confirmBtnPrevText = confirmBtn.textContent || '';
                    confirmBtn.disabled = true;
                    confirmBtn.textContent = existingOnly ? 'Pobieram palety...' : 'Rezerwuję palety...';
                }

                resultEl.innerHTML = existingOnly
                    ? '<div style="padding:10px 12px;border:1px solid #dbeafe;background:#eff6ff;color:#1e3a8a;border-radius:8px;font-size:13px;"><strong>Pobieram istniejące palety...</strong><div style="margin-top:4px;color:#334155;">To może potrwać kilka sekund. Proszę czekać.</div></div>'
                    : '<div style="padding:10px 12px;border:1px solid #dcfce7;background:#f0fdf4;color:#166534;border-radius:8px;font-size:13px;"><strong>Trwa rezerwacja palet...</strong><div style="margin-top:4px;color:#334155;">Proszę czekać na zakończenie operacji.</div></div>';

                const params = {
                    plan_id: (window.currentPlanId || ''),
                    count: count,
                    linia: linia,
                    existing_only: existingOnly,
                    only_pending: onlyPending,
                };

                const selectedDateEl = document.getElementById('current-date-iso');
                if (selectedDateEl && selectedDateEl.value) {
                    params.date = selectedDateEl.value;
                }

                if (!params.plan_id) {
                    const u = new URL(window.location.href);
                    params.plan_id = u.searchParams.get('plan_id') || u.searchParams.get('id') || '';
                }

                const resp = await fetch('/magazyn-dostawy/preprint', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(params)
                });

                if (resp.status === 401) {
                    window.location.href = '/login';
                    return;
                }

                let j = null;
                try { j = await resp.json(); } catch (e) { j = null; }

                if (resp.status >= 500 || (j && j.success === false && String(j.message || '').toLowerCase().indexOf('method not allowed') !== -1)) {
                    try {
                        const qsData = {
                            count: String(params.count),
                            linia: params.linia,
                            existing_only: String(!!params.existing_only),
                            only_pending: String(!!params.only_pending)
                        };
                        if (params.plan_id) qsData.plan_id = String(params.plan_id);
                        if (params.date) qsData.date = String(params.date);
                        const qs = new URLSearchParams(qsData);
                        const g = await fetch('/magazyn-dostawy/preprint?' + qs.toString(), { method: 'GET', credentials: 'same-origin' });
                        try { j = await g.json(); } catch (e) { j = null; }
                    } catch (e) {
                        // keep primary error payload
                    }
                }

                if (!j || j.success !== true) {
                    resultEl.innerHTML = '<div style="color:#c81e1e;">Błąd: ' + (j && j.message ? String(j.message) : 'Nieznany błąd') + '</div>';
                    return;
                }

                const modeLabel = (j.mode === 'existing')
                    ? 'Znalezione palety do wydruku:'
                    : ((j.mode === 'mixed') ? 'Znalezione palety + nowe rezerwacje:' : 'Utworzone rezerwacje:');
                if (Array.isArray(j.created) && j.created.length) {
                    const countersInfo =
                        (typeof j.requested_count === 'number')
                            ? `<div style="font-size:12px;color:#475569;margin-bottom:6px;">Zadane: ${j.requested_count}, znalezione: ${j.existing_count || 0}, wygenerowane: ${j.generated_count || 0}</div>`
                            : '';
                    const actionBar =
                        '<div style="display:flex;justify-content:flex-end;gap:8px;margin:8px 0 10px 0;">' +
                        '<button id="preprint_print_all" class="btn-action" style="background:#0b3a2a;color:#fff;border-radius:6px;padding:6px 10px;">Drukuj wszystko (drukarka)</button>' +
                        '</div>';
                    const list = j.created.map((it, index) => {
                        const seq = it.kolejnosc || (index + 1);
                        const orderNameRaw = String(it.nazwa_zlecenia || it.plan_name || '').trim();
                        const orderName = orderNameRaw ? escapeHtml(orderNameRaw) : '';
                        const orderInfo = orderName ? ` <span style="color:#475569;">- zlecenie: ${orderName}</span>` : '';
                        const sourceInfo = (it.source === 'existing')
                            ? ' <span style="font-size:11px;color:#065f46;background:#d1fae5;padding:1px 6px;border-radius:999px;">istniejaca</span>'
                            : ((it.source === 'reserve')
                                ? ' <span style="font-size:11px;color:#9a3412;background:#ffedd5;padding:1px 6px;border-radius:999px;">rezerwacja</span>'
                                : '');
                        const palletLabel = escapeHtml(String(it.nr_palety || it.id || ''));
                        return `<div id="preprint-row-${it.id}" style="padding:8px;border-bottom:1px solid #f1f5f9;display:flex;justify-content:space-between;align-items:center;"><div><strong>${palletLabel}</strong> - nr LP: ${seq}${orderInfo}${sourceInfo}</div><div style="display:flex;align-items:center;gap:8px;"><small id="preprint-status-${it.id}" style="color:#64748b;"></small><button class="btn-action" data-id="${it.id}" style="background:#0f172a;color:#fff;border-radius:6px;padding:6px 8px;">Drukuj</button></div></div>`;
                    }).join('');
                    const warningInfo = j.warning ? `<div style="font-size:12px;color:#b45309;margin-bottom:8px;">${String(j.warning)}</div>` : '';
                    resultEl.innerHTML = '<div style="font-weight:700;margin-bottom:8px;">' + modeLabel + '</div>' + countersInfo + warningInfo + actionBar + list + '<div id="preprint_bulk_status" style="margin-top:10px;font-size:12px;color:#334155;"></div>';

                    async function printDirect(id, printerMeta) {
                        const endpoint = `/drukuj_etykiete_zpl/${encodeURIComponent(id)}?linia=${encodeURIComponent(linia)}`;
                        const payload = {};
                        if (printerMeta && printerMeta.id) {
                            payload.printer_id = printerMeta.id;
                        } else if (printerMeta && printerMeta.ip) {
                            payload.printer_ip = printerMeta.ip;
                            if (printerMeta.name) {
                                payload.printer_name = printerMeta.name;
                            }
                        }
                        const r = await fetch(endpoint, {
                            method: 'POST',
                            credentials: 'same-origin',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        if (r.status === 401) {
                            window.location.href = '/login';
                            return { ok: false, message: 'Brak autoryzacji' };
                        }
                        let pj = null;
                        try { pj = await r.json(); } catch (e) { pj = null; }
                        const ok = !!(r.ok && pj && pj.success === true);
                        return {
                            ok: ok,
                            message: (pj && pj.message) ? String(pj.message) : (ok ? 'OK' : 'Błąd druku'),
                            printerName: (pj && pj.printer_name) ? String(pj.printer_name) : ''
                        };
                    }

                    resultEl.querySelectorAll('button[data-id]').forEach(b => b.addEventListener('click', async function (ev) {
                        const id = ev.currentTarget.getAttribute('data-id');
                        const st = document.getElementById('preprint-status-' + id);
                        if (st) {
                            st.textContent = 'drukowanie...';
                            st.style.color = '#64748b';
                        }

                        try {
                            const res = await printDirect(id, {
                                id: selectedPrinterId,
                                ip: selectedPrinterIp,
                                name: selectedPrinterName,
                            });
                            if (res.ok) {
                                if (st) {
                                    st.textContent = 'wydrukowano';
                                    st.style.color = '#047857';
                                    if (res.message) st.title = res.message;
                                }
                            } else {
                                if (st) {
                                    st.textContent = 'blad';
                                    st.style.color = '#b91c1c';
                                    st.title = res.message || '';
                                }
                                showToast('Błąd druku: ' + (res.message || 'Nieznany błąd'), 'danger');
                            }
                        } catch (e) {
                            if (st) {
                                st.textContent = 'blad';
                                st.style.color = '#b91c1c';
                            }
                            showToast('Błąd drukowania etykiety', 'danger');
                        }
                    }));

                    const printAllBtn = document.getElementById('preprint_print_all');
                    const bulkStatus = document.getElementById('preprint_bulk_status');
                    if (printAllBtn && bulkStatus) {
                        printAllBtn.addEventListener('click', async function () {
                            if (printAllBtn.dataset.busy === '1') return;
                            printAllBtn.dataset.busy = '1';
                            printAllBtn.disabled = true;

                            let okCount = 0;
                            let failCount = 0;
                            for (const item of j.created) {
                                const itemId = item && item.id;
                                if (!itemId) {
                                    failCount += 1;
                                    continue;
                                }

                                const st = document.getElementById('preprint-status-' + itemId);
                                if (st) {
                                    st.textContent = 'drukowanie...';
                                    st.style.color = '#64748b';
                                }

                                try {
                                    const res = await printDirect(itemId, {
                                        id: selectedPrinterId,
                                        ip: selectedPrinterIp,
                                        name: selectedPrinterName,
                                    });
                                    if (res.ok) {
                                        okCount += 1;
                                        if (st) {
                                            st.textContent = 'wydrukowano';
                                            st.style.color = '#047857';
                                            if (res.message) st.title = res.message;
                                        }
                                    } else {
                                        failCount += 1;
                                        if (st) {
                                            st.textContent = 'blad';
                                            st.style.color = '#b91c1c';
                                            st.title = res.message || '';
                                        }
                                    }
                                } catch (e) {
                                    failCount += 1;
                                    if (st) {
                                        st.textContent = 'blad';
                                        st.style.color = '#b91c1c';
                                    }
                                }
                            }

                            bulkStatus.textContent = `Druk zakonczony. Sukces: ${okCount}, bledy: ${failCount}.`;
                            printAllBtn.dataset.busy = '0';
                            printAllBtn.disabled = false;
                        });
                    }
                } else {
                    resultEl.innerHTML = (j.mode === 'existing')
                        ? '<div>Brak palet spełniających kryteria.</div>'
                        : '<div>Brak utworzonych rezerwacji.</div>';
                }
            } catch (e) {
                console.error('preprint failed', e);
                showToast('Błąd sieci podczas predruku', 'danger');
            } finally {
                if (confirmBtn) {
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = confirmBtnPrevText || (existingModeForBtn ? 'Pobierz i drukuj' : 'Zarezerwuj i drukuj');
                }
            }
        }
    })();

    /* ================= Global quick popup helper ================= */
    function createQuickPopup(title, html, opts) {
        opts = opts || {};
        
        // Header icon/color based on detected type
        var comb = (title || '') + ' ' + (String(html || ''));
        var isErr = /bł[ae]d|error|blad|fail|nie uda|✗/gi.test(comb);
        var isWarn = (!isErr && /uwaga|warning|ostrzeżenie|⚠️/gi.test(comb));
        var isSuccess = (!isErr && !isWarn && /sukces|success|zapisano|udana|pomoc|✓|ok/gi.test(comb));

        var iconSvg = '';
        if (isErr) {
            iconSvg = '<svg class="qp-header-icon" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="width:24px;height:24px;flex-shrink:0;"><circle cx="12" cy="12" r="10" fill="#fee2e2" stroke="#fca5a5" stroke-width="1.5"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
        } else if (isWarn) {
            iconSvg = '<svg class="qp-header-icon" viewBox="0 0 24 24" fill="none" stroke="#d97706" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:24px;height:24px;flex-shrink:0;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" fill="#fef3c7" stroke="#fcd34d" stroke-width="1.5"></path><line x1="12" y1="9" x2="12" y2="13" stroke="#d97706" stroke-width="2.5"></line><line x1="12" y1="17" x2="12.01" y2="17" stroke="#d97706" stroke-width="3" stroke-linecap="round"></line></svg>';
        } else if (isSuccess) {
            iconSvg = '<svg class="qp-header-icon" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="width:24px;height:24px;flex-shrink:0;"><circle cx="12" cy="12" r="10" fill="#d1fae5" stroke="#a7f3d0" stroke-width="1.5"></circle><polyline points="16 9 11 14 8 11"></polyline></svg>';
        } else {
            iconSvg = '<svg class="qp-header-icon" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="width:24px;height:24px;flex-shrink:0;"><circle cx="12" cy="12" r="10" fill="#dbeafe" stroke="#bfdbfe" stroke-width="1.5"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8" stroke-width="3"></line></svg>';
        }

        // If plain-text content is passed (no HTML tags), render it using
        // the styled popup templates so messages look consistent.
        try {
            var raw = String(html || '');
            if (!/[<][a-zA-Z]/.test(raw)) {
                var combined = (title || '') + ' ' + raw;
                var inferredType = isErr ? 'error' : (isWarn ? 'warning' : 'info');
                html = createPopupContent(inferredType === 'info' ? 'success' : inferredType, raw);
            }
        } catch (e) { /* ignore and use provided html */ }

        // Reuse existing global quick popup elements if present to avoid duplicates
        const existingBd = document.getElementById('quickBackdrop') || document.querySelector('.quick-backdrop');
        const existingM = document.getElementById('quickPopup') || document.querySelector('.quick-popup');
        if (existingBd && existingM) {
            try {
                const headerTitle = existingM.querySelector('.header-title') || existingM.querySelector('.qp-header strong');
                if (headerTitle) headerTitle.textContent = title || '';
                
                const iconContainer = existingM.querySelector('.qp-icon-container') || existingM.querySelector('.qp-header-left');
                if (iconContainer) {
                    if (iconContainer.classList.contains('qp-icon-container')) {
                        iconContainer.innerHTML = iconSvg;
                    }
                }
                
                const body = document.getElementById('quickPopupBody') || existingM.querySelector('.qp-body');
                if (body) {
                    body.innerHTML = html || '';
                    body.querySelectorAll('script').forEach(s => {
                        try {
                            if (s.src) {
                                const sc = document.createElement('script'); sc.src = s.src; sc.async = false; document.body.appendChild(sc);
                            } else {
                                window.eval(s.textContent);
                            }
                        } catch (e) {
                            console.warn('exec quick-popup script failed', e);
                        }
                    });
                }
                existingBd.style.display = 'block';
                existingBd.classList.add('show');
                existingM.style.display = 'block';
                document.body.classList.add('slide-over-open');
                setTimeout(() => existingM.classList.add('open'), 10);
                
                // Set wide class dynamically if containing large elements
                var hasWideContent = /[<](form|table|grid|iframe)/gi.test(String(html || ''));
                var isDosypkaPopup = /dosypka-popup-container/i.test(String(html || ''));
                if (hasWideContent) {
                    existingM.classList.add('qp-wide');
                } else {
                    existingM.classList.remove('qp-wide');
                }
                if (isDosypkaPopup) {
                    existingM.classList.add('qp-dosypka-full');
                } else {
                    existingM.classList.remove('qp-dosypka-full');
                }

                // Initialize component initializers after content is updated
                setTimeout(() => {
                    try {
                        if (typeof window.initDosypkiList === 'function') {
                            try { window.initDosypkiList(existingM); } catch (e) { console.warn('initDosypkiList failed', e); }
                        }
                    } catch (e) { }
                }, 10);
            } catch (e) { console.warn('reuse quick-popup failed', e); }
            return { close: function () { try { if (typeof closeQuickPopup === 'function') closeQuickPopup(); else { existingM.classList.remove('open'); existingBd.classList.remove('show'); setTimeout(() => { existingM.style.display = 'none'; existingBd.style.display = 'none'; document.body.classList.remove('slide-over-open'); }, 260); } } catch (e) { } }, element: existingM };
        }

        const bd = document.createElement('div'); bd.className = 'quick-backdrop'; bd.id = 'quickBackdrop';
        const m = document.createElement('div'); m.className = 'quick-popup'; m.id = 'quickPopup';
        
        // Set dynamic width class
        var hasWideContent = /[<](form|table|grid|iframe)/gi.test(String(html || ''));
        var isDosypkaPopup = /dosypka-popup-container/i.test(String(html || ''));
        if (hasWideContent) {
            m.classList.add('qp-wide');
        }
        if (isDosypkaPopup) {
            m.classList.add('qp-dosypka-full');
        }

        var headerHtml = '<div class="qp-header" role="dialog" aria-modal="true">'
            + '<div class="qp-header-left" style="display:flex;align-items:center;gap:12px;">'
            + '<div class="qp-icon-container" style="display:flex;align-items:center;justify-content:center;">' + iconSvg + '</div>'
            + '<div class="header-title"><strong>' + (title || '') + '</strong></div>'
            + '</div>'
            + '<button class="qp-close" aria-label="Zamknij">✕</button>'
            + '</div>';

        // Inject lightweight, scoped styles to improve visual appearance
        var scopedStyle = '<style>'
            + '.quick-backdrop{position:fixed;inset:0;background:rgba(15,23,42,0.4);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);z-index:30001;opacity:0;transition:opacity .25s ease;pointer-events:none}.quick-backdrop.show{opacity:1;pointer-events:auto}'
            + '.quick-popup{position:fixed;left:50%;top:50%;transform:translate(-50%, -50%) scale(0.95);z-index:30002;max-width:600px;width:calc(100% - 48px);background:#fff;border-radius:20px;box-shadow:0 25px 50px -12px rgba(15,23,42,0.25);overflow:hidden;display:block;opacity:0;transition:transform .3s cubic-bezier(0.34, 1.56, 0.64, 1), opacity .3s ease;border:1px solid rgba(15,23,42,0.08);pointer-events:none;font-family:\'Inter\', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif}'
            + '.quick-popup.qp-wide{max-width:920px}'
            + '.quick-popup.open{transform:translate(-50%, -50%) scale(1);opacity:1;pointer-events:auto}'
            + '.qp-header{display:flex;justify-content:space-between;align-items:center;padding:20px 24px;border-bottom:1px solid #f1f5f9;background:#fff}'
            + '.qp-header .header-title{font-size:18px;font-weight:700;color:#0f172a;letter-spacing:-0.02em;font-family:inherit}'
            + '.qp-header .qp-close{width:32px;height:32px;display:grid;place-items:center;border-radius:8px;color:#94a3b8;transition:all 0.2s ease;background:#f8fafc;border:none;cursor:pointer}'
            + '.qp-header .qp-close:hover{background:#fee2e2;color:#ef4444;transform:rotate(90deg)}'
            + '.qp-body{padding:24px;max-height:70vh;overflow:auto;font-size:15px;line-height:1.6;color:#334155;background:#fff;font-family:inherit;scrollbar-width:thin;scrollbar-color:#e2e8f0 transparent}'
            + '.qp-body::-webkit-scrollbar{width:6px}.qp-body::-webkit-scrollbar-thumb{background:#e2e8f0;border-radius:10px}'
            + '.qp-body .modern-table{width:100%;border-collapse:separate;border-spacing:0;margin-top:12px;border-radius:12px;overflow:hidden;border:1px solid #f1f5f9}'
            + '.qp-body .modern-table th{background:#f8fafc;color:#64748b;padding:12px 16px;border-bottom:2px solid #f1f5f9;text-align:left;font-weight:700;font-size:13px;text-transform:uppercase;letter-spacing:0.05em}'
            + '.qp-body .modern-table td{padding:14px 16px;border-bottom:1px solid #f1f5f9;color:#0f172a}'
            + '.qp-body tr:last-child td{border-bottom:none}'
            + '.qp-body .badge{display:inline-flex;align-items:center;padding:5px 12px;border-radius:99px;background:#f1f5f9;color:#475569;font-weight:700;font-size:12px;margin:4px 4px 4px 0;white-space:nowrap}'
            + '.qp-body input, .qp-body select, .qp-body textarea { color: #0f172a !important; caret-color: #0f172a !important; background: #fff !important; border: 1px solid #e2e8f0 !important; border-radius: 8px !important; padding: 8px 12px !important; font-family: inherit !important; }'
            + '.qp-body input:focus, .qp-body select:focus, .qp-body textarea:focus { border-color: #3b82f6 !important; outline: none !important; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important; }'
            + '.qp-actions{display:flex;gap:12px;justify-content:flex-end;margin-top:24px}'
            + '.btn-action{padding:10px 20px;border-radius:10px;font-weight:700;font-size:14px;cursor:pointer;transition:all 0.2s;border:none;font-family:inherit}'
            + '</style>';

        m.innerHTML = scopedStyle + headerHtml + '<div id="quickPopupBody" class="qp-body">' + (html || '') + '</div>';

        // Ensure popup/backdrop are appended to top-level root before evaluating scripts
        try {
            (document.documentElement || document.body).appendChild(bd);
            (document.documentElement || document.body).appendChild(m);
        } catch (e) { document.body.appendChild(bd); document.body.appendChild(m); }

        // Execute inline scripts inside the modal content now that it is in the DOM
        m.querySelectorAll('script').forEach(s => {
            try {
                if (s.src) {
                    const sc = document.createElement('script'); sc.src = s.src; sc.async = false; document.body.appendChild(sc);
                } else {
                    window.eval(s.textContent);
                }
            } catch (e) {
                console.warn('exec quick-popup script failed', e);
            }
        });

        // Positioning is controlled via CSS; avoid inline z-index to prevent conflicts
        requestAnimationFrame(() => { bd.classList.add('show'); m.classList.add('open'); document.body.classList.add('slide-over-open'); });
        // Initialize any known component initializers for injected content
        // Delay to ensure DOM elements are fully rendered and accessible by initializers
        setTimeout(() => {
            try {
                if (typeof window.initDosypkiList === 'function') {
                    try { window.initDosypkiList(m); } catch (e) { console.warn('initDosypkiList failed', e); }
                }
            } catch (e) { }
        }, 10);
        // Ensure popup body is scrollable and tables are visible (fix cases where content exists but is not shown)
        try {
            const qpBody = m.querySelector('.qp-body');
            if (qpBody) {
                const mobileMaxHeight = 'calc(100vh - 88px)';
                const desktopMaxHeight = '60vh';
                qpBody.style.maxHeight = qpBody.style.maxHeight || (window.innerWidth <= 768 ? mobileMaxHeight : desktopMaxHeight);
                qpBody.style.overflow = qpBody.style.overflow || 'auto';
            }
            const tables = m.querySelectorAll('table');
            tables.forEach((t, idx) => {
                const compStyle = getComputedStyle(t);
                if (compStyle.display === 'none') t.style.display = 'table';
            });
        } catch (e) { console.warn('quick-popup style init failed', e); }
        function remove() { m.classList.remove('open'); bd.classList.remove('show'); setTimeout(() => { try { m.remove(); bd.remove(); document.body.classList.remove('slide-over-open'); } catch (e) { } }, 260); }
        bd.addEventListener('click', remove);
        const closeBtn = m.querySelector('.qp-close'); if (closeBtn) closeBtn.addEventListener('click', remove);
        // Rebind any forms inside quick popup to submit via fetch (AJAX) so page doesn't fully navigate
        try {
            const forms = m.querySelectorAll('form');
            forms.forEach(function (innerForm) {
                innerForm.addEventListener('submit', function (evt) {
                    if (evt.defaultPrevented) {
                        return;
                    }

                    const confirmMsg = innerForm.dataset.confirm;
                    if (confirmMsg && !confirm(confirmMsg)) return;

                    evt.preventDefault();
                    function restoreSubmitButtons() {
                        try {
                            innerForm.querySelectorAll('button[type="submit"]').forEach(b => {
                                if (b.dataset._disabled_by_js === '1') {
                                    b.disabled = false;
                                    b.innerHTML = b.dataset._original_html || 'Wyślij';
                                }
                            });
                        } catch (e) { }
                    }
                    try {
                        innerForm.querySelectorAll('button[type="submit"]').forEach(b => {
                            b.dataset._original_html = b.innerHTML;
                            b.disabled = true;
                            b.dataset._disabled_by_js = '1';
                            b.innerHTML = '⏳...';
                        });
                    } catch (e) { }

                    const url = innerForm.getAttribute('action');
                    if (!url || url === '#' || url === '') {
                        // Skip if no action defined - avoid unintended POST / that lead to 405 errors
                        restoreSubmitButtons();
                        return;
                    }
                    const method = (innerForm.getAttribute('method') || 'POST').toUpperCase();
                    const data = new URLSearchParams(new FormData(innerForm));

                    fetch(url, { method: method, body: data, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' }, redirect: 'manual' })
                        .then(async function (resp) {
                            const isRedirect = resp.type === 'opaqueredirect' || (resp.status >= 300 && resp.status < 400);
                            const stayOpen = innerForm.dataset.stayOpen === 'true';
                            const refreshTarget = innerForm.dataset.refreshTarget;
                            const refreshUrl = innerForm.dataset.refreshUrl;

                            function finalizeSuccess() {
                                if (stayOpen && refreshTarget && refreshUrl) {
                                    fetch(refreshUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                                        .then(r => r.text())
                                        .then(html => {
                                            const target = document.querySelector(refreshTarget);
                                            if (target) target.outerHTML = html;
                                        });
                                    // Re-enable buttons
                                    innerForm.querySelectorAll('button[type="submit"]').forEach(b => {
                                        b.disabled = false;
                                        if (b.dataset._original_html) b.innerHTML = b.dataset._original_html;
                                    });
                                    return;
                                }
                                remove(); performPartialReload();
                            }

                            if (resp.status === 401) { window.location.href = '/login'; return; }
                            if (isRedirect) { finalizeSuccess(); return; }
                            if (resp.status === 204) { finalizeSuccess(); return; }

                            const txt = await resp.text();
                            try {
                                const j = JSON.parse(txt);
                                if (!resp.ok) {
                                    if (typeof showToast === 'function') showToast(j && j.message ? j.message : 'Błąd zapisu', 'warning');
                                    restoreSubmitButtons();
                                    return;
                                }
                                if (j && j.success) {
                                    if (typeof showToast === 'function' && j.message) showToast(j.message, 'success');
                                    finalizeSuccess();
                                }
                                else {
                                    if (typeof showToast === 'function') showToast(j && j.message ? j.message : 'Błąd', 'warning');
                                    restoreSubmitButtons();
                                }
                            } catch (e) {
                                if (!resp.ok) {
                                    if (typeof showToast === 'function') showToast('Błąd zapisu', 'warning');
                                    restoreSubmitButtons();
                                    return;
                                }
                                // Default fallback if not JSON
                                finalizeSuccess();
                            }
                        }).catch(err => {
                            console.error('Quick popup form submit failed', err);
                            if (typeof showToast === 'function') showToast('Błąd sieci', 'danger');
                            restoreSubmitButtons();
                        });
                });
            });
        } catch (e) { console.warn('rebind quick-popup form error', e); }

        return { close: remove, element: m };
    }

    function showQuickPopup(title, html, opts) { return createQuickPopup(title, html, opts); }
    window.createQuickPopup = createQuickPopup;
    window.showQuickPopup = showQuickPopup;

    // duplicate createQuickPopup removed; primary implementation above will be used

    function showSlideOver(urlOrHtml, opts) {
        opts = opts || {};
        if (!urlOrHtml) return;
        // If provided HTML fragment, show it directly
        if (typeof urlOrHtml === 'string' && urlOrHtml.trim().startsWith('<')) {
            createQuickPopup('', urlOrHtml, opts);
            return;
        }
        // Otherwise fetch the URL (AJAX expected)
        fetch(urlOrHtml, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' }, cache: 'no-store' })
            .then(async function (resp) {
                if (resp.status === 401) { window.location.href = '/login'; return; }
                const txt = await resp.text();
                createQuickPopup('', txt, opts);
            }).catch(function (err) {
                console.error('[showSlideOver] fetch failed:', err);
                createQuickPopup('Błąd', '<div class="p-10">Nie udało się załadować zawartości: ' + (err && err.message ? err.message : 'błąd') + '</div>', opts);
            });
    }
    window.showSlideOver = showSlideOver;

    // Unified safeAlert wrapper - prefers showQuickPopup and falls back to native alert
    function escapeHtml(str) {
        return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function createPopupContent(type, message) {
        var m = escapeHtml(message || '');
        // A clean, premium styled alert box. We don't need duplicate headers inside the body.
        return '<div style="padding: 12px 0 4px; font-size: 15px; color: #475569; white-space: pre-wrap; line-height: 1.6;">' + m + '</div>';
    }

    function safeAlert(title, message) {
        try {
            var tLow = (title || '').toLowerCase();
            var type = 'info';
            if (/błąd|error|blad/i.test(tLow) || /^✗/.test(message || '')) {
                type = 'error';
            } else if (/uwaga|warning|ostrzeżenie/i.test(tLow)) {
                type = 'warning';
            }

            var displayType = type;
            if (type === 'info') displayType = 'success';

            var contentHtml = createPopupContent(displayType, message || title || '');
            if (typeof showQuickPopup === 'function') {
                showQuickPopup(title || 'Komunikat', contentHtml);
                return;
            }
        } catch (e) {
            // ignore and fallback to native alert
        }
        try { window.alert(message || title); } catch (e) { /* best-effort */ }
    }
    window.safeAlert = safeAlert;

    // Reinitialize event listeners after partial reload
    function reinitializeAfterPartialReload() {
        console.info('[reinit] Re-initializing after partial reload');
        // Global click delegation is already on document, so it should work
        // But reinit any timers or specific elements here
        try {
            if (window.dashboardPageHelpers && typeof window.dashboardPageHelpers.applyAutoSzarzaMode === 'function') {
                window.dashboardPageHelpers.applyAutoSzarzaMode();
            }
        } catch (e) { /* best-effort */ }
    }

    window.addEventListener('app:partialReload', reinitializeAfterPartialReload);

    // Backwards-compatible shim for legacy templates that call `otworzOknoDodawaniaPalety(planId, produkt, typ)`
    if (typeof window.otworzOknoDodawaniaPalety !== 'function') {
        window.otworzOknoDodawaniaPalety = function (planId, produkt, typ) {
            try {
                var url = '/api/dodaj_palete_page/' + encodeURIComponent(planId);
                // pass product/type as query params for any server-side prefill if needed
                if (produkt) url += '?produkt=' + encodeURIComponent(produkt) + (typ ? '&typ=' + encodeURIComponent(typ) : '');
                showSlideOver(url, { backdrop: true, allowBackdropClose: true, transient: false });
            } catch (e) { console.error('otworzOknoDodawaniaPalety shim failed', e); }
        };
    }

    // Sanitize alerts that contain full HTML documents or HTML snippets.
    // Some server endpoints return an HTML error page; many templates did `alert(err.message)`
    // which caused the entire HTML to be shown. This wrapper strips tags and truncates.
    try {
        (function () {
            const _origAlert = window.alert.bind(window);
            window.alert = function (msg) {
                try {
                    if (typeof msg === 'string' && (msg.indexOf('<!DOCTYPE') !== -1 || msg.indexOf('<html') !== -1 || /<[^>]+>/.test(msg))) {
                        let t = msg.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
                        t = t.replace(/<[^>]*>/g, '');
                        t = t.replace(/\s+/g, ' ').trim();
                        if (t.length > 800) t = t.slice(0, 800) + '...';
                        return _origAlert(t);
                    }
                } catch (e) { /* fallthrough to original */ }
                return _origAlert(msg);
            };
        })();
    } catch (e) { console.warn('alert sanitization failed', e); }

    window.openPrintLabelModal = function(url, title) {
        if (!url) return;
        if (typeof window.openInApp === 'function') {
            openInApp(url, title || 'Etykieta Palety');
        } else if (typeof showQuickPopup === 'function') {
            const html = '<div style="height: 85vh; display: flex; flex-direction: column; margin: -10px -20px;">'
                       + '<iframe src="' + url + '" style="flex-grow: 1; width: 100%; border: none; border-radius: 0 0 12px 12px;"></iframe>'
                       + '</div>';
            showQuickPopup('Etykieta Palety', html);
        } else {
            window.open(url, '_blank');
        }
    };

    function applyPrintSuccessState(btn, originalHtml, paletaId) {
        if (btn && btn instanceof HTMLElement) {
            if (!btn.classList.contains('print-success-applied')) {
                btn.classList.add('print-success-applied');
                const isIconBtn = btn.classList.contains('btn-icon');
                if (isIconBtn) {
                    btn.style.color = '#10b981';
                    btn.innerHTML = '<span class="material-icons" style="font-size:18px;">print</span>';
                } else {
                    btn.innerHTML = '<span class="material-icons print-success-icon" style="color: #10b981; font-size: 14px; vertical-align: middle; margin-right: 4px;">print</span>' + originalHtml;
                }
            }
        }

        try {
            const printedPallets = JSON.parse(sessionStorage.getItem('printedPallets') || '{}');
            printedPallets[paletaId] = true;
            sessionStorage.setItem('printedPallets', JSON.stringify(printedPallets));
        } catch (e) {}
    }

    function normalizeBridgeCandidate(entry) {
        if (!entry || typeof entry !== 'object') return null;

        const endpointRaw = String(entry.endpoint || '').trim();
        const statusRaw = String(entry.status_endpoint || '').trim();
        if (!endpointRaw) return null;

        return {
            name: String(entry.name || 'bridge').trim() || 'bridge',
            endpoint: endpointRaw,
            statusEndpoint: statusRaw || endpointRaw.replace(/\/drukuj-zpl\/?$/i, '/status')
        };
    }

    function getFallbackBridgeCandidates(fallbackData) {
        const candidates = [];
        const seen = new Set();

        function pushCandidate(raw) {
            const normalized = normalizeBridgeCandidate(raw);
            if (!normalized) return;
            const key = (normalized.name + '|' + normalized.endpoint).toLowerCase();
            if (seen.has(key)) return;
            seen.add(key);
            candidates.push(normalized);
        }

        function pushCandidateWithProtocolVariants(raw) {
            const normalized = normalizeBridgeCandidate(raw);
            if (!normalized) return;

            pushCandidate({
                name: normalized.name,
                endpoint: normalized.endpoint,
                status_endpoint: normalized.statusEndpoint
            });

            const endpoint = String(normalized.endpoint || '').trim();
            const statusEndpoint = String(normalized.statusEndpoint || '').trim();

            if (/^https:\/\//i.test(endpoint)) {
                pushCandidate({
                    name: normalized.name + '_http',
                    endpoint: 'http://' + endpoint.slice(8),
                    status_endpoint: /^https:\/\//i.test(statusEndpoint)
                        ? ('http://' + statusEndpoint.slice(8))
                        : statusEndpoint
                });
            } else if (/^http:\/\//i.test(endpoint)) {
                pushCandidate({
                    name: normalized.name + '_https',
                    endpoint: 'https://' + endpoint.slice(7),
                    status_endpoint: /^http:\/\//i.test(statusEndpoint)
                        ? ('https://' + statusEndpoint.slice(7))
                        : statusEndpoint
                });
            }
        }

        if (fallbackData && Array.isArray(fallbackData.endpoints)) {
            fallbackData.endpoints.forEach(pushCandidateWithProtocolVariants);
        }

        pushCandidateWithProtocolVariants({
            name: 'legacy_bridge',
            endpoint: fallbackData && fallbackData.endpoint,
            status_endpoint: fallbackData && fallbackData.status_endpoint
        });

        pushCandidateWithProtocolVariants({
            name: 'localhost_bridge',
            endpoint: 'http://127.0.0.1:3001/drukuj-zpl',
            status_endpoint: 'http://127.0.0.1:3001/status'
        });

        return candidates;
    }

    async function isBridgeReachable(statusEndpoint, timeoutMs) {
        const controller = new AbortController();
        const timeoutId = setTimeout(function () {
            controller.abort();
        }, timeoutMs);

        try {
            const resp = await fetch(statusEndpoint, {
                method: 'GET',
                signal: controller.signal
            });
            return resp.ok;
        } catch (e) {
            return false;
        } finally {
            clearTimeout(timeoutId);
        }
    }

    async function tryLocalBridgeFallback(fallbackData) {
        if (!fallbackData || typeof fallbackData !== 'object') {
            return { ok: false, message: 'Brak danych fallbacku lokalnego.' };
        }

        const zpl = String(fallbackData.zpl || '');
        const copies = Math.max(1, Number(fallbackData.copies || 1));
        const printers = Array.isArray(fallbackData.printers) ? fallbackData.printers : [];
        const bridgeCandidates = getFallbackBridgeCandidates(fallbackData);

        if (!zpl || !printers.length) {
            return { ok: false, message: 'Fallback lokalny nie zawiera danych ZPL lub drukarek.' };
        }
        if (!bridgeCandidates.length) {
            return { ok: false, message: 'Brak dostępnego endpointu mostka dla fallbacku lokalnego.' };
        }

        let lastMessage = 'Nieudany wydruk przez fallback mostka.';

        for (const bridgeCandidate of bridgeCandidates) {
            const bridgeOnline = await isBridgeReachable(bridgeCandidate.statusEndpoint, 1500);
            if (!bridgeOnline) {
                lastMessage = 'Mostek niedostępny: ' + bridgeCandidate.statusEndpoint;
                continue;
            }

            for (const printer of printers) {
                const printerName = String((printer && printer.name) || 'Drukarka lokalna').trim();
                const printerIp = String((printer && printer.ip) || '').trim();
                if (!printerIp) continue;

                let printerOk = true;
                for (let copyNum = 1; copyNum <= copies; copyNum++) {
                    try {
                        const resp = await fetch(bridgeCandidate.endpoint, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                drukarka: printerName,
                                ip: printerIp,
                                dane: zpl
                            })
                        });

                        let body = {};
                        try { body = await resp.json(); } catch (e) { body = {}; }

                        if (!(resp.ok && body && body.success === true)) {
                            printerOk = false;
                            lastMessage = (body && body.message)
                                ? String(body.message)
                                : ('Błąd mostka (HTTP ' + resp.status + ') dla ' + bridgeCandidate.endpoint);
                            break;
                        }
                    } catch (error) {
                        printerOk = false;
                        lastMessage = (error && error.message)
                            ? String(error.message)
                            : ('Błąd połączenia z mostkiem ' + bridgeCandidate.endpoint);
                        break;
                    }
                }

                if (printerOk) {
                    return {
                        ok: true,
                        printerName: printerName,
                        printerIp: printerIp,
                        bridgeName: bridgeCandidate.name,
                        bridgeEndpoint: bridgeCandidate.endpoint,
                        message: 'Wydrukowano przez fallback mostka.'
                    };
                }
            }
        }

        return {
            ok: false,
            message: lastMessage
        };
    }

    window.tryLocalBridgeFallback = tryLocalBridgeFallback;

    window.drukujZPLDirect = function(paletaId, linia, planId, btn) {
        if (!paletaId) return;

        if (typeof showToast === 'function') showToast('Wysyłanie etykiety...', 'info');

        const originalHtml = (btn && btn instanceof HTMLElement) ? btn.innerHTML : '';

        const url = '/drukuj_etykiete_zpl/' + paletaId + '?linia=' + encodeURIComponent(linia || 'PSD');
        const fetchOptions = {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        };

        fetch(url, fetchOptions)
        .then(r => r.json())
        .then(async (data) => {
            if (data.success) {
                if (typeof showToast === 'function') {
                    const printerLabel = (data.printer_name || data.printer_ip)
                        ? (' do: ' + (data.printer_name || data.printer_ip))
                        : '';
                    if (data.data_produkcji) {
                        showToast('Wysłano etykietę' + printerLabel + ' (data produkcji: ' + data.data_produkcji + ')', 'success');
                    } else {
                        showToast('Wysłano etykietę' + printerLabel, 'success');
                    }
                }
                applyPrintSuccessState(btn, originalHtml, paletaId);
                return;
            }

            // Awaryjny wydruk lokalny (przeglądarka -> http://127.0.0.1:3001) dla przypadku,
            // gdy serwer pod linkiem nie ma trasy sieciowej do drukarki.
            if (data && data.local_bridge_fallback) {
                if (typeof showToast === 'function') {
                    showToast('Serwer nie doszedł do drukarki, próba wydruku lokalnego...', 'warning');
                }

                const localResult = await tryLocalBridgeFallback(data.local_bridge_fallback);
                if (localResult.ok) {
                    if (typeof showToast === 'function') {
                        showToast(
                            'Wydruk fallback OK: ' + (localResult.printerName || '') + ' (' + (localResult.printerIp || '') + ') [' + (localResult.bridgeName || 'bridge') + ']',
                            'success'
                        );
                    }
                    applyPrintSuccessState(btn, originalHtml, paletaId);
                    return;
                }

                if (typeof showToast === 'function') {
                    showToast('Błąd fallbacku lokalnego: ' + localResult.message, 'danger');
                } else {
                    alert('Błąd fallbacku lokalnego: ' + localResult.message);
                }
                return;
            }

            if (typeof showToast === 'function') showToast('Błąd druku: ' + data.message, 'danger');
            else alert('Błąd druku: ' + data.message);
        })
        .catch(err => {
            console.error('ZPL Print error:', err);
            if (typeof showToast === 'function') showToast('Błąd połączenia z serwerem druku', 'danger');
        });
    };
    window.restorePrintIcons = function() {
        try {
            const printedPallets = JSON.parse(sessionStorage.getItem('printedPallets') || '{}');
            const buttons = document.querySelectorAll('button[onclick^="drukujZPLDirect"]');
            buttons.forEach(btn => {
                const match = btn.getAttribute('onclick').match(/drukujZPLDirect\('([^']+)'/);
                if (match && match[1]) {
                    const paletaId = match[1];
                    if (printedPallets[paletaId] && !btn.classList.contains('print-success-applied')) {
                        btn.classList.add('print-success-applied');
                        const isIconBtn = btn.classList.contains('btn-icon');
                        if (isIconBtn) {
                            btn.style.color = '#10b981';
                            btn.innerHTML = '<span class="material-icons" style="font-size:18px;">print</span>';
                        } else {
                            btn.innerHTML = '<span class="material-icons print-success-icon" style="color: #10b981; font-size: 14px; vertical-align: middle; margin-right: 4px;">print</span>' + btn.innerHTML;
                        }
                    }
                }
            });
        } catch(e) { console.error(e); }
    };
    
    window.addEventListener('app:partialReload', window.restorePrintIcons);
    document.addEventListener('DOMContentLoaded', window.restorePrintIcons);

})();
