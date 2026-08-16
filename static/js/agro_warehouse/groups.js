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

