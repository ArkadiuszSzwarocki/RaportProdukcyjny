function fetchHistory() {

    if(!currentPallet.id) return;
    
    document.getElementById('modalHistoryContainer').style.display = 'block';
    document.getElementById('modalHistoryList').innerHTML = '<li style="color: #64748b;">Ładowanie...</li>';
    
    fetch(`/magazyny-nowe/api/pallet/history?id=${currentPallet.id}&type=${currentPallet.type}&linia=${currentPallet.linia}`)
    .then(r => r.json())
    .then(data => {
        const list = document.getElementById('modalHistoryList');
        list.innerHTML = '';
        if(data.success && data.history.length > 0) {
            data.history.forEach(h => {
                list.innerHTML += `<li style="border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    <strong style="color: #0f172a;">${h.autor_data}</strong> [${h.autor_login}]: <span style="color: #2563eb; font-weight: 600;">${h.typ_ruchu}</span>
                    <br><span style="color: #475569;">${h.komentarz || ''}</span>
                </li>`;
            });
        } else {
            list.innerHTML = '<li style="color: #64748b;">Brak historii dla tej palety.</li>';
        }
    });
}


