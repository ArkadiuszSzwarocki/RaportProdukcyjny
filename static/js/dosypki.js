// Static initializer for dosypki list slide-over
(function () {
    'use strict';

    async function fetchDosypki(container) {
        console.log('[dosypki.fetch] Starting fetch for container:', container);
        const statusEl = container.querySelector('#dosypki-status');
        const spinner = container.querySelector('#dosypki-spinner');
        const table = container.querySelector('#dosypki-table');
        const tbody = table && table.querySelector('tbody');
        console.log('[dosypki.fetch] Found elements - statusEl:', statusEl, 'spinner:', spinner, 'table:', table, 'tbody:', tbody);
        try {
            if (statusEl) { statusEl.textContent = 'Ładowanie...'; statusEl.style.display = ''; }
            if (spinner) spinner.classList.remove('hidden');

            // Get plan_id from data attributes or URL params
            const p15 = container.closest && container.closest('.p-15');
            const planIdFromAttr = (p15 && p15.getAttribute('data-plan-id')) || (container.getAttribute && container.getAttribute('data-plan-id'));
            const urlParams = new URLSearchParams(window.location.search);
            const planIdFromUrl = urlParams.get('plan_id');
            const planId = planIdFromAttr || planIdFromUrl;

            let fetchUrl = '/api/dosypki';
            if (planId) fetchUrl += '?plan_id=' + encodeURIComponent(planId);
            console.log('[dosypki.fetch] Fetching from:', fetchUrl);

            const res = await fetch(fetchUrl, { credentials: 'same-origin' });
            console.log('[dosypki.fetch] Response status:', res.status);
            const data = await res.json().catch(() => ({}));
            console.log('[dosypki.fetch] Response data:', data);
            if (spinner) spinner.classList.add('hidden');
            if (!data || !data.success) {
                if (statusEl) statusEl.textContent = (data && data.message) ? data.message : 'Brak dostępu';
                if (table) table.style.display = 'none';
                return;
            }
            const list = data.dosypki || [];
            console.log('[dosypki.fetch] Dosypki list:', list);
            if (list.length === 0) {
                if (statusEl) statusEl.textContent = 'Brak niepotwierdzonych dosypek.';
                if (table) table.style.display = 'none';
                return;
            }
            if (statusEl) statusEl.style.display = 'none';
            if (table) table.style.display = 'table';
            if (tbody) tbody.innerHTML = '';
            list.forEach(function (d, idx) {
                if (!tbody) return;
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="text-muted">${idx + 1}</td>
                    <td>${d.plan_id}</td>
                    <td>${d.nazwa ? d.nazwa : '<em>— brak nazwy —</em>'}</td>
                    <td>${d.kg}</td>
                    <td>${d.data_zlecenia}</td>
                    <td><button class="btn-action btn-save btn-small" data-id="${d.id}">Potwierdź</button></td>
                `;
                tbody.appendChild(tr);
            });
            console.log('[dosypki.fetch] Populated tbody with', list.length, 'rows');
        } catch (e) {
            if (spinner) spinner.classList.add('hidden');
            if (container && container.querySelector('#dosypki-status')) {
                container.querySelector('#dosypki-status').textContent = 'Błąd podczas ładowania';
                container.querySelector('#dosypki-status').style.display = '';
            }
            console.error('dosypki: fetch error', e);
        }
    }

    async function confirmDosypka(id, btn) {
        let originalText = null;
        try {
            btn.disabled = true;
            originalText = btn.textContent;
            btn.textContent = '⏳...';
            const res = await fetch('/potwierdz_dosypke/' + id, { method: 'POST', credentials: 'same-origin' });
            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                const row = btn.closest('tr');
                if (row) row.parentNode.removeChild(row);
                // force window reload to show confirmed dosypki on the dashboard
                setTimeout(() => { window.location.reload(); }, 300);
            } else {
                btn.disabled = false;
                if (originalText) btn.textContent = originalText;
                alert((data && data.message) || 'Błąd podczas potwierdzania');
            }
        } catch (e) {
            btn.disabled = false;
            try { if (originalText) btn.textContent = originalText; } catch (_) { }
            console.error('dosypki: confirm error', e);
            alert('Błąd sieci');
        }
    }

    function initContainer(container) {
        if (!container) return;
        // avoid double-init
        if (container.__dosypki_inited) return;
        container.__dosypki_inited = true;

        // delegate click for confirmation buttons
        container.addEventListener('click', function (ev) {
            const btn = ev.target.closest && ev.target.closest('button[data-id]');
            if (!btn) return;
            const id = btn.getAttribute('data-id');
            if (!id) return;
            if (!confirm('Potwierdzić dosypkę?')) return;
            confirmDosypka(id, btn);
        });

        // initial load
        fetchDosypki(container);
    }

    // Expose for manual init
    window.initDosypkiList = function (root) {
        console.log('[dosypki] initDosypkiList called with root:', root);
        const container = root || document.body;
        const statusEl = container.querySelector('#dosypki-status');
        console.log('[dosypki] Found statusEl:', statusEl);
        const p15 = statusEl && statusEl.closest('.p-15');
        console.log('[dosypki] Found .p-15 container:', p15);
        if (statusEl) {
            initContainer(p15 || document);
        } else {
            console.log('[dosypki] statusEl not found, trying to find .p-15 directly');
            const p15Direct = container.querySelector('.p-15');
            console.log('[dosypki] Direct .p-15 search result:', p15Direct);
            if (p15Direct) {
                initContainer(p15Direct);
            }
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
