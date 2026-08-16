/**
 * Dashboard Packaging Management Logic
 * Handles linking and returning packaging materials on Zebra terminals.
 */

function linkPackaging(opakId, planId) {
    const select = document.getElementById('select_warehouse_packaging');
    if (!select) return;
    const option = select.options[select.selectedIndex];
    if (!option || !option.value) {
        if (typeof AppDialog !== 'undefined') AppDialog.alert('Proszę wybrać materiał!'); else alert('Proszę wybrać materiał!');
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

    // First field: Meters Input
    var metersLabel = document.createElement('label');
    metersLabel.textContent = 'Ilość pobranej folii (METRY):';
    metersLabel.style.cssText = 'display:block;margin-bottom:6px;font-weight:600;color:#102a43;font-size:0.9rem;box-sizing:border-box;';

    var metersInput = document.createElement('input');
    metersInput.type = 'number';
    metersInput.step = 'any';
    metersInput.placeholder = 'np. 50';
    metersInput.style.cssText = 'width:100%;padding:10px;border:1px solid #bcccdc;border-radius:8px;margin-bottom:14px;box-sizing:border-box;font-size:1rem;background:#f0f4f8;';

    // Second field: Pieces Input
    var qtyLabel = document.createElement('label');
    qtyLabel.textContent = 'Przeliczone sztuki na maszynę (worek to 0.842m):';
    qtyLabel.style.cssText = 'display:block;margin-bottom:6px;font-weight:600;color:#486581;font-size:0.85rem;box-sizing:border-box;';

    var qtyInput = document.createElement('input');
    qtyInput.type = 'number';
    qtyInput.step = 'any';
    qtyInput.placeholder = `Całość (${stan})`;
    qtyInput.style.cssText = 'width:100%;padding:10px;border:1px solid #bcccdc;border-radius:8px;margin-bottom:14px;box-sizing:border-box;font-size:1rem;';

    metersInput.addEventListener('input', function() {
        var m = parseFloat(metersInput.value || 0);
        if (m > 0) {
            qtyInput.value = Math.round(m / 0.842);
        } else {
            qtyInput.value = '';
        }
    });

    qtyInput.addEventListener('input', function() {
        var q = parseFloat(qtyInput.value || 0);
        if (q > 0) {
            metersInput.value = (q * 0.842).toFixed(2);
        } else {
            metersInput.value = '';
        }
    });

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
            else if (typeof AppDialog !== 'undefined') AppDialog.alert('Błąd: ' + (res.error || 'Nieznany')); else alert('Błąd: ' + (res.error || 'Nieznany'));
        }).catch(err => { if (typeof AppDialog !== 'undefined') AppDialog.alert('Błąd połączenia: ' + err); else alert('Błąd połączenia: ' + err); });
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
    panel.appendChild(metersLabel);
    panel.appendChild(metersInput);
    panel.appendChild(qtyLabel);
    panel.appendChild(qtyInput);
    panel.appendChild(errorBox);
    panel.appendChild(actions);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    qtyInput.focus();
}

function updateReturnModalUI() {
    const radios = document.getElementsByName('returnType');
    let type = 'partial';
    for(let i=0; i<radios.length; i++){
        if(radios[i].checked) type = radios[i].value;
    }
    
    const label = document.getElementById('returnOpakQtyLabel');
    const qtyInput = document.getElementById('returnOpakQty');
    
    if (type === 'partial') {
        label.innerText = 'Ile sztuk odkładasz na magazyn?';
        qtyInput.value = '';
    } else {
        label.innerText = 'Ile sztuk zostało na całej odkładanej rolce?';
        if (qtyInput.dataset.stan) {
            qtyInput.value = qtyInput.dataset.stan;
        }
    }
}

function openReturnPackagingModal(id, nazwa, stan, suggestedLoc) {
    const modal = document.getElementById('returnPackagingModal');
    if (!modal) return;
    document.getElementById('returnOpakId').value = id;
    document.getElementById('returnOpakName').innerText = nazwa;
    
    // Store stan globally or in a data attribute
    const qtyInput = document.getElementById('returnOpakQty');
    qtyInput.dataset.stan = stan;
    
    // Default to partial return
    const radios = document.getElementsByName('returnType');
    for (let i = 0; i < radios.length; i++) {
        if (radios[i].value === 'partial') {
            radios[i].checked = true;
        }
    }
    updateReturnModalUI();
    
    const locInput = document.getElementById('returnOpakLoc');
    locInput.value = suggestedLoc || '';
    if (suggestedLoc) {
        locInput.placeholder = "Sugerowana: " + suggestedLoc;
    } else {
        locInput.placeholder = "Wpisz kod, np. MOP01";
    }

    const printCheckbox = document.getElementById('returnOpakPrintLabel');
    if (printCheckbox) {
        printCheckbox.checked = true;
    }
    
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
    const printCheckbox = document.getElementById('returnOpakPrintLabel');
    const shouldPrintLabel = !printCheckbox || !!printCheckbox.checked;
    
    const typeNode = document.querySelector('input[name="returnType"]:checked');
    const isPartial = typeNode && typeNode.value === 'partial';
    
    if(!qty || qty.trim() === '') qty = "0";
    if(parseFloat(qty) > 0 && !loc) return (typeof AppDialog !== 'undefined' ? AppDialog.alert('Podaj lokalizację zwrotu!') : alert('Podaj lokalizację zwrotu!'));
    
    fetch('/agro/api/opakowania/return', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            opakowanie_id: id,
            stan_po: qty,
            lokalizacja: loc,
            is_partial: isPartial,
            print_label: shouldPrintLabel,
        })
    }).then(r => r.json()).then(res => {
        if (!res.success) {
            if (typeof AppDialog !== 'undefined') AppDialog.alert('Błąd: ' + (res.error || 'Nieznany')); else alert('Błąd: ' + (res.error || 'Nieznany'));
            return;
        }

        const printResult = res.print_result || null;
        if (printResult && printResult.requested) {
            if (printResult.success) {
                if (typeof showToast === 'function') {
                    showToast('Zwrot zapisany. Etykieta informacyjna wydrukowana.', 'success');
                }
            } else {
                const warnMsg = 'Zwrot zapisany, ale wydruk etykiety nie powiódł się: ' + (printResult.message || 'Nieznany błąd');
                if (typeof showToast === 'function') {
                    showToast(warnMsg, 'warning');
                } else if (typeof AppDialog !== 'undefined') {
                    AppDialog.alert(warnMsg);
                } else {
                    alert(warnMsg);
                }
            }
        } else if (typeof showToast === 'function') {
            showToast('Zwrot zapisany.', 'success');
        }

        setTimeout(() => location.reload(), 450);
    }).catch(err => alert('Błąd połączenia: ' + err));
}

function reprintLastReturnPackagingLabel(btn) {
    const triggerBtn = btn && btn.tagName ? btn : null;
    const originalText = triggerBtn ? triggerBtn.innerText : '';

    if (triggerBtn) {
        triggerBtn.disabled = true;
        triggerBtn.innerText = 'DRUKOWANIE...';
    }

    fetch('/agro/api/opakowania/reprint_last_return_label', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
    }).then(r => r.json()).then(res => {
        if (res.success) {
            if (typeof showToast === 'function') {
                showToast('Ponowiono wydruk etykiety ostatniego zwrotu.', 'success');
            }
            return;
        }

        const msg = res.error || res.message || 'Nie udało się ponowić wydruku.';
        if (typeof showToast === 'function') {
            showToast(msg, 'warning');
        } else {
            alert(msg);
        }
    }).catch(err => {
        alert('Błąd połączenia: ' + err);
    }).finally(() => {
        if (triggerBtn) {
            triggerBtn.disabled = false;
            triggerBtn.innerText = originalText;
        }
    });
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

