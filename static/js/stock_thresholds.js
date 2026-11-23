/* Standalone warehouse minimum-stock thresholds modal and filter controls */
(function () {
    'use strict';

    const stockDialog = document.getElementById('stock-bulk-dialog');
    const bulkForm = document.getElementById('stock-bulk-form');
    if (!stockDialog || !bulkForm) {
        return;
    }

    const stockChecks = [...bulkForm.querySelectorAll('.stock-bulk-check')];
    const selectAll = document.getElementById('stock-select-all');
    const bulkSearch = document.getElementById('stock-bulk-search');
    const bulkCategoryFilter = document.getElementById('stock-bulk-category-filter');

    function syncStockSelection() {
        let count = 0;
        stockChecks.forEach((check) => {
            const row = check.closest('tr');
            const minInput = row.querySelector('input[type="number"]');
            const unitSelect = row.querySelector('select');
            if (minInput) minInput.disabled = !check.checked;
            if (unitSelect) unitSelect.disabled = !check.checked;
            row.classList.toggle('stock-bulk-selected', check.checked);
            if (check.checked) count += 1;
        });

        const countEl = document.getElementById('stock-bulk-count');
        const saveBtn = document.getElementById('stock-bulk-save');
        if (countEl) countEl.textContent = `Zaznaczono: ${count} / ${stockChecks.length}`;
        if (saveBtn) saveBtn.disabled = count === 0;

        if (selectAll) {
            selectAll.checked = count > 0 && count === stockChecks.length;
            selectAll.indeterminate = count > 0 && count < stockChecks.length;
        }

        bulkForm.querySelectorAll('.stock-category-check').forEach((category) => {
            const checks = stockChecks.filter(
                (check) => check.closest('tr').dataset.category === category.dataset.category,
            );
            const checked = checks.filter((check) => check.checked).length;
            category.checked = checks.length > 0 && checked === checks.length;
            category.indeterminate = checked > 0 && checked < checks.length;
        });
    }

    function applyBulkFilter() {
        const query = String(bulkSearch ? bulkSearch.value : '').trim().toLowerCase();
        const cat = bulkCategoryFilter ? bulkCategoryFilter.value : 'ALL';
        const visiblePerCategory = {};

        bulkForm.querySelectorAll('.stock-bulk-row').forEach((row) => {
            const matchesCat = cat === 'ALL' || row.dataset.category === cat;
            const matchesQuery = !query || String(row.dataset.material || '').toLowerCase().includes(query);
            const visible = matchesCat && matchesQuery;
            row.style.display = visible ? '' : 'none';
            if (visible) {
                visiblePerCategory[row.dataset.category] = (visiblePerCategory[row.dataset.category] || 0) + 1;
            }
        });

        bulkForm.querySelectorAll('tr[data-category-header]').forEach((header) => {
            header.style.display = visiblePerCategory[header.dataset.categoryHeader] ? '' : 'none';
        });
    }

    const openBtn = document.getElementById('stock-bulk-open');
    if (openBtn) {
        openBtn.addEventListener('click', () => {
            syncStockSelection();
            stockDialog.showModal();
        });
    }

    stockDialog.querySelectorAll('[data-close-stock]').forEach((button) => {
        button.addEventListener('click', () => stockDialog.close());
    });

    if (bulkSearch) bulkSearch.addEventListener('input', applyBulkFilter);
    if (bulkCategoryFilter) bulkCategoryFilter.addEventListener('change', applyBulkFilter);

    if (selectAll) {
        selectAll.addEventListener('change', () => {
            stockChecks.forEach((check) => {
                const row = check.closest('tr');
                if (row && row.style.display !== 'none') check.checked = selectAll.checked;
            });
            syncStockSelection();
        });
    }

    stockChecks.forEach((check) => check.addEventListener('change', syncStockSelection));

    bulkForm.querySelectorAll('.stock-category-check').forEach((category) => {
        category.addEventListener('change', () => {
            stockChecks
                .filter((check) => check.closest('tr').dataset.category === category.dataset.category)
                .forEach((check) => { check.checked = category.checked; });
            syncStockSelection();
        });
    });

    document.querySelectorAll('.stock-edit').forEach((button) => {
        button.addEventListener('click', () => {
            if (bulkSearch) bulkSearch.value = '';
            if (bulkCategoryFilter) bulkCategoryFilter.value = 'ALL';
            applyBulkFilter();
            let matchedRow = null;
            stockChecks.forEach((check) => {
                const row = check.closest('tr');
                const matched = row && row.dataset.ruleKey === button.dataset.ruleKey;
                check.checked = Boolean(matched);
                if (matched) matchedRow = row;
            });
            syncStockSelection();
            stockDialog.showModal();
            if (matchedRow) matchedRow.scrollIntoView({ block: 'center' });
        });
    });

    bulkForm.addEventListener('submit', () => {
        const button = document.getElementById('stock-bulk-save');
        if (button) {
            button.disabled = true;
            button.textContent = 'Zapisywanie…';
        }
    });

    document.querySelectorAll('form[data-confirm]').forEach((form) => {
        form.addEventListener('submit', (event) => {
            if (!window.confirm(form.dataset.confirm || 'Czy na pewno usunąć?')) {
                event.preventDefault();
            }
        });
    });
}());
