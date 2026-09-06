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
        const prefix = (typeof extractSSCCFromScan === 'function' ? extractSSCCFromScan(value) : (value || '')).trim();
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
                    const sscc = p.nr_palety || p.id;
                    option.value = sscc;
                    const stan = p.stan_magazynowy ? p.stan_magazynowy + ' ' + (p.type === 'opakowanie' ? 'szt' : 'kg') : 'Brak';
                    const fifoPrefix = p.is_first_fifo ? '⚡ [1. DO ZUŻYCIA FIFO] ' : (p.fifo_index ? `[FIFO #${p.fifo_index}] ` : '');
                    option.textContent = `${fifoPrefix}${p.nazwa} | Lok: ${p.lokalizacja || '-'} | Partia: ${p.nr_partii || '-'} | Stan: ${stan}`;
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
        const rawVal = input.value.trim();
        const code = (typeof extractSSCCFromScan === 'function' ? extractSSCCFromScan(rawVal) : rawVal).trim();
        if (!code) return;

        input.value = code;
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
        const orderRefElem = document.getElementById('order_ref');
        const orderRef = orderRefElem ? orderRefElem.value.trim() : '';

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
            lokalizacja_do: '',
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
            showToast('Zlecenie otwarte w Oczekujących! Magazynier 2 może już przyjmować palety skanerem.', 'success');
            if (typeof window.refreshSidebarBadges === 'function') {
                window.refreshSidebarBadges();
            }
            const savedId = data.id || window.EdycjaConfig.dostawaId;
            const targetUrl = savedId 
                ? `/magazyn-dostawy/${savedId}?linia=${window.EdycjaConfig.linia}`
                : (window.EdycjaConfig.urlOczekujace || ('/magazyn-dostawy/oczekujace?linia=' + window.EdycjaConfig.linia));
            setTimeout(() => {
                window.location.href = targetUrl;
            }, 600);
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

async function lockDraftPallets(pallets) {
    if (!pallets || pallets.length === 0) return;
    try {
        await fetch('/magazyn-dostawy/api/draft/lock', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                linia: (window.EdycjaConfig && window.EdycjaConfig.linia) || 'AGRO',
                items: pallets
            })
        });
    } catch (e) {
        console.warn('Błąd blokowania palet w wersji roboczej:', e);
    }
}

async function unlockDraftPallets(pallets) {
    if (!pallets || pallets.length === 0) return;
    try {
        await fetch('/magazyn-dostawy/api/draft/unlock', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                linia: (window.EdycjaConfig && window.EdycjaConfig.linia) || 'AGRO',
                items: pallets
            })
        });
    } catch (e) {
        console.warn('Błąd odblokowywania palet:', e);
    }
}

async function syncDraftPallets() {
    if (!items || items.length === 0) return;
    try {
        const res = await fetch('/magazyn-dostawy/api/draft/sync', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                linia: (window.EdycjaConfig && window.EdycjaConfig.linia) || 'AGRO',
                items: items
            })
        });
        const data = await res.json();
        if (data.success && data.result) {
            if (Array.isArray(data.result.items) && data.result.items.length > 0) {
                items = data.result.items;
                saveDraftState();
                renderItems();
            }
            if (Array.isArray(data.result.changes) && data.result.changes.length > 0) {
                const changesSummary = data.result.changes
                    .map(c => `${c.nr_palety}: ${c.old_location || 'brak'} ➔ ${c.new_location}`)
                    .join(', ');
                if (typeof showToast === 'function') {
                    showToast(`Zaktualizowano lokalizację palet z bazy danych: ${changesSummary}. Palety są zablokowane.`, 'warning');
                }
            }
        }
    } catch (e) {
        console.warn('Błąd synchronizacji wersji roboczej z bazą:', e);
    }
}

let liveTransferPollTimer = null;
let isInitializingLiveTransfer = false;

async function ensureLiveTransferInitialized() {
    if (window.EdycjaConfig && window.EdycjaConfig.dostawaId) {
        return window.EdycjaConfig.dostawaId;
    }
    if (isInitializingLiveTransfer) {
        await new Promise(resolve => setTimeout(resolve, 200));
        return window.EdycjaConfig ? window.EdycjaConfig.dostawaId : null;
    }
    isInitializingLiveTransfer = true;
    try {
        const orderRefElem = document.getElementById('order_ref');
        const orderRef = orderRefElem ? orderRefElem.value.trim() : '';
        const res = await fetch('/magazyn-dostawy/api/live-transfer/init', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                linia: (window.EdycjaConfig && window.EdycjaConfig.linia) || 'AGRO',
                order_ref: orderRef
            })
        });
        const data = await res.json();
        if (data.success && data.result && data.result.dostawa_id) {
            if (!window.EdycjaConfig) window.EdycjaConfig = {};
            window.EdycjaConfig.dostawaId = String(data.result.dostawa_id);
            if (orderRefElem && data.result.order_ref) {
                orderRefElem.value = data.result.order_ref;
            }
            try {
                if (window.history && window.history.replaceState) {
                    const url = new URL(window.location.href);
                    url.searchParams.set('id', window.EdycjaConfig.dostawaId);
                    window.history.replaceState({}, document.title, url.pathname + '?' + url.searchParams.toString());
                }
            } catch (err) {
                console.warn('History replaceState warning:', err);
            }
            startLiveTransferPolling();
            return window.EdycjaConfig.dostawaId;
        }
    } catch (e) {
        console.error('Error initializing live transfer order:', e);
    } finally {
        isInitializingLiveTransfer = false;
    }
    return window.EdycjaConfig ? window.EdycjaConfig.dostawaId : null;
}

async function addLiveTransferItem(item) {
    if (!item || (!item.nr_palety && !item.productName)) return;
    try {
        const dostawaId = await ensureLiveTransferInitialized();
        if (!dostawaId) return;

        const res = await fetch('/magazyn-dostawy/api/live-transfer/add-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                dostawa_id: dostawaId,
                linia: (window.EdycjaConfig && window.EdycjaConfig.linia) || 'AGRO',
                item: item
            })
        });
        const data = await res.json();
        if (data.success && data.result && data.result.item_id) {
            item.id = data.result.item_id;
            saveDraftState();
        }
    } catch (e) {
        console.warn('Error adding live transfer item:', e);
    }
}

async function removeLiveTransferItem(item) {
    if (!item || !window.EdycjaConfig || !window.EdycjaConfig.dostawaId) return;
    try {
        await fetch('/magazyn-dostawy/api/live-transfer/remove-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                dostawa_id: window.EdycjaConfig.dostawaId,
                linia: (window.EdycjaConfig && window.EdycjaConfig.linia) || 'AGRO',
                item_id: item.id,
                nr_palety: item.nr_palety
            })
        });
    } catch (e) {
        console.warn('Error removing live transfer item:', e);
    }
}

async function pollLiveTransferStatus() {
    if (!window.EdycjaConfig || !window.EdycjaConfig.dostawaId) return;
    try {
        const res = await fetch(`/magazyn-dostawy/api/live-transfer/status/${window.EdycjaConfig.dostawaId}`);
        const data = await res.json();
        if (data.success && data.result) {
            const statusInfo = data.result;
            let updated = false;

            if (Array.isArray(statusInfo.items)) {
                statusInfo.items.forEach(remoteItem => {
                    const localItem = items.find(i => 
                        (remoteItem.nr_palety && i.nr_palety === remoteItem.nr_palety) ||
                        (remoteItem.id && i.id === remoteItem.id)
                    );
                    if (localItem) {
                        if (remoteItem.accepted !== localItem.accepted || remoteItem.lokalizacja_przyjecia !== localItem.lokalizacja_przyjecia) {
                            localItem.accepted = remoteItem.accepted;
                            localItem.lokalizacja_przyjecia = remoteItem.lokalizacja_przyjecia;
                            updated = true;
                        }
                    }
                });
            }

            if (typeof updateLiveTransferUI === 'function') {
                updateLiveTransferUI(statusInfo);
            }

            if (updated) {
                saveDraftState();
                renderItems();
                updateSaveButtonState();
            }
        }
    } catch (e) {
        console.warn('Error polling live transfer status:', e);
    }
}

function startLiveTransferPolling() {
    if (liveTransferPollTimer) clearInterval(liveTransferPollTimer);
    if (window.EdycjaConfig && window.EdycjaConfig.dostawaId) {
        pollLiveTransferStatus();
        liveTransferPollTimer = setInterval(pollLiveTransferStatus, 3000);
    }
}


