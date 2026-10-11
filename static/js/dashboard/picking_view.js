/**
 * Picking View Module — Warehouse completion/picking order UI.
 *
 * Opens a dedicated modal for warehouse workers to scan pallets
 * from a FIFO-ordered picking list and confirm moves to MP01.
 */
const PickingViewModule = (function () {
    'use strict';

    const PICKING_DETAILS_API = '/warehouse-v2/api/orders/picking/';
    const PICKING_CONFIRM_API_SUFFIX = '/confirm';
    const PICKING_CANCEL_API_SUFFIX = '/cancel';
    const PICKING_ACTIVE_API = '/warehouse-v2/api/orders/picking/active';

    let _currentOrderRef = null;
    let _orderData = null;
    let _allItemsMap = {};

    function parseLocationString(locStr) {
        if (!locStr) return { rackId: '—', col: '—', lvl: '—' };
        const clean = String(locStr).trim().toUpperCase();
        const m = clean.match(/^([A-Z0-9]+?)[-_]?(\d{1,2})[-_]?(\d{1,2})$/i);
        if (m) {
            return {
                rackId: m[1],
                lvl: parseInt(m[2], 10),
                col: parseInt(m[3], 10)
            };
        }
        return { rackId: clean, col: '—', lvl: '—' };
    }

    function openPickingModal(orderRef) {
        _currentOrderRef = orderRef;
        const modal = document.getElementById('picking-order-modal');
        if (!modal) {
            console.error('Picking modal element not found');
            return;
        }
        modal.style.display = 'flex';

        loadOrderDetails(orderRef);

        setTimeout(function () {
            const scanInput = document.getElementById('picking-sscc-input');
            if (scanInput) scanInput.focus();
        }, 150);
    }

    function closePickingModal() {
        const modal = document.getElementById('picking-order-modal');
        if (modal) modal.style.display = 'none';
        _currentOrderRef = null;
        _orderData = null;
        _allItemsMap = {};
    }

    function selectItemFor3dView(pallet) {
        if (!pallet) return;
        const loc = pallet.lokalizacja_zrodlowa || '';
        const parsed = parseLocationString(loc);

        const rackLabel = document.getElementById('picking-active-rack-label');
        if (rackLabel) rackLabel.textContent = 'Regał: ' + parsed.rackId;

        const slotLabel = document.getElementById('picking-active-slot-label');
        if (slotLabel) {
            slotLabel.innerHTML = 'P: <span>' + parsed.lvl + '</span> &bull; G: <span>' + parsed.col + '</span>';
        }

        const titleEl = document.getElementById('picking-active-item-title');
        if (titleEl) {
            titleEl.textContent = (pallet.nazwa_surowca || 'Paleta') + ' (' + parseFloat(pallet.ilosc_kg || 0).toFixed(1) + ' kg)';
        }

        const subEl = document.getElementById('picking-active-item-sub');
        if (subEl) {
            subEl.textContent = 'SSCC: ' + (pallet.nr_palety || '—') + ' • Partia: ' + (pallet.nr_partii || '—');
        }

        // Highlight active row in table
        document.querySelectorAll('.picking-table-row').forEach(function (r) {
            r.classList.remove('picking-row-active');
        });
        const activeRow = document.getElementById('picking-row-' + pallet.id);
        if (activeRow) activeRow.classList.add('picking-row-active');
    }

    function selectItemById(itemId) {
        const item = _allItemsMap[itemId];
        if (item) {
            selectItemFor3dView(item);
        }
    }

    function loadOrderDetails(orderRef) {
        const tbody = document.getElementById('picking-items-tbody');
        const progressBar = document.getElementById('picking-progress-bar');
        const progressText = document.getElementById('picking-progress-text');
        const headerRef = document.getElementById('picking-order-ref');

        if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="padding: 20px; text-align: center; color: #64748b;">Ładowanie danych kompletacji...</td></tr>';
        if (headerRef) headerRef.textContent = orderRef;

        fetch(PICKING_DETAILS_API + encodeURIComponent(orderRef))
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data.success) {
                    if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="padding: 20px; text-align: center; color: #ef4444;">' + (data.message || 'Błąd ładowania') + '</td></tr>';
                    return;
                }

                _orderData = data.data;
                try {
                    renderPickingItems(_orderData);
                    updateProgress(_orderData.progress);
                } catch (renderErr) {
                    console.error('Error rendering picking items:', renderErr);
                }
            })
            .catch(function (err) {
                console.error('Picking load network error:', err);
                if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="padding: 20px; text-align: center; color: #ef4444;">Błąd połączenia z serwerem.</td></tr>';
            });
    }

    function renderPickingItems(orderData) {
        const tbody = document.getElementById('picking-items-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        _allItemsMap = {};

        const grouped = orderData.items_grouped || {};
        const surowceNames = Object.keys(grouped);

        if (surowceNames.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="padding: 20px; text-align: center; color: #94a3b8;">Brak pozycji w dyspozycji kompletacji.</td></tr>';
            return;
        }

        let firstPendingItem = null;

        surowceNames.forEach(function (nazwa) {
            var headerTr = document.createElement('tr');
            headerTr.style.cssText = 'background: linear-gradient(135deg, #1e293b, #334155); border: none;';
            headerTr.innerHTML = '<td colspan="7" style="padding: 10px 14px; font-weight: 700; font-size: 13px; color: #ffffff; letter-spacing: 0.3px;">' +
                '<span class="material-icons" style="font-size: 16px; vertical-align: middle; margin-right: 6px; color: #60a5fa;">inventory_2</span>' +
                nazwa + '</td>';
            tbody.appendChild(headerTr);

            var pallets = grouped[nazwa] || [];
            pallets.forEach(function (p) {
                p.nazwa_surowca = nazwa;
                _allItemsMap[p.id] = p;

                if (!firstPendingItem && p.status === 'OCZEKUJE' && !p.is_blocked) {
                    firstPendingItem = p;
                }

                var tr = document.createElement('tr');
                tr.id = 'picking-row-' + p.id;
                tr.className = 'picking-table-row';
                tr.dataset.sscc = (p.nr_palety || '').trim();
                tr.dataset.status = p.status;
                tr.onclick = function (e) {
                    if (e.target.closest('button')) return;
                    selectItemFor3dView(p);
                };

                var rowBg = '';
                var statusBadge = '';
                var actionHtml = '';

                if (p.status === 'SKOMPLETOWANA') {
                    rowBg = 'background: #f0fdf4;';
                    statusBadge = '<span style="background: #dcfce7; color: #166534; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; border: 1px solid #bbf7d0;">✅ GOTOWA</span>';
                    actionHtml = '<span style="color: #94a3b8; font-size: 12px;">—</span>';
                } else if (p.status === 'POMINIETA' || p.is_blocked) {
                    rowBg = 'background: #fef2f2;';
                    var reason = p.powod_blokady ? ' (' + p.powod_blokady + ')' : '';
                    statusBadge = '<span style="background: #fee2e2; color: #991b1b; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; border: 1px solid #fecaca;">⛔ BLOKADA' + reason + '</span>';
                    actionHtml = '<span style="color: #94a3b8; font-size: 12px;">pomiń</span>';
                } else if (p.status === 'ANULOWANA') {
                    rowBg = 'background: #f8fafc;';
                    statusBadge = '<span style="background: #f1f5f9; color: #64748b; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; border: 1px solid #e2e8f0;">❌ ANULOWANA</span>';
                    actionHtml = '<span style="color: #94a3b8; font-size: 12px;">—</span>';
                } else {
                    rowBg = '';
                    statusBadge = '<span style="background: #eff6ff; color: #1d4ed8; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; border: 1px solid #bfdbfe;">⏳ CZEKA</span>';
                    actionHtml = '<button type="button" onclick="PickingViewModule.confirmItemManual(' + p.id + ')" ' +
                        'style="background: #2563eb; color: #fff; border: none; padding: 5px 12px; border-radius: 6px; font-size: 11px; font-weight: 700; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;">' +
                        '<span class="material-icons" style="font-size: 15px;">check_circle</span>Pobrano</button>';
                }

                var fifoBadge = '';
                if (p.fifo_rank && !p.is_blocked && p.status === 'OCZEKUJE') {
                    if (p.fifo_rank === 1) {
                        fifoBadge = '<span style="background: #2563eb; color: #fff; padding: 2px 7px; border-radius: 4px; font-weight: 800; font-size: 11px;">#1 WYDAJ</span>';
                    } else {
                        fifoBadge = '<span style="background: #e0e7ff; color: #3730a3; padding: 2px 7px; border-radius: 4px; font-weight: 700; font-size: 11px;">#' + p.fifo_rank + '</span>';
                    }
                } else if (p.status === 'SKOMPLETOWANA') {
                    fifoBadge = '<span style="color: #16a34a; font-weight: bold;">✓</span>';
                } else {
                    fifoBadge = '<span style="color: #cbd5e1;">—</span>';
                }

                const parsed = parseLocationString(p.lokalizacja_zrodlowa);
                const locCell = '<div class="loc-rack-tag">' +
                    '<span class="loc-rack-num">' + (parsed.rackId || 'Regał —') + '</span>' +
                    '<span class="loc-slot-detail">Poziom ' + parsed.lvl + ' &bull; Kolumna ' + parsed.col + '</span>' +
                    '<span style="font-size: 10px; color: #94a3b8;">' + (p.lokalizacja_zrodlowa || '—') + '</span>' +
                    '</div>';

                tr.style.cssText = 'border-bottom: 1px solid #e2e8f0; ' + rowBg;
                tr.innerHTML =
                    '<td style="padding: 8px 10px; text-align: center;">' + fifoBadge + '</td>' +
                    '<td style="padding: 8px 10px;">' + locCell + '</td>' +
                    '<td style="padding: 8px 10px; font-family: monospace; font-weight: 600; font-size: 12px; color: #334155;">' + (p.nr_palety || '—') + '</td>' +
                    '<td style="padding: 8px 10px; color: #475569; font-size: 12px;">' + (p.nr_partii || '—') + '</td>' +
                    '<td style="padding: 8px 10px; text-align: right; font-weight: 700; font-size: 12px; color: ' + (p.is_blocked ? '#94a3b8' : '#0f172a') + ';">' + parseFloat(p.ilosc_kg || 0).toFixed(1) + ' kg</td>' +
                    '<td style="padding: 8px 10px; text-align: center;">' + statusBadge + '</td>' +
                    '<td style="padding: 8px 10px; text-align: center;">' + actionHtml + '</td>';

                tbody.appendChild(tr);
            });
        });

        if (firstPendingItem) {
            selectItemFor3dView(firstPendingItem);
        }
    }

    function updateProgress(progress) {
        var bar = document.getElementById('picking-progress-fill');
        var text = document.getElementById('picking-progress-text');
        if (!progress) return;

        var pct = progress.percent || 0;
        if (bar) {
            bar.style.width = pct + '%';
            if (pct >= 100) {
                bar.style.background = 'linear-gradient(135deg, #10b981, #059669)';
            } else if (pct > 50) {
                bar.style.background = 'linear-gradient(135deg, #3b82f6, #2563eb)';
            } else {
                bar.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
            }
        }
        if (text) {
            text.textContent = progress.completed + ' / ' + progress.total + ' palet skompletowanych (' + pct.toFixed(0) + '%)';
        }

        if (pct >= 100) {
            var scanSection = document.getElementById('picking-scan-section');
            if (scanSection) {
                scanSection.innerHTML = '<div style="text-align: center; padding: 20px; background: #f0fdf4; border-radius: 10px; border: 1.5px solid #bbf7d0;">' +
                    '<span class="material-icons" style="font-size: 48px; color: #16a34a;">task_alt</span>' +
                    '<h3 style="margin: 8px 0 4px 0; color: #166534; font-size: 18px;">Kompletacja zakończona!</h3>' +
                    '<p style="margin: 0; color: #15803d; font-size: 14px;">Wszystkie palety zostały skompletowane i przeniesione na MP01.</p>' +
                    '</div>';
            }
        }
    }

    function handleSsccScan() {
        var input = document.getElementById('picking-sscc-input');
        if (!input) return;
        var sscc = input.value.trim();
        if (!sscc || !_currentOrderRef) return;

        input.disabled = true;
        var statusEl = document.getElementById('picking-scan-status');
        if (statusEl) {
            statusEl.innerHTML = '<span style="color: #3b82f6;">⏳ Weryfikacja kodu...</span>';
        }

        fetch(PICKING_DETAILS_API + encodeURIComponent(_currentOrderRef) + PICKING_CONFIRM_API_SUFFIX, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sscc_code: sscc })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                input.value = '';
                input.disabled = false;
                input.focus();

                if (data.success) {
                    if (statusEl) {
                        statusEl.innerHTML = '<span style="color: #16a34a; font-weight: 700;">✅ ' + (data.message || 'Paleta potwierdzona!') + '</span>';
                    }
                    highlightCompletedRow(data.data);
                    loadOrderDetails(_currentOrderRef);
                    window.dispatchEvent(new CustomEvent('ordersChanged'));
                    if (typeof window.refreshSidebarBadges === 'function') {
                        window.refreshSidebarBadges();
                    }
                } else {
                    if (statusEl) {
                        statusEl.innerHTML = '<span style="color: #ef4444; font-weight: 700;">❌ ' + (data.message || 'Nie znaleziono palety.') + '</span>';
                    }
                    if (typeof showToast === 'function') {
                        showToast('❌ ' + (data.message || 'Błąd skanowania'), 'error');
                    }
                }
            })
            .catch(function (err) {
                console.error('Scan confirm error:', err);
                input.value = '';
                input.disabled = false;
                input.focus();
                if (statusEl) {
                    statusEl.innerHTML = '<span style="color: #ef4444;">❌ Błąd połączenia z serwerem.</span>';
                }
            });
    }

    function highlightCompletedRow(itemData) {
        if (!itemData || !itemData.item_id) return;
        var row = document.getElementById('picking-row-' + itemData.item_id);
        if (row) {
            row.style.background = '#dcfce7';
            row.style.transition = 'background 0.6s ease';
            setTimeout(function () {
                row.style.background = '#f0fdf4';
            }, 1500);
        }
    }

    function confirmItemManual(itemId) {
        if (!_currentOrderRef) return;

        fetch(PICKING_DETAILS_API + encodeURIComponent(_currentOrderRef) + PICKING_CONFIRM_API_SUFFIX, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_id: itemId })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    if (typeof showToast === 'function') {
                        showToast(data.message || '✅ Paleta potwierdzona!', 'success');
                    }
                    loadOrderDetails(_currentOrderRef);
                    window.dispatchEvent(new CustomEvent('ordersChanged'));
                    if (typeof window.refreshSidebarBadges === 'function') {
                        window.refreshSidebarBadges();
                    }
                } else {
                    if (typeof showToast === 'function') {
                        showToast('❌ ' + (data.message || 'Błąd potwierdzenia'), 'error');
                    } else {
                        alert(data.message || 'Błąd potwierdzenia');
                    }
                }
            })
            .catch(function (err) {
                console.error('Manual confirm error:', err);
                alert('Błąd połączenia z serwerem.');
            });
    }

    function finishPickingOrder(explicitMode) {
        if (!_currentOrderRef) return;

        var selectedMode = explicitMode;
        if (!selectedMode) {
            var choiceAll = confirm('Zakończenie dyspozycji kompletacji ' + _currentOrderRef + ':\n\n' +
                'Czy WSZYSTKIE surowce z tego zlecenia zostały fizycznie pobrane/zużyte na produkcji?\n\n' +
                '• Kliknij [OK] -> Oznacz WSZYSTKIE pozycje jako SKOMPLETOWANE (100% zrealizowane)\n' +
                '• Kliknij [Anuluj] -> Zakończ zlecenie i ZWOLNIJ niepobrane palety do magazynu');

            if (choiceAll) {
                selectedMode = 'all_completed';
            } else {
                var choiceRelease = confirm('Czy na pewno chcesz zakończyć zlecenie i ZWOLNIĆ niepobrane palety z powrotem do magazynu?\n\n(Pobrane dotąd palety pozostaną zaliczone jako skompletowane).');
                if (choiceRelease) {
                    selectedMode = 'release_unpicked';
                } else {
                    return;
                }
            }
        }

        fetch('/warehouse-v2/api/orders/picking/' + encodeURIComponent(_currentOrderRef) + '/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: selectedMode, operator: 'SYSTEM' })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data && data.success) {
                    if (typeof showToast === 'function') {
                        showToast(data.message || 'Dyspozycja została zakończona.', 'success');
                    } else {
                        alert(data.message || 'Dyspozycja została zakończona.');
                    }
                    closePickingModal();
                    window.dispatchEvent(new CustomEvent('ordersChanged'));
                    if (typeof window.refreshSidebarBadges === 'function') {
                        window.refreshSidebarBadges();
                    }
                    if (typeof loadCurrentPickingTab === 'function') {
                        loadCurrentPickingTab();
                    } else if (typeof loadActivePickingOrders === 'function') {
                        loadActivePickingOrders();
                    }
                } else {
                    alert((data && data.message) ? data.message : 'Błąd podczas kończenia dyspozycji.');
                }
            })
            .catch(function (err) {
                console.error('Finish picking error:', err);
                alert('Błąd połączenia z serwerem.');
            });
    }

    function cancelPickingOrder() {
        if (!_currentOrderRef) return;

        if (!confirm('Czy na pewno chcesz anulować OCZEKUJĄCE pozycje zlecenia ' + _currentOrderRef + '?\n\nZarezerwowane niepobrane palety zostaną natychmiast zwolnione do magazynu.\nPozycje już skompletowane pozostaną nienaruszone.')) {
            return;
        }

        fetch(PICKING_DETAILS_API + encodeURIComponent(_currentOrderRef) + PICKING_CANCEL_API_SUFFIX, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    if (typeof showToast === 'function') {
                        showToast(data.message || 'Oczekujące pozycje anulowane, palety zwolnione.', 'info');
                    } else {
                        alert(data.message || 'Oczekujące pozycje anulowane, palety zwolnione.');
                    }
                    closePickingModal();
                    window.dispatchEvent(new CustomEvent('ordersChanged'));
                    if (typeof window.refreshSidebarBadges === 'function') {
                        window.refreshSidebarBadges();
                    }
                    if (typeof loadCurrentPickingTab === 'function') {
                        loadCurrentPickingTab();
                    } else if (typeof loadActivePickingOrders === 'function') {
                        loadActivePickingOrders();
                    }
                } else {
                    alert(data.message || 'Błąd anulowania.');
                }
            })
            .catch(function (err) {
                console.error('Cancel error:', err);
                alert('Błąd połączenia z serwerem.');
            });
    }

    function printPickingList() {
        if (!_orderData) {
            alert('Najpierw otwórz dyspozycję kompletacji.');
            return;
        }

        var orderRef = _currentOrderRef || '';
        var nowStr = new Date().toLocaleString('pl-PL');
        var grouped = _orderData.items_grouped || {};
        var progress = _orderData.progress || {};

        var rowsHtml = '';
        Object.keys(grouped).forEach(function (nazwa) {
            rowsHtml += '<tr style="background: #f1f5f9;"><td colspan="7" style="padding: 8px; font-weight: bold; font-size: 14px; border: 1px solid #cbd5e1;">' + nazwa + '</td></tr>';
            (grouped[nazwa] || []).forEach(function (p) {
                var statusStr = p.status === 'SKOMPLETOWANA' ? '✅ SKOMPLET.'
                    : (p.is_blocked ? '⛔ ZABLOKOW.' : '⏳ OCZEKUJE');
                var fifoStr = p.fifo_rank ? '#' + p.fifo_rank : '—';
                rowsHtml += '<tr>' +
                    '<td style="padding: 6px 8px; border: 1px solid #cbd5e1; text-align: center; font-weight: bold;">' + fifoStr + '</td>' +
                    '<td style="padding: 6px 8px; border: 1px solid #cbd5e1; font-weight: bold;">' + (p.lokalizacja_zrodlowa || '—') + '</td>' +
                    '<td style="padding: 6px 8px; border: 1px solid #cbd5e1; font-family: monospace;">' + (p.nr_palety || '—') + '</td>' +
                    '<td style="padding: 6px 8px; border: 1px solid #cbd5e1;">' + (p.nr_partii || '—') + '</td>' +
                    '<td style="padding: 6px 8px; border: 1px solid #cbd5e1; text-align: right; font-weight: bold;">' + parseFloat(p.ilosc_kg || 0).toFixed(2) + ' kg</td>' +
                    '<td style="padding: 6px 8px; border: 1px solid #cbd5e1; text-align: center;">' + statusStr + '</td>' +
                    '<td style="padding: 6px 8px; border: 1px solid #cbd5e1; width: 120px;"></td>' +
                    '</tr>';
            });
        });

        var printWindow = window.open('', '_blank', 'width=900,height=700');
        if (!printWindow) {
            alert('Zezwól na wyskakujące okna (pop-up).');
            return;
        }

        var docHtml = '<!DOCTYPE html><html lang="pl"><head><meta charset="UTF-8">' +
            '<title>Dyspozycja Kompletacji ' + orderRef + '</title>' +
            '<style>' +
            'body { font-family: Arial, sans-serif; font-size: 13px; color: #1e293b; padding: 20px; }' +
            'h1 { font-size: 20px; margin: 0 0 6px 0; }' +
            '.meta-box { margin-bottom: 20px; padding: 10px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; }' +
            'table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }' +
            'th { background: #f1f5f9; padding: 8px; border: 1px solid #cbd5e1; text-align: left; font-size: 12px; }' +
            '.footer-signatures { display: flex; justify-content: space-between; margin-top: 40px; }' +
            '.sign-box { border-top: 1px solid #334155; width: 220px; text-align: center; padding-top: 6px; font-size: 12px; }' +
            '@media print { body { padding: 0; } button { display: none !important; } }' +
            '</style></head><body>' +
            '<div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px;">' +
            '<div><h1>📦 Dyspozycja Kompletacji — ' + orderRef + '</h1>' +
            '<p style="margin: 0; color: #64748b;">AgroMES &bull; Magazyn Surowców</p></div>' +
            '<button onclick="window.print()" style="padding: 10px 18px; font-size: 14px; font-weight: bold; background: #2563eb; color: #fff; border: none; border-radius: 6px; cursor: pointer;">🖨️ DRUKUJ</button></div>' +
            '<div class="meta-box"><strong>Operator:</strong> ' + (_orderData.operator_login || '—') +
            ' &nbsp;|&nbsp; <strong>Data:</strong> ' + nowStr +
            ' &nbsp;|&nbsp; <strong>Postęp:</strong> ' + (progress.completed || 0) + '/' + (progress.total || 0) + ' palet' +
            '</div>' +
            '<table><thead><tr>' +
            '<th style="text-align: center; width: 8%;">FIFO</th>' +
            '<th style="width: 14%;">Lokalizacja</th>' +
            '<th style="width: 20%;">Nr Palety / SSCC</th>' +
            '<th style="width: 14%;">Partia</th>' +
            '<th style="text-align: right; width: 14%;">Ilość</th>' +
            '<th style="text-align: center; width: 14%;">Status</th>' +
            '<th style="text-align: center; width: 16%;">Podpis pobrania</th>' +
            '</tr></thead><tbody>' + rowsHtml + '</tbody></table>' +
            '<div class="footer-signatures">' +
            '<div class="sign-box">Data i podpis operatora</div>' +
            '<div class="sign-box">Data i podpis magazyniera</div></div>' +
            '<script>window.onload=function(){setTimeout(function(){window.print();},300);};</script>' +
            '</body></html>';

        printWindow.document.open();
        printWindow.document.write(docHtml);
        printWindow.document.close();
    }

    function deletePickingOrder() {
        if (!_currentOrderRef) return;

        if (!confirm('Czy na pewno chcesz TRWALE USUNĄĆ dyspozycję kompletacji ' + _currentOrderRef + '?\nOperacji nie można cofnąć.')) {
            return;
        }

        fetch('/warehouse-v2/api/orders/picking/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order_ref: _currentOrderRef })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    if (typeof showToast === 'function') {
                        showToast(data.message || 'Dyspozycja usunięta.', 'success');
                    } else {
                        alert(data.message || 'Dyspozycja usunięta.');
                    }
                    closePickingModal();
                    window.dispatchEvent(new CustomEvent('ordersChanged'));
                    if (typeof window.refreshSidebarBadges === 'function') {
                        window.refreshSidebarBadges();
                    }
                    if (typeof loadCurrentPickingTab === 'function') {
                        loadCurrentPickingTab();
                    } else if (typeof loadActivePickingOrders === 'function') {
                        loadActivePickingOrders();
                    }
                } else {
                    alert(data.message || 'Błąd usuwania dyspozycji.');
                }
            })
            .catch(function (err) {
                console.error('Delete error:', err);
                alert('Błąd połączenia z serwerem.');
            });
    }

    function handleScanKeypress(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            handleSsccScan();
        }
    }

    return {
        openPickingModal: openPickingModal,
        closePickingModal: closePickingModal,
        handleSsccScan: handleSsccScan,
        handleScanKeypress: handleScanKeypress,
        confirmItemManual: confirmItemManual,
        finishPickingOrder: finishPickingOrder,
        cancelPickingOrder: cancelPickingOrder,
        deletePickingOrder: deletePickingOrder,
        printPickingList: printPickingList,
        selectItemById: selectItemById,
        selectItemFor3dView: selectItemFor3dView
    };
})();

window.PickingViewModule = PickingViewModule;
window.openPickingModal = PickingViewModule.openPickingModal;
window.closePickingModal = PickingViewModule.closePickingModal;
window.finishPickingOrder = PickingViewModule.finishPickingOrder;

window.addEventListener('click', function (event) {
    var modal = document.getElementById('picking-order-modal');
    if (event.target === modal) {
        PickingViewModule.closePickingModal();
    }
});
