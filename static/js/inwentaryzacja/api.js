function fetchProductNames(typ = '') {
    const url = window.INVENTORY_CONFIG.url_podpowiedzi_nazw + (typ ? '?typ=' + encodeURIComponent(typ) : '');
    fetch(url)
    .then(r => r.json())
    .then(data => {
        if(data.success) {
            const list = document.getElementById('productList');
            list.innerHTML = '';
            data.names.forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                list.appendChild(opt);
            });
        }
    });
}


function saveEntry(pallet, actualWeight, cardElement, btn, unit) {
    const weight = parseFloat(actualWeight);
    if(isNaN(weight)) {
        if (typeof safeToast === 'function') safeToast('Podaj poprawną wagę!', 'error');
        else alert('Podaj poprawną wagę!');
        return;
    }
    
    if(btn) { btn.innerHTML = '<span class="material-icons">hourglass_top</span>'; btn.style.background='#94a3b8'; }

    const loc = pallet.lokalizacja || lastLocation || (window.INVENTORY_CONFIG && window.INVENTORY_CONFIG.targetLokalizacja) || '';

    const payload = {
        sesja_id: window.INVENTORY_CONFIG.sesjaId,
        paleta_id: pallet.id || pallet.paleta_id,
        nr_palety: pallet.nr_palety,
        typ_palety: pallet.typ_palety || pallet.typ || 'surowiec',
        nazwa: pallet.nazwa || pallet.produkt,
        lokalizacja: loc,
        nr_partii: pallet.nr_partii,
        waga_systemowa: pallet.stan_magazynowy !== undefined ? pallet.stan_magazynowy : (pallet.waga_systemowa || 0),
        waga_faktyczna: weight,
        linia: pallet.linia || 'PSD',
        data_produkcji: pallet.data_produkcji,
        data_przydatnosci: pallet.data_przydatnosci,
        jednostka: unit || pallet.jednostka || 'kg'
    };

    fetch(window.INVENTORY_CONFIG.url_zapisz_wpis, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(data => {
        if(data.success) {
            if(weight <= 0) {
                // Wizualnie usuń: przekreślenie, czerwone, szary przycisk
                if(cardElement) cardElement.style.opacity = '0.6';
                if(btn) { btn.innerHTML='<span class="material-icons">delete_forever</span>'; btn.style.background='#ef4444'; }
                if(typeof safeToast === 'function') safeToast('Zapisano: USUNIĘTO (0 kg)', 'info');
            } else {
                if(cardElement) {
                    cardElement.style.borderColor = '#10b981';
                    cardElement.style.background = '#f0fdf4';
                }
                if(btn) { btn.innerHTML='<span class="material-icons">done_all</span>'; btn.style.background='#059669'; }
                if(typeof safeToast === 'function') safeToast(`✅ Zapisano: ${weight} ${unit || 'kg'}`, 'success');
            }
        } else {
            if(btn) { btn.innerHTML='<span class="material-icons">error</span>'; btn.style.background='#ef4444'; }
            if(typeof safeToast === 'function') safeToast('Błąd zapisu: ' + (data.message || data.error || 'Nieznany'), 'error');
            else alert('Błąd zapisu: ' + (data.message || data.error || 'Nieznany'));
        }
    }).catch(err => {
        console.error('saveEntry error:', err);
        if(btn) { btn.innerHTML='<span class="material-icons">save</span>'; btn.style.background='#10b981'; }
        if(typeof safeToast === 'function') safeToast('Błąd połączenia podczas zapisu', 'error');
    });
}



function finishInventory() {
    AppDialog.confirm(
        `Czy na pewno chcesz <b>zakończyć sesję inwentaryzacji #${window.INVENTORY_CONFIG.sesjaId}</b>?<br><br>` +
        `Po zakończeniu sesja zostanie zamknięta i wygenerowany zostanie raport różnic.`,
        'Zakończ inwentaryzację'
    ).then(confirmed => {
        if (!confirmed) return;
        
        safeToast('Zamykanie sesji...', 'info');
        const url = window.INVENTORY_CONFIG.url_zakoncz_sesje || '/magazyn/inwentaryzacja/api/zamknij-sesje';
        
        fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({sesja_id: window.INVENTORY_CONFIG.sesjaId})
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                safeToast('✅ Sesja została pomyślnie zakończona!', 'success');
                setTimeout(() => {
                    window.location.href = window.INVENTORY_CONFIG.url_raport;
                }, 400);
            } else {
                AppDialog.alert(data.message || data.error || 'Nie udało się zamknąć sesji.', 'Błąd');
            }
        })
        .catch(err => {
            console.error('finishInventory error:', err);
            AppDialog.alert('Błąd połączenia podczas zamykania sesji.', 'Błąd sieci');
        });
    });
}



