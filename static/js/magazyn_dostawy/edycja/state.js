// state.js
let items = window.EdycjaConfig.items || [];
let formSubmitAttempted = false;
let copiedRowsInfoByItem = {};
let palletPickerState = null;
let pendingDraftToDecide = null;


function getDraftModeFromUrl() {
        try {
            const params = new URLSearchParams(window.location.search || '');
            return String(params.get('draft') || '').trim().toLowerCase();
        } catch (error) {
            return '';
        }
    }

function getStoredDraftState() {
        try {
            const raw = window.localStorage.getItem(FORM_DRAFT_KEY);
            if (!raw) {
                return null;
            }
            const draft = JSON.parse(raw);
            if (!draft || !Array.isArray(draft.items)) {
                return null;
            }
            return draft;
        } catch (error) {
            console.warn('getStoredDraftState error', error);
            return null;
        }
    }

function hasDraftItems(draft) {
        return !!(draft && Array.isArray(draft.items) && draft.items.length > 0);
    }

function saveDraftState() {
        if (READ_ONLY_MODE) {
            return;
        }

        try {
            const sourceInput = document.getElementById('lokalizacja_z');
            const targetInput = document.getElementById('lokalizacja_do');
            const countInput = document.getElementById('pallet_count');
            const orderRefInput = document.getElementById('order_ref');
            const bypassInput = document.getElementById('skip_warehouse_lookup');

            const draft = {
                lokalizacja_z: sourceInput ? sourceInput.value : '',
                lokalizacja_do: targetInput ? targetInput.value : '',
                pallet_count: countInput ? countInput.value : '0',
                order_ref: orderRefInput ? orderRefInput.value : '',
                skip_warehouse_lookup: !!(bypassInput && bypassInput.checked),
                items: items,
                copyMarkers: copiedRowsInfoByItem,
                saved_at: new Date().toISOString(),
            };

            if (!hasDraftItems(draft)) {
                clearDraftState();
                return;
            }

            window.localStorage.setItem(FORM_DRAFT_KEY, JSON.stringify(draft));
        } catch (error) {
            console.warn('saveDraftState error', error);
        }
    }

function restoreDraftState(draftOverride = null, options = {}) {
        if (READ_ONLY_MODE) {
            return false;
        }

        try {
            const draft = draftOverride || getStoredDraftState();
            if (!draft || !Array.isArray(draft.items)) {
                return false;
            }

            const sourceInput = document.getElementById('lokalizacja_z');
            const targetInput = document.getElementById('lokalizacja_do');
            const countInput = document.getElementById('pallet_count');
            const orderRefInput = document.getElementById('order_ref');
            const bypassInput = document.getElementById('skip_warehouse_lookup');

            if (sourceInput) sourceInput.value = draft.lokalizacja_z || '';
            if (targetInput) targetInput.value = draft.lokalizacja_do || '';
            if (orderRefInput && draft.order_ref) orderRefInput.value = draft.order_ref || '';
            if (bypassInput) bypassInput.checked = !!draft.skip_warehouse_lookup;

            items = draft.items;
            if (countInput) countInput.value = String(items.length);

            copiedRowsInfoByItem = {};
            if (draft.copyMarkers && typeof draft.copyMarkers === 'object') {
                copiedRowsInfoByItem = draft.copyMarkers;
            } else if (draft.rowCopyInfo && typeof draft.rowCopyInfo === 'object') {
                const legacyTargetId = String(draft.rowCopyInfo.targetItemId || '').trim();
                const legacyFromRow = parseInt(draft.rowCopyInfo.fromRowNumber, 10);
                if (legacyTargetId !== '' && !Number.isNaN(legacyFromRow)) {
                    copiedRowsInfoByItem[legacyTargetId] = legacyFromRow;
                }
            }

            if (!options.silentToast && typeof showToast === 'function') {
                showToast('Przywrócono zapisany formularz roboczy.', 'info');
            }

            return true;
        } catch (error) {
            console.warn('restoreDraftState error', error);
            return false;
        }
    }

function clearDraftState() {
        try {
            window.localStorage.removeItem(FORM_DRAFT_KEY);
        } catch (error) {
            console.warn('clearDraftState error', error);
        }
    }

function updateItem(index, key, value) {
        if (READ_ONLY_MODE) {
            notifyReadOnly();
            return;
        }

        clearCopiedMarker(items[index], index);

        if (key === 'quantity') {
            setItemQuantity(index, value);
            saveDraftState();
            renderItems();
            return;
        }

        if (key === 'unit') {
            const currentQuantity = getItemQuantity(items[index]);
            if (value === 'szt') {
                items[index].packageForm = 'packaging';
                setItemQuantity(index, currentQuantity);
            } else if (value === 'kg') {
                items[index].packageForm = 'bags';
                setItemQuantity(index, currentQuantity);
            } else {
                items[index].packageForm = '';
            }
            saveDraftState();
            renderItems();
            return;
        }

        items[index][key] = value;
        saveDraftState();
        renderItems();
    }

function removeItem(index) {
        if (READ_ONLY_MODE) {
            notifyReadOnly();
            return;
        }
        const removedItems = items.splice(index, 1);
        const removed = removedItems && removedItems.length ? removedItems[0] : null;
        if (removed) {
            clearCopiedMarker(removed, index);
        }
        const countInput = document.getElementById('pallet_count');
        countInput.value = items.length;
        saveDraftState();
        renderItems();
    }
