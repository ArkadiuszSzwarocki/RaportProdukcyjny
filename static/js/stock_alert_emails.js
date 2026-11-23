/* Email Center stock alert recipient assignment and summary controls */
(function () {
    'use strict';

    const summaryForm = document.getElementById('stock-summary-form');
    if (summaryForm) {
        summaryForm.addEventListener('submit', () => {
            const button = summaryForm.querySelector('button[type="submit"]');
            if (button) {
                button.disabled = true;
                button.textContent = 'Wysyłanie…';
            }
        });
    }

    document.querySelectorAll('form[data-confirm]').forEach((form) => {
        form.addEventListener('submit', (event) => {
            if (!window.confirm(form.dataset.confirm || 'Czy na pewno wykonać tę operację?')) {
                event.preventDefault();
            }
        });
    });

    const table = document.getElementById('email-rules-table');
    const groupSelect = document.getElementById('email-group-select');
    const previewEl = document.getElementById('email-group-preview');
    if (!table || !groupSelect) {
        return;
    }

    const ruleChecks = [...table.querySelectorAll('.email-rule-check')];
    const selectAll = document.getElementById('email-select-all');
    const searchInput = document.getElementById('email-rules-search');
    const categorySelect = document.getElementById('email-rules-category');
    const countEl = document.getElementById('email-selected-count');
    const submitBtn = document.getElementById('email-assign-submit');

    function updateGroupPreview() {
        if (!previewEl) return;
        const option = groupSelect.selectedOptions[0];
        if (!option || !option.value) {
            previewEl.textContent = 'Brak wybranej grupy — zapis z pustą grupą odepnie odbiorców i wyłączy powiadomienia dla zaznaczonych pozycji.';
            return;
        }
        previewEl.textContent = `Do: ${option.dataset.to} · DW: ${option.dataset.cc || 'brak'}`;
    }

    function syncRuleSelection() {
        let count = 0;
        ruleChecks.forEach((check) => {
            const row = check.closest('tr');
            if (row) row.classList.toggle('stock-bulk-selected', check.checked);
            if (check.checked) count += 1;
        });

        if (countEl) countEl.textContent = `Zaznaczono: ${count} / ${ruleChecks.length}`;
        if (submitBtn) submitBtn.disabled = count === 0;

        if (selectAll) {
            selectAll.checked = count > 0 && count === ruleChecks.length;
            selectAll.indeterminate = count > 0 && count < ruleChecks.length;
        }

        table.querySelectorAll('.email-category-check').forEach((category) => {
            const checks = ruleChecks.filter(
                (check) => check.closest('tr').dataset.category === category.dataset.category,
            );
            const checked = checks.filter((check) => check.checked).length;
            category.checked = checks.length > 0 && checked === checks.length;
            category.indeterminate = checked > 0 && checked < checks.length;
        });
    }

    function applyRulesFilter() {
        const query = String(searchInput ? searchInput.value : '').trim().toLowerCase();
        const cat = categorySelect ? categorySelect.value : 'ALL';
        const visiblePerCategory = {};

        table.querySelectorAll('.email-rule-row').forEach((row) => {
            const matchesCat = cat === 'ALL' || row.dataset.category === cat;
            const matchesQuery = !query || String(row.dataset.material || '').toLowerCase().includes(query);
            const visible = matchesCat && matchesQuery;
            row.style.display = visible ? '' : 'none';
            if (visible) {
                visiblePerCategory[row.dataset.category] = (visiblePerCategory[row.dataset.category] || 0) + 1;
            }
        });

        table.querySelectorAll('tr[data-category-header]').forEach((header) => {
            header.style.display = visiblePerCategory[header.dataset.categoryHeader] ? '' : 'none';
        });
    }

    if (searchInput) searchInput.addEventListener('input', applyRulesFilter);
    if (categorySelect) categorySelect.addEventListener('change', applyRulesFilter);
    groupSelect.addEventListener('change', updateGroupPreview);

    if (selectAll) {
        selectAll.addEventListener('change', () => {
            ruleChecks.forEach((check) => {
                const row = check.closest('tr');
                if (row && row.style.display !== 'none') check.checked = selectAll.checked;
            });
            syncRuleSelection();
        });
    }

    ruleChecks.forEach((check) => check.addEventListener('change', syncRuleSelection));

    table.querySelectorAll('.email-category-check').forEach((category) => {
        category.addEventListener('change', () => {
            ruleChecks
                .filter((check) => check.closest('tr').dataset.category === category.dataset.category)
                .forEach((check) => { check.checked = category.checked; });
            syncRuleSelection();
        });
    });

    updateGroupPreview();
    syncRuleSelection();
}());
