    window.openUsageFor = function(id, nazwa, lok, qty) {
        const sel = ensureInventorySelectOptions('usage_surowiec_id');
        if (!sel) {
            showAlert('Brak listy palet do pobrania.');
            return;
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
                fetch(`/agro/api/current_plan?linia=${AGRO_CONFIG.linia}`).then(r => r.json()).then(res => {
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

    window.submitUsage = function() {
        const sId = document.getElementById('usage_surowiec_id').value;
        const qVal = document.getElementById('usage_ilosc').value;
        const pId = document.getElementById('usage_plan_id').value;
        const nVal = document.getElementById('usage_komentarz').value;
        const zbVal = document.getElementById('usage_zbiornik').value.trim();
        if (!sId || !qVal) return showAlert("Wypełnij wszystkie pola!");
        apiCall('/agro/api/usage', { surowiec_id: sId, ilosc: qVal, plan_id: pId, komentarz: nVal, zbiornik: zbVal || null, linia: AGRO_CONFIG.linia });
    };

    // QR SCANNER
    var _qrTargetFieldId = null;
