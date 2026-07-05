    window.openInventoryFor = function(id, nazwa, qty) {
        const sel = ensureInventorySelectOptions('inv_surowiec_id');
        if (sel) sel.value = id;
        document.getElementById('inv_qty').value = qty;
        openModal('modalInventory');
    };

    window.openStandardInventoryModal = function() {
        const first = (window._inventory || [])[0];
        if (first && typeof first.id !== 'undefined') {
            const qty = (typeof first.stan !== 'undefined') ? first.stan : (first.stan_magazynowy || 0);
            openInventoryFor(first.id, first.parent_nazwa || first.nazwa || '', qty);
            return;
        }

        ensureInventorySelectOptions('inv_surowiec_id');
        const qtyInput = document.getElementById('inv_qty');
        if (qtyInput) qtyInput.value = '';
        openModal('modalInventory');
    };

    window.openBulkInventoryModal = function() {
        document.getElementById('bulkInvBody').innerHTML = '<tr><td colspan="5" class="text-center text-muted">Ładowanie...</td></tr>';
        document.getElementById('bulkInvFilter').value = '';
        const prodBody = document.getElementById('prodInvBody');
        if (prodBody) {
            prodBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">Ładowanie...</td></tr>';
        }
        const prodFilter = document.getElementById('prodInvFilter');
        if (prodFilter) prodFilter.value = '';
        const prodZoneFilter = document.getElementById('prodInvZoneFilter');
        if (prodZoneFilter) prodZoneFilter.value = '';
        const prodTypeFilter = document.getElementById('prodInvTypeFilter');
        if (prodTypeFilter) prodTypeFilter.value = '';

        openModal('modalBulkInventory');

        Promise.all([
            fetch(`/agro/api/locations_inventory?linia=${AGRO_CONFIG.linia}`).then(r => r.json()),
            fetch(`/agro/api/production_inventory?linia=${AGRO_CONFIG.linia}&limit=1000`).then(r => r.json())
        ])
            .then(function(results) {
                const warehouseRes = results[0] || {};
                const productionRes = results[1] || {};

                if (!warehouseRes.success) {
                    showAlert('Błąd odczytu inwentaryzacji regałów: ' + (warehouseRes.error || 'Nieznany'));
                    return;
                }
                if (!productionRes.success) {
                    showAlert('Błąd odczytu inwentaryzacji produkcji: ' + (productionRes.error || 'Nieznany'));
                    return;
                }

                window._bulkInvItems = warehouseRes.items || [];
                window._prodInvItems = productionRes.items || [];
                renderBulkInventory(window._bulkInvItems);
                renderProductionInventory(window._prodInvItems);
                filterProductionInventory();
            })
            .catch(function(e) {
                console.error(e);
                showAlert('Błąd połączenia');
            });
    };

    function renderBulkInventory(items) {
        const body = document.getElementById('bulkInvBody');
        body.innerHTML = '';
        if (!items || items.length === 0) {
            body.innerHTML = '<tr><td colspan="5" class="text-center text-muted">Brak pozycji</td></tr>';
            return;
        }
        items.forEach(function(it) {
            const tr = document.createElement('tr');
            tr.className = 'bulk-inv-row';
            tr.dataset.nazwa = (it.nazwa || '').toLowerCase();
            tr.dataset.lok = (it.lokalizacja || '').toLowerCase();
            tr.innerHTML = `
                <td>${it.id}</td>
                <td>${it.nazwa || ''}</td>
                <td>${it.lokalizacja || '<span class="text-muted">—</span>'}</td>
                <td class="font-bold">${it.stan_magazynowy}</td>
                <td><input type="number" class="form-control bulk-inv-qty" data-id="${it.id}" step="0.1" value="${it.stan_magazynowy}" style="width:120px;"></td>
            `;
            body.appendChild(tr);
        });
    }

    window.filterBulkInventory = function() {
        const q = (document.getElementById('bulkInvFilter').value || '').toLowerCase();
        document.querySelectorAll('.bulk-inv-row').forEach(function(tr) {
            const show = !q || tr.dataset.nazwa.indexOf(q) !== -1 || tr.dataset.lok.indexOf(q) !== -1;
            tr.style.display = show ? '' : 'none';
        });
    };

    function renderProductionInventory(items) {
        const body = document.getElementById('prodInvBody');
        if (!body) return;

        body.innerHTML = '';
        if (!items || items.length === 0) {
            body.innerHTML = '<tr><td colspan="7" class="text-center text-muted">Brak pozycji produkcyjnych do inwentaryzacji</td></tr>';
            return;
        }

        items.forEach(function(it) {
            const tr = document.createElement('tr');
            tr.className = 'prod-inv-row';
            tr.dataset.nazwa = String(it.nazwa || '').toLowerCase();
            tr.dataset.zbiornik = String(it.zbiornik || '').toLowerCase();
            tr.dataset.plan = String(it.plan_name || it.plan_id || '').toLowerCase();
            tr.dataset.strefa = String(it.strefa || '').toUpperCase();
            tr.dataset.rodzaj = String(it.rodzaj || '').toUpperCase();

            const planLabel = it.plan_name ? (it.plan_name + (it.plan_id ? ' (#' + it.plan_id + ')' : '')) : (it.plan_id ? ('#' + it.plan_id) : '—');
            tr.innerHTML = `
                <td>#${it.ruch_id}</td>
                <td>${it.zbiornik || '—'}</td>
                <td>${it.strefa || 'INNE'}</td>
                <td>${it.rodzaj || 'SUROWCE'}</td>
                <td>
                    <div>${it.nazwa || ''}</div>
                    <div class="text-muted small">Plan: ${planLabel}</div>
                </td>
                <td class="font-bold">${it.stan_systemowy}</td>
                <td><input type="number" class="form-control prod-inv-qty" data-ruch-id="${it.ruch_id}" step="0.1" value="${it.stan_systemowy}" style="width:120px;"></td>
            `;
            body.appendChild(tr);
        });
    }

    window.filterProductionInventory = function() {
        const q = (document.getElementById('prodInvFilter') ? document.getElementById('prodInvFilter').value : '').toLowerCase();
        const zone = ((document.getElementById('prodInvZoneFilter') || {}).value || '').toUpperCase();
        const type = ((document.getElementById('prodInvTypeFilter') || {}).value || '').toUpperCase();

        document.querySelectorAll('.prod-inv-row').forEach(function(tr) {
            const textMatch = !q ||
                (tr.dataset.nazwa || '').indexOf(q) !== -1 ||
                (tr.dataset.zbiornik || '').indexOf(q) !== -1 ||
                (tr.dataset.plan || '').indexOf(q) !== -1;
            const zoneMatch = !zone || (tr.dataset.strefa || '') === zone;
            const typeMatch = !type || (tr.dataset.rodzaj || '') === type;
            tr.style.display = (textMatch && zoneMatch && typeMatch) ? '' : 'none';
        });
    };

    function _hasQtyChanged(newValue, oldValue) {
        const newNum = Number(newValue);
        const oldNum = Number(oldValue);
        if (!Number.isFinite(newNum) || !Number.isFinite(oldNum)) return false;
        return Math.abs(newNum - oldNum) > 0.0001;
    }

    window.submitBulkInventory = async function() {
        const warehouseInputs = document.querySelectorAll('.bulk-inv-qty');
        const warehouseItems = [];
        warehouseInputs.forEach(function(inp) {
            const id = inp.dataset.id;
            const orig = (window._bulkInvItems || []).find(x => String(x.id) === String(id));
            const newVal = parseFloat(inp.value);
            if (orig && !isNaN(newVal) && _hasQtyChanged(newVal, orig.stan_magazynowy)) {
                warehouseItems.push({ surowiec_id: id, actual_qty: newVal, komentarz: 'Inwentaryzacja zbiorcza' });
            }
        });

        const prodInputs = document.querySelectorAll('.prod-inv-qty');
        const productionItems = [];
        prodInputs.forEach(function(inp) {
            const ruchId = inp.dataset.ruchId;
            const orig = (window._prodInvItems || []).find(x => String(x.ruch_id) === String(ruchId));
            const newVal = parseFloat(inp.value);
            if (orig && !isNaN(newVal) && _hasQtyChanged(newVal, orig.stan_systemowy)) {
                productionItems.push({ ruch_id: ruchId, actual_qty: newVal, komentarz: 'Inwentaryzacja produkcji BB/MZ/KO' });
            }
        });

        if (warehouseItems.length === 0 && productionItems.length === 0) {
            return showAlert('Brak zmian do zapisania.');
        }

        if (!confirm('Zapisać zmiany? Regały: ' + warehouseItems.length + ', Produkcja: ' + productionItems.length)) {
            return;
        }

        try {
            let updatedWarehouse = 0;
            let updatedProduction = 0;

            if (warehouseItems.length > 0) {
                const warehouseResp = await fetch('/agro/api/bulk_inventory', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ items: warehouseItems, linia: AGRO_CONFIG.linia })
                });
                const warehouseRes = await warehouseResp.json();
                if (!warehouseResp.ok || !warehouseRes.success) {
                    showAlert('Błąd inwentaryzacji regałów: ' + (warehouseRes.error || 'Nieznany'));
                    return;
                }
                updatedWarehouse = Number(warehouseRes.updated || 0);
            }

            if (productionItems.length > 0) {
                const productionResp = await fetch('/agro/api/production_inventory', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ items: productionItems, linia: AGRO_CONFIG.linia })
                });
                const productionRes = await productionResp.json();
                if (!productionResp.ok || !productionRes.success) {
                    if (productionRes && Array.isArray(productionRes.errors) && productionRes.errors.length) {
                        const details = productionRes.errors.slice(0, 3).map(function(err) {
                            return '#' + (err.ruch_id || '?') + ': ' + (err.error || 'błąd');
                        }).join('; ');
                        showAlert('Błąd inwentaryzacji produkcji: ' + details);
                    } else {
                        showAlert('Błąd inwentaryzacji produkcji: ' + ((productionRes && productionRes.error) || 'Nieznany'));
                    }
                    return;
                }
                updatedProduction = Number(productionRes.updated || 0);
            }

            showAlert('Zapisano zmiany. Regały: ' + updatedWarehouse + ', Produkcja: ' + updatedProduction + '.');
            location.reload();
        } catch (e) {
            console.error(e);
            showAlert('Błąd połączenia');
        }
    };

    window.submitInventory = function() {
        const data = {
            surowiec_id: document.getElementById('inv_surowiec_id').value,
            actual_qty: document.getElementById('inv_qty').value,
            komentarz: document.getElementById('inv_komentarz').value,
            linia: AGRO_CONFIG.linia
        };
        if (!data.surowiec_id || data.actual_qty === "") return showAlert("Wypełnij wszystkie pola!");
        apiCall('/agro/api/inventory', data);
    };


