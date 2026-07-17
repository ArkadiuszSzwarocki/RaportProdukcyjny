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
    if(isNaN(weight)) return alert('Podaj poprawną wagę!');
    
    if(btn) { btn.innerHTML = '<span class="material-icons">hourglass_top</span>'; btn.style.background='#94a3b8'; }

    smartFetch(window.INVENTORY_CONFIG.url_zapisz_wpis, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            sesja_id: window.INVENTORY_CONFIG.sesjaId,
            paleta_id: pallet.id,
            nr_palety: pallet.nr_palety,
            typ_palety: pallet.typ_palety,
            nazwa: pallet.nazwa,
            lokalizacja: lastLocation,
            nr_partii: pallet.nr_partii,
            waga_systemowa: pallet.stan_magazynowy,
            waga_faktyczna: weight,
            linia: pallet.linia,
            data_produkcji: pallet.data_produkcji,
            data_przydatnosci: pallet.data_przydatnosci,
            jednostka: unit || 'kg'
        })
    })
    .then(r => r.json())
    .then(data => {
        if(data.success) {
            if(weight <= 0) {
                // Wizualnie usuń: przekreślenie, czerwone, szary przycisk
                cardElement.style.opacity = '0.6';
                if(btn) { btn.innerHTML='<span class="material-icons">delete_forever</span>'; btn.style.background='#ef4444'; }
            } else {
                cardElement.style.borderColor = '#10b981';
                cardElement.style.background = '#f0fdf4';
                if(btn) { btn.innerHTML='<span class="material-icons">done_all</span>'; btn.style.background='#059669'; }
            }
        } else {
            if(btn) { btn.innerHTML='<span class="material-icons">error</span>'; btn.style.background='#ef4444'; }
            alert('Błąd zapisu: ' + (data.message || data.error || 'Nieznany'));
        }
    }).catch(() => {
        if(btn) { btn.innerHTML='<span class="material-icons">save</span>'; btn.style.background='#10b981'; }
    });
}


function finishInventory() {
    if(confirm('Zakończyć sesję inwentaryzacji #' + window.INVENTORY_CONFIG.sesjaId + '?\n\nSesja zostanie zamknięta. Możesz ją potem zatwierdzić z raportu.')) {
        smartFetch('/magazyn/inwentaryzacja/api/zamknij-sesje', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({sesja_id: window.INVENTORY_CONFIG.sesjaId})
        }).then(r=>r.json()).then(data => {
            if(data.success) {
                window.location.href = window.INVENTORY_CONFIG.url_raport;
            } else {
                alert('Błąd: ' + (data.message || data.error));
            }
        });
    }
}


