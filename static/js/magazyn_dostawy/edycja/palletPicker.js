// palletPicker.js




function renderPalletSelectionModal() {
        if (!palletPickerState) {
            return;
        }

        const summary = document.getElementById('palletSelectSummary');
        const list = document.getElementById('palletSelectList');
        const confirmBtn = document.getElementById('palletSelectConfirmBtn');
        const searchInput = document.getElementById('palletSelectSearch');
        if (!summary || !list) {
            return;
        }

        const selectedCount = palletPickerState.selected.size;
        const query = String(palletPickerState.searchTerm || '').trim().toLowerCase();
        const filteredEntries = palletPickerState.pallets
            .map((pal, idx) => ({ pal, idx }))
            .filter(entry => {
                if (!query) {
                    return true;
                }
                const haystack = [
                    entry.pal.nazwa,
                    entry.pal.nr_palety,
                    entry.pal.id,
                    entry.pal.lokalizacja,
                    entry.pal.nr_partii,
                    entry.pal.type,
                ].map(v => String(v || '').toLowerCase()).join(' ');
                return haystack.includes(query);
            });

        summary.textContent = `Wyników: ${palletPickerState.pallets.length}. Po filtrze: ${filteredEntries.length}. Zaznaczone: ${selectedCount}. Docelowo: ${palletPickerState.desiredCount}.`;

        if (searchInput && searchInput.value !== palletPickerState.searchTerm) {
            searchInput.value = palletPickerState.searchTerm || '';
        }

        if (confirmBtn) {
            const canConfirm = selectedCount > 0 && selectedCount <= palletPickerState.desiredCount;
            confirmBtn.textContent = `Dodaj wybrane ${selectedCount}/${palletPickerState.desiredCount}`;
            confirmBtn.disabled = !canConfirm;
            confirmBtn.style.opacity = canConfirm ? '1' : '0.65';
            confirmBtn.style.cursor = canConfirm ? 'pointer' : 'not-allowed';
        }

        if (filteredEntries.length === 0) {
            list.innerHTML = '<div style="padding: 16px 4px; font-size: 12px; color: #64748b;">Brak palet pasujących do wyszukiwania.</div>';
            return;
        }

        list.innerHTML = filteredEntries.map(entry => {
            const pal = entry.pal;
            const idx = entry.idx;
            const checked = palletPickerState.selected.has(idx) ? 'checked' : '';
            const code = pal.nr_palety || String(pal.id);
            const qty = pal.stan_magazynowy || 0;
            const typeLabel = pal.type === 'opakowanie' ? 'opakowanie' : 'surowiec';
            return `
                <label style="display: grid; grid-template-columns: 24px 1fr auto; gap: 10px; align-items: center; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; margin-bottom: 8px; cursor: pointer;">
                    <input type="checkbox" data-idx="${idx}" ${checked} onchange="togglePalletSelection(${idx}, this.checked)">
                    <div style="min-width: 0;">
                        <div style="font-size: 13px; font-weight: 800; color: #0f172a;">${escapeAttr(pal.nazwa || '-')}</div>
                        <div style="font-size: 12px; color: #475569;">Kod: ${escapeAttr(code)} | Lokalizacja: ${escapeAttr(pal.lokalizacja || '-')} | Typ: ${escapeAttr(typeLabel)}</div>
                    </div>
                    <div style="font-size: 12px; font-weight: 700; color: #334155; text-align: right;">Stan: ${escapeAttr(qty)}</div>
                </label>
            `;
        }).join('');
    }

function togglePalletSelection(idx, checked) {
        if (!palletPickerState) {
            return;
        }
        if (checked) {
            palletPickerState.selected.add(idx);
        } else {
            palletPickerState.selected.delete(idx);
        }
        renderPalletSelectionModal();
    }



function confirmPalletSelection() {
        if (!palletPickerState) {
            return;
        }

        const selectedIndexes = Array.from(palletPickerState.selected).sort((a, b) => a - b);
        if (selectedIndexes.length === 0) {
            showToast('Zaznacz przynajmniej jedną paletę.', 'warning');
            return;
        }

        if (selectedIndexes.length > palletPickerState.desiredCount) {
            showToast(`Zaznaczono za dużo palet. Maksymalnie: ${palletPickerState.desiredCount}.`, 'warning');
            return;
        }

        const selectedPallets = selectedIndexes.map(idx => palletPickerState.pallets[idx]);
        closePalletSelectionModal();
        appendPalletsToItems(selectedPallets);
    }

function closePalletSelectionModal() {
        const modal = document.getElementById('palletSelectModal');
        const confirmBtn = document.getElementById('palletSelectConfirmBtn');
        if (modal) {
            modal.style.display = 'none';
        }
        if (confirmBtn) {
            confirmBtn.textContent = 'Dodaj wybrane';
            confirmBtn.disabled = false;
            confirmBtn.style.opacity = '1';
            confirmBtn.style.cursor = 'pointer';
        }
        document.removeEventListener('keydown', handlePalletSelectionEscape);
        palletPickerState = null;
    }

function openPalletSelectionModal(pallets, desiredCount) {
        const modal = document.getElementById('palletSelectModal');
        if (!modal) {
            appendPalletsToItems(pallets.slice(0, desiredCount));
            return;
        }

        palletPickerState = {
            pallets: pallets,
            desiredCount: desiredCount,
            selected: new Set(),
            searchTerm: '',
        };

        document.removeEventListener('keydown', handlePalletSelectionEscape);
        document.addEventListener('keydown', handlePalletSelectionEscape);
        renderPalletSelectionModal();
        modal.style.display = 'flex';

        const searchInput = document.getElementById('palletSelectSearch');
        if (searchInput) {
            searchInput.value = '';
            setTimeout(() => searchInput.focus(), 0);
        }
    }

function handlePalletSelectionEscape(event) {
        if (event.key !== 'Escape') {
            return;
        }

        const modal = document.getElementById('palletSelectModal');
        if (modal && modal.style.display === 'flex') {
            closePalletSelectionModal();
        }
    }

function updatePalletSelectionSearch(value) {
        if (!palletPickerState) {
            return;
        }
        palletPickerState.searchTerm = String(value || '');
        renderPalletSelectionModal();
    }

function generateManualRows(count) {
        if (READ_ONLY_MODE) {
            notifyReadOnly();
            return;
        }
        count = parseInt(count);
        if (isNaN(count) || count < 0) return;
        
        const currentCount = items.length;
        if (count > currentCount) {
            for (let i = currentCount; i < count; i++) {
                items.push(buildEmptyItem(String(i)));
            }
        } else if (count < currentCount) {
            const removed = items.slice(count);
            removed.forEach((item, removedIdx) => {
                clearCopiedMarker(item, count + removedIdx);
            });
            items = items.slice(0, count);
        }
        saveDraftState();
        renderItems();
    }

function appendPalletsToItems(selectedPallets) {
        const targetLoc = getCurrentTargetLocation();
        const conflictingPallets = selectedPallets.filter(pal => isRouteConflictLocation(pal && pal.lokalizacja, targetLoc));
        const validPallets = selectedPallets.filter(pal => !isRouteConflictLocation(pal && pal.lokalizacja, targetLoc));

        if (conflictingPallets.length > 0) {
            showToast(`Operacja niemożliwa: ${conflictingPallets.length} palet ma tę samą lokalizację co pole Dokąd (${targetLoc}).`, 'warning');
        }

        if (validPallets.length === 0) {
            return;
        }

        const existingKeys = new Set(
            items
                .map(it => getPalletReservationKeyFromItem(it))
                .filter(Boolean)
        );

        const newKeys = new Set();
        let duplicateAlreadyInForm = 0;
        let duplicateInSelection = 0;

        const dedupedPallets = validPallets.filter(pal => {
            const key = getPalletReservationKeyFromPallet(pal);
            if (!key) {
                return true;
            }

            if (existingKeys.has(key)) {
                duplicateAlreadyInForm += 1;
                return false;
            }

            if (newKeys.has(key)) {
                duplicateInSelection += 1;
                return false;
            }

            newKeys.add(key);
            return true;
        });

        if (duplicateAlreadyInForm > 0 && typeof showToast === 'function') {
            showToast(`Pominięto ${duplicateAlreadyInForm} palet: są już dodane w tym zleceniu.`, 'warning');
        }

        if (duplicateInSelection > 0 && typeof showToast === 'function') {
            showToast(`Pominięto ${duplicateInSelection} duplikatów z bieżącego wyboru.`, 'warning');
        }

        if (dedupedPallets.length === 0) {
            return;
        }

        const emptyIndexes = [];
        items.forEach((item, index) => {
            if (isItemPalletSlotEmpty(item)) {
                emptyIndexes.push(index);
            }
        });

        let filledOpenRows = 0;
        let appendedRows = 0;

        dedupedPallets.forEach((pal, idx) => {
            const newItem = createItemFromPallet(pal, idx);
            const slotIndex = emptyIndexes.length > 0 ? emptyIndexes.shift() : undefined;

            if (slotIndex !== undefined) {
                const existingId = items[slotIndex] && items[slotIndex].id;
                if (existingId) {
                    newItem.id = existingId;
                }
                clearCopiedMarker(items[slotIndex], slotIndex);
                items[slotIndex] = newItem;
                filledOpenRows += 1;
            } else {
                items.push(newItem);
                appendedRows += 1;
            }
        });

        const countInput = document.getElementById('pallet_count');
        if (countInput) {
            countInput.value = items.length;
        }

        saveDraftState();
        renderItems();
        if (typeof showToast === 'function') {
            if (filledOpenRows > 0 && appendedRows > 0) {
                showToast(`Uzupełniono ${filledOpenRows} otwartych wierszy i dodano ${appendedRows} nowych palet.`, 'success');
            } else if (filledOpenRows > 0) {
                showToast(`Uzupełniono ${filledOpenRows} otwartych wierszy.`, 'success');
            } else {
                showToast(`Dodano ${appendedRows} palet.`, 'success');
            }
        }
    }
