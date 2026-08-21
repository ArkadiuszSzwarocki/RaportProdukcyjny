
function generateTableRow(item, index) {
    const isBlockedCls = item.is_blocked ? 'is-blocked-row' : '';
    const isFirstFifo = Boolean(item.is_first_fifo);
    const rowStyle = isFirstFifo 
        ? 'cursor: pointer; background: #fffbeb !important; border-left: 4px solid #f59e0b;' 
        : 'cursor: pointer;';
    const icon = item.is_blocked 
        ? '<span class="material-icons" style="color: #be123c; font-size: 16px;">block</span>' 
        : (isFirstFifo 
            ? '<span class="material-icons" style="color: #ea580c; font-size: 16px;" title="Pierwsza partia do zużycia (FIFO)">bolt</span>'
            : '<span class="material-icons" style="color: #10b981; font-size: 16px;">check_circle</span>');
    
    const fifoBadge = isFirstFifo
        ? `<span class="badge" style="background: #f59e0b; color: #ffffff; font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 4px; display: inline-flex; align-items: center; gap: 3px; margin-left: 6px; vertical-align: middle; box-shadow: 0 1px 2px rgba(245,158,11,0.25);">
                <span class="material-icons" style="font-size: 12px;">bolt</span> 1. DO ZUŻYCIA (FIFO)
           </span>`
        : (item.fifo_batch_num && item.fifo_batch_num > 1 ? `<span class="badge" style="background: #f1f5f9; color: #475569; font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 4px; margin-left: 6px; vertical-align: middle;">Partia ${item.fifo_batch_num}</span>` : (item.fifo_index && item.fifo_total > 1 ? `<span class="badge" style="background: #f1f5f9; color: #475569; font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 4px; margin-left: 6px; vertical-align: middle;">FIFO #${item.fifo_index}</span>` : ''));

    const batchSubtitle = (item.batch && item.batch !== '-' && item.batch !== 'brak')
        ? `<div style="font-size: 11px; color: #64748b; font-weight: 600; margin-top: 2px;">Partia: <span style="font-family: monospace; color: #334155; font-weight: 700;">${item.batch}</span></div>`
        : '';

    const displayName = (item.productName && item.productName !== '-' && item.productName.trim() !== '') ? item.productName : (item.produkt || item.nazwa || 'Nieznany produkt');

    return `<tr class="pallet-row ${isBlockedCls}"
                style="${rowStyle}"
                data-display-id="${item.displayId}"
                data-product="${displayName.replace(/"/g, '&quot;')}"
                data-amount="${item.amount}"
                data-unit="${item.unit || 'kg'}"
                data-location="${item.location}"
                data-type="${item.type}"
                data-date="${item.date_prod}"
                data-date-exp="${item.date_exp || '-'}"
                data-batch="${(item.batch || '-').replace(/"/g, '&quot;')}"
                data-id="${item.id}"
                data-linia="${item.linia}"
                data-blocked="${item.is_blocked}"
                data-date-added="${item.date_added}">
        <td style="text-align: center; color: #94a3b8; font-weight: 700; background: ${isFirstFifo ? '#fef3c7' : '#f8fafc'}; font-size: 11px;">${index}</td>
        <td class="font-bold">
            <div style="display: flex; align-items: center; gap: 6px;">
                ${icon}
                ${item.displayId}
            </div>
        </td>
        <td data-label="Produkt">
            <strong class="text-primary">${displayName}</strong>
            ${fifoBadge}
            ${batchSubtitle}
        </td>
        <td data-label="Ilość"><strong>${item.amount}</strong> <small>${item.unit}</small></td>
        <td data-label="Lokalizacja" class="location-cell" data-loc-raw="${item.location}">
            ${formatLocation(item.location)}
        </td>
        <td data-label="Typ">
            <span class="status-badge" style="font-size: 10px; padding: 2px 8px;">${item.type}</span>
        </td>
        <td data-label="Produkcja" class="time-display">${item.date_prod}</td>
        <td data-label="Ważność" class="time-display" style="${isFirstFifo ? 'color: #ea580c; font-weight: 700;' : ''}">${item.date_exp}</td>
    </tr>`;
}

function generateGridCard(item) {
    const isBlockedCls = item.is_blocked ? 'is-blocked-card' : '';
    const isFirstFifo = Boolean(item.is_first_fifo);
    const cardFifoStyle = isFirstFifo ? 'border: 2px solid #f59e0b; background: #fffbeb;' : '';
    const icon = item.is_blocked 
        ? '<span class="material-icons text-danger" style="font-size: 18px;">block</span>' 
        : (isFirstFifo 
            ? '<span class="badge" style="background: #f59e0b; color: white; font-size: 9px; font-weight: 800; padding: 2px 5px; border-radius: 4px; display: inline-flex; align-items: center; gap: 2px;"><span class="material-icons" style="font-size: 10px;">bolt</span> 1. FIFO</span>' 
            : '');

    let loc_code = (item.location || '').toUpperCase();
    let loc_html = item.location || '???';
    if (loc_code.length >= 7 && loc_code.startsWith('R')) {
        loc_html = `<span class="location-part-rack">${loc_code.substring(0,3)}</span>
                    <span class="location-separator"> </span>
                    <span class="location-part-place">${loc_code.substring(3,5)}</span>
                    <span class="location-separator"> </span>
                    <span class="location-part-row">${loc_code.substring(5,7)}</span>`;
    }

    const batchSubtitle = (item.batch && item.batch !== '-' && item.batch !== 'brak')
        ? `<div style="font-size: 11px; color: #64748b; font-weight: 600; margin-top: 2px;">Partia: <span style="font-family: monospace; color: #334155; font-weight: 700;">${item.batch}</span></div>`
        : '';

    const displayName = (item.productName && item.productName !== '-' && item.productName.trim() !== '') ? item.productName : (item.produkt || item.nazwa || 'Nieznany produkt');

    return `<div class="pallet-card ${isBlockedCls}"
                 style="cursor: pointer; ${cardFifoStyle}"
                 data-display-id="${item.displayId}"
                 data-product="${displayName.replace(/"/g, '&quot;')}"
                 data-amount="${item.amount}"
                 data-unit="${item.unit || 'kg'}"
                 data-location="${item.location}"
                 data-type="${item.type}"
                 data-date="${item.date_prod}"
                 data-date-exp="${item.date_exp || '-'}"
                 data-batch="${(item.batch || '-').replace(/"/g, '&quot;')}"
                 data-id="${item.id}"
                 data-linia="${item.linia}"
                 data-blocked="${item.is_blocked}"
                 data-date-added="${item.date_added}">
        <div class="card-header">
            <span class="loc-tag" data-loc-raw="${item.location}">
                ${loc_html}
            </span>
            <span class="id-tag">#${item.displayId}</span>
        </div>
        <div class="card-body">
            <div class="product-name">${displayName}</div>
            ${batchSubtitle}
            <div class="amount-row">
                <span class="val">${item.amount}</span>
                <span class="unit">${item.unit}</span>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-top: 6px; padding-top: 4px; border-top: 1px dashed #e2e8f0;">
                <span>Prod: <strong style="color: #334155;">${item.date_prod}</strong></span>
                <span>Ważn: <strong style="${isFirstFifo ? 'color: #ea580c; font-weight: 700;' : 'color: #0284c7;'}">${item.date_exp}</strong></span>
            </div>
        </div>
        <div class="card-footer">
            <span class="type-label">${item.type}</span>
            ${icon}
        </div>
    </div>`;
}

function _updateFilterBanner(filter, visible, total) {
    // Znajdź lub stwórz banner
    let banner = document.getElementById('filterStatusBanner');
    const tableWrapper = document.querySelector('.list-view-wrapper');
    if (!tableWrapper) return;

    const hasSearch = filter && filter.length > 0;
    const hasWarehouse = currentWarehouseId && currentWarehouseId !== 'all';
    const hasRack = currentSubWarehouseId && currentSubWarehouseId !== 'all';
    const isFiltered = hasSearch || hasWarehouse || hasRack;

    if (!isFiltered) {
        // Ukryj banner gdy brak filtra
        if (banner) banner.style.display = 'none';
        return;
    }

    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'filterStatusBanner';
        banner.style.cssText = [
            'display:flex', 'align-items:center', 'gap:6px',
            'padding:6px 10px', 'margin-bottom:8px',
            'background:#eff6ff',
            'border-radius:8px',
            'font-size:12px', 'font-weight:500', 'color:#1d4ed8',
            'flex-wrap:wrap', 'justify-content:space-between'
        ].join(';');
        tableWrapper.insertAdjacentElement('beforebegin', banner);
    }

    // Buduj treść bannera
    const parts = [];
    if (hasSearch) parts.push(`<strong>"${filter}"</strong>`);
    if (hasWarehouse) parts.push(`Magazyn: <strong>${currentWarehouseId}</strong>`);
    if (hasRack) parts.push(`Regał: <strong>${currentSubWarehouseId}</strong>`);

    const hidden = total - visible;
    const resultInfo = hidden > 0
        ? `<span style="background:#1d4ed8;color:#fff;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;">${visible} z ${total}</span>`
        : `<span style="background:#10b981;color:#fff;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;">Wszystkie ${total}</span>`;

    banner.style.display = 'flex';
    banner.innerHTML = `
        <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
            <span>Przefiltrowano: ${parts.join(', ')}</span>
            ${resultInfo}
        </div>
        <button onclick="clearAllFilters()" style="border:none;background:none;cursor:pointer;color:#64748b;font-size:16px;padding:0 4px;line-height:1;display:flex;align-items:center;" title="Wyczyść filtry">
            <span class="material-icons" style="font-size:16px;">close</span>
        </button>
    `;
}

function clearAllFilters() {
    const input = document.getElementById('searchInput');
    if (input) { 
        input.value = ''; 
        localStorage.removeItem('warehouse_search'); 
    }
    const clearBtn = document.getElementById('clearSearchBtn');
    if (clearBtn) clearBtn.style.display = 'none';
    currentSearchQuery = '';

    // Reset radio buttons
    const allWh = document.getElementById('radio-all');
    if (allWh) { 
        allWh.checked = true; 
        currentWarehouseId = 'all'; 
        localStorage.setItem('warehouse_tab', 'all');
        if (typeof updateWhLabel === 'function') updateWhLabel('Wszystkie');
    }
    const allRack = document.getElementById('rack-all');
    if (allRack) { 
        allRack.checked = true; 
        currentSubWarehouseId = 'all'; 
        localStorage.setItem('warehouse_subtab', 'all');
        if (typeof updateRackLabel === 'function') updateRackLabel('Wszystkie Lokalizacje');
    }

    // Reset location checkboxes
    localStorage.removeItem('warehouse_locations');
    const checkboxes = document.querySelectorAll('.loc-checkbox');
    checkboxes.forEach(cb => cb.checked = true);
    selectedLocations = Array.from(checkboxes).map(cb => cb.value);
    if (typeof updateLocationDropdownLabel === 'function') {
        updateLocationDropdownLabel(checkboxes.length);
    }

    // Reset sorting
    currentSortCol = null;
    currentSortDir = 'asc';
    localStorage.removeItem('warehouse_sort_col');
    localStorage.removeItem('warehouse_sort_dir');
    if (typeof updateSortHeaderIndicators === 'function') {
        updateSortHeaderIndicators();
    }

    filterTable();
}

function isMatch(allText, locText, filter, locationFiltersArray) {
    const filterText = (filter || '').toUpperCase().trim();
    const textMatch = (filterText === "" || allText.indexOf(filterText) > -1);
    const slotMatch = (filterText !== "" && matchesLocationSlots(locText, filterText));

    if (!(textMatch || slotMatch)) return false;
    
    if (Array.isArray(locationFiltersArray) && locationFiltersArray.length > 0) {
        if (!locText) return false;
        const upLoc = locText.toUpperCase().trim();
        const matched = locationFiltersArray.some(f => upLoc === f || upLoc.startsWith(f));
        if (!matched) return false;
    }

    const locNormalized = normalizeLocationCode(locText);
    const locParts = parseLocationCode(locText);
    const upLoc = (locText || '').toUpperCase();
    const isOsip = upLoc.includes('OSIP') || upLoc.startsWith('OS');

    // 0. Magazyn OSIP widzi WYŁĄCZNIE własne lokalizacje (OS*, OSIP)
    if (currentWarehouseId === 'OSIP') {
        if (!isOsip) return false;
        
        if (currentSubWarehouseId && currentSubWarehouseId !== 'all') {
            if (currentSubWarehouseId === 'OS01') return upLoc.includes('OS01');
            if (currentSubWarehouseId === 'A') return upLoc.startsWith('A');
            return upLoc.includes(currentSubWarehouseId.toUpperCase());
        }
        return true;
    }

    // 1. Jeśli wybrano konkretny regał/podlokalizację (R01, R02, OS01, A itp.) - to jest priorytet
    if (currentSubWarehouseId && currentSubWarehouseId !== 'all') {
        if (currentSubWarehouseId === 'OS01') {
            return upLoc.includes('OS01');
        }
        if (currentSubWarehouseId === 'A') {
            return upLoc.startsWith('A');
        }
        const selectedRack = normalizeLocationCode(currentSubWarehouseId);
        if (!selectedRack) return true;
        if (locParts) {
            return locParts.rack === selectedRack;
        }
        return locNormalized.includes(selectedRack);
    }

    // 2. Jeśli nie wybrano regału, filtrujemy po magazynie głównym
    if (!currentWarehouseId || currentWarehouseId === 'all') {
        if (isOsip) {
            return false;
        }
        return true;
    }
    
    if (currentWarehouseId === 'MS01') {
        // MS01 shows its floor and racks R04-R07
        // Only match specific MS01 to avoid false positives with MP01-PODŁOGA
        return locText.includes('MS01') || 
               ['R04', 'R05', 'R06', 'R07'].some(r => (locParts ? locParts.rack === r : locText.includes(r)));
    }
    
    if (currentWarehouseId === 'MP01') {
        // MP01 shows its floor and racks R01-R03
        return locText.includes('MP01') || locText.includes('PODŁOGA') || 
               ['R01', 'R02', 'R03'].some(r => (locParts ? locParts.rack === r : locText.includes(r)));
    }

    // Inne magazyny (MGW, PSD, MDO, MOP)
    const searchPart = currentWarehouseId.toUpperCase().replace('BF_', '');
    return locText.includes(searchPart);
}

console.log("[warehouse_v2] Logika filtrowania zainicjowana.");

