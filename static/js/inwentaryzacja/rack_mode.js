function loadRack(prefix, slotToOpen = null) {
    const normPrefix = normalizeRackPrefix(prefix);
    const slot = slotToOpen && normalizeLocationCode(slotToOpen);
    if (slot && !isSlotOnInventoryRack(slot, normPrefix)) {
        safeToast('Nie ma takiego gniazda: ' + slot, 'error');
        return Promise.resolve();
    }
    
    return fetch(window.INVENTORY_CONFIG.url_szukaj_regalu, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prefix: normPrefix, sesja_id: window.INVENTORY_CONFIG.sesjaId})
    })
    .then(r => r.json())
    .then(data => {
        if(data.success) {
            currentRackPrefix = normPrefix;
            localStorage.setItem('lastInventoryRack', normPrefix);
            localStorage.removeItem('lastInventoryLoc');
            closeDetail();
            rackData = data.rack_data || {};
            document.getElementById('locationSearchCard').style.display = 'none';
            document.getElementById('resultsContainer').style.display = 'none';
            const blindContainer = document.getElementById('blindScanContainer');
            if (blindContainer) blindContainer.style.display = 'none';

            document.getElementById('activeRack').textContent = normPrefix;
            renderRackGrid(normPrefix);
            document.getElementById('rackContainer').style.display = 'block';
            
            // Pokaż dolny baner z raportem i zakończeniem
            const banner = document.getElementById('floatingFinishBanner');
            if (banner) banner.style.display = 'flex';
            
            if (slotToOpen) {
                const normSlot = normalizeLocationCode(slotToOpen);
                highlightAndOpenSlot(normSlot);
            } else {
                refocusRackScanner();
            }
        } else {
            safeToast(data.message || 'Nie można otworzyć tego regału.', 'error');
        }
    }).catch(() => safeToast('Nie udało się sprawdzić regału.', 'error'));
}


function inventoryRackDimensions(prefix) {
    return ({R04: [6, 3], R05: [4, 4], R06: [5, 5], R07: [11, 4], R09: [4, 6]})[prefix] || [10, 3];
}

function isSlotOnInventoryRack(slot, prefix) {
    if (!/^R[0-9]{6}$/.test(slot) || !slot.startsWith(prefix)) return false;
    const [maxCols, maxRows] = inventoryRackDimensions(prefix);
    const col = Number(slot.slice(3, 5));
    const row = Number(slot.slice(5, 7));
    return col >= 1 && col <= maxCols && row >= 1 && row <= maxRows;
}

function renderRackGrid(prefix) {
    const normPrefix = normalizeRackPrefix(prefix);
    const grid = document.getElementById('rackGrid');
    grid.innerHTML = '';
    
    const [maxCols, maxRows] = inventoryRackDimensions(normPrefix);

    grid.style.gridTemplateColumns = `repeat(${maxCols}, minmax(60px, 1fr))`;
    grid.style.minWidth = maxCols > 6 ? `${Math.max(650, maxCols * 62)}px` : '300px';

    for (let r = maxRows; r >= 1; r--) {
        for(let c = 1; c <= maxCols; c++) {
            const colStr = c.toString().padStart(2, '0');
            const rowStr = r.toString().padStart(2, '0');
            // Format: R010101 (normPrefix + col + row)
            const locId = `${normPrefix}${colStr}${rowStr}`;
            
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
            const pending = items.filter(item => !item.counted && item.nazwa !== 'PUSTE GNIAZDO');
            const counted = items.filter(item => item.counted);
            const complete = counted.length > 0 && pending.length === 0;
            const present = items.filter(item => item.nazwa !== 'PUSTE GNIAZDO' &&
                Number(item.counted ? item.waga_faktyczna : item.stan_magazynowy) > 0);
            const partial = counted.length > 0 && pending.length > 0;
            cell.style.background = complete ? '#dcfce7' : partial ? '#fef3c7' : items.length ? '#dbeafe' : 'white';
            cell.style.color = complete ? '#166534' : partial ? '#92400e' : items.length ? '#1e40af' : '#94a3b8';
            const indicatorNum = String(present.length);
            const numColor = cell.style.color;

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
    
    function rackListOrder(location) {
        const code = normalizeLocationCode(location);
        if (!/^R[0-9]{6}$/.test(code)) return 'Z' + code;
        // The stored slot code has the position before the row.
        return code.slice(0, 3) + code.slice(5, 7) + code.slice(3, 5);
    }

    allItemsOnRack.sort((a, b) =>
        rackListOrder(a.location).localeCompare(rackListOrder(b.location)) ||
        a.nazwa.localeCompare(b.nazwa, 'pl')
    );
    
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


function refreshRackData(prefix, activeLocIdToOpen) {
    return fetch(window.INVENTORY_CONFIG.url_szukaj_regalu, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prefix: prefix, sesja_id: window.INVENTORY_CONFIG.sesjaId})
    })
    .then(r => r.json())
    .then(data => {
        if(data.success && currentRackPrefix === prefix) {
            rackData = data.rack_data;
            renderRackGrid(prefix);
            if(activeLocIdToOpen) {
                openSlotDetail(activeLocIdToOpen);
            }
        }
    });
}


function markCellDone(locId, isEmpty) {
    const cell = document.getElementById(`cell-${locId}`);
    if(cell) {
        cell.style.background = '#dcfce7'; 
        cell.style.color = '#166534';
        cell.style.borderColor = '#10b981';
        
        const col = locId.slice(-4, -2);
        const row = locId.slice(-2);
        
        const items = rackData[locId] || [];
        let val = isEmpty ? '0' : '1';
        if (!isEmpty) {
            const countedActive = items.filter(i => i.nazwa !== 'PUSTE GNIAZDO' && i.counted && parseFloat(i.waga_faktyczna || 0) > 0).length;
            val = String(countedActive > 0 ? countedActive : 1);
        }
        const numColor = isEmpty ? '#94a3b8' : '#166534';
        
        cell.innerHTML = `
            <span>${col}-${row}</span>
            <span style="font-size: 13px; font-weight: 900; margin-top: 3px; color: ${numColor};">${val}</span>
        `;
    }
}



