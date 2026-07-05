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
        return isMatch(allText, item.location || '', filter);
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

