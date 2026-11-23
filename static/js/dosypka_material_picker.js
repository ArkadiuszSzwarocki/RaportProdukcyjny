// cspell:words premiks
/* Grouped BB / MZ / KO tank-assigned raw material picker and datalist sync */
(function () {
    'use strict';

    function parseGroupedData(root) {
        const script = (root || document).querySelector('#dosypka-materials-grouped');
        if (!script) return null;
        try {
            const parsed = JSON.parse(script.textContent || '{}');
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (err) {
            return null;
        }
    }

    function addNextMaterialRow(form) {
        if (form.id === 'dosypka-form' && typeof window.addDosypkaField === 'function') {
            window.addDosypkaField();
            return true;
        }
        if (form.id === 'ds-form' && typeof window.dsAddField === 'function') {
            window.dsAddField();
            return true;
        }
        return false;
    }

    function pickTargetNameInput(form) {
        const inputs = Array.from(form.querySelectorAll('input[name^="nazwa_"]')).filter(
            (el) => !el.disabled,
        );
        if (!inputs.length) return null;
        if (form._lastFocusedMaterialInput && !form._lastFocusedMaterialInput.disabled && form.contains(form._lastFocusedMaterialInput)) {
            if (!String(form._lastFocusedMaterialInput.value || '').trim()) {
                return form._lastFocusedMaterialInput;
            }
        }
        const firstEmpty = inputs.find((el) => !String(el.value || '').trim());
        if (firstEmpty) return firstEmpty;

        if (addNextMaterialRow(form)) {
            const updatedInputs = Array.from(form.querySelectorAll('input[name^="nazwa_"]')).filter(
                (el) => !el.disabled,
            );
            return updatedInputs.find((el) => !String(el.value || '').trim()) || null;
        }
        return null;
    }

    function applyMaterialSelection(form, materialName) {
        const target = pickTargetNameInput(form);
        if (!target) return;
        target.value = materialName;
        target.dispatchEvent(new Event('input', { bubbles: true }));
        target.dispatchEvent(new Event('change', { bubbles: true }));
        const row = target.closest('.dosypka-row, .ds-field-row');
        const kgInput = row ? row.querySelector('input[name^="kg_"]') : null;
        if (kgInput && !kgInput.disabled) {
            kgInput.focus();
            if (typeof kgInput.select === 'function') kgInput.select();
        }
    }

    function syncDatalist(form, data, showAll) {
        const datalist = document.getElementById('surowce-agro-list') || document.getElementById('surowce-list');
        if (!datalist) return;
        const tankByName = {};
        (data.groups || []).forEach((group) => {
            (group.items || []).forEach((item) => {
                tankByName[item.name] = item.all_tanks || item.tanks || [];
            });
        });

        const assigned = Array.isArray(data.assigned_names) ? data.assigned_names : [];
        const unassigned = Array.isArray(data.unassigned_names) ? data.unassigned_names : [];
        const names = showAll ? assigned.concat(unassigned) : assigned;

        datalist.innerHTML = '';
        const fragment = document.createDocumentFragment();
        names.forEach((name) => {
            const option = document.createElement('option');
            option.value = name;
            const codes = tankByName[name];
            if (Array.isArray(codes) && codes.length) {
                option.label = codes.join(', ');
            }
            fragment.appendChild(option);
        });
        datalist.appendChild(fragment);
        const allowInput = form.querySelector('input[name="allow_unassigned"]');
        if (allowInput) {
            allowInput.value = showAll ? '1' : '0';
        }
    }

    function renderPicker(pickerBox, form, data) {
        const groupsHost = pickerBox.querySelector('.dosypka-picker-groups');
        const unassignedBox = pickerBox.querySelector('.dosypka-picker-unassigned');
        const unassignedHost = pickerBox.querySelector('.dosypka-picker-unassigned-chips');
        const toggle = pickerBox.querySelector('#dosypka-show-all-materials');
        const headBox = pickerBox.querySelector('.dosypka-picker-head');
        if (!groupsHost) return;

        const maluchySet = new Set((data.maluchy_tanks || []).map((c) => String(c || '').trim().toUpperCase()));
        const existingLegend = headBox ? headBox.querySelector('.dosypka-maluchy-legend') : null;
        if (existingLegend) existingLegend.remove();
        if (headBox && maluchySet.size > 0) {
            const legend = document.createElement('div');
            legend.className = 'dosypka-maluchy-legend';
            legend.textContent = `🪣 Premix/Premiks w Maluchach: ${Array.from(maluchySet).join(', ')}`;
            headBox.appendChild(legend);
        }

        groupsHost.innerHTML = '';
        (data.groups || []).forEach((group) => {
            const card = document.createElement('div');
            card.className = 'dosypka-picker-group';

            const head = document.createElement('div');
            head.className = 'dosypka-picker-group-head';
            const titleSpan = document.createElement('span');
            titleSpan.textContent = group.title || group.code;
            const countSpan = document.createElement('span');
            countSpan.textContent = String((group.items || []).length);
            head.appendChild(titleSpan);
            head.appendChild(countSpan);
            card.appendChild(head);

            const chips = document.createElement('div');
            chips.className = 'dosypka-picker-chips';
            if (group.items && group.items.length) {
                group.items.forEach((item) => {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    const isPremixName = /(?:premix|premiks)/i.test(String(item.name || ''));
                    const matchedMaluchy = isPremixName
                        ? (Array.isArray(item.maluchy_tanks)
                            ? item.maluchy_tanks
                            : (item.tanks || []).filter((c) => maluchySet.has(String(c || '').toUpperCase())))
                        : [];
                    const inMaluchy = Boolean(isPremixName && (item.in_maluchy || matchedMaluchy.length > 0));
                    btn.className = 'dosypka-picker-chip' + (inMaluchy ? ' dosypka-picker-chip-maluchy' : '');
                    btn.title = inMaluchy
                        ? `${item.name} (${(item.tanks || []).join(', ')}) — 🪣 Wrzucono w Maluchach: ${matchedMaluchy.join(', ')}`
                        : `${item.name} (${(item.tanks || []).join(', ')})`;

                    const nameSpan = document.createElement('span');
                    nameSpan.textContent = item.name;
                    btn.appendChild(nameSpan);

                    (item.tanks || []).forEach((tankCode) => {
                        const isBucketTank = isPremixName && maluchySet.has(String(tankCode || '').toUpperCase());
                        const tankSpan = document.createElement('span');
                        tankSpan.className = 'dosypka-picker-chip-tanks' + (isBucketTank ? ' dosypka-picker-tank-maluchy' : '');
                        tankSpan.textContent = isBucketTank ? `🪣 ${tankCode}` : tankCode;
                        btn.appendChild(tankSpan);
                    });

                    btn.addEventListener('click', () => applyMaterialSelection(form, item.name));
                    chips.appendChild(btn);
                });
            } else {
                const empty = document.createElement('span');
                empty.className = 'dosypka-picker-empty';
                empty.textContent = 'Brak przypisanych surowców';
                chips.appendChild(empty);
            }
            card.appendChild(chips);
            groupsHost.appendChild(card);
        });

        const unassigned = Array.isArray(data.unassigned_names) ? data.unassigned_names : [];
        if (unassignedHost) {
            unassignedHost.innerHTML = '';
            unassigned.forEach((name) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'dosypka-picker-chip dosypka-picker-chip-unassigned';
                btn.textContent = name;
                btn.addEventListener('click', () => applyMaterialSelection(form, name));
                unassignedHost.appendChild(btn);
            });
        }

        const updateVisibility = () => {
            const showAll = Boolean(toggle && toggle.checked);
            syncDatalist(form, data, showAll);
            if (unassignedBox) {
                unassignedBox.hidden = !(showAll && unassigned.length > 0);
            }
        };

        if (toggle) {
            toggle.addEventListener('change', updateVisibility);
        }
        updateVisibility();
    }

    function bindForm(form) {
        if (!form || form.dataset.materialPickerBound === '1') return;
        const root = form.closest('.dosypka-popup-container, .ds-panel-body') || document;
        const pickerBox = root.querySelector('.dosypka-picker-box');
        const data = parseGroupedData(root);
        if (!pickerBox || !data) return;
        form.dataset.materialPickerBound = '1';

        form.addEventListener('focusin', (event) => {
            if (event.target && event.target.name && event.target.name.startsWith('nazwa_')) {
                form._lastFocusedMaterialInput = event.target;
            }
        });

        form.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter') return;
            const target = event.target;
            if (!target || !target.name || !target.name.startsWith('kg_')) return;
            event.preventDefault();
            const kgInputs = Array.from(form.querySelectorAll('input[name^="kg_"]')).filter(
                (el) => !el.disabled,
            );
            const idx = kgInputs.indexOf(target);
            if (idx !== -1 && idx + 1 < kgInputs.length) {
                const nextKg = kgInputs[idx + 1];
                nextKg.focus();
                if (typeof nextKg.select === 'function') nextKg.select();
            }
        });

        renderPicker(pickerBox, form, data);
    }

    function init() {
        document.querySelectorAll('#dosypka-form, #ds-form').forEach(bindForm);
    }

    window.initDosypkaMaterialPicker = init;
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
