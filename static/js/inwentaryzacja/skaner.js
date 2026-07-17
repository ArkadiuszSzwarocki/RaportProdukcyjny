let currentLocationPallets = [];

/**
 * safeToast - wrapper for showing toast notifications.
 * Falls back to AppDialog.alert when showToast is unavailable.
 */
function safeToast(msg, kind) {
    if (typeof showToast === 'function') {
        showToast(msg, kind || 'info');
    } else if (typeof AppDialog !== 'undefined') {
        AppDialog.alert(msg);
    }
}

/**
 * isLocationCode - checks if scanned code looks like a rack location.
 * Location codes: R followed by 4+ digits (e.g., R030101).
 */
function isLocationCode(code) {
    const normalized = code.replace(/-/g, '');
    return /^R\d{4,}$/.test(normalized);
}

/**
 * normalizeLocationCode - removes hyphens for consistent matching.
 */
function normalizeLocationCode(code) {
    return code.replace(/-/g, '');
}

/**
 * handleRackScan - smart scanner router for rack view.
 * Detects whether the scanned code is a location or pallet and routes accordingly.
 * Flow: ① Scan location → opens slot detail, ② Scan pallet → verifies on rack.
 */
function handleRackScan(code) {
    if (!code) return;
    code = code.trim().toUpperCase();
    const normalized = normalizeLocationCode(code);
    
    // 1. Location on current rack → open slot detail
    if (currentRackPrefix && normalized.startsWith(currentRackPrefix) && normalized.length >= 6) {
        safeToast('📍 Otwieram gniazdo ' + normalized, 'info');
        highlightAndOpenSlot(normalized);
        return;
    }
    
    // 2. Different rack prefix (e.g., R05 while viewing R03) → load new rack
    if (/^R\d{1,2}$/.test(normalized) && normalized !== currentRackPrefix) {
        loadRack(normalized);
        return;
    }
    
    // 3. Location on a different rack (e.g., R050101) → load rack + open slot
    if (isLocationCode(normalized) && currentRackPrefix && !normalized.startsWith(currentRackPrefix)) {
        const newPrefix = normalized.substring(0, 3);
        safeToast('📍 Przechodzę do regału ' + newPrefix, 'info');
        loadRack(newPrefix);
        setTimeout(() => highlightAndOpenSlot(normalized), 600);
        return;
    }
    
    // 4. Otherwise → treat as pallet code, verify on rack
    verifyPalletSSCCRack(code);
}

/**
 * handleDetailScan - smart scanner router for slot detail modal.
 * If a location is scanned, closes current detail and opens new slot.
 * If a pallet is scanned, verifies it in the current slot.
 */
function handleDetailScan(code) {
    if (!code) return;
    code = code.trim().toUpperCase();
    const normalized = normalizeLocationCode(code);
    
    // 1. Location on current rack → close detail, open new slot
    if (currentRackPrefix && normalized.startsWith(currentRackPrefix) && normalized.length >= 6) {
        closeDetail();
        safeToast('📍 Przechodzę do gniazda ' + normalized, 'info');
        setTimeout(() => highlightAndOpenSlot(normalized), 200);
        return;
    }
    
    // 2. Different rack prefix → close detail, load new rack
    if (/^R\d{1,2}$/.test(normalized)) {
        closeDetail();
        loadRack(normalized);
        return;
    }
    
    // 3. Location on a different rack → close detail, load rack + open slot
    if (isLocationCode(normalized)) {
        closeDetail();
        const newPrefix = normalized.substring(0, 3);
        safeToast('📍 Przechodzę do regału ' + newPrefix, 'info');
        loadRack(newPrefix);
        setTimeout(() => highlightAndOpenSlot(normalized), 600);
        return;
    }
    
    // 4. Pallet code → verify in current slot
    verifyPalletSSCC(code, 'detail');
}

/**
 * refocusRackScanner - re-focuses the rack scanner input for continuous scanning.
 */
function refocusRackScanner() {
    setTimeout(() => {
        const inp = document.getElementById('ssccVerifierInputRack');
        if (inp) inp.focus();
    }, 500);
}

/**
 * refocusDetailScanner - re-focuses the detail scanner input.
 */
function refocusDetailScanner() {
    setTimeout(() => {
        const inp = document.getElementById('ssccVerifierInputDetail');
        if (inp) inp.focus();
    }, 500);
}

let currentPallets = [];
let lastLocation = '';
let rackData = {}; // Map location -> [items]
let currentRackPrefix = '';

// Load state on page load
window.addEventListener('load', () => {
    const currentSessionId = "window.INVENTORY_CONFIG.sesjaId";
    const lastSessionId = localStorage.getItem('lastInventorySessionId');
    
    // Jeśli zmieniliśmy sesję, czyścimy stare zapamiętane lokalizacje
    if (lastSessionId !== currentSessionId) {
        localStorage.removeItem('lastInventoryLoc');
        localStorage.removeItem('lastInventoryRack');
        localStorage.setItem('lastInventorySessionId', currentSessionId);
    }

    const savedLoc = localStorage.getItem('lastInventoryLoc');
    const savedRack = localStorage.getItem('lastInventoryRack');
    
    fetchProductNames();

    if(savedRack) {
        document.getElementById('lokalizacjaInput').value = savedRack;
        document.getElementById('locationSearchCard').style.display = 'none';
        loadRack(savedRack);
    } else if(savedLoc) {
        document.getElementById('lokalizacjaInput').value = savedLoc;
        document.getElementById('locationSearchCard').style.display = 'none';
        searchLocation();
    } else {
        // Jeśli to nowa sesja i nie ma nic w localStorage, spróbuj automatycznie załadować obszar sesji
        const target = (window.INVENTORY_CONFIG.targetLokalizacja || "").trim().toUpperCase();
        if (target && target !== 'WSZYSTKO' && target !== 'WSZYSTKIE') {
            document.getElementById('lokalizacjaInput').value = target;
            document.getElementById('locationSearchCard').style.display = 'none';
            if (target.startsWith('R') && target.length >= 3 && target.length <= 4) {
                loadRack(target);
            } else {
                searchLocation();
            }
        } else {
            // Ukryj baner zakończenia na czystym ekranie wyszukiwania
            const banner = document.getElementById('floatingFinishBanner');
            if (banner) banner.style.display = 'none';
        }
    }
});



function fetchProductNames(typ = '') {
    const url = 'window.INVENTORY_CONFIG.url_podpowiedzi_nazw' + (typ ? '?typ=' + encodeURIComponent(typ) : '');
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

function searchLocation() {
    const rawLoc = document.getElementById('lokalizacjaInput').value.trim().toUpperCase();
    if(!rawLoc) return;
    
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
    
    // Fetch pallets at this location
    fetch('window.INVENTORY_CONFIG.url_szukaj_lokalizacji', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({lokalizacja: rawLoc, sesja_id: window.INVENTORY_CONFIG.sesjaId})
    })
    .then(r => r.json())
    .then(data => {
        if(data.success) {
            document.getElementById('locationSearchCard').style.display = 'none';
            document.getElementById('rackContainer').style.display = 'none';
            currentLocationPallets = data.pallets;
            renderPallets(data.pallets);
            document.getElementById('activeLocation').textContent = rawLoc;
            document.getElementById('resultsContainer').style.display = 'block';
            
            // Pokaż dolny baner z raportem i zakończeniem
            const banner = document.getElementById('floatingFinishBanner');
            if (banner) banner.style.display = 'flex';
            
            setTimeout(() => {
                const ssccInput = document.getElementById('ssccVerifierInputResults');
                if(ssccInput) ssccInput.focus();
            }, 100);
        }
    });
}

function loadRack(prefix) {
    currentRackPrefix = prefix;
    localStorage.setItem('lastInventoryRack', prefix);
    localStorage.removeItem('lastInventoryLoc');
    
    fetch('window.INVENTORY_CONFIG.url_szukaj_regalu', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prefix: prefix, sesja_id: window.INVENTORY_CONFIG.sesjaId})
    })
    .then(r => r.json())
    .then(data => {
        if(data.success) {
            rackData = data.rack_data;
            document.getElementById('locationSearchCard').style.display = 'none';
            document.getElementById('resultsContainer').style.display = 'none';
            document.getElementById('activeRack').textContent = prefix;
            renderRackGrid(prefix);
            document.getElementById('rackContainer').style.display = 'block';
            
            // Pokaż dolny baner z raportem i zakończeniem
            const banner = document.getElementById('floatingFinishBanner');
            if (banner) banner.style.display = 'flex';
            
            setTimeout(() => {
                const ssccInput = document.getElementById('ssccVerifierInputRack');
                if(ssccInput) ssccInput.focus();
            }, 100);
        }
    });
}

function renderRackGrid(prefix) {
    const grid = document.getElementById('rackGrid');
    grid.innerHTML = '';
    
    let maxCols = 10;
    let maxRows = 3;
    
    // R05 has 4 rows and 4 columns
    if (prefix === 'R05') {
        maxCols = 4;
        maxRows = 4;
    } else if (prefix === 'R06') {
        maxCols = 5;
        maxRows = 5;
    }
    
    grid.style.gridTemplateColumns = `repeat(${maxCols}, minmax(60px, 1fr))`;
    grid.style.minWidth = maxCols > 6 ? '650px' : '300px';

    for(let r = maxRows; r >= 1; r--) {
        for(let c = 1; c <= maxCols; c++) {
            const colStr = c.toString().padStart(2, '0');
            const rowStr = r.toString().padStart(2, '0');
            // Format: R010101 (prefix + col + row)
            // But prefix might be "R01" or "R-01". Let's handle clean prefix.
            const cleanPrefix = prefix.replace('-', '');
            const locId = `${cleanPrefix}${colStr}${rowStr}`;
            
            const cell = document.createElement('div');
            cell.id = `cell-${locId}`;
            cell.style.aspectRatio = '1/1';
            cell.style.background = 'white';
            cell.style.borderRadius = '4px';
            cell.style.display = 'flex';
            cell.style.flexDirection = 'column';
            cell.style.alignItems = 'center';
            cell.style.justifyContent = 'center';
            cell.style.fontSize = '8px';
            cell.style.fontWeight = '800';
            cell.style.cursor = 'pointer';
            cell.style.position = 'relative';
            
            const items = rackData[locId] || [];
            const hasCounted = items.some(i => i.counted);
            
            // Determine if there is a pallet in the slot currently (systemic or actual)
            let hasPallet = false;
            if (items.length > 0) {
                const countedItems = items.filter(i => i.counted);
                if (countedItems.length > 0) {
                    hasPallet = countedItems.some(i => i.waga_faktyczna > 0);
                } else {
                    hasPallet = true; // system has it, not counted yet
                }
            }

            if(items.length > 0) {
                cell.style.background = hasCounted ? '#dcfce7' : '#dbeafe'; // green if counted, blue if systemic exists
                cell.style.color = hasCounted ? '#166534' : '#1e40af';
            } else {
                if (hasCounted) {
                    cell.style.background = '#dcfce7'; // green if confirmed empty
                    cell.style.color = '#166534';
                } else {
                    cell.style.background = '#ffffff'; // white if system empty & uncounted
                    cell.style.color = '#94a3b8';
                }
            }

            const indicatorNum = hasPallet ? '1' : '0';
            const numColor = hasPallet ? (hasCounted ? '#166534' : '#2563eb') : '#94a3b8';
            
            cell.innerHTML = `
                <span>${colStr}-${rowStr}</span>
                <span style="font-size: 13px; font-weight: 900; margin-top: 3px; color: ${numColor};">${indicatorNum}</span>
            `;

            
            cell.onclick = () => highlightAndOpenSlot(locId);
            grid.appendChild(cell);
        }
    }
    
    // Wyrenderuj również listę palet pod regałem
    renderRackList(prefix);
}

function renderRackList(prefix) {
    const listContainer = document.getElementById('rackListContainer');
    if (!listContainer) return;
    listContainer.innerHTML = '';
    
    let allItemsOnRack = [];
    for (const [loc, items] of Object.entries(rackData)) {
        for (const item of items) {
            if (item.nazwa !== 'PUSTE GNIAZDO' && item.counted) {
                allItemsOnRack.push({ ...item, location: loc });
            }
        }
    }
    
    if (allItemsOnRack.length === 0) {
        listContainer.innerHTML = '<p style="text-align: center; color: #64748b; font-weight: 600; padding: 20px;">Brak palet na tym regale.</p>';
        return;
    }
    
    allItemsOnRack.sort((a, b) => {
        if (a.location < b.location) return -1;
        if (a.location > b.location) return 1;
        if (a.nazwa < b.nazwa) return -1;
        if (a.nazwa > b.nazwa) return 1;
        return 0;
    });
    
    let html = '<div style="background: white; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">';
    html += '<table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">';
    html += '<thead style="background: #f8fafc; border-bottom: 2px solid #e2e8f0; color: #64748b;">';
    html += '<tr><th style="padding: 12px 10px;">Lokalizacja</th><th style="padding: 12px 10px;">Produkt</th><th style="padding: 12px 10px; text-align: right;">Status</th></tr>';
    html += '</thead><tbody>';
    
    allItemsOnRack.forEach(p => {
        let statusHtml = '';
        if (p.counted) {
            if (p.waga_faktyczna === p.stan_magazynowy) {
                statusHtml = `<span style="color: #10b981;"><span class="material-icons" style="font-size: 14px; vertical-align: middle;">check_circle</span> ZGODNE</span>`;
            } else {
                statusHtml = `<span style="color: #ef4444;"><span class="material-icons" style="font-size: 14px; vertical-align: middle;">error</span> NIEZGODNE</span>`;
            }
        } else {
            statusHtml = `<span style="color: #94a3b8;">DO SPRAWDZENIA</span>`;
        }

        html += `<tr style="border-bottom: 1px solid #f1f5f9; cursor: pointer; transition: background 0.2s;" onclick="highlightAndOpenSlot('${p.location}')" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background='white'">
            <td style="padding: 12px 10px; font-weight: 800; color: #3b82f6; width: 30%;">${p.location}</td>
            <td style="padding: 12px 10px;">
                <div style="font-weight: 800; color: #0f172a; font-size: 13px;">${p.nazwa}</div>
                <div style="font-size: 10px; color: #94a3b8; font-weight: 700; margin-top: 2px;">
                    <span style="text-transform: uppercase;">${p.typ_palety}</span> • <span style="font-family: monospace;">${p.displayId}</span>
                </div>
            </td>
            <td style="padding: 12px 10px; text-align: right; font-weight: 800; width: 25%; font-size: 13px;">
                ${statusHtml}
            </td>
        </tr>`;
    });
    
    html += '</tbody></table></div>';
    listContainer.innerHTML = html;
}

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

function refreshRackData(prefix, activeLocIdToOpen) {
    return fetch('window.INVENTORY_CONFIG.url_szukaj_regalu', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prefix: prefix, sesja_id: window.INVENTORY_CONFIG.sesjaId})
    })
    .then(r => r.json())
    .then(data => {
        if(data.success) {
            rackData = data.rack_data;
            renderRackGrid(prefix);
            if(activeLocIdToOpen) {
                openSlotDetail(activeLocIdToOpen);
            }
        }
    });
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
                
                smartFetch('window.INVENTORY_CONFIG.url_zapisz_wpis', {
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
        smartFetch('window.INVENTORY_CONFIG.url_zapisz_wpis', {
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
            smartFetch('window.INVENTORY_CONFIG.url_zapisz_wpis', {
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

function markCellDone(locId, isEmpty) {
    const cell = document.getElementById(`cell-${locId}`);
    if(cell) {
        cell.style.background = '#dcfce7'; 
        cell.style.color = '#166534';
        cell.style.borderColor = '#10b981';
        
        const col = locId.slice(-4, -2);
        const row = locId.slice(-2);
        
        const val = isEmpty ? '0' : '1';
        const numColor = isEmpty ? '#94a3b8' : '#166534';
        
        cell.innerHTML = `
            <span>${col}-${row}</span>
            <span style="font-size: 13px; font-weight: 900; margin-top: 3px; color: ${numColor};">${val}</span>
        `;
    }
}


function renderPallets(pallets) {
    const list = document.getElementById('palletsList');
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
                           id="winput-${index}" placeholder="STAN FAKTYCZNY" autocomplete="off" inputmode="decimal"
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

function saveEntry(pallet, actualWeight, cardElement, btn, unit) {
    const weight = parseFloat(actualWeight);
    if(isNaN(weight)) return alert('Podaj poprawną wagę!');
    
    if(btn) { btn.innerHTML = '<span class="material-icons">hourglass_top</span>'; btn.style.background='#94a3b8'; }

    smartFetch('window.INVENTORY_CONFIG.url_zapisz_wpis', {
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
    if(confirm('Zakończyć sesję inwentaryzacji #window.INVENTORY_CONFIG.sesjaId?\n\nSesja zostanie zamknięta. Możesz ją potem zatwierdzić z raportu.')) {
        smartFetch('/magazyn/inwentaryzacja/api/zamknij-sesje', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({sesja_id: window.INVENTORY_CONFIG.sesjaId})
        }).then(r=>r.json()).then(data => {
            if(data.success) {
                window.location.href = 'window.INVENTORY_CONFIG.url_raport';
            } else {
                alert('Błąd: ' + (data.message || data.error));
            }
        });
    }
}

function clearSkaner() {
    document.getElementById('lokalizacjaInput').value = '';
    document.getElementById('resultsContainer').style.display = 'none';
    document.getElementById('rackContainer').style.display = 'none';
    document.getElementById('locationSearchCard').style.display = 'block';
    localStorage.removeItem('lastInventoryLoc');
    localStorage.removeItem('lastInventoryRack');
    
    // Ukryj dolny baner zakończenia
    const banner = document.getElementById('floatingFinishBanner');
    if (banner) banner.style.display = 'none';
    
    document.getElementById('lokalizacjaInput').focus();
}
let lookedUpPalletId = null;
let lookedUpSystemWeight = 0;
let lookupTimeout = null;

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
    lookedUpPalletId = null;
    lookedUpSystemWeight = 0;
    
    const statusDiv = document.getElementById('lookupStatus');
    if(statusDiv) {
        statusDiv.style.display = 'none';
        statusDiv.textContent = '';
    }
    
    const typeSelect = document.getElementById('newPalletType');
    if(selectedType) {
        typeSelect.value = selectedType;
    }
    
    document.getElementById('newPalletLoc').value = loc || lastLocation;
    document.getElementById('newPalletSSCC').value = '';
    document.getElementById('newPalletName').value = '';
    document.getElementById('newPalletWeight').value = '0';
    document.getElementById('newPalletUnit').value = (typeSelect.value === 'opakowanie') ? 'szt' : 'kg';
    document.getElementById('newPalletBatch').value = '';
    document.getElementById('newPalletDateProd').value = '';
    document.getElementById('newPalletDateExp').value = '';
    document.getElementById('newPalletPackaging').value = 'brak';
    document.getElementById('newPalletModal').style.display = 'flex';
    document.getElementById('newPalletSSCC').focus();
    document.getElementById('newPalletSSCC').select();
    
    fetchProductNames(typeSelect.value);
}

// Switch unit automatically based on category/type choice and regenerate SSCC
document.addEventListener('DOMContentLoaded', () => {
    const typeSelect = document.getElementById('newPalletType');
    if (typeSelect) {
        typeSelect.addEventListener('change', (e) => {
            const val = e.target.value;
            document.getElementById('newPalletUnit').value = (val === 'opakowanie') ? 'szt' : 'kg';
            
            const ssccInput = document.getElementById('newPalletSSCC');
            
            fetchProductNames(val);
        });
    }
});

function saveNewPallet() {
    const sscc = document.getElementById('newPalletSSCC').value.trim();
    const name = document.getElementById('newPalletName').value.trim();
    const type = document.getElementById('newPalletType').value;
    const weight = parseFloat(document.getElementById('newPalletWeight').value);
    const batch = document.getElementById('newPalletBatch').value.trim() || 'NOWA';
    const dProd = document.getElementById('newPalletDateProd').value;
    const dExp = document.getElementById('newPalletDateExp').value;
    const loc = document.getElementById('newPalletLoc').value;
    const packaging = document.getElementById('newPalletPackaging').value;
    const unit = document.getElementById('newPalletUnit').value;

    if(!sscc || !name || isNaN(weight)) return alert('Wypełnij wszystkie pola!');
    
    smartFetch('window.INVENTORY_CONFIG.url_zapisz_wpis', {
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
            document.getElementById('newPalletModal').style.display = 'none';
            if(currentRackPrefix) {
                markCellDone(loc, false);
                refreshRackData(currentRackPrefix, loc); // Refresh rack data AND slot detail popup!
            } else {
                searchLocation(); // Refresh list
            }
        } else {
            alert("Błąd: " + data.message);
        }
    });
}

function openInstructionsModal() {
    document.getElementById('instructionsModal').style.display = 'flex';
}
function closeInstructionsModal() {
    document.getElementById('instructionsModal').style.display = 'none';
}
// Close instructions modal when clicking backdrop
document.getElementById('instructionsModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('instructionsModal')) {
        closeInstructionsModal();
    }
});

// --- Dodatkowe funkcje --- 

let currentMovePallet = null;
let currentMoveOriginalLoc = null;

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

function verifyPalletSSCC(sscc, context) {
    if(!sscc) return;
    sscc = sscc.trim().toUpperCase();
    
    let foundLocally = false;
    let targetLoc = context === 'detail' ? document.getElementById('detailLocTitle').textContent : lastLocation;
    
    if (context === 'results') {
        const p = currentLocationPallets.find(p => (p.displayId && p.displayId.toUpperCase().includes(sscc)) || (p.nr_palety && p.nr_palety.toUpperCase().includes(sscc)));
        if (p) {
            foundLocally = true;
            p._unhidden = true;
            renderPallets(currentLocationPallets);
            
            setTimeout(() => {
                const cards = document.querySelectorAll('#resultsContainer .pallet-card');
                for (let card of cards) {
                    if (card.textContent.toUpperCase().includes(sscc)) {
                        highlightAndFocusCard(card);
                        break;
                    }
                }
            }, 100);
            safeToast('✅ Paleta przypisana do tej lokalizacji!', 'success');
        }
    } else if (context === 'detail') {
        let items = rackData[targetLoc] || [];
        const p = items.find(item => (item.displayId && item.displayId.toUpperCase().includes(sscc)) || (item.nr_palety && item.nr_palety.toUpperCase().includes(sscc)));
        if (p) {
            foundLocally = true;
            p._unhidden = true;
            openSlotDetail(targetLoc);
            
            setTimeout(() => {
                const cards = document.querySelectorAll('#slotDetail .pallet-card');
                for (let card of cards) {
                    if (card.textContent.toUpperCase().includes(sscc)) {
                        highlightAndFocusCard(card);
                        break;
                    }
                }
            }, 100);
            safeToast('✅ Paleta przypisana do tego gniazda!', 'success');
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
                let did = item.displayId ? String(item.displayId).toUpperCase() : '';
                let nrp = item.nr_palety ? String(item.nr_palety).toUpperCase() : '';
                let nzw = item.nazwa ? String(item.nazwa).toUpperCase() : '';
                
                if ((did && (did.includes(sscc) || sscc.includes(did))) || 
                    (nrp && (nrp.includes(sscc) || sscc.includes(nrp))) || 
                    (nzw && (nzw.includes(sscc) || sscc.includes(nzw)))) {
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
        safeToast('✅ Paleta znajduje się w gnieździe ' + foundLocId, 'success');
        highlightAndOpenSlot(foundLocId);
        
        setTimeout(() => {
            const cards = document.querySelectorAll('#slotDetail .pallet-card');
            for (let card of cards) {
                if (card.textContent.toUpperCase().includes(sscc)) {
                    highlightAndFocusCard(card);
                    break;
                }
            }
        }, 400);
    } else {
        globalSearchAndPrompt(sscc, 'rack', null);
    }
}

function highlightAndFocusCard(card) {
    card.style.outline = '4px solid #10b981';
    card.style.transform = 'scale(1.02)';
    card.scrollIntoView({behavior: 'smooth', block: 'center'});
    
    setTimeout(() => {
        card.style.outline = 'none';
        card.style.transform = 'none';
    }, 2000);
    
    const weightInput = card.querySelector('.actual-weight-input') || card.querySelector('.slot-weight-input');
    if (weightInput) {
        setTimeout(() => weightInput.focus(), 300);
    }
}

function globalSearchAndPrompt(sscc, context, targetLoc) {
    safeToast('Szukanie palety w systemie...', 'info');
    fetch('window.INVENTORY_CONFIG.url_szukaj_globalnie', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({sscc: sscc})
    })
    .then(r => r.json())
    .then(data => {
        if(data.success && data.paleta) {
            if (context === 'rack') {
                AppDialog.alert(
                    `Paleta <b>${sscc}</b> (${data.paleta.nazwa}) znajduje się w lokalizacji: <b>${data.paleta.lokalizacja}</b>.<br><br>Aby ją zweryfikować, najpierw zeskanuj lub wybierz odpowiednie gniazdo na tym regale.`,
                    'Paleta w innej lokalizacji'
                ).then(() => refocusRackScanner());
            } else {
                AppDialog.confirm(
                    `Paleta <b>${sscc}</b> (${data.paleta.nazwa}) znajduje się w innej lokalizacji: <b>${data.paleta.lokalizacja}</b>.<br><br>Czy przenieść ją do <b>${targetLoc}</b> i zweryfikować?`,
                    'Paleta znaleziona'
                ).then(confirmed => {
                    if(confirmed) {
                        movePalletToLocation(data.paleta, targetLoc, context);
                    } else {
                        if (context === 'detail') refocusDetailScanner();
                    }
                });
            }
        } else {
            AppDialog.alert(`Paleta z kodem <b>${sscc}</b> NIE ZNAJDUJE SIĘ w bieżącym widoku ani w bazie systemu.<br><br>Dodaj ją ręcznie klikając "DODAJ PALETĘ".`, 'Brak palety').then(() => {
                if (context === 'detail') refocusDetailScanner();
                if (context === 'rack') refocusRackScanner();
            });
        }
    }).catch(e => {
        AppDialog.alert('Błąd połączenia podczas globalnego szukania palety.', 'Błąd');
    });
}

function movePalletToLocation(paleta, targetLoc, context) {
    let mapTyp = 'PAL';
    const t = (paleta.typ || '').toLowerCase();
    if(t.includes('surowiec')) mapTyp = 'surowiec';
    else if(t.includes('opakowanie')) mapTyp = 'opakowanie';
    else if(t.includes('dodatek')) mapTyp = 'dodatek';

    smartFetch('window.INVENTORY_CONFIG.url_zapisz_wpis', {
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
            linia: paleta.linia,
            typ_opakowania: '',
            jednostka: paleta.jednostka || 'kg'
        })
    }).then(r => r.json()).then(saveData => {
        if (saveData.success) {
            safeToast('Paleta przypisana pomyślnie!', 'success');
            if(context === 'results') {
                searchLocation(); 
            } else if(context === 'detail') {
                fetch('window.INVENTORY_CONFIG.url_szukaj_regalu', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({prefix: currentRackPrefix, sesja_id: window.INVENTORY_CONFIG.sesjaId})
                })
                .then(r => r.json())
                .then(data => {
                    if(data.success) {
                        rackData = data.rack_data;
                        renderRackGrid(currentRackPrefix);
                        highlightAndOpenSlot(targetLoc); 
                    }
                });
            }
        } else {
            AppDialog.alert(saveData.message || 'Wystąpił błąd', 'Błąd zapisu');
        }
    }).catch(e => {
        AppDialog.alert('Błąd połączenia podczas przypisywania.', 'Błąd');
    });
}
let currentPrintPalletId = null;
let currentPrintPalletType = null;

function openPrinterModal(palletId, palletType) {
    openSharedPrinterModal({id: palletId, type: palletType}, function(printerId, payload) {
        safeToast('Wysyłanie do druku...', 'info');
        fetch('window.INVENTORY_CONFIG.url_print_pallet_label', {
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
