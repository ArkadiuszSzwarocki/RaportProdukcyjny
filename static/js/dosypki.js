// cspell:words wydozowane
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
        const triggers = document.querySelectorAll('.btn-with-badge[data-plan-id="' + String(planId) + '"]:not([data-szarza-id])');
        if (!triggers || triggers.length === 0) {
            debugWarn('[dosypki.badge] Trigger button not found for plan:', planId);
            return;
        }

        triggers.forEach(trigger => {
            let badge = trigger.querySelector('.action-badge');
            const current = badge ? parseInt(badge.textContent, 10) || 0 : 0;
            const next = Math.max(0, current + delta);

            if (next <= 0) {
                if (badge) {
                    badge.style.opacity = '0';
                    setTimeout(() => badge.remove(), 300);
                }
            } else {
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'action-badge';
                    badge.style.opacity = '0';
                    trigger.appendChild(badge);
                    badge.offsetHeight;
                    badge.style.opacity = '1';
                }
                badge.textContent = String(next);
            }
        });
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
        var out = '';
        if (role === 'masteradmin' || role === 'operator' || role === 'pracownik' || role === 'produkcja' || role === 'lider' || role === 'admin' || role === 'zarzad') {
            const disabledAttr = initialDisabled ? 'disabled style="opacity: 0.5; cursor: not-allowed;"' : '';
            out += '<button type="button" class="dosypka-confirm-btn" data-id="' + d.id + '" data-action="confirm" ' + disabledAttr + '>✓ Potwierdź</button>';
        }
        if (role === 'masteradmin' || role === 'admin' || role === 'lider' || role === 'laborant' || role === 'laboratorium') {
            out += ' <button type="button" class="dosypka-cancel-btn btn-action btn-danger btn-sm" data-id="' + d.id + '" title="Anuluj dosypkę" style="padding: 6px 10px; font-weight:700; border-radius:8px; margin-left:6px; cursor:pointer; background:#ef4444; color:#fff; border:none;">✕ Anuluj</button>';
        }
        return out;
    }

    function getZasypGroupKey(d) {
        const zasypPart = d.nr_szarzy || d.szarza_id || 'none';
        return String(d.plan_id || '') + ':' + String(zasypPart);
    }

    function buildZasypSeparatorHtml(d, isFirstGroup) {
        const key = getZasypGroupKey(d);
        let label = 'Bez przypisanego zasypu';
        if (d.nr_szarzy) {
            label = 'Zasyp #' + escapeHtml(d.nr_szarzy);
        } else if (d.szarza_id) {
            label = 'Szarża #' + escapeHtml(d.szarza_id);
        }
        const firstCls = isFirstGroup ? ' is-first-group' : '';
        return `<tr class="dosypki-zasyp-separator${firstCls}" data-zasyp-key="${escapeHtml(key)}"><td colspan="8">⚡ ${label} · Zlecenie #${escapeHtml(d.plan_id)}</td></tr>`;
    }

    function buildRowHtml(d, idx, role) {
        const nameHtml = d.nazwa ? escapeHtml(d.nazwa) : '<em>— brak nazwy —</em>';
        const planKg = d.kg_planowane !== undefined && d.kg_planowane !== null ? d.kg_planowane : d.kg;
        const valKg = d.kg_wydozowane !== undefined && d.kg_wydozowane !== null && Number(d.kg_wydozowane) > 0 ? d.kg_wydozowane : '';
        const hasValidInitialKg = valKg !== '' && !isNaN(parseFloat(valKg)) && parseFloat(valKg) > 0;

        let zasypHtml = '<span style="color:#94a3b8; font-size:12px;">—</span>';
        const zasypNum = d.nr_szarzy || d.zasyp_nr;
        if (zasypNum) {
            zasypHtml = `<span style="display:inline-flex; align-items:center; gap:6px; padding:6px 12px; background:linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); border:2px solid #f59e0b; border-radius:8px; color:#92400e; font-weight:900; font-size:13px; letter-spacing:0.5px; text-transform:uppercase; box-shadow:0 1px 3px rgba(245,158,11,0.25); white-space:nowrap;">
                <span style="font-size:14px;">⚡</span> DOSYPKA DO ZASYPU #${escapeHtml(zasypNum)}
            </span>`;
        } else if (d.szarza_id) {
            zasypHtml = `<span style="display:inline-flex; align-items:center; gap:4px; padding:5px 10px; background:#f1f5f9; border:1.5px solid #cbd5e1; border-radius:8px; color:#334155; font-weight:800; font-size:12px; text-transform:uppercase; white-space:nowrap;">
                DOSYPKA DO SZARŻY #${escapeHtml(d.szarza_id)}
            </span>`;
        }

        return `
            <tr data-plan-id="${escapeHtml(d.plan_id)}" data-dosypka-id="${escapeHtml(d.id)}" data-zasyp-key="${escapeHtml(getZasypGroupKey(d))}">
                <td class="text-muted" data-label="#">${idx + 1}</td>
                <td data-label="Plan ID"><span style="font-weight:700; color:#3b82f6;">#${escapeHtml(d.plan_id)}</span></td>
                <td data-label="Do zasypu" style="white-space:nowrap;">${zasypHtml}</td>
                <td data-label="Nazwa">
                    <span style="font-weight:800; font-size:14px; color:#1e293b;">${nameHtml}</span>
                </td>
                <td data-label="Zaplanowane">
                    <span style="display:inline-block; padding:4px 10px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:6px; color:#1e40af; font-weight:800;">${escapeHtml(planKg)} kg</span>
                </td>
                <td data-label="Wydozowano">
                    <div style="display:inline-flex; align-items:center; gap:6px;">
                        <input type="number" step="0.01" min="0.01" class="dosypka-actual-kg no-kb-icon" data-no-kb-block="true"
                               value="${escapeHtml(valKg)}" 
                               style="width: 120px; padding: 6px 10px; border: 2px solid #10b981; border-radius: 8px; font-weight: 800; font-size:15px; text-align: right; background: #fff;" 
                               placeholder="wpisz kg" 
                               autocomplete="off" />
                        <span style="font-weight:700; font-size:12px; color:#64748b;">kg</span>
                    </div>
                </td>
                <td data-label="Dodana" style="font-size:12px; color:#64748b;">${escapeHtml(d.data_zlecenia)}</td>
                <td data-label="Akcja" style="text-align: right;">${renderActionCell(d, role, !hasValidInitialKg)}</td>
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

    function syncBulkConfirmButton(container) {
        if (!container || typeof container.querySelector !== 'function') return;
        const bar = container.querySelector('#dosypki-bulk-bar');
        const allBtn = container.querySelector('#dosypka-confirm-all-btn');
        const countEl = container.querySelector('#dosypki-bulk-count');
        const tbody = container.querySelector('#dosypki-table tbody');
        if (!bar && !allBtn && !countEl) return;

        const rows = tbody ? Array.from(tbody.querySelectorAll('tr[data-dosypka-id]')).filter(
            (tr) => tr.dataset.removing !== '1',
        ) : [];
        let validCount = 0;
        rows.forEach((tr) => {
            const input = tr.querySelector('input.dosypka-actual-kg');
            const val = input ? parseFloat((input.value || '').replace(',', '.').trim()) : NaN;
            if (!isNaN(val) && val > 0) validCount += 1;
        });

        if (bar) bar.style.display = rows.length > 0 ? 'flex' : 'none';
        if (countEl) countEl.textContent = `Uzupełniono wag: ${validCount} / ${rows.length}`;
        if (allBtn) allBtn.disabled = !(rows.length > 0 && validCount === rows.length);
    }

    function syncConfirmButtonState(input) {
        const row = input && input.closest ? input.closest('tr') : null;
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
    }

    function captureDraftInputs(tbody) {
        const values = {};
        let focusedId = null;
        if (!tbody) return { values, focusedId };
        tbody.querySelectorAll('tr[data-dosypka-id]').forEach((row) => {
            const dosypkaId = row.getAttribute('data-dosypka-id');
            const input = row.querySelector('input.dosypka-actual-kg');
            if (!dosypkaId || !input) return;
            if (document.activeElement === input) {
                focusedId = dosypkaId;
            }
            if (input.dataset.dirty === '1') {
                values[dosypkaId] = input.value;
            }
        });
        return { values, focusedId };
    }

    function restoreDraftInputs(tbody, draft) {
        if (!tbody || !draft) return;
        Object.keys(draft.values || {}).forEach((dosypkaId) => {
            const row = tbody.querySelector('tr[data-dosypka-id="' + dosypkaId + '"]');
            const input = row ? row.querySelector('input.dosypka-actual-kg') : null;
            if (!input) return;
            input.value = draft.values[dosypkaId];
            input.dataset.dirty = '1';
            syncConfirmButtonState(input);
        });
        if (draft.focusedId) {
            const row = tbody.querySelector('tr[data-dosypka-id="' + draft.focusedId + '"]');
            const input = row ? row.querySelector('input.dosypka-actual-kg') : null;
            if (input && !input.disabled) input.focus();
        }
    }

    function removeDosypkaRow(container, row) {
        if (!row) return;
        const table = container ? container.querySelector('#dosypki-table') : null;
        const tbody = table ? table.querySelector('tbody') : row.parentNode;
        const statusEl = container ? container.querySelector('#dosypki-status') : null;
        row.dataset.removing = '1';
        row.style.opacity = '0.5';
        row.style.pointerEvents = 'none';
        syncBulkConfirmButton(container);
        setTimeout(() => {
            const zasypKey = row.getAttribute('data-zasyp-key');
            if (row.parentNode) row.parentNode.removeChild(row);
            if (!tbody) return;
            if (zasypKey) {
                const sameGroupRows = tbody.querySelectorAll('tr[data-dosypka-id][data-zasyp-key="' + zasypKey + '"]');
                if (sameGroupRows.length === 0) {
                    const sep = tbody.querySelector('tr.dosypki-zasyp-separator[data-zasyp-key="' + zasypKey + '"]');
                    if (sep && sep.parentNode) sep.parentNode.removeChild(sep);
                }
            }
            const remaining = tbody.querySelectorAll('tr[data-dosypka-id]');
            remaining.forEach((tr, idx) => {
                const indexCell = tr.querySelector('td[data-label="#"]');
                if (indexCell) indexCell.textContent = String(idx + 1);
            });
            if (remaining.length === 0) {
                if (statusEl) {
                    statusEl.textContent = 'Brak dosypek.';
                    statusEl.style.display = '';
                }
                if (table) table.style.display = 'none';
            }
            syncBulkConfirmButton(container);
        }, 200);
    }

    async function fetchDosypki(container) {
        debugLog('[dosypki.fetch] Starting fetch for container:', container);
        const statusEl = container.querySelector('#dosypki-status');
        const spinner = container.querySelector('#dosypki-spinner');
        const table = container.querySelector('#dosypki-table');
        const tbody = table && table.querySelector('tbody');
        const hasExistingRows = Boolean(tbody && tbody.querySelector('tr'));
        debugLog('[dosypki.fetch] Found elements - statusEl:', statusEl, 'spinner:', spinner, 'table:', table, 'tbody:', tbody);
        try {
            if (!hasExistingRows) {
                if (statusEl) { statusEl.textContent = 'Ładowanie...'; statusEl.style.display = ''; }
                if (spinner) spinner.classList.remove('hidden');
            }

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
                if (tbody) tbody.innerHTML = '';
                if (statusEl) { statusEl.textContent = 'Brak dosypek.'; statusEl.style.display = ''; }
                if (table) table.style.display = 'none';
                syncBulkConfirmButton(container);
                return;
            }
            const draft = captureDraftInputs(tbody);
            if (statusEl) statusEl.style.display = 'none';
            if (table) table.style.display = 'table';
            if (tbody) tbody.innerHTML = '';
            const groupedMap = new Map();
            list.forEach(function (d) {
                const key = getZasypGroupKey(d);
                if (!groupedMap.has(key)) groupedMap.set(key, []);
                groupedMap.get(key).push(d);
            });
            const groupedList = [];
            groupedMap.forEach(function (items) {
                items.forEach(function (item) { groupedList.push(item); });
            });

            let prevGroupKey = '';
            groupedList.forEach(function (d, idx) {
                if (!tbody) return;
                const groupKey = getZasypGroupKey(d);
                if (groupKey !== prevGroupKey) {
                    tbody.insertAdjacentHTML('beforeend', buildZasypSeparatorHtml(d, idx === 0));
                    prevGroupKey = groupKey;
                }
                tbody.insertAdjacentHTML('beforeend', buildRowHtml(d, idx, role));
            });
            restoreDraftInputs(tbody, draft);
            syncBulkConfirmButton(container);
            debugLog('[dosypki.fetch] Populated tbody with', list.length, 'rows');
            if (!draft.focusedId) {
                focusFirstEmptyInput(container);
            }
        } catch (e) {
            if (spinner) spinner.classList.add('hidden');
            if (container && container.querySelector('#dosypki-status')) {
                container.querySelector('#dosypki-status').textContent = 'Błąd podczas ładowania';
                container.querySelector('#dosypki-status').style.display = '';
            }
            debugError('dosypki: fetch error', e);
        }
    }

    function showConfirmMessage(container, message, success) {
        let feedback = container.querySelector('.dosypki-confirm-message');
        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'dosypki-confirm-message';
            feedback.setAttribute('role', 'status');
            container.appendChild(feedback);
        }
        feedback.textContent = message;
        feedback.style.color = success ? '#047857' : '#b91c1c';
        if (typeof window.showToast === 'function') {
            window.showToast(message, success ? 'success' : 'danger');
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
                    showConfirmMessage(container, 'Wpisz prawidłową wagę wydozowaną przez maszynę (większą od 0 kg)!', false);
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
                    'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
                },
                body: new URLSearchParams({ kg: actualKg }).toString()
            });
            const data = await res.json().catch(() => ({}));

            if (res.ok && data.success === true) {
                // 1. Dynamic UI update: remove only the confirmed row, keeping other inputs intact
                removeDosypkaRow(container, row);

                if (planId) {
                    updateDosypkiBadge(planId, -1);
                }
                showConfirmMessage(container, data.message || 'Potwierdzono dosypkę.', true);
                if (typeof window.performPartialReload === 'function') {
                    await window.performPartialReload({ force: true, preserveScroll: true, source: 'dosypki-confirm' });
                }
                if (window.dashboardAgroBanners && typeof window.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner === 'function') {
                    window.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner();
                }
            } else {
                btn.disabled = false;
                if (originalText) btn.textContent = originalText;
                showConfirmMessage(container, data.message || (res.redirected
                    ? 'Sesja wygasła. Zaloguj się ponownie i spróbuj zatwierdzić dosypkę.'
                    : 'Nie udało się potwierdzić dosypki (HTTP ' + res.status + ').'), false);
            }
        } catch (e) {
            btn.disabled = false;
            try { if (originalText) btn.textContent = originalText; } catch (_) { }
            debugError('dosypki: confirm error', e);
            showConfirmMessage(container, 'Nie udało się połączyć z serwerem. Dosypka nie została potwierdzona.', false);
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
            input.dataset.dirty = '1';
            syncConfirmButtonState(input);
            syncBulkConfirmButton(container);
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
            ev.preventDefault();
            const id = btn.getAttribute('data-id');
            if (!id) return;

            // Directly confirm dosypka without blocking browser confirm dialog
            // (removed native confirm per UX request)
            confirmDosypka(id, btn);
        });

        // delegate click for cancel/delete buttons
        container.addEventListener('click', async function (ev) {
            const cancelBtn = ev.target.closest && ev.target.closest('button.dosypka-cancel-btn[data-id]');
            if (!cancelBtn) return;
            if (cancelBtn.disabled) return;
            ev.preventDefault();
            const id = cancelBtn.getAttribute('data-id');
            if (!id) return;
            if (!confirm('Czy na pewno chcesz anulować tę dosypkę?')) return;

            const p15 = cancelBtn.closest && cancelBtn.closest('.p-15');
            const linia = getCurrentLinia(p15 || cancelBtn);
            cancelBtn.disabled = true;
            try {
                const res = await fetch('/anuluj_dosypke/' + id + '?linia=' + encodeURIComponent(linia), {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json'
                    }
                });
                const data = await res.json().catch(() => ({}));
                if (res.ok && data.success) {
                    showConfirmMessage(container, data.message || 'Dosypka została anulowana.', true);
                    const row = cancelBtn.closest('tr');
                    const planId = row ? row.getAttribute('data-plan-id') : null;
                    removeDosypkaRow(container, row);
                    if (planId) {
                        updateDosypkiBadge(planId, -1);
                    }
                    if (typeof window.performPartialReload === 'function') {
                        await window.performPartialReload({ force: true, preserveScroll: true, source: 'dosypki-cancel' });
                    }
                } else {
                    alert(data.message || 'Nie udało się anulować dosypki.');
                    cancelBtn.disabled = false;
                }
            } catch (e) {
                alert('Błąd sieci: ' + e.message);
                cancelBtn.disabled = false;
            }
        });

        // delegate click for bulk confirm all button
        container.addEventListener('click', async function (ev) {
            const allBtn = ev.target.closest && ev.target.closest('#dosypka-confirm-all-btn');
            if (!allBtn || allBtn.disabled) return;
            ev.preventDefault();
            const tbody = container.querySelector('#dosypki-table tbody');
            const rows = tbody ? Array.from(tbody.querySelectorAll('tr[data-dosypka-id]')).filter(
                (tr) => tr.dataset.removing !== '1',
            ) : [];
            if (!rows.length) return;

            const items = [];
            for (const row of rows) {
                const id = row.getAttribute('data-dosypka-id');
                const input = row.querySelector('input.dosypka-actual-kg');
                const parsed = input ? parseFloat((input.value || '').replace(',', '.').trim()) : NaN;
                if (!id || isNaN(parsed) || parsed <= 0) {
                    showConfirmMessage(container, 'Wpisz dodatnią wagę (większą od 0 kg) we wszystkich pozycjach przed zbiorczym zatwierdzeniem.', false);
                    if (input) input.focus();
                    return;
                }
                items.push({ id, kg: parsed, row, planId: row.getAttribute('data-plan-id') });
            }

            const linia = getCurrentLinia(container);
            const originalText = allBtn.textContent;
            allBtn.disabled = true;
            allBtn.textContent = '⏳ Zatwierdzanie...';
            setConfirmOverlay(container, true);
            let confirmedCount = 0;

            try {
                for (const item of items) {
                    const res = await fetch('/potwierdz_dosypke/' + item.id + '?linia=' + encodeURIComponent(linia), {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest',
                            'Accept': 'application/json',
                            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                        },
                        body: new URLSearchParams({ kg: item.kg }).toString(),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok || data.success !== true) {
                        showConfirmMessage(container, data.message || 'Nie udało się potwierdzić jednej z pozycji (HTTP ' + res.status + ').', false);
                        break;
                    }
                    confirmedCount += 1;
                    removeDosypkaRow(container, item.row);
                    if (item.planId) updateDosypkiBadge(item.planId, -1);
                }

                if (confirmedCount > 0) {
                    if (confirmedCount === items.length) {
                        showConfirmMessage(container, `Potwierdzono wszystkie dosypki (${confirmedCount}).`, true);
                    }
                    if (typeof window.performPartialReload === 'function') {
                        await window.performPartialReload({ force: true, preserveScroll: true, source: 'dosypki-confirm-all' });
                    }
                    if (window.dashboardAgroBanners && typeof window.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner === 'function') {
                        window.dashboardAgroBanners.syncDosypkiBadgesAndFallbackBanner();
                    }
                }
            } catch (e) {
                debugError('dosypki: confirm all error', e);
                showConfirmMessage(container, 'Nie udało się połączyć z serwerem podczas zbiorczego zatwierdzania.', false);
            } finally {
                allBtn.textContent = originalText;
                setConfirmOverlay(container, false);
                syncBulkConfirmButton(container);
            }
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
