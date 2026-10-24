/* Tracks print intent, never claims physical printer delivery. */
(() => {
    'use strict';
    const config = document.getElementById('movement-print-audit');
    if (!config || new URLSearchParams(location.search).get('internal_print') === '1') return;
    const documents = JSON.parse(config.textContent);
    if (!documents.length) { window.printMovementReport = () => window.print(); return; }
    let explicitPrint = false;
    let waiting = false;
    function payload(trigger) {
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
        const eventId = `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
        return JSON.stringify({event_id:eventId,documents,trigger});
    }
    window.printMovementReport = async function(trigger = 'button') {
        if (waiting) return;
        waiting = true;
        try {
            const response = await fetch('/magazyn-dostawy/api/print-requests', {
                method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
                body:payload(trigger)
            });
            if (!response.ok || !(await response.json()).success) {
                throw new Error('Nie zapisano historii wydruku. Odśwież logowanie lub spróbuj ponownie.');
            }
            explicitPrint = true;
            window.print();
        } catch (error) {
            alert(error.message || 'Nie udało się zapisać kliknięcia Drukuj.');
        } finally {
            waiting = false;
        }
    };
    window.addEventListener('afterprint', () => { explicitPrint = false; });
    window.addEventListener('beforeprint', () => {
        if (explicitPrint) return;
        explicitPrint = true;
        const body = payload('browser');
        if (typeof navigator.sendBeacon !== 'function' || !navigator.sendBeacon('/magazyn-dostawy/api/print-requests', new Blob([body], {type:'application/json'}))) {
            fetch('/magazyn-dostawy/api/print-requests', {method:'POST',credentials:'same-origin',
                headers:{'Content-Type':'application/json'},body,keepalive:true}).catch(() => {});
        }
    });
})();

/* Tracked print is opt-in. Browser printing remains available with intent-only audit. */
(() => {
    const config = document.getElementById('movement-print-audit');
    if (!config || new URLSearchParams(location.search).get('internal_print') === '1') return;
    const documents = JSON.parse(config.textContent);
    const anchor = document.querySelector('button[onclick*="printMovementReport"]');
    if (!anchor || !documents.length) return;
    const box = document.createElement('div');
    box.className = 'movement-tracked-controls';
    box.style.cssText = 'padding:12px;margin:12px 0;border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc;color:#0f172a;font:14px Arial;text-align:left';
    const title = document.createElement('strong');
    title.textContent = 'Druk A4 z monitorowaniem';
    const label = document.createElement('label');
    label.textContent = ' Drukarka: ';
    const select = document.createElement('select');
    select.setAttribute('aria-label', 'Drukarka A4 do monitorowanego wydruku');
    select.disabled = true;
    const button = document.createElement('button');
    button.type = 'button'; button.disabled = true;
    button.textContent = 'Wyślij i monitoruj';
    const note = document.createElement('p');
    note.setAttribute('role', 'status'); note.setAttribute('aria-live', 'polite');
    note.style.cssText = 'margin:8px 0 0;white-space:normal';
    note.textContent = 'Sprawdzanie konfiguracji drukarek A4…';
    label.append(select); box.append(title, label, button, note);
    anchor.parentNode.insertBefore(box, anchor.nextSibling);
    const printStyle = document.createElement('style');
    printStyle.textContent = '@media print{.movement-tracked-controls{display:none!important}}';
    document.head.append(printStyle);
    let attempts = 0;
    const terminal = new Set(['DEVICE_COMPLETED','DEVICE_WARNING','FAILED','CANCELLED']);
    const show = job => {
        note.textContent = `${job.status_name}. ${job.note} Drukarka: ${job.printer_label}.` +
            (job.spool_id ? ` Numer zadania Windows: ${job.spool_id}.` : '') + ` Identyfikator: ${job.request_id}`;
    };
    async function poll(id) {
        try {
            const response = await fetch(`/magazyn-dostawy/api/tracked-print/${encodeURIComponent(id)}`, {credentials:'same-origin'});
            const body = await response.json();
            if (!response.ok || !body.success) throw new Error('Nie odczytano statusu. Sprawdź historię druku przed ponowieniem.');
            show(body.job);
            if (terminal.has(body.job.status)) return;
        } catch (error) { note.textContent = error.message + ` Identyfikator: ${id}`; }
        if (++attempts < 24) setTimeout(() => poll(id), 5000);
        else note.append(' Automatyczne odświeżanie zakończone. Dalszy status sprawdzisz w Historii druku przesunięć.');
    }
    button.addEventListener('click', async () => {
        button.disabled = true; select.disabled = true;
        const id = crypto.randomUUID ? crypto.randomUUID() : '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, c => (Number(c) ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> Number(c) / 4).toString(16));
        note.textContent = 'Przygotowanie zadania…';
        try {
            const response = await fetch('/magazyn-dostawy/api/tracked-print', {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({event_id:id,documents,printer_key:select.value})});
            const body = await response.json();
            if (!response.ok || !body.success) throw new Error(body.error || 'Niepewny wynik wysłania. Sprawdź historię przed ponowieniem.');
            show(body.job); poll(id);
        } catch (error) {
            note.textContent = `${error.message} Identyfikator: ${id}. Nie ponowiono automatycznie.`;
        }
    });
    fetch('/magazyn-dostawy/api/tracked-print/options', {credentials:'same-origin'})
        .then(async response => {
            const body = await response.json();
            if (!response.ok || !body.success) throw new Error(body.error || 'Nie odczytano konfiguracji drukarek A4.');
            if (!body.printers.length) {
                note.textContent = 'Przygotowane do konfiguracji Brothera. Brak aktywnej drukarki A4 — potrzebne dane urządzenia. Dotychczasowy druk z przeglądarki działa bez potwierdzenia odbioru.';
                return;
            }
            if (documents.length > 20) {
                note.textContent = 'Wybierz maksymalnie 20 dokumentów na zadanie monitorowane.';
                return;
            }
            for (const printer of body.printers) {
                const option = document.createElement('option'); option.value = printer.key; option.textContent = printer.label; select.append(option);
            }
            select.disabled = false; button.disabled = false;
            note.textContent = 'Wyślij raport przez mostek. Zakończenie pokażemy wyłącznie zgodnie z otrzymanym statusem; nie uruchamia to okna druku przeglądarki.';
        }).catch(error => { note.textContent = error.message; });
})();
