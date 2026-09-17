/**
 * @file przyjecie_ruchu.js
 * @description Client logic for warehouse reception & internal transfer (Etap 2).
 */

let locationSuggestTimer = null;
let locationSuggestAbortController = null;
let locationSuggestLastPrefix = '';
let pendingAcceptItem = null;

function getConfig() {
    return window.PRZYJECIE_RUCHU_CONFIG || {};
}

function openLabelPreview(payload) {
    const url = buildLabelPreviewUrl(payload);
    window.open(url, '_blank', 'noopener');
}

function buildLabelPreviewUrl(payload) {
    const config = getConfig();
    const params = new URLSearchParams({
        nr_palety: String((payload && payload.nr_palety) || '').trim() || '---',
        product_name: String((payload && payload.product_name) || '').trim() || 'Brak nazwy',
        nr_partii: String((payload && payload.nr_partii) || '').trim() || '---',
        data_produkcji: String((payload && payload.data_produkcji) || '').trim() || '---',
        data_przydatnosci: String((payload && payload.data_przydatnosci) || '').trim() || '---',
        qty: String(Number((payload && payload.qty) || 0) || 0),
        p_type: String((payload && payload.p_type) || 'surowiec').trim() || 'surowiec',
        linia: config.linia || '',
        autoprint: '1'
    });

    return `${config.labelPreviewBaseUrl}?${params.toString()}`;
}

function normalizeLocationCode(value) {
    let s = String(value || '').trim().toUpperCase();
    if (!s) return '';
    if (/^MS[O](\d+|$)/.test(s)) s = s.replace(/^MS[O]/, 'MS0');
    if (/^MP[O](\d+|$)/.test(s)) s = s.replace(/^MP[O]/, 'MP0');
    if (/^MD[O](\d+|$)/.test(s)) s = s.replace(/^MD[O]/, 'MD0');
    if (/^MGW[O](\d+|$)/.test(s)) s = s.replace(/^MGW[O]/, 'MGW0');
    if (/^BF_?MS[O]/.test(s)) s = s.replace(/^BF_?MS[O]/, 'BF_MS0');
    if (/^BF_?MP[O]/.test(s)) s = s.replace(/^BF_?MP[O]/, 'BF_MP0');
    if (/^R[O]\d/.test(s)) s = s.replace(/^R[O]/, 'R0');
    return s;
}

function ensureLocationSuggestionsList() {
    let dataList = document.getElementById('locationSuggestionsList');
    if (dataList) return dataList;
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
        if (!normalized) return;
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
    if (prefix === locationSuggestLastPrefix) return;

    if (locationSuggestTimer) clearTimeout(locationSuggestTimer);
    locationSuggestTimer = setTimeout(() => {
        fetchLocationSuggestions(prefix);
    }, 120);
}

async function fetchLocationSuggestions(prefix) {
    if (locationSuggestAbortController) {
        locationSuggestAbortController.abort();
    }
    locationSuggestAbortController = new AbortController();
    const config = getConfig();
    const query = new URLSearchParams({
        linia: config.linia || '',
        prefix: prefix,
        only_free_for_racks: '1',
        limit: '50',
    });

    try {
        const response = await fetch(`/magazyn-dostawy/api/sugerowane-lokalizacje?${query.toString()}`, {
            signal: locationSuggestAbortController.signal,
        });
        const data = await response.json();
        if (!data || !data.success || !Array.isArray(data.suggestions)) return;
        locationSuggestLastPrefix = prefix;
        renderLocationSuggestionOptions(data.suggestions);
    } catch (error) {
        if (error && error.name === 'AbortError') return;
        console.warn('Location suggestions failed', error);
    }
}

function handleLocationSuggestInput(inputElement) {
    if (!inputElement) return;
    inputElement.value = normalizeLocationCode(inputElement.value);
    queueLocationSuggestions(inputElement.value);
}

function safeToast(msg, kind) {
    if (typeof showToast === 'function') {
        showToast(msg, kind || 'info');
    } else if (window.AppDialog && typeof AppDialog.alert === 'function') {
        AppDialog.alert(msg);
    } else {
        alert(msg);
    }
}

function updateProgressIndicators(data) {
    const config = getConfig();
    const total = Number(config.totalCount || 0);
    const accepted = Number((data && data.accepted_count) || 0);
    const rejected = Number((data && data.rejected_count) || 0);
    const processed = accepted + rejected;
    const pending = Math.max(total - processed, 0);

    const processedEl = document.getElementById('kpiProcessedCount');
    const pendingEl = document.getElementById('kpiPendingCount');
    const progressFillEl = document.getElementById('kpiProgressFill');

    if (processedEl) processedEl.textContent = `${processed} / ${total}`;
    if (pendingEl) pendingEl.textContent = `Do rozliczenia: ${pending}`;
    if (progressFillEl) {
        const pct = total > 0 ? Math.min(100, Math.max(0, (processed / total) * 100)) : 0;
        progressFillEl.style.width = pct.toFixed(2) + '%';
    }
}

function markRowAsProcessed(idx, mode, reason) {
    const row = document.getElementById(`row_${idx}`);
    const btn = document.getElementById(`btn_${idx}`);
    const rejectBtn = document.getElementById(`reject_btn_${idx}`);
    if (!row) return;

    row.classList.add('done');
    row.querySelectorAll('input').forEach(el => el.disabled = true);

    if (btn) {
        btn.disabled = true;
        btn.textContent = mode === 'rejected' ? 'Pozycja odrzucona' : 'Pozycja przyjęta';
    }
    if (rejectBtn) {
        rejectBtn.disabled = true;
        rejectBtn.textContent = mode === 'rejected' ? 'Odrzucono' : 'Rozliczono';
        if (mode === 'rejected' && reason) {
            rejectBtn.title = 'Powód: ' + reason;
        }
    }
}

async function cancelTransferOrder(dostawaId, orderRef) {
    const label = orderRef || dostawaId;
    const config = getConfig();
    const ok = await (window.AppDialog ? AppDialog.confirm(`Czy na pewno anulować całe zlecenie ${label}?`) : Promise.resolve(confirm(`Czy na pewno anulować całe zlecenie ${label}?`)));
    if (!ok) return;

    try {
        const res = await fetch(`/magazyn-dostawy/api/anuluj/${encodeURIComponent(dostawaId)}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await res.json();
        if (!data.success) {
            safeToast('Błąd: ' + (data.message || 'Nie udało się anulować zlecenia.'), 'danger');
            return;
        }
        safeToast(data.message || 'Zlecenie anulowane.', 'success');
        setTimeout(() => {
            window.location.href = config.postListUrl;
        }, 350);
    } catch (e) {
        safeToast('Błąd połączenia z serwerem.', 'danger');
    }
}

function acceptItemClick(itemId, idx, productName, qty, pType) {
    const config = getConfig();
    const locEl = document.getElementById(`loc_${idx}`);
    const sourceEl = document.getElementById(`src_${idx}`);
    const batchEl = document.getElementById(`batch_${idx}`);
    const prodEl = document.getElementById(`prod_${idx}`);
    const expEl = document.getElementById(`exp_${idx}`);

    const location = normalizeLocationCode(locEl ? locEl.value : '');
    if (locEl) locEl.value = location;
    const sourceSpot = (sourceEl ? sourceEl.value : '').trim().toUpperCase();
    const nrPartii = (batchEl ? batchEl.value : '').trim();
    const dataProdukcji = prodEl ? prodEl.value : null;
    const dataPrzydatnosci = expEl ? expEl.value : null;

    if (!location) {
        safeToast('Podaj lokalizację odstawienia.', 'warning');
        if (locEl) locEl.focus();
        return;
    }

    if (!config.isExternalDelivery && sourceSpot && sourceSpot !== '---' && sourceSpot === location) {
        safeToast(`Nie można przyjąć na tę samą lokalizację (${location}), z której przyjmujesz.`, 'warning');
        if (locEl) locEl.focus();
        return;
    }

    pendingAcceptItem = {
        itemId,
        idx,
        location,
        productName,
        qty: Number(qty || 0),
        pType: String(pType || 'surowiec'),
        nrPartii,
        dataProdukcji,
        dataPrzydatnosci
    };

    document.getElementById('modalProductName').textContent = productName;
    document.getElementById('printerModal').style.display = 'flex';
}

function closePrinterModal() {
    document.getElementById('printerModal').style.display = 'none';
    pendingAcceptItem = null;
}

async function confirmAcceptWithPrinter() {
    if (!pendingAcceptItem) return;
    const config = getConfig();
    const { itemId, idx, location, productName, qty, pType, nrPartii, dataProdukcji, dataPrzydatnosci } = pendingAcceptItem;

    closePrinterModal();

    const btn = document.getElementById(`btn_${idx}`);
    const rejectBtn = document.getElementById(`reject_btn_${idx}`);
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Zapisywanie...';
    }
    if (rejectBtn) rejectBtn.disabled = true;

    const printerId = document.getElementById('modalPrinterSelect').value;
    const wantsPdfPreview = printerId === config.pdfPreviewPrinterId;

    try {
        const res = await fetch(`/magazyn-dostawy/api/przyjmij-pozycje/${encodeURIComponent(config.dostawaId)}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                item_id: itemId,
                lokalizacja: location,
                nr_partii: nrPartii,
                data_produkcji: dataProdukcji,
                data_przydatnosci: dataPrzydatnosci,
                printer_id: printerId || null
            })
        });
        const data = await res.json();
        if (!data.success) {
            safeToast('Błąd: ' + (data.error || 'Nie udało się przyjąć pozycji'), 'danger');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Potwierdź przyjęcie';
            }
            if (rejectBtn) rejectBtn.disabled = false;
            return;
        }

        safeToast('Pozycja przyjęta.', 'success');
        updateProgressIndicators(data);
        markRowAsProcessed(idx, 'accepted');

        if (wantsPdfPreview) {
            openLabelPreview({
                nr_palety: data.nr_palety,
                product_name: productName,
                nr_partii: nrPartii || '---',
                data_produkcji: dataProdukcji || '---',
                data_przydatnosci: dataPrzydatnosci || '---',
                qty,
                p_type: pType,
            });
            safeToast('Otwarto podgląd etykiety PDF.', 'info');
        }

        if (data.all_accepted) {
            safeToast(`Wszystkie pozycje rozliczone. ${config.isExternalDelivery ? 'Dostawa zakończona.' : 'Ruch zakończony.'}`, 'success');
            setTimeout(() => {
                window.location.href = config.postListUrl;
            }, 1200);
            return;
        }

        setTimeout(() => {
            window.location.reload();
        }, 300);
    } catch (e) {
        safeToast('Błąd połączenia z serwerem.', 'danger');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Potwierdź przyjęcie';
        }
        if (rejectBtn) rejectBtn.disabled = false;
    }
}

function syncSelectedPrinter(printerId) {
    if (!printerId) return;
    try {
        localStorage.setItem('selected_warehouse_printer', printerId);
    } catch (e) {}

    const bulkSelect = document.getElementById('bulk_print_printer');
    if (bulkSelect && bulkSelect.value !== printerId) bulkSelect.value = printerId;

    const modalSelect = document.getElementById('modalPrinterSelect');
    if (modalSelect && modalSelect.value !== printerId) modalSelect.value = printerId;

    document.querySelectorAll('[id^="preprint_printer_"], [id^="reprint_printer_"]').forEach(el => {
        if (el && el.value !== printerId) el.value = printerId;
    });
}

function initDefaultPrinterSelection() {
    let savedPrinter = '';
    try {
        savedPrinter = localStorage.getItem('selected_warehouse_printer') || '';
    } catch (e) {}

    const bulkSelect = document.getElementById('bulk_print_printer');
    let fallbackPrinter = '';
    if (bulkSelect) {
        for (let i = 0; i < bulkSelect.options.length; i++) {
            const val = bulkSelect.options[i].value;
            if (val && val !== '__PDF_PREVIEW__') {
                fallbackPrinter = val;
                break;
            }
        }
    }

    const targetPrinter = savedPrinter || fallbackPrinter;
    if (targetPrinter) syncSelectedPrinter(targetPrinter);
}

async function reprintLabel(btnElement, idx, nrPalety, productName, batch, dateProd, dateExp, qty, pType) {
    const config = getConfig();
    const printerSelect = document.getElementById(`reprint_printer_${idx}`);
    let printerId = printerSelect ? printerSelect.value : '';
    if (!printerId) {
        const bulkSelect = document.getElementById('bulk_print_printer');
        if (bulkSelect && bulkSelect.value) {
            printerId = bulkSelect.value;
            syncSelectedPrinter(printerId);
        }
    }

    if (!printerId) {
        safeToast('Wybierz drukarkę przed dodrukiem!', 'warning');
        return;
    }

    if (printerId === config.pdfPreviewPrinterId) {
        openLabelPreview({
            nr_palety: nrPalety,
            product_name: productName,
            nr_partii: batch || '---',
            data_produkcji: dateProd || '---',
            data_przydatnosci: dateExp || '---',
            qty,
            p_type: pType || 'surowiec',
        });
        safeToast('Otwarto podgląd etykiety PDF.', 'info');
        return;
    }

    const btn = (btnElement && btnElement.nodeType) ? btnElement : (document.getElementById(`reprint_btn_${idx}`) || document.getElementById(`print_btn_${idx}`));
    const oldHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="material-icons" style="font-size: 16px;">hourglass_empty</span> Drukowanie...';
    }

    try {
        const resp = await fetch(config.reprintEndpointUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nr_palety: nrPalety,
                printer_id: printerId,
                product_name: productName,
                nr_partii: batch || '---',
                data_produkcji: dateProd || '---',
                data_przydatnosci: dateExp || '---',
                qty,
                p_type: pType
            })
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            safeToast(data.message || 'Etykiety wysłane do drukarki.', 'success');
        } else {
            safeToast('Błąd: ' + (data.error || 'Nieznany błąd'), 'danger');
        }
    } catch (e) {
        safeToast('Błąd komunikacji z serwerem.', 'danger');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldHtml;
        }
    }
}

async function preprintLabel(btnElement, idx, nrPalety, productName, qty, pType) {
    const config = getConfig();
    const printerSelect = document.getElementById(`preprint_printer_${idx}`);
    let printerId = printerSelect ? printerSelect.value : '';
    if (!printerId) {
        const bulkSelect = document.getElementById('bulk_print_printer');
        if (bulkSelect && bulkSelect.value) {
            printerId = bulkSelect.value;
            syncSelectedPrinter(printerId);
        }
    }

    if (!printerId) {
        safeToast('Wybierz drukarkę przed drukiem!', 'warning');
        return;
    }

    const nrPaletyValue = String(nrPalety || '').trim();
    if (!nrPaletyValue || nrPaletyValue === '---') {
        safeToast('Brak numeru palety (SSCC) do druku.', 'warning');
        return;
    }

    const batchEl = document.getElementById(`batch_${idx}`);
    const prodEl = document.getElementById(`prod_${idx}`);
    const expEl = document.getElementById(`exp_${idx}`);
    const batch = batchEl ? batchEl.value : '';
    const dateProd = prodEl ? prodEl.value : '';
    const dateExp = expEl ? expEl.value : '';
    const safeName = String(productName || 'Brak nazwy');

    if (printerId === config.pdfPreviewPrinterId) {
        openLabelPreview({
            nr_palety: nrPaletyValue,
            product_name: safeName,
            nr_partii: batch || '---',
            data_produkcji: dateProd || '---',
            data_przydatnosci: dateExp || '---',
            qty: Number(qty || 0),
            p_type: pType || 'surowiec',
        });
        safeToast('Otwarto podgląd etykiety PDF.', 'info');
        return;
    }

    const btn = (btnElement && btnElement.nodeType) ? btnElement : document.getElementById(`print_btn_${idx}`);
    const oldHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="material-icons" style="font-size: 16px;">hourglass_empty</span> Drukowanie...';
    }

    try {
        const resp = await fetch(config.reprintEndpointUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nr_palety: nrPaletyValue,
                printer_id: printerId,
                product_name: safeName,
                nr_partii: batch || '---',
                data_produkcji: dateProd || '---',
                data_przydatnosci: dateExp || '---',
                qty: Number(qty || 0),
                p_type: pType || 'surowiec'
            })
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            safeToast(data.message || 'Etykiety wysłane do drukarki.', 'success');
        } else {
            safeToast('Błąd: ' + (data.error || 'Nieznany błąd'), 'danger');
        }
    } catch (e) {
        safeToast('Błąd komunikacji z serwerem.', 'danger');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldHtml;
        }
    }
}

async function printAllPendingLabels() {
    const config = getConfig();
    const items = config.pendingPrintItems || [];
    if (!items || items.length === 0) {
        safeToast('Brak pozycji do wydruku.', 'warning');
        return;
    }

    const printerSelect = document.getElementById('bulk_print_printer');
    const printerId = printerSelect ? printerSelect.value : '';
    if (!printerId) {
        safeToast('Wybierz drukarkę przed drukiem.', 'warning');
        return;
    }

    const btn = document.getElementById('bulkPrintBtn');
    const oldHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="material-icons" style="font-size: 16px;">hourglass_empty</span> Drukowanie...';
    }

    const validItems = [];
    for (const item of items) {
        const nrPalety = String(item.nr_palety || '').trim();
        if (!nrPalety || nrPalety === '---') continue;
        validItems.push({
            nr_palety: nrPalety,
            product_name: String(item.product_name || 'Brak nazwy'),
            nr_partii: String(item.nr_partii || '---'),
            data_produkcji: String(item.data_produkcji || '---'),
            data_przydatnosci: String(item.data_przydatnosci || '---'),
            qty: Number(item.qty || 0),
            p_type: item.p_type || 'surowiec',
        });
    }

    if (validItems.length === 0) {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldHtml;
        }
        safeToast('Brak poprawnych pozycji do druku.', 'warning');
        return;
    }

    if (printerId === config.pdfPreviewPrinterId) {
        validItems.forEach(payload => openLabelPreview(payload));
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldHtml;
        }
        safeToast(`Otwarto podgląd etykiet: ${validItems.length}.`, 'info');
        return;
    }

    try {
        const resp = await fetch(config.reprintEndpointUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                printer_id: printerId,
                copies: 2,
                items: validItems
            })
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            safeToast(data.message || `Wysłano ${validItems.length * 2} etykiet do drukarki.`, 'success');
        } else {
            safeToast('Błąd: ' + (data.error || 'Nieznany błąd'), 'danger');
        }
    } catch (e) {
        safeToast('Błąd komunikacji z serwerem.', 'danger');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldHtml;
        }
    }
}

async function rejectItem(itemId, idx) {
    const config = getConfig();
    const btn = document.getElementById(`btn_${idx}`);
    const rejectBtn = document.getElementById(`reject_btn_${idx}`);
    const reason = await (window.AppDialog && typeof AppDialog.prompt === 'function' 
        ? AppDialog.prompt('Powód odrzucenia pozycji:', 'Brak palety do przyjęcia') 
        : Promise.resolve(prompt('Powód odrzucenia pozycji:', 'Brak palety do przyjęcia')));

    if (reason === null) return;

    if (rejectBtn) {
        rejectBtn.disabled = true;
        rejectBtn.textContent = 'Zapisywanie...';
    }
    if (btn) btn.disabled = true;

    try {
        const res = await fetch(`/magazyn-dostawy/api/odrzuc-pozycje/${encodeURIComponent(config.dostawaId)}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                item_id: itemId,
                reason: String(reason || '').trim(),
            })
        });
        const data = await res.json();
        if (!data.success) {
            safeToast('Błąd: ' + (data.error || 'Nie udało się odrzucić pozycji'), 'danger');
            if (rejectBtn) {
                rejectBtn.disabled = false;
                rejectBtn.innerHTML = '<span class="material-icons" style="font-size: 18px;">block</span> Odrzuć pozycję';
            }
            if (btn) btn.disabled = false;
            return;
        }

        safeToast('Pozycja odrzucona.', 'warning');
        updateProgressIndicators(data);

        if (data.all_accepted) {
            safeToast(`Wszystkie pozycje rozliczone. ${config.isExternalDelivery ? 'Dostawa zakończona.' : 'Ruch zakończony.'}`, 'success');
            setTimeout(() => {
                window.location.href = config.postListUrl;
            }, 800);
            return;
        }

        markRowAsProcessed(idx, 'rejected', String(reason || '').trim());
    } catch (e) {
        safeToast('Błąd połączenia z serwerem.', 'danger');
        if (rejectBtn) {
            rejectBtn.disabled = false;
            rejectBtn.innerHTML = '<span class="material-icons" style="font-size: 18px;">block</span> Odrzuć pozycję';
        }
        if (btn) btn.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', function () {
    ensureLocationSuggestionsList();
    initDefaultPrinterSelection();
});
