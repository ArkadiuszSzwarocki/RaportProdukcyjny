(function() {
    function initAgroRozliczenie() {
        var formEl = document.getElementById('form-rozliczenie-agro');
        if (!formEl) return; // Brak panelu rozliczenia na stronie

        var sel = document.getElementById('wri_opak');
        var stanEl = document.getElementById('wri_stan');
        var stanPoEl = document.getElementById('wri-stan-po');
        var zuzyteEl = document.getElementById('wri-zuzyte');
        var wriWyprod = document.getElementById('wri_wyprod');
        var wriRoznica = document.getElementById('wri-roznica');
        
        var autoUsed = Number(formEl.getAttribute('data-estimated-bags')) || 0;
        var planId = formEl.getAttribute('data-plan-id');
        var draftKey = 'agro_rozliczenie_draft_' + planId;

        // Ładowanie zapisanych wartości z LocalStorage
        function loadDraft() {
            try {
                var draft = localStorage.getItem(draftKey);
                if (draft) {
                    var data = JSON.parse(draft);
                    if (sel && data.opakowanie_id) sel.value = data.opakowanie_id;
                    if (wriWyprod && data.wyprodukowano_szt) wriWyprod.value = data.wyprodukowano_szt;
                }
            } catch (e) { console.error('Błąd wczytywania draftu', e); }
        }

        // Zapisywanie aktualnych wartości do LocalStorage
        function saveDraft() {
            try {
                var data = {
                    opakowanie_id: sel ? sel.value : '',
                    wyprodukowano_szt: wriWyprod ? wriWyprod.value : ''
                };
                localStorage.setItem(draftKey, JSON.stringify(data));
            } catch (e) { console.error('Błąd zapisu draftu', e); }
        }

        function refresh() {
            if (!sel) return;
            var opt = sel.options[sel.selectedIndex];
            if (!opt || !opt.value) {
                if (stanEl) stanEl.value = '-';
                if (stanPoEl) stanPoEl.textContent = '-';
                if (zuzyteEl) zuzyteEl.textContent = String(Math.round(autoUsed));
            } else {
                var stock = Number(opt.getAttribute('data-stock') || 0);
                var after = stock - autoUsed;
                if (stanEl) stanEl.value = String(Math.round(stock));
                if (stanPoEl) {
                    stanPoEl.textContent = String(Math.round(after));
                    stanPoEl.style.color = after < 0 ? '#c53030' : '';
                }
                if (zuzyteEl) zuzyteEl.textContent = String(Math.round(autoUsed));
            }
            
            if (wriWyprod && wriRoznica) {
                var wpisane = Number(wriWyprod.value) || 0;
                if (wpisane > 0) {
                    var roznica = wpisane - autoUsed;
                    wriRoznica.textContent = String(Math.round(roznica)) + ' szt.';
                } else {
                    wriRoznica.textContent = '-';
                }
            }
            saveDraft();
        }
        
        // Inicjalizacja
        loadDraft();
        
        if(sel) sel.addEventListener('change', refresh);
        if(wriWyprod) wriWyprod.addEventListener('input', refresh);
        
        refresh();
        
        // Automatyczny zapis po kliknięciu STOP (ikona na karcie produkcyjnej)
        document.body.addEventListener('click', function(e) {
            var stopBtn = e.target.closest('.btn-stop-icon');
            if(stopBtn) {
                var form = document.getElementById('form-rozliczenie-agro');
                var selCheck = document.getElementById('wri_opak');
                if(form && selCheck && selCheck.value) {
                    var formData = new FormData(form);
                    fetch(form.action, {
                        method: 'POST',
                        body: formData,
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    }).then(function(res) {
                        if(res.ok) { localStorage.removeItem(draftKey); }
                    }).catch(console.error);
                }
            }
        }, true);
        
        // Usunięcie draftu po zwykłym wysłaniu formularza (jeśli jest triggerowane ręcznie)
        if (formEl) {
            formEl.addEventListener('submit', function() {
                localStorage.removeItem(draftKey);
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAgroRozliczenie);
    } else {
        initAgroRozliczenie();
    }
})();
