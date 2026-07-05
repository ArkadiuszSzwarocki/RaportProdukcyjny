let locationSuggestTimer = null;
let locationSuggestAbortController = null;
let locationSuggestLastPrefix = '';
let configDataEl = document.getElementById('magazyn-config-data');
window.MAGAZYN_CONFIG = {
    linia: configDataEl ? configDataEl.dataset.linia : '',
    pendingTransferItems: configDataEl ? JSON.parse(configDataEl.dataset.pendingItems || '[]') : []
};
let pendingTransferItems = window.MAGAZYN_CONFIG.pendingTransferItems;
let activeTransferItem = null;

function normalizeLocationCode(value) {
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
        const normalized = normalizeLocationCode(code);
        if (!normalized) {
            return;
        }
        const option = document.createElement('option');
        option.value = normalized;
        dataList.appendChild(option);
    });
}

function queueLocationSuggestions(rawValue) {
    const prefix = normalizeLocationCode(rawValue);
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
        linia: window.MAGAZYN_CONFIG.linia,
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

function handleLocationSuggestInput(inputElement) {
    if (!inputElement) {
        return;
    }
    inputElement.value = normalizeLocationCode(inputElement.value);
    queueLocationSuggestions(inputElement.value);
}

