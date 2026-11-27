function safeToast(msg, kind) {
    if (typeof showToast === 'function') {
        showToast(msg, kind || 'info');
    } else if (typeof AppDialog !== 'undefined') {
        AppDialog.alert(msg);
    }
}

/**
 * normalizeRackPrefix - standardizes rack prefix (e.g., 'R-01', 'R1', 'R-1', 'R01' -> 'R01').
 */
function normalizeRackPrefix(prefix) {
    if (!prefix) return '';
    const clean = String(prefix).toUpperCase().replace(/[^A-Z0-9]/g, '');
    const match = clean.match(/^R?(\d{1,2})$/);
    if (match) {
        return 'R' + match[1].padStart(2, '0');
    }
    return clean;
}

/**
 * normalizeLocationCode - normalizes slot locations (e.g., 'R-01-01-01', 'R10101', 'R010101' -> 'R010101').
 */
function normalizeLocationCode(code) {
    if (!code) return '';
    const clean = String(code).toUpperCase().replace(/[^A-Z0-9]/g, '');
    const match = clean.match(/^R?(\d{1,2})(\d{2})(\d{2})$/);
    if (match) {
        const rack = match[1].padStart(2, '0');
        const col = match[2];
        const row = match[3];
        return `R${rack}${col}${row}`;
    }
    return clean;
}

/**
 * isLocationCode - checks if scanned code looks like a rack slot location (e.g. R010101, R-01-01-01, R10101).
 */
function isLocationCode(code) {
    const normalized = normalizeLocationCode(code);
    return /^R\d{6}$/.test(normalized);
}

/**
 * isRackCode - checks if code is a rack identifier (e.g., R01, R-01, R1, R-5, R05).
 */
function isRackCode(code) {
    if (!code) return false;
    const clean = String(code).toUpperCase().replace(/[^A-Z0-9]/g, '');
    return /^R?\d{1,2}$/.test(clean);
}

/**
 * handleRackScan - smart scanner router for rack view.
 * Detects whether the scanned code is a location or pallet and routes accordingly.
 * Flow: ① Scan location → opens slot detail, ② Scan pallet → verifies on rack.
 */

function clearSkaner() {
    document.getElementById('lokalizacjaInput').value = '';
    document.getElementById('resultsContainer').style.display = 'none';
    document.getElementById('rackContainer').style.display = 'none';
    document.getElementById('locationSearchCard').style.display = 'block';
    localStorage.removeItem('lastInventoryLoc');
    localStorage.removeItem('lastInventoryRack');
    
    // Ukryj dolny baner zakończenia
    const banner = document.getElementById('floatingFinishBanner');
    if (banner) banner.style.display = 'none';
    
    document.getElementById('lokalizacjaInput').focus();
}

function openInstructionsModal() {
    document.getElementById('instructionsModal').style.display = 'flex';
}
function closeInstructionsModal() {
    document.getElementById('instructionsModal').style.display = 'none';
}
// Close instructions modal when clicking backdrop
document.getElementById('instructionsModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('instructionsModal')) {
        closeInstructionsModal();
    }
});

// --- Dodatkowe funkcje --- 


function highlightAndFocusCard(card) {
    card.style.outline = '4px solid #10b981';
    card.style.transform = 'scale(1.02)';
    card.scrollIntoView({behavior: 'smooth', block: 'center'});
    
    setTimeout(() => {
        card.style.outline = 'none';
        card.style.transform = 'none';
    }, 2000);
    
    const weightInput = card.querySelector('.actual-weight-input') || card.querySelector('.slot-weight-input');
    if (weightInput) {
        setTimeout(() => weightInput.focus(), 300);
    }
}

/**
 * attachScannerAutoEnter - automatically triggers action on Enter, barcode scanner input stream, or paste.
 * Supports:
 * - Enter key on keydown and keyup
 * - Automatic detection on barcode scanner rapid input (instant on slot/SSCC format or ~250ms debounce)
 * - Paste events
 */
function attachScannerAutoEnter(inputElementOrId, callback, options = {}) {
    const input = typeof inputElementOrId === 'string' ? document.getElementById(inputElementOrId) : inputElementOrId;
    if (!input || input._scannerAutoEnterAttached) return;
    input._scannerAutoEnterAttached = true;

    let scanTimer = null;
    let lastSubmitTime = 0;
    const minLength = options.minLength || 2;
    const debounceMs = options.debounceMs || 250;

    function triggerSubmit() {
        if (scanTimer) {
            clearTimeout(scanTimer);
            scanTimer = null;
        }
        const now = Date.now();
        if (now - lastSubmitTime < 150) return; // Prevent double trigger within 150ms
        
        const val = input.value.trim();
        if (!val || (options.acceptCode && !options.acceptCode(val))) return;
        lastSubmitTime = now;
        input.value = '';
        callback(val);
    }


    // 1. Enter key via keydown
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.keyCode === 13 || e.which === 13) {
            e.preventDefault();
            e.stopPropagation();
            triggerSubmit();
        }
    });

    // 2. Enter key via keyup fallback (for Android / Zebra DataWedge)
    input.addEventListener('keyup', (e) => {
        if (e.key === 'Enter' || e.keyCode === 13 || e.which === 13) {
            e.preventDefault();
            e.stopPropagation();
            if (input.value.trim()) {
                triggerSubmit();
            }
        }
    });

    // 3. Barcode scanner typing (stream of characters without Enter)
    input.addEventListener('input', () => {
        if (scanTimer) clearTimeout(scanTimer);
        const val = input.value.trim();
        if (!val || val.length < minLength || (options.acceptCode && !options.acceptCode(val))) return;

        // Instant auto-enter when completed format is detected:
        // - Rack slot code: R010101 (7 chars) or R-01-01-01 (10 chars)
        // - Full SSCC: 18-20 digits
        const isFullLoc = isLocationCode(val) || /^R\d{2}-\d{2}-\d{2}$/i.test(val);
        const digitsOnly = val.replace(/\D/g, '');
        const isFullSSCC = digitsOnly.length >= 18;

        if (isFullLoc || isFullSSCC) {
            scanTimer = setTimeout(triggerSubmit, 40);
            return;
        }

        scanTimer = setTimeout(triggerSubmit, debounceMs);
    });

    // 4. Paste event
    input.addEventListener('paste', () => {
        setTimeout(triggerSubmit, 40);
    });
}


function parseTapeDecimal(raw) {
    if (raw === null || raw === undefined) return NaN;
    const cleaned = String(raw).trim().replace(/\s+/g, '').replace(',', '.');
    if (!cleaned) return NaN;
    return parseFloat(cleaned);
}

function getTapeBagWeightKg(nazwa) {
    const key = String(nazwa || '').trim().toLowerCase();
    if (!key) return null;
    const map = (window.INVENTORY_CONFIG && window.INVENTORY_CONFIG.tapeWeights) || {};
    const val = map[key];
    return (val !== undefined && val !== null && Number(val) > 0) ? Number(val) : null;
}

function isTapePallet(p) {
    if (!p) return false;
    const pkg = String(p.typ_opakowania || '').toLowerCase();
    if (pkg.includes('taśm') || pkg.includes('tasm')) return true;
    const typ = String(p.typ_palety || p.typ || '').toLowerCase();
    if (typ.includes('opakowanie') && getTapeBagWeightKg(p.nazwa) !== null) return true;
    return false;
}

async function saveSingleTapeBagWeight(nazwa, bagWeightKg) {
    const url = window.INVENTORY_CONFIG && window.INVENTORY_CONFIG.url_tape_conversions;
    if (!url || !nazwa) return false;
    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ nazwa: nazwa, waga_worka_kg: bagWeightKg })
        });
        const data = await resp.json();
        if (data.success && data.map) {
            if (window.INVENTORY_CONFIG) {
                window.INVENTORY_CONFIG.tapeWeights = data.map;
            }
            window.dispatchEvent(new CustomEvent('tapeWeightsUpdated', { detail: data.map }));
            return true;
        }
        safeToast(data.message || 'Nie udało się zapisać wagi worka', 'error');
        return false;
    } catch (err) {
        safeToast('Błąd połączenia przy zapisie wagi worka', 'error');
        return false;
    }
}

function mountTapeConverterWidget(containerEl, pallet, targetQtyInput, targetUnitSelect, options = {}) {
    if (!containerEl || !pallet || !targetQtyInput) return null;
    const savedBagKg = getTapeBagWeightKg(pallet.nazwa);
    const disabledAttr = options.disabled ? 'disabled' : '';

    containerEl.innerHTML = `
        <div class="tape-conv-box" style="background: #eff6ff; border: 1.5px solid #bfdbfe; border-radius: 12px; padding: 10px 12px; margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap;">
                <span style="font-size: 11px; font-weight: 800; color: #1d4ed8; text-transform: uppercase; display: flex; align-items: center; gap: 4px;">
                    <span class="material-icons" style="font-size: 15px;">calculate</span> Przelicznik taśmy (kg → szt)
                </span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <button type="button" class="tape-toggle-split-btn" ${disabledAttr}
                            style="background: white; border: 1px solid #93c5fd; color: #1d4ed8; border-radius: 8px; padding: 3px 8px; font-size: 11px; font-weight: 800; cursor: pointer; display: flex; align-items: center; gap: 3px;">
                        <span class="material-icons" style="font-size: 14px;">call_split</span> Rozbij na rolki
                    </button>
                    <button type="button" onclick="openTapeConverterModal()" style="background: none; border: none; color: #2563eb; font-size: 11px; font-weight: 700; cursor: pointer; text-decoration: underline; padding: 0;">Wszystkie taśmy</button>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                <div class="tape-single-kg-wrap">
                    <label style="display: block; font-size: 10px; font-weight: 800; color: #475569; margin-bottom: 3px; text-transform: uppercase;">Waga rolki / palety (kg)</label>
                    <input type="text" inputmode="decimal" class="tape-roll-kg-input" ${disabledAttr} placeholder="np. 500"
                           style="width: 100%; box-sizing: border-box; border: 2px solid #3b82f6; border-radius: 10px; padding: 8px 10px; font-size: 16px; font-weight: 800; color: #0f172a; background: white; outline: none;">
                </div>
                <div>
                    <label style="display: block; font-size: 10px; font-weight: 800; color: #475569; margin-bottom: 3px; text-transform: uppercase;">Waga 1 worka (kg)</label>
                    <div style="display: flex; gap: 4px;">
                        <input type="text" inputmode="decimal" class="tape-bag-kg-input" ${disabledAttr} value="${savedBagKg !== null ? savedBagKg : ''}" placeholder="np. 0.150"
                               style="width: 100%; min-width: 0; box-sizing: border-box; border: 1.5px solid #93c5fd; border-radius: 10px; padding: 8px 8px; font-size: 14px; font-weight: 800; color: #0f172a; background: white; outline: none;">
                        <button type="button" class="tape-save-bag-btn" ${disabledAttr} title="Zapisz wagę 1 worka dla tej taśmy"
                                style="background: #2563eb; color: white; border: none; border-radius: 10px; padding: 0 9px; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                            <span class="material-icons" style="font-size: 16px;">save</span>
                        </button>
                    </div>
                </div>
            </div>
            <div class="tape-split-panel" style="display: none; margin-top: 10px; padding-top: 8px; border-top: 1px dashed #93c5fd;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-size: 11px; font-weight: 800; color: #1e40af; text-transform: uppercase;">Pojedyncze rolki (kg):</span>
                    <button type="button" class="tape-add-roll-btn" ${disabledAttr}
                            style="background: #2563eb; color: white; border: none; border-radius: 8px; padding: 4px 10px; font-size: 11px; font-weight: 800; cursor: pointer; display: flex; align-items: center; gap: 3px;">
                        <span class="material-icons" style="font-size: 14px;">add</span> Dodaj rolkę
                    </button>
                </div>
                <div class="tape-rolls-list" style="display: flex; flex-direction: column; gap: 6px;"></div>
                <div style="margin-top: 6px; font-size: 10px; color: #475569; font-weight: 600;">
                    Rolka #1 zostaje pod obecnym SSCC, każda kolejna rolka dostanie własny kod OPK w inwentaryzacji i magazynie.
                </div>
            </div>
            <div class="tape-conv-result" style="margin-top: 7px; font-size: 12px; font-weight: 700; color: #1e40af;"></div>
        </div>
    `;

    const rollInput = containerEl.querySelector('.tape-roll-kg-input');
    const singleWrap = containerEl.querySelector('.tape-single-kg-wrap');
    const bagInput = containerEl.querySelector('.tape-bag-kg-input');
    const saveBagBtn = containerEl.querySelector('.tape-save-bag-btn');
    const toggleSplitBtn = containerEl.querySelector('.tape-toggle-split-btn');
    const splitPanel = containerEl.querySelector('.tape-split-panel');
    const addRollBtn = containerEl.querySelector('.tape-add-roll-btn');
    const rollsListEl = containerEl.querySelector('.tape-rolls-list');
    const resultEl = containerEl.querySelector('.tape-conv-result');

    let splitMode = false;
    let rollValues = ['', ''];

    function renderSplitRolls() {
        const bagKg = parseTapeDecimal(bagInput.value);
        rollsListEl.innerHTML = rollValues.map((val, idx) => {
            const kg = parseTapeDecimal(val);
            const pcsText = (isFinite(kg) && kg > 0 && isFinite(bagKg) && bagKg > 0)
                ? `= ${Math.round(kg / bagKg).toLocaleString('pl-PL')} szt`
                : '—';
            return `
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="font-size: 11px; font-weight: 800; color: #475569; width: 54px; flex-shrink: 0;">Rolka #${idx + 1}</span>
                    <input type="text" inputmode="decimal" class="tape-split-roll-input" data-roll-idx="${idx}" ${disabledAttr}
                           value="${String(val || '').replace(/"/g, '&quot;')}" placeholder="kg..."
                           style="flex: 1; min-width: 0; border: 1.5px solid #3b82f6; border-radius: 8px; padding: 6px 8px; font-size: 14px; font-weight: 800; background: white; outline: none;">
                    <span class="tape-split-roll-pcs" style="font-size: 12px; font-weight: 800; color: #059669; min-width: 78px; text-align: right;">${pcsText}</span>
                    ${rollValues.length > 2 ? `<button type="button" class="tape-remove-roll-btn" data-roll-idx="${idx}" ${disabledAttr} style="background: #fee2e2; color: #dc2626; border: none; border-radius: 8px; width: 28px; height: 28px; font-weight: 900; cursor: pointer; flex-shrink: 0;">&times;</button>` : ''}
                </div>
            `;
        }).join('');

        rollsListEl.querySelectorAll('.tape-split-roll-input').forEach(inp => {
            inp.addEventListener('input', () => {
                const idx = parseInt(inp.dataset.rollIdx, 10);
                rollValues[idx] = inp.value;
                const rowPcs = inp.parentElement && inp.parentElement.querySelector('.tape-split-roll-pcs');
                const kg = parseTapeDecimal(inp.value);
                const bKg = parseTapeDecimal(bagInput.value);
                if (rowPcs) {
                    rowPcs.textContent = (isFinite(kg) && kg > 0 && isFinite(bKg) && bKg > 0)
                        ? `= ${Math.round(kg / bKg).toLocaleString('pl-PL')} szt`
                        : '—';
                }
                recalc();
            });
            inp.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const idx = parseInt(inp.dataset.rollIdx, 10);
                    const nextInp = rollsListEl.querySelector(`.tape-split-roll-input[data-roll-idx="${idx + 1}"]`);
                    if (nextInp) {
                        nextInp.focus();
                    } else if (typeof options.onEnter === 'function') {
                        options.onEnter();
                    }
                }
            });
        });

        rollsListEl.querySelectorAll('.tape-remove-roll-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.rollIdx, 10);
                if (rollValues.length > 2) {
                    rollValues.splice(idx, 1);
                    renderSplitRolls();
                    recalc();
                }
            });
        });
    }

    function getSplitRollsSzt() {
        if (!splitMode) return null;
        const bagKg = parseTapeDecimal(bagInput.value);
        if (!isFinite(bagKg) || bagKg <= 0) {
            return { error: 'Wpisz wagę 1 worka (kg), aby przeliczyć rolki.' };
        }
        const filled = rollValues
            .map((v, i) => ({ idx: i + 1, raw: String(v || '').trim(), kg: parseTapeDecimal(v) }))
            .filter(r => r.raw !== '');
        if (filled.length < 2) {
            return { error: 'Wpisz wagę (kg) dla co najmniej 2 rolek albo wyłącz rozbijanie.' };
        }
        const result = [];
        for (const r of filled) {
            if (!isFinite(r.kg) || r.kg <= 0) {
                return { error: `Podaj poprawną wagę > 0 kg dla rolki #${r.idx}.` };
            }
            const pcs = Math.round(r.kg / bagKg);
            if (pcs <= 0) {
                return { error: `Przeliczona ilość dla rolki #${r.idx} wynosi 0 szt.` };
            }
            result.push(pcs);
        }
        return result;
    }

    function recalc() {
        const bagKg = parseTapeDecimal(bagInput.value);

        if (splitMode) {
            if (!isFinite(bagKg) || bagKg <= 0) {
                resultEl.style.color = '#dc2626';
                resultEl.textContent = 'Najpierw wpisz wagę 1 worka w kg (np. 0.150).';
                return;
            }
            let totalKg = 0;
            let totalPcs = 0;
            let validCount = 0;
            for (const v of rollValues) {
                const kg = parseTapeDecimal(v);
                if (isFinite(kg) && kg > 0) {
                    totalKg += kg;
                    totalPcs += Math.round(kg / bagKg);
                    validCount += 1;
                }
            }
            if (validCount > 0) {
                targetQtyInput.value = String(totalPcs);
                if (targetUnitSelect) targetUnitSelect.value = 'szt';
                targetQtyInput.dispatchEvent(new Event('input', { bubbles: true }));
                resultEl.style.color = validCount >= 2 ? '#059669' : '#b45309';
                resultEl.innerHTML = `Razem: <strong>${validCount} ${validCount === 1 ? 'rolka' : (validCount < 5 ? 'rolki' : 'rolek')}</strong> | ${Math.round(totalKg * 100) / 100} kg → <strong>${totalPcs.toLocaleString('pl-PL')} szt</strong>`;
            } else {
                resultEl.style.color = '#475569';
                resultEl.textContent = `Wpisz wagę każdej rolki w kg (dzielnik: ${bagKg} kg/worek).`;
            }
            return;
        }

        const rollKg = parseTapeDecimal(rollInput.value);

        if (rollInput.value.trim() === '') {
            if (!isFinite(bagKg) || bagKg <= 0) {
                resultEl.style.color = '#b45309';
                resultEl.textContent = 'Wpisz wagę 1 worka (kg) dla tej taśmy, np. 0.150.';
            } else {
                resultEl.style.color = '#475569';
                resultEl.textContent = `Wpisz wagę w kg — system podzieli przez ${bagKg} kg/worek.`;
            }
            return;
        }

        if (!isFinite(rollKg) || rollKg < 0) {
            resultEl.style.color = '#dc2626';
            resultEl.textContent = 'Podaj poprawną wagę w kg.';
            return;
        }

        if (!isFinite(bagKg) || bagKg <= 0) {
            resultEl.style.color = '#dc2626';
            resultEl.textContent = 'Najpierw wpisz wagę 1 worka w kg (np. 0.150).';
            return;
        }

        const pcs = rollKg === 0 ? 0 : Math.round(rollKg / bagKg);
        targetQtyInput.value = String(pcs);
        if (targetUnitSelect) {
            targetUnitSelect.value = 'szt';
        }
        targetQtyInput.dispatchEvent(new Event('input', { bubbles: true }));
        resultEl.style.color = '#059669';
        resultEl.innerHTML = `= <strong>${pcs.toLocaleString('pl-PL')} szt</strong> (${rollKg} kg ÷ ${bagKg} kg)`;
    }

    if (toggleSplitBtn) {
        toggleSplitBtn.addEventListener('click', () => {
            splitMode = !splitMode;
            splitPanel.style.display = splitMode ? 'block' : 'none';
            if (singleWrap) singleWrap.style.opacity = splitMode ? '0.45' : '1';
            rollInput.disabled = splitMode || Boolean(options.disabled);
            toggleSplitBtn.style.background = splitMode ? '#1d4ed8' : 'white';
            toggleSplitBtn.style.color = splitMode ? 'white' : '#1d4ed8';
            toggleSplitBtn.innerHTML = splitMode
                ? '<span class="material-icons" style="font-size: 14px;">close</span> Jedna paleta'
                : '<span class="material-icons" style="font-size: 14px;">call_split</span> Rozbij na rolki';
            if (splitMode) {
                if (rollInput.value.trim() && !rollValues[0]) {
                    rollValues[0] = rollInput.value.trim();
                }
                renderSplitRolls();
                const firstRoll = rollsListEl.querySelector('.tape-split-roll-input');
                if (firstRoll) firstRoll.focus();
            }
            recalc();
        });
    }

    if (addRollBtn) {
        addRollBtn.addEventListener('click', () => {
            rollValues.push('');
            renderSplitRolls();
            const inputs = rollsListEl.querySelectorAll('.tape-split-roll-input');
            if (inputs.length) inputs[inputs.length - 1].focus();
        });
    }

    rollInput.addEventListener('input', recalc);
    bagInput.addEventListener('input', () => {
        if (splitMode) renderSplitRolls();
        recalc();
    });

    rollInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            recalc();
            if (typeof options.onEnter === 'function') {
                options.onEnter();
            }
        }
    });

    if (saveBagBtn) {
        saveBagBtn.addEventListener('click', async () => {
            const bagKg = parseTapeDecimal(bagInput.value);
            if (!isFinite(bagKg) || bagKg <= 0) {
                safeToast('Wpisz poprawną wagę 1 worka > 0 (np. 0.150)', 'error');
                bagInput.focus();
                return;
            }
            saveBagBtn.disabled = true;
            const ok = await saveSingleTapeBagWeight(pallet.nazwa, bagKg);
            saveBagBtn.disabled = false;
            if (ok) {
                safeToast(`Zapisano ${bagKg} kg/worek dla: ${pallet.nazwa}`, 'success');
                if (splitMode) renderSplitRolls();
                recalc();
            }
        });
    }

    const onGlobalUpdate = () => {
        if (!document.body.contains(containerEl)) {
            window.removeEventListener('tapeWeightsUpdated', onGlobalUpdate);
            return;
        }
        const updated = getTapeBagWeightKg(pallet.nazwa);
        if (updated !== null) {
            bagInput.value = String(updated);
            if (splitMode) renderSplitRolls();
            recalc();
        }
    };
    window.addEventListener('tapeWeightsUpdated', onGlobalUpdate);

    recalc();
    const api = { rollInput, bagInput, recalc, getSplitRollsSzt };
    containerEl._tapeWidget = api;
    return api;
}



