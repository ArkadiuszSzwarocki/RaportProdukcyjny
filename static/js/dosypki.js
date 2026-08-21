// Static initializer for dosypki list slide-over
(function () {
    'use strict';

    var debugEnabled = !!window.__RP_DEBUG__;

    function debugLog() {
        if (!debugEnabled) return;
        console.log.apply(console, arguments);
    }

    function debugWarn() {
        if (!debugEnabled) return;
        console.warn.apply(console, arguments);
    }

    function debugError() {
        if (!debugEnabled) return;
        console.error.apply(console, arguments);
    }

    function getDashboardConfigState() {
        if (!window.dashboardConfig || typeof window.dashboardConfig.getState !== 'function') {
            return null;
        }
        return window.dashboardConfig.getState();
    }

    function getCurrentRole(root) {
        const config = getDashboardConfigState();
        const container = root && root.closest ? (root.closest('.p-15') || root) : root;
        const roleFromAttr = container && container.getAttribute ? container.getAttribute('data-current-role') : '';
        const roleFromConfig = config && config.currentRole ? config.currentRole : '';
        return String(roleFromAttr || roleFromConfig || '').toLowerCase();
    }

    function getCurrentLinia(root) {
        const config = getDashboardConfigState();
        const container = root && root.closest ? (root.closest('.p-15') || root) : root;
        const liniaFromAttr = container && container.getAttribute ? container.getAttribute('data-linia') : '';
        const urlParams = new URLSearchParams(window.location.search);
        return String(liniaFromAttr || (config && config.linia) || urlParams.get('linia') || 'PSD');
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function updateDosypkiBadge(planId, delta) {
        if (!planId) return;
        debugLog('[dosypki.badge] Updating badge for plan:', planId, 'delta:', delta);
        const trigger = document.querySelector('.btn-with-badge[data-plan-id="' + String(planId) + '"]');
        if (!trigger) {
            debugWarn('[dosypki.badge] Trigger button not found for plan:', planId);
            return;
        }
        let badge = trigger.querySelector('.action-badge');
        const current = badge ? parseInt(badge.textContent, 10) || 0 : 0;
        const next = Math.max(0, current + delta);

        debugLog('[dosypki.badge] Current:', current, 'Next:', next);

        if (next <= 0) {
            if (badge) {
                badge.style.opacity = '0';
                setTimeout(() => badge.remove(), 300);
            }
            return;
        }
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'action-badge';
            badge.style.opacity = '0';
            trigger.appendChild(badge);
            // Trigger reflow for animation
            badge.offsetHeight;
            badge.style.opacity = '1';
        }
        badge.textContent = String(next);
    }

    function ensureConfirmOverlay(container) {
        if (!container || !container.querySelector) return null;
        var overlay = container.querySelector('.dosypki-confirm-overlay');
        if (overlay) return overlay;

        overlay = document.createElement('div');
        overlay.className = 'dosypki-confirm-overlay';
        overlay.innerHTML = '<div class="dosypki-confirm-spinner" aria-label="Ladowanie"></div>';
        container.appendChild(overlay);
        return overlay;
    }

    function setConfirmOverlay(container, isActive) {
        var root = container && container.classList && container.classList.contains('dosypki-list-root')
            ? container
            : (container && container.querySelector ? container.querySelector('.dosypki-list-root') : null);
        if (!root) return;
        var overlay = ensureConfirmOverlay(root);
        if (!overlay) return;
        if (isActive) {
            overlay.classList.add('is-active');
        } else {
            overlay.classList.remove('is-active');
        }
    }

    function renderActionCell(d, role, initialDisabled = false) {
        if (role === 'masteradmin' || role === 'operator' || role === 'pracownik' || role === 'produkcja' || role === 'lider' || role === 'admin' || role === 'zarzad') {
            const disabledAttr = initialDisabled ? 'disabled style="opacity: 0.5; cursor: not-allowed;"' : '';
            return '<button class="dosypka-confirm-btn" data-id="' + d.id + '" data-action="confirm" ' + disabledAttr + '>✓ Potwierdź</button>';
        }
        return '';
    }

    function buildRowHtml(d, idx, role) {
        const nameHtml = d.nazwa ? escapeHtml(d.nazwa) : '<em>— brak nazwy —</em>';
        const planKg = d.kg_planowane !== undefined && d.kg_planowane !== null ? d.kg_planowane : d.kg;
        const valKg = d.kg_wydozowane !== undefined && d.kg_wydozowane !== null ? d.kg_wydozowane : planKg;
        return `
            <tr data-plan-id="${escapeHtml(d.plan_id)}" data-dosypka-id="${escapeHtml(d.id)}">
                <td class="text-muted" data-label="#">${idx + 1}</td>
                <td data-label="Plan ID"><span style="font-weight:700; color:#3b82f6;">#${escapeHtml(d.plan_id)}</span></td>
                <td data-label="Nazwa">
                    <span style="font-weight:800; font-size:14px; color:#1e293b;">${nameHtml}</span>
                </td>
                <td data-label="Zaplanowane">
                    <span style="display:inline-block; padding:4px 10px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:6px; color:#1e40af; font-weight:800;">${escapeHtml(planKg)} kg</span>
                </td>
                <td data-label="Wydozowano">
                    <div style="display:inline-flex; align-items:center; gap:6px;">
                        <input type="number" step="0.01" min="0.01" class="dosypka-actual-kg" 
                               value="${escapeHtml(valKg)}" 
                               style="width: 90px; padding: 6px 8px; border: 2px solid #10b981; border-radius: 8px; font-weight: 800; font-size:14px; text-align: right; background: #fff;" 
                               placeholder="wpisz kg" 
                               autocomplete="off" />
                        <span style="font-weight:700; font-size:12px; color:#64748b;">kg</span>
                    </div>
                </td>
                <td data-label="Dodana" style="font-size:12px; color:#64748b;">${escapeHtml(d.data_zlecenia)}</td>
                <td data-label="Akcja" style="text-align: right;">${renderActionCell(d, role, false)}</td>
            </tr>
        `;
    }

    function focusFirstEmptyInput(container) {
        if (!container) return;
        setTimeout(() => {
            const inputs = container.querySelectorAll('input.dosypka-actual-kg');
            for (const input of inputs) {
                if (!input.value && !input.disabled) {
                    input.focus();
                    break;
                }
            }
        }, 120);
    }

    async function fetchDosypki(container) {
        debugLog('[dosypki.fetch] Starting fetch for container:', container);
        const statusEl = container.querySelector('#dosypki-status');
        const spinner = container.querySelector('#dosypki-spinner');
        const table = container.querySelector('#dosypki-table');
        const tbody = table && table.querySelector('tbody');
        debugLog('[dosypki.fetch] Found elements - statusEl:', statusEl, 'spinner:', spinner, 'table:', table, 'tbody:', tbody);
        try {
            if (statusEl) { statusEl.textContent = 'Ładowanie...'; statusEl.style.display = ''; }
            if (spinner) spinner.classList.remove('hidden');

            // Get plan_id from data attributes or URL params
            const p15 = container.closest && container.closest('.p-15');
            const planIdFromAttr = (p15 && p15.getAttribute('data-plan-id')) || (container.getAttribute && container.getAttribute('data-plan-id'));
            const urlParams = new URLSearchParams(window.location.search);
            const planIdFromUrl = urlParams.get('plan_id');
            const planId = planIdFromAttr || planIdFromUrl;
            const role = getCurrentRole(container);

            // Get linia from the fragment first, then dashboard config, then URL param.
            const linia = getCurrentLinia(container);

            debugLog('[dosypki.fetch] planIdFromAttr:', planIdFromAttr, 'planIdFromUrl:', planIdFromUrl, 'planId:', planId);
            debugLog('[dosypki.fetch] linia:', linia, 'Current role:', role);

            let fetchUrl = '/api/dosypki?linia=' + encodeURIComponent(linia);
            if (planId) fetchUrl += '&plan_id=' + encodeURIComponent(planId);
            debugLog('[dosypki.fetch] Fetching from:', fetchUrl);

            const res = await fetch(fetchUrl, { 
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            debugLog('[dosypki.fetch] Response status:', res.status);
            const data = await res.json().catch(() => ({}));
            debugLog('[dosypki.fetch] Response data:', data);
            if (spinner) spinner.classList.add('hidden');
            if (!data || !data.success) {
                if (statusEl) statusEl.textContent = (data && data.message) ? data.message : 'Brak dostępu';
                if (table) table.style.display = 'none';
                return;
            }
            const list = data.dosypki || [];
            debugLog('[dosypki.fetch] Dosypki list:', list);
            if (list.length === 0) {
                if (statusEl) statusEl.textContent = 'Brak dosypek.';
                if (table) table.style.display = 'none';
                return;
            }
            if (statusEl) statusEl.style.display = 'none';
            if (table) table.style.display = 'table';
            if (tbody) tbody.innerHTML = '';
            list.forEach(function (d, idx) {
                if (!tbody) return;
                tbody.insertAdjacentHTML('beforeend', buildRowHtml(d, idx, role));
            });
            debugLog('[dosypki.fetch] Populated tbody with', list.length, 'rows');
            focusFirstEmptyInput(container);
        } catch (e) {
            if (spinner) spinner.classList.add('hidden');
            if (container && container.querySelector('#dosypki-status')) {
                container.querySelector('#dosypki-status').textContent = 'Błąd podczas ładowania';
                container.querySelector('#dosypki-status').style.display = '';
            }
            debugError('dosypki: fetch error', e);
        }
    }

    async function confirmDosypka(id, btn) {
        let originalText = null;
        const container = btn.closest && btn.closest('.p-15') ? btn.closest('.p-15') : document;
        try {
            const row = btn.closest('tr');
            const planId = row ? row.getAttribute('data-plan-id') : null;
            const actualInput = row ? row.querySelector('.dosypka-actual-kg') : null;
            let actualKg = null;
            if (actualInput) {
                const rawVal = (actualInput.value || '').replace(',', '.').trim();
                const parsed = parseFloat(rawVal);
                if (isNaN(parsed) || parsed <= 0) {
                    if (typeof AppDialog !== 'undefined' && AppDialog.alert) {
                        AppDialog.alert('Wpisz prawidłową wagę wydozowaną przez maszynę (większą od 0 kg)!');
                    } else {
                        alert('Wpisz prawidłową wagę wydozowaną przez maszynę (większą od 0 kg)!');
                    }
                    actualInput.focus();
                    return;
                }
                actualKg = parsed;
            }

            const p15 = btn.closest && btn.closest('.p-15');
            const linia = getCurrentLinia(p15 || btn);

            btn.disabled = true;
            originalText = btn.textContent;
            btn.textContent = '⏳...';
            setConfirmOverlay(container, true);

            const res = await fetch('/potwierdz_dosypke/' + id + '?linia=' + encodeURIComponent(linia), {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ kg: actualKg })
            });
            const data = await res.json().catch(() => ({}));

            if (res.ok) {
                // 1. Dynamic UI update: remove row and update badge
                if (row) {
                    row.style.opacity = '0.5';
                    row.style.pointerEvents = 'none';
                    setTimeout(() => { if (row.parentNode) row.parentNode.removeChild(row); }, 300);
                }

                if (planId) {
                    updateDosypkiBadge(planId, -1);
                }
                await fetchDosypki(container);
                if (typeof window.performPartialReload === 'function') {
                    window.performPartialReload({ force: true, preserveScroll: true, source: 'dosypki-confirm' });
                }
            } else {
                btn.disabled = false;
                if (originalText) btn.textContent = originalText;
                AppDialog.alert((data && data.message) || 'Błąd podczas potwierdzania');
            }
        } catch (e) {
            btn.disabled = false;
            try { if (originalText) btn.textContent = originalText; } catch (_) { }
            debugError('dosypki: confirm error', e);
            AppDialog.alert('Błąd sieci');
        } finally {
            setConfirmOverlay(container, false);
        }
    }

    function initContainer(container) {
        if (!container) return;
        // avoid double-init
        if (container.__dosypki_inited) return;
        container.__dosypki_inited = true;

        // Real-time input validation to enable/disable confirm button
        container.addEventListener('input', function (ev) {
            const input = ev.target.closest && ev.target.closest('input.dosypka-actual-kg');
            if (!input) return;
            const row = input.closest('tr');
            const btn = row ? row.querySelector('.dosypka-confirm-btn') : null;
            if (!btn) return;
            const val = parseFloat((input.value || '').replace(',', '.').trim());
            if (!isNaN(val) && val > 0) {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
            } else {
                btn.disabled = true;
                btn.style.opacity = '0.5';
                btn.style.cursor = 'not-allowed';
            }
        });

        // Pressing Enter in the input field submits confirmation
        container.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter') {
                const input = ev.target.closest && ev.target.closest('input.dosypka-actual-kg');
                if (!input) return;
                const row = input.closest('tr');
                const btn = row ? row.querySelector('.dosypka-confirm-btn') : null;
                if (btn && !btn.disabled) {
                    ev.preventDefault();
                    btn.click();
                }
            }
        });

        // delegate click for confirmation buttons
        // Only handle clicks on buttons explicitly rendered as dosypka confirmation
        container.addEventListener('click', function (ev) {
            const btn = ev.target.closest && ev.target.closest('button.dosypka-confirm-btn[data-id]');
            if (!btn) return;
            if (btn.disabled) return;
            const id = btn.getAttribute('data-id');
            if (!id) return;

            // Directly confirm dosypka without blocking browser confirm dialog
            // (removed native confirm per UX request)
            confirmDosypka(id, btn);
        });

        // initial load
        fetchDosypki(container);
        focusFirstEmptyInput(container);
    }

    // Expose for manual init
    window.initDosypkiList = function (root) {
        const container = root || document.body;
        const statusEl = container.querySelector('#dosypki-status');
        const p15 = statusEl && statusEl.closest('.p-15');
        if (statusEl) {
            initContainer(p15 || document);
        }
    };

    window.reloadActiveDosypkiList = function () {
        const statusEl = document.querySelector('#dosypki-status');
        if (statusEl && statusEl.offsetParent !== null) { // if visible
            const p15 = statusEl.closest('.p-15') || document;
            fetchDosypki(p15);
        }
    };

    // Auto-init if fragment inserted later (works with slide-over injection)
    const observer = new MutationObserver(function (mutations) {
        for (const m of mutations) {
            for (const node of m.addedNodes) {
                if (!(node instanceof HTMLElement)) continue;
                if (node.querySelector && node.querySelector('#dosypki-status')) {
                    initContainer(node.querySelector('#dosypki-status').closest('.p-15') || node);
                    return;
                }
                if (node.id === 'dosypki-status') {
                    initContainer(node.closest('.p-15') || node);
                    return;
                }
            }
        }
    });
    observer.observe(document.documentElement || document.body, { childList: true, subtree: true });

    // Also try init on DOMContentLoaded in case template was rendered server-side
    document.addEventListener('DOMContentLoaded', function () {
        const statusEl = document.getElementById('dosypki-status');
        if (statusEl) {
            initContainer(statusEl.closest('.p-15') || document);
        }
    });

    // Fallback polling: some injection methods replace innerHTML of an existing popup
    // without creating new nodes, so MutationObserver may miss it. Poll briefly after load.
    (function pollForDosypkiInsertion() {
        let attempts = 0;
        const maxAttempts = 20; // ~2 seconds at 100ms
        const iv = setInterval(function () {
            attempts++;
            try {
                const statusEl = document.getElementById('dosypki-status');
                const tableEl = document.getElementById('dosypki-table');
                const node = statusEl || tableEl;
                if (node) {
                    initContainer((node.closest && node.closest('.p-15')) || document);
                    clearInterval(iv);
                    return;
                }
            } catch (e) { /* ignore */ }
            if (attempts >= maxAttempts) clearInterval(iv);
        }, 100);
    })();

})();
