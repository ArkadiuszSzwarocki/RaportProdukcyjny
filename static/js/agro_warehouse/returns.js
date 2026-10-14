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
        fetch(`/agro/api/production_items_for_return?linia=${AGRO_CONFIG.linia}`)
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
                <td><input type="radio" name="return_select" value="${agroEscapeHtml(it.ruch_id)}" data-sid="${agroEscapeHtml(it.surowiec_id)}" data-plan="${agroEscapeHtml(it.plan_id||'')}" data-max="${agroEscapeHtml(it.do_zwrotu)}" data-nazwa="${agroEscapeHtml(it.nazwa||'')}" data-lok="${agroEscapeHtml(it.lokalizacja||'')}"></td>
                <td>${agroEscapeHtml(it.nazwa || '')}</td>
                <td>${agroEscapeHtml(it.lokalizacja || '—')}</td>
                <td class="font-bold">${agroEscapeHtml(it.ilosc_pobrana)}</td>
                <td>${agroEscapeHtml(it.ilosc_zwrocona)}</td>
                <td class="font-bold text-primary">${agroEscapeHtml(it.do_zwrotu)}</td>
                <td>${agroEscapeHtml(it.plan_name ? it.plan_name + ' (#' + it.plan_id + ')' : (it.plan_id || '—'))}</td>
                <td class="text-muted small">${agroEscapeHtml(it.data || '')}</td>
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
            linia: AGRO_CONFIG.linia
        };
        if (!data.surowiec_id || !data.ilosc || parseFloat(data.ilosc) <= 0) return showAlert("Podaj ilość zwrotu!");
        apiCall('/agro/api/return', data);
    };

