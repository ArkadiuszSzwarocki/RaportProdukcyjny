/**
 * Agro Warehouse Logic
 */
(function () {
    const CONFIG = {
        linia: document.body.getAttribute('data-linia') || 'Agro',
        current_plan_id: null,
        current_plan_name: null
    };

    // ---- ALERT HELPER (używa toast jeśli dostępny, fallback na alert) ----
    window.showAlert = function(msg) {
        if (typeof window.showToast === 'function') {
            window.showToast(String(msg), 'warning');
        } else {
            alert(msg);
        }
    };

    // ---- HANDLERY DLA PRZYCISKÓW Z GRUPY (Zmień nazwę / Korekta / Pobierz FIFO) ----
    window.handleOpenUsageForGroup = function(e, nazwa, lok, qty) {
        if (e && e.stopPropagation) e.stopPropagation();
        // Znajdź pierwszą paletę z grupy
        const g = (window._inventory_groups || []).find(x => x.nazwa === nazwa);
        if (!g || !g.pallets || g.pallets.length === 0) {
            showAlert('Brak palet dla: ' + nazwa); return;
        }
        const p = g.pallets[0];
        openUsageFor(p.id, nazwa, p.lokalizacja || '', p.stan || 0);
    };

    window.handleOpenInventoryForGroup = function(e, nazwa, qty) {
        if (e && e.stopPropagation) e.stopPropagation();
        const g = (window._inventory_groups || []).find(x => x.nazwa === nazwa);
        if (!g || !g.pallets || g.pallets.length === 0) {
            showAlert('Brak palet dla: ' + nazwa); return;
        }
        const p = g.pallets[0];
        openInventoryFor(p.id, nazwa, p.stan || 0);
    };

    window.handleOpenRenameFromGroup = function(e, nazwa) {
        if (e && e.stopPropagation) e.stopPropagation();
        const g = (window._inventory_groups || []).find(x => x.nazwa === nazwa);
        if (!g || !g.pallets || g.pallets.length === 0) {
            showAlert('Brak palet dla: ' + nazwa); return;
        }
        const p = g.pallets[0];
        openRenameModal(p.id, nazwa);
    };

    window.initWarehouse = function(config) {
        Object.assign(CONFIG, config);
        window._current_plan = { id: CONFIG.current_plan_id, name: CONFIG.current_plan_name };
    };

    window.openModal = function(id) {
        const d = document.getElementById(id);
        if (!d) return;
        if (typeof d.showModal === 'function') {
            d.showModal();
            return;
        }
        d.style.display = 'block';
        d.setAttribute('data-open', '1');
    };

    window.closeModal = function(id) {
        const d = document.getElementById(id);
        if (!d) return;
        if (typeof d.close === 'function') {
            try { d.close(); return; } catch(e) {}
        }
        d.style.display = 'none';
        d.removeAttribute('data-open');
    };

    window.openUsageFor = function(id, nazwa, lok, qty) {
        const sel = document.getElementById('usage_surowiec_id');
        if (!sel.options.length) {
            window._inventory.forEach(function(s) {
                const o = document.createElement('option');
                o.value = s.id;
                o.textContent = s.nazwa + ' - ' + (s.lokalizacja || 'Brak') + ' (' + s.stan + ' kg)';
                sel.appendChild(o);
            });
        }
        sel.value = id;
        document.getElementById('usage_ilosc').value = qty;
        document.getElementById('usage_location_scan').value = lok || '';
        document.getElementById('usage_zbiornik').value = '';
        document.getElementById('usage_plan_id').value = '';
        document.getElementById('usage_komentarz').value = '';
        
        try {
            if (window._current_plan && window._current_plan.id) {
                document.getElementById('usage_plan_id').value = window._current_plan.id || '';
                document.getElementById('usage_plan_name').value = window._current_plan.name || '';
            } else {
                fetch(`/agro/api/current_plan?linia=${CONFIG.linia}`).then(r => r.json()).then(res => {
                    if (res && res.success) {
                        window._current_plan = { id: res.plan_id || null, name: res.plan_name || null };
                        document.getElementById('usage_plan_id').value = res.plan_id || '';
                        document.getElementById('usage_plan_name').value = res.plan_name || '';
                    }
                }).catch(e => console.warn('Failed to fetch current plan id', e));
            }
        } catch(e) { console.warn('Unable to prefill plan id', e); }
        openModal('modalUsage');
    };

    window.openInventoryFor = function(id, nazwa, qty) {
        document.getElementById('inv_surowiec_id').value = id;
        document.getElementById('inv_qty').value = qty;
        openModal('modalInventory');
    };

    window.openRenameModal = function(id, nazwa) {
        document.getElementById('rename_surowiec_id').value = id;
        document.getElementById('rename_new_name').value = nazwa || '';
        document.getElementById('rename_komentarz').value = '';
        openModal('modalRename');
    };

    window.submitRename = function() {
        const id = document.getElementById('rename_surowiec_id').value;
        const newName = document.getElementById('rename_new_name').value.trim();
        const koment = document.getElementById('rename_komentarz').value.trim();
        if (!id || !newName) return showAlert('Podaj nową nazwę!');
        fetch('/agro/api/rename', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ surowiec_id: id, new_name: newName, komentarz: koment, linia: CONFIG.linia })
        }).then(r => r.json()).then(res => {
            if (res.success) location.reload();
            else showAlert('Błąd: ' + (res.error || 'Nieznany'));
        }).catch(e => { console.error(e); showAlert('Błąd połączenia'); });
    };

    window.openProductionModal = function() {
        document.getElementById('prod_limit').value = 50;
        document.getElementById('prodMovesBody').innerHTML = '';
        openModal('modalProduction');
        loadProductionMoves();
    };

    window.loadProductionMoves = function() {
        const limit = parseInt(document.getElementById('prod_limit').value) || 50;
        fetch(`/agro/api/production_moves?linia=${CONFIG.linia}&limit=` + limit)
            .then(r => r.json())
            .then(res => {
                if (!res.success) return showAlert('Błąd: ' + (res.error || 'Nieznany'));
                const body = document.getElementById('prodMovesBody');
                body.innerHTML = '';
                res.moves.forEach(m => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${m.surowiec_nazwa || ''}</td>
                        <td class="font-bold">${m.ilosc}</td>
                        <td>${m.lokalizacja || ''}</td>
                        <td>${m.zbiornik || ''}</td>
                        <td>${m.plan_id || ''}</td>
                        <td>${m.autor_login || ''}</td>
                        <td>${m.autor_data || ''}</td>
                    `;
                    body.appendChild(tr);
                });
            }).catch(e => { console.error(e); showAlert('Błąd połączenia'); });
    };

    window.openGroupPopup = function(evt, index, nazwa) {
        if (evt && evt.stopPropagation) evt.stopPropagation();
        closeGroupPopup();
        const g = window._inventory_groups[index];
        const popup = document.createElement('div');
        popup.id = 'groupPopup';
        popup.className = 'group-popup';
        popup.innerHTML = '<div class="popup-close" onclick="closeGroupPopup()">✕</div>' + renderGroupPopupHtml(g, nazwa);
        document.body.appendChild(popup);

        try { bindGroupPopupButtons(popup); } catch(e) { console.warn('bindGroupPopupButtons failed', e); }

        try {
            const anchor = evt && evt.currentTarget ? evt.currentTarget : (evt && evt.target ? evt.target : null);
            const rect = anchor ? anchor.getBoundingClientRect() : null;
            let left = rect ? (rect.right + 8) : (window.innerWidth - popup.offsetWidth - 20);
            let top = rect ? rect.top : 80;
            if (left + popup.offsetWidth > window.innerWidth - 8) {
                left = (rect ? rect.left - popup.offsetWidth - 8 : 20);
            }
            if (top + popup.offsetHeight > window.innerHeight - 20) top = window.innerHeight - popup.offsetHeight - 20;
            if (top < 10) top = 10;
            popup.style.left = left + 'px';
            popup.style.top = top + 'px';
        } catch(e) {}

        setTimeout(function(){
            window.addEventListener('click', outsideClickHandler);
            window.addEventListener('resize', closeGroupPopup);
            window.addEventListener('keydown', escCloseHandler);
        }, 10);
    };

    function renderGroupPopupHtml(g, nazwa) {
        if (!g) return '<div class="popup-body"><div class="text-muted small">Brak palet</div></div>';
        let html = '<div class="popup-title small text-muted" style="margin-bottom:8px;">Palety dla: ' + (g.nazwa || nazwa) + '</div>';
        html += '<div class="popup-body">';
        g.pallets.forEach(function(p){
            html += '<div class="pallet-row" style="display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px; border-radius:6px; background:#fff; border:1px solid #f1f5f9; margin-bottom:8px;">';
            html += '<div class="pallet-info" style="flex:1; min-width:0; font-size:13px;">#' + p.id + ' — ' + (p.nazwa||'') + '<div class="text-muted" style="font-size:12px; margin-top:4px;">(' + (p.lokalizacja||'Brak') + ')</div></div>';
            html += '<div class="pallet-actions" style="display:flex; gap:6px; flex-direction:column; width:120px;">';
                html += '<button class="btn btn-ghost btn-xxs popup-usage" data-id="' + p.id + '" data-name=' + JSON.stringify(g.nazwa) + ' data-lok=' + JSON.stringify(p.lokalizacja||'') + ' data-stan=' + (p.stan||0) + '>Pobierz</button>';
                html += '<button class="btn btn-ghost btn-xxs popup-return" data-id="' + p.id + '" data-name=' + JSON.stringify(g.nazwa) + ' data-lok=' + JSON.stringify(p.lokalizacja||'') + '>Zwrot</button>';
                html += '<button class="btn btn-ghost btn-xxs popup-issuew" data-id="' + p.id + '" data-name=' + JSON.stringify(g.nazwa) + '>Wydanie</button>';
                html += '<button class="btn btn-ghost btn-xxs popup-inv" data-id="' + p.id + '" data-name=' + JSON.stringify(g.nazwa) + ' data-stan=' + (p.stan||0) + '>Korekta</button>';
                html += '<button class="btn btn-ghost btn-xxs popup-rename" data-id="' + p.id + '" data-name=' + JSON.stringify(p.nazwa||g.nazwa) + '>Zmień nazwę</button>';
            html += '</div></div>';
        });
        html += '</div>';
        return html;
    }

    window.closeGroupPopup = function() {
        const existing = document.getElementById('groupPopup');
        if (existing) existing.remove();
        window.removeEventListener('click', outsideClickHandler);
        window.removeEventListener('resize', closeGroupPopup);
        window.removeEventListener('keydown', escCloseHandler);
    };

    function bindGroupPopupButtons(popup) {
        if (!popup) return;
        popup.querySelectorAll('.popup-usage').forEach(function(btn){
            btn.addEventListener('click', function(e){
                e.stopPropagation();
                openUsageFor(btn.dataset.id, btn.dataset.name, btn.dataset.lok, parseFloat(btn.dataset.stan) || 0);
            });
        });
        popup.querySelectorAll('.popup-inv').forEach(function(btn){
            btn.addEventListener('click', function(e){
                e.stopPropagation();
                openInventoryFor(btn.dataset.id, btn.dataset.name, parseFloat(btn.dataset.stan) || 0);
            });
        });
        popup.querySelectorAll('.popup-rename').forEach(function(btn){
            btn.addEventListener('click', function(e){
                e.stopPropagation();
                openRenameModal(btn.dataset.id, btn.dataset.name);
            });
        });
        popup.querySelectorAll('.popup-return').forEach(function(btn){
            btn.addEventListener('click', function(e){
                e.stopPropagation();
                openReturnFor(btn.dataset.id, btn.dataset.name, btn.dataset.lok);
            });
        });
        popup.querySelectorAll('.popup-issuew').forEach(function(btn){
            btn.addEventListener('click', function(e){
                e.stopPropagation();
                openIssueWarehouseFor(btn.dataset.id, btn.dataset.name);
            });
        });
    }

    function outsideClickHandler(e) {
        const p = document.getElementById('groupPopup');
        if (p && !p.contains(e.target)) closeGroupPopup();
    }

    function escCloseHandler(e) { if (e.key === 'Escape') closeGroupPopup(); }

    window.apiCall = async function(endpoint, data) {
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const res = await response.json();
            if (res.success) {
                location.reload();
            } else {
                showAlert("Błąd: " + (res.error || "Nieznany błąd"));
            }
        } catch (e) {
            console.error(e);
            showAlert("Błąd połączenia z serwerem.");
        }
    };

    window.addDeliveryRow = function(nazwa = '', ilosc = '', komentarz = '') {
        const container = document.getElementById('deliveryList');
        const row = document.createElement('div');
        row.className = 'delivery-row row items-center gap-8';
        row.style.display = 'flex';
        row.innerHTML = `
            <input type="text" class="form-control del-name" placeholder="Nazwa surowca" list="surowceList" style="flex:1;" value="${nazwa}">
            <input type="number" class="form-control del-qty" step="0.1" placeholder="Ilość (kg)" style="width:140px;" value="${ilosc}">
            <input type="text" class="form-control del-note" placeholder="Komentarz (opcjonalnie)" style="flex:0.8;" value="${komentarz}">
            <button type="button" class="btn btn-ghost" onclick="this.parentNode.remove()">Usuń</button>
        `;
        container.appendChild(row);
    };

    window.submitDelivery = function() {
        const editId = document.getElementById('del_edit_id').value;
        const rows = document.querySelectorAll('.delivery-row');
        if (editId) {
            if (rows.length === 0) return showAlert('Brak danych do zapisania');
            const first = rows[0];
            const nameVal = first.querySelector('.del-name').value.trim();
            const qtyVal = first.querySelector('.del-qty').value.toString().replace(',', '.');
            const qtyNum = parseFloat(qtyVal);
            if (!nameVal || !isFinite(qtyNum)) return showAlert('Wypełnij wszystkie pola prawidłowymi wartościami!');
            const noteVal = first.querySelector('.del-note').value.trim();
            fetch('/agro/api/delivery', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ ruch_id: editId, nazwa: nameVal, ilosc: qtyNum, komentarz: noteVal })
            }).then(r => r.json()).then(res => {
                if (res.success) location.reload();
                else showAlert('Błąd: ' + (res.error || 'Nieznany'));
            }).catch(e => { console.error(e); showAlert('Błąd połączenia'); });
        } else {
            const items = [];
            rows.forEach(r => {
                const nameVal = r.querySelector('.del-name').value.trim();
                const qtyVal = r.querySelector('.del-qty').value.toString().replace(',', '.');
                const qtyNum = parseFloat(qtyVal);
                const noteVal = r.querySelector('.del-note').value.trim();
                if (nameVal && isFinite(qtyNum) && qtyNum > 0) items.push({ nazwa: nameVal, ilosc: qtyNum, komentarz: noteVal });
            });
            if (items.length === 0) return showAlert('Dodaj przynajmniej jedną paletę z prawidłowymi danymi');
            apiCall('/agro/api/delivery', { items: items, linia: CONFIG.linia });
        }
    };

    window.openCreateDeliveryModal = function() {
        document.getElementById('del_edit_id').value = '';
        document.getElementById('modalDeliveryTitle').innerText = 'Przyjęcie Dostawy (Nowa Paleta)';
        document.getElementById('modalDeliverySubmit').innerText = 'Zgłoś Dostawę';
        document.getElementById('deliveryList').innerHTML = '';
        for (let i = 0; i < 20; i++) addDeliveryRow();
        openModal('modalDelivery');
    };

    window.openConfirmModal = async function(ruch_id, nazwa, ilosc) {
        document.getElementById('conf_ruch_id').value = ruch_id;
        document.getElementById('conf_nazwa').innerText = nazwa;
        document.getElementById('conf_ilosc').innerText = ilosc;
        document.getElementById('conf_lokalizacja').value = '';
        const sugBox = document.getElementById('suggestionBox');
        sugBox.style.display = 'none';
        try {
            const response = await fetch('/agro/api/suggest-location', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nazwa: nazwa, linia: CONFIG.linia })
            });
            const res = await response.json();
            if (res.success && res.suggestion) {
                document.getElementById('conf_lokalizacja').value = res.suggestion;
                document.getElementById('suggestionText').innerHTML = '<span class="material-icons" style="font-size:16px;">lightbulb</span> Sugerowane miejsce: <strong>' + res.suggestion + '</strong>';
                sugBox.style.display = 'block';
            }
        } catch (e) {}
        openModal('modalConfirm');
    };

    window.submitConfirm = function() {
        const rId = document.getElementById('conf_ruch_id').value;
        const locVal = document.getElementById('conf_lokalizacja').value;
        if (!locVal) return showAlert("Podaj lokalizację!");
        apiCall('/agro/api/confirm', { ruch_id: rId, lokalizacja: locVal, linia: CONFIG.linia });
    };

    window.submitUsage = function() {
        const sId = document.getElementById('usage_surowiec_id').value;
        const qVal = document.getElementById('usage_ilosc').value;
        const pId = document.getElementById('usage_plan_id').value;
        const nVal = document.getElementById('usage_komentarz').value;
        const zbVal = document.getElementById('usage_zbiornik').value.trim();
        if (!sId || !qVal) return showAlert("Wypełnij wszystkie pola!");
        apiCall('/agro/api/usage', { surowiec_id: sId, ilosc: qVal, plan_id: pId, komentarz: nVal, zbiornik: zbVal || null, linia: CONFIG.linia });
    };

    // QR SCANNER
    var _qrTargetFieldId = null;
    window.openQrScanner = function(targetFieldId) {
        _qrTargetFieldId = targetFieldId;
        const inp = document.getElementById('qrScanInput');
        inp.value = '';
        document.getElementById('qrConfirmBtn').disabled = true;
        openModal('modalQr');
        setTimeout(() => inp.focus(), 80);
    };

    window.closeQrScanner = function() { closeModal('modalQr'); };

    document.addEventListener('DOMContentLoaded', function() {
        const inp = document.getElementById('qrScanInput');
        if (!inp) return;
        inp.addEventListener('input', () => {
            const val = inp.value.trim().toUpperCase();
            inp.value = val;
            document.getElementById('qrConfirmBtn').disabled = val.length === 0;
        });
        inp.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = inp.value.trim().toUpperCase();
                if (val) applyQrResult(val);
            }
        });
    });

    function applyQrResult(val) {
        closeQrScanner();
        if (!_qrTargetFieldId || !val) return;
        if (_qrTargetFieldId === 'usage_location_scan') {
            const sel = document.getElementById('usage_surowiec_id');
            let matched = false;
            for (let i = 0; i < sel.options.length; i++) {
                if (sel.options[i].textContent.toUpperCase().indexOf(val) !== -1) {
                    sel.selectedIndex = i;
                    matched = true;
                    break;
                }
            }
            if (!matched) showAlert('Nie znaleziono palety dla lokalizacji: ' + val);
        } else {
            const el = document.getElementById(_qrTargetFieldId);
            if (el) { el.value = val; el.dispatchEvent(new Event('input')); }
        }
    }

    window.confirmQrManual = function() {
        const val = document.getElementById('qrScanInput').value.trim().toUpperCase();
        if (val) applyQrResult(val);
    };

    // RETURN & ISSUE
    window.openReturnFor = function(id, nazwa, lok) {
        openReturnModal();
    };

    window.openReturnModal = function(preselect_ruch_id) {
        const formSection = document.getElementById('returnFormSection');
        if (formSection) formSection.style.display = 'none';
        const btn = document.getElementById('btnSubmitReturn');
        if (btn) btn.disabled = true;
        const body = document.getElementById('returnItemsBody');
        if (body) body.innerHTML = '<tr><td colspan="8" class="text-center text-muted">Ładowanie...</td></tr>';
        openModal('modalReturn');
        fetch(`/agro/api/production_items_for_return?linia=${CONFIG.linia}`)
            .then(r => r.json())
            .then(res => {
                if (!res.success) return showAlert('Błąd: ' + (res.error || 'Nieznany'));
                window._returnItems = res.items;
                renderReturnItems(res.items, preselect_ruch_id);
            }).catch(e => { console.error(e); showAlert('Błąd połączenia'); });
    };

    function renderReturnItems(items, preselect_ruch_id) {
        const body = document.getElementById('returnItemsBody');
        if (!body) return;
        body.innerHTML = '';
        if (!items || items.length === 0) {
            body.innerHTML = '<tr><td colspan="8" class="text-center text-muted">Brak pozycji do zwrotu</td></tr>';
            return;
        }
        items.forEach(function(it) {
            const tr = document.createElement('tr');
            tr.style.cursor = 'pointer';
            tr.innerHTML = `
                <td><input type="radio" name="return_select" value="${it.ruch_id}" data-sid="${it.surowiec_id}" data-plan="${it.plan_id||''}" data-max="${it.do_zwrotu}" data-nazwa="${it.nazwa||''}" data-lok="${it.lokalizacja||''}"></td>
                <td>${it.nazwa || ''}</td>
                <td>${it.lokalizacja || '<span class="text-muted">—</span>'}</td>
                <td class="font-bold">${it.ilosc_pobrana}</td>
                <td>${it.ilosc_zwrocona}</td>
                <td class="font-bold text-primary">${it.do_zwrotu}</td>
                <td>${it.plan_name ? it.plan_name + ' (#' + it.plan_id + ')' : (it.plan_id || '—')}</td>
                <td class="text-muted small">${it.data || ''}</td>
            `;
            tr.addEventListener('click', function(e) {
                if (e.target.tagName !== 'INPUT') {
                    const radio = tr.querySelector('input[type=radio]');
                    radio.checked = true;
                    selectReturnItem(radio);
                }
            });
            body.appendChild(tr);
        });

        body.querySelectorAll('input[name=return_select]').forEach(radio => {
            radio.addEventListener('change', () => selectReturnItem(radio));
        });

        if (preselect_ruch_id) {
            const preRadio = body.querySelector('input[value="' + preselect_ruch_id + '"]');
            if (preRadio) { preRadio.checked = true; selectReturnItem(preRadio); }
        }
    }

    function selectReturnItem(radio) {
        document.getElementById('return_ruch_id').value = radio.value;
        document.getElementById('return_surowiec_id').value = radio.dataset.sid;
        document.getElementById('return_plan_id').value = radio.dataset.plan || '';
        document.getElementById('return_lokalizacja').value = radio.dataset.lok || '';
        const maxQty = parseFloat(radio.dataset.max) || 0;
        document.getElementById('return_ilosc').value = maxQty;
        document.getElementById('return_ilosc').max = maxQty;
        document.getElementById('returnMaxHint').textContent = 'Max: ' + maxQty + ' kg';
        document.getElementById('return_komentarz').value = '';
        document.getElementById('returnFormSection').style.display = '';
        document.getElementById('btnSubmitReturn').disabled = false;
    }

    window.submitReturn = function() {
        const data = {
            ruch_produkcja_id: document.getElementById('return_ruch_id').value,
            surowiec_id: document.getElementById('return_surowiec_id').value,
            ilosc: document.getElementById('return_ilosc').value,
            plan_id: document.getElementById('return_plan_id').value || null,
            komentarz: document.getElementById('return_komentarz').value,
            lokalizacja: document.getElementById('return_lokalizacja').value.trim(),
            linia: CONFIG.linia
        };
        if (!data.surowiec_id || !data.ilosc || parseFloat(data.ilosc) <= 0) return showAlert("Podaj ilość zwrotu!");
        apiCall('/agro/api/return', data);
    };

    window.openIssueWarehouseFor = function(id, nazwa) {
        const sel = document.getElementById('issuew_surowiec_id');
        if (sel) sel.value = id;
        document.getElementById('issuew_ilosc').value = '';
        document.getElementById('issuew_komentarz').value = '';
        openModal('modalIssueWarehouse');
    };

    window.submitIssueWarehouse = function() {
        const data = {
            surowiec_id: document.getElementById('issuew_surowiec_id').value,
            ilosc: document.getElementById('issuew_ilosc').value,
            komentarz: document.getElementById('issuew_komentarz').value,
            linia: CONFIG.linia
        };
        if (!data.surowiec_id || !data.ilosc || parseFloat(data.ilosc) <= 0) return showAlert("Wypełnij wszystkie pola!");
        apiCall('/agro/api/issue_warehouse', data);
    };

    // BULK INVENTORY
    window.openBulkInventoryModal = function() {
        document.getElementById('bulkInvBody').innerHTML = '<tr><td colspan="5" class="text-center text-muted">Ładowanie...</td></tr>';
        document.getElementById('bulkInvFilter').value = '';
        openModal('modalBulkInventory');
        fetch(`/agro/api/locations_inventory?linia=${CONFIG.linia}`)
            .then(r => r.json())
            .then(res => {
                if (!res.success) return showAlert('Błąd: ' + (res.error || 'Nieznany'));
                window._bulkInvItems = res.items;
                renderBulkInventory(res.items);
            }).catch(e => { console.error(e); showAlert('Błąd połączenia'); });
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

    window.submitBulkInventory = function() {
        const inputs = document.querySelectorAll('.bulk-inv-qty');
        const items = [];
        inputs.forEach(function(inp) {
            const id = inp.dataset.id;
            const orig = window._bulkInvItems.find(x => String(x.id) === String(id));
            const newVal = parseFloat(inp.value);
            if (orig && !isNaN(newVal) && newVal !== orig.stan_magazynowy) {
                items.push({ surowiec_id: id, actual_qty: newVal, komentarz: 'Inwentaryzacja zbiorcza' });
            }
        });
        if (items.length === 0) return showAlert('Brak zmian do zapisania.');
        if (!confirm('Zapisać ' + items.length + ' zmian(y) w inwentaryzacji?')) return;
        fetch('/agro/api/bulk_inventory', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ items: items, linia: CONFIG.linia })
        }).then(r => r.json()).then(res => {
            if (res.success) { showAlert('Zaktualizowano ' + (res.updated || 0) + ' pozycji.'); location.reload(); }
            else showAlert('Błąd: ' + (res.error || 'Nieznany'));
        }).catch(e => { console.error(e); showAlert('Błąd połączenia'); });
    };

    window.submitInventory = function() {
        const data = {
            surowiec_id: document.getElementById('inv_surowiec_id').value,
            actual_qty: document.getElementById('inv_qty').value,
            komentarz: document.getElementById('inv_komentarz').value,
            linia: CONFIG.linia
        };
        if (!data.surowiec_id || data.actual_qty === "") return showAlert("Wypełnij wszystkie pola!");
        apiCall('/agro/api/inventory', data);
    };
