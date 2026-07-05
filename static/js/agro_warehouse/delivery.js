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
            apiCall('/agro/api/delivery', { items: items, linia: AGRO_CONFIG.linia });
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
                body: JSON.stringify({ nazwa: nazwa, linia: AGRO_CONFIG.linia })
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
        apiCall('/agro/api/confirm', { ruch_id: rId, lokalizacja: locVal, linia: AGRO_CONFIG.linia });
    };

