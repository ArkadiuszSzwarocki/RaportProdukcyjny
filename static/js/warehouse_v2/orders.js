// cspell:words pozostale
/**
 * Moduł listy zamówień z magazynu.
 */
const OrdersModule = (function () {
    'use strict';

    const API_BASE = '/warehouse-v2/api/orders';
    const REFRESH_INTERVAL_MS = 3000;

    let _refreshTimer = null;
    let _orders = [];
    let _change = null;
    let _changeBusy = false;
    let _materialsReady = false;

    function init() {
        const form = document.getElementById('orderChangeForm');
        if (form) {
            form.addEventListener('submit', _submitChange);
            document.getElementById('orderChangeMode').addEventListener('change', _changeMode);
            document.getElementById('orderChangeClose').addEventListener('click', function () {
                if (!_changeBusy) document.getElementById('orderChangeDialog').close();
            });
            document.getElementById('orderChangeDialog').addEventListener('cancel', function (event) {
                if (_changeBusy) event.preventDefault();
            });
        }
        _loadOrders();
        _startAutoRefresh();

        window.addEventListener('focus', _loadOrders);
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'visible') _loadOrders();
        });
        window.addEventListener('ordersChanged', _loadOrders);
    }

    function _loadOrders() {
        const dialog = document.getElementById('orderChangeDialog');
        if (dialog && dialog.open) return Promise.resolve();
        return fetch(API_BASE)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) return;
                _orders = data.orders;
                _renderOrders(_orders);
            })
            .catch(function (err) {
                console.error('Błąd ładowania zamówień:', err);
            });
    }

    function _renderOrders(orders) {
        orders = orders.flatMap(function (order) {
            return (order.items || []).map(function (item, index) {
                return Object.assign({}, order, {items: [item], position: index + 1, itemIndex: item.item_index == null ? index : item.item_index,
                    status: item.realizacja_status || order.status});
            });
        });
        var tbody = document.getElementById('ordersTbody');
        var table = document.getElementById('ordersTable');
        var empty = document.getElementById('ordersEmpty');
        var badge = document.getElementById('ordersCount');

        if (!tbody || !table || !empty || !badge) return;

        badge.textContent = orders.length;

        var noweCount = orders.filter(function(o) { return ['NOWE', 'CZESCIOWE'].includes(o.status); }).length;
        var sidebarBadge = document.getElementById('sidebarOrdersBadge');
        if (sidebarBadge) {
            sidebarBadge.textContent = noweCount;
            if (noweCount > 0) {
                sidebarBadge.style.display = 'inline-flex';
            } else {
                sidebarBadge.style.display = 'none';
            }
        }

        if (orders.length === 0) {
            table.style.display = 'none';
            empty.style.display = 'block';
            return;
        }

        table.style.display = 'table';
        empty.style.display = 'none';

        tbody.innerHTML = orders.map(function (o) {
            var isNowe = ['NOWE', 'CZESCIOWE'].includes(o.status);
            var item = o.items[0];
            var cancelled = item.cancellation;
            var replaces = item.replaces;
            var komentarz = o.komentarz ? '<div style="margin-top:8px; font-size:12px; color:#64748b;"><strong>Komentarz:</strong> ' + _escapeHtml(o.komentarz) + '</div>' : '';

            var itemsHtml = '';
            var displayedItems = Array.isArray(o.items) ? o.items.filter(function(it) {
                if (!it) return false;
                if (it.brakujace_kg !== undefined && it.brakujace_kg !== null) {
                    return parseFloat(it.brakujace_kg) > 0;
                }
                return (parseFloat(it.ilosc_kg) || 0) > 0;
            }) : [];

            if (displayedItems.length > 0) {
                itemsHtml = '<ul style="margin:0; padding-left:16px; list-style-type:disc;">';
                displayedItems.forEach(function(it) {
                    var displayQty = (it.brakujace_kg !== undefined && it.brakujace_kg !== null) ? it.brakujace_kg : it.ilosc_kg;
                    itemsHtml += '<li><strong>' + _escapeHtml(it.surowiec_nazwa) + '</strong> — ' + _formatKg(displayQty) + ' kg</li>';
                    if (isNowe || cancelled) {
                        itemsHtml += '<li>W transferze: ' + _formatKg(it.przypisane_kg || 0) +
                            ' kg · ' + (cancelled ? 'Anulowano: ' : 'Pozostało: ') + _formatKg(cancelled ? cancelled.cancelled_kg : (it.pozostale_kg == null ? displayQty : it.pozostale_kg)) + ' kg</li>';
                    }
                });
                itemsHtml += '</ul>';
            } else {
                itemsHtml = '<span style="color:#94a3b8;">Brak pozycji (100% na stanie)</span>';
            }

            if (cancelled) {
                itemsHtml += '<div class="order-change-note"><strong>Powód:</strong> ' + _escapeHtml(cancelled.reason) +
                    '<br>Zatwierdził: ' + _escapeHtml(cancelled.login) + ' · ' + _escapeHtml(cancelled.at) +
                    (cancelled.replacement_order_id ? '<br>Nowe zamówienie: <a href="#order-' + Number(cancelled.replacement_order_id) + '-0">#' + Number(cancelled.replacement_order_id) + '</a>' : '') + '</div>';
            }
            if (replaces) {
                itemsHtml += '<div class="order-change-note">Zamiast: ' + _escapeHtml(replaces.material) +
                    ' · <a href="#order-' + Number(replaces.order_id) + '-' + Number(replaces.item_index) + '">zamówienie #' + Number(replaces.order_id) + '</a>' +
                    '<br>Powód: ' + _escapeHtml(replaces.reason) + '<br>Zatwierdził: ' + _escapeHtml(replaces.login) + '</div>';
            }
            var statusHtml = isNowe
                ? '<span class="order-status-badge nowe">' + (o.status === 'CZESCIOWE' ? 'CZĘŚCIOWO' : 'NOWE') + '</span>'
                : '<span class="order-status-badge zamkniete">ZAMKNIĘTE</span>';

            if (cancelled) statusHtml = '<span class="order-status-badge cancelled">' + (cancelled.replacement_order_id ? 'ZAMIENIONE' : 'ANULOWANE') + '</span>';

            var actionHtml = '<div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">';
            if (isNowe) {
                actionHtml += '<span style="font-size:12px">Rozliczenie po skanie do transferu</span>';
                if (window.CAN_DELETE_ORDERS) actionHtml += '<button type="button" class="btn btn-outline" onclick="OrdersModule.openChange(' + Number(o.id) + ',' + Number(o.itemIndex) + ')">Anuluj / zamień</button>';
            } else {
                actionHtml += '<span style="color:#94a3b8; font-size:12px;">' +
                    _escapeHtml(o.magazynier_login || '') +
                    '<br>' + _formatDate(o.confirmed_at) +
                '</span>';
            }

            if (window.CAN_DELETE_ORDERS && !cancelled && !replaces) {
                actionHtml += '<button class="order-delete-btn" onclick="OrdersModule.deleteOrder(' + o.id + ', this)" title="Trwale usuń całe zamówienie (wszystkie pozycje)">' +
                    '<span class="material-icons" style="font-size:15px;">delete</span>' +
                '</button>';
            }
            actionHtml += '</div>';

            return '<tr id="order-' + Number(o.id) + '-' + Number(o.itemIndex) + '">' +
                '<td data-label="ID"><strong>#' + o.id + ' / ' + o.position + '</strong></td>' +
                '<td data-label="Zamówione surowce">' + itemsHtml + komentarz + '</td>' +
                '<td data-label="Operator">' + _escapeHtml(o.operator_login) + '</td>' +
                '<td data-label="Data">' + _formatDate(o.created_at) + '</td>' +
                '<td data-label="Status">' + statusHtml + '</td>' +
                '<td data-label="Akcja">' + actionHtml + '</td>' +
            '</tr>';
        }).join('');
    }

    function _changeMode() {
        const replace = document.getElementById('orderChangeMode').value === 'replace';
        document.getElementById('orderReplacementFields').hidden = !replace;
        document.getElementById('orderReplacementName').required = replace;
        document.getElementById('orderReplacementKg').required = replace;
        document.getElementById('orderChangeSubmit').disabled = _changeBusy || (replace && !_materialsReady);
    }

    async function openChange(orderId, index) {
        const order = _orders.find(order => Number(order.id) === orderId);
        const item = order && order.items.find((item, offset) => Number(item.item_index == null ? offset : item.item_index) === index);
        if (!item || item.cancellation) return;
        const dialog = document.getElementById('orderChangeDialog');
        if (!dialog || dialog.open) return;
        _change = {orderId, index};
        const change = _change;
        _materialsReady = false;
        document.getElementById('orderChangeForm').reset();
        document.getElementById('orderChangeSummary').textContent = '#' + orderId + ' — ' + item.surowiec_nazwa + ' · pozostało ' + _formatKg(item.pozostale_kg) + ' kg';
        document.getElementById('orderReplacementKg').value = item.pozostale_kg;
        document.getElementById('orderChangeError').textContent = '';
        _changeMode();
        dialog.showModal();
        try {
            const response = await fetch(API_BASE + '/surowce');
            const data = await response.json();
            if (_change !== change || !dialog.open) return;
            if (!response.ok || !data.success) throw new Error('Nie udało się pobrać słownika surowców. Otwórz okno ponownie.');
            const select = document.getElementById('orderReplacementName');
            select.replaceChildren(new Option('Wybierz surowiec', ''));
            data.surowce.filter(material => material.nazwa.trim().toLowerCase() !== item.surowiec_nazwa.trim().toLowerCase())
                .forEach(material => select.add(new Option(material.nazwa, material.nazwa)));
            _materialsReady = true;
        } catch (error) {
            if (_change !== change || !dialog.open) return;
            document.getElementById('orderChangeError').textContent = error.message;
        }
        _changeMode();
    }

    async function _submitChange(event) {
        event.preventDefault();
        if (_changeBusy || !_change || !document.getElementById('orderChangeForm').reportValidity()) return;
        const mode = document.getElementById('orderChangeMode').value;
        if (mode === 'replace' && !_materialsReady) return;
        _changeBusy = true;
        _changeMode();
        document.getElementById('orderChangeClose').disabled = true;
        document.getElementById('orderChangeError').textContent = '';
        try {
            const response = await fetch(API_BASE + '/' + _change.orderId + '/items/' + _change.index + '/resolve', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode, reason: document.getElementById('orderChangeReason').value,
                    replacement_name: document.getElementById('orderReplacementName').value,
                    replacement_kg: document.getElementById('orderReplacementKg').value})
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || 'Nie udało się zapisać decyzji.');
            document.getElementById('orderChangeDialog').close();
            _showToast(data.message, 'success');
            _change = null;
            await _loadOrders();
            if (typeof window.refreshSidebarBadges === 'function') window.refreshSidebarBadges();
        } catch (error) {
            document.getElementById('orderChangeError').textContent = error.message;
        } finally {
            _changeBusy = false;
            document.getElementById('orderChangeClose').disabled = false;
            _changeMode();
        }
    }

    function deleteOrder(orderId, btnElement) {
        if (!confirm('Czy na pewno chcesz TRWALE USUNĄĆ zamówienie #' + orderId + '?\nOperacji nie można cofnąć.')) return;

        if (btnElement) btnElement.disabled = true;

        fetch(API_BASE + '/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order_id: orderId })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                _showToast(data.message || 'Zamówienie usunięte.', 'success');
                _loadOrders();
                window.dispatchEvent(new CustomEvent('ordersChanged'));
                if (typeof window.refreshSidebarBadges === 'function') {
                    window.refreshSidebarBadges();
                }
            } else {
                _showToast(data.message || 'Błąd usuwania zamówienia.', 'error');
                if (btnElement) btnElement.disabled = false;
            }
        })
        .catch(function (err) {
            console.error('Błąd usuwania zamówienia:', err);
            _showToast('Błąd połączenia z serwerem.', 'error');
            if (btnElement) btnElement.disabled = false;
        });
    }

    function confirmOrder(orderId, btnElement) {
        if (!confirm('Potwierdzasz odczytanie zamówienia #' + orderId + '?')) return;

        if (btnElement) btnElement.disabled = true;

        fetch(API_BASE + '/' + orderId + '/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                _showToast(data.message, 'success');
                _loadOrders();
                window.dispatchEvent(new CustomEvent('ordersChanged'));
                if (typeof window.refreshSidebarBadges === 'function') {
                    window.refreshSidebarBadges();
                }
            } else {
                _showToast(data.message || 'Wystąpił błąd.', 'error');
                if (btnElement) btnElement.disabled = false;
            }
        })
        .catch(function (err) {
            console.error('Błąd potwierdzania zamówienia:', err);
            _showToast('Błąd połączenia z serwerem.', 'error');
            if (btnElement) btnElement.disabled = false;
        });
    }

    function _startAutoRefresh() {
        if (_refreshTimer) clearInterval(_refreshTimer);
        _refreshTimer = setInterval(function () {
            _loadOrders();
        }, REFRESH_INTERVAL_MS);
    }

    function _escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function _formatKg(value) {
        var num = parseFloat(value);
        if (isNaN(num)) return '0';
        return num % 1 === 0 ? num.toString() : num.toFixed(2);
    }

    function _formatDate(dateStr) {
        if (!dateStr) return '—';
        var parts = dateStr.split(' ');
        if (parts.length < 2) return dateStr;
        var dateParts = parts[0].split('-');
        var timeParts = parts[1].split(':');
        if (dateParts.length < 3 || timeParts.length < 2) return dateStr;
        return dateParts[2] + '.' + dateParts[1] + ' ' + timeParts[0] + ':' + timeParts[1];
    }

    function _showToast(message, type) {
        var toast = document.getElementById('orderToast');
        if (!toast) return;

        toast.textContent = message;
        toast.className = 'order-toast ' + (type || 'success');

        void toast.offsetWidth;
        toast.classList.add('show');

        setTimeout(function () {
            toast.classList.remove('show');
        }, 3500);
    }

    document.addEventListener('DOMContentLoaded', init);

    return {
        openChange: openChange,
        confirmOrder: confirmOrder,
        deleteOrder: deleteOrder,
        loadOrders: _loadOrders
    };
})();
