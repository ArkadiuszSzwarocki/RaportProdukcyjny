/**
 * OSIP TRANSFER NOWY - Logika Dedykowanego Formularza Nowego Transferu
 */

const DRAFT_KEY = 'osip_transfer_nowy_draft_v1';
let scannedItems = [];

document.addEventListener('DOMContentLoaded', () => {
    initRouteSelectors();
    initScanner();
    initDraft();
    initSubmission();
});

/**
 * Wybór karty trasy po kliknięciu
 */
function selectRouteCard(routeVal) {
    const radio = document.querySelector(`input[name="trf_route"][value="${routeVal}"]`);
    if (radio) {
        radio.checked = true;
        radio.dispatchEvent(new Event('change'));
    }
}

/**
 * Obsługa kart wyboru trasy (MS01 -> OSIP, OSIP -> MS01, CUSTOM)
 */
function initRouteSelectors() {
    const routeRadios = document.querySelectorAll('input[name="trf_route"]');
    const customSelectors = document.getElementById('custom-wh-selectors');

    routeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            document.querySelectorAll('.trf-route-card').forEach(card => {
                card.classList.remove('active');
                const indicator = card.querySelector('.trf-route-icon-indicator');
                if (indicator) indicator.textContent = 'radio_button_unchecked';
            });

            const parentCard = e.target.closest('.trf-route-card');
            if (parentCard) {
                parentCard.classList.add('active');
                const indicator = parentCard.querySelector('.trf-route-icon-indicator');
                if (indicator) indicator.textContent = 'check_circle';
            }

            if (e.target.value === 'CUSTOM') {
                if (customSelectors) customSelectors.style.display = 'grid';
            } else {
                if (customSelectors) customSelectors.style.display = 'none';
            }

            saveDraftToStorage();
        });
    });

    const selectSource = document.getElementById('select-custom-source');
    const selectDest = document.getElementById('select-custom-dest');
    if (selectSource) selectSource.addEventListener('change', saveDraftToStorage);
    if (selectDest) selectDest.addEventListener('change', saveDraftToStorage);

    // Pre-selekcja na podstawie parametrów URL
    const urlParams = new URLSearchParams(window.location.search);
    const sourceParam = (urlParams.get('source') || '').toUpperCase();
    const destParam = (urlParams.get('dest') || '').toUpperCase();
    const scopeParam = (urlParams.get('scope') || '').toLowerCase();

    if ((sourceParam === 'OSIP' && destParam === 'MS01') || scopeParam === 'osip') {
        selectRouteCard('OSIP_MS01');
    } else if ((sourceParam === 'MS01' && destParam === 'OSIP') || scopeParam === 'centrala') {
        selectRouteCard('MS01_OSIP');
    }
}

/**
 * Inicjalizacja pola skanera kodów kreskowych / SSCC
 */
function initScanner() {
    const input = document.getElementById('trf-pallet-input');
    const btn = document.getElementById('btn-add-scanned-pallet');
    const notes = document.getElementById('trf-notes-input');

    if (input) {
        input.focus();
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                processPalletScan();
            }
        });
    }

    if (btn) {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            processPalletScan();
        });
    }

    if (notes) {
        notes.addEventListener('input', saveDraftToStorage);
    }
}

let isScanProcessing = false;

/**
 * Przetwarza zeskanowany kod palety (odpytuje API i dodaje do listy)
 */
async function processPalletScan() {
    const input = document.getElementById('trf-pallet-input');
    const statusMsg = document.getElementById('trf-scan-status-msg');
    if (!input) return;

    if (isScanProcessing) {
        return;
    }

    const rawCode = input.value.trim();
    if (!rawCode) {
        showTrfToast('warning', 'Wprowadź lub zeskanuj kod palety.');
        input.focus();
        return;
    }

    const codeUpper = rawCode.toUpperCase();

    // Sprawdź czy paleta nie została już wcześniej dodana do tego formularza
    const exists = scannedItems.some(it => String(it.nr_palety).toUpperCase() === codeUpper);
    if (exists) {
        showTrfToast('warning', `Paleta ${codeUpper} znajduje się już na liście tego zlecenia.`);
        input.value = '';
        input.focus();
        return;
    }

    isScanProcessing = true;
    input.disabled = true;

    if (statusMsg) {
        statusMsg.innerHTML = `<span class="material-icons" style="font-size:16px; color:#2563eb; vertical-align:middle;">sync</span> Wyszukiwanie palety <strong>${escapeHtml(codeUpper)}</strong> w systemie...`;
        statusMsg.style.color = '#2563eb';
    }

    try {
        const resp = await fetch(`/warehouse-v2/api/zaladunki/lookup_pallet?code=${encodeURIComponent(rawCode)}`);
        const data = await resp.json();

        let palletObj = null;

        if (data.success && data.pallet) {
            const p = data.pallet;
            palletObj = {
                pallet_id: p.pallet_id || p.id || null,
                nr_palety: p.nr_palety || codeUpper,
                nazwa_produktu: p.nazwa_produktu || p.productName || p.nazwa || 'Surowiec / Towar',
                typ_palety: p.typ_palety || p.type || 'Surowiec',
                ilosc_kg: parseFloat(p.ilosc_kg || p.amount || p.stan_magazynowy || 0.0)
            };
        } else {
            // W przypadku nieznalezienia w bazie centralnej - pozwalamy dodać tymczasową pozycję ze skanera
            palletObj = {
                pallet_id: null,
                nr_palety: codeUpper,
                nazwa_produktu: 'Paleta Zeskanowana',
                typ_palety: 'Surowiec',
                ilosc_kg: 0.0
            };
        }

        // Re-check unikalności przed dodaniem
        if (!scannedItems.some(it => String(it.nr_palety).toUpperCase() === String(palletObj.nr_palety).toUpperCase())) {
            scannedItems.push(palletObj);
            renderScannedTable();
            saveDraftToStorage();

            if (statusMsg) {
                statusMsg.innerHTML = `<span class="material-icons" style="font-size:16px; color:#16a34a; vertical-align:middle;">check_circle</span> Pomyślnie dodano paletę <strong>${escapeHtml(palletObj.nr_palety)}</strong> (${palletObj.ilosc_kg.toFixed(2)} kg).`;
                statusMsg.style.color = '#16a34a';
            }

            showTrfToast('success', `Dodano paletę ${palletObj.nr_palety}`);
        }
    } catch (err) {
        console.error('Błąd weryfikacji palety:', err);
        // Fallback w razie problemów z siecią
        const fallbackObj = {
            pallet_id: null,
            nr_palety: codeUpper,
            nazwa_produktu: 'Paleta Zeskanowana',
            typ_palety: 'Surowiec',
            ilosc_kg: 0.0
        };
        if (!scannedItems.some(it => String(it.nr_palety).toUpperCase() === String(fallbackObj.nr_palety).toUpperCase())) {
            scannedItems.push(fallbackObj);
            renderScannedTable();
            saveDraftToStorage();
        }
    } finally {
        isScanProcessing = false;
        input.disabled = false;
        input.value = '';
        input.focus();
    }
}

/**
 * Renderuje tabelę z zeskanowanymi paletami oraz przelicza podsumowanie
 */
function renderScannedTable() {
    const tbody = document.getElementById('trf-scanned-tbody');
    const cntEl = document.getElementById('stat-pallets-count');
    const weightEl = document.getElementById('stat-total-weight');
    const submitBtn = document.getElementById('btn-submit-transfer');

    if (!tbody) return;

    let totalWeight = 0.0;
    scannedItems.forEach(it => {
        totalWeight += parseFloat(it.ilosc_kg || 0.0);
    });

    if (cntEl) cntEl.textContent = scannedItems.length;
    if (weightEl) weightEl.textContent = `${totalWeight.toFixed(2)} kg`;

    if (submitBtn) {
        submitBtn.disabled = scannedItems.length === 0;
    }

    if (scannedItems.length === 0) {
        tbody.innerHTML = `
            <tr id="trf-empty-row">
                <td colspan="6" class="trf-empty-state">
                    <span class="material-icons">inventory</span>
                    <div>Brak zeskanowanych palet. Zeskanuj pierwszą paletę powyżej.</div>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = '';
    scannedItems.forEach((item, idx) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight: 800; color: #94a3b8;">#${idx + 1}</td>
            <td><span class="badge-sscc">${escapeHtml(item.nr_palety || '-')}</span></td>
            <td style="font-weight: 800; color: #0f172a;">${escapeHtml(item.nazwa_produktu || '-')}</td>
            <td><span style="background:#f1f5f9; border:1px solid #cbd5e1; padding:3px 8px; border-radius:6px; font-size:12px; font-weight:700;">${escapeHtml(item.typ_palety || 'Surowiec')}</span></td>
            <td style="text-align: right; font-weight: 800; color: #16a34a;">${parseFloat(item.ilosc_kg || 0).toFixed(2)} kg</td>
            <td style="text-align: center;">
                <button type="button" class="btn-remove-row" onclick="removeScannedItem(${idx})" title="Usuń tę paletę ze zlecenia">
                    <span class="material-icons" style="font-size:18px;">delete</span>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

/**
 * Usuwa paletę z listy
 */
function removeScannedItem(idx) {
    if (idx >= 0 && idx < scannedItems.length) {
        const removed = scannedItems.splice(idx, 1);
        renderScannedTable();
        saveDraftToStorage();
        if (removed && removed[0]) {
            showTrfToast('info', `Usunięto paletę ${removed[0].nr_palety} z listy.`);
        }
    }
}

/**
 * Zapisuje wersję roboczą w localStorage
 */
function saveDraftToStorage() {
    try {
        const route = document.querySelector('input[name="trf_route"]:checked')?.value || 'MS01_OSIP';
        const customSource = document.getElementById('select-custom-source')?.value || 'OSIP';
        const customDest = document.getElementById('select-custom-dest')?.value || 'MS01';
        const notes = document.getElementById('trf-notes-input')?.value || '';

        const draft = {
            route,
            customSource,
            customDest,
            notes,
            items: scannedItems,
            updatedAt: new Date().toISOString()
        };

        localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch (e) {
        console.warn('Nie udało się zapisać wersji roboczej transferu:', e);
    }
}

/**
 * Inicjalizacja i przywracanie wersji roboczej z localStorage
 */
function initDraft() {
    const draftAlert = document.getElementById('trf-draft-alert');
    const discardBtn = document.getElementById('btn-discard-draft');

    if (discardBtn) {
        discardBtn.addEventListener('click', () => {
            clearDraftStorage();
            scannedItems = [];
            renderScannedTable();
            if (draftAlert) draftAlert.style.display = 'none';
            showTrfToast('info', 'Odrzucono szkic zlecenia.');
        });
    }

    try {
        const raw = localStorage.getItem(DRAFT_KEY);
        if (!raw) return;

        const draft = JSON.parse(raw);
        if (draft && Array.isArray(draft.items) && draft.items.length > 0) {
            scannedItems = draft.items;

            if (draft.route) {
                const radio = document.querySelector(`input[name="trf_route"][value="${draft.route}"]`);
                if (radio) {
                    radio.checked = true;
                    radio.dispatchEvent(new Event('change'));
                }
            }

            if (draft.notes) {
                const notesEl = document.getElementById('trf-notes-input');
                if (notesEl) notesEl.value = draft.notes;
            }

            if (draftAlert) draftAlert.style.display = 'flex';
            renderScannedTable();
        }
    } catch (e) {
        console.warn('Błąd wczytywania szkicu transferu:', e);
    }
}

function clearDraftStorage() {
    try {
        localStorage.removeItem(DRAFT_KEY);
    } catch (e) {}
}

/**
 * Inicjalizacja wysłania formularza zlecenia transferu
 */
function initSubmission() {
    const submitBtn = document.getElementById('btn-submit-transfer');
    if (!submitBtn) return;

    submitBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        await submitTransferOrder();
    });
}

/**
 * Składa POST na API tworzenia transferu
 */
async function submitTransferOrder() {
    const submitBtn = document.getElementById('btn-submit-transfer');
    if (scannedItems.length === 0) {
        showTrfToast('warning', 'Zeskanuj co najmniej jedną paletę przed utworzeniem zlecenia.');
        return;
    }

    const routeVal = document.querySelector('input[name="trf_route"]:checked')?.value || 'MS01_OSIP';
    let sourceWh = 'MS01';
    let destWh = 'OSIP';

    if (routeVal === 'MS01_OSIP') {
        sourceWh = 'MS01';
        destWh = 'OSIP';
    } else if (routeVal === 'OSIP_MS01') {
        sourceWh = 'OSIP';
        destWh = 'MS01';
    } else if (routeVal === 'CUSTOM') {
        sourceWh = document.getElementById('select-custom-source')?.value || 'OSIP';
        destWh = document.getElementById('select-custom-dest')?.value || 'MS01';
    }

    if (sourceWh === destWh) {
        showTrfToast('warning', 'Magazyn źródłowy i docelowy nie mogą być takie same!');
        return;
    }

    const notesVal = document.getElementById('trf-notes-input')?.value || '';

    const payload = {
        source_warehouse: sourceWh,
        destination_warehouse: destWh,
        notes: notesVal,
        items: scannedItems.map(it => ({
            pallet_id: it.pallet_id || null,
            nr_palety: it.nr_palety,
            product_name: it.nazwa_produktu || 'Surowiec',
            requested_qty: parseFloat(it.ilosc_kg || 0.0),
            unit: 'kg',
            item_type: it.typ_palety || 'Surowiec'
        }))
    };

    try {
        if (submitBtn) submitBtn.disabled = true;

        const resp = await fetch('/osip/api/transfers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(payload)
        });

        const data = await resp.json();

        if (data.success) {
            clearDraftStorage();
            showTrfToast('success', data.message || 'Utworzono zlecenie transferu!');
            setTimeout(() => {
                window.location.href = '/osip/transfers';
            }, 1000);
        } else {
            showTrfToast('error', data.message || 'Nie udało się utworzyć zlecenia transferu.');
            if (submitBtn) submitBtn.disabled = false;
        }
    } catch (err) {
        console.error('Błąd tworzenia zlecenia transferu:', err);
        showTrfToast('error', 'Wystąpił błąd połączenia z serwerem.');
        if (submitBtn) submitBtn.disabled = false;
    }
}

/**
 * Wyświetla toast z powiadomieniem
 */
function showTrfToast(type, message) {
    let container = document.getElementById('trfToastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'trfToastContainer';
        container.className = 'trf-toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `trf-toast toast-${type}`;

    let icon = 'info';
    if (type === 'success') icon = 'check_circle';
    if (type === 'error') icon = 'error_outline';
    if (type === 'warning') icon = 'warning';

    toast.innerHTML = `<span class="material-icons">${icon}</span> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
