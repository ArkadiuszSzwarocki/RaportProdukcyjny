
function generateTableRow(item, index) {
    const isBlockedCls = item.is_blocked ? 'is-blocked-row' : '';
    const icon = item.is_blocked ? '<span class="material-icons" style="color: #be123c; font-size: 16px;">block</span>' : '<span class="material-icons" style="color: #10b981; font-size: 16px;">check_circle</span>';
    
    return `<tr class="pallet-row ${isBlockedCls}"
                style="cursor: pointer;"
                data-display-id="${item.displayId}"
                data-product="${item.productName.replace(/"/g, '&quot;')}"
                data-amount="${item.amount}"
                data-location="${item.location}"
                data-type="${item.type}"
                data-date="${item.date_prod}"
                data-id="${item.id}"
                data-linia="${item.linia}"
                data-blocked="${item.is_blocked}"
                data-date-added="${item.date_added}">
        <td style="text-align: center; color: #94a3b8; font-weight: 700; background: #f8fafc; font-size: 11px;">${index}</td>
        <td class="font-bold">
            <div style="display: flex; align-items: center; gap: 6px;">
                ${icon}
                ${item.displayId}
            </div>
        </td>
        <td data-label="Produkt">
            <strong class="text-primary">${item.productName}</strong>
        </td>
        <td data-label="Ilość"><strong>${item.amount}</strong> <small>${item.unit}</small></td>
        <td data-label="Lokalizacja" class="location-cell" data-loc-raw="${item.location}">
            ${formatLocation(item.location)}
        </td>
        <td data-label="Typ">
            <span class="status-badge" style="font-size: 10px; padding: 2px 8px;">${item.type}</span>
        </td>
        <td data-label="Produkcja" class="time-display">${item.date_prod}</td>
        <td data-label="Ważność" class="time-display">${item.date_exp}</td>
    </tr>`;
}

function generateGridCard(item) {
    const isBlockedCls = item.is_blocked ? 'is-blocked-card' : '';
    const icon = item.is_blocked ? '<span class="material-icons text-danger" style="font-size: 18px;">block</span>' : '';
    let loc_code = (item.location || '').toUpperCase();
    let loc_html = item.location || '???';
    if (loc_code.length >= 7 && loc_code.startsWith('R')) {
        loc_html = `<span class="location-part-rack">${loc_code.substring(0,3)}</span>
                    <span class="location-separator"> </span>
                    <span class="location-part-place">${loc_code.substring(3,5)}</span>
                    <span class="location-separator"> </span>
                    <span class="location-part-row">${loc_code.substring(5,7)}</span>`;
    }

    return `<div class="pallet-card ${isBlockedCls}"
                 style="cursor: pointer;"
                 data-display-id="${item.displayId}"
                 data-product="${item.productName.replace(/"/g, '&quot;')}"
                 data-amount="${item.amount}"
                 data-location="${item.location}"
                 data-type="${item.type}"
                 data-date="${item.date_prod}"
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
            <div class="product-name">${item.productName}</div>
            <div class="amount-row">
                <span class="val">${item.amount}</span>
                <span class="unit">${item.unit}</span>
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
    if (input) { input.value = ''; localStorage.removeItem('warehouse_search'); }
    currentSearchQuery = '';
    // Reset radio buttons
    const allWh = document.getElementById('radio-all');
    if (allWh) { allWh.checked = true; currentWarehouseId = 'all'; }
    const allRack = document.getElementById('rack-all');
    if (allRack) { allRack.checked = true; currentSubWarehouseId = 'all'; }
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

    // 1. Jeśli wybrano konkretny regał/podlokalizację (R01, R02 itp.) - to jest priorytet
    if (currentSubWarehouseId && currentSubWarehouseId !== 'all') {
        const selectedRack = normalizeLocationCode(currentSubWarehouseId);
        if (!selectedRack) return true;
        if (locParts) {
            return locParts.rack === selectedRack;
        }
        return locNormalized.includes(selectedRack);
    }

    // 2. Jeśli nie wybrano regału, filtrujemy po magazynie głównym
    if (!currentWarehouseId || currentWarehouseId === 'all') {
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

console.log("[magazyny_nowe] Logika filtrowania zainicjowana.");

