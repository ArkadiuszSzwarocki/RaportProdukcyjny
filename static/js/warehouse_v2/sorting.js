// ---- SORTING LOGIC ----
function sortTable(n) {
    const table = document.getElementById("magazynyTable");
    if (!table) return;
    
    let dir = 'asc';
    if (currentSortCol === n) {
        dir = (currentSortDir === 'asc') ? 'desc' : 'asc';
    } else {
        dir = 'asc';
    }

    currentSortCol = n;
    currentSortDir = dir;
    localStorage.setItem('warehouse_sort_col', String(n));
    localStorage.setItem('warehouse_sort_dir', dir);

    updateSortHeaderIndicators();

    if (typeof filterTable === 'function') {
        filterTable();
    }
}

function updateSortHeaderIndicators() {
    const table = document.getElementById("magazynyTable");
    if (!table) return;
    const ths = table.querySelectorAll("thead th");
    ths.forEach(t => t.removeAttribute("data-dir"));
    if (currentSortCol !== null && ths[currentSortCol]) {
        ths[currentSortCol].setAttribute("data-dir", currentSortDir);
    }
}

function sortWarehouseItems(items, colIndex, dir) {
    if (!Array.isArray(items) || items.length <= 1 || colIndex === null) return items;

    const isAsc = (dir === 'asc');

    return items.sort((a, b) => {
        if (colIndex === 1) { // ID Palety
            const idA = String(a.displayId || a.id || '').toUpperCase();
            const idB = String(b.displayId || b.id || '').toUpperCase();
            return isAsc ? idA.localeCompare(idB) : idB.localeCompare(idA);
        }

        if (colIndex === 2) { // Produkt
            const nameA = String(a.productName || '').toUpperCase();
            const nameB = String(b.productName || '').toUpperCase();
            return isAsc ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA);
        }

        if (colIndex === 3) { // Ilość
            const numA = parseFloat(a.amount) || 0;
            const numB = parseFloat(b.amount) || 0;
            return isAsc ? numA - numB : numB - numA;
        }

        if (colIndex === 4) { // Lokalizacja
            const locA = (typeof parseLocationCode === 'function') ? parseLocationCode(a.location) : null;
            const locB = (typeof parseLocationCode === 'function') ? parseLocationCode(b.location) : null;

            if (locA && locB) {
                if (locA.rackNo !== locB.rackNo) {
                    return isAsc ? locA.rackNo - locB.rackNo : locB.rackNo - locA.rackNo;
                }
                if (locA.rowNo !== locB.rowNo) {
                    return isAsc ? locA.rowNo - locB.rowNo : locB.rowNo - locA.rowNo;
                }
                if (locA.placeNo !== locB.placeNo) {
                    return isAsc ? locA.placeNo - locB.placeNo : locB.placeNo - locA.placeNo;
                }
            } else if (locA && !locB) {
                return isAsc ? -1 : 1;
            } else if (!locA && locB) {
                return isAsc ? 1 : -1;
            }
            const strA = String(a.location || '').toUpperCase();
            const strB = String(b.location || '').toUpperCase();
            return isAsc ? strA.localeCompare(strB) : strB.localeCompare(strA);
        }

        if (colIndex === 5) { // Typ
            const typA = String(a.type || '').toUpperCase();
            const typB = String(b.type || '').toUpperCase();
            return isAsc ? typA.localeCompare(typB) : typB.localeCompare(typA);
        }

        if (colIndex === 6) { // Produkcja
            const dateA = String(a.date_prod || '');
            const dateB = String(b.date_prod || '');
            return isAsc ? dateA.localeCompare(dateB) : dateB.localeCompare(dateA);
        }

        if (colIndex === 7) { // Ważność
            const expA = (a.date_exp && a.date_exp !== '-') ? a.date_exp : '9999-99-99';
            const expB = (b.date_exp && b.date_exp !== '-') ? b.date_exp : '9999-99-99';
            return isAsc ? expA.localeCompare(expB) : expB.localeCompare(expA);
        }

        return 0;
    });
}


