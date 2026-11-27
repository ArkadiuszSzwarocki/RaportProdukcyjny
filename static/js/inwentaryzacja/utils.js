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
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 8px;">
                <span style="font-size: 11px; font-weight: 800; color: #1d4ed8; text-transform: uppercase; display: flex; align-items: center; gap: 4px;">
                    <span class="material-icons" style="font-size: 15px;">calculate</span> Przelicznik taśmy (kg → szt)
                </span>
                <button type="button" onclick="openTapeConverterModal()" style="background: none; border: none; color: #2563eb; font-size: 11px; font-weight: 700; cursor: pointer; text-decoration: underline; padding: 0;">Wszystkie taśmy</button>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                <div>
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
            <div class="tape-conv-result" style="margin-top: 7px; font-size: 12px; font-weight: 700; color: #1e40af;"></div>
        </div>
    `;

    const rollInput = containerEl.querySelector('.tape-roll-kg-input');
    const bagInput = containerEl.querySelector('.tape-bag-kg-input');
    const saveBagBtn = containerEl.querySelector('.tape-save-bag-btn');
    const resultEl = containerEl.querySelector('.tape-conv-result');

    function recalc() {
        const rollKg = parseTapeDecimal(rollInput.value);
        const bagKg = parseTapeDecimal(bagInput.value);

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

    rollInput.addEventListener('input', recalc);
    bagInput.addEventListener('input', recalc);

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
            recalc();
        }
    };
    window.addEventListener('tapeWeightsUpdated', onGlobalUpdate);

    recalc();
    return { rollInput, bagInput, recalc };
}



