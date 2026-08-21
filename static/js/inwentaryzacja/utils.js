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
        if (!val) return;
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
        if (!val || val.length < minLength) return;

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



