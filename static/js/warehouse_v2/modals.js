function openPalletModal(displayId, productName, amount, location, type, dateProd, realId, linia, isBlocked, dateAdded, batch, dateExp, unit, packagingType) {
    currentPallet = { displayId, productName, amount, location, type, date: dateProd, id: realId, linia: linia, is_blocked: isBlocked, date_added: dateAdded, batch, date_exp: dateExp, unit, packaging_type: packagingType || 'Worek (25kg)' };
    
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

    const pkgBadge = document.getElementById('modalPackagingBadge');
    if (pkgBadge) {
        if (typeof formatPackagingBadge === 'function') {
            pkgBadge.innerHTML = formatPackagingBadge(currentPallet.packaging_type);
        } else {
            pkgBadge.innerHTML = `<span class="badge" style="background: #e0f2fe; color: #0284c7; border: 1px solid #bae6fd; font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 6px;">${currentPallet.packaging_type}</span>`;
        }
    }

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
                    if (p.packaging_type) currentPallet.packaging_type = p.packaging_type;

                    setEl('modalBatch', p.batch);
                    setEl('modalDateProd', p.date_prod);
                    setEl('modalDateExp', p.date_exp);
                    setEl('modalDateAdded', p.date_added);
                    setEl('modalAmount', p.amount);
                    setEl('modalUnit', p.unit || 'kg');
                    setEl('modalLocation', p.location);
                    setEl('modalProductName', p.productName);

                    if (pkgBadge && typeof formatPackagingBadge === 'function') {
                        pkgBadge.innerHTML = formatPackagingBadge(currentPallet.packaging_type);
                    }
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

// ─────────────────────────────────────────────────────────────
// ZMIANA RODZAJU OPAKOWANIA (PACKAGING TYPE MODAL)
// ─────────────────────────────────────────────────────────────
function openChangePackagingForPallet(palletId, currentPkg, type, linia) {
    // If modal not open or different pallet, populate currentPallet minimal structure
    if (!currentPallet || String(currentPallet.id) !== String(palletId)) {
        const item = (typeof allWarehouseItems !== 'undefined') 
            ? allWarehouseItems.find(it => String(it.id) === String(palletId)) 
            : null;
        
        currentPallet = {
            id: palletId,
            type: type || (item ? item.type : 'Wyrób Gotowy'),
            linia: linia || (item ? item.linia : (typeof LINIA !== 'undefined' ? LINIA : 'PSD')),
            packaging_type: currentPkg || (item ? item.packaging_type : 'Worek (25kg)')
        };
    }
    promptChangePackaging();
}
window.openChangePackagingForPallet = openChangePackagingForPallet;

function promptChangePackaging() {
    if (!currentPallet || !currentPallet.id) {
        if (typeof showToast === 'function') showToast('Nie wybrano palety.', 'error');
        return;
    }

    const modal = document.getElementById('changePackagingModal');
    const select = document.getElementById('packagingTypeSelect');
    const customWrap = document.getElementById('customPackagingWrap');
    const customInput = document.getElementById('customPackagingInput');
    const errorEl = document.getElementById('changePackagingError');

    if (!modal || !select) return;

    if (errorEl) errorEl.style.display = 'none';

    // Dopasuj bieżące opakowanie w selekcie
    const curPkg = (currentPallet.packaging_type || '').trim();
    let found = false;
    for (let i = 0; i < select.options.length; i++) {
        if (select.options[i].value === curPkg) {
            select.selectedIndex = i;
            found = true;
            break;
        }
    }

    if (!found) {
        if (curPkg && curPkg !== '-') {
            select.value = 'Inne';
            if (customWrap) customWrap.style.display = 'block';
            if (customInput) customInput.value = curPkg;
        } else {
            select.selectedIndex = 1; // domyślnie Worek (25kg)
            if (customWrap) customWrap.style.display = 'none';
        }
    } else {
        if (customWrap) customWrap.style.display = 'none';
    }

    modal.style.display = 'flex';
}

function closeChangePackagingModal() {
    const modal = document.getElementById('changePackagingModal');
    if (modal) modal.style.display = 'none';
}

function onPackagingTypeSelectChange(val) {
    const customWrap = document.getElementById('customPackagingWrap');
    const customInput = document.getElementById('customPackagingInput');
    if (customWrap) {
        if (val === 'Inne') {
            customWrap.style.display = 'block';
            if (customInput) customInput.focus();
        } else {
            customWrap.style.display = 'none';
        }
    }
}

async function submitChangePackaging() {
    if (!currentPallet || !currentPallet.id) return;

    const select = document.getElementById('packagingTypeSelect');
    const customInput = document.getElementById('customPackagingInput');
    const errorEl = document.getElementById('changePackagingError');

    let finalPkg = select ? select.value : 'Worek (25kg)';
    if (finalPkg === 'Inne') {
        finalPkg = (customInput && customInput.value.trim()) ? customInput.value.trim() : 'Inne';
    }

    const payload = {
        id: currentPallet.id,
        type: currentPallet.type,
        packaging_type: finalPkg,
        linia: currentPallet.linia || (typeof LINIA !== 'undefined' ? LINIA : 'PSD')
    };

    try {
        const res = await fetch('/warehouse-v2/api/pallet/update-packaging', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.success) {
            currentPallet.packaging_type = finalPkg;

            // Zaktualizuj plakietkę w otwartym modalu szczegółów
            const pkgBadge = document.getElementById('modalPackagingBadge');
            if (pkgBadge) {
                if (typeof formatPackagingBadge === 'function') {
                    pkgBadge.innerHTML = formatPackagingBadge(finalPkg);
                } else {
                    pkgBadge.innerHTML = `<span class="badge" style="background: #e0f2fe; color: #0284c7; border: 1px solid #bae6fd; font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 6px;">${finalPkg}</span>`;
                }
            }

            // Zaktualizuj w pamięci globalnej tabeli
            if (typeof allWarehouseItems !== 'undefined') {
                const item = allWarehouseItems.find(it => String(it.id) === String(currentPallet.id));
                if (item) item.packaging_type = finalPkg;
            }
            if (typeof currentFilteredItems !== 'undefined') {
                const item = currentFilteredItems.find(it => String(it.id) === String(currentPallet.id));
                if (item) item.packaging_type = finalPkg;
            }

            // Zaktualizuj komórkę tabeli w DOM
            const row = document.querySelector(`tr[data-id="${currentPallet.id}"]`);
            if (row) {
                row.dataset.packaging = finalPkg;
                const cell = row.querySelector('.packaging-cell');
                if (cell && typeof formatPackagingBadge === 'function') {
                    cell.innerHTML = formatPackagingBadge(finalPkg);
                }
            }

            closeChangePackagingModal();
            if (typeof showToast === 'function') {
                showToast(`Zmieniono rodzaj opakowania na: ${finalPkg}`, 'success');
            }
        } else {
            if (errorEl) {
                errorEl.textContent = data.error || 'Wystąpił błąd podczas zapisywania.';
                errorEl.style.display = 'block';
            }
        }
    } catch (err) {
        console.error('Błąd zapisu opakowania:', err);
        if (errorEl) {
            errorEl.textContent = 'Błąd połączenia z serwerem.';
            errorEl.style.display = 'block';
        }
    }
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
    if (typeof showToast === 'function') {
        showToast(message || 'Operacja wykonana pomyślnie.', 'success');
    }
}



