/**
 * Magazyny Nowe - Dashboard Initialization & State Synchronization
 */

function initWarehouseDashboard() {
    console.log("Inicjalizacja Magazyn V2 Dashboard...");

    // 1. Odtwórz Główny Magazyn (URL query param ma pierwszeństwo, potem localStorage, potem serwerowy domyślny)
    const urlParams = new URLSearchParams(window.location.search);
    const urlZakladka = urlParams.get('zakladka');
    let initialWarehouse = urlZakladka || localStorage.getItem('warehouse_tab');
    
    if (initialWarehouse) {
        const targetRadio = document.getElementById('radio-' + initialWarehouse);
        if (targetRadio) {
            targetRadio.checked = true;
            const labelEl = document.querySelector(`label[for="${targetRadio.id}"] .item-name`);
            if (labelEl && typeof updateWhLabel === 'function') {
                updateWhLabel(labelEl.innerText);
            }
            currentWarehouseId = initialWarehouse;
        } else {
            syncStateFromDOM();
        }
    } else {
        syncStateFromDOM();
    }

    // 2. Odtwórz Regał / Podlokalizację
    const savedSubWarehouse = localStorage.getItem('warehouse_subtab');
    if (savedSubWarehouse) {
        const targetRack = document.getElementById('rack-' + savedSubWarehouse);
        if (targetRack) {
            targetRack.checked = true;
            const labelEl = document.querySelector(`label[for="${targetRack.id}"] .item-name`);
            if (labelEl && typeof updateRackLabel === 'function') {
                updateRackLabel(labelEl.innerText);
            }
            currentSubWarehouseId = savedSubWarehouse;
        } else {
            const allRack = document.getElementById('rack-all');
            if (allRack) {
                allRack.checked = true;
                if (typeof updateRackLabel === 'function') updateRackLabel('Wszystkie Lokalizacje');
            }
            currentSubWarehouseId = 'all';
        }
    } else {
        const checkedRack = document.querySelector('input[name="rack_select"]:checked');
        if (checkedRack) {
            currentSubWarehouseId = checkedRack.id.replace('rack-', '');
        }
    }

    // 3. Widoczność opcji regałów w zależności od magazynu (np. OSIP)
    document.querySelectorAll('.nav-item-row-rack').forEach(row => {
        const rid = row.getAttribute('data-rack-id');
        if (currentWarehouseId === 'OSIP') {
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

    // 4. Paski pojemności
    document.querySelectorAll('.capacity-bar').forEach(b => b.style.display = 'none');
    let targetCapId = (currentSubWarehouseId !== 'all') ? currentSubWarehouseId : currentWarehouseId;
    let capBar = document.getElementById('cap-' + targetCapId) || 
                 document.getElementById('cap-' + targetCapId.toUpperCase()) ||
                 document.getElementById('cap-' + targetCapId.toLowerCase()) ||
                 document.getElementById('cap-' + currentWarehouseId);
    if (capBar) {
        capBar.style.display = 'block';
    }

    // 5. Inicjalizacja filtra lokalizacji (dropdown multiselect)
    if (typeof populateLocationFilter === 'function') {
        populateLocationFilter();
    }

    // 6. Odtwórz wyszukiwarkę
    const searchInput = document.getElementById('searchInput');
    const clearBtn = document.getElementById('clearSearchBtn');
    if (searchInput) {
        const savedSearch = localStorage.getItem('warehouse_search');
        if (savedSearch) {
            searchInput.value = savedSearch;
            currentSearchQuery = savedSearch;
            if (clearBtn) clearBtn.style.display = 'block';
        }
        
        searchInput.addEventListener('input', function() {
            localStorage.setItem('warehouse_search', this.value);
            if (clearBtn) clearBtn.style.display = this.value.length > 0 ? 'block' : 'none';
            if (typeof filterTable === 'function') filterTable();
        });
    }

    // 7. Odtwórz tryb widoku (lista / kafelki)
    const savedView = localStorage.getItem('warehouse_view_mode') || 'list';
    if (typeof setViewMode === 'function') {
        setViewMode(savedView);
    }

    // 8. Odtwórz sortowanie
    const savedSortCol = localStorage.getItem('warehouse_sort_col');
    const savedSortDir = localStorage.getItem('warehouse_sort_dir');
    if (savedSortCol !== null && !isNaN(parseInt(savedSortCol, 10))) {
        currentSortCol = parseInt(savedSortCol, 10);
        currentSortDir = savedSortDir === 'desc' ? 'desc' : 'asc';
        if (typeof updateSortHeaderIndicators === 'function') {
            updateSortHeaderIndicators();
        }
    }

    // 9. Uruchom pierwsze filtrowanie i renderowanie
    if (typeof filterTable === 'function') {
        filterTable();
    }

    // 10. Nasłuchiwacze zamykania modali po kliknięciu w tło
    const palletModal = document.getElementById('palletModal');
    if (palletModal) {
        palletModal.addEventListener('click', function(e) {
            if (e.target === this && typeof closePalletModal === 'function') {
                closePalletModal();
            }
        });
    }

    // 11. Dynamiczne ładowanie aktywnych drukarek
    const whPrinterSelect = document.getElementById('printerSelect');
    if (whPrinterSelect) {
        const liniaQuery = (typeof LINIA !== 'undefined' ? LINIA : 'PSD');
        fetch('/magazyn-dostawy/api/active-printers?linia=' + encodeURIComponent(liniaQuery))
        .then(r => r.json())
        .then(res => {
            if (res && res.success && Array.isArray(res.printers)) {
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
}

document.addEventListener('DOMContentLoaded', function() {
    initWarehouseDashboard();
});


