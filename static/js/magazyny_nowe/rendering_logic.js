let selectedLocations = []; // To store selected locations from multiselect

function populateLocationFilter() {
    const checkboxesContainer = document.getElementById('locationCheckboxes');
    if (!checkboxesContainer) return;
    
    // Get unique location prefixes (racks)
    const uniqueLocationsSet = new Set();
    allWarehouseItems.forEach(item => {
        let loc = (item.location || '').toUpperCase().trim();
        if (loc.length === 0) return;
        
        if (/^R\d{2}/.test(loc)) {
            uniqueLocationsSet.add(loc.substring(0, 3));
        } else {
            uniqueLocationsSet.add(loc);
        }
    });
    
    const uniqueLocations = [...uniqueLocationsSet].sort((a, b) => a.localeCompare(b));
    
    let html = '';
    uniqueLocations.forEach(loc => {
        const isChecked = selectedLocations.length === 0 || selectedLocations.includes(loc) ? 'checked' : '';
        html += `
            <label style="display: flex; align-items: center; gap: 8px; padding: 4px 8px; cursor: pointer; border-radius: 6px; hover:background-color: #f1f5f9;">
                <input type="checkbox" value="${loc}" class="loc-checkbox" onchange="updateSelectedLocations()" ${isChecked}>
                <span style="font-size: 13px; font-weight: 500;">${loc}</span>
            </label>
        `;
    });
    checkboxesContainer.innerHTML = html;
    if (selectedLocations.length === 0) {
        selectedLocations = [...uniqueLocations];
    }
}

function updateSelectedLocations() {
    const checkboxes = document.querySelectorAll('.loc-checkbox');
    selectedLocations = Array.from(checkboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value);
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
    currentFilteredItems = allWarehouseItems.filter(item => {
        let allText = `${item.displayId} ${item.productName} ${item.amount} ${item.type} ${item.date_prod} ${item.date_exp} ${item.location}`.toUpperCase();
        return isMatch(allText, item.location || '', filter, selectedLocations);
    });

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
    _updateFilterBanner(filter, currentFilteredItems.length, allWarehouseItems.length);
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

