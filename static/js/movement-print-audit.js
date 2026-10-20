/* Tracks print intent, never claims physical printer delivery. */
(() => {
    'use strict';
    const config = document.getElementById('movement-print-audit');
    if (!config) return;
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
