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

let currentFilteredItems = [];
let currentRenderedCount = 0;
const PAGE_SIZE = 100;

// ---- TOAST NOTIFICATIONS ----
function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:99999;display:flex;flex-direction:column;gap:10px;max-width:340px;';
        document.body.appendChild(container);
    }
    const colors = { success: '#10b981', error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' };
    const icons  = { success: 'check_circle', error: 'error', warning: 'warning', info: 'info' };
    const toast = document.createElement('div');
    toast.style.cssText = `background:${colors[type]||colors.info};color:#fff;padding:14px 18px;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,0.25);display:flex;align-items:center;gap:10px;font-size:14px;font-weight:600;opacity:0;transform:translateX(40px);transition:all 0.3s ease;`;
    toast.innerHTML = `<span class="material-icons" style="font-size:20px;">${icons[type]||icons.info}</span>${message}`;
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.style.opacity='1'; toast.style.transform='translateX(0)'; });
    setTimeout(() => {
        toast.style.opacity='0'; toast.style.transform='translateX(40px)';
        setTimeout(() => toast.remove(), 350);
    }, 4000);
}

// ---- HARD DELETE PALLET (admin only) ----
function deletePalletPermanently() {
    if (!currentPallet.id) return;
    if (!confirm(`⚠️ TRWAŁE USUNIĘCIE\n\nPaleta: ${currentPallet.displayId}\nProdukt: ${currentPallet.productName}\n\nOperacja nieodwracalna. Kontynuować?`)) return;
    
    fetch('/magazyny-nowe/api/pallet/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ id: currentPallet.id, type: currentPallet.type, linia: currentPallet.linia })
    }).then(r => r.json()).then(data => {
        if (data.success) {
            removePalletFromDOM(currentPallet.id, `🗑️ ${data.message || 'Usunięto pomyślnie'}`);
        } else {
            showToast('Błąd: ' + (data.error || data.message || 'Nieznany błąd'), 'error');
        }
    }).catch(e => showToast('Błąd połączenia: ' + e, 'error'));
}


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
    
    const setEl = (id, val) => { const el = document.getElementById(id); if(el) el.textContent = val; };
    setEl('modalDisplayId', displayId);
    setEl('modalProductName', productName);
    setEl('modalAmount', amount);
    setEl('modalLocation', location || 'Brak lokalizacji');
    setEl('modalType', type);
    setEl('modalDate', date || '-');
    setEl('modalDateAdded', dateAdded || '-');

    const qrImg = document.getElementById('modalQrCode');
    if (qrImg) {
        qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=60x60&data=${encodeURIComponent(displayId)}`;
        qrImg.style.display = 'block';
    }

    // Blocking status indicator in modal
    const blockBtn = document.getElementById('toggleBlockBtn');
    if (blockBtn) {
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
    }
    
    const returnBtn = document.getElementById('returnToRawBtn');
    if (returnBtn) {
        returnBtn.style.display = (type === 'Wyrób Gotowy') ? 'flex' : 'none';
    }
    
    const histContainer = document.getElementById('modalHistoryContainer');
    const histList = document.getElementById('modalHistoryList');
    if (histContainer) histContainer.style.display = 'none';
    if (histList) histList.innerHTML = '';
    
    const modal = document.getElementById('palletModal');
    const content = document.getElementById('palletModalContent');
    
    if (!modal || !content) {
        console.error('Modal elements not found! Check _modals.html is included.');
        return;
    }
    
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

// Usuwa paletę z DOM bez przeładowania strony
function removePalletFromDOM(palletId, message) {
    closePalletModal();
    
    // Usuń z globalnej tablicy danych allWarehouseItems, aby uniknąć ponownego wyrenderowania przez filterTable
    allWarehouseItems = allWarehouseItems.filter(item => String(item.id) !== String(palletId));
    if (typeof currentFilteredItems !== 'undefined') {
        currentFilteredItems = currentFilteredItems.filter(item => String(item.id) !== String(palletId));
    }
    
    // Znajdź i usuń wiersz tabeli oraz kafelek
    const row = document.querySelector(`tr[data-id="${palletId}"]`);
    const card = document.querySelector(`.pallet-card[data-id="${palletId}"]`);
    
    [row, card].forEach(el => {
        if (!el) return;
        el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        el.style.opacity = '0';
        el.style.transform = 'scale(0.95)';
        setTimeout(() => el.remove(), 320);
    });
    
    // Pokaż toast zamiast alert
    showToast(message || 'Operacja wykonana pomyślnie.', 'success');
}

// ---- PALLET OPERATIONS ----
function promptMoveLocation() {
    if(!currentPallet.id) return;
    
    // Generowanie podpowiedzi tylko raz
    const datalist = document.getElementById('locationSuggestions');
    if (datalist && datalist.children.length === 0) {
        let options = '';
        for(let r=1; r<=10; r++) {
            let rStr = r.toString().padStart(2,'0');
            let maxCols = (r===5) ? 4 : 10;
            let maxRows = (r===5) ? 4 : 3;
            for(let row=1; row<=maxRows; row++) {
                for(let col=1; col<=maxCols; col++) {
                    options += `<option value="R${rStr}${col.toString().padStart(2,'0')}${row.toString().padStart(2,'0')}"></option>`;
                }
            }
        }
        options += '<option value="MP01"></option><option value="MS01"></option><option value="MGW01"></option>';
        datalist.innerHTML = options;
    }

    const input = document.getElementById('newLocationInput');
    const errEl = document.getElementById('moveLocationError');
    if(input) {
        input.value = ''; // okno ma być puste
        if(errEl) errEl.style.display = 'none';
    }
    
    const modal = document.getElementById('moveLocationModal');
    if(modal) modal.style.display = 'flex';
}

function closeMoveLocationModal() {
    const modal = document.getElementById('moveLocationModal');
    if(modal) modal.style.display = 'none';
}

function submitMoveLocation() {
    if(!currentPallet.id) return;
    const input = document.getElementById('newLocationInput');
    const errEl = document.getElementById('moveLocationError');
    let newLoc = input ? input.value.trim().toUpperCase() : '';
    
    if(!newLoc) {
        if(errEl) {
            errEl.textContent = 'Lokalizacja nie może być pusta!';
            errEl.style.display = 'block';
        }
        return;
    }

    if(errEl) errEl.style.display = 'none';

    fetch('/magazyny-nowe/api/pallet/move', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: currentPallet.id,
            type: currentPallet.type,
            location: newLoc,
            linia: currentPallet.linia || 'PSD'
        })
    }).then(r => r.json()).then(data => {
        if(data.success) {
            showToast("Przeniesiono pomyślnie.", 'success');
            closeMoveLocationModal();
            closePalletModal();
            setTimeout(() => window.location.reload(), 1000);
        } else {
            if(errEl) {
                errEl.textContent = "Błąd: " + (data.error || data.message || "Nieznany błąd zapisu");
                errEl.style.display = 'block';
            } else {
                alert("Błąd: " + (data.error || data.message));
            }
        }
    }).catch(e => {
        if(errEl) {
            errEl.textContent = "Błąd połączenia z serwerem.";
            errEl.style.display = 'block';
        }
    });
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
    if(confirm(`Czy na pewno chcesz WYDAĆ paletę ${currentPallet.displayId}?\n\nPaleta trafi do tabeli EXPEDITION (magazyn_archiwum) i zniknie z aktywnej listy.`)) {
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
                removePalletFromDOM(currentPallet.id, `Paleta ${currentPallet.displayId} wydana do EXPEDITION ✓`);
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
                removePalletFromDOM(currentPallet.id, `Paleta ${currentPallet.displayId} zarchiwizowana ✓`);
            } else {
                alert("Błąd: " + data.error);
            }
        });
    }
}

function promptReturnToRaw() {
    if(!currentPallet.id) return;
    if(confirm(`Czy na pewno chcesz zwrócić paletę ${currentPallet.displayId} (${currentPallet.productName}) jako SUROWIEC?\nPaleta zostanie wyzerowana w wyrobach gotowych i dodana do surowców na lokalizację OSIP.`)) {
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
                removePalletFromDOM(currentPallet.id, data.message || 'Zwrócono pomyślnie ✓');
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
            showToast(data.message || 'Status blokady zmieniony.', 'success');
            // Zaktualizuj stan wizualny wiersza bez reload
            const row = document.querySelector(`tr[data-id="${currentPallet.id}"]`);
            const card = document.querySelector(`.pallet-card[data-id="${currentPallet.id}"]`);
            const newBlocked = !currentPallet.is_blocked;
            [row, card].forEach(el => {
                if (!el) return;
                el.dataset.blocked = newBlocked ? '1' : '0';
                el.classList.toggle('is-blocked-row', newBlocked);
                el.classList.toggle('is-blocked-card', newBlocked);
            });
            closePalletModal();
        } else {
            alert("Błąd: " + data.error);
        }
    });
}

function printCurrentPallet() {
    if(!currentPallet.id) return;
    const printerId = document.getElementById('printerSelect').value;
    if(!printerId) {
        alert("Wybierz drukarkę z listy przed wydrukiem.");
        return;
    }
    
    fetch('/magazyny-nowe/api/pallet/print', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: currentPallet.id,
            type: currentPallet.type,
            linia: currentPallet.linia,
            printer_id: printerId
        })
    }).then(r => r.json()).then(data => {
        if(data.success) {
            alert("Etykieta została pomyślnie wysłana do drukarki: " + data.message);
        } else {
            alert("Błąd podczas drukowania: " + data.error);
        }
    }).catch(e => {
        alert("Błąd połączenia: " + e);
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
            <td><input type="radio" name="return_sel" value="${it.surowiec_id}" 
                data-max="${it.do_zwrotu}" data-nazwa="${it.nazwa}" data-plan="${it.plan_id || ''}" data-lok="${it.lokalizacja || ''}" data-rid="${it.ruch_id}"></td>
            <td class="font-bold">${it.nazwa}</td>
            <td><span class="badge-outline small">${it.lokalizacja || '—'}</span></td>
            <td class="text-right">${it.ilosc_pobrana}</td>
            <td class="text-right text-success">${it.ilosc_zwrocona}</td>
            <td class="text-right font-bold text-primary">${it.do_zwrotu}</td>
            <td class="text-muted small">${it.data}</td>
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

    // 2. Przywróć wyszukiwarkę i filtry z localStorage
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        const savedSearch = localStorage.getItem('warehouse_search');
        if (savedSearch) {
            searchInput.value = savedSearch;
            currentSearchQuery = savedSearch;
        }
        // Zapisuj przy każdym naciśnięciu klawisza
        searchInput.addEventListener('input', function() {
            localStorage.setItem('warehouse_search', this.value);
            filterTable();
        });
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

    // Dynamic loading of network printers in pallet details modal
    const whPrinterSelect = document.getElementById('printerSelect');
    if (whPrinterSelect) {
        const liniaQuery = (typeof LINIA !== 'undefined' ? LINIA : 'PSD');
        fetch('/magazyn-dostawy/api/active-printers?linia=' + encodeURIComponent(liniaQuery))
        .then(r => r.json())
        .then(res => {
            if (res && res.success && Array.isArray(res.printers)) {
                // Keep only placeholder, remove old database static options to prevent duplicates or stale entries
                whPrinterSelect.innerHTML = '<option value="">-- Wybierz drukarkę --</option>';
                res.printers.forEach(p => {
                    const option = document.createElement('option');
                    option.value = p.selection_value || `db:${p.id}`;
                    const ipTxt = p.ip ? ` (${p.ip})` : '';
                    const locTxt = p.lokalizacja ? ` - ${p.lokalizacja}` : '';
                    const sourceTxt = (p.source === 'network') ? ' [sieć]' : '';
                    option.textContent = `${p.nazwa || 'Drukarka'}${ipTxt}${locTxt}${sourceTxt}`;
                    whPrinterSelect.appendChild(option);
                });
                
                const warningEl = document.getElementById('printerSelectionWarning');
                if (warningEl) {
                    warningEl.style.display = res.printers.length > 0 ? 'none' : 'block';
                }
            }
        })
        .catch(e => console.warn("Failed to load active printers dynamically:", e));
    }
});

// Updated filterTable to support both list and grid via dynamic JS rendering
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
            'display:flex', 'align-items:center', 'gap:10px',
            'padding:8px 14px', 'margin-bottom:8px',
            'background:linear-gradient(135deg,#eff6ff,#dbeafe)',
            'border:1px solid #93c5fd', 'border-radius:10px',
            'font-size:13px', 'font-weight:600', 'color:#1d4ed8',
            'flex-wrap:wrap'
        ].join(';');
        tableWrapper.insertAdjacentElement('beforebegin', banner);
    }

    // Buduj treść bannera
    const parts = [];
    if (hasSearch) parts.push(`🔍 Szukano: <strong>"${filter}"</strong>`);
    if (hasWarehouse) parts.push(`🏭 Magazyn: <strong>${currentWarehouseId}</strong>`);
    if (hasRack) parts.push(`📦 Regał: <strong>${currentSubWarehouseId}</strong>`);

    const hidden = total - visible;
    const resultInfo = hidden > 0
        ? `<span style="margin-left:auto;background:#1d4ed8;color:#fff;padding:2px 10px;border-radius:20px;font-size:12px;">${visible} z ${total} rekordów</span>`
        : `<span style="margin-left:auto;background:#10b981;color:#fff;padding:2px 10px;border-radius:20px;font-size:12px;">Wszystkie ${total} rekordów</span>`;

    banner.style.display = 'flex';
    banner.innerHTML = `
        <span class="material-icons" style="font-size:18px;color:#2563eb;">filter_list</span>
        <span>Przefiltrowano: ${parts.join(' &nbsp;·&nbsp; ')}</span>
        ${resultInfo}
        <button onclick="clearAllFilters()" style="border:none;background:none;cursor:pointer;color:#64748b;font-size:11px;padding:0 4px;" title="Wyczyść filtry">✕ wyczyść</button>
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
