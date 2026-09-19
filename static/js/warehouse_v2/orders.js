/**
 * Moduł listy zamówień z magazynu.
 */
const OrdersModule = (function () {
    'use strict';

    const API_BASE = '/warehouse-v2/api/orders';
    const REFRESH_INTERVAL_MS = 3000;

    let _refreshTimer = null;

    function init() {
        _loadOrders();
        _startAutoRefresh();

        window.addEventListener('focus', _loadOrders);
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'visible') _loadOrders();
        });
        window.addEventListener('ordersChanged', _loadOrders);
    }

    function _loadOrders() {
        fetch(API_BASE)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) return;
                _renderOrders(data.orders);
            })
            .catch(function (err) {
                console.error('Błąd ładowania zamówień:', err);
            });
    }

    function _renderOrders(orders) {
        var tbody = document.getElementById('ordersTbody');
        var table = document.getElementById('ordersTable');
        var empty = document.getElementById('ordersEmpty');
        var badge = document.getElementById('ordersCount');

        if (!tbody || !table || !empty || !badge) return;

        badge.textContent = orders.length;

        var noweCount = orders.filter(function(o) { return o.status === 'NOWE'; }).length;
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
            var isNowe = o.status === 'NOWE';
            var komentarz = o.komentarz ? '<div style="margin-top:8px; font-size:12px; color:#64748b;"><strong>Komentarz:</strong> ' + _escapeHtml(o.komentarz) + '</div>' : '';

            var itemsHtml = '';
            if (Array.isArray(o.items) && o.items.length > 0) {
                itemsHtml = '<ul style="margin:0; padding-left:16px; list-style-type:disc;">';
                o.items.forEach(function(it) {
                    itemsHtml += '<li><strong>' + _escapeHtml(it.surowiec_nazwa) + '</strong> — ' + _formatKg(it.ilosc_kg) + ' kg</li>';
                });
                itemsHtml += '</ul>';
            } else {
                itemsHtml = '<span style="color:#94a3b8;">Brak pozycji</span>';
            }

            var statusHtml = isNowe
                ? '<span class="order-status-badge nowe">NOWE</span>'
                : '<span class="order-status-badge zamkniete">ZAMKNIĘTE</span>';

            var actionHtml = '<div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">';
            if (isNowe) {
                actionHtml += '<button class="order-confirm-btn" onclick="OrdersModule.confirmOrder(' + o.id + ', this)">' +
                    '<span class="material-icons" style="font-size:16px;">check</span> Potwierdź' +
                '</button>';
            } else {
                actionHtml += '<span style="color:#94a3b8; font-size:12px;">' +
                    _escapeHtml(o.magazynier_login || '') +
                    '<br>' + _formatDate(o.confirmed_at) +
                '</span>';
            }

            if (window.CAN_DELETE_ORDERS) {
                actionHtml += '<button class="order-delete-btn" onclick="OrdersModule.deleteOrder(' + o.id + ', this)" title="Trwale usuń zamówienie">' +
                    '<span class="material-icons" style="font-size:15px;">delete</span>' +
                '</button>';
            }
            actionHtml += '</div>';

            return '<tr>' +
                '<td data-label="ID"><strong>#' + o.id + '</strong></td>' +
                '<td data-label="Zamówione surowce">' + itemsHtml + komentarz + '</td>' +
                '<td data-label="Operator">' + _escapeHtml(o.operator_login) + '</td>' +
                '<td data-label="Data">' + _formatDate(o.created_at) + '</td>' +
                '<td data-label="Status">' + statusHtml + '</td>' +
                '<td data-label="Akcja">' + actionHtml + '</td>' +
            '</tr>';
        }).join('');
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
        confirmOrder: confirmOrder,
        deleteOrder: deleteOrder,
        loadOrders: _loadOrders
    };
})();
