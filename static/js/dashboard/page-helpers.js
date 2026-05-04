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
            var roleDefault = ['pracownik', 'produkcja', 'lider'].includes(role) ? 'auto' : 'manual';
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
        var row = document.getElementById('details-' + id);
        var icon = document.getElementById('icon-' + id);
        if (!row) {
            return;
        }

        var isHidden = getComputedStyle(row).display === 'none' || row.style.display === 'none';
        row.style.display = isHidden ? 'block' : 'none';
        if (icon) {
            icon.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
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
    };

    ready(init);
})(window);