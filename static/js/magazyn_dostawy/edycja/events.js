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
                    lookupAndAddPallets();
                }
            }
        });
        scannerInput.addEventListener('input', (e) => queueScannerSuggestions(e.target.value));

        // Global keydown listener to auto-focus scanner input
        document.addEventListener('keydown', (e) => {
            // Ignore if focus is already in an input, textarea, or contenteditable
            const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
            if (activeTag === 'input' || activeTag === 'textarea' || document.activeElement.isContentEditable) {
                return;
            }
            
            // Ignore control keys (Ctrl, Alt, Meta)
            if (e.ctrlKey || e.altKey || e.metaKey) return;
            
            // If it's a printable character or number, focus the input
            if (e.key.length === 1) {
                scannerInput.focus();
                // We do not prevent default, so the character will be typed into the focused input
            }
        });
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
