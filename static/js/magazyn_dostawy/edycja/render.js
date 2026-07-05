// render.js


function notifyReadOnly() {
        if (typeof showToast === 'function') {
            showToast('Status OCZEKUJE: formularz wydania działa w trybie podglądu.', 'warning');
        } else if (typeof AppDialog !== 'undefined') {
            AppDialog.alert('Status OCZEKUJE: formularz wydania działa w trybie podglądu.');
        }
    }

function toggleFlowHelp() {
        const panel = document.getElementById('flowHelpPanel');
        if (!panel) {
            return;
        }
        panel.style.display = panel.style.display === 'none' || !panel.style.display ? 'block' : 'none';
    }

function hideDraftDecisionBanner() {
        const banner = document.getElementById('draftDecisionBanner');
        if (banner) {
            banner.style.display = 'none';
        }
    }

function showDraftDecisionBanner(draft) {
        const banner = document.getElementById('draftDecisionBanner');
        if (!banner) {
            return;
        }

        const meta = document.getElementById('draftDecisionMeta');
        const savedAt = draft && draft.saved_at ? new Date(draft.saved_at) : null;
        const savedAtText = savedAt && !Number.isNaN(savedAt.getTime())
            ? savedAt.toLocaleString('pl-PL')
            : 'nieznany czas zapisu';
        const itemsCount = draft && Array.isArray(draft.items) ? draft.items.length : 0;

        if (meta) {
            meta.textContent = `Szkic: ${itemsCount} palet, zapis: ${savedAtText}.`;
        }

        banner.style.display = 'block';
    }

function continueDraftEntry() {
        if (!pendingDraftToDecide) {
            return;
        }
        restoreDraftState(pendingDraftToDecide, { silentToast: false });
        pendingDraftToDecide = null;
        hideDraftDecisionBanner();
        renderItems();
        updateSaveButtonState();
    }

function startFreshEntry() {
        clearDraftState();
        pendingDraftToDecide = null;
        hideDraftDecisionBanner();

        items = [];
        copiedRowsInfoByItem = {};
        palletPickerState = null;

        const countInput = document.getElementById('pallet_count');
        const targetInput = document.getElementById('lokalizacja_do');
        const scannerInput = document.getElementById('scanner_input');
        const bypassInput = document.getElementById('skip_warehouse_lookup');
        if (countInput) countInput.value = '0';
        if (targetInput) targetInput.value = '';
        if (scannerInput) scannerInput.value = '';
        if (bypassInput) bypassInput.checked = false;

        renderItems();
        updateSaveButtonState();
    }

function renderLocationSuggestionOptions(suggestions) {
        const dataList = ensureLocationSuggestionsList();
        dataList.innerHTML = '';

        (suggestions || []).forEach(code => {
            const normalizedCode = normalizeLocation(code);
            if (!normalizedCode) {
                return;
            }
            const option = document.createElement('option');
            option.value = normalizedCode;
            dataList.appendChild(option);
        });
    }

function handleLocationSuggestInput(inputElement) {
        if (!inputElement) {
            return;
        }
        inputElement.value = normalizeLocation(inputElement.value);
        queueLocationSuggestions(inputElement.value);
    }

function renderSaveInfo(saveInfo, variant, messages) {
        if (!saveInfo) {
            return;
        }

        if (!Array.isArray(messages) || messages.length === 0) {
            saveInfo.style.display = 'none';
            saveInfo.innerHTML = '';
            return;
        }

        const isSuccess = variant === 'success';
        saveInfo.style.display = 'block';
        saveInfo.style.background = isSuccess ? '#ecfdf5' : '#fff7ed';
        saveInfo.style.border = `1px solid ${isSuccess ? '#86efac' : '#fed7aa'}`;
        saveInfo.style.color = isSuccess ? '#166534' : '#9a3412';

        const marker = isSuccess ? '✓' : '•';
        saveInfo.innerHTML = messages
            .map(msg => `<div style="line-height: 1.35; margin: 1px 0;">${marker} ${escapeAttr(msg)}</div>`)
            .join('');
    }

function updateSaveButtonState() {
        const saveBtn = document.getElementById('save_transfer_btn');
        const saveInfo = document.getElementById('save_transfer_info');
        const targetInput = document.getElementById('lokalizacja_do');
        if (!saveBtn) {
            return;
        }

        const blockers = getSaveBlockers();
        const enabled = blockers.length === 0;
        saveBtn.disabled = !enabled;
        saveBtn.style.opacity = enabled ? '1' : '0.55';
        saveBtn.style.cursor = enabled ? 'pointer' : 'not-allowed';

        const targetLoc = targetInput ? targetInput.value : '';
        const highlightTarget = !isFilled(targetLoc) && Array.isArray(items) && items.length > 0;
        if (targetInput) {
            targetInput.style.border = highlightTarget ? '2px solid #dc2626' : '1px solid #e2e8f0';
            targetInput.style.boxShadow = highlightTarget ? 'inset 0 0 0 1px rgba(220,38,38,0.08)' : 'none';
        }

        if (enabled) {
            saveBtn.title = '';
            renderSaveInfo(saveInfo, 'success', ['Formularz kompletny. Możesz kliknąć PRZESUŃ.']);
        } else {
            saveBtn.title = blockers[0] || 'Przycisk jest tymczasowo zablokowany.';
            renderSaveInfo(saveInfo, 'warning', blockers);
        }
    }

function renderItems() {
        const tbody = document.querySelector('#itemsTable tbody');
        const noItems = document.getElementById('noItemsMsg');
        const disabledAttr = READ_ONLY_MODE ? 'disabled' : '';
        const targetLoc = getCurrentTargetLocation();
        tbody.innerHTML = '';
        
        if (items.length === 0) {
            noItems.style.display = 'block';
            copiedRowsInfoByItem = {};
            
            document.getElementById('th_paleta').style.display = 'none';
            document.getElementById('th_partia').style.display = 'none';
            document.getElementById('th_prod').style.display = 'none';
            document.getElementById('th_przyd').style.display = 'none';
            
            updateSaveButtonState();
            return;
        }
        noItems.style.display = 'none';

        const hasManual = items.some(it => it.is_manual);
        const anyHasPaleta = hasManual || items.some(it => isFilled(it.nr_palety));
        const anyHasPartia = hasManual || items.some(it => isFilled(it.nr_partii));
        const anyHasProd = hasManual || items.some(it => isFilled(it.data_produkcji));
        const anyHasPrzyd = hasManual || items.some(it => isFilled(it.data_przydatnosci));

        document.getElementById('th_paleta').style.display = anyHasPaleta ? 'table-cell' : 'none';
        document.getElementById('th_partia').style.display = anyHasPartia ? 'table-cell' : 'none';
        document.getElementById('th_prod').style.display = anyHasProd ? 'table-cell' : 'none';
        document.getElementById('th_przyd').style.display = anyHasPrzyd ? 'table-cell' : 'none';

        items.forEach((item, index) => {
            const row = document.createElement('tr');
            row.style.background = item.is_manual ? '#f0fdf4' : (index % 2 === 0 ? '#fff' : '#fcfcfc');
            row.style.borderBottom = '2px solid #e2e8f0';

            const quantityValue = getItemQuantity(item);
            const unitValue = getItemUnit(item);
            const validation = getItemValidationMap(item, targetLoc);
            const productBorderStyle = getValidationBorderStyle(validation.productName);
            const sourceBorderStyle = getValidationBorderStyle(validation.sourceSpot);
            const quantityBorderStyle = getValidationBorderStyle(validation.quantity);
            const unitBorderStyle = getValidationBorderStyle(validation.unit);
            const batchBorderStyle = getValidationBorderStyle(validation.nr_partii);
            const prodDateBorderStyle = getValidationBorderStyle(validation.data_produkcji);
            const expiryDateBorderStyle = getValidationBorderStyle(validation.data_przydatnosci);
            const copiedFromNumber = getCopiedFromNumber(item, index);
            const copyButtonHtml = index > 0
                ? `<button ${disabledAttr} onclick="copyItem(${index})" title="Kopiuj dane z palety nr ${index}" style="background:none; border:none; color:#0ea5e9; cursor:pointer;">
                        <span class="material-icons" style="font-size:20px;">content_copy</span>
                   </button>`
                : '';
            const showWarning = (hasErr) => (hasErr && formSubmitAttempted) ? `<span class="material-icons" style="color: #dc2626; font-size: 16px; position: absolute; right: 18px; top: 17px; pointer-events: none;">warning</span>` : '';

            row.innerHTML = `
                <td style="padding: 10px 20px; font-size: 13px; color: #64748b; vertical-align: middle; font-weight: 800; white-space: nowrap;">
                    ${index + 1}
                </td>
                <td style="padding: 8px 10px; border: none; position: relative;">
                    ${copiedFromNumber ? `<div style="font-size: 10px; font-weight: 700; color: #b91c1c; margin-bottom: 4px;">Skopiowano z palety nr ${copiedFromNumber}</div>` : ''}
                    ${showWarning(validation.productName)}
                    <input type="text" ${disabledAttr} value="${escapeAttr(item.productName || '')}" onchange="updateItem(${index}, 'productName', this.value)"
                           list="productsList" placeholder="Wybierz produkt"
                           style="width: 100%; height: 34px; ${productBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 13px; font-weight: 700; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; position: relative;">
                    ${showWarning(validation.sourceSpot)}
                      <input type="text" ${disabledAttr} value="${escapeAttr(item.sourceSpot || '')}" onchange="updateItem(${index}, 'sourceSpot', this.value.toUpperCase())"
                          oninput="handleLocationSuggestInput(this)" onfocus="queueLocationSuggestions(this.value)" list="locationSuggestionsList" autocomplete="off"
                           placeholder="np. BF_MS01"
                           style="width: 100%; height: 34px; ${sourceBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 700; text-transform: uppercase; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; position: relative;">
                    ${showWarning(validation.quantity)}
                    <input type="number" ${disabledAttr} value="${escapeAttr(quantityValue)}"
                           onchange="updateItem(${index}, 'quantity', this.value)" placeholder=""
                           style="width: 100%; height: 34px; ${quantityBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 13px; text-align: right; font-weight: 700; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; position: relative;">
                    ${showWarning(validation.unit)}
                    <select ${disabledAttr} onchange="updateItem(${index}, 'unit', this.value)"
                            style="width: 100%; height: 34px; ${unitBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 13px; font-weight: 700; box-sizing: border-box; min-width: 0; background: white;">
                        <option value="" ${unitValue === '' ? 'selected' : ''}>--</option>
                        <option value="kg" ${unitValue === 'kg' ? 'selected' : ''}>kg</option>
                        <option value="szt" ${unitValue === 'szt' ? 'selected' : ''}>szt</option>
                    </select>
                </td>
                <td style="padding: 8px 10px; border: none; ${anyHasPaleta ? '' : 'display:none;'}">
                    <input type="text" ${disabledAttr} value="${escapeAttr(item.nr_palety || '')}" onchange="updateItem(${index}, 'nr_palety', this.value.toUpperCase())"
                           placeholder="Nr SSCC"
                           style="width: 100%; height: 34px; border: 1px solid #e2e8f0; border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 600; box-sizing: border-box; min-width: 0; text-transform: uppercase;">
                </td>
                <td style="padding: 8px 10px; border: none; ${anyHasPartia ? '' : 'display:none;'}">
                    <input type="text" ${disabledAttr} value="${escapeAttr(item.nr_partii || '')}" onchange="updateItem(${index}, 'nr_partii', this.value)"
                           placeholder="Nr partii"
                           style="width: 100%; height: 34px; ${batchBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 600; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; ${anyHasProd ? '' : 'display:none;'}">
                    <input type="date" ${disabledAttr} value="${escapeAttr(item.data_produkcji || '')}" onchange="updateItem(${index}, 'data_produkcji', this.value)"
                           title="Data produkcji"
                           style="width: 100%; height: 34px; ${prodDateBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 600; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 8px 10px; border: none; ${anyHasPrzyd ? '' : 'display:none;'}">
                    <input type="date" ${disabledAttr} value="${escapeAttr(item.data_przydatnosci || '')}" onchange="updateItem(${index}, 'data_przydatnosci', this.value)"
                           title="Data przydatności"
                           style="width: 100%; height: 34px; ${expiryDateBorderStyle} border-radius: 4px; padding: 0 8px; font-size: 12px; font-weight: 600; box-sizing: border-box; min-width: 0;">
                </td>
                <td style="padding: 10px 20px; text-align: center; vertical-align: middle;">
                    <div style="display: inline-flex; align-items: center; gap: 6px;">
                        ${copyButtonHtml}
                        <button ${disabledAttr} onclick="removeItem(${index})" title="Usuń paletę nr ${index + 1}" style="background:none; border:none; color:#ef4444; cursor:pointer;">
                            <span class="material-icons" style="font-size:20px;">delete</span>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });

        updateSaveButtonState();
    }

function addEmptyRow() {
        if (READ_ONLY_MODE) {
            notifyReadOnly();
            return;
        }
        items.push(buildEmptyItem());
        const countInput = document.getElementById('pallet_count');
        countInput.value = items.length;
        saveDraftState();
        renderItems();
    }

function copyItem(index) {
        if (READ_ONLY_MODE) {
            notifyReadOnly();
            return;
        }
        if (index <= 0) {
            return;
        }

        const source = items[index - 1];
        const target = items[index];
        if (!source || !target) {
            return;
        }

        target.productName = source.productName || '';
        target.nr_partii = source.nr_partii || '';
        target.data_produkcji = source.data_produkcji || '';
        target.data_przydatnosci = source.data_przydatnosci || '';
        const sourceUnit = getItemUnit(source);
        if (sourceUnit === 'szt') {
            target.packageForm = 'packaging';
        } else if (sourceUnit === 'kg') {
            target.packageForm = 'bags';
        } else {
            target.packageForm = '';
        }
        target.sourceSpot = source.sourceSpot || getDefaultSourceSpot();

        const copiedQty = getItemQuantity(source);
        if (!(copiedQty === '' || copiedQty === null || copiedQty === undefined)) {
            if (getItemUnit(source) === 'szt') {
                target.unitsPerPallet = copiedQty;
                target.netWeight = '';
            } else {
                target.netWeight = copiedQty;
                target.unitsPerPallet = '';
            }
        } else {
            target.netWeight = '';
            target.unitsPerPallet = '';
        }

        setCopiedFromNumber(target, index, index);

        saveDraftState();
        renderItems();
    }
