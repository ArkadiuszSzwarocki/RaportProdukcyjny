/**
 * Magazyny Nowe - Logika Interfejsu
 * Obsługuje filtrowanie, sortowanie, modale i operacje na paletach.
 */

// ---- STATE MANAGEMENT ----
let currentWarehouseId = 'all';
let currentSubWarehouseId = 'all';
let currentSearchQuery = '';
let currentPallet = {}; 
let scanBuffer = '';
let scanTimeout = null;

// Funkcja synchronizująca stan z widokiem (DOM)
function syncStateFromDOM() {
    const checkedWh = document.querySelector('input[name="main_wh"]:checked');
    if (checkedWh) {
        currentWarehouseId = checkedWh.id.replace('radio-', '');
    }
    
    const checkedRack = document.querySelector('input[name="rack_select"]:checked');
    if (checkedRack) {
        currentSubWarehouseId = checkedRack.id.replace('rack-', '');
    }
    
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        currentSearchQuery = searchInput.value;
    }
    
    console.log("Zsynchronizowano stan z DOM:", { warehouse: currentWarehouseId, sub: currentSubWarehouseId });
}

// ---- SCANNER HANDLER ----
document.addEventListener('keydown', function(e) {
    if(e.key === 'Enter' && scanBuffer.length > 3) {
        handleScan(scanBuffer);
        scanBuffer = '';
    } else {
        if(e.key.length === 1) scanBuffer += e.key;
        clearTimeout(scanTimeout);
        scanTimeout = setTimeout(() => { scanBuffer = ''; }, 200); 
    }
});

function handleScan(barcode) {
    alert("Zeskanowano kod: " + barcode + ". Tutaj wdrożymy logikę rozpoznawania po ID z biblioteki.");
}

// ---- PALLET MODAL ----
function openPalletModal(displayId, productName, amount, location, type, date, realId, linia, isBlocked, dateAdded) {
    currentPallet = { displayId, productName, amount, location, type, date, id: realId, linia: linia, is_blocked: isBlocked, date_added: dateAdded };
    
    document.getElementById('modalDisplayId').textContent = displayId;
    document.getElementById('modalProductName').textContent = productName;
    document.getElementById('modalAmount').textContent = amount;
    document.getElementById('modalLocation').textContent = location || 'Brak lokalizacji';
    document.getElementById('modalType').textContent = type;
    document.getElementById('modalDate').textContent = date || '-';
    
    const dateAddedEl = document.getElementById('modalDateAdded');
    if (dateAddedEl) {
        dateAddedEl.textContent = dateAdded || '-';
    }

    // Blocking status indicator in modal
    const blockBtn = document.getElementById('toggleBlockBtn');
    if (currentPallet.is_blocked) {
        blockBtn.innerHTML = '<span class="material-icons">lock_open</span> ODBLOKUJ PALETĘ';
        blockBtn.className = 'modal-btn-secondary';
        blockBtn.style.background = '#10b981';
        blockBtn.style.color = '#fff';
    } else {
        blockBtn.innerHTML = '<span class="material-icons">block</span> ZABLOKUJ PALETĘ';
        blockBtn.className = 'modal-btn-secondary';
        blockBtn.style.background = '#be123c';
        blockBtn.style.color = '#fff';
    }
    
    const returnBtn = document.getElementById('returnToRawBtn');
    if(type === 'Wyrób Gotowy') {
        returnBtn.style.display = 'flex';
    } else {
        returnBtn.style.display = 'none';
    }
    
    document.getElementById('modalHistoryContainer').style.display = 'none';
    document.getElementById('modalHistoryList').innerHTML = '';
    
    const modal = document.getElementById('palletModal');
    const content = document.getElementById('palletModalContent');
    
    modal.style.display = 'flex';
    setTimeout(() => {
        content.style.transform = 'scale(1)';
    }, 10);
}

function closePalletModal() {
    const modal = document.getElementById('palletModal');
    const content = document.getElementById('palletModalContent');
    
    content.style.transform = 'scale(0.95)';
    setTimeout(() => {
        modal.style.display = 'none';
        currentPallet = {};
    }, 200); 
}

// ---- PALLET OPERATIONS ----
function promptMoveLocation() {
    if(!currentPallet.id) return;
    let newLoc = prompt(`Wpisz nową lokalizację dla palety ${currentPallet.displayId} (np. MS01-A1, Stanowisko Big Bag):`, currentPallet.location);
    if(newLoc && newLoc !== currentPallet.location) {
        fetch('/magazyny-nowe/api/pallet/move', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                location: newLoc,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                alert("Przeniesiono pomyślnie.");
                window.location.reload();
            } else {
                alert("Błąd: " + data.error);
            }
        });
    }
}

function promptRename() {
    if(!currentPallet.id) return;
    let newName = prompt(`Zmień nazwę produktu dla palety ${currentPallet.displayId}:`, currentPallet.productName);
    if(newName && newName !== currentPallet.productName) {
        fetch('/magazyny-nowe/api/pallet/rename', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                name: newName,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                alert("Nazwa zaktualizowana.");
                window.location.reload();
            } else {
                alert("Błąd: " + data.error);
            }
        });
    }
}

function promptUpdateWeight() {
    if(!currentPallet.id) return;
    let newWeight = prompt(`Podaj nową wagę/ilość dla palety ${currentPallet.displayId}:`, currentPallet.amount);
    if(newWeight !== null && newWeight !== currentPallet.amount) {
        fetch('/magazyny-nowe/api/pallet/update-weight', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                weight: parseFloat(newWeight),
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                alert(data.message || "Waga zaktualizowana.");
                window.location.reload();
            } else {
                alert("Błąd: " + data.error);
            }
        });
    }
}

function promptDispatch() {
    if(!currentPallet.id) return;
    if(confirm(`Czy na pewno chcesz WYDAĆ paletę ${currentPallet.displayId}? Paleta zostanie przeniesiona do lokalizacji EXPEDITION i jej stan zostanie wyzerowany.`)) {
        fetch('/magazyny-nowe/api/pallet/dispatch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                alert("Wydano pomyślnie.");
                window.location.reload();
            } else {
                alert("Błąd: " + data.error);
            }
        });
    }
}

function promptArchive() {
    if(!currentPallet.id) return;
    if(confirm(`Czy na pewno chcesz zarchiwizować paletę ${currentPallet.displayId}? Ilość zostanie wyzerowana.`)) {
        fetch('/magazyny-nowe/api/pallet/archive', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                alert("Zarchiwizowano pomyślnie.");
                window.location.reload();
            } else {
                alert("Błąd: " + data.error);
            }
        });
    }
}

function promptReturnToRaw() {
    if(!currentPallet.id) return;
    if(confirm(`Czy na pewno chcesz zwrócić paletę ${currentPallet.displayId} (${currentPallet.productName}) jako SUROWIEC? Paleta zostanie wyzerowana w wyrobach gotowych i dodana do surowców na lokalizację OSIP.`)) {
        fetch('/magazyny-nowe/api/pallet/return-to-raw', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                alert(data.message || "Zwrócono pomyślnie.");
                window.location.reload();
            } else {
                alert("Błąd: " + data.error);
            }
        });
    }
}

function fetchHistory() {
    if(!currentPallet.id) return;
    
    document.getElementById('modalHistoryContainer').style.display = 'block';
    document.getElementById('modalHistoryList').innerHTML = '<li style="color: #64748b;">Ładowanie...</li>';
    
    fetch(`/magazyny-nowe/api/pallet/history?id=${currentPallet.id}&type=${currentPallet.type}&linia=${currentPallet.linia}`)
    .then(r => r.json())
    .then(data => {
        const list = document.getElementById('modalHistoryList');
        list.innerHTML = '';
        if(data.success && data.history.length > 0) {
            data.history.forEach(h => {
                list.innerHTML += `<li style="border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    <strong style="color: #0f172a;">${h.autor_data}</strong> [${h.autor_login}]: <span style="color: #2563eb; font-weight: 600;">${h.typ_ruchu}</span>
                    <br><span style="color: #475569;">${h.komentarz || ''}</span>
                </li>`;
            });
        } else {
            list.innerHTML = '<li style="color: #64748b;">Brak historii dla tej palety.</li>';
        }
    });
}

function togglePalletBlock() {
    if(!currentPallet.id) return;
    fetch('/magazyny-nowe/api/pallet/toggle-block', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: currentPallet.id,
            type: currentPallet.type,
            linia: currentPallet.linia
        })
    }).then(r => r.json()).then(data => {
        if(data.success) {
            alert(data.message || "Status blokady zmieniony.");
            window.location.reload();
        } else {
            alert("Błąd: " + data.error);
        }
    });
}

// ---- WAREHOUSE FILTERING & TABS ----
function switchWarehouse(warehouseId) {
    console.log("Przełączanie magazynu na:", warehouseId);
    
    currentWarehouseId = warehouseId;
    currentSubWarehouseId = 'all'; // Resetuj regał przy zmianie magazynu
    localStorage.setItem('warehouse_tab', warehouseId);
    localStorage.setItem('warehouse_subtab', 'all');
    
    // Zaktualizuj UI regałów (zaznacz "Wszystkie")
    const allRackInput = document.getElementById('rack-all');
    if (allRackInput) {
        allRackInput.checked = true;
        updateRackLabel('Wszystkie Lokalizacje');
    }
    
    // 1. Paski pojemności (Przełączanie widoczności)
    document.querySelectorAll('.capacity-bar').forEach(b => b.style.display = 'none');
    
    let capBar = document.getElementById('cap-' + warehouseId) || 
                 document.getElementById('cap-' + warehouseId.toUpperCase()) ||
                 document.getElementById('cap-' + warehouseId.toLowerCase());
                 
    if (capBar) {
        capBar.style.display = 'block';
    }
    
    // 2. Filtruj tabelę lokalnie
    filterTable(); 
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


// ---- SORTING LOGIC ----
function sortTable(n) {
    const table = document.getElementById("magazynyTable");
    if (!table) return;
    const tbody = table.querySelector("tbody");
    if (!tbody) return;
    
    const rows = Array.from(tbody.querySelectorAll("tr"));
    if (rows.length <= 1) return;

    const ths = table.querySelectorAll("thead th");
    const th = ths[n];
    let dir = th.getAttribute("data-dir") === "asc" ? "desc" : "asc";
    
    ths.forEach(t => t.setAttribute("data-dir", ""));
    th.setAttribute("data-dir", dir);

    rows.sort((rowA, rowB) => {
        let tdA = rowA.getElementsByTagName("td")[n];
        let tdB = rowB.getElementsByTagName("td")[n];
        
        if (!tdA || !tdB) return 0;
        
        let valA = tdA.textContent.trim();
        let valB = tdB.textContent.trim();
        
        if (n === 3) { // Ilość column index shifted
            let numA = parseFloat(valA.replace(/[^0-9.-]+/g,""));
            let numB = parseFloat(valB.replace(/[^0-9.-]+/g,""));
            if (!isNaN(numA) && !isNaN(numB)) {
                return dir === "asc" ? numA - numB : numB - numA;
            }
        }

        if (n === 4) { // Lokalizacja
            const locA = parseLocationCode(valA);
            const locB = parseLocationCode(valB);

            if (locA && locB) {
                if (locA.rackNo !== locB.rackNo) {
                    return dir === "asc" ? locA.rackNo - locB.rackNo : locB.rackNo - locA.rackNo;
                }
                if (locA.rowNo !== locB.rowNo) {
                    return dir === "asc" ? locA.rowNo - locB.rowNo : locB.rowNo - locA.rowNo;
                }
                if (locA.placeNo !== locB.placeNo) {
                    return dir === "asc" ? locA.placeNo - locB.placeNo : locB.placeNo - locA.placeNo;
                }
            } else if (locA && !locB) {
                return dir === "asc" ? -1 : 1;
            } else if (!locA && locB) {
                return dir === "asc" ? 1 : -1;
            }
        }
        return dir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
    });

    const frag = document.createDocumentFragment();
    rows.forEach(r => frag.appendChild(r));
    tbody.appendChild(frag);
}

// ---- MAIN MENU HANDLER ----

// ---- REPORTS & PRINT ----
function openReportsModal() { document.getElementById('reportsModal').style.display = 'flex'; }
function closeReportsModal() { document.getElementById('reportsModal').style.display = 'none'; }

function printInventorySheet(items, linia) {
    const sortedItems = items.sort((a, b) => a.location.localeCompare(b.location));
    const printArea = document.getElementById('printArea');
    if(!printArea) return;
    
    let html = `
        <div style="font-family: 'Segoe UI', sans-serif; padding: 20px;">
            <h1 style="text-align: center; font-size: 20px; border-bottom: 2px solid #000; padding-bottom: 10px;">
                ARKUSZ INWENTARYZACJI RĘCZNEJ - MAGAZYN CENTRALNY
            </h1>
            <div style="display: flex; justify-content: space-between; margin: 20px 0; font-size: 14px;">
                <span>Data wydruku: ${new Date().toLocaleString()}</span>
                <span>Hala: ${linia}</span>
                <span>Magazynier: ........................................</span>
            </div>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #f2f2f2;">
                        <th style="border: 1px solid #000; padding: 8px; text-align: center; width: 40px;">Lp.</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: left;">Lokalizacja</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: left;">Nazwa Produktu</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: left;">Data Prod. / Ważność</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: left;">Partia (Batch)</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: right;">System (kg/szt)</th>
                        <th style="border: 1px solid #000; padding: 8px; width: 100px;">STAN FAKTYCZNY</th>
                    </tr>
                </thead>
                <tbody>
    `;

    sortedItems.forEach((it, index) => {
        html += `
            <tr>
                <td style="border: 1px solid #000; padding: 6px; text-align: center; font-size: 12px; font-weight: bold;">${index + 1}</td>
                <td style="border: 1px solid #000; padding: 6px; font-family: monospace; font-weight: bold; font-size: 13px;">${it.location}</td>
                <td style="border: 1px solid #000; padding: 6px; font-size: 12px;">${it.productName}</td>
                <td style="border: 1px solid #000; padding: 6px; font-size: 11px;">${it.date_prod} / ${it.date_exp}</td>
                <td style="border: 1px solid #000; padding: 6px; font-size: 11px;">${it.batch}</td>
                <td style="border: 1px solid #000; padding: 6px; text-align: right; font-size: 12px;">${it.amount.toFixed(1)}</td>
                <td style="border: 1px solid #000; padding: 6px;"></td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
            <div style="margin-top: 30px; font-size: 12px;">
                Podpis osoby odpowiedzialnej: ................................................................
            </div>
        </div>
    `;

    printArea.innerHTML = html;
    window.print();
}

// ---- RETURN FROM PRODUCTION LOGIC ----
function openReturnModal(linia) {
    const body = document.getElementById('returnItemsBody');
    if(!body) return;
    document.getElementById('returnFormSection').style.display = 'none';
    body.innerHTML = '<tr><td colspan="7" class="text-center p-20 text-muted">Ładowanie...</td></tr>';
    document.getElementById('returnModal').style.display = 'flex';
    
    fetch(`/agro/api/production_items_for_return?linia=${linia}&limit=300`)
        .then(r => r.json())
        .then(res => {
            if(!res.success) return alert('Błąd: ' + (res.error || 'Nieznany'));
            renderReturnItems(res.items, linia);
        }).catch(e => { console.error(e); alert('Błąd połączenia'); });
}

function closeReturnModal() { document.getElementById('returnModal').style.display = 'none'; }

function escapeHTML(str) {
    if (!str && str !== 0) return '';
    return String(str).replace(/[&<>'"]/g, tag => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;'
    }[tag] || tag));
}

function renderReturnItems(items, linia) {
    const body = document.getElementById('returnItemsBody');
    body.innerHTML = '';
    if(!items || items.length === 0) {
        body.innerHTML = '<tr><td colspan="7" class="text-center p-20 text-muted">Brak surowców do zwrotu</td></tr>';
        return;
    }
    items.forEach(it => {
        const tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        tr.className = 'return-item-row';
        tr.innerHTML = `
            <td><input type="radio" name="return_sel" value="${escapeHTML(it.surowiec_id)}" 
                data-max="${escapeHTML(it.do_zwrotu)}" data-nazwa="${escapeHTML(it.nazwa)}" data-plan="${escapeHTML(it.plan_id || '')}" data-lok="${escapeHTML(it.lokalizacja || '')}" data-rid="${escapeHTML(it.ruch_id)}"></td>
            <td class="font-bold">${escapeHTML(it.nazwa)}</td>
            <td><span class="badge-outline small">${escapeHTML(it.lokalizacja || '—')}</span></td>
            <td class="text-right">${escapeHTML(it.ilosc_pobrana)}</td>
            <td class="text-right text-success">${escapeHTML(it.ilosc_zwrocona)}</td>
            <td class="text-right font-bold text-primary">${escapeHTML(it.do_zwrotu)}</td>
            <td class="text-muted small">${escapeHTML(it.data)}</td>
        `;
        tr.onclick = () => {
            const radio = tr.querySelector('input');
            radio.checked = true;
            selectReturnItem(radio, tr);
        };
        body.appendChild(tr);
    });
}

function selectReturnItem(radio, row) {
    document.querySelectorAll('.return-item-row').forEach(r => r.classList.remove('return-row-selected'));
    row.classList.add('return-row-selected');
    
    document.getElementById('return_ruch_id').value = radio.dataset.rid;
    document.getElementById('return_surowiec_id').value = radio.value;
    document.getElementById('return_plan_id').value = radio.dataset.plan;
    document.getElementById('return_nazwa').value = radio.dataset.nazwa;
    document.getElementById('return_lokalizacja').value = radio.dataset.lok;
    document.getElementById('return_ilosc').value = radio.dataset.max;
    document.getElementById('return_max_hint').textContent = 'Max: ' + radio.dataset.max + ' kg';
    document.getElementById('returnFormSection').style.display = 'block';
    
    document.getElementById('returnFormSection').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function submitReturn(linia) {
    const rId = document.getElementById('return_ruch_id').value;
    const sId = document.getElementById('return_surowiec_id').value;
    const qVal = parseFloat(document.getElementById('return_ilosc').value);
    const pId = document.getElementById('return_plan_id').value;
    const lok = document.getElementById('return_lokalizacja').value.trim();
    const note = document.getElementById('return_komentarz').value.trim();
    
    if(!sId || isNaN(qVal) || qVal <= 0) return alert('Podaj poprawną ilość!');
    if(!lok) return alert('Podaj lokalizację docelową!');

    fetch('/agro/api/return', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            surowiec_id: sId,
            ilosc: qVal,
            plan_id: pId || null,
            komentarz: note,
            ruch_produkcja_id: rId,
            lokalizacja: lok,
            linia: linia
        })
    }).then(r => r.json()).then(res => {
        if(res.success) {
            alert('Zwrot zapisany pomyślnie.');
            window.location.reload();
        } else alert('Błąd: ' + res.error);
    }).catch(e => { console.error(e); alert('Błąd połączenia'); });
}

// Initial setup
document.addEventListener('DOMContentLoaded', function() {
    console.log("Magazyn: Inicjalizacja stanu z widoku...");
    
    // 1. Zsynchronizuj zmienne JS z tym co zaznaczył serwer w HTML
    syncStateFromDOM();

    // 2. Przywróć wyszukiwarkę (tylko to zostawiamy w localStorage)
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        const savedSearch = localStorage.getItem('warehouse_search');
        if (savedSearch) {
            searchInput.value = savedSearch;
        }
    }

    // Domyślnie sortuj po lokalizacji rosnąco (regał -> rząd -> miejsce).
    const magazynyTable = document.getElementById('magazynyTable');
    if (magazynyTable) {
        sortTable(4);
    }

    // 3. Odpal filtrację na bazie tego co faktycznie widać w menu
    filterTable();

    // Modal close logic
    const modal = document.getElementById('palletModal');
    if(modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                closePalletModal();
            }
        });
    }

    // Restore view mode from localStorage
    const savedView = localStorage.getItem('warehouse_view_mode') || 'list';
    if (savedView === 'grid') {
        setViewMode('grid');
    }
});

// Updated filterTable to support both list and grid
function filterTable() {
    const input = document.getElementById("searchInput");
    const filter = input ? input.value.toUpperCase().trim() : "";
    const container = document.getElementById('warehouseItemsContainer');
    if (!container) return;

    syncStateFromDOM();

    // 1. Filter List View (Table Rows)
    const rows = container.querySelectorAll(".list-view-wrapper tr:not(:first-child)");
    rows.forEach(row => {
        const locCell = Array.from(row.getElementsByTagName("td")).find(td => td.getAttribute('data-label') === 'Lokalizacja');
        const locRaw = locCell ? (locCell.dataset.locRaw || locCell.textContent || '') : '';
        const locText = String(locRaw).toUpperCase().trim();
        const rowText = row.textContent.toUpperCase();
        
        const match = isMatch(rowText, locText, filter);
        row.style.display = match ? "" : "none";
    });

    // 2. Filter Grid View (Cards)
    const cards = container.querySelectorAll(".pallet-card");
    cards.forEach(card => {
        const locEl = card.querySelector(".loc-tag");
        const locRaw = locEl ? (locEl.dataset.locRaw || locEl.innerText || '') : '';
        const locText = String(locRaw).toUpperCase().trim();
        const cardText = card.innerText.toUpperCase();
        
        const match = isMatch(cardText, locText, filter);
        card.style.display = match ? "" : "none";
    });
}

function isMatch(allText, locText, filter) {
    const filterText = (filter || '').toUpperCase().trim();
    const textMatch = (filterText === "" || allText.indexOf(filterText) > -1);
    const slotMatch = (filterText !== "" && matchesLocationSlots(locText, filterText));

    if (!(textMatch || slotMatch)) return false;

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
