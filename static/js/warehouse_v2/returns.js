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
            if(!res.success) {
                AppDialog.alert('Błąd: ' + (res.error || 'Nieznany'));
                return;
            }
            renderReturnItems(res.items, linia);
        }).catch(e => { console.error(e); AppDialog.alert('Błąd połączenia'); });
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
    
    if(!sId || isNaN(qVal) || qVal <= 0) {
        AppDialog.alert('Podaj poprawną ilość!');
        return;
    }
    if(!lok) {
        AppDialog.alert('Podaj lokalizację docelową!');
        return;
    }

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
            AppDialog.alert('Zwrot zapisany pomyślnie.').then(() => {
                window.location.reload();
            });
        } else {
            AppDialog.alert('Błąd: ' + res.error);
        }
    }).catch(e => { console.error(e); AppDialog.alert('Błąd połączenia'); });
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

