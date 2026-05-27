/**
 * Dashboard Packaging Management Logic
 * Handles linking and returning packaging materials on Zebra terminals.
 */

function linkPackaging(opakId, planId) {
    const qtyInput = prompt('Podaj ilość do pobrania na maszynę (np. 700). Zostaw puste, aby pobrać całą paletę/paczkę:');
    if (qtyInput === null) return; // User cancelled
    
    let iloscPobrana = null;
    if (qtyInput.trim() !== '') {
        iloscPobrana = parseFloat(qtyInput.replace(',', '.'));
        if (isNaN(iloscPobrana) || iloscPobrana <= 0) {
            alert('Wprowadzono nieprawidłową ilość.');
            return;
        }
    }
    
    if(!confirm('Czy na pewno podpiąć to opakowanie pod aktualne zlecenie?')) return;
    fetch('/agro/api/opakowania/link', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ opakowanie_id: opakId, plan_id: planId, ilosc_pobrana: iloscPobrana })
    }).then(r => r.json()).then(res => {
        if(res.success) location.reload();
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

