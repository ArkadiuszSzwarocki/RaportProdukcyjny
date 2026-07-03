// api.js
let locationSuggestTimer = null;
let locationSuggestAbortController = null;
let locationSuggestLastPrefix = '';
let scannerSuggestTimer = null;
let scannerSuggestAbortController = null;


function ensureLocationSuggestionsList() {
        let dataList = document.getElementById('locationSuggestionsList');
        if (dataList) {
            return dataList;
        }

        dataList = document.createElement('datalist');
        dataList.id = 'locationSuggestionsList';
        document.body.appendChild(dataList);
        return dataList;
    }

function queueLocationSuggestions(rawValue) {
        const prefix = normalizeLocation(rawValue);
        if (!prefix) {
            locationSuggestLastPrefix = '';
            renderLocationSuggestionOptions([]);
            return;
        }

        if (prefix === locationSuggestLastPrefix) {
            return;
        }

        if (locationSuggestTimer) {
            clearTimeout(locationSuggestTimer);
        }

        locationSuggestTimer = setTimeout(() => {
            fetchLocationSuggestions(prefix);
        }, 120);
    }

function queueScannerSuggestions(value) {
        if (scannerSuggestTimer) clearTimeout(scannerSuggestTimer);
        const prefix = (value || '').trim();
        if (prefix.length < 2) return;
        scannerSuggestTimer = setTimeout(() => fetchScannerSuggestions(prefix), 250);
    }

async function fetchLocationSuggestions(prefix) {
        if (locationSuggestAbortController) {
            locationSuggestAbortController.abort();
        }

        locationSuggestAbortController = new AbortController();
        const query = new URLSearchParams({
            linia: '${window.EdycjaConfig.linia}',
            prefix: prefix,
            only_free_for_racks: '1',
            limit: '50',
        });

        try {
            const response = await fetch(`/magazyn-dostawy/api/sugerowane-lokalizacje?${query.toString()}`, {
                signal: locationSuggestAbortController.signal,
            });

            const data = await response.json();
            if (!data || !data.success || !Array.isArray(data.suggestions)) {
                return;
            }

            locationSuggestLastPrefix = prefix;
            renderLocationSuggestionOptions(data.suggestions);
        } catch (error) {
            if (error && error.name === 'AbortError') {
                return;
            }
            console.warn('Location suggestions failed', error);
        }
    }

async function fetchScannerSuggestions(prefix) {
        if (scannerSuggestAbortController) scannerSuggestAbortController.abort();
        scannerSuggestAbortController = new AbortController();
        const bypassLookup = isWarehouseLookupBypassed();
        try {
            const res = await fetch(`/magazyn-dostawy/api/dostepne-palety?linia=${window.EdycjaConfig.linia}&prefix=${encodeURIComponent(prefix)}&skip_warehouse_lookup=${bypassLookup ? '1' : '0'}`, {
                signal: scannerSuggestAbortController.signal
            });
            const data = await res.json();
            if (data.success && Array.isArray(data.pallets)) {
                let list = document.getElementById('palletGlobalSuggestionsList');
                if (!list) return;
                list.innerHTML = '';
                // Ograniczamy do 25 podpowiedzi, by nie zapchać przeglądarki
                data.pallets.slice(0, 25).forEach(p => {
                    const option = document.createElement('option');
                    // Jako value wstawiamy SSCC lub ID
                    const sscc = p.nr_palety || p.id;
                    option.value = sscc;
                    // Jako tekst wstawiamy nazwę i lokalizację, żeby widział w podpowiedziach
                    const stan = p.stan_magazynowy ? p.stan_magazynowy + ' kg/szt' : 'Brak';
                    option.textContent = `${p.nazwa} | Lokalizacja: ${p.lokalizacja || '-'} | Stan: ${stan}`;
                    list.appendChild(option);
                });
            }
        } catch (error) {
            if (error && error.name === 'AbortError') return;
            console.warn('Scanner suggestions failed', error);
        }
    }

async function lookupAndAddPallets() {
        if (READ_ONLY_MODE) {
            notifyReadOnly();
            return;
        }
        const input = document.getElementById('scanner_input');
        const countInput = document.getElementById('pallet_count');
        const code = input.value.trim();
        if (!code) return;

        const count = parseInt(countInput.value) || 1;
        input.value = 'Szukam...';
        input.disabled = true;

        try {
            const bypassLookup = isWarehouseLookupBypassed();
            const res = await fetch(`/magazyn-dostawy/api/dostepne-palety?linia=${window.EdycjaConfig.linia}&prefix=${encodeURIComponent(code)}&skip_warehouse_lookup=${bypassLookup ? '1' : '0'}`);
            const data = await res.json();

            if (!data.success || !Array.isArray(data.pallets) || data.pallets.length === 0) {
                showToast('Nie znaleziono palet dla podanego kodu/regału.', 'warning');
                return;
            }

            const desiredCount = Math.max(1, count);
            if (data.pallets.length === 1) {
                appendPalletsToItems([data.pallets[0]]);
                return;
            }

            openPalletSelectionModal(data.pallets, desiredCount);
        } catch (e) {
            showToast('Błąd połączenia', 'danger');
        } finally {
            input.value = '';
            input.disabled = false;
            input.focus();
        }
    }

async function savePrzesuniecie() {
        if (READ_ONLY_MODE) {
            notifyReadOnly();
            return;
        }
        const targetInputElement = document.getElementById('lokalizacja_do');
        const targetLoc = targetInputElement ? targetInputElement.value : '';
        const orderRefElem = document.getElementById('order_ref');
        const orderRef = orderRefElem ? orderRefElem.value.trim() : '';

        const conflictingItems = items.filter(item => isRouteConflictLocation(item && item.sourceSpot, targetLoc));
        if (conflictingItems.length > 0) {
            return showToast(`Operacja niemożliwa: ${conflictingItems.length} palet ma lokalizację źródłową taką samą jak Dokąd (${normalizeLocation(targetLoc)}).`, 'warning');
        }

        const unknownSourceLocations = getUnknownSourceLocations();
        if (unknownSourceLocations.length > 0) {
            const preview = unknownSourceLocations.slice(0, 3).join(', ');
            const suffix = unknownSourceLocations.length > 3 ? ', ...' : '';
            return showToast(`Nieznane lokalizacje źródłowe: ${preview}${suffix}.`, 'warning');
        }

        if (items.length === 0) return showToast('Dodaj przynajmniej jedną paletę!', 'warning');
        
        formSubmitAttempted = true;
        renderItems();
        
        if (!items.every(isItemComplete)) {
            return showToast('Uzupełnij wszystkie pola w każdej palecie.', 'warning');
        }

        const payload = {
            id: window.EdycjaConfig.dostawaId,
            order_ref: orderRef,
            lokalizacja_do: targetLoc,
            linia: window.EdycjaConfig.linia,
            items: items,
            skip_warehouse_lookup: isWarehouseLookupBypassed(),
            status: "OCZEKUJE"
        };

        const res = await fetch("/magazyn-dostawy/api/zapisz", {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            clearDraftState();
            resetTransferFormAfterSave();
            showToast('Zapisano pomyślnie! Otwieram raport...', 'success');
            if (typeof window.refreshSidebarBadges === 'function') {
                window.refreshSidebarBadges();
            }
            setTimeout(() => {
                window.open(`/magazyn-dostawy/raport-przesuniecia/${data.id}?linia=${window.EdycjaConfig.linia}`, '_blank');
            }, 500);
        } else {
            showToast('Błąd: ' + data.error, 'danger');
        }
    }

function resetTransferFormAfterSave() {
        const targetInput = document.getElementById('lokalizacja_do');
        const countInput = document.getElementById('pallet_count');
        const orderRefInput = document.getElementById('order_ref');
        const scannerInput = document.getElementById('scanner_input');
        const bypassInput = document.getElementById('skip_warehouse_lookup');

        if (targetInput) targetInput.value = '';
        if (countInput) countInput.value = '0';
        if (orderRefInput) orderRefInput.value = generateWZ();
        if (scannerInput) scannerInput.value = '';
        if (bypassInput) bypassInput.checked = false;

        items = [];
        copiedRowsInfoByItem = {};
        palletPickerState = null;

        renderItems();
        updateSaveButtonState();
    }
