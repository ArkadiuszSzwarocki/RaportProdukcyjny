function openPalletModal(displayId, productName, amount, location, type, dateProd, realId, linia, isBlocked, dateAdded, batch, dateExp, unit) {
    currentPallet = { displayId, productName, amount, location, type, date: dateProd, id: realId, linia: linia, is_blocked: isBlocked, date_added: dateAdded, batch, date_exp: dateExp, unit };
    
    const setEl = (id, val) => { const el = document.getElementById(id); if(el) el.textContent = val || '-'; };
    setEl('modalDisplayId', displayId);
    setEl('modalProductName', productName);
    setEl('modalAmount', amount);
    setEl('modalUnit', unit || 'kg');
    setEl('modalLocation', location || 'Brak lokalizacji');
    setEl('modalType', type);
    setEl('modalBatch', batch || '-');
    setEl('modalDateProd', dateProd || '-');
    setEl('modalDateExp', dateExp || '-');
    setEl('modalDateAdded', dateAdded || '-');

    // Pobierz pełne, aktualne dane palety bezpośrednio z bazy danych
    if (realId && type) {
        const curLinia = linia || (typeof LINIA !== 'undefined' ? LINIA : 'PSD');
        fetch(`/warehouse-v2/api/pallet/details?id=${encodeURIComponent(realId)}&type=${encodeURIComponent(type)}&linia=${encodeURIComponent(curLinia)}`)
            .then(r => r.json())
            .then(res => {
                if (res.success && res.pallet) {
                    const p = res.pallet;
                    currentPallet.batch = p.batch;
                    currentPallet.date_exp = p.date_exp;
                    currentPallet.date_prod = p.date_prod;
                    currentPallet.date_added = p.date_added;
                    currentPallet.unit = p.unit;
                    currentPallet.amount = p.amount;
                    currentPallet.location = p.location;
                    currentPallet.productName = p.productName;

                    setEl('modalBatch', p.batch);
                    setEl('modalDateProd', p.date_prod);
                    setEl('modalDateExp', p.date_exp);
                    setEl('modalDateAdded', p.date_added);
                    setEl('modalAmount', p.amount);
                    setEl('modalUnit', p.unit || 'kg');
                    setEl('modalLocation', p.location);
                    setEl('modalProductName', p.productName);
                }
            })
            .catch(err => console.warn('Błąd pobierania szczegółów palety:', err));
    }

    // Blocking status indicator in modal
    const blockBtn = document.getElementById('toggleBlockBtn');
    if (blockBtn) {
        if (currentPallet.is_blocked) {
            blockBtn.innerHTML = '<span class="material-icons">lock_open</span> ODBLOKUJ PALETĘ';
            blockBtn.className = 'modal-btn-secondary';
            blockBtn.style.background = '#10b981';
            blockBtn.style.color = '#fff';
        } else {
            blockBtn.innerHTML = '<span class="material-icons">block</span> ZABLOKUJ PALETĘ';
            blockBtn.className = 'modal-btn-secondary';
            blockBtn.style.background = '#be123c';
            blockBtn.style.color = '#fff';
        }
    }
    
    const returnBtn = document.getElementById('returnToRawBtn');
    if (returnBtn) {
        returnBtn.style.display = (type === 'Wyrób Gotowy') ? 'flex' : 'none';
    }
    
    const histContainer = document.getElementById('modalHistoryContainer');
    const histList = document.getElementById('modalHistoryList');
    if (histContainer) histContainer.style.display = 'none';
    if (histList) histList.innerHTML = '';
    
    const modal = document.getElementById('palletModal');
    const content = document.getElementById('palletModalContent');
    
    if (!modal || !content) {
        console.error('Modal elements not found! Check _modals.html is included.');
        return;
    }
    
    modal.style.display = 'flex';
    setTimeout(() => {
        content.style.transform = 'scale(1)';
    }, 10);
}

function closePalletModal() {
    const modal = document.getElementById('palletModal');
    const content = document.getElementById('palletModalContent');
    
    content.style.transform = 'scale(0.95)';
    setTimeout(() => {
        modal.style.display = 'none';
        currentPallet = {};
    }, 200); 
}

// Usuwa paletę z DOM bez przeładowania strony
function removePalletFromDOM(palletId, message) {
    closePalletModal();
    
    // Usuń z globalnej tablicy danych allWarehouseItems, aby uniknąć ponownego wyrenderowania przez filterTable
    allWarehouseItems = allWarehouseItems.filter(item => String(item.id) !== String(palletId));
    if (typeof currentFilteredItems !== 'undefined') {
        currentFilteredItems = currentFilteredItems.filter(item => String(item.id) !== String(palletId));
    }
    
    // Znajdź i usuń wiersz tabeli oraz kafelek
    const row = document.querySelector(`tr[data-id="${palletId}"]`);
    const card = document.querySelector(`.pallet-card[data-id="${palletId}"]`);
    
    [row, card].forEach(el => {
        if (!el) return;
        el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        el.style.opacity = '0';
        el.style.transform = 'scale(0.95)';
        setTimeout(() => el.remove(), 320);
    });
    
    // Pokaż toast zamiast alert
    showToast(message || 'Operacja wykonana pomyślnie.', 'success');
}


