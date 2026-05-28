/**
 * Dashboard Packaging Management Logic
 * Handles linking and returning packaging materials on Zebra terminals.
 */

function linkPackaging(opakId, planId) {
    const select = document.getElementById('select_warehouse_packaging');
    if (!select) return;
    const option = select.options[select.selectedIndex];
    if (!option || !option.value) {
        alert('Proszę wybrać materiał!');
        return;
    }
    const name = option.getAttribute('data-nazwa') || option.text;
    const stan = parseFloat(option.getAttribute('data-stan') || 0);
    const lok = option.getAttribute('data-lokalizacja') || '';

    // Remove any existing overlay
    var existing = document.getElementById('link-packaging-overlay');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.id = 'link-packaging-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:20000;display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;';

    var panel = document.createElement('div');
    panel.style.cssText = 'width:100%;max-width:440px;background:#fff;border-radius:12px;box-shadow:0 18px 40px rgba(0,0,0,0.28);padding:20px;box-sizing:border-box;';

    var title = document.createElement('h3');
    title.textContent = 'Pobranie materiału na maszynę';
    title.style.cssText = 'margin:0 0 4px 0;font-size:1.15rem;color:#102a43;font-weight:700;box-sizing:border-box;';

    var desc = document.createElement('p');
    desc.innerHTML = `Materiał: <strong>${name}</strong><br>Lokalizacja: <strong>${lok || '-'}</strong> | Stan: <strong>${stan} szt/kg</strong>`;
    desc.style.cssText = 'margin:0 0 16px 0;font-size:0.9rem;color:#334e68;line-height:1.4;box-sizing:border-box;';

    // Total quantity field
    var qtyLabel = document.createElement('label');
    qtyLabel.textContent = 'Ilość do pobrania (szt / kg):';
    qtyLabel.style.cssText = 'display:block;margin-bottom:6px;font-weight:600;color:#102a43;font-size:0.9rem;box-sizing:border-box;';

    var qtyInput = document.createElement('input');
    qtyInput.type = 'number';
    qtyInput.placeholder = `Całość (${stan})`;
    qtyInput.style.cssText = 'width:100%;padding:10px;border:1px solid #bcccdc;border-radius:8px;margin-bottom:14px;box-sizing:border-box;font-size:1rem;';

    // Calculator section (Rolls / Packs)
    var calcBox = document.createElement('div');
    calcBox.style.cssText = 'background:#f0f4f8;border:1px solid #d9e2ec;border-radius:8px;padding:12px;margin-bottom:16px;box-sizing:border-box;';

    var calcTitle = document.createElement('div');
    calcTitle.textContent = '🧮 Kalkulator rolek / paczek (opcjonalny):';
    calcTitle.style.cssText = 'font-weight:700;color:#102a43;font-size:0.85rem;margin-bottom:8px;box-sizing:border-box;';

    var calcInputs = document.createElement('div');
    calcInputs.style.cssText = 'display:flex;gap:8px;box-sizing:border-box;';

    var rollsCol = document.createElement('div');
    rollsCol.style.cssText = 'flex:1;box-sizing:border-box;';
    var rollsLabel = document.createElement('div');
    rollsLabel.textContent = 'Liczba rolek/paczek';
    rollsLabel.style.cssText = 'font-size:0.75rem;color:#486581;margin-bottom:4px;';
    var rollsInput = document.createElement('input');
    rollsInput.type = 'number';
    rollsInput.placeholder = 'np. 6';
    rollsInput.style.cssText = 'width:100%;padding:6px 8px;border:1px solid #bcccdc;border-radius:6px;box-sizing:border-box;font-size:0.88rem;';

    var sizeCol = document.createElement('div');
    sizeCol.style.cssText = 'flex:1;box-sizing:border-box;';
    var sizeLabel = document.createElement('div');
    sizeLabel.textContent = 'Sztuk w rolce/paczce';
    sizeLabel.style.cssText = 'font-size:0.75rem;color:#486581;margin-bottom:4px;';
    var sizeInput = document.createElement('input');
    sizeInput.type = 'number';
    sizeInput.placeholder = 'np. 700';
    sizeInput.style.cssText = 'width:100%;padding:6px 8px;border:1px solid #bcccdc;border-radius:6px;box-sizing:border-box;font-size:0.88rem;';

    rollsCol.appendChild(rollsLabel);
    rollsCol.appendChild(rollsInput);
    sizeCol.appendChild(sizeLabel);
    sizeCol.appendChild(sizeInput);
    calcInputs.appendChild(rollsCol);
    calcInputs.appendChild(sizeCol);
    calcBox.appendChild(calcTitle);
    calcBox.appendChild(calcInputs);

    // Auto-calculate listener
    function updateFromCalc() {
        var r = parseFloat(rollsInput.value || 0);
        var s = parseFloat(sizeInput.value || 0);
        if (r > 0 && s > 0) {
            qtyInput.value = r * s;
        }
    }
    rollsInput.addEventListener('input', updateFromCalc);
    sizeInput.addEventListener('input', updateFromCalc);

    var errorBox = document.createElement('div');
    errorBox.style.cssText = 'min-height:18px;color:#c81e1e;font-size:0.85rem;margin-bottom:12px;box-sizing:border-box;';

    var actions = document.createElement('div');
    actions.style.cssText = 'display:flex;justify-content:flex-end;gap:8px;box-sizing:border-box;';

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Anuluj';
    cancelBtn.style.cssText = 'border:1px solid #9fb3c8;background:#fff;color:#334e68;border-radius:8px;padding:8px 14px;font-weight:600;cursor:pointer;';

    var confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.textContent = 'Podepnij';
    confirmBtn.style.cssText = 'border:1px solid #0f609b;background:#127fbf;color:#fff;border-radius:8px;padding:8px 14px;font-weight:700;cursor:pointer;';

    cancelBtn.addEventListener('click', function() {
        overlay.remove();
    });

    confirmBtn.addEventListener('click', function() {
        var qtyVal = qtyInput.value.trim();
        var finalQty = null;
        if (qtyVal !== '') {
            finalQty = parseFloat(qtyVal);
            if (isNaN(finalQty) || finalQty <= 0) {
                errorBox.textContent = 'Wprowadź prawidłową ilość do pobrania.';
                return;
            }
        }

        overlay.remove();
        
        fetch('/agro/api/opakowania/link', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ opakowanie_id: opakId, plan_id: planId, ilosc_pobrana: finalQty })
        }).then(r => r.json()).then(res => {
            if(res.success) location.reload();
            else alert('Błąd: ' + (res.error || 'Nieznany'));
        }).catch(err => alert('Błąd połączenia: ' + err));
    });

    overlay.addEventListener('click', function(event) {
        if (event.target === overlay) {
            overlay.remove();
        }
    });

    actions.appendChild(cancelBtn);
    actions.appendChild(confirmBtn);

    panel.appendChild(title);
    panel.appendChild(desc);
    panel.appendChild(qtyLabel);
    panel.appendChild(qtyInput);
    panel.appendChild(calcBox);
    panel.appendChild(errorBox);
    panel.appendChild(actions);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    qtyInput.focus();
}

function openReturnPackagingModal(id, nazwa, stan) {
    const modal = document.getElementById('returnPackagingModal');
    if (!modal) return;
    
    document.getElementById('returnOpakId').value = id;
    document.getElementById('returnOpakName').innerText = nazwa;
    document.getElementById('returnOpakQty').value = stan;
    document.getElementById('returnOpakLoc').value = '';
    
    if (typeof modal.showModal === 'function') {
        modal.showModal();
    } else {
        modal.style.display = 'block';
    }
}

function closeReturnModal() {
    const modal = document.getElementById('returnPackagingModal');
    if (!modal) return;
    
    if (typeof modal.close === 'function') {
        modal.close();
    } else {
        modal.style.display = 'none';
    }
}

function submitReturnPackaging() {
    const id = document.getElementById('returnOpakId').value;
    let qty = document.getElementById('returnOpakQty').value;
    const loc = document.getElementById('returnOpakLoc').value.trim();
    
    if(!qty || qty.trim() === '') qty = "0";
    if(parseFloat(qty) > 0 && !loc) return alert('Podaj lokalizację zwrotu!');
    
    fetch('/agro/api/opakowania/return', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ opakowanie_id: id, stan_po: qty, lokalizacja: loc })
    }).then(r => r.json()).then(res => {
        if(res.success) location.reload();
        else alert('Błąd: ' + (res.error || 'Nieznany'));
    }).catch(err => alert('Błąd połączenia: ' + err));
}

function undoPackagingLink(linkId) {
    if(!confirm('Czy na pewno chcesz cofnąć podpięcie tego opakowania? Opcja ta usunie to powiązanie.')) return;
    fetch('/agro/api/opakowania/undo_link', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ link_id: linkId })
    }).then(r => r.json()).then(res => {
        if(res.success) location.reload();
        else alert('Błąd: ' + (res.error || 'Nieznany'));
    }).catch(err => alert('Błąd połączenia: ' + err));
}

function undoPackagingReturn(linkId) {
    if(!confirm('Czy na pewno chcesz cofnąć zwrot tego opakowania? Opcja ta przywróci je na maszynę oraz cofnie stan magazynowy.')) return;
    fetch('/agro/api/opakowania/undo_return', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ link_id: linkId })
    }).then(r => r.json()).then(res => {
        if(res.success) location.reload();
        else alert('Błąd: ' + (res.error || 'Nieznany'));
    }).catch(err => alert('Błąd połączenia: ' + err));
}

