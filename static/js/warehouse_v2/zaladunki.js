/**
 * Kontroler UI dla Wydań Zewnętrznych na Samochód (Załadunki ZZA/ZZL)
 * Odpowiedzialność: Obsługa skanera Zebra/kamery, lista wielu palet na załadunek,
 * natychmiastowe czyszczenie pola po skanie, autozapis draftu i rejestracja wyjazdu.
 */

let scannedPallets = [];
const DRAFT_STORAGE_KEY = 'zaladunki_vehicle_dispatch_draft_v2';

document.addEventListener('DOMContentLoaded', function () {
    initScannerListeners();
    initTransportAutoSaveListeners();
    loadDispatchDraft();
});

/**
 * Inicjalizuje nasłuchiwacze dla pola skanera kodów.
 */
function initScannerListeners() {
    const scanInput = document.getElementById('palletScanInput');
    const clearBtn = document.getElementById('clearScanBtn');

    if (!scanInput) return;

    scanInput.focus();

    // Pokazuj/ukryj przycisk czyszczenia
    scanInput.addEventListener('input', function () {
        if (clearBtn) {
            clearBtn.style.display = this.value.length > 0 ? 'block' : 'none';
        }
    });

    // Obsługa sprzętowych czytników kodów kreskowych (wysyłających Enter)
    scanInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            handlePalletScanLookup();
        }
    });
}

/**
 * Inicjalizuje automatyczny zapis danych transportowych przy zmianie pól.
 */
function initTransportAutoSaveListeners() {
    const fieldIds = [
        'dispatchVehicleReg',
        'dispatchDriver',
        'dispatchCustomer',
        'dispatchWz',
        'dispatchNotes'
    ];

    fieldIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', saveDispatchDraft);
            el.addEventListener('change', saveDispatchDraft);
        }
    });
}

/**
 * Czyści pole skanera i ustawia fokus.
 */
function clearPalletScanInput() {
    const scanInput = document.getElementById('palletScanInput');
    const clearBtn = document.getElementById('clearScanBtn');
    const statusMsg = document.getElementById('palletScanStatus');

    if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
    }
    if (clearBtn) clearBtn.style.display = 'none';
    if (statusMsg) {
        statusMsg.innerHTML = '<span class="material-icons" style="font-size:16px; color:#2563eb;">qr_code_scanner</span> Gotowy do skanowania czytnikiem lub aparatem.';
        statusMsg.style.color = '#64748b';
    }
}

/**
 * Główna funkcja wyszukiwania i dodawania zeskanowanej palety do listy załadunku.
 */
async function handlePalletScanLookup(e) {
    if (e && e.preventDefault) e.preventDefault();

    const scanInput = document.getElementById('palletScanInput');
    const statusMsg = document.getElementById('palletScanStatus');
    const scanBtn = document.getElementById('scanLookupBtn');

    if (!scanInput) return;
    const code = (scanInput.value || '').trim();

    if (!code) {
        showZaladunkiToast('warning', 'Wpisz lub zeskanuj kod palety (SSCC, QR lub numer).');
        scanInput.focus();
        return;
    }

    if (statusMsg) {
        statusMsg.innerHTML = `<span class="material-icons" style="font-size:16px; animation:spin 1s linear infinite;">sync</span> Szukanie palety: <strong>${code}</strong>...`;
        statusMsg.style.color = '#2563eb';
    }

    if (scanBtn) scanBtn.disabled = true;

    try {
        const linia = (document.getElementById('currentWarehouseLine')?.value || 'AGRO').toUpperCase();
        const resp = await fetch('/warehouse-v2/api/zaladunki/lookup-pallet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code, linia: linia })
        });

        const data = await resp.json();

        if (!data.success || !data.pallet) {
            if (statusMsg) {
                statusMsg.innerHTML = `<span class="material-icons" style="font-size:16px; color:#ef4444;">error</span> ${data.message || 'Nie znaleziono palety w magazynie.'}`;
                statusMsg.style.color = '#dc2626';
            }
            showZaladunkiToast('error', data.message || 'Nie znaleziono palety w magazynie');
            scanInput.select();
            return;
        }

        const p = data.pallet;
        const palletCode = String(p.nr_palety || p.displayId || code).trim();

        // Sprawdź czy paleta nie znajduje się już na liście załadunku
        const alreadyExists = scannedPallets.some(item => {
            const itemCode = String(item.nr_palety || item.displayId || '').trim();
            return (item.pallet_id && item.pallet_id === p.id && item.src_table === p.src_table) ||
                   (itemCode && itemCode.toUpperCase() === palletCode.toUpperCase());
        });

        if (alreadyExists) {
            showZaladunkiToast('warning', `Paleta ${palletCode} jest już na liście tego załadunku!`);
            if (statusMsg) {
                statusMsg.innerHTML = `<span class="material-icons" style="font-size:16px; color:#d97706;">warning</span> Paleta <strong>${palletCode}</strong> jest już dodana do załadunku.`;
                statusMsg.style.color = '#d97706';
            }
            // Wyczyść pole skanera i pozostaw fokus
            clearPalletScanInput();
            return;
        }

        // Dodaj nową paletę do listy
        const newPallet = {
            pallet_id: p.id,
            nr_palety: palletCode,
            displayId: p.displayId || palletCode,
            nazwa_produktu: p.productName || 'Brak nazwy',
            typ_palety: p.type || 'Surowiec',
            linia: p.linia || linia,
            src_table: p.src_table || '',
            ilosc_kg: parseFloat(p.amount || 0.0),
            max_kg: parseFloat(p.amount || 0.0),
            lokalizacja: p.location || '-',
            nr_partii: p.batch || '-'
        };

        scannedPallets.push(newPallet);

        // Natychmiast wyczyść pole skanera dla kolejnego skanu
        clearPalletScanInput();

        // Zaktualizuj widok tabeli palet i podsumowania
        renderScannedPalletsTable();
        saveDispatchDraft();
        playSuccessBeep();

        if (statusMsg) {
            statusMsg.innerHTML = `<span class="material-icons" style="font-size:16px; color:#16a34a;">check_circle</span> Dodano do załadunku: <strong>${newPallet.nazwa_produktu}</strong> (${newPallet.displayId})`;
            statusMsg.style.color = '#16a34a';
        }

        showZaladunkiToast('success', `Dodano paletę: ${newPallet.displayId} (${newPallet.ilosc_kg.toFixed(2)} kg)`);

    } catch (err) {
        console.error('Błąd skanowania palety:', err);
        if (statusMsg) {
            statusMsg.innerHTML = '<span class="material-icons" style="font-size:16px; color:#ef4444;">wifi_off</span> Błąd połączenia z serwerem.';
            statusMsg.style.color = '#dc2626';
        }
        showZaladunkiToast('error', 'Wystąpił błąd połączenia z serwerem.');
    } finally {
        if (scanBtn) scanBtn.disabled = false;
    }
}

/**
 * Renderuje tabelę ze zeskanowanymi paletami na ten załadunek.
 */
function renderScannedPalletsTable() {
    const tbody = document.getElementById('scannedPalletsTbody');
    const tfoot = document.getElementById('scannedPalletsTfoot');
    if (!tbody) return;

    const count = scannedPallets.length;
    let totalWeight = 0.0;

    scannedPallets.forEach(p => {
        totalWeight += parseFloat(p.ilosc_kg || 0.0);
    });

    // Aktualizacja liczników i KPI
    document.getElementById('kpiCurrentPalletCount').innerText = count;
    document.getElementById('kpiCurrentTotalWeight').innerText = totalWeight.toFixed(2);
    document.getElementById('badgePalletCount').innerText = count;
    document.getElementById('badgeTotalWeight').innerText = totalWeight.toFixed(2);
    document.getElementById('tfootTotalWeight').innerText = `${totalWeight.toFixed(2)} kg`;
    document.getElementById('tfootPalletCount').innerText = `${count} palet`;

    const submitBtn = document.getElementById('btnSubmitDispatch');
    const submitText = document.getElementById('submitBtnText');
    if (submitBtn && submitText) {
        if (count > 0) {
            submitBtn.disabled = false;
            submitText.innerText = `ZATWIERDŹ ZAŁADUNEK NA SAMOCHÓD (${count} ${count === 1 ? 'paleta' : 'palet'} • ${totalWeight.toFixed(2)} kg)`;
        } else {
            submitBtn.disabled = true;
            submitText.innerText = 'ZATWIERDŹ ZAŁADUNEK NA SAMOCHÓD (0 palet)';
        }
    }

    if (count === 0) {
        tbody.innerHTML = `
            <tr id="emptyScannedRow">
                <td colspan="8" style="text-align: center; padding: 36px 15px; color: #94a3b8; font-weight: 700;">
                    <span class="material-icons" style="font-size: 36px; display: block; margin-bottom: 6px; color: #cbd5e1;">qr_code_scanner</span>
                    Brak zeskanowanych palet na ten załadunek.<br>
                    <span style="font-size: 12px; font-weight: 500;">Zeskanuj kod kreskowy lub SSCC powyżej, aby dodać paletę do załadunku.</span>
                </td>
            </tr>
        `;
        if (tfoot) tfoot.style.display = 'none';
        return;
    }

    if (tfoot) tfoot.style.display = 'table-footer-group';

    tbody.innerHTML = '';
    scannedPallets.forEach((p, idx) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight: 800; color: #94a3b8;">#${idx + 1}</td>
            <td>
                <span class="badge-pallet">${escapeHtml(p.displayId || p.nr_palety)}</span>
            </td>
            <td style="font-weight: 800; color: #0f172a;">
                ${escapeHtml(p.nazwa_produktu)}
            </td>
            <td>
                <span class="badge-type-line">${escapeHtml(p.typ_palety)} • ${escapeHtml(p.linia)}</span>
            </td>
            <td style="text-align: right;">
                <input type="number" step="0.01" min="0.01" class="zaladunki-pallet-weight-input"
                       value="${parseFloat(p.ilosc_kg || 0).toFixed(2)}"
                       data-index="${idx}"
                       onchange="updatePalletWeight(${idx}, this.value)"
                       title="Edytuj ilość ładowaną z tej palety">
            </td>
            <td style="font-family: monospace; font-weight: 700; color: #475569;">
                ${escapeHtml(p.nr_partii || '-')}
            </td>
            <td style="font-weight: 700; color: #475569;">
                ${escapeHtml(p.lokalizacja || '-')}
            </td>
            <td style="text-align: center;">
                <button type="button" class="btn-remove-pallet" onclick="removePalletFromList(${idx})" title="Usuń paletę z tego załadunku">
                    <span class="material-icons" style="font-size: 18px;">delete</span>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

/**
 * Aktualizuje wagę konkretnej palety na liście załadunku.
 */
function updatePalletWeight(index, newWeight) {
    const w = parseFloat(newWeight);
    if (!isNaN(w) && w > 0 && scannedPallets[index]) {
        scannedPallets[index].ilosc_kg = w;
        renderScannedPalletsTable();
        saveDispatchDraft();
    }
}

/**
 * Usuwa wybraną paletę z listy załadunku.
 */
function removePalletFromList(index) {
    if (scannedPallets[index]) {
        const removed = scannedPallets.splice(index, 1)[0];
        renderScannedPalletsTable();
        saveDispatchDraft();
        showZaladunkiToast('info', `Usunięto paletę ${removed.displayId || removed.nr_palety} z załadunku.`);
    }
}

/**
 * Czyści całą listę zeskanowanych palet na ten załadunek.
 */
function clearAllScannedPallets() {
    if (scannedPallets.length === 0) return;
    scannedPallets = [];
    renderScannedPalletsTable();
    saveDispatchDraft();
    showZaladunkiToast('info', 'Wyczyszczono listę palet załadunku.');
}

/**
 * Zapisuje aktualny stan danych transportowych i listy palet do localStorage.
 */
function saveDispatchDraft() {
    try {
        const draft = {
            transport: {
                vehicleReg: document.getElementById('dispatchVehicleReg')?.value || '',
                driver: document.getElementById('dispatchDriver')?.value || '',
                customer: document.getElementById('dispatchCustomer')?.value || '',
                wz: document.getElementById('dispatchWz')?.value || '',
                notes: document.getElementById('dispatchNotes')?.value || ''
            },
            pallets: scannedPallets,
            savedAt: new Date().toISOString()
        };

        const hasContent = Boolean(
            draft.pallets.length > 0 ||
            draft.transport.vehicleReg ||
            draft.transport.driver ||
            draft.transport.customer ||
            draft.transport.wz ||
            draft.transport.notes
        );

        if (hasContent) {
            localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
            updateDraftBadge(true);
        } else {
            localStorage.removeItem(DRAFT_STORAGE_KEY);
            updateDraftBadge(false);
        }
    } catch (e) {
        console.warn('Błąd zapisu draftu załadunku:', e);
    }
}

/**
 * Odczytuje i przywraca stan danych transportowych oraz listę palet z localStorage.
 */
function loadDispatchDraft() {
    try {
        const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
        if (!raw) {
            renderScannedPalletsTable();
            return;
        }

        const draft = JSON.parse(raw);
        if (!draft) {
            renderScannedPalletsTable();
            return;
        }

        // Przywróć pola transportowe
        if (draft.transport) {
            if (draft.transport.vehicleReg) setFieldValue('dispatchVehicleReg', draft.transport.vehicleReg);
            if (draft.transport.driver) setFieldValue('dispatchDriver', draft.transport.driver);
            if (draft.transport.customer) setFieldValue('dispatchCustomer', draft.transport.customer);
            if (draft.transport.wz) setFieldValue('dispatchWz', draft.transport.wz);
            if (draft.transport.notes) setFieldValue('dispatchNotes', draft.transport.notes);
        }

        // Przywróć listę palet
        if (Array.isArray(draft.pallets) && draft.pallets.length > 0) {
            scannedPallets = draft.pallets;
            updateDraftBadge(true);
            const statusMsg = document.getElementById('palletScanStatus');
            if (statusMsg) {
                statusMsg.innerHTML = `<span class="material-icons" style="font-size:16px; color:#16a34a;">restore</span> Przywrócono wersję roboczą załadunku (${scannedPallets.length} palet).`;
                statusMsg.style.color = '#16a34a';
            }
        }

        renderScannedPalletsTable();

    } catch (e) {
        console.warn('Błąd wczytywania draftu załadunku:', e);
        renderScannedPalletsTable();
    }
}

function setFieldValue(id, val) {
    const el = document.getElementById(id);
    if (el && val !== undefined && val !== null) {
        el.value = val;
    }
}

/**
 * Pokazuje lub ukrywa etykietę informującą o wersji roboczej.
 */
function updateDraftBadge(show) {
    const badge = document.getElementById('dispatchDraftBadge');
    if (badge) {
        badge.style.display = show ? 'inline-flex' : 'none';
    }
}

/**
 * Usuwa zapisaną wersję roboczą z localStorage i resetuje wszystkie pola.
 */
function clearDispatchDraftAndReset() {
    try {
        localStorage.removeItem(DRAFT_STORAGE_KEY);
    } catch (e) {}

    scannedPallets = [];
    const fields = [
        'dispatchVehicleReg',
        'dispatchDriver',
        'dispatchCustomer',
        'dispatchWz',
        'dispatchNotes'
    ];
    fields.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    clearPalletScanInput();
    renderScannedPalletsTable();
    updateDraftBadge(false);
    showZaladunkiToast('info', 'Wyczyszczono dane załadunku.');
}

/**
 * Wysyła całe zgłoszenie załadunku na samochód (wraz z listą palet) do API.
 */
async function submitVehicleDispatch(e) {
    if (e && e.preventDefault) e.preventDefault();

    if (scannedPallets.length === 0) {
        showZaladunkiToast('error', 'Najpierw zeskanuj co najmniej jedną paletę na ten załadunek!');
        document.getElementById('palletScanInput')?.focus();
        return;
    }

    const vehicleReg = (document.getElementById('dispatchVehicleReg')?.value || '').trim();
    if (!vehicleReg) {
        showZaladunkiToast('warning', 'Wpisz numer rejestracyjny samochodu przed zatwierdzeniem.');
        document.getElementById('dispatchVehicleReg')?.focus();
        return;
    }

    const btn = document.getElementById('btnSubmitDispatch');
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="animation:spin 1s linear infinite;">sync</span> Rejestrowanie wyjazdu pojazdu...';

    const payload = {
        nr_rejestracyjny: vehicleReg,
        kierowca: (document.getElementById('dispatchDriver')?.value || '').trim(),
        odbiorca: (document.getElementById('dispatchCustomer')?.value || '').trim(),
        nr_dokumentu_wz: (document.getElementById('dispatchWz')?.value || '').trim(),
        uwagi: (document.getElementById('dispatchNotes')?.value || '').trim(),
        linia: document.getElementById('currentWarehouseLine')?.value || 'AGRO',
        pallets: scannedPallets
    };

    try {
        const resp = await fetch('/warehouse-v2/api/zaladunki/dispatch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const res = await resp.json();

        if (res.success) {
            showZaladunkiToast('success', res.message || 'Załadunek na samochód został pomyślnie zarejestrowany!');
            playSuccessBeep();

            // Zaktualizuj historię wydań
            await refreshDispatchHistoryTable();

            // Wyczyść listę palet i zapisany draft
            try {
                localStorage.removeItem(DRAFT_STORAGE_KEY);
            } catch (e) {}
            scannedPallets = [];
            document.getElementById('dispatchNotes').value = '';

            renderScannedPalletsTable();
            updateDraftBadge(false);
            clearPalletScanInput();

        } else {
            showZaladunkiToast('error', res.message || 'Nie udało się zarejestrować załadunku.');
        }
    } catch (err) {
        console.error('Błąd rejestracji załadunku:', err);
        showZaladunkiToast('error', 'Wystąpił błąd połączenia z serwerem.');
    } finally {
        btn.disabled = false;
        renderScannedPalletsTable();
    }
}

/**
 * Rozwija lub zwija szczegółową listę palet dla danego dokumentu WZ w rejestrze wydań.
 */
function toggleWzGroupDetails(detailsId) {
    const el = document.getElementById(detailsId);
    if (!el) return;
    const isHidden = el.style.display === 'none' || !el.style.display;
    el.style.display = isHidden ? 'block' : 'none';
}

/**
 * Odświeża zgrupowany rejestr wydań zewnętrznych (po WZ) bez przeładowania całej strony.
 */
async function refreshDispatchHistoryTable() {
    try {
        const resp = await fetch('/warehouse-v2/api/zaladunki/history');
        const data = await resp.json();

        if (data.success) {
            const container = document.getElementById('dispatchHistoryGroupedContainer');
            const historyCountEl = document.getElementById('kpiHistoryCount');
            const groupBadge = document.getElementById('historyGroupCountBadge');

            const grouped = data.grouped || [];
            const history = data.history || [];

            if (historyCountEl) historyCountEl.innerText = history.length;
            if (groupBadge) groupBadge.innerText = `${grouped.length} dokumentów WZ`;

            if (!container) return;

            if (grouped.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 40px 15px; color: #94a3b8; font-weight: 700;">
                        <span class="material-icons" style="font-size: 36px; display: block; margin-bottom: 6px; color: #cbd5e1;">local_shipping</span>
                        Brak zarejestrowanych wydań zewnętrznych na samochód.
                    </div>
                `;
                return;
            }

            container.innerHTML = '';
            grouped.forEach((grp, idx) => {
                const groupDiv = document.createElement('div');
                groupDiv.className = 'wz-group-card';
                const isFirstThree = idx < 3;
                const detailsId = `wzGroupDetails-dyn-${idx}`;

                let rowsHtml = '';
                (grp.items || []).forEach((item, itemIdx) => {
                    rowsHtml += `
                        <tr>
                            <td style="font-weight: 800; color: #94a3b8;">#${itemIdx + 1}</td>
                            <td><span class="badge-pallet">${escapeHtml(item.nr_palety || '-')}</span></td>
                            <td style="font-weight: 800; color: #0f172a;">${escapeHtml(item.nazwa_produktu || '-')}</td>
                            <td><span class="badge-type-line">${escapeHtml(item.typ_palety || '-')}</span></td>
                            <td style="text-align: right; font-weight: 800; color: #16a34a;">${parseFloat(item.ilosc_kg || 0).toFixed(2)} kg</td>
                            <td style="font-weight: 700; color: #475569;">${escapeHtml(item.magazynier || '-')}</td>
                            <td style="font-size: 12px; color: #64748b; font-weight: 600;">${escapeHtml(item.created_at || '-')}</td>
                        </tr>
                    `;
                });

                groupDiv.innerHTML = `
                    <div class="wz-group-header" onclick="toggleWzGroupDetails('${detailsId}')">
                        <div class="wz-group-header-left">
                            <span class="wz-doc-badge ${grp.has_wz ? 'wz-doc-badge-active' : 'wz-doc-badge-fallback'}">
                                <span class="material-icons" style="font-size:16px;">description</span>
                                <strong>${escapeHtml(grp.nr_dokumentu_wz)}</strong>
                            </span>
                            <span class="badge-reg">${escapeHtml(grp.nr_rejestracyjny)}</span>
                            <span class="wz-header-meta">
                                <strong>Kierowca:</strong> ${escapeHtml(grp.kierowca)} &bull; 
                                <strong>Odbiorca:</strong> ${escapeHtml(grp.odbiorca)}
                            </span>
                        </div>
                        <div class="wz-group-header-right">
                            <span class="wz-stat-pill" title="Łączna waga w dokumencie WZ">
                                <span class="material-icons" style="font-size:15px; color:#16a34a;">scale</span>
                                <strong>${parseFloat(grp.total_weight_kg || 0).toFixed(2)} kg</strong>
                            </span>
                            <span class="wz-stat-pill" title="Liczba palet w tym WZ">
                                <span class="material-icons" style="font-size:15px; color:#2563eb;">inventory_2</span>
                                <strong>${grp.pallets_count} ${grp.pallets_count === 1 ? 'paleta' : 'palet'}</strong>
                            </span>
                            <span style="font-size:12px; color:#64748b; font-weight:700;">${escapeHtml(grp.created_at || '')}</span>
                            <button type="button" class="wz-toggle-btn" title="Pokaż / ukryj pozycje WZ">
                                <span class="material-icons wz-toggle-icon">expand_more</span>
                            </button>
                        </div>
                    </div>
                    <div class="wz-group-body" id="${detailsId}" style="display: none;">
                        <table class="zaladunki-table wz-subtable">
                            <thead>
                                <tr>
                                    <th style="width: 40px;">LP</th>
                                    <th style="width: 190px;">Nr Palety / SSCC</th>
                                    <th>Nazwa Towaru / Surowca</th>
                                    <th style="width: 130px;">Typ & Linia</th>
                                    <th style="width: 130px; text-align: right;">Ilość (kg)</th>
                                    <th style="width: 120px;">Magazynier</th>
                                    <th style="width: 140px;">Data Załadunku</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${rowsHtml}
                            </tbody>
                        </table>
                    </div>
                `;
                container.appendChild(groupDiv);
            });
        }
    } catch (err) {
        console.error('Błąd pobierania historii wydań:', err);
    }
}

/**
 * Wyświetla elegancki toast z powiadomieniem (zastępuje window.alert).
 */
function showZaladunkiToast(type, message) {
    let container = document.getElementById('zaladunkiToastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'zaladunkiToastContainer';
        container.className = 'zaladunki-toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `zaladunki-toast toast-${type}`;

    let icon = 'info';
    if (type === 'success') icon = 'check_circle';
    if (type === 'error') icon = 'error_outline';
    if (type === 'warning') icon = 'warning_amber';
    if (type === 'info') icon = 'info';

    toast.innerHTML = `<span class="material-icons">${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

/**
 * Krótki sygnał dźwiękowy potwierdzający udany skan.
 */
function playSuccessBeep() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.frequency.setValueAtTime(600, audioCtx.currentTime);
        osc.frequency.setValueAtTime(900, audioCtx.currentTime + 0.08);
        gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.25);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.25);
    } catch (e) {}
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
