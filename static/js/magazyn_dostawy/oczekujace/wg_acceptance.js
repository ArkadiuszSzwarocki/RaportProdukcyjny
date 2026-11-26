function parseWeightValue(value) {
    const normalized = String(value || '').trim().replace(',', '.');
    const parsed = parseFloat(normalized);
    return Number.isFinite(parsed) ? parsed : NaN;
}

let currentWgAcceptLine = 'PSD';

function acceptWG(id, nrPalety, wagaNetto = null, linia = null) {
    document.getElementById('wgId').value = id;
    document.getElementById('wgNrPalety').innerText = nrPalety;
    currentWgAcceptLine = linia || (String(nrPalety || '').startsWith('AGR') ? 'AGRO' : window.MAGAZYN_CONFIG.linia);
    const wagaInput = document.getElementById('wgWaga');
    if (wagaInput) {
        if (wagaNetto === null || wagaNetto === undefined || wagaNetto === '' || Number.isNaN(Number(wagaNetto))) {
            wagaInput.value = '';
        } else {
            wagaInput.value = Number(wagaNetto).toFixed(2);
        }
    }
    const locInput = document.getElementById('wgLokalizacja');
    if (locInput) {
        locInput.value = '';
    }
    document.getElementById('modalWG').showModal();

    if (wagaInput) {
        wagaInput.focus();
        wagaInput.select();
    }
}

function submitAcceptWG() {
    const id = document.getElementById('wgId').value;
    const wagaValue = parseWeightValue(document.getElementById('wgWaga').value);
    const lok = normalizeLocationCode(document.getElementById('wgLokalizacja').value);
    if (!Number.isFinite(wagaValue) || wagaValue <= 0) {
        AppDialog.alert('Podaj poprawną wagę netto palety (większą od 0).');
        return;
    }
    if (!lok) {
        AppDialog.alert('Podaj lokalizację');
        return;
    }

    fetch('/magazyn-dostawy/api/przyjmij-wg', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ id: id, nr_palety: document.getElementById('wgNrPalety').innerText, lokalizacja: lok, linia: currentWgAcceptLine, waga: wagaValue })
    }).then(r => r.json()).then(res => {
        if (res.success) {
            performSilentRefresh(); closeModal('modalWG');
            if (res.open_report_url) {
                var win = window.open(res.open_report_url, '_blank');
                if (!win || win.closed || typeof win.closed === 'undefined') {
                    window.location.href = res.open_report_url;
                }
            }
        } else {
            AppDialog.alert(res.error || 'Błąd zapisu');
        }
    });
}

async function deletePendingWG(id, nrPalety, linia) {
    const label = nrPalety || `ID=${id}`;
    const targetLine = linia || (String(nrPalety || '').startsWith('AGR') ? 'AGRO' : (window.MAGAZYN_CONFIG && window.MAGAZYN_CONFIG.linia) || 'PSD');
    const confirmed = await AppDialog.confirm(`Czy na pewno usunąć oczekującą paletę ${label} z bufora produkcji (${targetLine})?`);
    if (!confirmed) {
        return;
    }

    try {
        const res = await fetch(`/api/usun_palete_ajax?linia=${encodeURIComponent(targetLine)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ id: id, linia: targetLine })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            if (typeof performSilentRefresh === 'function') {
                await performSilentRefresh();
            } else {
                location.reload();
            }
            return;
        }
        AppDialog.alert(data.message || data.error || 'Nie udało się usunąć oczekującej palety.');
    } catch (e) {
        AppDialog.alert('Błąd połączenia z serwerem.');
    }
}


