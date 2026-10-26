/* Station history loads only on entry or a filter change; stale responses cannot replace newer results. */
(function () {
    'use strict';
    function init() {
        const form = document.getElementById('stationHistoryFilters');
        if (!form || form.dataset.initialized) return;
        form.dataset.initialized = '1';
        const body = document.getElementById('stationHistoryTableBody');
        const count = document.getElementById('stationHistoryCount');
        const status = document.getElementById('stationHistoryStatus');
        const fields = {
            linia: 'historyFilterLinia', dataOd: 'historyFilterDataOd', dataDo: 'historyFilterDataDo',
            typ_operacji: 'historyFilterTyp', surowiec: 'historyFilterSurowiec',
            stacja: 'historyFilterStacja', limit: 'historyFilterLimit'
        };
        let pending = null;
        let sequence = 0;
        let debounce = null;
        const initial = new URLSearchParams(window.location.search);
        Object.entries(fields).forEach(([key, id]) => {
            if (initial.has(key)) document.getElementById(id).value = initial.get(key);
        });
        function node(tag, className, text) {
            const result = document.createElement(tag);
            if (className) result.className = className;
            if (text !== undefined) result.textContent = String(text);
            return result;
        }
        function message(text, error) {
            const row = node('tr');
            const cell = node('td', 'station-history-message' + (error ? ' station-history-error' : ''), text);
            cell.colSpan = 7;
            row.appendChild(cell);
            body.replaceChildren(row);
        }
        function operation(row) {
            const raw = String(row.typ || 'Operacja');
            const type = raw.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
            const categories = [
                [/czyszcz|clean/, 'Czyszczenie', 'cleaning'], [/dosyp/, 'Dosypka', 'batch'],
                [/zasyp|bufor/, 'Zasyp', 'batch'], [/usun/, 'Usunięcie', 'removal'],
                [/przywroc/, 'Przywrócenie', 'reception'], [/przeklasyfik|reclass/, 'Przeklasyfikowanie', 'movement'],
                [/dostawa|\bpz\b/, 'Dostawa / PZ', 'reception'], [/utworz/, 'Utworzenie palety', 'reception'],
                [/przyjecie|\bpw\b/, 'Przyjęcie / PW', 'reception'], [/podzial/, 'Podział palety', 'movement'],
                [/przesuni|transfer|relokac|ruch/, 'Przesunięcie', 'movement'], [/wydanie|produkcja/, 'Wydanie na produkcję', 'movement']
            ];
            const match = categories.find(([pattern]) => pattern.test(type));
            const badge = node('span', 'station-history-operation ' + (match ? match[2] : ''), match ? match[1] : raw);
            badge.title = row.komentarz && row.komentarz !== '-' ? raw + ': ' + row.komentarz : raw;
            return badge;
        }
        function render(rows) {
            const fragment = document.createDocumentFragment();
            rows.forEach(row => {
                const tr = node('tr');
                const dateText = String(row.data || '-').replace(/^(\d{4})-(\d{2})-(\d{2})/, '$3.$2.$1');
                tr.appendChild(node('td', 'station-history-code', dateText));
                const routeCell = node('td');
                const route = node('div', 'station-history-route');
                let location = String(row.stacja || '');
                if (!/->|→/.test(location) && row.skad && row.dokad && row.skad !== '-' && row.dokad !== '-' && row.skad !== row.dokad) {
                    location = row.skad + ' -> ' + row.dokad;
                }
                location.split(/->|→/).map(part => part.trim()).forEach((part, index) => {
                    if (index) route.appendChild(node('span', '', '→'));
                    const production = /^(BB|MZ|WZ|KO|ZB|MIX|LP)\d+$/i.test(part);
                    route.appendChild(node('span', 'station-history-location ' + (production ? 'production' : (index ? 'destination' : '')), part || '-'));
                });
                routeCell.appendChild(route);
                tr.appendChild(routeCell);
                tr.appendChild(node('td', 'station-history-product', row.nazwa && row.nazwa !== '-' ? row.nazwa : 'Nieokreślony'));
                tr.appendChild(node('td', 'station-history-code', row.nr_palety || '-'));
                const quantity = Number(row.ilosc);
                tr.appendChild(node('td', 'station-history-quantity', row.ilosc != null && Number.isFinite(quantity) ? quantity.toLocaleString('pl-PL', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '-'));
                const details = node('td');
                details.appendChild(operation(row));
                if (row.komentarz && row.komentarz !== '-') {
                    const comment = node('div', 'station-history-comment', row.komentarz);
                    comment.title = row.komentarz;
                    details.appendChild(comment);
                }
                tr.appendChild(details);
                tr.appendChild(node('td', '', row.user || '-'));
                fragment.appendChild(tr);
            });
            body.replaceChildren(fragment);
        }
        async function load() {
            clearTimeout(debounce);
            const version = ++sequence;
            if (pending) pending.abort();
            const values = Object.fromEntries(Object.entries(fields).map(([key, id]) => [key, document.getElementById(id).value.trim()]));
            if (values.dataOd && values.dataDo && values.dataOd > values.dataDo) {
                message('Data od nie może być późniejsza niż data do.', true);
                count.textContent = 'Wpisy: —';
                status.textContent = '';
                return;
            }
            values.stacja = values.stacja.toUpperCase();
            if (!values.stacja && /^(BB|MZ|WZ|KO|ZB|MIX|LP|MGW|MS|MP)\s*\d{1,3}$/i.test(values.surowiec)) {
                values.stacja = values.surowiec.replace(/\s/g, '').toUpperCase();
                values.surowiec = '';
            }
            const query = new URLSearchParams();
            Object.entries(values).forEach(([key, value]) => { if (value && value !== 'ALL') query.set(key, value); });
            if (values.linia === 'ALL') query.set('linia', 'ALL');
            const page = new URL(window.location.href);
            page.search = query.toString();
            window.history.replaceState(null, '', page.toString());
            const controller = new AbortController();
            pending = controller;
            let timedOut = false;
            const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 25000);
            message('Ładowanie historii…', false);
            count.textContent = 'Wpisy: —';
            status.textContent = 'Pobieranie danych…';
            try {
                const response = await fetch('/warehouse-v2/historia-stacji/data?' + query.toString(), {cache: 'no-store', signal: controller.signal});
                const data = await response.json();
                if (version !== sequence || controller.signal.aborted) return;
                if (!response.ok || !data.success || !Array.isArray(data.data)) throw Error(data.error || data.message || 'Nie udało się pobrać historii.');
                if (data.data.length) render(data.data);
                else message('Brak wpisów dla wybranej stacji i filtrów.', false);
                count.textContent = 'Wpisy: ' + data.data.length;
                status.textContent = (values.linia === 'ALL' ? 'Wszystkie hale' : values.linia) + (values.stacja ? ' · Stacja: ' + values.stacja : '') +
                    (data.data.length >= Number(values.limit) ? ' · Osiągnięto limit wyników — zawęź filtry lub zwiększ limit.' : '');
            } catch (error) {
                if (version !== sequence || (error.name === 'AbortError' && !timedOut)) return;
                message(timedOut ? 'Pobieranie trwało zbyt długo. Zawęź zakres dat i spróbuj ponownie.' : error.message || 'Błąd połączenia z serwerem.', true);
                status.textContent = '';
            } finally {
                clearTimeout(timeout);
                if (version === sequence) pending = null;
            }
        }
        function localDate(value) {
            return value.getFullYear() + '-' + String(value.getMonth() + 1).padStart(2, '0') + '-' + String(value.getDate()).padStart(2, '0');
        }
        form.addEventListener('submit', event => { event.preventDefault(); load(); });
        ['historyFilterSurowiec', 'historyFilterStacja'].forEach(id => {
            document.getElementById(id).addEventListener('input', () => {
                clearTimeout(debounce);
                // Invalidate immediately so an earlier response cannot flash unfiltered rows while typing.
                ++sequence;
                if (pending) pending.abort();
                debounce = setTimeout(load, 350);
            });
        });
        ['historyFilterLinia', 'historyFilterDataOd', 'historyFilterDataDo', 'historyFilterTyp', 'historyFilterLimit'].forEach(id => {
            document.getElementById(id).addEventListener('change', load);
        });
        document.querySelectorAll('[data-history-days]').forEach(button => button.addEventListener('click', () => {
            const days = Number(button.dataset.historyDays);
            const today = new Date();
            const start = new Date(today);
            start.setDate(today.getDate() - (days > 0 ? days - 1 : 0));
            document.getElementById('historyFilterDataOd').value = localDate(start);
            document.getElementById('historyFilterDataDo').value = localDate(today);
            load();
        }));
        document.getElementById('clearHistoryDates').addEventListener('click', () => {
            document.getElementById('historyFilterDataOd').value = '';
            document.getElementById('historyFilterDataDo').value = '';
            load();
        });
        window.addEventListener('pagehide', () => { ++sequence; clearTimeout(debounce); if (pending) pending.abort(); });
        load();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
