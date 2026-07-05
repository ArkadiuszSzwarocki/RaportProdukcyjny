function normalizeScanCode(value) {
    return String(value || '').trim().toUpperCase();
}

let activeGlobalItemType = null; // 'transfer' or 'wg'

function updateGlobalScanHint(message, kind) {
    const hint = document.getElementById('globalScanHint');
    if (!hint) return;
    hint.textContent = message;
    if (kind === 'success') hint.style.color = '#15803d';
    else if (kind === 'error') hint.style.color = '#b91c1c';
    else hint.style.color = '#1e40af';
}

function handleGlobalScannerSubmit() {
    const input = document.getElementById('globalScannerInput');
    if (!input) return;

    const rawCode = input.value;
    if (!rawCode.trim()) return;

    // KROK 1: Skanowanie palety (jeśli nie mamy zapisanej aktywnej palety)
    if (!activeTransferItem) {
        const transferMatch = findTransferByScannedCode(rawCode);
        if (transferMatch.status === 'single') {
            activeGlobalItemType = 'transfer';
            activeTransferItem = transferMatch.item;
            input.value = '';
            input.placeholder = "2. Zeskanuj lokalizację docelową";
            input.setAttribute('list', 'locationSuggestionsList');
            queueLocationSuggestions('');
            input.focus();
            updateGlobalScanHint(`Zeskanowano paletę z DOSTAWY. Teraz zeskanuj lokalizację docelową.`, 'success');
            return;
        }

        const wgMatch = findWGByScannedCode(rawCode);
        if (wgMatch.status === 'single') {
            activeGlobalItemType = 'wg';
            activeTransferItem = wgMatch.item;
            input.value = '';
            input.placeholder = "2. Zeskanuj lokalizację docelową";
            input.setAttribute('list', 'locationSuggestionsList');
            queueLocationSuggestions('');
            input.focus();
            updateGlobalScanHint(`Zeskanowano paletę z PRODUKCJI (WG). Teraz zeskanuj lokalizację docelową.`, 'success');
            return;
        }

        input.value = '';
        if (transferMatch.status === 'many' || wgMatch.status === 'many') {
            updateGlobalScanHint('Znaleziono więcej niż jedną paletę. Użyj pełnego kodu SSCC.', 'error');
            if (typeof showToast === 'function') showToast('Znaleziono więcej niż jedną paletę. Użyj pełnego kodu.', 'warning');
            return;
        }

        updateGlobalScanHint('Nie znaleziono oczekującej palety dla tego kodu.', 'error');
        if (typeof showToast === 'function') showToast('Nie znaleziono palety dla zeskanowanego kodu.', 'warning');
        return;
    }

    // KROK 2: Skanowanie lokalizacji (mamy już aktywną paletę)
    handleGlobalLocationScanSubmit(rawCode);
}

async function handleGlobalLocationScanSubmit(rawLocationCode) {
    const input = document.getElementById('globalScannerInput');

    const lok = normalizeLocationCode(rawLocationCode);
    if (!lok) {
        updateGlobalScanHint('Podaj lokalizację odstawczą.', 'error');
        if (typeof showToast === 'function') showToast('Podaj lokalizację odstawczą.', 'warning');
        return;
    }

    if (input) input.disabled = true;

    if (!activeGlobalItemType || !activeTransferItem) {
        if (input) input.disabled = false;
        return;
    }

    try {
        let resp;
        if (activeGlobalItemType === 'transfer') {
            resp = await fetch(`/magazyn-dostawy/api/przyjmij-pozycje/${encodeURIComponent(activeTransferItem.dostawa_id)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    item_id: activeTransferItem.item_id,
                    lokalizacja: lok,
                    nr_partii: activeTransferItem.nr_partii || null,
                    data_produkcji: activeTransferItem.data_produkcji || null,
                    data_przydatnosci: activeTransferItem.data_przydatnosci || null,
                    printer_id: null
                })
            });
        } else if (activeGlobalItemType === 'wg') {
            const parsedWaga = parseWeightValue(activeTransferItem.waga);
            resp = await fetch('/magazyn-dostawy/api/przyjmij-wg', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    id: activeTransferItem.id,
                    lokalizacja: lok,
                    linia: window.MAGAZYN_CONFIG.linia,
                    waga: Number.isFinite(parsedWaga) ? parsedWaga : null
                })
            });
        }

        const data = await resp.json();
        if (resp.ok && data.success) {
            if (typeof showToast === 'function') showToast(data.message || 'Pozycja przyjęta.', 'success');
            updateGlobalScanHint('Pozycja przyjęta. Skanuj kolejną paletę.', 'success');

            // Zresetowanie wejścia
            activeGlobalItemType = null;
            activeTransferItem = null;
            if (input) {
                input.value = '';
                input.placeholder = "1. Zeskanuj paletę (SSCC) i naciśnij Enter";
                input.removeAttribute('list');
                input.disabled = false;
                input.focus();
            }

            performSilentRefresh();
            return;
        }

        const errorMsg = (data && (data.error || data.message)) || 'Błąd zapisu.';
        updateGlobalScanHint(errorMsg, 'error');
        if (typeof showToast === 'function') showToast(errorMsg, 'warning');
    } catch (e) {
        updateGlobalScanHint('Błąd połączenia z serwerem.', 'error');
        if (typeof showToast === 'function') showToast('Błąd połączenia z serwerem.', 'warning');
    } finally {
        if (input) input.disabled = false;
        if (input && activeTransferItem) input.focus();
    }
}

