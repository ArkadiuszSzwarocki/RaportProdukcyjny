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
            body: JSON.stringify({ surowiec_id: id, new_name: newName, komentarz: koment, linia: AGRO_CONFIG.linia })
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
        fetch(`/agro/api/production_moves?linia=${AGRO_CONFIG.linia}&limit=` + limit)
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

    window.openIssueWarehouseFor = function(id, nazwa) {
        const sel = ensureInventorySelectOptions('issuew_surowiec_id');
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
            linia: AGRO_CONFIG.linia
        };
        if (!data.surowiec_id || !data.ilosc || parseFloat(data.ilosc) <= 0) return showAlert("Wypełnij wszystkie pola!");
        apiCall('/agro/api/issue_warehouse', data);
    };

    // BULK INVENTORY
