/* Server events trigger data-only updates; no interval or page reload. */
(function () {
    'use strict';
    let events, wanted = null, applied = null, busy = false, retry = null, scheduled = null;
    function normalize(items) {
        const fields = ['displayId','id','linia','productName','packaging_type','type','location','batch','date_prod','date_exp','date_added','unit','order_id','order_ref','order_doc_type','order_doc_label','order_source','order_dest','order_date'];
        return items.map(item => {
            const result = {};
            for (const key of fields) result[key] = String(item[key] == null ? '' : item[key]);
            result.amount = Number(item.amount) || 0;
            result.is_blocked = Number(!!Number(item.is_blocked));
            result.packaging_type ||= 'Worek (25kg)';
            for (const key of ['batch','date_prod','date_exp','date_added']) result[key] ||= '-';
            return result;
        });
    }
    function updateSummary(stats, fefo) {
        for (const [id, value] of Object.entries(stats || {})) {
            const bar = document.getElementById('cap-' + id);
            if (!bar) continue;
            const percent = Number(value.percent) || 0;
            const color = percent > 90 ? '#ef4444' : percent > 75 ? '#f59e0b' : '#10b981';
            const label = bar.querySelector(':scope > div:first-child > span:last-child');
            if (label) { label.textContent = percent + '%'; label.style.color = color; }
            const fill = bar.querySelector(':scope > div:nth-child(2) > div');
            if (fill) { fill.style.width = Math.min(100, percent) + '%'; fill.style.background = color; }
            const count = bar.querySelector(':scope > div:last-child > span');
            if (count) count.textContent = value.occupied + ' / ' + value.total + ' PALET';
        }
        if (!Array.isArray(fefo)) return;
        const toggle = document.getElementById('fefoDrawerToggle');
        const drawer = document.getElementById('fefoDrawer');
        if (toggle) {
            toggle.hidden = fefo.length === 0;
            const count = toggle.querySelector('.fefo-drawer-count');
            if (count) count.textContent = fefo.length;
        }
        if (drawer) {
            const description = drawer.querySelector('.fefo-drawer-description');
            if (description) description.textContent = fefo.length + ' palet z krótkim terminem przydatności';
            const body = drawer.querySelector('tbody');
            if (body && body.dataset.snapshot !== JSON.stringify(fefo)) {
                const rows = fefo.map(pallet => {
                    const row = document.createElement('tr');
                    for (const [key, label] of [['nr_palety','Nr palety'],['nazwa','Nazwa'],['lokalizacja','Lokalizacja'],['data_przydatnosci','Ważność']]) {
                        const cell = document.createElement('td');
                        cell.dataset.label = label;
                        cell.style.padding = '5px';
                        cell.textContent = pallet[key] || '-';
                        if (key === 'data_przydatnosci') cell.style.color = '#ef4444';
                        row.appendChild(cell);
                    }
                    return row;
                });
                body.replaceChildren(...rows);
                body.dataset.snapshot = JSON.stringify(fefo);
            }
        }
    }
    let fingerprint;
    async function update() {
        if (busy || document.hidden || wanted === applied || wanted === null) return;
        busy = true;
        const version = wanted;
        try {
            const response = await fetch('/warehouse-v2/api/live/snapshot?linia=' + encodeURIComponent(LINIA), {credentials:'same-origin', cache:'no-store', silent:true});
            if (!response.ok) throw new Error('snapshot ' + response.status);
            const data = await response.json();
            if (!data.success || !Array.isArray(data.items)) throw new Error('Invalid snapshot');
            const normalized = normalize(data.items);
            const next = JSON.stringify(normalized);
            if (next !== fingerprint) {
                allWarehouseItems = normalized;
                if (typeof populateLocationFilter === 'function') populateLocationFilter();
                filterTable({preserveScroll:true});
                const emptyState = document.getElementById('warehouseEmptyState');
                if (emptyState) emptyState.hidden = normalized.length > 0;
                fingerprint = next;
            }
            updateSummary(data.stats, data.fefo);
            applied = version;
        } catch (error) {
            console.warn('[WarehouseLive]', error);
            if (!retry) retry = setTimeout(() => {retry = null; update();}, 10000);
        } finally {
            busy = false;
        }
        if (wanted !== applied && applied === version) update();
    }
    function connect() {
        if (window.__rpNavigating || events || document.hidden || !window.EventSource) return;
        events = new EventSource('/warehouse-v2/api/live/events');
        events.addEventListener('warehouse-change', event => {
            wanted = event.data;
            if (!scheduled && wanted !== applied) scheduled = setTimeout(() => { scheduled = null; update(); }, 150);
        });
    }
    function disconnect() {
        if (events) events.close();
        events = null;
        if (retry) clearTimeout(retry);
        if (scheduled) clearTimeout(scheduled);
        scheduled = null;
        retry = null;
    }
    document.addEventListener('DOMContentLoaded', () => {
        fingerprint = JSON.stringify(normalize(allWarehouseItems));
        connect();
    });
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) disconnect();
        else { connect(); update(); }
    });
    window.addEventListener('rp:navigation-start', disconnect);
    window.addEventListener('rp:navigation-cancelled', connect);
    window.addEventListener('pagehide', disconnect);
    window.addEventListener('pageshow', connect);
}());
