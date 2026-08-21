function renderPallets(pallets) {
    const list = document.getElementById('palletsList');
    if(!list) return;
    list.innerHTML = '';
    const realPallets = pallets.filter(p => p.nazwa !== 'PUSTE GNIAZDO' && (p.counted || p._unhidden)).reverse();
    currentPallets = realPallets;

    
    const isOccupied = realPallets.some(p => {
        if (p.counted) return parseFloat(p.waga_faktyczna) > 0;
        return parseFloat(p.stan_magazynowy) > 0;
    });
    const isRestrictedRack = lastLocation && (/^R0?[1-7]/.test(lastLocation) || /^R-0?[1-7]/.test(lastLocation));
    const canAddAnother = !(isRestrictedRack && isOccupied);

    const mainBtn = document.getElementById('btnAddPalletMain');
    if (mainBtn) {
        mainBtn.style.display = canAddAnother ? 'flex' : 'none';
    }
    
    // Check if explicitly empty
    const isExplicitlyEmpty = pallets.length === 1 && pallets[0].nazwa === 'PUSTE GNIAZDO';

    if(realPallets.length === 0) {
        if (isExplicitlyEmpty) {
            list.innerHTML = `
                <div style="text-align:center; padding:30px; background:#f0fdf4; border-radius:12px; border:1px solid #10b981;">
                    <span class="material-icons" style="font-size:40px; color:#10b981;">check_circle</span>
                    <div style="color:#166534; font-weight:700; margin-top:8px;">POTWIERDZONO: PUSTE GNIAZDO</div>
                </div>`;
            return;
        }
        list.innerHTML = `
            <div style="text-align:center; padding:30px; background:#f8fafc; border-radius:12px; border:1px dashed #cbd5e1;">
                <span class="material-icons" style="font-size:40px; color:#94a3b8;">qr_code_scanner</span>
                <div style="color:#64748b; font-weight:700; margin-top:8px;">Zeskanuj paletę, aby ją sprawdzić.</div>
            </div>`;
        return;
    }
    
    realPallets.forEach((p, index) => {
        const systemQty = p.stan_magazynowy || 0;
        const isCounted = p.counted;
        
        const card = document.createElement('div');
        card.className = 'pallet-card';
        card.dataset.palletId = p.id;
        card.style.transition = 'all 0.2s';
        if(isCounted) { card.style.borderColor='#10b981'; card.style.background='#f0fdf4'; }
        
        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
                <div style="overflow:hidden; flex:1;">
                    <div style="font-size:9px; font-weight:800; color:#94a3b8; text-transform:uppercase;">${p.typ_palety}</div>
                    <div style="font-size:15px; font-weight:800; color:#0f172a;" class="pname-${index}">${p.nazwa}</div>
                    <div style="font-size:11px; color:#64748b; font-family:monospace;">${p.displayId}</div>
                </div>
                <div style="text-align:right; font-size:11px; color:#64748b; font-weight:700; flex-shrink:0; margin-left:10px; display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
                    <button onclick="openPrinterModal('${p.id}', '${p.typ_palety}')" style="background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 8px; font-size: 10px; cursor: pointer; color: #475569; display: flex; align-items: center; gap: 4px; font-weight: 800;" title="Drukuj podwójną etykietę">
                        <span class="material-icons" style="font-size: 12px; color: #64748b;">print</span> Drukuj x2
                    </button>
                    <div style="display: none;">SYS: <span style="font-size:14px; font-weight:800; color:#334155;">${systemQty} ${p.jednostka || 'kg'}</span></div>
                </div>
            </div>
            <div id="change-indicator-${index}" style="display:none; padding:6px 10px; border-radius:8px; font-size:12px; font-weight:700; margin-bottom:8px;"></div>
            <div style="display:flex; gap:10px; align-items:center;">
                <div style="display: flex; flex: 1; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: white; align-items: center;">
                    <input type="number" step="0.1" class="weight-input actual-weight-input" 
                           id="winput-${index}" placeholder="Wpisz wagę..." autocomplete="off" inputmode="none"
                           value="${isCounted && p.waga_faktyczna !== null && p.waga_faktyczna !== undefined ? p.waga_faktyczna : ''}"
                           style="border: none; flex: 1; margin: 0; padding: 12px; font-weight: 800; font-size: 16px; outline: none; text-align: left;">

                    <select class="actual-unit-select" id="uinput-${index}" style="border: none; background: #f1f5f9; padding: 12px; font-weight: 800; font-size: 13px; color: #475569; outline: none; border-left: 1px solid #e2e8f0; height: 100%; cursor: pointer;">
                        <option value="kg" ${(p.jednostka || 'kg') === 'kg' ? 'selected' : ''}>kg</option>
                        <option value="szt" ${(p.jednostka || 'kg') === 'szt' ? 'selected' : ''}>szt</option>
                    </select>
                </div>
                <button class="save-btn" id="sbtn-${index}" title="Zapisz"
                        style="background:${isCounted ? '#059669' : '#10b981'}">
                    <span class="material-icons">${isCounted ? 'done_all' : 'save'}</span>
                </button>
            </div>`;
        
        list.appendChild(card);
        
        const input = card.querySelector('.actual-weight-input');
        const unitSelect = card.querySelector('.actual-unit-select');
        const saveBtn = card.querySelector('.save-btn');
        const indicator = card.querySelector(`#change-indicator-${index}`);
        
        // Live visual feedback when weight changes
        function updateListStyle() {
            const w = parseFloat(input.value);
            const unit = unitSelect.value;
            if(isNaN(w) || input.value === '') { indicator.style.display='none'; return; }
            indicator.style.display = 'block';
            if(w <= 0) {
                // USUWANIE: czerwone przekreślenie
                indicator.style.background = '#fee2e2';
                indicator.style.color = '#dc2626';
                indicator.innerHTML = `<s>${p.nazwa}</s> — USUNIĘTO`;
                card.style.borderColor = '#fca5a5';
                card.style.background = '#fff5f5';
                card.querySelector('.pname-'+index)?.style && (card.querySelector('.pname-'+index).style.textDecoration='line-through');
                card.querySelector('.pname-'+index)?.style && (card.querySelector('.pname-'+index).style.color='#dc2626');
            } else if(w !== systemQty || unit !== (p.jednostka || 'kg')) {
                // KOREKTA: żółte
                indicator.style.background = '#fef9c3';
                indicator.style.color = '#92400e';
                indicator.innerHTML = `✏️ Zapisano: <strong>${w} ${unit}</strong> (Niezgodne z sys.)`;
                card.style.borderColor = '#fbbf24';
                card.style.background = '#fffbeb';
                card.querySelector('.pname-'+index)?.style && (card.querySelector('.pname-'+index).style.textDecoration='none');
                card.querySelector('.pname-'+index)?.style && (card.querySelector('.pname-'+index).style.color='#0f172a');
            } else {
                // OK: zielone
                indicator.style.background = '#dcfce7';
                indicator.style.color = '#166534';
                indicator.innerHTML = `✅ Potwierdzono: ${w} ${unit} (Zgodne)`;
                card.style.borderColor = '#10b981';
                card.style.background = '#f0fdf4';
                card.querySelector('.pname-'+index)?.style && (card.querySelector('.pname-'+index).style.textDecoration='none');
                card.querySelector('.pname-'+index)?.style && (card.querySelector('.pname-'+index).style.color='#0f172a');
            }
        }
        
        input.addEventListener('input', updateListStyle);
        unitSelect.addEventListener('change', updateListStyle);
        
        // Auto-save on blur/change
        input.addEventListener('change', () => {
            if (input.value !== '') {
                saveBtn.click();
            }
        });
        unitSelect.addEventListener('change', () => {
            if (input.value !== '') {
                saveBtn.click();
            }
        });
        
        saveBtn.onclick = () => saveEntry(p, input.value, card, saveBtn, unitSelect.value);
        input.addEventListener('keydown', (e) => {
            if(e.key === 'Enter') {
                e.preventDefault();
                saveEntry(p, input.value, card, saveBtn, unitSelect.value);
                const allInputs = document.querySelectorAll('.actual-weight-input');
                if(allInputs[index+1]) { allInputs[index+1].focus(); allInputs[index+1].select(); }
            }
        });
        
        // Trigger live visual feedback on render if already counted
        if(isCounted) {
            updateListStyle();
        }
    });
    
    // Focus first unfilled input
    const inputs = list.querySelectorAll('.actual-weight-input');
    const empty = Array.from(inputs).find(i => !i.value);
    if(empty) { setTimeout(() => { empty.focus(); }, 100); }
}


function handleSSCCInput() {
    const code = document.getElementById('newPalletSSCC').value.trim();
    const statusDiv = document.getElementById('lookupStatus');
    const resultsDiv = document.getElementById('palletSearchResults');
    
    // Reset lookup state
    statusDiv.style.display = 'none';
    statusDiv.textContent = '';
    resultsDiv.style.display = 'none';
    resultsDiv.innerHTML = '';
    lookedUpPalletId = null;
    lookedUpSystemWeight = 0;
    
    if(lookupTimeout) clearTimeout(lookupTimeout);
    if(code.length < 2) return;
    
    lookupTimeout = setTimeout(() => {
        statusDiv.style.display = 'block';
        statusDiv.style.color = '#3b82f6';
        statusDiv.textContent = 'Szukanie palety w bazie...';
        
        fetch(`/magazyn/inwentaryzacja/api/search-pallets?query=${encodeURIComponent(code)}`)
        .then(r => r.json())
        .then(data => {
            if(data.success) {
                const pallets = data.pallets;
                if (pallets.length === 0) {
                    statusDiv.style.color = '#64748b';
                    statusDiv.textContent = '⚪ Nowy kod palety (brak w bazie danych)';
                    resultsDiv.style.display = 'none';
                    return;
                }
                
                // If exact match on nr_palety (e.g. barcode scanner)
                const exactMatch = pallets.find(p => p.nr_palety && p.nr_palety.toUpperCase() === code.toUpperCase());
                if (exactMatch) { 
                    selectPalletFromResult(exactMatch);
                    return;
                }
                
                // Otherwise show dropdown
                statusDiv.style.display = 'none';
                let html = '<div style="border:1px solid #e2e8f0; border-radius:8px; background:white; max-height:220px; overflow-y:auto; box-shadow:0 10px 15px -3px rgba(0,0,0,0.1); margin-top:5px;">';
                pallets.forEach(p => {
                    const jsData = encodeURIComponent(JSON.stringify(p));
                    html += `<div onclick="selectPalletFromResult(JSON.parse(decodeURIComponent('${jsData}')))" style="padding:10px; border-bottom:1px solid #f1f5f9; cursor:pointer; font-size:12px; display:flex; flex-direction:column; gap:4px; transition:background 0.2s;" onmouseover="this.style.background='#f0f9ff'" onmouseout="this.style.background='white'">
                        <div style="font-weight:700; color:#1e293b;">${p.nazwa}</div>
                        <div style="color:#64748b; font-size:11px;">SSCC: <span style="font-weight:600; color:#3b82f6;">${p.nr_palety || 'Brak'}</span> | Partia: ${p.nr_partii || 'Brak'} | Lok: ${p.lokalizacja || 'Brak'}</div>
                    </div>`;
                });
                html += '</div>';
                resultsDiv.innerHTML = html;
                resultsDiv.style.display = 'block';
            }
        })
        .catch(err => {
            statusDiv.style.color = '#ef4444';
            statusDiv.textContent = '🔴 Błąd podczas szukania';
        });
    }, 400);
}


function selectPalletFromResult(p) {
    document.getElementById('palletSearchResults').style.display = 'none';
    
    lookedUpPalletId = p.id;
    lookedUpSystemWeight = p.stan_magazynowy || 0;
    
    const statusDiv = document.getElementById('lookupStatus');
    statusDiv.style.display = 'block';
    statusDiv.style.color = '#10b981';
    statusDiv.innerHTML = `🟢 Znaleziono w bazie: <strong>${p.nazwa}</strong> (Id: ${p.id})`;
    
    // Autofill other fields
    document.getElementById('newPalletSSCC').value = p.nr_palety || '';
    document.getElementById('newPalletName').value = p.nazwa || '';
    if (p.typ_palety) {
        document.getElementById('newPalletType').value = p.typ_palety;
    }
    document.getElementById('newPalletWeight').value = p.stan_magazynowy || '0';
    document.getElementById('newPalletBatch').value = p.nr_partii || '';
    document.getElementById('newPalletDateProd').value = p.data_produkcji || '';
    document.getElementById('newPalletDateExp').value = p.data_przydatnosci || '';
    document.getElementById('newPalletPackaging').value = p.typ_opakowania || 'brak';
    document.getElementById('newPalletUnit').value = p.jednostka || 'kg';
}


function generateLocalSSCC(type) {
    let prefix = 'WG';
    if (type === 'surowiec') prefix = 'SUR';
    else if (type === 'opakowanie') prefix = 'OPK';
    else if (type === 'dodatek') prefix = 'DOD';
    
    const nowMs = Date.now().toString();
    const random = Math.floor(Math.random() * 10000).toString().padStart(4, '0');
    return `${prefix}${nowMs}${random}`;
}


function addNewPallet(loc) {
    const detailModal = document.getElementById('slotDetail');
    if (detailModal) detailModal.style.display = 'none';

    const pendingLocInput = document.getElementById('pendingNewPalletLoc');
    if(pendingLocInput) pendingLocInput.value = loc || '';
    
    const catSelect = document.getElementById('modalCategorySelect');
    if(catSelect) catSelect.value = 'surowiec';
    
    const modal = document.getElementById('categorySelectionModal');
    if(modal) modal.style.display = 'flex';
    else openNewPalletModal(loc, 'surowiec'); // Fallback if modal not found
}

function confirmCategorySelection() {
    const loc = document.getElementById('pendingNewPalletLoc').value;
    const cat = document.getElementById('modalCategorySelect').value;
    document.getElementById('categorySelectionModal').style.display = 'none';
    openNewPalletModal(loc, cat);
}


function openNewPalletModal(loc, selectedType) {
    const detailModal = document.getElementById('slotDetail');
    if (detailModal) detailModal.style.display = 'none';

    lookedUpPalletId = null;
    lookedUpSystemWeight = 0;
    
    const statusDiv = document.getElementById('lookupStatus');
    if(statusDiv) {
        statusDiv.style.display = 'none';
        statusDiv.textContent = '';
    }
    
    const typeSelect = document.getElementById('newPalletType');
    if(selectedType && typeSelect) {
        typeSelect.value = selectedType;
    }
    
    const locInput = document.getElementById('newPalletLoc');
    if (locInput) locInput.value = loc || lastLocation || '';
    
    const ssccInput = document.getElementById('newPalletSSCC');
    if (ssccInput) ssccInput.value = '';
    
    const nameInput = document.getElementById('newPalletName');
    if (nameInput) nameInput.value = '';
    
    const weightInput = document.getElementById('newPalletWeight');
    if (weightInput) weightInput.value = '';
    
    const unitSelect = document.getElementById('newPalletUnit');
    if (unitSelect && typeSelect) {
        unitSelect.value = (typeSelect.value === 'opakowanie') ? 'szt' : 'kg';
    }
    
    const batchInput = document.getElementById('newPalletBatch');
    if (batchInput) batchInput.value = '';
    
    const prodDateInput = document.getElementById('newPalletProdDate') || document.getElementById('newPalletDateProd');
    if (prodDateInput) prodDateInput.value = '';
    
    const expDateInput = document.getElementById('newPalletExpDate') || document.getElementById('newPalletDateExp');
    if (expDateInput) expDateInput.value = '';
    
    const packagingSelect = document.getElementById('newPalletPackaging');
    if (packagingSelect) packagingSelect.value = 'brak';
    
    const modal = document.getElementById('newPalletModal');
    if (modal) modal.style.display = 'flex';
    
    if (ssccInput) {
        setTimeout(() => {
            ssccInput.focus();
            ssccInput.select();
        }, 100);
    }
    
    if (typeSelect) {
        fetchProductNames(typeSelect.value);
    }
}

// Switch unit automatically based on category/type choice and regenerate SSCC

function saveNewPallet() {
    const sscc = (document.getElementById('newPalletSSCC')?.value || '').trim();
    const name = (document.getElementById('newPalletName')?.value || '').trim();
    const type = document.getElementById('newPalletType')?.value || 'surowiec';
    const weightVal = document.getElementById('newPalletWeight')?.value;
    const weight = weightVal !== '' && !isNaN(parseFloat(weightVal)) ? parseFloat(weightVal) : 0;
    const batch = (document.getElementById('newPalletBatch')?.value || '').trim() || 'BRAK';
    const dProd = document.getElementById('newPalletProdDate')?.value || document.getElementById('newPalletDateProd')?.value || '';
    const dExp = document.getElementById('newPalletExpDate')?.value || document.getElementById('newPalletDateExp')?.value || '';
    const loc = document.getElementById('newPalletLoc')?.value || lastLocation;
    const packaging = document.getElementById('newPalletPackaging')?.value || 'brak';
    const unit = document.getElementById('newPalletUnit')?.value || 'kg';

    if(!sscc || !name) {
        safeToast('Wpisz numer palety (SSCC) i nazwę produktu!', 'error');
        return;
    }
    
    safeToast('Zapisywanie nowej palety...', 'info');
    
    smartFetch(window.INVENTORY_CONFIG.url_zapisz_wpis, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            sesja_id: window.INVENTORY_CONFIG.sesjaId,
            paleta_id: lookedUpPalletId,
            nr_palety: sscc,
            typ_palety: type,
            nazwa: name,
            lokalizacja: loc,
            nr_partii: batch,
            waga_systemowa: lookedUpPalletId ? lookedUpSystemWeight : 0,
            waga_faktyczna: weight,
            data_produkcji: dProd,
            data_przydatnosci: dExp,
            linia: 'PSD',
            typ_opakowania: packaging,
            jednostka: unit
        })
    }).then(r => r.json()).then(data => {
        if(data.success) {
            safeToast('✅ Paleta dodana pomyślnie!', 'success');
            document.getElementById('newPalletModal').style.display = 'none';
            if(currentRackPrefix) {
                markCellDone(loc, false);
                refreshRackData(currentRackPrefix, loc); // Refresh rack data AND slot detail popup!
            } else {
                searchLocation(loc || lastLocation); // Refresh list with explicit location
                if (typeof loadCountedBlindItems === 'function') {
                    loadCountedBlindItems(loc || lastLocation);
                }
            }
        } else {
            safeToast('Błąd: ' + (data.message || 'Nie udało się zapisać'), 'error');
        }
    }).catch(err => {
        console.error(err);
        safeToast('Błąd sieci podczas zapisu', 'error');
    });
}


function promptMoveLocationScanner(p, locId) {
    currentMovePallet = p;
    currentMoveOriginalLoc = locId;
    
    // Generuj podpowiedzi
    const datalist = document.getElementById('locationSuggestions');
    if (datalist && datalist.children.length === 0) {
        let options = '';
        for(let r=1; r<=10; r++) {
            let rStr = r.toString().padStart(2,'0');
            let maxCols = (r===5) ? 4 : (r===6 ? 5 : 10);
            let maxRows = (r===5) ? 4 : (r===6 ? 5 : 3);
            for(let row=1; row<=maxRows; row++) {
                for(let col=1; col<=maxCols; col++) {
                    options += `<option value="R${rStr}${col.toString().padStart(2,'0')}${row.toString().padStart(2,'0')}"></option>`;
                }
            }
        }
        options += '<option value="MP01"></option><option value="MS01"></option><option value="MGW01"></option>';
        datalist.innerHTML = options;
    }
    
    document.getElementById('newLocationInput').value = '';
    document.getElementById('moveLocationError').style.display = 'none';
    
    const sysAmount = p.stan_magazynowy || 0;
    document.getElementById('moveAmountInput').value = sysAmount;
    document.getElementById('moveAmountUnit').textContent = p.jednostka || 'kg';
    
    document.getElementById('moveLocationModal').style.display = 'flex';
}


function submitMoveLocation() {
    if(!currentMovePallet) return;
    
    const inputLoc = document.getElementById('newLocationInput');
    const inputAmt = document.getElementById('moveAmountInput');
    const errEl = document.getElementById('moveLocationError');
    const btn = document.getElementById('submitMoveBtn');
    
    let newLoc = inputLoc.value.trim().toUpperCase();
    let amount = parseFloat(inputAmt.value);
    
    if(!newLoc) {
        errEl.textContent = 'Lokalizacja nie może być pusta!';
        errEl.style.display = 'block';
        return;
    }
    if(newLoc === currentMoveOriginalLoc) {
        errEl.textContent = 'Lokalizacja musi być inna niż obecna!';
        errEl.style.display = 'block';
        return;
    }
    if(isNaN(amount) || amount <= 0) {
        errEl.textContent = 'Podaj poprawną ilość do przeniesienia!';
        errEl.style.display = 'block';
        return;
    }
    
    errEl.style.display = 'none';
    btn.innerHTML = '<span class="material-icons rotate-anim">sync</span>';
    btn.disabled = true;
    
    let pt = currentMovePallet.typ_palety;
    let capitalType = pt.charAt(0).toUpperCase() + pt.slice(1);
    if(pt === 'wyrób gotowy') capitalType = 'Wyrób Gotowy';
    
    smartFetch('/warehouse-v2/api/pallet/move', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: currentMovePallet.id,
            type: capitalType,
            location: newLoc,
            linia: currentMovePallet.linia || 'PSD',
            amount: amount // Przekazujemy podaną ilość (może być mniejsza od całości = split)
        })
    }).then(r => r.json()).then(data => {
        btn.innerHTML = 'ZAPISZ';
        btn.disabled = false;
        if(data.success) {
            document.getElementById('moveLocationModal').style.display = 'none';
            refreshRackData(currentRackPrefix);
            closeDetail();
        } else {
            errEl.textContent = "Błąd: " + (data.error || data.message || "Nieznany błąd zapisu");
            errEl.style.display = 'block';
        }
    }).catch(e => {
        btn.innerHTML = 'ZAPISZ';
        btn.disabled = false;
        errEl.textContent = "Błąd połączenia z serwerem.";
        errEl.style.display = 'block';
    });
}


function isPalletMatch(item, code) {
    if (!item || !code) return false;
    code = String(code).trim().toUpperCase();
    const cleanCode = code.replace('(00)', '').replace(']C1', '').replace(/^SUR|^AGR|^OPK|^DOD/i, '').replace(/^0+/, '').trim();
    
    const did = item.displayId ? String(item.displayId).toUpperCase() : '';
    const nrp = item.nr_palety ? String(item.nr_palety).toUpperCase() : '';
    const cleanNrp = nrp.replace('(00)', '').replace(']C1', '').replace(/^SUR|^AGR|^OPK|^DOD/i, '').replace(/^0+/, '').trim();
    const pid = item.id ? String(item.id) : '';

    if (nrp && (nrp === code || nrp.includes(code) || code.includes(nrp))) return true;
    if (did && (did === code || did.includes(code) || code.includes(did))) return true;
    if (pid && (pid === code || pid === cleanCode)) return true;
    if (cleanNrp && cleanCode && (cleanNrp === cleanCode || cleanNrp.includes(cleanCode) || cleanCode.includes(cleanNrp))) return true;
    return false;
}

function verifyPalletSSCC(sscc, context) {
    if(!sscc) return;
    sscc = sscc.trim().toUpperCase();
    
    let foundLocally = false;
    let targetLoc = context === 'detail' 
        ? normalizeLocationCode(document.getElementById('detailLocTitle').textContent) 
        : normalizeLocationCode(lastLocation);
    
    if (context === 'results') {
        const p = currentLocationPallets.find(p => isPalletMatch(p, sscc));
        if (p) {
            foundLocally = true;
            p._unhidden = true;
            renderPallets(currentLocationPallets);
            
            setTimeout(() => {
                const cards = document.querySelectorAll('#resultsContainer .pallet-card');
                for (let card of cards) {
                    if (isPalletMatch(p, sscc)) {
                        highlightAndFocusCard(card);
                        break;
                    }
                }
            }, 100);
            safeToast('✅ Odczytano paletę: ' + p.nazwa, 'success');
        }
    } else if (context === 'detail') {
        let items = rackData[targetLoc] || [];
        const p = items.find(item => isPalletMatch(item, sscc));
        if (p) {
            foundLocally = true;
            p._unhidden = true;
            openSlotDetail(targetLoc);
            safeToast('✅ Odczytano paletę: ' + p.nazwa, 'success');
        }
    }
    
    if (!foundLocally) {
        globalSearchAndPrompt(sscc, context, targetLoc);
    }
}


function verifyPalletSSCCRack(sscc) {
    if(!sscc) return;
    sscc = sscc.trim().toUpperCase();
    
    let foundLocId = null;
    let foundItem = null;
    
    if (rackData) {
        for (const [loc, items] of Object.entries(rackData)) {
            for (const item of items) {
                if (isPalletMatch(item, sscc)) {
                    foundLocId = loc;
                    foundItem = item;
                    break;
                }
            }
            if (foundLocId) break;
        }
    }
    
    if (foundLocId) {
        foundItem._unhidden = true;
        safeToast('✅ Paleta w gnieździe ' + foundLocId + ': ' + foundItem.nazwa, 'success');
        highlightAndOpenSlot(foundLocId);
    } else {
        globalSearchAndPrompt(sscc, 'rack', null);
    }
}



function globalSearchAndPrompt(sscc, context, targetLoc) {
    if (!targetLoc) targetLoc = lastLocation;
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
            const destLoc = targetLoc || (typeof isLocationCode === 'function' && isLocationCode(lastLocation) ? lastLocation : null);
            
            if (destLoc) {
                AppDialog.confirm(
                    `Znaleziono w bazie: <b>${pal.nazwa}</b><br>SSCC: <b>${sscc}</b> | Partia: <b>${pal.nr_partii || '-'}</b> | Waga: <b>${pal.waga || 0} ${pal.jednostka || 'kg'}</b><br>Poprzednia lok: <b>${pal.lokalizacja || 'BRAK'}</b><br><br>Czy przypisać tę paletę do gniazda <b>${destLoc}</b>?`,
                    'Przypisanie palety do gniazda'
                ).then(confirmed => {
                    if(confirmed) {
                        movePalletToLocation(pal, destLoc, context);
                    } else {
                        if (context === 'detail') refocusDetailScanner();
                        else refocusRackScanner();
                    }
                });
            } else {
                AppDialog.alert(
                    `Znaleziono paletę <b>${sscc}</b> (${pal.nazwa}) w lokalizacji: <b>${pal.lokalizacja || 'Brak'}</b>.<br><br>Najpierw zeskanuj lub wybierz gniazdo na regale, do którego chcesz ją przypisać.`,
                    'Wybierz gniazdo'
                ).then(() => refocusRackScanner());
            }
        } else {
            const destLoc = targetLoc || lastLocation;
            AppDialog.confirm(
                `Paleta z kodem <b>${sscc}</b> nie znajduje się w bazie.<br><br>Czy chcesz ją teraz dodać do gniazda <b>${destLoc || ''}</b>?`,
                'Brak palety w bazie'
            ).then(confirmed => {
                if (confirmed) {
                    openNewPalletModal(destLoc, 'surowiec');
                    setTimeout(() => {
                        const ssccInp = document.getElementById('newPalletSSCC');
                        if (ssccInp) {
                            ssccInp.value = sscc;
                            const nameInp = document.getElementById('newPalletName');
                            if (nameInp) nameInp.focus();
                        }
                    }, 200);
                } else {
                    if (context === 'detail') refocusDetailScanner();
                    else refocusRackScanner();
                }
            });
        }
    }).catch(e => {
        console.error('globalSearch error:', e);
        AppDialog.alert('Błąd połączenia podczas szukania palety.', 'Błąd');
    });
}


function movePalletToLocation(paleta, targetLoc, context) {
    let mapTyp = 'surowiec';
    const t = (paleta.typ || '').toLowerCase();
    if(t.includes('opakowanie')) mapTyp = 'opakowanie';
    else if(t.includes('dodatek')) mapTyp = 'dodatek';
    else if(t.includes('gotow') || t.includes('wyrób')) mapTyp = 'wyrób gotowy';
    else if(t.includes('surowiec')) mapTyp = 'surowiec';

    safeToast('Przypisywanie palety...', 'info');

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
            waga_faktyczna: paleta.waga || 0,
            data_produkcji: paleta.data_produkcji || '',
            data_przydatnosci: paleta.data_przydatnosci || '',
            linia: paleta.linia || 'PSD',
            typ_opakowania: '',
            jednostka: paleta.jednostka || 'kg'
        })
    }).then(r => r.json()).then(saveData => {
        if (saveData.success) {
            safeToast('✅ Paleta przypisana pomyślnie!', 'success');
            if(context === 'results') {
                searchLocation(targetLoc || lastLocation); 
            } else {
                fetch(window.INVENTORY_CONFIG.url_szukaj_regalu, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({prefix: currentRackPrefix, sesja_id: window.INVENTORY_CONFIG.sesjaId})
                })
                .then(r => r.json())
                .then(data => {
                    if(data.success) {
                        rackData = data.rack_data;
                        renderRackGrid(currentRackPrefix);
                        markCellDone(targetLoc, false);
                        highlightAndOpenSlot(targetLoc); 
                    }
                });
            }
        } else {
            AppDialog.alert(saveData.message || 'Wystąpił błąd', 'Błąd zapisu');
        }
    }).catch(e => {
        console.error('movePallet error:', e);
        AppDialog.alert('Błąd połączenia podczas przypisywania.', 'Błąd');
    });
}


function openPrinterModal(palletId, palletType) {
    openSharedPrinterModal({id: palletId, type: palletType}, function(printerId, payload) {
        safeToast('Wysyłanie do druku...', 'info');
        fetch(window.INVENTORY_CONFIG.url_print_pallet_label, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: payload.id,
                type: payload.type,
                printer_id: printerId,
                copies: 2
            })
        }).then(r => r.json()).then(data => {
            if (data.success) safeToast('Wysłano na drukarkę (2 kopie)!', 'success');
            else AppDialog.alert(data.error || data.message || 'Wystąpił błąd podczas druku', 'Błąd');
        }).catch(e => AppDialog.alert('Błąd połączenia', 'Błąd'));
    });
}

