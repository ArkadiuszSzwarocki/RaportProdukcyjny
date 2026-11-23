/* Live tank-material validation hints for dosypka forms (popup & full page). */
(function () {
    'use strict';

    function normalizeMaterialName(value) {
        return String(value || '').toLowerCase().replace(/[\s\-_.,()\/]+/g, ' ').trim();
    }

    function readTankMap(root) {
        const script = (root || document).querySelector('#dosypka-tank-map');
        if (!script) return {};
        try {
            const parsed = JSON.parse(script.textContent || '{}');
            if (!parsed || typeof parsed !== 'object') return {};
            const normalized = {};
            Object.keys(parsed).forEach((key) => {
                normalized[normalizeMaterialName(key)] = parsed[key];
            });
            return normalized;
        } catch (err) {
            return {};
        }
    }

    function ensureHintElement(input) {
        const row = input.closest('.dosypka-row, .ds-field-row');
        const group = row || input.closest('.dosypka-field-group, .ds-field-group') || input.parentElement;
        if (!group) return null;
        let hint = group.querySelector('.dosypka-tank-hint');
        if (!hint) {
            hint = document.createElement('span');
            hint.className = 'dosypka-tank-hint';
            hint.style.cssText = 'font-size:12px;font-weight:800;display:none;align-items:center;gap:4px;padding:4px 8px;border-radius:7px;white-space:nowrap;';
            if (row && input.parentElement === row) {
                row.insertBefore(hint, input);
            } else {
                group.appendChild(hint);
            }
        }
        return hint;
    }

    function updateInputTankHint(input, tankMap) {
        const hint = ensureHintElement(input);
        if (!hint) return;
        const raw = String(input.value || '').trim();
        if (!raw) {
            hint.style.display = 'none';
            hint.textContent = '';
            hint.title = '';
            return;
        }
        const hasAnyTanks = Object.keys(tankMap).length > 0;
        const matched = tankMap[normalizeMaterialName(raw)];
        if (Array.isArray(matched) && matched.length > 0) {
            const shortCodes = matched.map(t => t.code).join(', ');
            const fullLabels = matched.map(t => {
                const kgPart = t.amount_kg !== null && t.amount_kg !== undefined ? ` (${Number(t.amount_kg).toFixed(0)} kg)` : '';
                return `${t.code}${kgPart}`;
            }).join(', ');
            hint.style.display = 'inline-flex';
            hint.style.background = '#ecfdf5';
            hint.style.color = '#065f46';
            hint.style.border = '1px solid #6ee7b7';
            hint.textContent = shortCodes;
            hint.title = `Zbiornik: ${fullLabels}`;
        } else if (hasAnyTanks) {
            hint.style.display = 'inline-flex';
            hint.style.background = '#fef2f2';
            hint.style.color = '#991b1b';
            hint.style.border = '1px solid #fca5a5';
            hint.textContent = '⛔ Brak';
            hint.title = 'Brak surowca na żadnym aktywnym zbiorniku / stacji';
        } else {
            hint.style.display = 'none';
        }
    }

    function bindForm(form) {
        if (!form || form.dataset.tankValidatorBound === '1') return;
        form.dataset.tankValidatorBound = '1';
        const tankMap = readTankMap(form.parentElement || document);
        const handler = (event) => {
            const target = event.target;
            if (!target || !target.name || !target.name.startsWith('nazwa_')) return;
            updateInputTankHint(target, tankMap);
        };
        form.addEventListener('input', handler);
        form.addEventListener('change', handler);
        form.querySelectorAll('input[name^="nazwa_"]').forEach(input => updateInputTankHint(input, tankMap));
    }

    function init() {
        document.querySelectorAll('#dosypka-form, #ds-form').forEach(bindForm);
    }

    window.initDosypkaTankValidator = init;
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
