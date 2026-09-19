/**
 * Logika Kalkulatora Zasypu (Sprawdzanie zapotrzebowania, kolejka FIFO, blokady i wydruk zamówień)
 */
const ZasypCalculatorModule = (function () {
    'use strict';

    const CHECK_STOCK_API = '/warehouse-v2/api/orders/check_stock';
    const CREATE_ORDER_API = '/warehouse-v2/api/orders/create';
    const START_PICKING_API = '/warehouse-v2/api/orders/start-picking';
    const SUROWCE_API = '/warehouse-v2/api/orders/surowce';

    let _availableSurowce = [];
    let _missingItemsToOrder = [];
    let _lastCalculationData = null;

    function normStr(s) {
        if (!s) return '';
        let str = String(s).toLowerCase().trim();
        const repl = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'};
        for (let k in repl) {
            str = str.split(k).join(repl[k]);
        }
        return str.replace(/[^a-z0-9]/g, '');
    }

    function init() {
        loadSurowce();
    }

    function loadSurowce() {
        return fetch(SUROWCE_API)
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success && data.surowce) {
                    _availableSurowce = data.surowce;
                    populateDatalist();
                }
                return _availableSurowce;
            })
            .catch(function(err) {
                console.error('Błąd podczas pobierania surowców do kalkulatora:', err);
                return _availableSurowce;
            });
    }

    function populateDatalist() {
        const datalist = document.getElementById('calc-surowce-datalist');
        if (!datalist) return;
        datalist.innerHTML = '';
        _availableSurowce.forEach(function(s) {
            if (s && s.nazwa) {
                const opt = document.createElement('option');
                opt.value = s.nazwa;
                datalist.appendChild(opt);
            }
        });
    }

    function openModal() {
        const modal = document.getElementById('zasyp-calculator-modal');
        if (modal) {
            modal.style.display = 'flex';
            resetForm();
            loadSurowce().then(function() {
                if (document.getElementById('calc-items-tbody').children.length === 0) {
                    addRow();
                }
            });
        }
    }

    function closeModal() {
        const modal = document.getElementById('zasyp-calculator-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    function resetForm() {
        document.getElementById('calc-order-tons').value = '';
        document.getElementById('calc-items-tbody').innerHTML = '';
        hideResults();
    }

    function hideResults() {
        document.getElementById('calc-results-section').style.display = 'none';
        document.getElementById('calc-results-tbody').innerHTML = '';
        document.getElementById('calc-order-action-container').style.display = 'none';
        _missingItemsToOrder = [];
        _lastCalculationData = null;
    }

    function addRow() {
        populateDatalist();
        const tbody = document.getElementById('calc-items-tbody');
        const template = document.getElementById('calc-row-template').content.cloneNode(true);
        const row = template.querySelector('tr');
        const input = row.querySelector('.calc-surowiec-input');
        const rate = row.querySelector('.calc-rate-input');

        if (input) {
            input.addEventListener('input', function() {
                hideResults();
                validateDuplicates();
            });
            input.addEventListener('change', function() {
                validateDuplicates();
            });
            input.addEventListener('focus', function() {
                populateDatalist();
            });
        }
        if (rate) {
            rate.addEventListener('input', hideResults);
        }

        tbody.appendChild(template);
        hideResults();
    }

    function parseNum(val) {
        if (val === null || val === undefined) return 0;
        const str = String(val).trim().replace(',', '.');
        return parseFloat(str) || 0;
    }

    function validateDuplicates() {
        const tbody = document.getElementById('calc-items-tbody');
        const rows = tbody.querySelectorAll('tr');
        const seen = new Map();
        let hasDuplicates = false;

        rows.forEach(function(row) {
            const input = row.querySelector('.calc-surowiec-input');
            if (!input) return;
            const val = normStr(input.value);
            input.style.borderColor = '#cbd5e1';
            input.style.backgroundColor = '#ffffff';

            if (val) {
                if (seen.has(val)) {
                    hasDuplicates = true;
                    input.style.borderColor = '#ef4444';
                    input.style.backgroundColor = '#fef2f2';
                    const prevInput = seen.get(val);
                    prevInput.style.borderColor = '#ef4444';
                    prevInput.style.backgroundColor = '#fef2f2';
                } else {
                    seen.set(val, input);
                }
            }
        });

        return !hasDuplicates;
    }

    function collectItems() {
        const items = [];
        const tbody = document.getElementById('calc-items-tbody');
        const rows = tbody.querySelectorAll('tr');
        const seenNames = new Set();
        let duplicateFound = null;
        let invalidDictFound = null;

        rows.forEach(function(row) {
            const inputEl = row.querySelector('.calc-surowiec-input');
            const surowiec = inputEl ? inputEl.value.trim() : '';
            const rateInput = row.querySelector('.calc-rate-input')?.value;
            const rate = parseNum(rateInput);

            if (surowiec) {
                const norm = normStr(surowiec);
                if (seenNames.has(norm)) {
                    duplicateFound = surowiec;
                }
                seenNames.add(norm);

                let canonicalName = surowiec;
                if (_availableSurowce && _availableSurowce.length > 0) {
                    const dictMatch = _availableSurowce.find(function(s) {
                        if (!s || !s.nazwa) return false;
                        const sClean = s.nazwa.trim().toLowerCase();
                        return sClean === surowiec.toLowerCase() || normStr(s.nazwa) === norm;
                    });
                    if (dictMatch) {
                        canonicalName = dictMatch.nazwa;
                    } else {
                        invalidDictFound = surowiec;
                    }
                }

                if (rate > 0) {
                    items.push({
                        surowiec_nazwa: canonicalName,
                        przelicznik_na_1t: rate
                    });
                }
            }
        });

        if (duplicateFound) {
            const msg = `⚠️ Surowiec "${duplicateFound}" został dodany więcej niż raz w kalkulatorze.\nKalkulator nie pozwala na duplikaty — połącz przelicznik w jednej pozycji.`;
            if (typeof showToast === 'function') {
                showToast(msg, 'warning');
            } else {
                alert(msg);
            }
            return null;
        }

        if (invalidDictFound) {
            const msg = `⚠️ Surowiec "${invalidDictFound}" nie występuje w słowniku surowców.\nWybierz poprawny surowiec z listy podpowiedzi lub dodaj go wcześniej do słownika.`;
            if (typeof showToast === 'function') {
                showToast(msg, 'warning');
            } else {
                alert(msg);
            }
            return null;
        }

        return items;
    }

    function checkStock() {
        const tonsInput = document.getElementById('calc-order-tons').value;
        const tons = parseNum(tonsInput);

        if (tons <= 0) {
            const msg = '⚠️ Wprowadź prawidłową wielkość zlecenia w tonach (większą od 0).';
            if (typeof showToast === 'function') showToast(msg, 'warning');
            else alert(msg);
            return;
        }

        const items = collectItems();
        if (items === null) {
            return; // Duplikat wykryty
        }

        if (items.length === 0) {
            const msg = '⚠️ Dodaj przynajmniej jeden surowiec ze słownika i podaj jego przelicznik (kg/1t).';
            if (typeof showToast === 'function') showToast(msg, 'warning');
            else alert(msg);
            return;
        }

        fetch(CHECK_STOCK_API, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                order_tons: tons,
                items: items
            })
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                _lastCalculationData = {
                    order_tons: tons,
                    results: data.results || [],
                    scanned_zones: data.scanned_zones || []
                };
                renderResults(data.results || [], data.scanned_zones || [], tons);
            } else {
                const errorMsg = data.message || data.error || 'Nieznany błąd podczas sprawdzania stanów.';
                if (typeof showToast === 'function') showToast('❌ ' + errorMsg, 'error');
                else alert('❌ ' + errorMsg);
            }
        })
        .catch(function(err) {
            console.error('Błąd zapytania check_stock:', err);
            if (typeof showToast === 'function') showToast('❌ Błąd połączenia z serwerem.', 'error');
            else alert('❌ Błąd połączenia z serwerem.');
        });
    }

    function renderResults(results, scannedZones, orderTons) {
        const tbody = document.getElementById('calc-results-tbody');
        tbody.innerHTML = '';
        _missingItemsToOrder = [];
        let hasMissing = false;

        // Renderowanie informacji o przeszukanych magazynach
        const zonesContainer = document.getElementById('calc-scanned-zones-info');
        if (zonesContainer) {
            const zonesList = (scannedZones && scannedZones.length > 0) 
                ? scannedZones.join(' &bull; ') 
                : 'Regały (R*) &bull; Magazyn podręczny (MP01) &bull; Bufor przyjęć (BF_MP01)';
            zonesContainer.innerHTML = `🔍 <strong>Przeszukiwane strefy magazynowe:</strong> ${zonesList}`;
        }

        results.forEach(function(r, index) {
            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid #e2e8f0';

            let missingHtml = `<span style="background: #f0fdf4; color: #166534; font-weight: 700; padding: 5px 12px; border-radius: 6px; font-size: 13px; border: 1px solid #bbf7d0;">0.00 kg (KOMPLET)</span>`;
            if (r.brakujace_kg > 0) {
                missingHtml = `<span style="background: #fef2f2; color: #b91c1c; font-weight: 700; padding: 5px 12px; border-radius: 6px; font-size: 13px; border: 1px solid #fecaca;">-${r.brakujace_kg.toFixed(2)} kg</span>`;
                hasMissing = true;
                _missingItemsToOrder.push({
                    surowiec_nazwa: r.surowiec_nazwa,
                    ilosc_kg: r.brakujace_kg
                });
            }

            const stanColor = r.stan_magazynowy_kg >= r.potrzebne_kg ? '#059669' : '#d97706';
            const blockedBadge = (r.zablokowane_kg && r.zablokowane_kg > 0)
                ? `<div style="margin-top: 4px;"><span style="background: #fffbeb; color: #b45309; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; border: 1px solid #fde68a;">⚠️ Zablokowane: ${r.zablokowane_kg.toFixed(2)} kg</span></div>`
                : '';

            const locsText = (r.lokalizacje && r.lokalizacje.length > 0)
                ? r.lokalizacje.join(', ')
                : 'Brak w przeszukanych strefach';

            tr.innerHTML = `
                <td style="padding: 14px; font-weight: 700; color: #0f172a; font-size: 14px; vertical-align: top;">
                    <div>${r.surowiec_nazwa}</div>
                    <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-top: 4px;">
                        📍 Lokalizacje: <strong>${locsText}</strong>
                    </div>
                </td>
                <td style="padding: 14px; text-align: right; font-size: 14px; font-weight: 600; color: #334155; vertical-align: top;">
                    ${r.potrzebne_kg.toFixed(2)} kg
                    <div style="font-size: 11px; color: #94a3b8; font-weight: normal;">(norma: ${r.przelicznik_na_1t} kg/t)</div>
                </td>
                <td style="padding: 14px; text-align: right; font-size: 14px; color: ${stanColor}; font-weight: 700; vertical-align: top;">
                    ${r.stan_magazynowy_kg.toFixed(2)} kg
                    ${blockedBadge}
                </td>
                <td style="padding: 14px; text-align: right; font-size: 14px; vertical-align: top;">
                    ${missingHtml}
                </td>
            `;
            tbody.appendChild(tr);

            // Wiersz ze szczegółami palet FIFO dla danego surowca
            if (r.palety_fifo && r.palety_fifo.length > 0) {
                const trDetails = document.createElement('tr');
                trDetails.style.backgroundColor = '#f8fafc';
                trDetails.style.borderBottom = '2px solid #cbd5e1';

                let palletsTableHtml = `
                    <div style="padding: 12px 14px; background: #f8fafc; border-radius: 8px;">
                        <div style="font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                            <span class="material-icons" style="font-size: 16px; color: #3b82f6;">sort</span>
                            Kolejka wydań FIFO & Wykaz palet (${r.surowiec_nazwa}):
                        </div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 12px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
                            <thead>
                                <tr style="background: #e2e8f0; color: #334155;">
                                    <th style="padding: 6px 10px; text-align: center; width: 14%;">Kolejka FIFO</th>
                                    <th style="padding: 6px 10px; text-align: left; width: 18%;">Lokalizacja</th>
                                    <th style="padding: 6px 10px; text-align: left; width: 22%;">Nr Palety / SSCC</th>
                                    <th style="padding: 6px 10px; text-align: left; width: 18%;">Partia / Data</th>
                                    <th style="padding: 6px 10px; text-align: right; width: 14%;">Ilość</th>
                                    <th style="padding: 6px 10px; text-align: center; width: 14%;">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                r.palety_fifo.forEach(function(p) {
                    let statusBadge = '';
                    let fifoBadge = '';

                    if (p.is_blocked) {
                        statusBadge = `<span style="background: #fef2f2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-weight: 700; border: 1px solid #fecaca;">ZABLOKOWANA${p.powod_blokady ? ' (' + p.powod_blokady + ')' : ''}</span>`;
                        fifoBadge = `<span style="color: #94a3b8; font-weight: 600;">— (blokada)</span>`;
                    } else {
                        statusBadge = `<span style="background: #f0fdf4; color: #166534; padding: 2px 8px; border-radius: 4px; font-weight: 700; border: 1px solid #bbf7d0;">DOSTĘPNA</span>`;
                        if (p.fifo_rank === 1) {
                            fifoBadge = `<span style="background: #2563eb; color: #ffffff; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px;">#1 WYDAJ PIERWSZĄ</span>`;
                        } else {
                            fifoBadge = `<span style="background: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px;">#${p.fifo_rank} FIFO</span>`;
                        }
                    }

                    palletsTableHtml += `
                        <tr style="border-bottom: 1px solid #f1f5f9; ${p.is_blocked ? 'background: #fff8f8;' : ''}">
                            <td style="padding: 6px 10px; text-align: center;">${fifoBadge}</td>
                            <td style="padding: 6px 10px; font-weight: 700; color: #1e293b;">📍 ${p.lokalizacja}</td>
                            <td style="padding: 6px 10px; font-family: monospace; font-weight: 600;">${p.nr_palety}</td>
                            <td style="padding: 6px 10px; color: #475569;">${p.nr_partii} <span style="font-size: 11px; color: #94a3b8;">(${p.data || '—'})</span></td>
                            <td style="padding: 6px 10px; text-align: right; font-weight: 700; color: ${p.is_blocked ? '#94a3b8' : '#0f172a'};">${p.stan_magazynowy.toFixed(2)} kg</td>
                            <td style="padding: 6px 10px; text-align: center;">${statusBadge}</td>
                        </tr>
                    `;
                });

                palletsTableHtml += `
                            </tbody>
                        </table>
                    </div>
                `;

                trDetails.innerHTML = `<td colspan="4" style="padding: 0 14px 14px 14px;">${palletsTableHtml}</td>`;
                tbody.appendChild(trDetails);
            }
        });

        document.getElementById('calc-results-section').style.display = 'block';
        
        // Always show picking button after calculation (picking order covers all pallets, not just missing)
        document.getElementById('calc-order-action-container').style.display = 'flex';

        // Przewiń płynnie do sekcji wyników
        document.getElementById('calc-results-section').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function printFifoList() {
        if (!_lastCalculationData || !_lastCalculationData.results || _lastCalculationData.results.length === 0) {
            alert('Najpierw wykonaj kalkulację zapotrzebowania, aby wydrukować listę wydań FIFO.');
            return;
        }

        const data = _lastCalculationData;
        const nowStr = new Date().toLocaleString('pl-PL');
        const tons = data.order_tons || 0;

        let printWindow = window.open('', '_blank', 'width=900,height=700');
        if (!printWindow) {
            alert('Zezwól na wyskakujące okna (pop-up), aby wydrukować specyfikację wydań FIFO.');
            return;
        }

        let itemsSummaryRows = '';
        let fifoPalletsRows = '';

        data.results.forEach(function(r) {
            const missingText = r.brakujace_kg > 0 ? `-${r.brakujace_kg.toFixed(2)} kg (BRAK)` : '0.00 kg (KOMPLET)';
            itemsSummaryRows += `
                <tr>
                    <td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">${r.surowiec_nazwa}</td>
                    <td style="padding: 8px; border: 1px solid #cbd5e1; text-align: right;">${r.potrzebne_kg.toFixed(2)} kg</td>
                    <td style="padding: 8px; border: 1px solid #cbd5e1; text-align: right;">${r.stan_magazynowy_kg.toFixed(2)} kg</td>
                    <td style="padding: 8px; border: 1px solid #cbd5e1; text-align: right; color: ${r.zablokowane_kg > 0 ? '#b45309' : '#64748b'};">${r.zablokowane_kg.toFixed(2)} kg</td>
                    <td style="padding: 8px; border: 1px solid #cbd5e1; text-align: right; font-weight: bold; color: ${r.brakujace_kg > 0 ? '#b91c1c' : '#166534'};">${missingText}</td>
                </tr>
            `;

            if (r.palety_fifo && r.palety_fifo.length > 0) {
                r.palety_fifo.forEach(function(p) {
                    const statusStr = p.is_blocked ? `ZABLOKOWANA (${p.powod_blokady || 'blokada'})` : 'DOSTĘPNA';
                    const fifoStr = p.fifo_rank ? `#${p.fifo_rank} (FIFO)` : '—';
                    fifoPalletsRows += `
                        <tr style="${p.is_blocked ? 'background-color: #fef2f2;' : ''}">
                            <td style="padding: 6px 8px; border: 1px solid #cbd5e1; text-align: center; font-weight: bold;">${fifoStr}</td>
                            <td style="padding: 6px 8px; border: 1px solid #cbd5e1; font-weight: bold;">${r.surowiec_nazwa}</td>
                            <td style="padding: 6px 8px; border: 1px solid #cbd5e1; text-align: center; font-weight: bold;">${p.lokalizacja}</td>
                            <td style="padding: 6px 8px; border: 1px solid #cbd5e1; font-family: monospace;">${p.nr_palety}</td>
                            <td style="padding: 6px 8px; border: 1px solid #cbd5e1;">${p.nr_partii}</td>
                            <td style="padding: 6px 8px; border: 1px solid #cbd5e1; text-align: right; font-weight: bold;">${p.stan_magazynowy.toFixed(2)} kg</td>
                            <td style="padding: 6px 8px; border: 1px solid #cbd5e1; text-align: center;">${statusStr}</td>
                            <td style="padding: 6px 8px; border: 1px solid #cbd5e1; width: 100px;"></td>
                        </tr>
                    `;
                });
            }
        });

        const docHtml = `
            <!DOCTYPE html>
            <html lang="pl">
            <head>
                <meta charset="UTF-8">
                <title>Karta Zapotrzebowania & Lista Wydań FIFO</title>
                <style>
                    body { font-family: Arial, sans-serif; font-size: 13px; color: #1e293b; padding: 20px; }
                    h1 { font-size: 20px; margin: 0 0 6px 0; }
                    .meta-box { margin-bottom: 20px; padding: 10px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; }
                    table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
                    th { background: #f1f5f9; padding: 8px; border: 1px solid #cbd5e1; text-align: left; font-size: 12px; }
                    .footer-signatures { display: flex; justify-content: space-between; margin-top: 40px; }
                    .sign-box { border-top: 1px solid #334155; width: 220px; text-align: center; padding-top: 6px; font-size: 12px; }
                    @media print {
                        body { padding: 0; }
                        button { display: none !important; }
                    }
                </style>
            </head>
            <body>
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px;">
                    <div>
                        <h1>📋 Karta Zapotrzebowania & Lista Wydań Surowców (FIFO)</h1>
                        <p style="margin: 0; color: #64748b; font-size: 13px;">Raport Produkcyjny &bull; Magazyn Surowców</p>
                    </div>
                    <button onclick="window.print()" style="padding: 10px 18px; font-size: 14px; font-weight: bold; background: #2563eb; color: #fff; border: none; border-radius: 6px; cursor: pointer;">🖨️ DRUKUJ</button>
                </div>

                <div class="meta-box">
                    <strong>Wielkość zlecenia:</strong> ${tons} ton &nbsp;|&nbsp; 
                    <strong>Data kalkulacji:</strong> ${nowStr} &nbsp;|&nbsp;
                    <strong>Przeszukane strefy:</strong> Regały (R*), MP01, BF_MP01
                </div>

                <h3 style="margin: 0 0 8px 0; font-size: 15px;">1. Zestawienie zapotrzebowania i stanów</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Surowiec</th>
                            <th style="text-align: right;">Potrzebne</th>
                            <th style="text-align: right;">Dostępne aktywne</th>
                            <th style="text-align: right;">Zablokowane</th>
                            <th style="text-align: right;">Bilans / Do zamówienia</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${itemsSummaryRows}
                    </tbody>
                </table>

                <h3 style="margin: 0 0 8px 0; font-size: 15px;">2. Wykaz palet do wydania według kolejki FIFO</h3>
                <table>
                    <thead>
                        <tr>
                            <th style="text-align: center;">Kolejka FIFO</th>
                            <th>Surowiec</th>
                            <th style="text-align: center;">Lokalizacja</th>
                            <th>Nr Palety / SSCC</th>
                            <th>Partia</th>
                            <th style="text-align: right;">Ilość (kg)</th>
                            <th style="text-align: center;">Status</th>
                            <th style="text-align: center;">Podpis wydania</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${fifoPalletsRows || '<tr><td colspan="8" style="padding: 10px; text-align: center; border: 1px solid #cbd5e1;">Brak fizycznych palet na stanie w przeszukanych strefach.</td></tr>'}
                    </tbody>
                </table>

                <div class="footer-signatures">
                    <div class="sign-box">Data i podpis operatora</div>
                    <div class="sign-box">Data i podpis magazyniera</div>
                </div>

                <script>
                    window.onload = function() {
                        setTimeout(function() { window.print(); }, 300);
                    };
                </script>
            </body>
            </html>
        `;

        printWindow.document.open();
        printWindow.document.write(docHtml);
        printWindow.document.close();
    }

    function submitOrder() {
        if (!_lastCalculationData || !_lastCalculationData.results || _lastCalculationData.results.length === 0) {
            alert('Najpierw wykonaj kalkulację zapotrzebowania.');
            return;
        }
        startPickingFromResults();
    }

    function startPickingFromResults() {
        if (!_lastCalculationData || !_lastCalculationData.results) {
            alert('Brak danych kalkulacji do utworzenia dyspozycji kompletacji.');
            return;
        }

        const btn = document.querySelector('#calc-order-action-container button');
        let originalText = '';
        if (btn) {
            originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span class="material-icons" style="font-size: 18px; animation: spin 1s linear infinite;">sync</span> Tworzenie dyspozycji...';
        }

        const payload = {
            items: _lastCalculationData.results,
            order_tons: _lastCalculationData.order_tons
        };

        fetch(START_PICKING_API, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.data && data.data.order_ref) {
                if (typeof showToast === 'function') {
                    showToast('✅ ' + (data.message || 'Dyspozycja kompletacji utworzona!'), 'success');
                }
                closeModal();
                window.dispatchEvent(new CustomEvent('ordersChanged', { detail: data.data }));
                if (typeof window.refreshSidebarBadges === 'function') {
                    window.refreshSidebarBadges();
                }
                if (typeof PickingViewModule !== 'undefined' && PickingViewModule.openPickingModal) {
                    PickingViewModule.openPickingModal(data.data.order_ref);
                } else {
                    alert('✅ Dyspozycja utworzona: ' + data.data.order_ref + '\nOtwórz moduł kompletacji, aby kontynuować.');
                }
            } else {
                var errorMsg = data.message || 'Nieznany błąd podczas tworzenia dyspozycji.';
                if (typeof showToast === 'function') {
                    showToast('❌ ' + errorMsg, 'error');
                } else {
                    alert('❌ ' + errorMsg);
                }
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                }
            }
        })
        .catch(function(err) {
            console.error('Błąd start-picking:', err);
            if (typeof showToast === 'function') {
                showToast('❌ Błąd połączenia z serwerem.', 'error');
            } else {
                alert('❌ Błąd połączenia z serwerem.');
            }
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        });
    }

    return {
        init: init,
        openModal: openModal,
        closeModal: closeModal,
        addRow: addRow,
        checkStock: checkStock,
        submitOrder: submitOrder,
        startPickingFromResults: startPickingFromResults,
        printFifoList: printFifoList
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    ZasypCalculatorModule.init();
});

// Globalne funkcje
window.openZasypCalculatorModal = ZasypCalculatorModule.openModal;
window.closeZasypCalculatorModal = ZasypCalculatorModule.closeModal;
window.addCalculatorRow = ZasypCalculatorModule.addRow;
window.checkStockAndCalculate = ZasypCalculatorModule.checkStock;
window.submitCalculatorOrder = ZasypCalculatorModule.submitOrder;
window.printZasypFifoList = ZasypCalculatorModule.printFifoList;

window.addEventListener('click', function(event) {
    const modal = document.getElementById('zasyp-calculator-modal');
    if (event.target === modal) {
        window.closeZasypCalculatorModal();
    }
});
