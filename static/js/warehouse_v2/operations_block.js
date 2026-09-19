async function togglePalletBlock() {
    if(!currentPallet.id && !currentPallet.displayId) return;
    
    let blockReason = null;
    if (!currentPallet.is_blocked) {
        blockReason = await AppDialog.prompt(
            `Podaj powód zablokowania palety ${currentPallet.displayId || '#' + currentPallet.id}:`,
            'Kontrola jakości'
        );
        if (blockReason === null) {
            return; // Użytkownik anulował
        }
        blockReason = blockReason.trim() || 'Blokada manualna (Jakość / Magazyn)';
    }

    fetch('/warehouse-v2/api/pallet/toggle-block', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: currentPallet.id,
            sscc: currentPallet.displayId,
            type: currentPallet.type,
            linia: currentPallet.linia,
            reason: blockReason
        })
    }).then(r => r.json()).then(data => {
        if(data.success) {
            showToast(data.message || 'Status blokady zmieniony.', 'success');
            const newBlocked = !currentPallet.is_blocked;
            currentPallet.is_blocked = newBlocked;
            currentPallet.block_reason = newBlocked ? blockReason : null;
            const targetId = currentPallet.id;
            const targetSscc = currentPallet.displayId;

            if (typeof updateBlockButtonDisplay === 'function') {
                updateBlockButtonDisplay(newBlocked);
            }

            allWarehouseItems.forEach(x => {
                if ((targetId && String(x.id) === String(targetId) && x.type === currentPallet.type) || (targetSscc && x.displayId === targetSscc)) {
                    x.is_blocked = newBlocked ? 1 : 0;
                    x.block_reason = newBlocked ? blockReason : null;
                }
            });

            if (typeof currentFilteredItems !== 'undefined') {
                currentFilteredItems.forEach(x => {
                    if ((targetId && String(x.id) === String(targetId) && x.type === currentPallet.type) || (targetSscc && x.displayId === targetSscc)) {
                        x.is_blocked = newBlocked ? 1 : 0;
                        x.block_reason = newBlocked ? blockReason : null;
                    }
                });
            }

            // Zaktualizuj stan wizualny wiersza bez reload
            const row = document.querySelector(`tr[data-id="${targetId}"]`) || (targetSscc ? document.querySelector(`tr[data-sscc="${targetSscc}"]`) : null);
            const card = document.querySelector(`.pallet-card[data-id="${targetId}"]`) || (targetSscc ? document.querySelector(`.pallet-card[data-sscc="${targetSscc}"]`) : null);
            [row, card].forEach(el => {
                if (!el) return;
                el.dataset.blocked = newBlocked ? '1' : '0';
                el.classList.toggle('is-blocked-row', newBlocked);
                el.classList.toggle('is-blocked-card', newBlocked);
            });
            closePalletModal();
            if (typeof populateBlockedFilter === 'function') {
                populateBlockedFilter();
            }
            if (typeof filterTable === 'function') {
                filterTable({ preserveScroll: true });
            }
        } else {
            AppDialog.alert("Błąd: " + (data.message || data.error));
        }
    });
}

function previewCurrentPallet() {
    if (!currentPallet || !currentPallet.id) {
        AppDialog.alert('Brak aktywnej palety do podglądu.');
        return;
    }
    const linia = currentPallet.linia || (typeof LINIA !== 'undefined' ? LINIA : 'PSD');
    const type = currentPallet.type || '';
    const sscc = currentPallet.displayId || '';
    const previewUrl = `/warehouse-v2/podglad-etykiety/${encodeURIComponent(currentPallet.id)}?linia=${encodeURIComponent(linia)}&type=${encodeURIComponent(type)}&sscc=${encodeURIComponent(sscc)}`;
    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
        window.open(previewUrl, '_blank');
    } else {
        window.open(previewUrl, 'label_preview_psd', 'width=900,height=1000,resizable=yes,scrollbars=yes');
    }
}

async function printCurrentPallet(triggerBtn) {
    try {
        if (!currentPallet || !currentPallet.id) {
            AppDialog.alert('Brak aktywnej palety do wydruku.');
            return;
        }

        const printerSelect = document.getElementById('printerSelect');
        if (!printerSelect) {
            AppDialog.alert('Błąd UI: nie znaleziono listy drukarek. Odśwież stronę (Ctrl+F5).');
            return;
        }

        const printerId = printerSelect.value;
        if (!printerId) {
            AppDialog.alert('Wybierz drukarkę z listy przed wydrukiem.');
            return;
        }

        if (typeof showToast === 'function') {
            showToast('Rozpoczynam druk etykiety...', 'info');
        }

        const requestBody = {
            id: currentPallet.id,
            nr_palety: currentPallet.displayId || currentPallet.nr_palety || '',
            display_id: currentPallet.displayId || '',
            type: currentPallet.type,
            linia: currentPallet.linia,
            printer_id: printerId
        };

        const controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        const timeoutMs = 25000;
        let timeoutId = null;
        if (controller) {
            timeoutId = setTimeout(function () {
                try { controller.abort(); } catch (e) {}
            }, timeoutMs);
        }

        const fetchOptions = {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(requestBody)
        };
        if (controller) {
            fetchOptions.signal = controller.signal;
        }

        if (triggerBtn && triggerBtn instanceof HTMLElement) {
            triggerBtn.disabled = true;
        }

        fetch('/warehouse-v2/api/pallet/print', fetchOptions)
        .then(r => r.json())
        .then(async data => {
            if(data.success) {
                if (typeof showToast === 'function') {
                    showToast('Etykieta wysłana do drukarki: ' + data.message, 'success');
                }
                return;
            }

            if (data && data.local_bridge_fallback && typeof window.tryLocalBridgeFallback === 'function') {
                if (typeof showToast === 'function') {
                    showToast('Serwer nie doszedł do drukarki. Próbuję fallback mostka...', 'warning');
                }

                const localResult = await window.tryLocalBridgeFallback(data.local_bridge_fallback);
                if (localResult && localResult.ok) {
                    AppDialog.alert('Etykieta wydrukowana przez fallback: ' + (localResult.printerName || '') + ' (' + (localResult.printerIp || '') + ')');
                    return;
                }

                const fallbackMessage = (localResult && localResult.message)
                    ? String(localResult.message)
                    : 'Nie udało się wykonać fallbacku lokalnego.';

                const baseError = (data && (data.error || data.message)) ? (data.error || data.message) : 'Nieznany błąd';
                AppDialog.alert('Błąd podczas drukowania: ' + baseError + '\nFallback: ' + fallbackMessage);
                return;
            }

            const errorMsg = (data && (data.error || data.message)) ? (data.error || data.message) : 'Nieznany błąd';
            AppDialog.alert('Błąd podczas drukowania: ' + errorMsg);
        })
        .catch(e => {
            if (e && e.name === 'AbortError') {
                AppDialog.alert('Brak odpowiedzi z serwera druku (timeout). Sprawdź połączenie i spróbuj ponownie.');
                return;
            }
            AppDialog.alert('Błąd połączenia: ' + e);
        })
        .finally(() => {
            if (timeoutId) {
                clearTimeout(timeoutId);
            }
            if (triggerBtn && triggerBtn instanceof HTMLElement) {
                triggerBtn.disabled = false;
            }
        });
    } catch (e) {
        const msg = (e && e.message) ? e.message : String(e);
        AppDialog.alert('Błąd klienta podczas drukowania: ' + msg);
    }
}


