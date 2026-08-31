/**
 * static/js/common/date-switcher.js
 * Unified Date Switcher & Calendar Picker Controller.
 * Clean Architecture - Single Source of Truth for date navigation across the application.
 */
(function (global) {
    'use strict';

    function padZero(num) {
        return num < 10 ? '0' + num : String(num);
    }

    /**
     * Parses YYYY-MM-DD or DD.MM.YYYY string safely in local time (no UTC drift).
     * @param {string} str 
     * @returns {Date}
     */
    function parseLocalIso(str) {
        if (!str || typeof str !== 'string') {
            return new Date();
        }
        const trimmed = str.trim();
        // Format: YYYY-MM-DD
        if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
            const parts = trimmed.split('-');
            return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
        }
        // Format: DD.MM.YYYY
        if (/^\d{2}\.\d{2}\.\d{4}$/.test(trimmed)) {
            const parts = trimmed.split('.');
            return new Date(parseInt(parts[2], 10), parseInt(parts[1], 10) - 1, parseInt(parts[0], 10));
        }
        // Format: DD.MM.YY
        if (/^\d{2}\.\d{2}\.\d{2}$/.test(trimmed)) {
            const parts = trimmed.split('.');
            const fullYear = 2000 + parseInt(parts[2], 10);
            return new Date(fullYear, parseInt(parts[1], 10) - 1, parseInt(parts[0], 10));
        }
        const d = new Date(trimmed);
        return isNaN(d.getTime()) ? new Date() : d;
    }

    /**
     * Formats Date to YYYY-MM-DD
     * @param {Date} date 
     * @returns {string}
     */
    function formatIsoDate(date) {
        if (!(date instanceof Date) || isNaN(date.getTime())) {
            return '';
        }
        return date.getFullYear() + '-' + padZero(date.getMonth() + 1) + '-' + padZero(date.getDate());
    }

    /**
     * Formats Date to display format DD.MM.YY
     * @param {Date} date 
     * @returns {string}
     */
    function formatDisplayDate(date) {
        if (!(date instanceof Date) || isNaN(date.getTime())) {
            return '';
        }
        const yy = String(date.getFullYear()).slice(-2);
        return padZero(date.getDate()) + '.' + padZero(date.getMonth() + 1) + '.' + yy;
    }

    /**
     * Handles changing date on a specific picker element
     * @param {HTMLElement} pickerEl 
     * @param {string|Date} newDate 
     */
    function applyDateChange(pickerEl, newDate) {
        if (!pickerEl) return;
        const d = (newDate instanceof Date) ? newDate : parseLocalIso(newDate);
        const isoStr = formatIsoDate(d);
        const displayStr = formatDisplayDate(d);

        pickerEl.setAttribute('data-current-date', isoStr);

        const labelEl = pickerEl.querySelector('.unified-date-label, [data-date-label]');
        if (labelEl) {
            labelEl.textContent = displayStr;
        }

        const inputEl = pickerEl.querySelector('input.unified-date-input, [data-date-input]');
        if (inputEl && inputEl.value !== isoStr) {
            inputEl.value = isoStr;
        }

        const mode = (pickerEl.getAttribute('data-date-mode') || 'url').toLowerCase();
        const paramName = pickerEl.getAttribute('data-date-param') || 'data';

        if (mode === 'url') {
            try {
                const url = new URL(window.location.href);
                url.searchParams.set(paramName, isoStr);
                // Clear any conflicting range parameters
                url.searchParams.delete('data_od');
                url.searchParams.delete('data_do');

                // Preserve scroll position before navigating
                try {
                    localStorage.setItem('system_scroll_pos', String(window.scrollY));
                } catch (e) {}

                window.location.assign(url.toString());
            } catch (e) {
                console.error('[DateSwitcher] URL redirect failed:', e);
                window.location.search = '?' + paramName + '=' + encodeURIComponent(isoStr);
            }
        } else {
            // Event / AJAX mode
            const eventDetail = {
                date: isoStr,
                displayDate: displayStr,
                dateObj: d,
                pickerId: pickerEl.id || null,
                pickerEl: pickerEl
            };

            pickerEl.dispatchEvent(new CustomEvent('app:date-changed', {
                bubbles: true,
                detail: eventDetail
            }));

            window.dispatchEvent(new CustomEvent('app:date-changed', {
                detail: eventDetail
            }));
        }
    }

    /**
     * Shifts date by specified offset (e.g. -1 or +1)
     * @param {HTMLElement} pickerEl 
     * @param {number} offsetDays 
     */
    function shiftDate(pickerEl, offsetDays) {
        if (!pickerEl) return;
        const currentIso = pickerEl.getAttribute('data-current-date')
            || (pickerEl.querySelector('input.unified-date-input') ? pickerEl.querySelector('input.unified-date-input').value : null)
            || '';
        const curDate = parseLocalIso(currentIso);
        curDate.setDate(curDate.getDate() + offsetDays);
        applyDateChange(pickerEl, curDate);
    }

    /**
     * Initializes a single date picker component DOM element
     * @param {HTMLElement} pickerEl 
     */
    function initPicker(pickerEl) {
        if (!pickerEl || pickerEl._dateSwitcherInitialized) return;
        pickerEl._dateSwitcherInitialized = true;

        const inputEl = pickerEl.querySelector('input.unified-date-input, [data-date-input]');
        if (inputEl) {
            inputEl.addEventListener('change', function () {
                if (this.value) {
                    applyDateChange(pickerEl, this.value);
                }
            });
        }

        const prevBtn = pickerEl.querySelector('[data-date-action="prev"], .unified-date-prev');
        if (prevBtn) {
            prevBtn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                shiftDate(pickerEl, -1);
            });
        }

        const nextBtn = pickerEl.querySelector('[data-date-action="next"], .unified-date-next');
        if (nextBtn) {
            nextBtn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                shiftDate(pickerEl, 1);
            });
        }
    }

    /**
     * Initializes all date pickers on the page
     */
    function initAll() {
        const pickers = document.querySelectorAll('.unified-date-picker, [data-unified-date-picker]');
        pickers.forEach(initPicker);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }

    // Public API
    global.DateSwitcher = {
        parseLocalIso: parseLocalIso,
        formatIsoDate: formatIsoDate,
        formatDisplayDate: formatDisplayDate,
        applyDateChange: applyDateChange,
        shiftDate: shiftDate,
        initPicker: initPicker,
        initAll: initAll
    };

})(window);
