function searchLocation() {
    const rawLoc = document.getElementById('lokalizacjaInput').value.trim().toUpperCase();
    if(!rawLoc) return;
    
    // Zabezpieczenie przed zeskanowaniem palety jako lokalizacji
    // Usuwamy znaki specjalne (np. nawiasy (00), prefiksy GS1 ]C1) i sprawdzamy czy ma 15+ cyfr
    const digitsOnly = rawLoc.replace(/\D/g, '');
    const isPalletPrefix = /^(SUR|AGR|PSD|OP|P\d)\d+/.test(rawLoc);
    
    if (digitsOnly.length >= 15 || rawLoc.includes('00359') || isPalletPrefix) {
        safeToast('Błąd: Oczekiwano LOKALIZACJI, a nie palety!', 'error');
        if (typeof AppDialog !== 'undefined') {
            AppDialog.alert('Zeskanowałeś kod palety zamiast lokalizacji. Najpierw zeskanuj LOKALIZACJĘ (np. R010101, MGW01)!', 'Zła kolejność skanowania');
        }
        document.getElementById('lokalizacjaInput').value = '';
        return;
    }
    
    // Check if it's a Rack (e.g. "R01", "R-01" or similar length 3-4)
    if(rawLoc.startsWith('R') && rawLoc.length >= 3 && rawLoc.length <= 4) {
        loadRack(rawLoc);
        return;
    }

    // If we are in Rack mode and scan a slot, handle it locally
    if(currentRackPrefix && rawLoc.startsWith(currentRackPrefix) && rawLoc.length >= 6) {
        highlightAndOpenSlot(rawLoc);
        document.getElementById('lokalizacjaInput').value = ''; // clear for next scan
        return;
    }
    
    lastLocation = rawLoc;
    currentRackPrefix = '';
    localStorage.setItem('lastInventoryLoc', rawLoc);
    localStorage.removeItem('lastInventoryRack');
    
    // BLIND INVENTORY MODE - do not show existing pallets
    document.getElementById('locationSearchCard').style.display = 'none';
    document.getElementById('rackContainer').style.display = 'none';
    document.getElementById('resultsContainer').style.display = 'none';
    
    const blindContainer = document.getElementById('blindScanContainer');
    if (blindContainer) {
        blindContainer.style.display = 'block';
        document.getElementById('blindActiveLocation').textContent = rawLoc;
        
        // Clear previous session scanned items list from UI for new location
        document.getElementById('blindScannedItems').innerHTML = '';
        
        const banner = document.getElementById('floatingFinishBanner');
        if (banner) banner.style.display = 'flex';
        
        setTimeout(() => {
            const ssccInput = document.getElementById('blindSsccInput');
            if(ssccInput) ssccInput.focus();
        }, 100);
    }
}

// Globalna zmienna na dane aktualnie skanowanej palety w trybie ślepym

function handleBlindSSCCScan(sscc) {
    if(!sscc) return;
    sscc = sscc.trim().toUpperCase();
    
    safeToast('Szukanie palety w systemie...', 'info');
    fetch(window.INVENTORY_CONFIG.url_szukaj_globalnie, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({sscc: sscc})
    })
    .then(r => r.json())
    .then(data => {
        if(data.success && data.paleta) {
            currentBlindPallet = data.paleta;
            document.getElementById('blindModalSscc').textContent = sscc;
            document.getElementById('blindModalNazwa').textContent = data.paleta.nazwa || 'Brak nazwy';
            document.getElementById('blindModalWagaSys').textContent = (data.paleta.waga || 0) + ' kg';
            
            document.getElementById('blindWeightInput').value = data.paleta.waga || '';
            document.getElementById('blindWeightModal').style.display = 'flex';
            setTimeout(() => {
                document.getElementById('blindWeightInput').focus();
                document.getElementById('blindWeightInput').select();
            }, 100);
        } else {
            AppDialog.alert(`Paleta z kodem <b>${sscc}</b> NIE ZNAJDUJE SIĘ w bazie systemu.<br><br>Dodaj ją ręcznie klikając "DODAJ PALETĘ".`, 'Brak palety').then(() => {
                document.getElementById('blindSsccInput').focus();
            });
        }
    }).catch(e => {
        AppDialog.alert('Błąd połączenia podczas szukania palety.', 'Błąd');
        document.getElementById('blindSsccInput').focus();
    });
}


function submitBlindWeight() {
    const weightVal = document.getElementById('blindWeightInput').value;
    if (weightVal === '') {
        safeToast('Podaj wagę!', 'error');
        return;
    }
    
    if (!currentBlindPallet) return;
    
    const waga_faktyczna = parseFloat(weightVal);
    const targetLoc = lastLocation;
    const paleta = currentBlindPallet;
    
    let mapTyp = 'PAL';
    const t = (paleta.typ || '').toLowerCase();
    if(t.includes('surowiec')) mapTyp = 'surowiec';
    else if(t.includes('opakowanie')) mapTyp = 'opakowanie';
    else if(t.includes('dodatek')) mapTyp = 'dodatek';

    safeToast('Zapisywanie...', 'info');
    document.getElementById('blindWeightModal').style.display = 'none';

    smartFetch(window.INVENTORY_CONFIG.url_zapisz_wpis, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            sesja_id: window.INVENTORY_CONFIG.sesjaId,
            paleta_id: paleta.id,
            nr_palety: paleta.nr_palety,
            typ_palety: mapTyp,
            nazwa: paleta.nazwa,
            lokalizacja: targetLoc,
            nr_partii: paleta.nr_partii || 'BRAK',
            waga_systemowa: paleta.waga || 0,
            waga_faktyczna: waga_faktyczna,
            data_produkcji: paleta.data_produkcji || '',
            data_przydatnosci: paleta.data_przydatnosci || '',
            linia: paleta.linia,
            typ_opakowania: '',
            jednostka: paleta.jednostka || 'kg'
        })
    }).then(r => r.json()).then(saveData => {
        if (saveData.success) {
            safeToast('✅ Zapisano!', 'success');
            
            // Add to blindScannedItems list visually
            const list = document.getElementById('blindScannedItems');
            const item = document.createElement('div');
            item.style.padding = '10px';
            item.style.background = '#fff';
            item.style.borderRadius = '8px';
            item.style.border = '1px solid #e2e8f0';
            item.style.display = 'flex';
            item.style.justifyContent = 'space-between';
            item.innerHTML = `
                <div>
                    <div style="font-size: 11px; font-weight: 700; color: #64748b;">${paleta.nr_palety || 'Brak SSCC'}</div>
                    <div style="font-size: 13px; font-weight: 800; color: #0f172a;">${paleta.nazwa}</div>
                </div>
                <div style="font-size: 14px; font-weight: 800; color: #10b981; display:flex; align-items:center;">
                    ${waga_faktyczna} kg
                </div>
            `;
            list.insertBefore(item, list.firstChild);
            
            currentBlindPallet = null;
            setTimeout(() => {
                document.getElementById('blindSsccInput').focus();
            }, 100);
        } else {
            AppDialog.alert(saveData.message || 'Błąd podczas zapisu.', 'Błąd').then(() => {
                document.getElementById('blindSsccInput').focus();
            });
        }
    }).catch(e => {
        AppDialog.alert('Błąd sieci podczas zapisu.', 'Błąd').then(() => {
            document.getElementById('blindSsccInput').focus();
        });
    });
}


