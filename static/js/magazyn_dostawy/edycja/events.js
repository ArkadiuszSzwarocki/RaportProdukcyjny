// events.js
function cancelTransferForm(event) {
    if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
    }
    if (!window.EdycjaConfig.READ_ONLY_MODE) {
        clearDraftState();
    }
    window.location.href = window.EdycjaConfig.urlListaDostaw;
}

document.addEventListener('DOMContentLoaded', () => {
    const ref = document.getElementById('order_ref');
    if (!ref.value) ref.value = generateWZ();

    ensureLocationSuggestionsList();

    const targetInput = document.getElementById('lokalizacja_do');
    const bypassInput = document.getElementById('skip_warehouse_lookup');
    if (targetInput) {
        targetInput.addEventListener('change', () => {
            saveDraftState();
            renderItems();
            updateSaveButtonState();
        });
    }
    if (bypassInput) {
        bypassInput.addEventListener('change', () => {
            saveDraftState();
            renderItems();
            updateSaveButtonState();
        });
    }

    const scannerInput = document.getElementById('scanner_input');
    if (scannerInput) {
        scannerInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = e.target.value.trim();
                if (val) {
                    lookupAndAddPallets(val);
                    e.target.value = '';
                }
            }
        });
        scannerInput.addEventListener('input', (e) => queueScannerSuggestions(e.target.value));
    }

    const draft = getStoredDraftState();
    if (hasDraftItems(draft)) {
        const mode = getDraftModeFromUrl();
        if (mode === 'restore') {
            restoreDraftState(draft, { silentToast: true });
            renderItems();
            updateSaveButtonState();
        } else if (mode === 'new') {
            startFreshEntry();
        } else {
            pendingDraftToDecide = draft;
            showDraftDecisionBanner(draft);
            renderItems();
            updateSaveButtonState();
        }
    } else {
        if (!window.EdycjaConfig.IS_NEW_TRANSFER_FORM && items.length > 0) {
            // Edit existing handled by data injection
        } else if (items.length === 0) {
            addEmptyRow();
        }
        renderItems();
        updateSaveButtonState();
    }
});
