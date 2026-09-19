// ---- WAREHOUSE FILTERING & TABS ----
function switchWarehouse(warehouseId, keepCurrentSubtab = false) {
    console.log("Przełączanie magazynu na:", warehouseId, "keepCurrentSubtab:", keepCurrentSubtab);
    
    currentWarehouseId = warehouseId;
    localStorage.setItem('warehouse_tab', warehouseId);
    
    // Dynamiczne ukrywanie/pokazywanie opcji w menu regałów
    document.querySelectorAll('.nav-item-row-rack').forEach(row => {
        const rid = row.getAttribute('data-rack-id');
        if (warehouseId === 'OSIP') {
            if (rid === 'all' || rid === 'OS01' || rid === 'OS01-77' || rid === 'A01-A99' || rid === 'BFOS' || rid === 'OSIP') {
                row.style.display = 'flex';
            } else {
                row.style.display = 'none';
            }
        } else {
            if (rid === 'OS01' || rid === 'OS01-77' || rid === 'A01-A99' || rid === 'BFOS' || rid === 'OSIP') {
                row.style.display = 'none';
            } else {
                row.style.display = 'flex';
            }
        }
    });

    const isOsipRack = (currentSubWarehouseId === 'OS01' || currentSubWarehouseId === 'OS01-77' || currentSubWarehouseId === 'A01-A99' || currentSubWarehouseId === 'BFOS' || currentSubWarehouseId === 'OSIP');
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

// ---- DYNAMIC BLOCKED REASONS FILTER (POGŁĘBIONA FILTRACJA POWODÓW BLOKADY) ----
function getItemBlockReason(item) {
    if (!item) return null;
    
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    if (item.date_exp && item.date_exp !== '-' && item.date_exp !== 'brak') {
        const expDate = new Date(item.date_exp);
        if (!isNaN(expDate.getTime()) && expDate.getTime() < today.getTime()) {
            return "Przeterminowanie (Data ważności)";
        }
    }

    if (item.block_reason && String(item.block_reason).trim() !== '') {
        return String(item.block_reason).trim();
    }

    if (item.is_blocked || item.is_system_blocked) {
        return "Blokada manualna (Magazyn / Jakość)";
    }

    return null;
}

function populateBlockedFilter() {
    const checkboxesContainer = document.getElementById('blockedReasonCheckboxes');
    if (!checkboxesContainer || typeof allWarehouseItems === 'undefined' || !Array.isArray(allWarehouseItems)) return;

    // Zbierz wszystkie powody i zlicz ich wystąpienia
    const reasonCounts = {};
    allWarehouseItems.forEach(item => {
        const reason = getItemBlockReason(item);
        if (reason) {
            reasonCounts[reason] = (reasonCounts[reason] || 0) + 1;
        }
    });

    const uniqueReasons = Object.keys(reasonCounts).sort((a, b) => a.localeCompare(b));
    const totalBlocked = Object.values(reasonCounts).reduce((a, b) => a + b, 0);

    const badge = document.getElementById('headerBlockedCountBadge');
    if (badge) {
        badge.textContent = String(totalBlocked);
        badge.style.display = totalBlocked > 0 ? 'inline-block' : 'none';
    }

    if (uniqueReasons.length === 0) {
        checkboxesContainer.innerHTML = `
            <div style="text-align: center; padding: 16px 8px; color: #94a3b8; font-size: 13px;">
                <span class="material-icons" style="font-size: 28px; color: #10b981; display: block; margin-bottom: 4px;">check_circle</span>
                Brak zablokowanych palet w magazynie
            </div>`;
        updateBlockedDropdownLabel();
        return;
    }

    let html = '';
    uniqueReasons.forEach(reason => {
        const count = reasonCounts[reason] || 0;
        const isChecked = selectedBlockedReasons.includes(reason) ? 'checked' : '';
        const isExpiredType = reason.toLowerCase().includes('przetermin');
        const icon = isExpiredType ? 'history_toggle_off' : 'lock';
        const iconColor = isExpiredType ? '#ea580c' : '#dc2626';

        html += `
            <label style="display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 8px; cursor: pointer; border-radius: 8px; transition: background 0.15s ease;">
                <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
                    <input type="checkbox" value="${reason.replace(/"/g, '&quot;')}" class="blocked-reason-checkbox" onchange="updateSelectedBlockedReasons()" ${isChecked} style="accent-color: #dc2626; width: 16px; height: 16px;">
                    <span class="material-icons" style="font-size: 16px; color: ${iconColor}; flex-shrink: 0;">${icon}</span>
                    <span style="font-size: 13px; font-weight: 600; color: #1e293b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${reason}</span>
                </div>
                <span style="font-size: 11px; font-weight: 800; background: #fee2e2; color: #991b1b; padding: 1px 7px; border-radius: 9999px; flex-shrink: 0;">${count}</span>
            </label>
        `;
    });

    checkboxesContainer.innerHTML = html;
    updateBlockedDropdownLabel();
}

function updateSelectedBlockedReasons() {
    const checkboxes = document.querySelectorAll('.blocked-reason-checkbox');
    selectedBlockedReasons = Array.from(checkboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value);

    updateBlockedDropdownLabel();
    if (typeof filterTable === 'function') {
        filterTable({ preserveScroll: true });
    }
}

function selectAllBlockedReasons(select) {
    const checkboxes = document.querySelectorAll('.blocked-reason-checkbox');
    checkboxes.forEach(cb => cb.checked = select);
    updateSelectedBlockedReasons();
}

function updateBlockedDropdownLabel() {
    const labelEl = document.getElementById('blockedDropdownLabel');
    const btn = document.getElementById('blockedDropdownBtn');
    if (!labelEl) return;

    const count = Array.isArray(selectedBlockedReasons) ? selectedBlockedReasons.length : 0;
    const checkboxes = document.querySelectorAll('.blocked-reason-checkbox');
    const totalReasons = checkboxes.length;

    if (count === 0) {
        labelEl.textContent = 'Zablokowane';
        if (btn) btn.classList.remove('active');
    } else if (count === totalReasons && totalReasons > 0) {
        labelEl.textContent = 'Wszystkie Zablokowane';
        if (btn) btn.classList.add('active');
    } else {
        labelEl.textContent = `Zablokowane (${count}/${totalReasons})`;
        if (btn) btn.classList.add('active');
    }
}

function toggleBlockedDropdown() {
    const menu = document.getElementById('blockedDropdownMenu');
    if (!menu) return;
    const isHidden = (menu.style.display === 'none' || menu.style.display === '');
    
    // Zamknij inne menu
    const locMenu = document.getElementById('locationDropdownMenu');
    if (locMenu) locMenu.style.display = 'none';

    menu.style.display = isHidden ? 'block' : 'none';
}

function updateBlockedBadgeCount() {
    populateBlockedFilter();
}
