(function (global) {
    'use strict';

    if (global.dashboardPageHelpers) {
        return;
    }

    var initialized = false;
    var dayShiftBound = false;
    var overviewBound = false;
    var paletaTimersInterval = null;

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

    function getAutoSzarzaMode() {
        try {
            var config = getConfigState();
            var role = String(config && config.currentRole || '').toLowerCase();
            var roleDefault = ['operator', 'pracownik', 'produkcja', 'lider'].includes(role) ? 'auto' : 'manual';
            var mode = (localStorage.getItem('zasyp_auto_szarza_mode') || roleDefault).toLowerCase();
            return mode === 'auto' ? 'auto' : 'manual';
        } catch (error) {
            return 'manual';
        }
    }

    function applyAutoSzarzaMode() {
        var config = getConfigState();
        if (!(getSekcja() === 'Zasyp' && String(config && config.linia || '').toUpperCase() === 'AGRO')) {
            return;
        }

        var mode = getAutoSzarzaMode();
        document.querySelectorAll('.auto-szarza-mode-input').forEach(function (element) {
            element.value = mode;
        });

        document.querySelectorAll('.auto-szarza-switch').forEach(function (element) {
            element.checked = mode === 'auto';
        });

        document.querySelectorAll('.manual-szarza-btn').forEach(function (element) {
            if (mode === 'auto') {
                element.style.opacity = '0.45';
                element.style.filter = 'grayscale(35%)';
                element.style.pointerEvents = 'none';
                element.title = 'Tryb AUTO SZARŻA jest włączony. Dodanie nastąpi przy starcie Naważania.';
                return;
            }

            element.style.opacity = '';
            element.style.filter = '';
            element.style.pointerEvents = '';
            element.title = '+ SZARŻA';
        });
    }

    function toggleAutoSzarzaMode(checkbox) {
        var mode = checkbox && checkbox.checked ? 'auto' : 'manual';
        try {
            localStorage.setItem('zasyp_auto_szarza_mode', mode);
        } catch (error) {
        }
        applyAutoSzarzaMode();
    }

    function openRaportPalet() {
        try {
            var input = document.getElementById('current-date-iso');
            var dateIso = (input && input.value) ? input.value : (new Date()).toISOString().slice(0, 10);
            var url = '/agro/raport_palet?data=' + encodeURIComponent(dateIso) + '&select=1';
            if (typeof global.showSlideOver === 'function') {
                global.showSlideOver(url, { backdrop: true });
                return false;
            }
            global.open(url, '_blank');
        } catch (error) {
            console.error('openRaportPalet error', error);
        }
        return false;
    }

    function openModal(id) {
        try {
            if (global.__RP_DEBUG__) {
                console.debug('[modal-disabled] openModal called, id=', id);
            }
        } catch (error) {
        }
    }

    function closeAllModals() {
        try {
            if (global.__RP_DEBUG__) {
                console.debug('[modal-disabled] closeAllModals called');
            }
        } catch (error) {
        }
        try {
            if (typeof global.closeQuickPopup === 'function') {
                global.closeQuickPopup();
            }
        } catch (error) {
        }
        try {
            if (typeof global.closeCenterModal === 'function') {
                global.closeCenterModal();
            }
        } catch (error) {
        }
    }

    function formatElapsed(secs) {
        var normalizedSecs = Number(secs) || 0;
        if (normalizedSecs < 0) {
            normalizedSecs = 0;
        }
        var hours = Math.floor(normalizedSecs / 3600);
        var minutes = Math.floor((normalizedSecs % 3600) / 60);
        var seconds = normalizedSecs % 60;
        if (hours > 0) {
            return hours + 'h ' + String(minutes).padStart(2, '0') + 'm';
        }
        if (minutes > 0) {
            return minutes + 'm ' + String(seconds).padStart(2, '0') + 's';
        }
        return seconds + 's';
    }

    function updatePaletaTimers() {
        document.querySelectorAll('.paleta-elapsed').forEach(function (element) {
            var dateStart = element.getAttribute('data-start');
            if (!dateStart) {
                return;
            }
            var timestamp = Date.parse(dateStart.replace(' ', 'T'));
            if (isNaN(timestamp)) {
                return;
            }
            var secs = Math.floor((Date.now() - timestamp) / 1000);
            element.textContent = '⏱️ ' + formatElapsed(secs);
        });

        document.querySelectorAll('.order-elapsed').forEach(function (element) {
            var dateStart = element.getAttribute('data-start');
            if (!dateStart) {
                return;
            }
            var timestamp = Date.parse(dateStart.replace(' ', 'T'));
            if (isNaN(timestamp)) {
                return;
            }
            var secs = Math.floor((Date.now() - timestamp) / 1000);
            element.textContent = formatElapsed(secs);
        });
    }

    function initUpdatePaletaTimers() {
        updatePaletaTimers();
        if (global.dashboardScheduler && typeof global.dashboardScheduler.addTask === 'function') {
            global.dashboardScheduler.addTask('dashboard-paleta-live-timers', 1000, updatePaletaTimers, { runImmediately: false });
            return;
        }
        global.clearInterval(paletaTimersInterval);
        paletaTimersInterval = global.setInterval(updatePaletaTimers, 1000);
    }

    function toggleDetails(id) {
        var detailsContainer = document.getElementById('details-' + id);
        if (!detailsContainer) {
            console.warn('[rp-debug] toggleDetails: details container not found for ID:', id);
            return;
        }

        var card = document.querySelector('.card[data-id="' + id + '"]');
        var title = card ? card.getAttribute('data-order-title') : ('Zlecenie #' + id);
        var summary = card ? card.getAttribute('data-order-summary') : '';
        var paletyCount = card ? card.getAttribute('data-palety-count') : '0';
        var sekcjaAttr = card ? card.getAttribute('data-sekcja') : 'Workowanie';
        
        var config = getConfigState();
        var linia = (config && config.linia) ? String(config.linia).toUpperCase() : 'PSD';
        
        var dateIso = '';
        if (global.dashboardCardActions && typeof global.dashboardCardActions.resolveCurrentPlanDate === 'function') {
            dateIso = global.dashboardCardActions.resolveCurrentPlanDate();
        } else {
            // Local fallback if card-actions.js is not loaded yet or failed
            var isoInput = document.getElementById('current-date-iso');
            dateIso = (isoInput && isoInput.value) ? isoInput.value : '';
            if (!dateIso) {
                try {
                    var params = new URLSearchParams(global.location.search);
                    dateIso = params.get('data') || '';
                } catch(e) {}
            }
        }

        // Build Modal Header with Summary and Report Link
        var modalHtml = '<div class="agro-modal-header mb-15" style="border-bottom: 2px solid #eee; padding-bottom: 12px; margin-bottom: 15px;">';
        modalHtml += '<div class="d-flex justify-between align-center">';
        modalHtml += '  <div>';
        modalHtml += '    <h2 style="margin:0; color:#2c3e50; font-size:1.25em;">' + title + '</h2>';
        modalHtml += '    <div style="font-size:0.9em; margin-top:4px;">';
        modalHtml += '       <span class="text-muted">Wykonanie:</span> <strong>' + summary + '</strong>';
        modalHtml += '       <span style="margin: 0 8px; color: #ccc;">|</span>';
        modalHtml += '       <span class="text-muted">' + (sekcjaAttr === 'Zasyp' ? 'Zasypy' : 'Palety') + ':</span> <strong>' + paletyCount + ' szt.</strong>';
        modalHtml += '    </div>';
        modalHtml += '  </div>';
        
        if (linia === 'AGRO') {
            var raportUrl = '/agro/raport_palet?data=' + encodeURIComponent(dateIso) + '&select=1';
            modalHtml += '  <a href="' + raportUrl + '" class="btn-action btn-blue" style="text-decoration:none; display:flex; align-items:center; gap:5px; padding:8px 15px;">';
            modalHtml += '    <span class="material-icons" style="font-size:18px;">print</span> RAPORT';
            modalHtml += '  </a>';
        }
        modalHtml += '</div>';
        modalHtml += '</div>';

        // Add the actual details content
        modalHtml += '<div class="agro-modal-body">' + detailsContainer.innerHTML + '</div>';

        if (global.dashboardUi && typeof global.dashboardUi.openQuickPopup === 'function') {
            global.dashboardUi.openQuickPopup(modalHtml);
            
            // Set modal title in the standard popup header if exists
            var headerTitle = document.querySelector('#quickPopup .header-title');
            if (headerTitle) {
                headerTitle.textContent = 'Szczegóły zlecenia';
            }
            
            // Re-bind slide links in the new content
            if (typeof global.dashboardUi.bindSlideLinks === 'function') {
                // Since bindSlideLinks usually binds to body, it might already work.
                // But if it's specific, we might need a refresh.
            }
        } else {
            // Fallback to inline toggle if UI helper missing
            var isHidden = getComputedStyle(detailsContainer).display === 'none' || detailsContainer.style.display === 'none';
            detailsContainer.style.display = isHidden ? 'block' : 'none';
        }
    }

    function shiftCurrentDay(offset, container) {
        function pad(value) {
            return value < 10 ? ('0' + value) : String(value);
        }

        function isoFromDate(date) {
            return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
        }

        var isoInput = document.getElementById('current-date-iso');
        var baseIso = isoInput ? isoInput.value : null;
        var baseDate = baseIso ? new Date(baseIso + 'T00:00:00') : new Date();
        var target = new Date(baseDate.getTime());
        target.setDate(target.getDate() + offset);

        var iso = isoFromDate(target);
        var params = new URLSearchParams(global.location.search);
        var sekcja = (container && container.dataset ? container.dataset.sekcja : '') || params.get('sekcja');
        var config = getConfigState();
        var linia = params.get('linia') || String(config && config.linia || 'PSD');
        if (sekcja) {
            params.set('sekcja', sekcja);
        } else {
            params.delete('sekcja');
        }
        params.set('linia', linia);
        params.set('data', iso);
        global.location.search = params.toString();
    }

    function bindDayShiftNavigation() {
        if (dayShiftBound) {
            return;
        }
        dayShiftBound = true;
    }

    function bindDateOverview() {
        if (overviewBound) {
            return;
        }
        overviewBound = true;

        var isoInput = document.getElementById('current-date-iso');
        if (!isoInput) {
            return;
        }
        var currentEl = document.getElementById('overview-current');
        var rangeEl = document.getElementById('overview-range');
        if (!currentEl || !rangeEl) {
            return;
        }

        function parseIso(value) {
            return new Date((value || '') + 'T00:00:00');
        }

        function formatDate(date) {
            try {
                return date.toLocaleDateString('pl-PL', { day: '2-digit', month: 'short', year: 'numeric' });
            } catch (error) {
                return date.toISOString().slice(0, 10);
            }
        }

        function startOfWeek(date) {
            var normalized = new Date(date.getTime());
            var dayOfWeek = normalized.getDay();
            var delta = (dayOfWeek + 6) % 7;
            normalized.setDate(normalized.getDate() - delta);
            normalized.setHours(0, 0, 0, 0);
            return normalized;
        }

        function endOfWeek(date) {
            var normalized = startOfWeek(date);
            normalized.setDate(normalized.getDate() + 6);
            return normalized;
        }

        function startOfMonth(date) {
            return new Date(date.getFullYear(), date.getMonth(), 1);
        }

        function endOfMonth(date) {
            return new Date(date.getFullYear(), date.getMonth() + 1, 0);
        }

        var currentDate = isoInput.value ? parseIso(isoInput.value) : new Date();
        currentEl.textContent = formatDate(currentDate);

        function showDay() {
            rangeEl.textContent = formatDate(currentDate);
        }

        function showWeek() {
            var start = startOfWeek(currentDate);
            var end = endOfWeek(currentDate);
            rangeEl.textContent = formatDate(start) + ' — ' + formatDate(end);
        }

        function showMonth() {
            var start = startOfMonth(currentDate);
            var end = endOfMonth(currentDate);
            rangeEl.textContent = formatDate(start) + ' — ' + formatDate(end);
        }

        showDay();

        var dayBtn = document.getElementById('view-day');
        var weekBtn = document.getElementById('view-week');
        var monthBtn = document.getElementById('view-month');
        if (dayBtn) {
            dayBtn.addEventListener('click', showDay);
        }
        if (weekBtn) {
            weekBtn.addEventListener('click', showWeek);
        }
        if (monthBtn) {
            monthBtn.addEventListener('click', showMonth);
        }
    }

    function initDebugLogging() {
        if (!global.__RP_DEBUG__) {
            return;
        }
        console.log('%c===DASHBOARD LOADED===', 'color:blue;font-weight:bold');
        console.log('Cards elements:', document.querySelectorAll('.card').length);
        console.log('Card actions elements:', document.querySelectorAll('.card-actions').length);
        document.querySelectorAll('.card-actions').forEach(function (cardAction, index) {
            var links = cardAction.querySelectorAll('a');
            var buttons = cardAction.querySelectorAll('button');
            console.log('Card #' + (index + 1) + ': ' + links.length + ' links, ' + buttons.length + ' buttons');
        });
        console.log('===END INIT LOG===');
    }

    function handleDocumentClick(event) {
        var dayNavButton = event.target.closest('button[data-day-offset]');
        if (dayNavButton) {
            event.preventDefault();
            shiftCurrentDay(parseInt(dayNavButton.getAttribute('data-day-offset') || 0, 10), dayNavButton.closest('.day-tile'));
            return;
        }

        var raportTrigger = event.target.closest('#raportPaletBtn');
        if (raportTrigger) {
            event.preventDefault();
            openRaportPalet();
            return;
        }

        var toggleTrigger = event.target.closest('[data-toggle-details]');
        if (toggleTrigger) {
            event.preventDefault();
            toggleDetails(toggleTrigger.getAttribute('data-toggle-details'));
            return;
        }

        var sendZwolnienieTrigger = event.target.closest('[data-action="send-zwolnienie-mieszalnika"]');
        if (sendZwolnienieTrigger) {
            event.preventDefault();
            if (global.dashboardAgroBanners && typeof global.dashboardAgroBanners.sendZwolnienieMieszalnika === 'function') {
                global.dashboardAgroBanners.sendZwolnienieMieszalnika();
            }
        }
    }

    function handleDocumentChange(event) {
        var checkbox = event.target.closest('.auto-szarza-switch');
        if (!checkbox) {
            return;
        }
        toggleAutoSzarzaMode(checkbox);
    }

    function handleDocumentSubmit(event) {
        var form = event.target;
        if (!form || !form.getAttribute) {
            return;
        }

        var message = form.getAttribute('data-confirm');
        if (!message) {
            return;
        }

        if (!global.confirm(message)) {
            event.preventDefault();
        }
    }

    function init() {
        if (initialized) {
            return;
        }
        initialized = true;

        initDebugLogging();
        document.addEventListener('click', handleDocumentClick, false);
        document.addEventListener('change', handleDocumentChange, false);
        document.addEventListener('submit', handleDocumentSubmit, false);

        applyAutoSzarzaMode();
        closeAllModals();
        initUpdatePaletaTimers();
        bindDayShiftNavigation();
        bindDateOverview();
    }

    async function showRaportZbiorczy(zasypId, linia) {
        var normalizedLinia = linia || 'AGRO';
        var modalEl = document.getElementById('modal-raport-zbiorczy');
        if (!modalEl) {
            return;
        }
        var modal = new bootstrap.Modal(modalEl);
        modal.show();
        
        var loadingEl = document.getElementById('raport-zbiorczy-loading');
        var contentEl = document.getElementById('raport-zbiorczy-content');
        if (loadingEl) loadingEl.style.display = 'block';
        if (contentEl) contentEl.style.display = 'none';
        
        try {
            var response = await fetch('/api/raport-zbiorczy/' + zasypId + '?linia=' + encodeURIComponent(normalizedLinia));
            var data = await response.json();
            
            if (data.success) {
                var r = data.raport;
                var estimatedSum = ((r.szarze ? (r.szarze.suma_kg || 0) : 0) + (r.dosypki || []).reduce(function(sum, d) { return sum + (d.kg || 0); }, 0)).toFixed(1);
                var html = '<div class="row mb-3">';
                html += '  <div class="col-md-6 border-end">';
                html += '    <h6 class="text-primary border-bottom pb-2"><i class="fas fa-industry me-1"></i> Dane Zasypu</h6>';
                html += '    <p class="mb-1"><strong>Produkt:</strong> ' + (r.zasyp ? r.zasyp.produkt : 'Brak danych') + '</p>';
                html += '    <p class="mb-1"><strong>Status zlecenia:</strong> <span class="badge bg-secondary">' + (r.zasyp ? r.zasyp.status : 'Brak danych') + '</span></p>';
                html += '    <p class="mb-1 mt-2"><strong>Zasypano (szarże + dosypki):</strong> <span class="text-primary fw-bold">' + estimatedSum + ' kg</span></p>';
                html += '  </div>';
                html += '  <div class="col-md-6 ps-md-4">';
                html += '    <h6 class="text-success border-bottom pb-2"><i class="fas fa-box me-1"></i> Wydajność Workowania</h6>';
                html += '    <p class="mb-1"><strong>Czas pracy maszyny:</strong> ' + (r.palety ? r.palety.czas_pracy_h : '0') + ' h</p>';
                html += '    <p class="mb-1 mt-2"><strong>Wydajność:</strong> <span class="badge bg-success fs-6">' + (r.palety ? r.palety.wydajnosc_kg_h : '0') + ' kg/h</span></p>';
                html += '    <p class="mb-1 mt-2"><strong>Wyprodukowano:</strong> <strong>' + (r.palety ? r.palety.liczba : '0') + '</strong> palet (łącznie ' + (r.palety ? r.palety.suma_kg : '0') + ' kg)</p>';
                html += '  </div>';
                html += '</div>';
                
                html += '<h6 class="border-bottom pb-2 mt-4 text-warning"><i class="fas fa-scroll me-1"></i> Zużyte Opakowania i Folie na zleceniu</h6>';
                html += '<ul class="list-group list-group-flush mt-2 shadow-sm">';
                if (r.opakowania && r.opakowania.length > 0) {
                    var itemsHtml = r.opakowania.map(function(o) {
                        return '<li class="list-group-item d-flex justify-content-between align-items-center"><div><strong>' + o.opakowanie_nazwa + '</strong><br><small class="text-muted">Stan obecny na maszynie: ' + o.stan_po + '</small></div><span class="badge bg-primary rounded-pill" style="font-size: 0.9em;">Zużyto: ' + o.zuzyte_worki + '</span></li>';
                    }).join('');
                    html += itemsHtml;
                } else {
                    html += '<li class="list-group-item text-muted">Brak zarejestrowanych zużyć opakowań i folii dla tego zlecenia.</li>';
                }
                html += '</ul>';
                
                if (contentEl) contentEl.innerHTML = html;
            } else {
                if (contentEl) contentEl.innerHTML = '<div class="alert alert-warning">' + data.message + '</div>';
            }
        } catch (err) {
            if (contentEl) contentEl.innerHTML = '<div class="alert alert-danger">Błąd podczas pobierania danych raportu.</div>';
        } finally {
            if (loadingEl) loadingEl.style.display = 'none';
            if (contentEl) contentEl.style.display = 'block';
        }
    }

    global.showRaportZbiorczy = showRaportZbiorczy;

    global.dashboardPageHelpers = {
        init: init,
        openRaportPalet: openRaportPalet,
        getAutoSzarzaMode: getAutoSzarzaMode,
        applyAutoSzarzaMode: applyAutoSzarzaMode,
        toggleAutoSzarzaMode: toggleAutoSzarzaMode,
        openModal: openModal,
        initUpdatePaletaTimers: initUpdatePaletaTimers,
        updatePaletaTimers: updatePaletaTimers,
        formatElapsed: formatElapsed,
        toggleDetails: toggleDetails,
        closeAllModals: closeAllModals,
        showRaportZbiorczy: showRaportZbiorczy,
    };

    ready(init);
})(window);