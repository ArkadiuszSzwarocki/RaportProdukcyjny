/**
 * Logika Kalkulatora Zasypu (Sprawdzanie zapotrzebowania i wysyłanie zamówień)
 */
const ZasypCalculatorModule = (function () {
    'use strict';

    const CHECK_STOCK_API = '/magazyny-nowe/api/orders/check_stock';
    const CREATE_ORDER_API = '/magazyny-nowe/api/orders/create';
    const SUROWCE_API = '/magazyny-nowe/api/orders/surowce';

    let _availableSurowce = [];
    let _missingItemsToOrder = []; // Cache to store missing items that need to be ordered

    function init() {
        loadSurowce();
    }

    function loadSurowce() {
        fetch(SUROWCE_API)
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success && data.surowce) {
                    _availableSurowce = data.surowce;
                }
            })
            .catch(function(err) {
                console.error('Błąd podczas pobierania surowców do kalkulatora:', err);
            });
    }

    function openModal() {
        const modal = document.getElementById('zasyp-calculator-modal');
        if (modal) {
            modal.style.display = 'flex';
            resetForm();
            // Start with one row by default
            addRow();
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
    }

    function addRow() {
        const tbody = document.getElementById('calc-items-tbody');
        const template = document.getElementById('calc-row-template').content.cloneNode(true);
        const select = template.querySelector('.calc-surowiec-select');
        
        _availableSurowce.forEach(function(s) {
            const opt = document.createElement('option');
            opt.value = s.nazwa;
            opt.textContent = s.nazwa;
            select.appendChild(opt);
        });

        tbody.appendChild(template);
        hideResults(); // Zmieniono dane wejściowe, ukryj wyniki
    }

    function collectItems() {
        const items = [];
        const tbody = document.getElementById('calc-items-tbody');
        const rows = tbody.querySelectorAll('tr');

        rows.forEach(function(row) {
            const surowiec = row.querySelector('.calc-surowiec-select').value;
            const rate = parseFloat(row.querySelector('.calc-rate-input').value) || 0;

            if (surowiec && rate > 0) {
                items.push({
                    surowiec_nazwa: surowiec,
                    przelicznik_na_1t: rate
                });
            }
        });

        return items;
    }

    function checkStock() {
        const tonsInput = document.getElementById('calc-order-tons').value;
        const tons = parseFloat(tonsInput) || 0;

        if (tons <= 0) {
            alert('Wprowadź prawidłową wielkość zlecenia w tonach.');
            return;
        }

        const items = collectItems();
        if (items.length === 0) {
            alert('Dodaj przynajmniej jeden surowiec i podaj jego przelicznik.');
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
                renderResults(data.results);
            } else {
                alert('Błąd: ' + (data.error || data.message || 'Nieznany błąd.'));
            }
        })
        .catch(function(err) {
            console.error('Błąd zapytania check_stock:', err);
            alert('Wystąpił błąd komunikacji z serwerem.');
        });
    }

    function renderResults(results) {
        const tbody = document.getElementById('calc-results-tbody');
        tbody.innerHTML = '';
        _missingItemsToOrder = [];
        let hasMissing = false;

        results.forEach(function(r) {
            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid #f1f5f9';

            let missingHtml = `<span style="color: #64748b; font-weight: bold;">0.00 kg</span>`;
            if (r.brakujace_kg > 0) {
                missingHtml = `<span style="color: #ef4444; font-weight: bold;">${r.brakujace_kg.toFixed(2)} kg</span>`;
                hasMissing = true;
                _missingItemsToOrder.push({
                    surowiec_nazwa: r.surowiec_nazwa,
                    ilosc_kg: r.brakujace_kg
                });
            }

            tr.innerHTML = `
                <td style="padding: 10px; font-weight: 600; color: #334155; font-size: 13px;">${r.surowiec_nazwa}</td>
                <td style="padding: 10px; text-align: right; font-size: 13px;">${r.potrzebne_kg.toFixed(2)} kg</td>
                <td style="padding: 10px; text-align: right; font-size: 13px; color: ${r.stan_magazynowy_kg >= r.potrzebne_kg ? '#10b981' : '#f59e0b'}; font-weight: 600;">${r.stan_magazynowy_kg.toFixed(2)} kg</td>
                <td style="padding: 10px; text-align: right; font-size: 13px;">${missingHtml}</td>
            `;
            tbody.appendChild(tr);
        });

        document.getElementById('calc-results-section').style.display = 'block';
        
        if (hasMissing) {
            document.getElementById('calc-order-action-container').style.display = 'flex';
        } else {
            document.getElementById('calc-order-action-container').style.display = 'none';
        }
    }

    function submitOrder() {
        if (_missingItemsToOrder.length === 0) {
            alert('Brakujące surowce zostały już dodane lub brak braków.');
            return;
        }

        const btn = document.querySelector('#calc-order-action-container button');
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = 'Wysyłanie...';

        fetch(CREATE_ORDER_API, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                items: _missingItemsToOrder,
                komentarz: ''
            })
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                alert('Zamówienie wysłane z sukcesem! Przekazano do magazynu.');
                closeModal();
            } else {
                alert('Błąd tworzenia zamówienia: ' + (data.error || data.message || 'Nieznany błąd'));
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        })
        .catch(function(err) {
            console.error('Błąd zamówienia:', err);
            alert('Wystąpił błąd komunikacji z serwerem podczas wysyłania zamówienia.');
            btn.disabled = false;
            btn.innerHTML = originalText;
        });
    }

    return {
        init: init,
        openModal: openModal,
        closeModal: closeModal,
        addRow: addRow,
        checkStock: checkStock,
        submitOrder: submitOrder
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    ZasypCalculatorModule.init();
});

// Globalne funkcje do przypięcia na kliknięciach (bo onclick="..")
window.openZasypCalculatorModal = ZasypCalculatorModule.openModal;
window.closeZasypCalculatorModal = ZasypCalculatorModule.closeModal;
window.addCalculatorRow = ZasypCalculatorModule.addRow;
window.checkStockAndCalculate = ZasypCalculatorModule.checkStock;
window.submitCalculatorOrder = ZasypCalculatorModule.submitOrder;

window.addEventListener('click', function(event) {
    const modal = document.getElementById('zasyp-calculator-modal');
    if (event.target === modal) {
        window.closeZasypCalculatorModal();
    }
});
