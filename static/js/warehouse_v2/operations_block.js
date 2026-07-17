function togglePalletBlock() {
    if(!currentPallet.id) return;
    fetch('/warehouse-v2/api/pallet/toggle-block', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: currentPallet.id,
            type: currentPallet.type,
            linia: currentPallet.linia
        })
    }).then(r => r.json()).then(data => {
        if(data.success) {
            showToast(data.message || 'Status blokady zmieniony.', 'success');
            // Zaktualizuj stan wizualny wiersza bez reload
            const row = document.querySelector(`tr[data-id="${currentPallet.id}"]`);
            const card = document.querySelector(`.pallet-card[data-id="${currentPallet.id}"]`);
            const newBlocked = !currentPallet.is_blocked;
            [row, card].forEach(el => {
                if (!el) return;
                el.dataset.blocked = newBlocked ? '1' : '0';
                el.classList.toggle('is-blocked-row', newBlocked);
                el.classList.toggle('is-blocked-card', newBlocked);
            });
            closePalletModal();
        } else {
            AppDialog.alert("Błąd: " + data.error);
        }
    });
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


