function loadRack(prefix) {
    currentRackPrefix = prefix;
    localStorage.setItem('lastInventoryRack', prefix);
    localStorage.removeItem('lastInventoryLoc');
    
    fetch(window.INVENTORY_CONFIG.url_szukaj_regalu, {
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


function refreshRackData(prefix, activeLocIdToOpen) {
    return fetch(window.INVENTORY_CONFIG.url_szukaj_regalu, {
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



