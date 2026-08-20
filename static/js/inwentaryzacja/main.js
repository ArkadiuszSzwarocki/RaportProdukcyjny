function handleRackScan(code) {
    if (!code) return;
    code = code.trim().toUpperCase();
    const normalized = normalizeLocationCode(code);
    const rackPrefix = currentRackPrefix ? normalizeRackPrefix(currentRackPrefix) : '';
    
    // 1. Location code on current rack (e.g. R010101 while viewing R01) → open slot detail
    if (isLocationCode(normalized) && rackPrefix && normalized.startsWith(rackPrefix)) {
        safeToast('📍 Otwieram gniazdo ' + normalized, 'info');
        highlightAndOpenSlot(normalized);
        return;
    }
    
    // 2. Different rack code (e.g., R05, R-05, R5) → load new rack
    if (isRackCode(code)) {
        const targetRack = normalizeRackPrefix(code);
        if (targetRack !== rackPrefix) {
            safeToast('📍 Przechodzę do regału ' + targetRack, 'info');
            loadRack(targetRack);
            return;
        }
    }
    
    // 3. Location on a different rack (e.g., R050101 while viewing R01) → load rack + open slot
    if (isLocationCode(normalized)) {
        const newPrefix = normalized.substring(0, 3);
        safeToast('📍 Przechodzę do gniazda ' + normalized, 'info');
        loadRack(newPrefix, normalized);
        return;
    }
    
    // 4. Otherwise → treat as pallet code, verify on rack
    verifyPalletSSCCRack(code);
}

/**
 * handleDetailScan - smart scanner router for slot detail modal.
 * If a location is scanned, switches directly to the new slot.
 * If a pallet is scanned, verifies it in the current slot.
 */
function handleDetailScan(code) {
    if (!code) return;
    code = code.trim().toUpperCase();
    const normalized = normalizeLocationCode(code);
    const rackPrefix = currentRackPrefix ? normalizeRackPrefix(currentRackPrefix) : '';
    
    // 1. Location on current rack → switch directly to new slot
    if (isLocationCode(normalized) && rackPrefix && normalized.startsWith(rackPrefix)) {
        safeToast('📍 Przechodzę do gniazda ' + normalized, 'info');
        highlightAndOpenSlot(normalized);
        return;
    }
    
    // 2. Different rack code (e.g. R05, R-05) → close detail, load new rack
    if (isRackCode(code)) {
        closeDetail();
        const targetRack = normalizeRackPrefix(code);
        safeToast('📍 Przechodzę do regału ' + targetRack, 'info');
        loadRack(targetRack);
        return;
    }
    
    // 3. Location on a different rack → close detail, load rack + open slot
    if (isLocationCode(normalized)) {
        closeDetail();
        const newPrefix = normalized.substring(0, 3);
        safeToast('📍 Przechodzę do gniazda ' + normalized, 'info');
        loadRack(newPrefix, normalized);
        return;
    }
    
    // 4. Pallet code → verify in current slot
    verifyPalletSSCC(code, 'detail');
}

/**
 * refocusRackScanner - re-focuses the rack scanner input for continuous scanning.
 */
function refocusRackScanner() {
    setTimeout(() => {
        const modal = document.getElementById('slotDetail');
        const isModalOpen = modal && modal.style.display !== 'none';
        if (!isModalOpen) {
            const inp = document.getElementById('ssccVerifierInputRack');
            if (inp) inp.focus();
        }
    }, 100);
}

/**
 * refocusDetailScanner - re-focuses the detail scanner input.
 */
function refocusDetailScanner() {
    setTimeout(() => {
        const modal = document.getElementById('slotDetail');
        const isModalOpen = modal && modal.style.display !== 'none';
        if (isModalOpen) {
            const inp = document.getElementById('ssccVerifierInputDetail');
            if (inp) inp.focus();
        }
    }, 100);
}


function initInventoryScannerListeners() {
    if (typeof attachScannerAutoEnter !== 'function') return;

    attachScannerAutoEnter('lokalizacjaInput', (code) => {
        searchLocation(code);
    });

    attachScannerAutoEnter('ssccVerifierInputRack', (code) => {
        handleRackScan(code);
    });

    attachScannerAutoEnter('ssccVerifierInputDetail', (code) => {
        handleDetailScan(code);
    });

    attachScannerAutoEnter('ssccVerifierInputResults', (code) => {
        verifyPalletSSCC(code, 'results');
    });

    attachScannerAutoEnter('blindSsccInput', (code) => {
        handleBlindSSCCScan(code);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initInventoryScannerListeners();

    const typeSelect = document.getElementById('newPalletType');
    if (typeSelect) {
        typeSelect.addEventListener('change', (e) => {
            const val = e.target.value;
            document.getElementById('newPalletUnit').value = (val === 'opakowanie') ? 'szt' : 'kg';
            
            const ssccInput = document.getElementById('newPalletSSCC');
            
            fetchProductNames(val);
        });
    }
});

// Also initialize on window load to ensure all dynamic elements are caught
window.addEventListener('load', () => {
    initInventoryScannerListeners();
});



