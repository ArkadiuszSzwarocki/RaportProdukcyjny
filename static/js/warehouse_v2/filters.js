// ---- WAREHOUSE FILTERING & TABS ----
function switchWarehouse(warehouseId, keepCurrentSubtab = false) {
    console.log("Przełączanie magazynu na:", warehouseId, "keepCurrentSubtab:", keepCurrentSubtab);
    
    currentWarehouseId = warehouseId;
    localStorage.setItem('warehouse_tab', warehouseId);
    
    // Dynamiczne ukrywanie/pokazywanie opcji w menu regałów
    document.querySelectorAll('.nav-item-row-rack').forEach(row => {
        const rid = row.getAttribute('data-rack-id');
        if (warehouseId === 'OSIP') {
            if (rid === 'all' || rid === 'OS01' || rid === 'OS01-77' || rid === 'OSIP') {
                row.style.display = 'flex';
            } else {
                row.style.display = 'none';
            }
        } else {
            if (rid === 'OS01' || rid === 'OS01-77' || rid === 'OSIP') {
                row.style.display = 'none';
            } else {
                row.style.display = 'flex';
            }
        }
    });

    const isOsipRack = (currentSubWarehouseId === 'OS01' || currentSubWarehouseId === 'OS01-77' || currentSubWarehouseId === 'OSIP');
    const isStandardRack = (!isOsipRack && currentSubWarehouseId !== 'all');

    // Sprawdź czy bieżący regał jest kompatybilny z nowym magazynem
    if (!keepCurrentSubtab || (warehouseId === 'OSIP' && isStandardRack) || (warehouseId !== 'OSIP' && isOsipRack)) {
        currentSubWarehouseId = 'all';
        localStorage.setItem('warehouse_subtab', 'all');
        const allRackInput = document.getElementById('rack-all');
        if (allRackInput) {
            allRackInput.checked = true;
            if (typeof updateRackLabel === 'function') {
                updateRackLabel('Wszystkie Lokalizacje');
            }
        }
    } else {
        // Zachowaj wybrany regał
        localStorage.setItem('warehouse_subtab', currentSubWarehouseId);
        const activeRackInput = document.getElementById('rack-' + currentSubWarehouseId);
        if (activeRackInput) {
            activeRackInput.checked = true;
            const labelEl = document.querySelector(`label[for="${activeRackInput.id}"] .item-name`);
            if (labelEl && typeof updateRackLabel === 'function') {
                updateRackLabel(labelEl.innerText);
            }
        }
    }

    // 1. Paski pojemności (Przełączanie widoczności)
    document.querySelectorAll('.capacity-bar').forEach(b => b.style.display = 'none');
    
    let targetCapId = (currentSubWarehouseId !== 'all') ? currentSubWarehouseId : warehouseId;
    let capBar = document.getElementById('cap-' + targetCapId) || 
                 document.getElementById('cap-' + targetCapId.toUpperCase()) ||
                 document.getElementById('cap-' + targetCapId.toLowerCase()) ||
                 document.getElementById('cap-' + warehouseId);
                 
    if (capBar) {
        capBar.style.display = 'block';
    }
    
    // 2. Filtruj tabelę lokalnie
    if (typeof filterTable === 'function') {
        filterTable();
    }
}

function switchSubWarehouse(subId, element) {
    console.log("Przełączanie regału na:", subId);
    currentSubWarehouseId = subId;
    localStorage.setItem('warehouse_subtab', subId);
    
    // 1. Paski pojemności (Przełączanie widoczności dla regału)
    document.querySelectorAll('.capacity-bar').forEach(b => b.style.display = 'none');
    
    let targetId = subId;
    if (subId === 'all' || !subId) {
        targetId = currentWarehouseId;
    }
    
    let capBar = document.getElementById('cap-' + targetId) || 
                 document.getElementById('cap-' + targetId.toUpperCase()) ||
                 document.getElementById('cap-' + targetId.toLowerCase());
                 
    if (capBar) {
        capBar.style.display = 'block';
    } else {
        // Fallback do głównego magazynu jeśli nie ma paska dla regału
        let mainBar = document.getElementById('cap-' + currentWarehouseId);
        if (mainBar) mainBar.style.display = 'block';
    }
    
    // 2. Filtruj tabelę lokalnie
    filterTable();
}

function normalizeLocationCode(value) {
    return String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

function parseLocationCode(value) {
    const normalized = normalizeLocationCode(value);
    if (!/^R\d{6}$/.test(normalized)) {
        return null;
    }

    const rack = normalized.substring(0, 3);
    const place = normalized.substring(3, 5);
    const row = normalized.substring(5, 7);
    return {
        normalized,
        rack,
        place,
        row,
        rackNo: parseInt(rack.substring(1), 10),
        placeNo: parseInt(place, 10),
        rowNo: parseInt(row, 10),
    };
}

function parseLocationFilter(filterText) {
    const normalized = normalizeLocationCode(filterText);
    if (!normalized) return null;

    if (/^R\d{6}$/.test(normalized)) {
        return {
            type: 'full',
            rack: normalized.substring(0, 3),
            place: normalized.substring(3, 5),
            row: normalized.substring(5, 7),
        };
    }
    if (/^R\d{4}$/.test(normalized)) {
        return {
            type: 'rackPlace',
            rack: normalized.substring(0, 3),
            place: normalized.substring(3, 5),
        };
    }
    if (/^R\d{2}$/.test(normalized)) {
        return {
            type: 'rack',
            rack: normalized,
        };
    }
    if (/^\d{4}$/.test(normalized)) {
        return {
            type: 'placeRow',
            place: normalized.substring(0, 2),
            row: normalized.substring(2, 4),
        };
    }
    if (/^\d{2}$/.test(normalized)) {
        return {
            type: 'singleSegment',
            value: normalized,
        };
    }
    return null;
}

function matchesLocationSlots(locText, filterText) {
    const locParts = parseLocationCode(locText);
    if (!locParts) return false;

    const parsedFilter = parseLocationFilter(filterText);
    if (!parsedFilter) return false;

    if (parsedFilter.type === 'full') {
        return (
            locParts.rack === parsedFilter.rack &&
            locParts.place === parsedFilter.place &&
            locParts.row === parsedFilter.row
        );
    }
    if (parsedFilter.type === 'rackPlace') {
        return locParts.rack === parsedFilter.rack && locParts.place === parsedFilter.place;
    }
    if (parsedFilter.type === 'rack') {
        return locParts.rack === parsedFilter.rack;
    }
    if (parsedFilter.type === 'placeRow') {
        return locParts.place === parsedFilter.place && locParts.row === parsedFilter.row;
    }
    if (parsedFilter.type === 'singleSegment') {
        return locParts.place === parsedFilter.value || locParts.row === parsedFilter.value;
    }
    return false;
}



