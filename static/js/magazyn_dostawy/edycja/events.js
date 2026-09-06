// events.js
function cancelTransferForm(event) {
    if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
    }
    const draft = getStoredDraftState();
    if (hasDraftItems(draft)) {
        if (confirm('Czy na pewno chcesz porzucić wprowadzone palety i wyczyścić formularz? Wybierz OK, aby usunąć szkic, lub Anuluj, aby zachować wprowadzone palety.')) {
            if (!window.EdycjaConfig.READ_ONLY_MODE) {
                if (typeof unlockDraftPallets === 'function' && draft.items) {
                    unlockDraftPallets(draft.items);
                }
                clearDraftState();
            }
        }
    }
    window.location.href = window.EdycjaConfig.urlListaDostaw;
}

document.addEventListener('DOMContentLoaded', () => {
    // Strip 'draft' query parameter from URL so Back button or refresh never re-executes mode
    try {
        if (window.history && window.history.replaceState) {
            const currentUrl = new URL(window.location.href);
            if (currentUrl.searchParams.has('draft')) {
                currentUrl.searchParams.delete('draft');
                window.history.replaceState({}, document.title, currentUrl.pathname + (currentUrl.searchParams.toString() ? '?' + currentUrl.searchParams.toString() : ''));
            }
        }
    } catch (e) {
        console.warn('replaceState draft cleanup error', e);
    }

    const ref = document.getElementById('order_ref');
    if (!ref.value) ref.value = generateWZ();

    ensureLocationSuggestionsList();

    const bypassInput = document.getElementById('skip_warehouse_lookup');
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
                const cleaned = extractSSCCFromScan(e.target.value);
                e.target.value = cleaned;
                if (cleaned) {
                    lookupAndAddPallets();
                }
            }
        });
        scannerInput.addEventListener('input', (e) => {
            const raw = e.target.value;
            const cleaned = extractSSCCFromScan(raw);
            if (cleaned !== raw) {
                e.target.value = cleaned;
            }
            queueScannerSuggestions(cleaned);
        });
        scannerInput.addEventListener('paste', (e) => {
            setTimeout(() => {
                const cleaned = extractSSCCFromScan(scannerInput.value);
                if (cleaned !== scannerInput.value) {
                    scannerInput.value = cleaned;
                }
            }, 10);
        });

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
            }
        });
    }

    const draft = getStoredDraftState();
    if (hasDraftItems(draft)) {
        // Automatically restore draft into table so scans are NEVER lost when visiting other views/scanner
        restoreDraftState(draft, { silentToast: true });
        showDraftDecisionBanner(draft);
        renderItems();
        updateSaveButtonState();
        if (typeof syncDraftPallets === 'function') {
            syncDraftPallets();
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

    if (typeof startLiveTransferPolling === 'function') {
        startLiveTransferPolling();
    }
});
