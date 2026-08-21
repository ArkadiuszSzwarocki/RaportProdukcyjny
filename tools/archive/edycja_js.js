
    const READ_ONLY_MODE = {{ 'true' if is_readonly_issue else 'false' }};
    const IS_NEW_TRANSFER_FORM = {{ 'true' if not dostawa else 'false' }};
    let items = {{ (dostawa['items']|tojson if dostawa and dostawa.get('items') else '[]')|safe }};
    let formSubmitAttempted = false;
    let copiedRowsInfoByItem = {};
    let palletPickerState = null;
    let pendingDraftToDecide = null;
    let locationSuggestTimer = null;
    let locationSuggestAbortController = null;
    let locationSuggestLastPrefix = '';
    const FORM_DRAFT_KEY = "magazyn_dostawy_draft_{{ linia }}_{{ dostawa.id if dostawa else 'new' }}";
    const KNOWN_SOURCE_LOCATIONS_SET = new Set(({{ lokalizacje|tojson|safe }} || []).map(v => String(v || '').toUpperCase()));

    function notifyReadOnly() {
        if (typeof showToast === 'function') {
            showToast('Status OCZEKUJE: formularz wydania działa w trybie podglądu.', 'warning');
        } else {
            alert('Status OCZEKUJE: formularz wydania działa w trybie podglądu.');
        }
    }

    function generateWZ() {
        const now = new Date();
        const dd = String(now.getDate()).padStart(2, '0');
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const rrrr = now.getFullYear();
        const hh = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');
        return `${dd}${mm}${rrrr}${hh}${min}${ss}`;
    }

    function toggleFlowHelp() {
        const panel = document.getElementById('flowHelpPanel');
        if (!panel) {
            return;
        }
        panel.style.display = panel.style.display === 'none' || !panel.style.display ? 'block' : 'none';
    }

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

    function hideDraftDecisionBanner() {
        const banner = document.getElementById('draftDecisionBanner');
        if (banner) {
            banner.style.display = 'none';
        }
    }

    function showDraftDecisionBanner(draft) {
        const banner = document.getElementById('draftDecisionBanner');
        if (!banner) {
            return;
        }

        const meta = document.getElementById('draftDecisionMeta');
        const savedAt = draft && draft.saved_at ? new Date(draft.saved_at) : null;
        const savedAtText = savedAt && !Number.isNaN(savedAt.getTime())
            ? savedAt.toLocaleString('pl-PL')
            : 'nieznany czas zapisu';
        const itemsCount = draft && Array.isArray(draft.items) ? draft.items.length : 0;

        if (meta) {
            meta.textContent = `Szkic: ${itemsCount} palet, zapis: ${savedAtText}.`;
        }

        banner.style.display = 'block';
    }

    function continueDraftEntry() {
        if (!pendingDraftToDecide) {
            return;
        }
        restoreDraftState(pendingDraftToDecide, { silentToast: false });
        pendingDraftToDecide = null;
        hideDraftDecisionBanner();
        renderItems();
        updateSaveButtonState();
    }

    function startFreshEntry() {
        clearDraftState();
        pendingDraftToDecide = null;
        hideDraftDecisionBanner();

        items = [];
        copiedRowsInfoByItem = {};
        palletPickerState = null;

        const countInput = document.getElementById('pallet_count');
        const targetInput = document.getElementById('lokalizacja_do');
        const scannerInput = document.getElementById('scanner_input');
        const bypassInput = document.getElementById('skip_warehouse_lookup');
        if (countInput) countInput.value = '0';
        if (targetInput) targetInput.value = '';
        if (scannerInput) scannerInput.value = '';
        if (bypassInput) bypassInput.checked = false;

        renderItems();
        updateSaveButtonState();
    }

    function cancelTransferForm(event) {
        if (event && typeof event.preventDefault === 'function') {
            event.preventDefault();
        }

        if (!READ_ONLY_MODE) {
            clearDraftState();
        }

        window.location.href = "{{ url_for('magazyn_dostawy.lista_dostaw', linia=linia) }}";
    }

    function escapeAttr(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function getItemUnit(item) {
        if (!item || !item.packageForm) {
            return '';
        }
        return item.packageForm === 'packaging' ? 'szt' : 'kg';
    }

    function getItemQuantity(item) {
        if (!item) {
            return '';
        }
        const unit = getItemUnit(item);
        let raw = '';
        if (unit === 'szt') {
            raw = item.unitsPerPallet;
        } else if (unit === 'kg') {
            raw = item.netWeight;
        } else {
            raw = item.netWeight || item.unitsPerPallet;
        }
        return (raw === null || raw === undefined || raw === '') ? '' : raw;
    }

    function setItemQuantity(index, value) {
        const normalized = String(value ?? '').trim().replace(',', '.');
        if (normalized === '') {
            items[index].netWeight = '';
            items[index].unitsPerPallet = '';
            return;
        }

        const parsed = parseFloat(normalized);
        if (Number.isNaN(parsed)) {
            return;
        }

        if (getItemUnit(items[index]) === 'szt') {
            items[index].unitsPerPallet = parsed;
            items[index].netWeight = '';
        } else {
            items[index].netWeight = parsed;
            items[index].unitsPerPallet = '';
        }
    }

    function getDefaultSourceSpot() {
        return '';
    }

    function buildEmptyItem(suffix = '') {
        return {
            id: 'MANUAL_' + Date.now() + (suffix ? '_' + suffix : ''),
            productName: '',
            netWeight: '',
            unitsPerPallet: '',
            packageForm: '',
            sourceSpot: getDefaultSourceSpot(),
            nr_palety: '',
            nr_partii: '',
            data_produkcji: '',
            data_przydatnosci: '',
            accepted: false,
            is_manual: true
        };
    }

    function isFilled(value) {
        return String(value ?? '').trim() !== '';
    }

    function isPositiveNumber(value) {
        const parsed = parseFloat(String(value ?? '').replace(',', '.'));
        return !Number.isNaN(parsed) && parsed > 0;
    }

    function isItemComplete(item) {
        const bypassLookup = isWarehouseLookupBypassed();
        return (
            isFilled(item && item.productName)
            && (bypassLookup || isFilled(item && item.sourceSpot))
            && isFilled(getItemUnit(item))
            && isPositiveNumber(getItemQuantity(item))
        );
    }

    function normalizeLocation(value) {
        return String(value || '').trim().toUpperCase();
    }

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

    function renderLocationSuggestionOptions(suggestions) {
        const dataList = ensureLocationSuggestionsList();
        dataList.innerHTML = '';

        (suggestions || []).forEach(code => {
            const normalizedCode = normalizeLocation(code);
            if (!normalizedCode) {
                return;
            }
            const option = document.createElement('option');
            option.value = normalizedCode;
            dataList.appendChild(option);
        });
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

    async function fetchLocationSuggestions(prefix) {
        if (locationSuggestAbortController) {
            locationSuggestAbortController.abort();
        }

        locationSuggestAbortController = new AbortController();
        const query = new URLSearchParams({
            linia: '{{ linia }}',
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

    let scannerSuggestTimer = null;
    let scannerSuggestAbortController = null;

    function queueScannerSuggestions(value) {
        if (scannerSuggestTimer) clearTimeout(scannerSuggestTimer);
        const prefix = (value || '').trim();
        if (prefix.length < 2) return;
        scannerSuggestTimer = setTimeout(() => fetchScannerSuggestions(prefix), 250);
    }

    async function fetchScannerSuggestions(prefix) {
        if (scannerSuggestAbortController) scannerSuggestAbortController.abort();
        scannerSuggestAbortController = new AbortController();
        const bypassLookup = isWarehouseLookupBypassed();
        try {
            const res = await fetch(`/magazyn-dostawy/api/dostepne-palety?linia={{ linia }}&prefix=${encodeURIComponent(prefix)}&skip_warehouse_lookup=${bypassLookup ? '1' : '0'}`, {
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

    function handleLocationSuggestInput(inputElement) {
        if (!inputElement) {
            return;
        }
        inputElement.value = normalizeLocation(inputElement.value);
        queueLocationSuggestions(inputElement.value);
    }

    function isSameLocation(left, right) {
        const l = normalizeLocation(left);
        const r = normalizeLocation(right);
        return l !== '' && r !== '' && l === r;
    }

    function isRouteConflictLocation(sourceLoc, targetLoc) {
        const source = normalizeLocation(sourceLoc);
        const target = normalizeLocation(targetLoc);
        if (source === '' || target === '') {
            return false;
        }

        if (source === target) {
            return true;
        }

        // Treat prefix variants as the same route family, e.g. BF_MS01 / BF_MS01_x.
        return source.startsWith(target) || target.startsWith(source);
    }

    function isKnownSourceLocation(value) {
        const loc = normalizeLocation(value);
        if (!loc) {
            return false;
        }

        if (KNOWN_SOURCE_LOCATIONS_SET.has(loc)) {
            return true;
        }

        const rackMatch = loc.match(/^R0([1-7])(\d{2})(\d{2})$/);
        if (rackMatch) {
            return true;
        }

        const osipMatch = loc.match(/^OS(\d{2})$/);
        if (osipMatch) {
            const nr = parseInt(osipMatch[1], 10);
            return nr >= 1 && nr <= 77;
        }

        const bbMatch = loc.match(/^BB(\d{2})$/);
        if (bbMatch) {
            const nr = parseInt(bbMatch[1], 10);
            return nr >= 1 && nr <= 24;
        }

        const mzSimple = loc.match(/^MZ(\d{2})$/);
        if (mzSimple) {
            const nr = parseInt(mzSimple[1], 10);
            return nr >= 1 && nr <= 6;
        }

        // Magazyn Dodatków (MD / MDO)
        if (loc.startsWith('MD') || loc.startsWith('MDO')) {
            return true;
        }

        return loc === 'MZ05-01' || loc === 'MZ06-01';
    }

    function getUnknownSourceLocations() {
        if (isWarehouseLookupBypassed()) return [];
        const unique = new Set();
        items.forEach(item => {
            const source = normalizeLocation(item && item.sourceSpot);
            if (source && !isKnownSourceLocation(source)) {
                unique.add(source);
            }
        });
        return Array.from(unique);
    }

    function getValidationBorderStyle(hasError) {
        if (hasError && formSubmitAttempted) {
            return 'border: 2px solid #dc2626; box-shadow: inset 0 0 0 1px rgba(220,38,38,0.08); background-color: #fff1f2;';
        }
        return 'border: 1px solid #e2e8f0;';
    }

    function getItemValidationMap(item, targetLoc) {
        const sourceLoc = normalizeLocation(item && item.sourceSpot);
        const unit = getItemUnit(item);
        const quantity = getItemQuantity(item);

        const bypassLookup = isWarehouseLookupBypassed();

        const sourceInvalid =
            (!bypassLookup && !isFilled(sourceLoc))
            || (!bypassLookup && isFilled(sourceLoc) && !isKnownSourceLocation(sourceLoc))
            || isRouteConflictLocation(sourceLoc, targetLoc);

        return {
            productName: !isFilled(item && item.productName),
            sourceSpot: sourceInvalid,
            quantity: !isPositiveNumber(quantity),
            unit: !isFilled(unit),
            nr_partii: false,
            data_produkcji: false,
            data_przydatnosci: false,
        };
    }

    function getCurrentTargetLocation() {
        const targetInput = document.getElementById('lokalizacja_do');
        return normalizeLocation(targetInput ? targetInput.value : '');
    }

    function isWarehouseLookupBypassed() {
        const bypassInput = document.getElementById('skip_warehouse_lookup');
        return !!(bypassInput && bypassInput.checked);
    }

    function getItemCopyMarkerKey(item, index) {
        const rawId = item && item.id;
        if (rawId !== undefined && rawId !== null && String(rawId).trim() !== '') {
            return String(rawId);
        }
        return `idx_${index}`;
    }

    function getCopiedFromNumber(item, index) {
        const key = getItemCopyMarkerKey(item, index);
        const raw = copiedRowsInfoByItem[key];
        const parsed = parseInt(raw, 10);
        return Number.isNaN(parsed) ? null : parsed;
    }

    function setCopiedFromNumber(item, index, fromRowNumber) {
        const key = getItemCopyMarkerKey(item, index);
        copiedRowsInfoByItem[key] = parseInt(fromRowNumber, 10);
    }

    function clearCopiedMarker(item, index) {
        const key = getItemCopyMarkerKey(item, index);
        if (Object.prototype.hasOwnProperty.call(copiedRowsInfoByItem, key)) {
            delete copiedRowsInfoByItem[key];
        }
    }

    function isItemPalletSlotEmpty(item) {
        if (!item) {
            return false;
        }

        const hasBoundPallet = isFilled(item.sourcePalletId) || isFilled(item.sourcePalletNo);
        if (hasBoundPallet) {
            return false;
        }

        return !isFilled(item.productName)
            && !isFilled(getItemQuantity(item))
            && !isFilled(getItemUnit(item))
            && !isFilled(item.nr_partii)
            && !isFilled(item.data_produkcji)
            && !isFilled(item.data_przydatnosci);
    }

    function canSaveTransfer() {
        if (READ_ONLY_MODE) {
            return false;
        }

        const targetInput = document.getElementById('lokalizacja_do');
        const targetLoc = targetInput ? targetInput.value : '';

        if (!isFilled(targetLoc)) {
            return false;
        }

        if (!Array.isArray(items) || items.length === 0) {
            return false;
        }

        const hasSourceTargetConflict = items.some(item => isRouteConflictLocation(item && item.sourceSpot, targetLoc));
        if (hasSourceTargetConflict) {
            return false;
        }

        if (getUnknownSourceLocations().length > 0) {
            return false;
        }

        return items.every(isItemComplete);
    }

    function getSaveBlockers() {
        if (READ_ONLY_MODE) {
            return ['Status OCZEKUJE: formularz wydania jest tylko do podglądu.'];
        }

        const blockers = [];
        
        if (!Array.isArray(items) || items.length === 0) {
            blockers.push('Dodaj przynajmniej jedną paletę.');
            return blockers;
        }

        const targetInput = document.getElementById('lokalizacja_do');
        const targetLoc = targetInput ? targetInput.value : '';

        const conflictingItems = items.filter(item => isRouteConflictLocation(item && item.sourceSpot, targetLoc));
        if (conflictingItems.length > 0) {
            blockers.push(`Operacja niemożliwa: ${conflictingItems.length} palet ma lokalizację źródłową kolidującą z Dokąd (${normalizeLocation(targetLoc)}).`);
        }

        const unknownSourceLocations = getUnknownSourceLocations();
        if (unknownSourceLocations.length > 0) {
            const preview = unknownSourceLocations.slice(0, 3).join(', ');
            const suffix = unknownSourceLocations.length > 3 ? ', ...' : '';
            blockers.push(`Nieznane lokalizacje źródłowe: ${preview}${suffix}. Popraw lokalizacje przed zapisem.`);
        }

        const incompleteCount = items.filter(item => !isItemComplete(item)).length;
        if (incompleteCount > 0) {
            blockers.push(`Uzupełnij wszystkie pola w każdej palecie. Niekompletne: ${incompleteCount}.`);
        }

        return blockers;
    }

    function renderSaveInfo(saveInfo, variant, messages) {
        if (!saveInfo) {
            return;
        }

        if (!Array.isArray(messages) || messages.length === 0) {
            saveInfo.style.display = 'none';
            saveInfo.innerHTML = '';
            return;
        }

        const isSuccess = variant === 'success';
        saveInfo.style.display = 'block';
        saveInfo.style.background = isSuccess ? '#ecfdf5' : '#fff7ed';
        saveInfo.style.border = `1px solid ${isSuccess ? '#86efac' : '#fed7aa'}`;
        saveInfo.style.color = isSuccess ? '#166534' : '#9a3412';

        const marker = isSuccess ? '✓' : '•';
        saveInfo.innerHTML = messages
            .map(msg => `<div style="line-height: 1.35; margin: 1px 0;">${marker} ${escapeAttr(msg)}</div>`)
            .join('');
    }

    function updateSaveButtonState() {
        const saveBtn = document.getElementById('save_transfer_btn');
        const saveInfo = document.getElementById('save_transfer_info');
        const targetInput = document.getElementById('lokalizacja_do');
        if (!saveBtn) {
            return;
        }

        const blockers = getSaveBlockers();
        const enabled = blockers.length === 0;
        saveBtn.disabled = !enabled;
        saveBtn.style.opacity = enabled ? '1' : '0.55';
        saveBtn.style.cursor = enabled ? 'pointer' : 'not-allowed';

        const targetLoc = targetInput ? targetInput.value : '';
        const highlightTarget = !isFilled(targetLoc) && Array.isArray(items) && items.length > 0;
        if (targetInput) {
            targetInput.style.border = highlightTarget ? '2px solid #dc2626' : '1px solid #e2e8f0';
            targetInput.style.boxShadow = highlightTarget ? 'inset 0 0 0 1px rgba(220,38,38,0.08)' : 'none';
        }

        if (enabled) {
            saveBtn.title = '';
            renderSaveInfo(saveInfo, 'success', ['Formularz kompletny. Możesz kliknąć PRZESUŃ.']);
        } else {
            saveBtn.title = blockers[0] || 'Przycisk jest tymczasowo zablokowany.';
            renderSaveInfo(saveInfo, 'warning', blockers);
        }
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
            if (orderRefInput && draft.order_ref) orderRefInput.value = draft.order_ref;
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

    function renderItems() {
        const tbody = document.querySelector('#itemsTable tbody');
        const noItems = document.getElementById('noItemsMsg');
        const disabledAttr = READ_ONLY_MODE ? 'disabled' : '';
        const targetLoc = getCurrentTargetLocation();
        tbody.innerHTML = '';
        
        if (items.length === 0) {
            noItems.style.display = 'block';
            copiedRowsInfoByItem = {};
            
            document.getElementById('th_paleta').style.display = 'none';
            document.getElementById('th_partia').style.display = 'none';
            document.getElementById('th_prod').style.display = 'none';
            document.getElementById('th_przyd').style.display = 'none';
            
            updateSaveButtonState();
            return;
        }
        noItems.style.display = 'none';

        const hasManual = items.some(it => it.is_manual);
        const anyHasPaleta = hasManual || items.some(it => isFilled(it.nr_palety));
        const anyHasPartia = hasManual || items.some(it => isFilled(it.nr_partii));
        const anyHasProd = hasManual || items.some(it => isFilled(it.data_produkcji));
        const anyHasPrzyd = hasManual || items.some(it => isFilled(it.data_przydatnosci));

        document.getElementById('th_paleta').style.display = anyHasPaleta ? 'table-cell' : 'none';
        document.getElementById('th_partia').style.display = anyHasPartia ? 'table-cell' : 'none';
        document.getElementById('th_prod').style.display = anyHasProd ? 'table-cell' : 'none';
        document.getElementById('th_przyd').style.display = anyHasPrzyd ? 'table-cell' : 'none';

        items.forEach((item, index) => {
            const row = document.createElement('tr');
            row.style.background = item.is_manual ? '#f0fdf4' : (index % 2 === 0 ? '#fff' : '#fcfcfc');
            row.style.borderBottom = '2px solid #e2e8f0';

            const quantityValue = getItemQuantity(item);
            const unitValue = getItemUnit(item);
            const validation = getItemValidationMap(item, targetLoc);
            const productBorderStyle = getValidationBorderStyle(validation.productName);
            const sourceBorderStyle = getValidationBorderStyle(validation.sourceSpot);
            const quantityBorderStyle = getValidationBorderStyle(validation.quantity);
            const unitBorderStyle = getValidationBorderStyle(validation.unit);
            const batchBorderStyle = getValidationBorderStyle(validation.nr_partii);
            const prodDateBorderStyle = getValidationBorderStyle(validation.data_produkcji);
            const expiryDateBorderStyle = getValidationBorderStyle(validation.data_przydatnosci);
            const copiedFromNumber = getCopiedFromNumber(item, index);
            const copyButtonHtml = index > 0
                ? `<button ${disabledAttr} onclick="copyItem(${index})" title="Kopiuj dane z palety nr ${index}" style="background:none; border:none; color:#0ea5e9; cursor:pointer;">
                        <span class="material-icons" style="font-size:20px;">content_copy</span>
                   </button>`
                : '';
            const showWarning = (hasErr) => (hasErr && formSubmitAttempted) ? `<span class="material-icons" style="color: #dc2626; font-size: 16px; position: absolute; right: 18px; top: 17px; pointer-events: none;">warning</span>` : '';

            row.innerHTML = `
                <td style="padding: 10px 20px; font-size: 13px; color: #64748b; vertical-align: middle; font-weight: 800; white-space: nowrap;">
                    ${index + 1}
                </td>
                <td style="padding: 8px 10px; border: none; position: relative;">
                    ${copiedFromNumber ? `<div style="font-size: 10px; font-weight: 700; color: #b91c1c; margin-bottom: 4px;">Skopiowano z palety nr ${copiedFromNumber}</div>` : ''}
                    ${showWarning(validation.productName)}
                    <input type="text" ${disabledAttr} value="${escapeAttr(item.productName || '')}" onchange="updateItem(${index}, 'productName', this.value)"
                           list="productsList" placeholder="Wybierz produkt"
                           style="width: 100%; height: 34px; ${productBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 13px; font-weight: 700; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; position: relative;">
                    ${showWarning(validation.sourceSpot)}
                      <input type="text" ${disabledAttr} value="${escapeAttr(item.sourceSpot || '')}" onchange="updateItem(${index}, 'sourceSpot', this.value.toUpperCase())"
                          oninput="handleLocationSuggestInput(this)" onfocus="queueLocationSuggestions(this.value)" list="locationSuggestionsList" autocomplete="off"
                           placeholder="np. BF_MS01"
                           style="width: 100%; height: 34px; ${sourceBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 700; text-transform: uppercase; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; position: relative;">
                    ${showWarning(validation.quantity)}
                    <input type="number" ${disabledAttr} value="${escapeAttr(quantityValue)}"
                           onchange="updateItem(${index}, 'quantity', this.value)" placeholder=""
                           style="width: 100%; height: 34px; ${quantityBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 13px; text-align: right; font-weight: 700; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; position: relative;">
                    ${showWarning(validation.unit)}
                    <select ${disabledAttr} onchange="updateItem(${index}, 'unit', this.value)"
                            style="width: 100%; height: 34px; ${unitBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 13px; font-weight: 700; box-sizing: border-box; min-width: 0; background: white;">
                        <option value="" ${unitValue === '' ? 'selected' : ''}>--</option>
                        <option value="kg" ${unitValue === 'kg' ? 'selected' : ''}>kg</option>
                        <option value="szt" ${unitValue === 'szt' ? 'selected' : ''}>szt</option>
                    </select>
                </td>
                <td style="padding: 8px 10px; border: none; ${anyHasPaleta ? '' : 'display:none;'}">
                    <input type="text" ${disabledAttr} value="${escapeAttr(item.nr_palety || '')}" onchange="updateItem(${index}, 'nr_palety', this.value.toUpperCase())"
                           placeholder="Nr SSCC"
                           style="width: 100%; height: 34px; border: 1px solid #e2e8f0; border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 600; box-sizing: border-box; min-width: 0; text-transform: uppercase;">
                </td>
                <td style="padding: 8px 10px; border: none; ${anyHasPartia ? '' : 'display:none;'}">
                    <input type="text" ${disabledAttr} value="${escapeAttr(item.nr_partii || '')}" onchange="updateItem(${index}, 'nr_partii', this.value)"
                           placeholder="Nr partii"
                           style="width: 100%; height: 34px; ${batchBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 600; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; ${anyHasProd ? '' : 'display:none;'}">
                    <input type="date" ${disabledAttr} value="${escapeAttr(item.data_produkcji || '')}" onchange="updateItem(${index}, 'data_produkcji', this.value)"
                           title="Data produkcji"
                           style="width: 100%; height: 34px; ${prodDateBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 600; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; ${anyHasPrzyd ? '' : 'display:none;'}">
                    <input type="date" ${disabledAttr} value="${escapeAttr(item.data_przydatnosci || '')}" onchange="updateItem(${index}, 'data_przydatnosci', this.value)"
                           title="Data przydatności"
                           style="width: 100%; height: 34px; ${expiryDateBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 600; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 10px 20px; text-align: center; vertical-align: middle;">
                    <div style="display: inline-flex; align-items: center; gap: 6px;">
                        ${copyButtonHtml}
                        <button ${disabledAttr} onclick="removeItem(${index})" title="Usuń paletę nr ${index + 1}" style="background:none; border:none; color:#ef4444; cursor:pointer;">
                            <span class="material-icons" style="font-size:20px;">delete</span>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });

        updateSaveButtonState();
    }

    const wszystkieProdukty = {{ wszystkie_produkty|tojson|safe }};

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

    function addEmptyRow() {
        if (READ_ONLY_MODE) {
            notifyReadOnly();
            return;
        }
        items.push(buildEmptyItem());
        const countInput = document.getElementById('pallet_count');
        countInput.value = items.length;
        saveDraftState();
        renderItems();
    }

    function copyItem(index) {
        if (READ_ONLY_MODE) {
            notifyReadOnly();
            return;
        }
        if (index <= 0) {
            return;
        }

        const source = items[index - 1];
        const target = items[index];
        if (!source || !target) {
            return;
        }

        target.productName = source.productName || '';
        target.nr_partii = source.nr_partii || '';
        target.data_produkcji = source.data_produkcji || '';
        target.data_przydatnosci = source.data_przydatnosci || '';
        const sourceUnit = getItemUnit(source);
        if (sourceUnit === 'szt') {
            target.packageForm = 'packaging';
        } else if (sourceUnit === 'kg') {
            target.packageForm = 'bags';
        } else {
            target.packageForm = '';
        }
        target.sourceSpot = source.sourceSpot || getDefaultSourceSpot();

        const copiedQty = getItemQuantity(source);
        if (!(copiedQty === '' || copiedQty === null || copiedQty === undefined)) {
            if (getItemUnit(source) === 'szt') {
                target.unitsPerPallet = copiedQty;
                target.netWeight = '';
            } else {
                target.netWeight = copiedQty;
                target.unitsPerPallet = '';
            }
        } else {
            target.netWeight = '';
            target.unitsPerPallet = '';
        }

        setCopiedFromNumber(target, index, index);

        saveDraftState();
        renderItems();
    }

    function normalizePalletKey(value) {
        return String(value || '').trim().toUpperCase();
    }

    function getPalletReservationKeyFromItem(item) {
        if (!item) {
            return '';
        }

        const palletNo = normalizePalletKey(item.sourcePalletNo || item.nr_palety);
        if (palletNo) {
            return `NR:${palletNo}`;
        }

        const palletId = item.sourcePalletId;
        const scannedType = normalizePalletKey(item.scannedType || item.type);
        if (palletId !== undefined && palletId !== null && String(palletId).trim() !== '' && scannedType) {
            return `ID:${scannedType}:${String(palletId).trim()}`;
        }

        return '';
    }

    function getPalletReservationKeyFromPallet(pal) {
        if (!pal) {
            return '';
        }

        const palletNo = normalizePalletKey(pal.nr_palety);
        if (palletNo) {
            return `NR:${palletNo}`;
        }

        const palletId = pal.id;
        const scannedType = normalizePalletKey(pal.type);
        if (palletId !== undefined && palletId !== null && String(palletId).trim() !== '' && scannedType) {
            return `ID:${scannedType}:${String(palletId).trim()}`;
        }

        return '';
    }

    function createItemFromPallet(pal, idx = 0) {
        const scannedType = String(pal.type || '').toLowerCase();
        const rawQty = pal.stan_magazynowy;
        const parsedQty = parseFloat(String(rawQty ?? '').replace(',', '.'));
        const qty = Number.isNaN(parsedQty) ? '' : parsedQty;
        const isPackaging = scannedType === 'opakowanie';

        return {
            id: String(pal.id) + '_' + Date.now() + '_' + idx,
            sourcePalletId: pal.id,
            sourcePalletNo: pal.nr_palety || '',
            productName: pal.nazwa || '',
            netWeight: isPackaging ? '' : qty,
            unitsPerPallet: isPackaging ? qty : '',
            packageForm: isPackaging ? 'packaging' : 'bags',
            sourceSpot: pal.lokalizacja || getDefaultSourceSpot(),
            nr_partii: pal.nr_partii || '',
            data_produkcji: pal.data_produkcji || '',
            data_przydatnosci: pal.data_przydatnosci || '',
            accepted: false,
            scannedType: pal.type || ''
        };
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

    function handlePalletSelectionEscape(event) {
        if (event.key !== 'Escape') {
            return;
        }

        const modal = document.getElementById('palletSelectModal');
        if (modal && modal.style.display === 'flex') {
            closePalletSelectionModal();
        }
    }

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

    function updatePalletSelectionSearch(value) {
        if (!palletPickerState) {
            return;
        }
        palletPickerState.searchTerm = String(value || '');
        renderPalletSelectionModal();
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
            const res = await fetch(`/magazyn-dostawy/api/dostepne-palety?linia={{ linia }}&prefix=${encodeURIComponent(code)}&skip_warehouse_lookup=${bypassLookup ? '1' : '0'}`);
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
            id: "{{ dostawa.id if dostawa else '' }}",
            order_ref: orderRef,
            lokalizacja_do: targetLoc,
            linia: "{{ linia }}",
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
            showToast('Zapisano pomyślnie!', 'success');
            if (typeof window.refreshSidebarBadges === 'function') {
                window.refreshSidebarBadges();
            }
        } else {
            showToast('Błąd: ' + data.error, 'danger');
        }
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
            });
        }
        if (bypassInput) {
            bypassInput.addEventListener('change', saveDraftState);
        }
        if (ref) {
            ref.addEventListener('change', saveDraftState);
            ref.addEventListener('input', saveDraftState);
        }
        
        const datalist = document.createElement('datalist');
        datalist.id = 'productsList';
        wszystkieProdukty.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p;
            datalist.appendChild(opt);
        });
        document.body.appendChild(datalist);

        if (IS_NEW_TRANSFER_FORM && !READ_ONLY_MODE) {
            const draftMode = getDraftModeFromUrl();

            if (draftMode === 'new') {
                clearDraftState();
            } else {
                const storedDraft = getStoredDraftState();
                if (hasDraftItems(storedDraft)) {
                    restoreDraftState(storedDraft, { silentToast: false });
                }
            }
        } else {
            restoreDraftState();
        }
        
        renderItems();
        updateSaveButtonState();

        if (!READ_ONLY_MODE) {
            window.addEventListener('beforeunload', saveDraftState);
        }
    });
