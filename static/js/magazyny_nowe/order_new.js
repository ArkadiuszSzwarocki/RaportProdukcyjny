/**
 * Moduł tworzenia nowego zamówienia (wielopozycyjnego).
 */
const OrderNewModule = (function () {
    'use strict';

    const API_BASE = '/warehouse-v2/api/orders';
    let _availableSurowce = [];
    let _rowCount = 0;

    function init() {
        _loadSurowce().then(() => {
            // Dodaj pierwszy domyślny wiersz
            addRow();
        });
    }

    function _loadSurowce() {
        return fetch(API_BASE + '/surowce')
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    _availableSurowce = data.surowce;
                }
            })
            .catch(err => console.error('Błąd ładowania surowców:', err));
    }

    function addRow() {
        _rowCount++;
        const container = document.getElementById('itemsContainer');
        
        const rowDiv = document.createElement('div');
        rowDiv.className = 'form-row';
        rowDiv.id = 'row-' + _rowCount;

        // Select dla surowca
        const surowiecGroup = document.createElement('div');
        surowiecGroup.className = 'form-group flex-2';
        surowiecGroup.innerHTML = '<label>Surowiec</label>' +
            '<select class="item-surowiec" required>' +
            '<option value="">— Wybierz surowiec —</option>' +
            _availableSurowce.map(s => '<option value="' + _escapeHtml(s.nazwa) + '">' + _escapeHtml(s.nazwa) + '</option>').join('') +
            '</select>';

        // Input dla ilości
        const iloscGroup = document.createElement('div');
        iloscGroup.className = 'form-group flex-1';
        iloscGroup.innerHTML = '<label>Ilość (kg)</label>' +
            '<input type="number" class="item-ilosc" min="0.01" step="0.01" placeholder="0.00" required>';

        // Przycisk usuwania
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-row-btn';
        removeBtn.innerHTML = '<span class="material-icons">delete</span>';
        removeBtn.onclick = function() { removeRow(rowDiv.id); };

        rowDiv.appendChild(surowiecGroup);
        rowDiv.appendChild(iloscGroup);
        rowDiv.appendChild(removeBtn);

        container.appendChild(rowDiv);
    }

    function removeRow(rowId) {
        const row = document.getElementById(rowId);
        if (row) {
            row.remove();
        }
    }

    function submitOrder() {
        const rows = document.querySelectorAll('.form-row');
        const items = [];
        let hasError = false;

        if (rows.length === 0) {
            _showToast('Musisz dodać co najmniej jeden surowiec.', 'error');
            return;
        }

        rows.forEach(row => {
            const surowiecSelect = row.querySelector('.item-surowiec');
            const iloscInput = row.querySelector('.item-ilosc');

            const surowiec_nazwa = surowiecSelect.value;
            const ilosc_kg = parseFloat(iloscInput.value);

            if (!surowiec_nazwa) {
                hasError = true;
                surowiecSelect.style.borderColor = '#ef4444';
            } else {
                surowiecSelect.style.borderColor = '#fbbf24';
            }

            if (!ilosc_kg || ilosc_kg <= 0) {
                hasError = true;
                iloscInput.style.borderColor = '#ef4444';
            } else {
                iloscInput.style.borderColor = '#fbbf24';
            }

            if (surowiec_nazwa && ilosc_kg > 0) {
                items.push({
                    surowiec_nazwa: surowiec_nazwa,
                    ilosc_kg: ilosc_kg
                });
            }
        });

        if (hasError) {
            _showToast('Popraw błędy w formularzu (wymagany surowiec i ilość > 0).', 'error');
            return;
        }

        const komentarzInput = document.getElementById('orderKomentarz');
        const komentarz = komentarzInput ? komentarzInput.value.trim() : '';
        const submitBtn = document.getElementById('submitBtn');

        submitBtn.disabled = true;

        fetch(API_BASE + '/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                items: items,
                komentarz: komentarz
            })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                _showToast(data.message, 'success');
                setTimeout(() => {
                    // Przekierowanie na listę zamówień (ORDER_LIST_URL zdefiniowane w HTML)
                    window.location.href = (typeof ORDER_LIST_URL !== 'undefined') ? ORDER_LIST_URL : '/warehouse-v2/zamowienia';
                }, 1000);
            } else {
                _showToast(data.message || data.error || 'Wystąpił błąd.', 'error');
                submitBtn.disabled = false;
            }
        })
        .catch(err => {
            console.error('Błąd tworzenia zamówienia:', err);
            _showToast('Błąd połączenia z serwerem.', 'error');
            submitBtn.disabled = false;
        });
    }

    function _showToast(message, type) {
        const toast = document.getElementById('orderToast');
        if (!toast) return;

        toast.textContent = message;
        toast.className = 'order-toast ' + (type || 'success');

        void toast.offsetWidth;
        toast.classList.add('show');

        setTimeout(() => {
            toast.classList.remove('show');
        }, 3500);
    }

    function _escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    document.addEventListener('DOMContentLoaded', init);

    return {
        addRow: addRow,
        removeRow: removeRow,
        submitOrder: submitOrder
    };
})();
