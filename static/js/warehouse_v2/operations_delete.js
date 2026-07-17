// ---- HARD DELETE PALLET (admin only) ----
function deletePalletPermanently() {
    if (!currentPallet.id) return;
    AppDialog.confirm(`⚠️ TRWAŁE USUNIĘCIE\n\nPaleta: ${currentPallet.displayId}\nProdukt: ${currentPallet.productName}\n\nOperacja nieodwracalna. Kontynuować?`).then(ok => {
        if (!ok) return;
    
    fetch('/warehouse-v2/api/pallet/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ id: currentPallet.id, type: currentPallet.type, linia: currentPallet.linia })
    }).then(r => r.json()).then(data => {
        if (data.success) {
            removePalletFromDOM(currentPallet.id, `🗑️ ${data.message || 'Usunięto pomyślnie'}`);
        } else {
            showToast('Błąd: ' + (data.error || data.message || 'Nieznany błąd'), 'error');
        }
    }).catch(e => showToast('Błąd połączenia: ' + e, 'error'));
    });
}



