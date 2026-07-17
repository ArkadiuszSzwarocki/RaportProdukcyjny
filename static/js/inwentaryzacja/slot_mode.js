function highlightAndOpenSlot(locId) {
    // Remove highlight from all
    document.querySelectorAll('#rackGrid > div').forEach(d => {
        d.style.outline = 'none';
        d.style.zIndex = '1';
    });
    
    const cell = document.getElementById(`cell-${locId}`);
    if(cell) {
        cell.style.outline = '3px solid #3b82f6';
        cell.style.zIndex = '10';
        cell.scrollIntoView({behavior: 'smooth', block: 'center'});
    }
    
    lastLocation = locId;
    openSlotDetail(locId);
}


function openSlotDetail(locId) {
    const detail = document.getElementById('slotDetail');
    const title = document.getElementById('detailLocTitle');
    const content = document.getElementById('detailContent');
    
    title.textContent = locId;
    content.innerHTML = '';
    
    const items = rackData[locId] || [];
    const isExplicitlyEmpty = items.length === 1 && items[0].nazwa === 'PUSTE GNIAZDO';

    if(items.length === 0 || isExplicitlyEmpty) {
        let statusHtml = '';
        if(isExplicitlyEmpty) {
            statusHtml = `<div style="background: #dcfce7; color: #166534; padding: 12px; border-radius: 12px; font-weight: 700; margin-bottom: 15px; display: flex; align-items: center; justify-content: center; gap: 8px;">
                            <span class="material-icons">check_circle</span> POTWIERDZONO: PUSTE GNIAZDO
                          </div>`;
        } else {
            statusHtml = `<p style="color: #64748b; font-size: 14px; margin-bottom: 15px;">To gniazdo jest puste systemowo.</p>`;
        }

        content.innerHTML = `
            <div style="text-align: center; padding: 20px;">
                ${statusHtml}
                <div style="display: flex; flex-direction: column; gap: 10px;">
                    ${!isExplicitlyEmpty ? `<button id="btnConfirmEmpty" class="btn-primary" style="background:#10b981; border:none; padding:12px; border-radius:12px; color:white; font-weight:700;">POTWIERDŹ PUSTE</button>` : ''}
                    <button onclick="addNewPallet('${locId}')" style="background:white; border:1px solid #3b82f6; padding:12px; border-radius:12px; color:#3b82f6; font-weight:700; display:flex; align-items:center; justify-content:center; gap:5px;">
                        <span class="material-icons">add</span> DODAJ PALETĘ
                    </button>
                </div>
            </div>
        `;
        if(!isExplicitlyEmpty) {
            document.getElementById('btnConfirmEmpty').onclick = () => markEmpty(locId);
        }
    } else {
        const realItems = items.filter(p => p.nazwa !== 'PUSTE GNIAZDO' && (p.counted || p._unhidden));
        
        if (realItems.length === 0) {
            content.innerHTML = `
            <div style="text-align: center; padding: 20px;">
                <p style="color: #64748b; font-size: 14px; margin-bottom: 15px;">Zeskanuj paletę, aby ją sprawdzić.</p>
                <div style="display: flex; flex-direction: column; gap: 10px;">
                    <button id="btnConfirmEmpty" class="btn-primary" style="background:#10b981; border:none; padding:12px; border-radius:12px; color:white; font-weight:700;">POTWIERDŹ PUSTE</button>
                    <button onclick="addNewPallet('${locId}')" style="background:white; border:1px solid #3b82f6; padding:12px; border-radius:12px; color:#3b82f6; font-weight:700; display:flex; align-items:center; justify-content:center; gap:5px;">
                        <span class="material-icons">add</span> DODAJ RĘCZNIE
                    </button>
                </div>
            </div>
            `;
            document.getElementById('btnConfirmEmpty').onclick = () => markEmpty(locId);
        } else {
            realItems.forEach(p => {
            const card = document.createElement('div');
            card.className = 'pallet-card';
            card.style.transition = 'all 0.2s';
            card.style.position = 'relative';
            
            const systemQty = p.stan_magazynowy || 0;
            const displayWeight = p.counted && p.waga_faktyczna !== null && p.waga_faktyczna !== undefined ? p.waga_faktyczna : '';
            
            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                    <div style="overflow: hidden; flex: 1; padding-right: 8px;">
                        <div style="font-size: 9px; font-weight: 800; color: #94a3b8; text-transform: uppercase;">${p.typ_palety}</div>
                        <div style="font-size: 14px; font-weight: 800; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" class="pallet-pname">${p.nazwa}</div>
                        <div style="font-size: 11px; color: #64748b; font-family: monospace;">${p.displayId}</div>
                    </div>
                    <div style="text-align: right; font-size: 11px; color: #64748b; font-weight: 700; flex-shrink: 0; display: flex; flex-direction: column; align-items: flex-end; gap: 6px;">
                        <div style="display: none;">SYS: <span style="font-size: 13px; font-weight: 800; color: #334155;">${systemQty} ${p.jednostka || 'kg'}</span></div>
                        ${p.id ? `<button class="move-pallet-btn" style="background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 8px; font-size: 10px; cursor: pointer; color: #475569; display: flex; align-items: center; gap: 4px; font-weight: 800;" title="Przenieś paletę w inne miejsce">
                            <span class="material-icons" style="font-size: 12px; color: #3b82f6;">place</span> Przenieś
                        </button>
                        <button onclick="openPrinterModal('${p.id}', '${p.typ_palety}')" style="background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 8px; font-size: 10px; cursor: pointer; color: #475569; display: flex; align-items: center; gap: 4px; font-weight: 800; margin-top: 4px;" title="Drukuj podwójną etykietę">
                            <span class="material-icons" style="font-size: 12px; color: #64748b;">print</span> Drukuj x2
                        </button>` : ''}
                    </div>
                </div>
                <div class="slot-change-indicator" style="display:none; padding:4px 8px; border-radius:6px; font-size:11px; font-weight:700; margin-bottom:8px;"></div>
                <div style="display: flex; gap: 10px; align-items: center;">
                    <div style="display: flex; flex: 1; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: white; align-items: center;">
                        <input type="number" step="0.1" inputmode="none" class="weight-input slot-weight-input" placeholder="STAN FAKTYCZNY" value="${displayWeight}" style="border: none; flex: 1; margin: 0; padding: 12px; font-weight: 800; font-size: 16px; outline: none; text-align: left;">
                        <select class="slot-unit-select" style="border: none; background: #f1f5f9; padding: 12px; font-weight: 800; font-size: 13px; color: #475569; outline: none; border-left: 1px solid #e2e8f0; height: 100%; cursor: pointer;">
                            <option value="kg" ${(p.jednostka || 'kg') === 'kg' ? 'selected' : ''}>kg</option>
                            <option value="szt" ${(p.jednostka || 'kg') === 'szt' ? 'selected' : ''}>szt</option>
                        </select>
                    </div>
                    <button class="save-btn" style="background: ${p.counted ? '#059669' : '#10b981'}" title="Zapisz">
                        <span class="material-icons">${p.counted ? 'done_all' : 'save'}</span>
                    </button>
                </div>
            `;
            
            content.appendChild(card);
            
            const input = card.querySelector('.slot-weight-input');
            
            // Allow soft keyboard to open on explicit user click/tap
            const allowKeyboard = () => input.removeAttribute('inputmode');
            input.addEventListener('click', allowKeyboard);
            input.addEventListener('touchstart', allowKeyboard);
            const unitSelect = card.querySelector('.slot-unit-select');
            const saveBtn = card.querySelector('.save-btn');
            const indicator = card.querySelector('.slot-change-indicator');
            const nameEl = card.querySelector('.pallet-pname');
            
            function updateSlotCardStyle() {
                const w = parseFloat(input.value);
                const unit = unitSelect.value;
                if(isNaN(w) || input.value === '') { 
                    indicator.style.display='none'; 
                    card.style.borderColor = '#e2e8f0';
                    card.style.background = '#f8fafc';
                    nameEl.style.textDecoration = 'none';
                    nameEl.style.color = '#0f172a';
                    return; 
                }
                indicator.style.display = 'block';
                if(w <= 0) {
                    indicator.style.background = '#fee2e2';
                    indicator.style.color = '#dc2626';
                    indicator.innerHTML = `<s>${p.nazwa}</s> — USUNIĘTO`;
                    card.style.borderColor = '#fca5a5';
                    card.style.background = '#fff5f5';
                    nameEl.style.textDecoration = 'line-through';
                    nameEl.style.color = '#dc2626';
                } else if(w !== systemQty || unit !== (p.jednostka || 'kg')) {
                    indicator.style.background = '#fef9c3';
                    indicator.style.color = '#92400e';
                    indicator.innerHTML = `✏️ Zapisano: <strong>${w} ${unit}</strong> (Niezgodne z sys.)`;
                    card.style.borderColor = '#fbbf24';
                    card.style.background = '#fffbeb';
                    nameEl.style.textDecoration = 'none';
                    nameEl.style.color = '#0f172a';
                } else {
                    indicator.style.background = '#dcfce7';
                    indicator.style.color = '#166534';
                    indicator.innerHTML = `✅ Potwierdzono: ${w} ${unit} (Zgodne)`;
                    card.style.borderColor = '#10b981';
                    card.style.background = '#f0fdf4';
                    nameEl.style.textDecoration = 'none';
                    nameEl.style.color = '#0f172a';
                }
            }
            
            input.addEventListener('input', updateSlotCardStyle);
            unitSelect.addEventListener('change', updateSlotCardStyle);
            
            const moveBtn = card.querySelector('.move-pallet-btn');
            if(moveBtn) {
                moveBtn.onclick = (e) => {
                    e.preventDefault();
                    promptMoveLocationScanner(p, locId);
                };
            }
            
            if(p.counted) {
                updateSlotCardStyle();
            }
            
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
            
            saveBtn.onclick = () => {
                const weight = parseFloat(input.value);
                const unit = unitSelect.value;
                if(isNaN(weight)) return alert('Podaj poprawną wagę!');
                
                saveBtn.innerHTML = '<span class="material-icons">hourglass_top</span>';
                saveBtn.style.background = '#94a3b8';
                
                smartFetch(window.INVENTORY_CONFIG.url_zapisz_wpis, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        sesja_id: window.INVENTORY_CONFIG.sesjaId,
                        paleta_id: p.id,
                        nr_palety: p.nr_palety,
                        typ_palety: p.typ_palety,
                        nazwa: p.nazwa,
                        lokalizacja: locId,
                        nr_partii: p.nr_partii,
                        waga_systemowa: systemQty,
                        waga_faktyczna: weight,
                        linia: p.linia || 'PSD',
                        data_produkcji: p.data_produkcji,
                        data_przydatnosci: p.data_przydatnosci,
                        jednostka: unit
                    })
                }).then(r => r.json()).then(data => {
                    if(data.success) {
                        saveBtn.innerHTML = '<span class="material-icons">done_all</span>';
                        saveBtn.style.background = '#059669';
                        markCellDone(locId, false);
                        
                        refreshRackData(currentRackPrefix);
                        setTimeout(() => { closeDetail(); refocusRackScanner(); }, 300);
                    } else {
                        saveBtn.innerHTML = '<span class="material-icons">error</span>';
                        saveBtn.style.background = '#ef4444';
                        alert('Błąd: ' + data.message);
                    }
                }).catch(() => {
                    saveBtn.innerHTML = '<span class="material-icons">save</span>';
                    saveBtn.style.background = '#10b981';
                });
            };
            
            input.addEventListener('keydown', (e) => {
                if(e.key === 'Enter') {
                    e.preventDefault();
                    saveBtn.click();
                }
            });
        });
        
        // Also add options to add/clear
        const isOccupied = realItems.some(p => {
            if (p.counted) return parseFloat(p.waga_faktyczna) > 0;
            return parseFloat(p.stan_magazynowy) > 0;
        });
        const isRestrictedRack = /^R0?[1-7]/.test(locId) || /^R-0?[1-7]/.test(locId);
        const canAddAnother = !(isRestrictedRack && isOccupied);

        const footerDiv = document.createElement('div');
        footerDiv.style.marginTop = '15px';
        footerDiv.style.display = 'grid';
        footerDiv.style.gridTemplateColumns = canAddAnother ? '1fr 1fr' : '1fr';
        footerDiv.style.gap = '10px';
        
        let footerHtml = '';
        if (canAddAnother) {
            footerHtml += `<button onclick="addNewPallet('${locId}')" style="background:#f8fafc; border:1px solid #e2e8f0; padding:10px; border-radius:10px; color:#64748b; font-size:12px; font-weight:700;">+ DODAJ KOLEJNĄ</button>`;
        }
        footerHtml += `<button id="btnConfirmEmptyFooter" style="background:#fef2f2; border:1px solid #fee2e2; padding:10px; border-radius:10px; color:#ef4444; font-size:12px; font-weight:700;">WYCZYŚĆ (PUSTE)</button>`;
        
        footerDiv.innerHTML = footerHtml;
        content.appendChild(footerDiv);
        document.getElementById('btnConfirmEmptyFooter').onclick = () => markEmpty(locId);
        } // zamyka blok: if (realItems.length === 0)
    }
    detail.style.display = 'flex';
    
    // Autofocus SSCC verifier first
    setTimeout(() => {
        const ssccInput = document.getElementById('ssccVerifierInputDetail');
        if(ssccInput) ssccInput.focus();
    }, 100);
}


function closeDetail() {
    document.getElementById('slotDetail').style.display = 'none';
    refocusRackScanner();
}

// Close modal when clicking on the backdrop
document.getElementById('slotDetail').addEventListener('click', (e) => {
    if (e.target === document.getElementById('slotDetail')) {
        closeDetail();
    }
});


function markEmpty(locId) {
    // Confirmed empty without additional question as requested
    
    // If there were items, we need to set them to 0
    const items = rackData[locId] || [];
    if(items.length === 0) {
        smartFetch(window.INVENTORY_CONFIG.url_zapisz_wpis, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                sesja_id: window.INVENTORY_CONFIG.sesjaId,
                paleta_id: null,
                typ_palety: 'surowiec',
                nazwa: 'PUSTE GNIAZDO',
                lokalizacja: locId,
                nr_partii: '-',
                waga_systemowa: 0,
                waga_faktyczna: 0,
                linia: 'PSD'
            })
        }).then(() => {
            markCellDone(locId, true);
            refreshRackData(currentRackPrefix, locId);
            setTimeout(() => closeDetail(), 1000);
        });
    } else {
        let count = 0;
        items.forEach(p => {
            smartFetch(window.INVENTORY_CONFIG.url_zapisz_wpis, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    sesja_id: window.INVENTORY_CONFIG.sesjaId,
                    paleta_id: p.id,
                    typ_palety: p.typ_palety,
                    nazwa: p.nazwa,
                    lokalizacja: locId,
                    nr_partii: p.nr_partii,
                    waga_systemowa: p.stan_magazynowy,
                    waga_faktyczna: 0,
                    linia: p.linia || 'PSD'
                })
            }).then(() => {
                count++;
                if(count === items.length) {
                    markCellDone(locId, true);
                    refreshRackData(currentRackPrefix, locId);
                    setTimeout(() => closeDetail(), 1000);
                }
            });
        });
    }
}


