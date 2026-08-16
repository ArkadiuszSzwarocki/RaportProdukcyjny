
    // ---- ALERT HELPER (używa toast jeśli dostępny, fallback na alert) ----
    window.showAlert = function(msg) {
        if (typeof window.showToast === 'function') {
            window.showToast(String(msg), 'warning');
        } else {
            alert(msg);
        }
    };

    window.initWarehouse = function(config) {
        Object.assign(CONFIG, config);
        window._current_plan = { id: AGRO_CONFIG.current_plan_id, name: AGRO_CONFIG.current_plan_name };
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

    function ensureInventorySelectOptions(selectId) {
        const sel = document.getElementById(selectId);
        if (!sel || sel.options.length) return sel;

        (window._inventory || []).forEach(function(s) {
            const o = document.createElement('option');
            o.value = s.id;
            const labelName = s.parent_nazwa || s.nazwa || 'Surowiec';
            const labelLoc = s.lokalizacja || 'Brak';
            const labelQty = (typeof s.stan !== 'undefined' ? s.stan : (s.stan_magazynowy || 0));
            o.textContent = labelName + ' - ' + labelLoc + ' (' + labelQty + ' kg)';
            sel.appendChild(o);
        });

        return sel;
    }

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

