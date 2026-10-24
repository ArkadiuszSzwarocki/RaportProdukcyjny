(() => {
    const terminal = new Set(['DEVICE_COMPLETED','DEVICE_WARNING','FAILED','CANCELLED']);
    const rows = [...document.querySelectorAll('[data-tracked-job]')].filter(row => !terminal.has(row.dataset.status));
    let rounds = 0;
    async function refresh() {
        // One lookup per unique task, even when a batch contains many documents.
        const ids = [...new Set(rows.filter(row => !terminal.has(row.dataset.status)).map(row => row.dataset.trackedJob))];
        for (const id of ids) {
            try {
                const response = await fetch(`/magazyn-dostawy/api/tracked-print/${encodeURIComponent(id)}`,{credentials:'same-origin'});
                const body = await response.json();
                if (!response.ok || !body.success) throw new Error('Status zadania chwilowo niedostępny.');
                for (const row of rows.filter(item => item.dataset.trackedJob === id)) {
                    row.dataset.status = body.job.status;
                    row.querySelector('.tracked-status').textContent = body.job.status_name;
                    row.querySelector('.tracked-note').textContent = body.job.note;
                    row.querySelector('.tracked-spool').textContent = body.job.spool_id ? `Zadanie Windows: ${body.job.spool_id}` : '';
                }
            } catch (error) {
                for (const row of rows.filter(item => item.dataset.trackedJob === id)) row.querySelector('.tracked-note').textContent = error.message + ' Wynik wydruku niepotwierdzony.';
            }
        }
        if (++rounds < 12 && ids.length) setTimeout(refresh,15000);
    }
    if (rows.length) refresh();
})();
