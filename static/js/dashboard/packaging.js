/**
 * Dashboard Packaging Management Logic
 * Handles linking and returning packaging materials on Zebra terminals.
 */

function linkPackaging(opakId, planId) {
    if(!confirm('Czy na pewno podpiąć to opakowanie pod aktualne zlecenie?')) return;
    fetch('/agro/api/opakowania/link', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ opakowanie_id: opakId, plan_id: planId })
    }).then(r => r.json()).then(res => {
        if(res.success) {
            if (typeof window.performPartialReload === 'function') {
                window.performPartialReload();
            } else {
                location.reload();
            }
        }
        else alert('Błąd: ' + (res.error || 'Nieznany'));
    }).catch(err => alert('Błąd połączenia: ' + err));
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
        if(res.success) {
            closeReturnModal();
            if (typeof window.performPartialReload === 'function') {
                window.performPartialReload();
            } else {
                location.reload();
            }
        }
        else alert('Błąd: ' + (res.error || 'Nieznany'));
    }).catch(err => alert('Błąd połączenia: ' + err));
}

function openLinkPackagingModal(id, nazwa, stan, planId) {
    const modal = document.getElementById('linkPackagingModal');
    if (!modal) return;
    
    document.getElementById('linkOpakId').value = id;
    document.getElementById('linkPlanId').value = planId;
    document.getElementById('linkOpakName').innerText = "Pobierasz: " + nazwa;
    document.getElementById('linkOpakStockInfo').innerText = "Dostępny stan w magazynie: " + stan + " szt.";
    document.getElementById('linkOpakQty').value = '';
    document.getElementById('linkOpakQty').max = stan;
    
    if (typeof modal.showModal === 'function') {
        modal.showModal();
    } else {
        modal.style.display = 'block';
    }
}

function closeLinkModal() {
    const modal = document.getElementById('linkPackagingModal');
    if (!modal) return;
    
    if (typeof modal.close === 'function') {
        modal.close();
    } else {
        modal.style.display = 'none';
    }
}

function submitLinkPackaging() {
    const id = document.getElementById('linkOpakId').value;
    const planId = document.getElementById('linkPlanId').value;
    const qty = document.getElementById('linkOpakQty').value;
    
    fetch('/agro/api/opakowania/link', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ opakowanie_id: id, plan_id: planId, pobrana_ilosc: qty })
    }).then(r => r.json()).then(res => {
        if(res.success) {
            closeLinkModal();
            if (typeof window.performPartialReload === 'function') {
                window.performPartialReload();
            } else {
                location.reload();
            }
        }
        else alert('Błąd: ' + (res.error || 'Nieznany'));
    }).catch(err => alert('Błąd połączenia: ' + err));
}

function undoPackagingPull(linkId, nazwa, stanPoczatkowy) {
    if(!confirm(`Czy na pewno chcesz cofnąć to pobranie?\n\nPobrana ilość (${stanPoczatkowy} szt.) materiału "${nazwa}" zostanie zwrócona z powrotem do magazynu.`)) return;
    
    fetch('/agro/api/opakowania/undo', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ link_id: linkId })
    }).then(r => r.json()).then(res => {
        if(res.success) {
            if (typeof window.performPartialReload === 'function') {
                window.performPartialReload();
            } else {
                location.reload();
            }
        } else {
            alert('Błąd: ' + (res.error || 'Nieznany'));
        }
    }).catch(err => alert('Błąd połączenia: ' + err));
}

function undoPackagingReturn(linkId, nazwa, stanPo) {
    if(!confirm(`Czy na pewno chcesz cofnąć to zdjęcie/zwrot?\n\nMateriał "${nazwa}" wróci na maszynę jako aktywny, a ilość zwrócona (${stanPo} szt.) zostanie odjęta z magazynu.`)) return;
    
    fetch('/agro/api/opakowania/undo_return', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ link_id: linkId })
    }).then(r => r.json()).then(res => {
        if(res.success) {
            if (typeof window.performPartialReload === 'function') {
                window.performPartialReload();
            } else {
                location.reload();
            }
        } else {
            alert('Błąd: ' + (res.error || 'Nieznany'));
        }
    }).catch(err => alert('Błąd połączenia: ' + err));
}
