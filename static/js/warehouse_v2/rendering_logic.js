function populateLocationFilter() {
    const checkboxesContainer = document.getElementById('locationCheckboxes');
    if (!checkboxesContainer) return;
    
    // Get unique location prefixes (racks)
    const uniqueLocationsSet = new Set();
    allWarehouseItems.forEach(item => {
        let loc = (item.location || '').toUpperCase().trim();
        if (loc.length === 0) return;
        
        if (typeof currentWarehouseId !== 'undefined' && currentWarehouseId === 'OSIP') {
            const isOsip = loc.includes('OSIP') || loc.startsWith('OS');
            if (!isOsip) return;
        }
        
        if (/^R\d{2}/.test(loc)) {
            uniqueLocationsSet.add(loc.substring(0, 3));
        } else {
            uniqueLocationsSet.add(loc);
        }
    });
    
    const uniqueLocations = [...uniqueLocationsSet].sort((a, b) => a.localeCompare(b));
    
    // Odczytaj zapisane lokalizacje z localStorage
    const savedLocs = localStorage.getItem('warehouse_locations');
    if (savedLocs) {
        try {
            const parsed = JSON.parse(savedLocs);
            if (Array.isArray(parsed)) {
                selectedLocations = parsed;
            }
        } catch (e) {
            console.warn("Błąd parsowania warehouse_locations z localStorage:", e);
        }
    }
    
    if (!selectedLocations || selectedLocations.length === 0) {
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
    
    const total = totalUnique || document.querySelectorAll('.loc-checkbox').length;
    if (selectedLocations.length === total || total === 0) {
        labelEl.textContent = 'Filtruj Lokacje';
    } else if (selectedLocations.length === 0) {
        labelEl.textContent = 'Żadna Lokacja (0)';
    } else {
        labelEl.textContent = `Lokacje (${selectedLocations.length}/${total})`;
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

function filterTable() {
    const input = document.getElementById("searchInput");
    const filter = input ? input.value.toUpperCase().trim() : "";
    
    // Zapisz aktualną wartość wyszukiwania do localStorage (persist po reload)
    if (input) {
        localStorage.setItem('warehouse_search', input.value);
    }
    const container = document.getElementById('warehouseItemsContainer');
    if (!container) return;

    syncStateFromDOM();

    // 1. Filter JavaScript Array instead of DOM
    let filtered = allWarehouseItems.filter(item => {
        let allText = `${item.displayId} ${item.productName} ${item.amount} ${item.type} ${item.date_prod} ${item.date_exp} ${item.location}`.toUpperCase();
        return isMatch(allText, item.location || '', filter, selectedLocations);
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

        // Znajdź najwcześniejszą datę partii w grupie
        const earliestBatchKey = total > 0 ? getBatchDateKey(group[0]) : '';
        const hasMultipleBatches = group.some(x => getBatchDateKey(x) !== earliestBatchKey);

        const uniqueBatches = [];
        group.forEach(item => {
            const bKey = getBatchDateKey(item);
            if (!uniqueBatches.includes(bKey)) uniqueBatches.push(bKey);
        });

        group.forEach((item, idx) => {
            const bKey = getBatchDateKey(item);
            const batchNum = uniqueBatches.indexOf(bKey) + 1;
            const isEarliestBatch = (bKey === earliestBatchKey);

            item.fifo_index = idx + 1;
            item.fifo_batch_num = batchNum;
            item.fifo_total = total;
            // Zaznacz wszystkie palety posiadające najwcześniejszą datę ważności/produkcji
            item.is_first_fifo = isEarliestBatch && (hasMultipleBatches || total > 1);
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

    // 2. Reset Pagination
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

    // 3. Render first batch
    loadMoreItems();

    // 4. Aktualizuj banner statusu filtra
    if (typeof _updateFilterBanner === 'function') {
        _updateFilterBanner(filter, currentFilteredItems.length, allWarehouseItems.length);
    }
}

function loadMoreItems() {
    const tbody = document.querySelector(".list-view-wrapper tbody");
    const grid = document.getElementById('palletGridContainer');
    if (!tbody || !grid) return;

    const start = currentRenderedCount;
    const end = Math.min(start + PAGE_SIZE, currentFilteredItems.length);
    
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
    return loc || 'Brak';
}

