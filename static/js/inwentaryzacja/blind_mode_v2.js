function loadCountedBlindItems(loc) {
    const sesjaId = (window.INVENTORY_CONFIG && window.INVENTORY_CONFIG.sesjaId) || null;
    const list = document.getElementById('blindScannedItems');
    if (!list) return;
    
    fetch(window.INVENTORY_CONFIG.url_szukaj_lokalizacji, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ lokalizacja: loc, sesja_id: sesjaId })
    })
    .then(r => r.json())
    .then(data => {
        list.innerHTML = '';
        if (data.success && data.pallets) {
            const allPallets = data.pallets.filter(p => p.nazwa !== 'PUSTE GNIAZDO');
            const counted = allPallets.filter(p => p.counted);
            
            // Summary counter header
            const summaryDiv = document.createElement('div');
            summaryDiv.style.cssText = 'display:flex; justify-content:space-between; align-items:center; background:white; padding:10px 14px; border-radius:10px; border:1px solid #fed7aa; margin-bottom:10px;';
            summaryDiv.innerHTML = `
                <div style="font-size:13px; font-weight:800; color:#1e293b;">
                    Zeskanowano: <span style="color:#f97316; font-size:15px;">${counted.length} / ${allPallets.length}</span>
                </div>
                <div style="font-size:11px; font-weight:800; color:${counted.length === allPallets.length && allPallets.length > 0 ? '#10b981' : '#64748b'};">
                    ${counted.length === allPallets.length && allPallets.length > 0 ? '✅ KOMPLET' : `Pozostało: ${allPallets.length - counted.length}`}
                </div>
            `;
            list.appendChild(summaryDiv);
            
            if (allPallets.length === 0) {
                const emptyDiv = document.createElement('div');
                emptyDiv.style.cssText = 'color:#94a3b8; font-size:12px; text-align:center; padding:12px; background:white; border-radius:8px;';
                emptyDiv.textContent = 'Brak palet przypisanych do tej lokalizacji';
                list.appendChild(emptyDiv);
                return;
            }
            
            // Sort: counted first, then uncounted
            const sorted = [...allPallets].sort((a, b) => (b.counted ? 1 : 0) - (a.counted ? 1 : 0));
            
            sorted.forEach(p => {
                const item = document.createElement('div');
                const isCounted = p.counted;
                item.style.cssText = isCounted
                    ? 'padding:10px 12px; background:#f0fdf4; border-radius:10px; border:2px solid #10b981; display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;'
                    : 'padding:10px 12px; background:white; border-radius:10px; border:1px solid #e2e8f0; display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; opacity:0.85;';
                
                const icon = isCounted 
                    ? '<span class="material-icons" style="font-size:18px; color:#10b981;">check_circle</span>'
                    : '<span class="material-icons" style="font-size:18px; color:#cbd5e1;">radio_button_unchecked</span>';
                
                const statusText = isCounted
                    ? `<span style="font-size:14px; font-weight:900; color:#166534;">${p.waga_faktyczna} ${p.jednostka || 'kg'}</span>`
                    : `<span style="font-size:11px; font-weight:700; color:#94a3b8;">${p.stan_magazynowy || 0} ${p.jednostka || 'kg'}</span>`;
                
                item.innerHTML = `
                    <div style="display:flex; align-items:center; gap:8px; overflow:hidden; flex:1; padding-right:8px;">
                        ${icon}
                        <div style="overflow:hidden;">
                            <div style="font-size:13px; font-weight:800; color:${isCounted ? '#0f172a' : '#334155'}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${p.nazwa}</div>
                            <div style="font-size:10px; color:#64748b; font-family:monospace;">${p.nr_palety || p.displayId} ${p.nr_partii ? '| Partia: ' + p.nr_partii : ''}</div>
                        </div>
                    </div>
                    <div style="text-align:right; flex-shrink:0;">
                        ${statusText}
                    </div>
                `;
                list.appendChild(item);
            });
        }
    })
    .catch(err => {
        console.error('Błąd pobierania pozycji:', err);
    });
}


function searchLocation(locOverride) {
    const inputEl = document.getElementById('lokalizacjaInput');
    let rawLoc = (locOverride !== undefined && locOverride !== null ? String(locOverride) : (inputEl ? inputEl.value : '')).trim().toUpperCase();
    if (!rawLoc && lastLocation) {
        rawLoc = lastLocation.trim().toUpperCase();
    }
    if(!rawLoc) return;
    if (inputEl) inputEl.value = '';
    
    // Zabezpieczenie przed zeskanowaniem palety jako lokalizacji
    // Usuwamy znaki specjalne (np. nawiasy (00), prefiksy GS1 ]C1) i sprawdzamy czy ma 15+ cyfr
    const digitsOnly = rawLoc.replace(/\D/g, '');
    const isPalletPrefix = /^(SUR|AGR|PSD|OP|P\d)\d+/.test(rawLoc);
    
    if (digitsOnly.length >= 15 || rawLoc.includes('00359') || isPalletPrefix) {
        safeToast('Błąd: Oczekiwano LOKALIZACJI, a nie palety!', 'error');
        if (typeof AppDialog !== 'undefined') {
            AppDialog.alert('Zeskanowałeś kod palety zamiast lokalizacji. Najpierw zeskanuj LOKALIZACJĘ (np. R010101, MGW01)!', 'Zła kolejność skanowania');
        }
        if (inputEl) inputEl.value = '';
        return;
    }
    
    // 1. If it's a Rack code (e.g. "R01", "R-01", "R1", "R-1")
    if (isRackCode(rawLoc)) {
        const rackPrefix = normalizeRackPrefix(rawLoc);
        loadRack(rackPrefix);
        return;
    }

    // 2. If it's a Rack Slot code (e.g. "R010101", "R-01-01-01", "R10101")
    if (isLocationCode(rawLoc)) {
        const normalized = normalizeLocationCode(rawLoc);
        const rackPrefix = normalized.substring(0, 3);
        loadRack(rackPrefix, normalized);
        return;
    }

    const sesjaId = (window.INVENTORY_CONFIG && window.INVENTORY_CONFIG.sesjaId) || (window.inventoryConfig && window.inventoryConfig.sesjaId) || null;

    // Verify location against DB and session limits
    const verifyUrl = window.INVENTORY_CONFIG && window.INVENTORY_CONFIG.url_verify_location 
        ? window.INVENTORY_CONFIG.url_verify_location 
        : '/api/verify-location';
        
    fetch(verifyUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lokalizacja: rawLoc, sesja_id: sesjaId })
    })
    .then(r => r.json())
    .then(data => {
        if (!data.success) {
            safeToast(data.message, 'error');
            if (typeof AppDialog !== 'undefined') {
                AppDialog.alert(data.message, 'Błąd lokalizacji');
            }
            document.getElementById('lokalizacjaInput').value = '';
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
            
            // Load and display already scanned items for this session and location
            loadCountedBlindItems(rawLoc);
            
            const banner = document.getElementById('floatingFinishBanner');
            if(banner) banner.style.display = 'block';
            
            setTimeout(() => {
                const inp = document.getElementById('blindSsccInput');
                if (inp) {
                    inp.value = '';
                    inp.focus();
                }
            }, 300);
        }
    })
    .catch(err => {
        console.error('Verify error:', err);
        safeToast('Błąd weryfikacji lokalizacji.', 'error');
    });
}


// Globalna zmienna na dane aktualnie skanowanej palety w trybie ślepym

function handleBlindSSCCScan(sscc) {
    if(!sscc) return;
    sscc = sscc.trim().toUpperCase();
    
    safeToast('Szukanie palety w systemie...', 'info');
    fetch(window.INVENTORY_CONFIG.url_szukaj_globalnie, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            sscc: sscc,
            sesja_id: window.INVENTORY_CONFIG.sesjaId
        })
    })
    .then(r => r.json())
    .then(data => {
        if(data.success && data.paleta) {
            const pal = data.paleta;

            function openBlindWeight(prefillWeight) {
                currentBlindPallet = pal;
                document.getElementById('blindModalSscc').textContent = sscc;
                document.getElementById('blindModalNazwa').textContent = pal.nazwa || 'Brak nazwy';
                
                const wSysEl = document.getElementById('blindModalWagaSys');
                if (wSysEl) wSysEl.style.display = 'none'; // Ukryj wagę systemową w trybie ślepym
                
                const weightInp = document.getElementById('blindWeightInput');
                weightInp.value = prefillWeight !== undefined && prefillWeight !== null ? prefillWeight : '';
                weightInp.placeholder = 'Wpisz wagę...';
                
                if (!weightInp.dataset.enterBound) {
                    weightInp.dataset.enterBound = 'true';
                    weightInp.addEventListener('keydown', (e) => {
                        if (e.key === 'Enter') {
                            e.preventDefault();
                            submitBlindWeight();
                        }
                    });
                }
                
                document.getElementById('blindWeightModal').style.display = 'flex';
                setTimeout(() => {
                    weightInp.focus();
                    if (weightInp.value) weightInp.select();
                }, 100);
            }

            if (pal.already_counted) {
                AppDialog.confirm(
                    `⚠️ Ta paleta została już <b>wcześniej zważona</b> w tej sesji!<br><br>` +
                    `📦 <b>${pal.nazwa}</b><br>` +
                    `🏷️ SSCC: <b>${sscc}</b><br>` +
                    `⚖️ Poprzednia waga: <b style="color: #10b981;">${pal.previous_weight} kg</b><br><br>` +
                    `Czy chcesz <b>skorygować / zmienić wagę</b> tej palety?`,
                    'Paleta już zeskanowana'
                ).then(confirmed => {
                    if (confirmed) {
                        openBlindWeight(pal.previous_weight);
                    } else {
                        const inp = document.getElementById('blindSsccInput');
                        if (inp) {
                            inp.value = '';
                            inp.focus();
                        }
                    }
                });
            } else {
                openBlindWeight('');
            }
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



let isSubmittingBlind = false;

function submitBlindWeight() {
    if (isSubmittingBlind) return;

    const weightVal = document.getElementById('blindWeightInput').value;
    if (weightVal === '') {
        safeToast('Podaj wagę!', 'error');
        return;
    }
    
    if (!currentBlindPallet) return;
    
    isSubmittingBlind = true;
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

    fetch(window.INVENTORY_CONFIG.url_zapisz_wpis, {
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
            linia: paleta.linia || 'PSD',
            typ_opakowania: '',
            jednostka: paleta.jednostka || 'kg'
        })
    }).then(r => r.json()).then(saveData => {
        isSubmittingBlind = false;
        if (saveData.success) {
            safeToast('✅ Zapisano pomyślnie!', 'success');
            loadCountedBlindItems(targetLoc);
            currentBlindPallet = null;
            setTimeout(() => {
                const inp = document.getElementById('blindSsccInput');
                if (inp) {
                    inp.value = '';
                    inp.focus();
                }
            }, 100);
        } else {
            AppDialog.alert(saveData.message || 'Błąd podczas zapisu.', 'Błąd').then(() => {
                const inp = document.getElementById('blindSsccInput');
                if (inp) {
                    inp.value = '';
                    inp.focus();
                }
            });
        }
    }).catch(e => {
        isSubmittingBlind = false;
        console.error('Save error:', e);
        AppDialog.alert('Błąd sieci podczas zapisu.', 'Błąd').then(() => {
            const inp = document.getElementById('blindSsccInput');
            if (inp) {
                inp.value = '';
                inp.focus();
            }
        });
    });
}




