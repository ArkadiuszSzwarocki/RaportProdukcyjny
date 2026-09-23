function populateLocationFilter() {
    const checkboxesContainer = document.getElementById('locationCheckboxes');
    if (!checkboxesContainer) return;
    
    // Get unique location prefixes (racks)
    const uniqueLocationsSet = new Set();
    allWarehouseItems.forEach(item => {
        let loc = (item.location || '').toUpperCase().trim();
        if (loc.length === 0) return;
        
        if (typeof currentWarehouseId !== 'undefined' && currentWarehouseId === 'OSIP') {
            const isOsip = loc.includes('OSIP') || loc.startsWith('OS') || loc.startsWith('A') || loc === 'BFOS';
            if (!isOsip) return;
        }
        
        if (/^R\d{2}/.test(loc)) {
            uniqueLocationsSet.add(loc.substring(0, 3));
        } else {
            uniqueLocationsSet.add(loc);
        }
    });
    
    if (typeof currentWarehouseId !== 'undefined' && currentWarehouseId === 'OSIP') {
        for (let i = 1; i <= 99; i++) {
            uniqueLocationsSet.add(`A${String(i).padStart(2, '0')}`);
        }
        uniqueLocationsSet.add('BFOS');
    }
    
    const uniqueLocations = [...uniqueLocationsSet].sort((a, b) => a.localeCompare(b));
    
    // Read saved locations from localStorage
    const savedLocs = localStorage.getItem('warehouse_locations');
    if (savedLocs !== null) {
        try {
            const parsed = JSON.parse(savedLocs);
            if (Array.isArray(parsed)) {
                selectedLocations = parsed;
            } else {
                selectedLocations = [...uniqueLocations];
            }
        } catch (e) {
            console.warn("Error parsing warehouse_locations from localStorage:", e);
            selectedLocations = [...uniqueLocations];
        }
    } else {
        selectedLocations = [...uniqueLocations];
    }
    
    let html = '';
    uniqueLocations.forEach(loc => {
        const isChecked = selectedLocations.includes(loc) ? 'checked' : '';
        html += `
            <label style="display: flex; align-items: center; gap: 8px; padding: 4px 8px; cursor: pointer; border-radius: 6px; hover:background-color: #f1f5f9;">
                <input type="checkbox" value="${loc}" class="loc-checkbox" onchange="updateSelectedLocations()" ${isChecked}>
                <span style="font-size: 13px; font-weight: 500;">${loc}</span>
            </label>
        `;
    });
    checkboxesContainer.innerHTML = html;
    updateLocationDropdownLabel(uniqueLocations.length);
}

function updateLocationDropdownLabel(totalUnique) {
    const labelEl = document.getElementById('locationDropdownLabel');
    if (!labelEl) return;
    
    const checkboxes = document.querySelectorAll('.loc-checkbox');
    const total = (typeof totalUnique === 'number' && totalUnique > 0) ? totalUnique : checkboxes.length;
    const count = Array.isArray(selectedLocations) ? selectedLocations.length : 0;
    
    if (total === 0) {
        labelEl.textContent = 'Filtruj Lokacje';
    } else if (count === total) {
        labelEl.textContent = 'Wszystkie Lokacje';
    } else if (count === 0) {
        labelEl.textContent = 'Brak Lokacji (0)';
    } else {
        labelEl.textContent = `Lokacje (${count}/${total})`;
    }
}

function updateSelectedLocations() {
    const checkboxes = document.querySelectorAll('.loc-checkbox');
    selectedLocations = Array.from(checkboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value);
    
    localStorage.setItem('warehouse_locations', JSON.stringify(selectedLocations));
    updateLocationDropdownLabel(checkboxes.length);
    filterTable();
}

function selectAllLocations(select) {
    const checkboxes = document.querySelectorAll('.loc-checkbox');
    checkboxes.forEach(cb => cb.checked = select);
    updateSelectedLocations();
}

function filterTable(options = {}) {
    const preserveScroll = (options && options.preserveScroll !== undefined) ? options.preserveScroll : true;
    
    // Zapisz aktualną pozycję scrolla przed manipulacją DOM
    const savedWindowScrollY = window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0;
    const container = document.getElementById('warehouseItemsContainer');
    if (!container) return;
    const listWrapper = container.querySelector('.list-view-wrapper');
    const savedWrapperScrollTop = listWrapper ? listWrapper.scrollTop : 0;

    const input = document.getElementById("searchInput");
    const filter = input ? input.value.toUpperCase().trim() : "";
    
    // Zapisz aktualną wartość wyszukiwania do localStorage (persist po reload)
    if (input) {
        localStorage.setItem('warehouse_search', input.value);
    }

    syncStateFromDOM();

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const isItemExpired = (item) => {
        if (!item.date_exp || item.date_exp === '-' || item.date_exp === 'brak') return false;
        const expDate = new Date(item.date_exp);
        return !isNaN(expDate.getTime()) && expDate.getTime() < today.getTime();
    };

    // Oznacz palety przeterminowane jako zablokowane systemowo
    allWarehouseItems.forEach(item => {
        if (isItemExpired(item)) {
            item.is_blocked = 1;
            item.is_system_blocked = true;
        }
    });

    // 1. Filtruj tablicę JavaScript
    let filtered = allWarehouseItems.filter(item => {
        // Pogłębiona filtracja po powodach zablokowania
        if (typeof selectedBlockedReasons !== 'undefined' && Array.isArray(selectedBlockedReasons) && selectedBlockedReasons.length > 0) {
            const reason = (typeof getItemBlockReason === 'function') ? getItemBlockReason(item) : null;
            if (!reason || !selectedBlockedReasons.includes(reason)) {
                return false;
            }
        } else if (typeof filterOnlyBlocked !== 'undefined' && filterOnlyBlocked) {
            const isBlocked = Boolean(item.is_blocked) || Boolean(item.is_system_blocked) || isItemExpired(item);
            if (!isBlocked) return false;
        }
        let allText = `${item.displayId} ${item.productName} ${item.amount} ${item.type} ${item.date_prod} ${item.date_exp} ${item.location} ${item.order_doc_label || ''} ${item.order_ref || ''} ${item.order_source || ''}`.toUpperCase();
        return isMatch(allText, item.location || '', filter, selectedLocations, item);
    });

    // 1b. Oblicz kolejność FIFO per produkt
    const productGroups = {};
    filtered.forEach(item => {
        const pKey = String(item.productName || '').trim().toLowerCase();
        if (!productGroups[pKey]) productGroups[pKey] = [];
        productGroups[pKey].push(item);
    });

    const getBatchDateKey = (item) => {
        const exp = (item.date_exp && item.date_exp !== '-') ? item.date_exp : '9999-99-99';
        const prod = (item.date_prod && item.date_prod !== '-') ? item.date_prod : '9999-99-99';
        return `${exp}_${prod}`;
    };

    const fifoKey = (item) => {
        const batchKey = getBatchDateKey(item);
        const added = (item.date_added && item.date_added !== '-') ? item.date_added : '9999-99-99';
        const id = parseInt(item.id || 0) || 0;
        return `${batchKey}_${added}_${String(id).padStart(10, '0')}`;
    };

    const fifoList = [];
    Object.keys(productGroups).forEach(pKey => {
        const group = productGroups[pKey];
        group.sort((a, b) => fifoKey(a).localeCompare(fifoKey(b)));
        const total = group.length;

        // Only valid, non-expired, non-blocked pallets are eligible for FIFO release
        const validGroup = group.filter(x => !x.is_blocked && !isItemExpired(x));
        const earliestValidBatchKey = validGroup.length > 0 ? getBatchDateKey(validGroup[0]) : null;
        const hasMultipleBatches = validGroup.some(x => getBatchDateKey(x) !== earliestValidBatchKey);

        const uniqueBatches = [];
        group.forEach(item => {
            const bKey = getBatchDateKey(item);
            if (!uniqueBatches.includes(bKey)) uniqueBatches.push(bKey);
        });

        group.forEach((item, idx) => {
            const bKey = getBatchDateKey(item);
            const batchNum = uniqueBatches.indexOf(bKey) + 1;
            const isEligible = !item.is_blocked && !isItemExpired(item);
            const isEarliestBatch = Boolean(isEligible && earliestValidBatchKey && (bKey === earliestValidBatchKey));

            item.fifo_index = idx + 1;
            item.fifo_batch_num = batchNum;
            item.fifo_total = total;
            // Mark as 1st FIFO only if the pallet is eligible (not expired, not blocked)
            item.is_first_fifo = Boolean(isEarliestBatch && (hasMultipleBatches || validGroup.length > 1));
        });
        fifoList.push(...group);
    });

    // Zastosuj sortowanie lub domyślny porządek FIFO
    if (typeof currentSortCol !== 'undefined' && currentSortCol !== null && typeof sortWarehouseItems === 'function') {
        currentFilteredItems = sortWarehouseItems(fifoList, currentSortCol, currentSortDir);
    } else if (filter) {
        fifoList.sort((a, b) => {
            const nameCmp = String(a.productName || '').localeCompare(String(b.productName || ''));
            if (nameCmp !== 0) return nameCmp;
            return (a.fifo_index || 999) - (b.fifo_index || 999);
        });
        currentFilteredItems = fifoList;
    } else {
        currentFilteredItems = fifoList;
    }

    // 2. Zachowaj dotychczasową liczbę wyrenderowanych elementów, by nie ucinać widoku
    const targetRenderCount = preserveScroll ? Math.max(currentRenderedCount || 0, PAGE_SIZE) : PAGE_SIZE;
    currentRenderedCount = 0;
    
    const tbody = container.querySelector(".list-view-wrapper tbody");
    const grid = document.getElementById('palletGridContainer');
    if (tbody) {
        tbody.innerHTML = '';
        tbody.style.opacity = '0';
    }
    if (grid) {
        grid.innerHTML = '';
        grid.style.opacity = '0';
    }

    // 3. Render items
    loadItemsBatch(targetRenderCount);

    // 4. Aktualizuj banner statusu filtra oraz licznik zablokowanych
    if (typeof _updateFilterBanner === 'function') {
        _updateFilterBanner(filter, currentFilteredItems.length, allWarehouseItems.length);
    }
    if (typeof updateBlockedBadgeCount === 'function') {
        updateBlockedBadgeCount();
    }

    // 5. Odtwórz pozycję scrolla
    if (preserveScroll && savedWindowScrollY > 0) {
        window.scrollTo({ top: savedWindowScrollY, behavior: 'instant' });
        if (listWrapper && savedWrapperScrollTop > 0) {
            listWrapper.scrollTop = savedWrapperScrollTop;
        }
        requestAnimationFrame(() => {
            window.scrollTo({ top: savedWindowScrollY, behavior: 'instant' });
            if (listWrapper && savedWrapperScrollTop > 0) {
                listWrapper.scrollTop = savedWrapperScrollTop;
            }
        });
        setTimeout(() => {
            window.scrollTo({ top: savedWindowScrollY, behavior: 'instant' });
            if (listWrapper && savedWrapperScrollTop > 0) {
                listWrapper.scrollTop = savedWrapperScrollTop;
            }
        }, 50);
    }
}

function loadMoreItems() {
    loadItemsBatch(PAGE_SIZE);
}

function loadItemsBatch(batchSize) {
    const tbody = document.querySelector(".list-view-wrapper tbody");
    const grid = document.getElementById('palletGridContainer');
    if (!tbody || !grid) return;

    if (currentFilteredItems.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding: 48px 16px; color: #64748b;">
            <span class="material-icons" style="font-size: 44px; color: #94a3b8; display: block; margin-bottom: 8px;">filter_alt_off</span>
            <div style="font-size: 15px; font-weight: 700; color: #334155; margin-bottom: 4px;">Brak palet dla wybranych lokalizacji / filtrów</div>
            <div style="font-size: 13px; color: #64748b;">Zmień kryteria wyszukiwania lub filtry blokad/lokalizacji, aby wyświetlić pozycje.</div>
        </td></tr>`;
        grid.innerHTML = `<div style="grid-column: 1 / -1; text-align:center; padding: 48px 16px; color: #64748b;">
            <span class="material-icons" style="font-size: 44px; color: #94a3b8; display: block; margin-bottom: 8px;">filter_alt_off</span>
            <div style="font-size: 15px; font-weight: 700; color: #334155; margin-bottom: 4px;">Brak palet dla wybranych lokalizacji / filtrów</div>
            <div style="font-size: 13px; color: #64748b;">Zmień kryteria wyszukiwania lub filtry blokad/lokalizacji, aby wyświetlić pozycje.</div>
        </div>`;
        const loadMoreContainer = document.getElementById('loadMoreContainer');
        if (loadMoreContainer) {
            loadMoreContainer.style.display = 'none';
        }
        requestAnimationFrame(() => {
            tbody.style.opacity = '1';
            grid.style.opacity = '1';
        });
        return;
    }

    const start = currentRenderedCount;
    const end = Math.min(start + (batchSize || PAGE_SIZE), currentFilteredItems.length);
    
    let tableHtml = '';
    let gridHtml = '';
    
    for (let i = start; i < end; i++) {
        const item = currentFilteredItems[i];
        tableHtml += generateTableRow(item, i + 1);
        gridHtml += generateGridCard(item);
    }
    
    tbody.insertAdjacentHTML('beforeend', tableHtml);
    grid.insertAdjacentHTML('beforeend', gridHtml);
    
    currentRenderedCount = end;
    
    const loadMoreContainer = document.getElementById('loadMoreContainer');
    if (loadMoreContainer) {
        loadMoreContainer.style.display = (currentRenderedCount < currentFilteredItems.length) ? 'block' : 'none';
    }
    
    requestAnimationFrame(() => {
        tbody.style.opacity = '1';
        grid.style.opacity = '1';
    });
}

function formatLocation(loc) {
    let loc_code = (loc || '').toUpperCase();
    if (loc_code.length >= 7 && loc_code.startsWith('R')) {
        return `<span class="location-code">
                    <span class="location-part-rack">${loc_code.substring(0,3)}</span>
                    <span class="location-separator"> </span>
                    <span class="location-part-place">${loc_code.substring(3,5)}</span>
                    <span class="location-separator"> </span>
                    <span class="location-part-row">${loc_code.substring(5,7)}</span>
                </span>`;
    }
    if (loc_code.startsWith('OCZEKUJ')) {
        return `<span style="background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 6px; display: inline-flex; align-items: center; gap: 3px;">
                    <span class="material-icons" style="font-size: 13px; color: #3b82f6;">hourglass_top</span> ${loc}
                </span>`;
    }
    return loc || 'Brak';
}

