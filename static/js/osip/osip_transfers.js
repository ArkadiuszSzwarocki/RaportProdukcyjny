/**
 * Obsługa listy i akcji transferów wewnętrznych OSIP <-> Centrala.
 */

document.addEventListener('DOMContentLoaded', () => {
    const tbody = document.getElementById('transfers-tbody');
    const cntPlanned = document.getElementById('cnt-planned');
    const cntTransit = document.getElementById('cnt-transit');
    const cntCompleted = document.getElementById('cnt-completed');
    const cntCancelled = document.getElementById('cnt-cancelled');

    const btnNew = document.getElementById('btn-new-transfer');
    const modalEl = document.getElementById('modal-new-transfer');
    const formNew = document.getElementById('form-new-transfer');
    const submitNew = document.getElementById('submit-new-transfer');
    const itemsList = document.getElementById('transfer-items-list');
    const addItemBtn = document.getElementById('add-item-row-btn');

    const scanInput = document.getElementById('scan-pallet-input');
    const scanBtn = document.getElementById('scan-pallet-btn');
    const cntScanned = document.getElementById('scanned-pallets-count');
    const weightScanned = document.getElementById('scanned-pallets-weight');

    const step1Div = document.getElementById('transfer-step-1');
    const step2Div = document.getElementById('transfer-step-2');
    const modalTitle = document.getElementById('modal-new-transfer-title');
    const selectedDirectionBadge = document.getElementById('selected-direction-badge');
    const inputSourceWh = document.getElementById('new-source-wh');
    const inputDestWh = document.getElementById('new-dest-wh');

    const selectStep1Source = document.getElementById('select-step1-source');
    const selectStep1Dest = document.getElementById('select-step1-dest');
    const btnConfirmDirection = document.getElementById('btn-confirm-direction');

    function checkStep1Selection() {
        if (!selectStep1Source || !selectStep1Dest || !btnConfirmDirection) return;
        const s = selectStep1Source.value;
        const d = selectStep1Dest.value;

        if (s && d) {
            if (s === d) {
                btnConfirmDirection.disabled = true;
                btnConfirmDirection.innerHTML = 'ŹRÓDŁO I CEL NIE MOGĄ BYĆ TAKIE SAME <i class="fas fa-exclamation-triangle ml-2"></i>';
                btnConfirmDirection.className = 'btn btn-warning btn-lg btn-block font-weight-bold shadow-sm py-3';
            } else {
                btnConfirmDirection.disabled = false;
                btnConfirmDirection.innerHTML = 'PRZEJDŹ DO SKANOWANIA PALET <i class="fas fa-arrow-right ml-2"></i>';
                btnConfirmDirection.className = 'btn btn-primary btn-lg btn-block font-weight-bold shadow-sm py-3';
            }
        } else {
            btnConfirmDirection.disabled = true;
            btnConfirmDirection.innerHTML = 'WYBIERZ MAGAZYN ŹRÓDŁOWY I DOCELOWY <i class="fas fa-arrow-right ml-2"></i>';
            btnConfirmDirection.className = 'btn btn-secondary btn-lg btn-block font-weight-bold shadow-sm py-3';
        }
    }

    if (selectStep1Source) selectStep1Source.addEventListener('change', checkStep1Selection);
    if (selectStep1Dest) selectStep1Dest.addEventListener('change', checkStep1Selection);

    if (btnConfirmDirection) {
        btnConfirmDirection.addEventListener('click', () => {
            const s = selectStep1Source.value;
            const d = selectStep1Dest.value;
            if (s && d && s !== d) {
                goToStep(2, s, d);
            }
        });
    }

    function goToStep(step, source = '', dest = '') {
        if (step === 1) {
            if (selectStep1Source) selectStep1Source.value = '';
            if (selectStep1Dest) selectStep1Dest.value = '';
            checkStep1Selection();

            if (step1Div) step1Div.style.display = 'block';
            if (step2Div) step2Div.style.display = 'none';
            if (submitNew) submitNew.style.display = 'none';
            if (modalTitle) modalTitle.innerHTML = '<i class="fas fa-arrow-right-arrow-left mr-2"></i>Krok 1/2: Wybór magazynu (Skąd ➔ Dokąd)';
        } else if (step === 2) {
            if (inputSourceWh) inputSourceWh.value = source;
            if (inputDestWh) inputDestWh.value = dest;

            let sourceName = source === 'MS01' ? 'Centrala (MS01)' : (source === 'OSIP' ? 'Magazyn OSIP' : source);
            let destName = dest === 'MS01' ? 'Centrala (MS01)' : (dest === 'OSIP' ? 'Magazyn OSIP' : dest);

            if (selectedDirectionBadge) {
                selectedDirectionBadge.innerHTML = `${sourceName} &rarr; ${destName}`;
            }
            if (modalTitle) {
                modalTitle.innerHTML = `<i class="fas fa-barcode mr-2 text-warning"></i>Krok 2/2: Skanowanie palet (${sourceName} &rarr; ${destName})`;
            }

            if (step1Div) step1Div.style.display = 'none';
            if (step2Div) step2Div.style.display = 'block';
            if (submitNew) submitNew.style.display = 'inline-block';

            setTimeout(() => {
                if (scanInput) scanInput.focus();
            }, 200);
        }
    }

    const changeDirBtn = document.getElementById('change-direction-btn');
    if (changeDirBtn) {
        changeDirBtn.addEventListener('click', () => {
            goToStep(1);
        });
    }

    function openTransferModal() {
        if (!modalEl) return;
        goToStep(1);
        try {
            if (window.jQuery && typeof window.jQuery(modalEl).modal === 'function') {
                window.jQuery(modalEl).modal('show');
            }
        } catch (e) {
            console.warn('jQuery modal show error:', e);
        }

        modalEl.classList.add('show');
        modalEl.style.display = 'block';
        modalEl.removeAttribute('aria-hidden');
        modalEl.setAttribute('aria-modal', 'true');
        modalEl.setAttribute('role', 'dialog');
        document.body.classList.add('modal-open');

        let backdrop = document.querySelector('.modal-backdrop');
        if (!backdrop) {
            backdrop = document.createElement('div');
            backdrop.className = 'modal-backdrop fade show';
            document.body.appendChild(backdrop);
        }
    }

    function closeTransferModal() {
        if (!modalEl) return;
        try {
            if (window.jQuery && typeof window.jQuery(modalEl).modal === 'function') {
                window.jQuery(modalEl).modal('hide');
            }
        } catch (e) {
            console.warn('jQuery modal hide error:', e);
        }

        modalEl.classList.remove('show');
        modalEl.style.display = 'none';
        modalEl.setAttribute('aria-hidden', 'true');
        modalEl.removeAttribute('aria-modal');
        document.body.classList.remove('modal-open');

        let backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) backdrop.remove();
        goToStep(1);
    }

    function updateScannedCounters() {
        const rows = document.querySelectorAll('.item-row');
        let count = 0;
        let totalWeight = 0;

        rows.forEach(row => {
            count++;
            const qVal = parseFloat(row.querySelector('.item-qty')?.value || '0');
            if (!isNaN(qVal) && qVal > 0) {
                totalWeight += qVal;
            }
        });

        if (cntScanned) cntScanned.textContent = count;
        if (weightScanned) weightScanned.textContent = totalWeight.toFixed(2) + ' kg';

        const emptyMsg = document.getElementById('empty-items-msg');
        if (emptyMsg) {
            emptyMsg.style.display = count > 0 ? 'none' : 'block';
        }
    }

    // ─── MUTEX: zapobiega podwójnemu dodaniu palety niezależnie od długości kodu ───
    let _isProcessingScan = false;

    async function handlePalletScan() {
        if (!scanInput) return;
        const code = scanInput.value.trim();
        if (!code) return;

        // Wyczyść pole i zatrzymaj timer PRZED jakimkolwiek procesowaniem
        scanInput.value = '';
        if (scanTimeout) {
            clearTimeout(scanTimeout);
            scanTimeout = null;
        }
        scanInput.focus();

        // Mutex – tylko jedno wywołanie na raz
        if (_isProcessingScan) {
            console.warn('[SCAN] Inne skanowanie w toku, pomijam.');
            return;
        }
        _isProcessingScan = true;

        const codeUpper = code.toUpperCase();
        // Sprawdź już istniejące pozycje na liście
        const existingCodes = Array.from(document.querySelectorAll('.item-code'))
            .map(inp => (inp.value || '').trim().toUpperCase());
        if (existingCodes.includes(codeUpper)) {
            console.warn(`[SCAN] Paleta ${code} już na liście.`);
            _isProcessingScan = false;
            return;
        }

        let productName = 'Paleta ' + code;
        let batchNo = '';
        let prodDate = '';
        let qty = 1000;
        let palletId = null;

        try {
            const res = await fetch('/agro/scanner/lookup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, linia: 'AGRO' })
            });
            if (res.ok) {
                const json = await res.json();
                if (json.success && json.pallet) {
                    const p = json.pallet;
                    productName = p.nazwa || p.produkt_nazwa || p.name || p.surowiec_nazwa || productName;
                    batchNo = p.nr_partii || p.batch || p.partia || '';
                    prodDate = p.data_produkcji || p.data_przydatnosci || '';
                    qty = parseFloat(p.stan_magazynowy || p.waga_netto || p.ilosc || p.weight || 1000);
                    palletId = p.id || p.pallet_id || null;
                    if (p.is_transfer && p.transfer && (p.transfer.status === 'PLANNED' || p.transfer.status === 'IN_TRANSIT')) {
                        alert(`Paleta ${code} bierze już udział w aktywnym zleceniu transferu ${p.transfer.transfer_code}!`);
                        _isProcessingScan = false;
                        return;
                    }
                }
            }
        } catch (e) {
            console.warn('[SCAN] Lookup error:', e);
        } finally {
            _isProcessingScan = false;
        }

        addScannedItemRow({
            nr_palety: code,
            pallet_id: palletId,
            product_name: productName,
            nr_partii: batchNo,
            data_produkcji: prodDate,
            requested_qty: qty
        });
    }

    function addScannedItemRow(itemData = {}) {
        // Ostatnia linia obrony przed duplikatami
        const code = (itemData.nr_palety || '').trim().toUpperCase();
        if (code) {
            const existingCodes = Array.from(document.querySelectorAll('.item-code'))
                .map(inp => (inp.value || '').trim().toUpperCase());
            if (existingCodes.includes(code)) {
                console.warn(`[DOM] Paleta ${code} już na liście - blokuję powtórzenie.`);
                return;
            }
        }
        const emptyMsg = document.getElementById('empty-items-msg');
        if (emptyMsg) emptyMsg.style.display = 'none';

        const div = document.createElement('div');
        div.className = 'card border-0 shadow-sm p-3 mb-3 item-row bg-white';
        div.style.borderRadius = '12px';
        div.style.border = '1px solid #cbd5e1';

        div.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-2 pb-2 border-bottom">
                <div class="d-flex align-items-center gap-2">
                    <span class="badge px-3 py-1 font-weight-bold" style="font-size: 0.9rem; background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe;">
                        <i class="fas fa-barcode mr-1"></i> PALETA: ${itemData.nr_palety || 'KOD RĘCZNY'}
                    </span>
                    <input type="hidden" class="item-code" value="${itemData.nr_palety || ''}">
                    <input type="hidden" class="item-pallet-id" value="${itemData.pallet_id || ''}">
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger font-weight-bold remove-item-btn" title="Usuń pozycję">
                    <i class="fas fa-trash-alt mr-1"></i> USUŃ PALETĘ
                </button>
            </div>

            <div class="row">
                <div class="col-md-4 mb-2 mb-md-0">
                    <label class="small text-muted font-weight-bold mb-1">Nazwa Surowca / Produktu</label>
                    <input type="text" class="form-control form-control-sm font-weight-bold item-product bg-white text-dark" value="${itemData.product_name || ''}" required style="border: 1px solid #cbd5e1;">
                </div>
                <div class="col-md-3 mb-2 mb-md-0">
                    <label class="small text-muted font-weight-bold mb-1">Numer Partii</label>
                    <input type="text" class="form-control form-control-sm item-batch bg-white text-dark" value="${itemData.nr_partii || ''}" placeholder="Partia" style="border: 1px solid #cbd5e1;">
                </div>
                <div class="col-md-3 mb-2 mb-md-0">
                    <label class="small text-muted font-weight-bold mb-1">Data Prod. / Ważności</label>
                    <input type="date" class="form-control form-control-sm item-date bg-white text-dark" value="${itemData.data_produkcji || ''}" style="border: 1px solid #cbd5e1;">
                </div>
                <div class="col-md-2">
                    <label class="small text-muted font-weight-bold mb-1">Waga / Ilość</label>
                    <div class="input-group input-group-sm">
                        <input type="number" step="0.01" class="form-control form-control-sm font-weight-bold item-qty bg-white text-primary" value="${itemData.requested_qty || ''}" placeholder="Waga" required style="border: 1px solid #cbd5e1;">
                        <div class="input-group-append"><span class="input-group-text font-weight-bold bg-white border-left-0">kg</span></div>
                    </div>
                </div>
            </div>
        `;

        itemsList.appendChild(div);

        div.querySelector('.item-qty').addEventListener('input', updateScannedCounters);
        div.querySelector('.remove-item-btn').addEventListener('click', () => {
            div.remove();
            updateScannedCounters();
            saveTransferDraft();
        });

        updateScannedCounters();
        saveTransferDraft();
    }

    let scanTimeout = null;
    if (scanInput) {
        // Enter: natychmiastowe skanowanie, kasuje timer
        scanInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                e.stopPropagation();
                if (scanTimeout) { clearTimeout(scanTimeout); scanTimeout = null; }
                handlePalletScan();
            }
        });

        // input: ustaw timer tylko jeśli Enter jeszcze nie wywołał handlePalletScan
        // Długi debounce (800ms) bo Zebra kończy transmisję Enter-em – timer i tak zostanie skasowany
        scanInput.addEventListener('input', () => {
            if (scanTimeout) clearTimeout(scanTimeout);
            scanTimeout = setTimeout(() => {
                if (scanInput.value.trim().length > 0) {
                    handlePalletScan();
                }
            }, 800);
        });
    }

    if (scanBtn) {
        scanBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (scanTimeout) clearTimeout(scanTimeout);
            handlePalletScan();
        });
    }

    if (modalEl) {
        modalEl.querySelectorAll('[data-dismiss="modal"], .close').forEach(btn => {
            btn.addEventListener('click', closeTransferModal);
        });
    }

    let allTransfersData = [];
    let currentStatusFilter = 'ALL';

    const searchInput = document.getElementById('transfers-search-input');
    const totalCountBadge = document.getElementById('total-transfers-count');

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            applyFiltersAndRender();
        });
    }

    document.querySelectorAll('.filter-status-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-status-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentStatusFilter = btn.getAttribute('data-status');
            applyFiltersAndRender();
        });
    });

    async function loadTransfers() {
        if (!tbody) return;
        try {
            const res = await fetch('/osip/api/transfers');
            const json = await res.json();
            if (json.success) {
                allTransfersData = json.transfers || [];
                updateKpiCounters(allTransfersData);
                applyFiltersAndRender();
            } else {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted p-4"><i class="fas fa-exclamation-circle text-warning mr-2"></i> ${json.message || 'Nie udało się pobrać transferów.'}</td></tr>`;
            }
        } catch (e) {
            console.error('Błąd pobierania transferów:', e);
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger p-4"><i class="fas fa-exclamation-triangle mr-2"></i> Wystąpił błąd połączenia z serwerem.</td></tr>`;
        }
    }

    function updateKpiCounters(transfers) {
        let planned = 0, transit = 0, completed = 0, cancelled = 0;
        transfers.forEach(t => {
            if (t.status === 'PLANNED') planned++;
            else if (t.status === 'IN_TRANSIT') transit++;
            else if (t.status === 'COMPLETED') completed++;
            else if (t.status === 'CANCELLED') cancelled++;
        });

        if (cntPlanned) cntPlanned.textContent = planned;
        if (cntTransit) cntTransit.textContent = transit;
        if (cntCompleted) cntCompleted.textContent = completed;
        if (cntCancelled) cntCancelled.textContent = cancelled;
    }

    function applyFiltersAndRender() {
        let filtered = allTransfersData;

        if (currentStatusFilter !== 'ALL') {
            filtered = filtered.filter(t => t.status === currentStatusFilter);
        }

        const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
        if (query) {
            filtered = filtered.filter(t => 
                (t.transfer_code && t.transfer_code.toLowerCase().includes(query)) ||
                (t.source_warehouse && t.source_warehouse.toLowerCase().includes(query)) ||
                (t.destination_warehouse && t.destination_warehouse.toLowerCase().includes(query)) ||
                (t.created_by && t.created_by.toLowerCase().includes(query))
            );
        }

        if (totalCountBadge) {
            totalCountBadge.textContent = `Wyświetlono: ${filtered.length} z ${allTransfersData.length}`;
        }

        renderTransfersTable(filtered);
    }

    function renderTransfersTable(transfers) {
        if (transfers.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-5 text-muted">
                        <i class="fas fa-inbox fa-2x mb-2 text-slate-300"></i>
                        <div>Brak zleceń transferów spełniających kryteria.</div>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = transfers.map(t => {
            let statusBadge = '';
            if (t.status === 'PLANNED') {
                statusBadge = '<span class="status-pill" style="background:#fef3c7; color:#92400e; border:1px solid #fde68a;"><i class="fas fa-clock mr-1"></i> Zaplanowano</span>';
            } else if (t.status === 'IN_TRANSIT') {
                statusBadge = '<span class="status-pill" style="background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd;"><i class="fas fa-truck-loading mr-1"></i> W Tranzycie</span>';
            } else if (t.status === 'COMPLETED') {
                statusBadge = '<span class="status-pill" style="background:#d1fae5; color:#065f46; border:1px solid #a7f3d0;"><i class="fas fa-check-circle mr-1"></i> Zakończono</span>';
            } else if (t.status === 'CANCELLED') {
                statusBadge = '<span class="status-pill" style="background:#ffe4e6; color:#9f1239; border:1px solid #fecdd3;"><i class="fas fa-times-circle mr-1"></i> Anulowano</span>';
            }

            // Określenie czy transport jedzie NA OSIP (O) czy DO CENTRALI (C)
            const dest = (t.destination_warehouse || '').toUpperCase();
            const isToOsip = dest.includes('OSIP');

            let truckBadgeHtml = '';
            if (isToOsip) {
                // Jedzie na OSIP -> Ciężarówka niebieska z literą O
                truckBadgeHtml = `
                    <div class="truck-badge-box truck-to-osip">
                        <div class="truck-avatar" title="Jedzie na Magazyn OSIP (O)">
                            <i class="fas fa-truck-moving"></i>
                            <span class="truck-letter-badge">O</span>
                        </div>
                        <div>
                            <div class="font-weight-bold text-dark" style="font-size: 0.95rem;">${t.transfer_code}</div>
                            <small class="font-weight-bold text-primary"><i class="fas fa-arrow-right mr-1"></i>Dostawa na OSIP [O]</small>
                        </div>
                    </div>
                `;
            } else {
                // Jedzie do Centrali -> Ciężarówka zielona z literą C
                truckBadgeHtml = `
                    <div class="truck-badge-box truck-to-centrala">
                        <div class="truck-avatar" title="Jedzie do Centrali (C)">
                            <i class="fas fa-truck-moving fa-flip-horizontal"></i>
                            <span class="truck-letter-badge">C</span>
                        </div>
                        <div>
                            <div class="font-weight-bold text-dark" style="font-size: 0.95rem;">${t.transfer_code}</div>
                            <small class="font-weight-bold text-success"><i class="fas fa-arrow-left mr-1"></i>Dostawa do Centrali [C]</small>
                        </div>
                    </div>
                `;
            }

            let actionsHtml = '';
            if (t.status === 'PLANNED') {
                actionsHtml = `
                    <button class="btn btn-sm btn-primary font-weight-bold shadow-sm action-dispatch-btn mr-1" data-id="${t.id}">
                        <i class="fas fa-truck-loading mr-1"></i> Wydaj / Załadunek
                    </button>
                    <button class="btn btn-sm btn-outline-danger font-weight-bold action-cancel-btn" data-id="${t.id}">Anuluj</button>
                `;
            } else if (t.status === 'IN_TRANSIT') {
                actionsHtml = `
                    <button class="btn btn-sm btn-outline-danger font-weight-bold action-cancel-btn" data-id="${t.id}">Zawróć</button>
                `;
            } else {
                actionsHtml = `<span class="text-muted small font-weight-bold"><i class="fas fa-lock mr-1"></i> Zamknięte</span>`;
            }

            return `
                <tr class="transfer-row" style="cursor: pointer;" data-id="${t.id}" title="Kliknij, aby otworzyć szczegóły zlecenia">
                    <td class="pl-4">${truckBadgeHtml}</td>
                    <td>
                        <span class="badge px-3 py-1 font-weight-bold" style="background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe;">${t.source_warehouse}</span>
                        <i class="fas fa-arrow-right text-muted mx-2 small"></i>
                        <span class="badge px-3 py-1 font-weight-bold" style="background: #dcfce7; color: #166534; border: 1px solid #bbf7d0;">${t.destination_warehouse}</span>
                    </td>
                    <td>
                        <div class="font-weight-bold text-dark">${t.created_at || '-'}</div>
                        <small class="text-muted"><i class="fas fa-user mr-1"></i>${t.created_by}</small>
                    </td>
                    <td><span class="badge badge-secondary px-3 py-1 font-weight-bold" style="font-size: 0.85rem;">${t.items_count} palet</span></td>
                    <td>${statusBadge}</td>
                    <td class="text-right pr-4">${actionsHtml}</td>
                </tr>
            `;
        }).join('');

        attachActionListeners();
    }

    function attachActionListeners() {
        document.querySelectorAll('.transfer-row').forEach(row => {
            row.addEventListener('click', (e) => {
                if (e.target.closest('button')) return; // ignore button clicks inside the row
                const id = row.getAttribute('data-id');
                if (id) {
                    window.location.href = `/osip/transfers/${id}`;
                }
            });
        });

        document.querySelectorAll('.action-dispatch-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.getAttribute('data-id');
                if (confirm(`Czy chcesz zatwierdzić załadunek dla zlecenia ID #${id}?`)) {
                    const res = await fetch(`/osip/api/transfers/${id}/dispatch`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ loaded_pallets: [] })
                    });
                    const json = await res.json();
                    alert(json.message);
                    loadTransfers();
                }
            });
        });

        document.querySelectorAll('.action-receive-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = btn.getAttribute('data-id');
                openReceiveTransferModal(id);
            });
        });

        document.querySelectorAll('.action-cancel-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.getAttribute('data-id');
                if (confirm(`Czy na pewno chcesz anulować/zwrócić transfer ID #${id}?`)) {
                    const res = await fetch(`/osip/api/transfers/${id}/cancel`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    const json = await res.json();
                    alert(json.message);
                    loadTransfers();
                }
            });
        });
    }

    // ═════════════════════════════════════════════════════════════════
    // LOGIKA MODALU PRZYJĘCIA TRANSFERU (ZE SKANOWANIEM PALET)
    // ═════════════════════════════════════════════════════════════════
    let currentReceivingTransfer = null;
    let scannedItemsState = {};

    window.openReceiveTransferModal = async function(transferId, scannedCode = '') {
        let transfer = allTransfersData.find(t => t.id == transferId || t.transfer_code == transferId);
        try {
            const res = await fetch('/osip/api/transfers');
            if (res.ok) {
                const json = await res.json();
                if (json.success && json.transfers) {
                    allTransfersData = json.transfers;
                    transfer = allTransfersData.find(t => t.id == transferId || t.transfer_code == transferId) || transfer;
                }
            }
        } catch(e) {}

        if (!transfer) {
            console.warn('Nie znaleziono transferu ID:', transferId);
            return;
        }

        currentReceivingTransfer = transfer;
        scannedItemsState = {};
        (transfer.items || []).forEach(it => {
            if (it.status === 'RECEIVED') {
                const code = it.nr_palety || `PAL-${it.pallet_id || it.id}`;
                scannedItemsState[code] = true;
            }
        });

        const codeBadge = document.getElementById('receive-code-badge');
        const dirLabel = document.getElementById('receive-direction-label');
        const countBadge = document.getElementById('receive-items-count-badge');
        if (codeBadge) codeBadge.textContent = transfer.transfer_code;
        if (dirLabel) dirLabel.textContent = `${transfer.source_warehouse} ➔ ${transfer.destination_warehouse}`;
        if (countBadge) countBadge.textContent = `${transfer.items ? transfer.items.length : 0} pozycji`;

        renderReceiveModalItems();

        if (scannedCode) {
            markItemAsScanned(scannedCode);
        }

        const receiveModalEl = document.getElementById('modal-receive-transfer');
        if (receiveModalEl) {
            try {
                if (window.jQuery && typeof window.jQuery(receiveModalEl).modal === 'function') {
                    window.jQuery(receiveModalEl).modal('show');
                }
            } catch(e) {}
            receiveModalEl.classList.add('show');
            receiveModalEl.style.display = 'block';
            receiveModalEl.removeAttribute('aria-hidden');
            document.body.classList.add('modal-open');

            let backdrop = document.querySelector('.modal-backdrop');
            if (!backdrop) {
                backdrop = document.createElement('div');
                backdrop.className = 'modal-backdrop fade show';
                document.body.appendChild(backdrop);
            }

            const recInput = document.getElementById('receive-scan-input');
            if (recInput) {
                recInput.value = '';
                setTimeout(() => recInput.focus(), 200);
            }
        }
    };

    window.closeReceiveModal = function() {
        const receiveModalEl = document.getElementById('modal-receive-transfer');
        if (receiveModalEl) {
            try {
                if (window.jQuery && typeof window.jQuery(receiveModalEl).modal === 'function') {
                    window.jQuery(receiveModalEl).modal('hide');
                }
            } catch(e) {}
            receiveModalEl.classList.remove('show');
            receiveModalEl.style.display = 'none';
            receiveModalEl.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('modal-open');
            let backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) backdrop.remove();
        }
    };

    function renderReceiveModalItems() {
        const tbody = document.getElementById('receive-modal-tbody');
        if (!tbody || !currentReceivingTransfer) return;

        const items = currentReceivingTransfer.items || [];
        if (items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted p-4">Brak pozycji w tym zleceniu transferu.</td></tr>`;
            updateReceiveProgress();
            return;
        }

        tbody.innerHTML = items.map((it, idx) => {
            const code = it.nr_palety || `PAL-${it.pallet_id || it.id}`;
            const isScanned = !!scannedItemsState[code] || it.status === 'RECEIVED';
            const statusBadge = isScanned 
                ? '<span class="badge badge-success px-3 py-1 font-weight-bold" style="font-size: 0.85rem;"><i class="fas fa-check-circle mr-1"></i> Zeskanowano</span>'
                : '<span class="badge badge-warning px-3 py-1 font-weight-bold" style="font-size: 0.85rem;"><i class="fas fa-clock mr-1"></i> Oczekuje</span>';

            const rowStyle = isScanned ? 'background-color: #f0fdf4;' : '';
            const defaultLoc = currentReceivingTransfer.destination_warehouse === 'OSIP' ? 'OS01' : 'MS01';

            return `
                <tr style="${rowStyle}" id="receive-row-${idx}">
                    <td class="text-center">${statusBadge}</td>
                    <td><strong class="text-dark">${code}</strong></td>
                    <td>${it.product_name}</td>
                    <td><span class="badge badge-secondary px-2 py-1 font-weight-bold">${it.requested_qty} ${it.unit || 'kg'}</span></td>
                    <td><span class="badge badge-light border text-dark font-weight-bold px-2 py-1">${defaultLoc}</span></td>
                </tr>
            `;
        }).join('');

        updateReceiveProgress();
    }

    window.toggleItemScanned = function(code) {
        if (scannedItemsState[code]) {
            delete scannedItemsState[code];
        } else {
            scannedItemsState[code] = true;
        }
        renderReceiveModalItems();
    };

    function markItemAsScanned(code) {
        if (!currentReceivingTransfer) return;
        const codeClean = code.trim();
        const items = currentReceivingTransfer.items || [];
        const matched = items.find(it => (it.nr_palety && it.nr_palety.toLowerCase() === codeClean.toLowerCase()) || (`${it.pallet_id}` === codeClean) || (`PAL-${it.pallet_id}`.toLowerCase() === codeClean.toLowerCase()));

        if (matched) {
            const realCode = matched.nr_palety || `PAL-${matched.pallet_id || matched.id}`;
            scannedItemsState[realCode] = true;
            renderReceiveModalItems();
        } else {
            alert(`Zeskanowana paleta ${codeClean} nie należy do tego zlecenia transferu!`);
        }
    }

    function updateReceiveProgress() {
        if (!currentReceivingTransfer) return;
        const total = (currentReceivingTransfer.items || []).length;
        const scanned = Object.keys(scannedItemsState).length;
        const progressEl = document.getElementById('receive-scan-progress');
        const progressBar = document.getElementById('receive-progress-bar');
        
        if (progressEl) progressEl.textContent = `${scanned} / ${total} palet`;
        if (progressBar) {
            const pct = total > 0 ? Math.round((scanned / total) * 100) : 0;
            progressBar.style.width = `${pct}%`;
        }
    }

    const recInput = document.getElementById('receive-scan-input');
    const recBtn = document.getElementById('receive-scan-btn');
    let recScanTimeout = null;

    if (recInput) {
        recInput.addEventListener('input', () => {
            clearTimeout(recScanTimeout);
            recScanTimeout = setTimeout(() => {
                const val = recInput.value.trim();
                if (val) {
                    markItemAsScanned(val);
                    recInput.value = '';
                    recInput.focus();
                }
            }, 350);
        });

        recInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(recScanTimeout);
                const val = recInput.value.trim();
                if (val) {
                    markItemAsScanned(val);
                    recInput.value = '';
                    recInput.focus();
                }
            }
        });
    }

    if (recBtn) {
        recBtn.addEventListener('click', () => {
            const val = recInput ? recInput.value.trim() : '';
            if (val) {
                markItemAsScanned(val);
                recInput.value = '';
                recInput.focus();
            }
        });
    }

    const btnConfirmFullReceive = document.getElementById('btn-confirm-full-receive');
    if (btnConfirmFullReceive) {
        btnConfirmFullReceive.addEventListener('click', async () => {
            if (!currentReceivingTransfer) return;

            const targetLocs = {};
            document.querySelectorAll('.target-loc-input').forEach(inp => {
                const c = inp.getAttribute('data-code');
                targetLocs[c] = inp.value.trim() || 'OS01';
            });

            const res = await fetch(`/osip/api/transfers/${currentReceivingTransfer.id}/receive`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_locations: targetLocs })
            });
            const json = await res.json();
            alert(json.message);
            if (json.success) {
                closeReceiveModal();
                loadTransfers();
            }
        });
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('#btn-new-transfer');
        if (btn) {
            e.preventDefault();
            openTransferModal();
        }
    });

    if (addItemBtn && itemsList) {
        addItemBtn.addEventListener('click', () => {
            addScannedItemRow();
        });
    }

    if (submitNew) {
        submitNew.addEventListener('click', async () => {
            const source = document.getElementById('new-source-wh').value;
            const dest = document.getElementById('new-dest-wh').value;
            const notes = document.getElementById('new-transfer-notes').value;

            const itemRows = document.querySelectorAll('.item-row');
            const items = [];
            itemRows.forEach(row => {
                const p = row.querySelector('.item-product').value;
                const q = row.querySelector('.item-qty').value;
                const codeInp = row.querySelector('.item-code');
                const palletIdInp = row.querySelector('.item-pallet-id');

                if (p && q) {
                    items.push({
                        nr_palety: codeInp ? codeInp.value : null,
                        pallet_id: palletIdInp && palletIdInp.value ? parseInt(palletIdInp.value, 10) : null,
                        product_name: p,
                        requested_qty: parseFloat(q),
                        unit: 'kg',
                        item_type: 'raw'
                    });
                }
            });

            if (items.length === 0) {
                alert('Dodaj co najmniej jedną pozycję lub zeskanuj paletę do transferu.');
                return;
            }

            const res = await fetch('/osip/api/transfers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_warehouse: source,
                    destination_warehouse: dest,
                    notes: notes,
                    items: items
                })
            });

            const json = await res.json();
            alert(json.message);
            if (json.success) {
                localStorage.removeItem('osip_transfer_draft');
                closeTransferModal();
                formNew.reset();
                itemsList.innerHTML = `<div class="text-center text-muted py-3 border rounded bg-white" id="empty-items-msg"><i class="fas fa-barcode mr-1"></i> Brak zeskanowanych palet. Zeskanuj pierwszą paletę powyżej.</div>`;
                updateScannedCounters();
                loadTransfers();
            }
        });
    }

    // ═════════════════════════════════════════════════════════════════
    // BEZPIECZEŃSTWO DANYCH: AUTO-ZAPIS I ODZYSKIWANIE SZKICU DANYCH
    // ═════════════════════════════════════════════════════════════════
    function saveTransferDraft() {
        try {
            const source = inputSourceWh ? inputSourceWh.value : '';
            const dest = inputDestWh ? inputDestWh.value : '';
            const notes = document.getElementById('new-transfer-notes')?.value || '';
            const itemRows = document.querySelectorAll('.item-row');
            
            const items = [];
            itemRows.forEach(row => {
                const p = row.querySelector('.item-product')?.value || '';
                const q = row.querySelector('.item-qty')?.value || '';
                const codeInp = row.querySelector('.item-code')?.value || '';
                const palletIdInp = row.querySelector('.item-pallet-id')?.value || '';
                const batch = row.querySelector('.item-batch')?.value || '';
                const dateVal = row.querySelector('.item-date')?.value || '';
                if (p || codeInp) {
                    items.push({
                        nr_palety: codeInp,
                        pallet_id: palletIdInp,
                        product_name: p,
                        nr_partii: batch,
                        data_produkcji: dateVal,
                        requested_qty: q
                    });
                }
            });

            if (items.length > 0 || source || dest) {
                const draft = { source, dest, notes, items, timestamp: Date.now() };
                localStorage.setItem('osip_transfer_draft', JSON.stringify(draft));
            } else {
                localStorage.removeItem('osip_transfer_draft');
            }
        } catch (e) {
            console.warn('Save draft error:', e);
        }
    }

    function checkAndRestoreDraft() {
        try {
            const rawDraft = localStorage.getItem('osip_transfer_draft');
            if (!rawDraft) return;
            const draft = JSON.parse(rawDraft);
            if (draft && draft.items && draft.items.length > 0) {
                const alertBox = document.getElementById('draft-restore-alert');
                const infoEl = document.getElementById('draft-restore-info');
                if (alertBox) {
                    alertBox.style.display = 'block';
                    if (infoEl) infoEl.textContent = `Odnaleziono niezapisany szkic zlecenia (${draft.items.length} zeskanowanych palet). Czy chcesz kontynuować?`;
                }
            }
        } catch (e) {
            console.warn('Check draft error:', e);
        }
    }

    window.restoreDraftModal = function() {
        try {
            const rawDraft = localStorage.getItem('osip_transfer_draft');
            if (!rawDraft) return;
            const draft = JSON.parse(rawDraft);

            // Najpierw otwórz modal
            openTransferModal();

            // Następnie przejdź do odpowiedniego kroku
            if (draft.source && draft.dest) {
                goToStep(2, draft.source, draft.dest);
            } else {
                goToStep(1);
            }

            if (draft.notes) {
                const notesEl = document.getElementById('new-transfer-notes');
                if (notesEl) notesEl.value = draft.notes;
            }

            // Dodaj palety do listy (addScannedItemRow blokuje duplikaty)
            if (draft.items && draft.items.length > 0) {
                const emptyMsg = document.getElementById('empty-items-msg');
                if (emptyMsg) emptyMsg.style.display = 'none';
                draft.items.forEach(it => addScannedItemRow(it));
                updateScannedCounters();
            }

            const alertBox = document.getElementById('draft-restore-alert');
            if (alertBox) alertBox.style.display = 'none';
        } catch (e) {
            console.warn('Error restoring draft modal:', e);
        }
    };

    window.discardDraft = function() {
        localStorage.removeItem('osip_transfer_draft');
        const alertBox = document.getElementById('draft-restore-alert');
        if (alertBox) alertBox.style.display = 'none';
    };

    // Auto-save draft przy każdej zmianie w formularzu
    document.addEventListener('input', (e) => {
        if (e.target.closest('#modal-new-transfer')) {
            saveTransferDraft();
        }
    });

    // Ostrzeżenie przed wyjściem ze strony
    window.addEventListener('beforeunload', (e) => {
        const itemRows = document.querySelectorAll('.item-row');
        if (itemRows.length > 0 && modalEl && (modalEl.classList.contains('show') || modalEl.style.display === 'block')) {
            e.preventDefault();
            e.returnValue = 'Masz niezapisane palety w transferze! Czy na pewno chcesz opuścić stronę?';
            return e.returnValue;
        }
    });

    loadTransfers();
    checkAndRestoreDraft();

    // ─── POWIADOMIENIA O TRANSFERACH IN_TRANSIT na stronie transferów ───
    async function checkInboundTransferBanner() {
        try {
            const res = await fetch('/osip/api/transfers');
            const json = await res.json();
            if (!json.success) return;
            const inTransit = (json.transfers || []).filter(t => t.status === 'IN_TRANSIT');
            const banner = document.getElementById('transfers-inbound-banner');
            const bannerText = document.getElementById('transfers-inbound-text');
            if (!banner) return;
            if (inTransit.length > 0) {
                const toOsip = inTransit.filter(t => (t.destination_warehouse || '').toUpperCase().includes('OSIP'));
                const toCentrala = inTransit.filter(t => !(t.destination_warehouse || '').toUpperCase().includes('OSIP'));
                let parts = [];
                if (toOsip.length > 0) parts.push(`🚛 [O] ${toOsip.length} transfer${toOsip.length > 1 ? 'y' : ''} jedzie NA OSIP`);
                if (toCentrala.length > 0) parts.push(`🚛 [C] ${toCentrala.length} transfer${toCentrala.length > 1 ? 'y' : ''} jedzie DO CENTRALI`);
                if (bannerText) bannerText.textContent = parts.join(' | ');
                banner.style.display = 'flex';
            } else {
                banner.style.display = 'none';
            }
        } catch (e) {
            console.warn('checkInboundTransferBanner error:', e);
        }
    }
    checkInboundTransferBanner();
    // ═════════════════════════════════════════════════════════════════
    // LOGIKA MODALU PODGLĄDU
    // ═════════════════════════════════════════════════════════════════
    window.openViewTransferModal = async function(transferId) {
        let transfer = allTransfersData.find(t => t.id == transferId || t.transfer_code == transferId);
        try {
            const res = await fetch('/osip/api/transfers');
            if (res.ok) {
                const json = await res.json();
                if (json.success && json.transfers) {
                    allTransfersData = json.transfers;
                    transfer = allTransfersData.find(t => t.id == transferId || t.transfer_code == transferId) || transfer;
                }
            }
        } catch(e) {}

        if (!transfer) return;

        document.getElementById('view-modal-code').textContent = transfer.transfer_code || '';
        
        let statusBadge = '';
        if (transfer.status === 'PLANNED') statusBadge = '<span class="badge badge-warning px-3 py-1 font-weight-bold"><i class="fas fa-clock mr-1"></i> Zaplanowano</span>';
        else if (transfer.status === 'IN_TRANSIT') statusBadge = '<span class="badge badge-primary px-3 py-1 font-weight-bold"><i class="fas fa-truck-loading mr-1"></i> W Tranzycie</span>';
        else if (transfer.status === 'COMPLETED') statusBadge = '<span class="badge badge-success px-3 py-1 font-weight-bold"><i class="fas fa-check-circle mr-1"></i> Zakończono</span>';
        else if (transfer.status === 'CANCELLED') statusBadge = '<span class="badge badge-danger px-3 py-1 font-weight-bold"><i class="fas fa-times-circle mr-1"></i> Anulowano</span>';
        
        document.getElementById('view-modal-status').innerHTML = statusBadge;
        document.getElementById('view-modal-route').textContent = `${transfer.source_warehouse} ➔ ${transfer.destination_warehouse}`;
        document.getElementById('view-modal-creator').innerHTML = `${transfer.created_at || '-'} <br><small class="text-muted"><i class="fas fa-user mr-1"></i>${transfer.created_by}</small>`;
        
        const items = transfer.items || [];
        const receivedCount = items.filter(it => it.status === 'RECEIVED').length;
        document.getElementById('view-modal-count').textContent = `${receivedCount} z ${items.length} odebrane`;

        const tbody = document.getElementById('view-modal-tbody');
        tbody.innerHTML = items.map(item => {
            let itemStatusBadge = '';
            let rowStyle = '';
            if (item.status === 'RECEIVED') {
                itemStatusBadge = '<span class="badge badge-success px-3 py-1 font-weight-bold" style="font-size:0.85rem;"><i class="fas fa-check-circle mr-1"></i> Odebrana</span>';
                rowStyle = 'background-color: #f0fdf4;';
            } else if (item.status === 'LOADED' || item.status === 'PLANNED') {
                itemStatusBadge = '<span class="badge badge-warning px-3 py-1 font-weight-bold" style="font-size:0.85rem;"><i class="fas fa-clock mr-1"></i> Oczekuje</span>';
            } else if (item.status === 'CANCELLED') {
                itemStatusBadge = '<span class="badge badge-danger px-3 py-1 font-weight-bold" style="font-size:0.85rem;"><i class="fas fa-times-circle mr-1"></i> Zwrócona</span>';
            }

            return `
                <tr>
                    <td>${itemStatusBadge}</td>
                    <td><strong>${item.nr_palety || 'Brak'}</strong></td>
                    <td>${item.product_name || '-'}</td>
                    <td><strong>${item.requested_qty || 0}</strong></td>
                </tr>
            `;
        }).join('');

        const viewModalEl = document.getElementById('modal-view-transfer');
        if (viewModalEl) {
            document.body.appendChild(viewModalEl);
            viewModalEl.style.zIndex = '10050';
            try {
                if (window.jQuery && typeof window.jQuery(viewModalEl).modal === 'function') {
                    window.jQuery(viewModalEl).modal('show');
                }
            } catch (e) {}
            viewModalEl.classList.add('show');
            viewModalEl.style.display = 'block';
            viewModalEl.removeAttribute('aria-hidden');
            document.body.classList.add('modal-open');

            let backdrop = document.querySelector('.modal-backdrop');
            if (!backdrop) {
                backdrop = document.createElement('div');
                backdrop.className = 'modal-backdrop fade show';
                backdrop.style.zIndex = '10040';
                document.body.appendChild(backdrop);
            } else {
                backdrop.style.zIndex = '10040';
            }
        }
    };

    window.closeViewModal = function() {
        const viewModalEl = document.getElementById('modal-view-transfer');
        if (viewModalEl) {
            try {
                if (window.jQuery && typeof window.jQuery(viewModalEl).modal === 'function') {
                    window.jQuery(viewModalEl).modal('hide');
                }
            } catch (e) {}
            viewModalEl.classList.remove('show');
            viewModalEl.style.display = 'none';
            viewModalEl.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('modal-open');
            document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
        }
    };

});
