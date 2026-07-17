function handleRackScan(code) {
    if (!code) return;
    code = code.trim().toUpperCase();
    const normalized = normalizeLocationCode(code);
    
    // 1. Location on current rack → open slot detail
    if (currentRackPrefix && normalized.startsWith(currentRackPrefix) && normalized.length >= 6) {
        safeToast('📍 Otwieram gniazdo ' + normalized, 'info');
        highlightAndOpenSlot(normalized);
        return;
    }
    
    // 2. Different rack prefix (e.g., R05 while viewing R03) → load new rack
    if (/^R\d{1,2}$/.test(normalized) && normalized !== currentRackPrefix) {
        loadRack(normalized);
        return;
    }
    
    // 3. Location on a different rack (e.g., R050101) → load rack + open slot
    if (isLocationCode(normalized) && currentRackPrefix && !normalized.startsWith(currentRackPrefix)) {
        const newPrefix = normalized.substring(0, 3);
        safeToast('📍 Przechodzę do regału ' + newPrefix, 'info');
        loadRack(newPrefix);
        setTimeout(() => highlightAndOpenSlot(normalized), 600);
        return;
    }
    
    // 4. Otherwise → treat as pallet code, verify on rack
    verifyPalletSSCCRack(code);
}

/**
 * handleDetailScan - smart scanner router for slot detail modal.
 * If a location is scanned, closes current detail and opens new slot.
 * If a pallet is scanned, verifies it in the current slot.
 */

function handleDetailScan(code) {
    if (!code) return;
    code = code.trim().toUpperCase();
    const normalized = normalizeLocationCode(code);
    
    // 1. Location on current rack → close detail, open new slot
    if (currentRackPrefix && normalized.startsWith(currentRackPrefix) && normalized.length >= 6) {
        closeDetail();
        safeToast('📍 Przechodzę do gniazda ' + normalized, 'info');
        setTimeout(() => highlightAndOpenSlot(normalized), 200);
        return;
    }
    
    // 2. Different rack prefix → close detail, load new rack
    if (/^R\d{1,2}$/.test(normalized)) {
        closeDetail();
        loadRack(normalized);
        return;
    }
    
    // 3. Location on a different rack → close detail, load rack + open slot
    if (isLocationCode(normalized)) {
        closeDetail();
        const newPrefix = normalized.substring(0, 3);
        safeToast('📍 Przechodzę do regału ' + newPrefix, 'info');
        loadRack(newPrefix);
        setTimeout(() => highlightAndOpenSlot(normalized), 600);
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
        const inp = document.getElementById('ssccVerifierInputRack');
        if (inp) inp.focus();
    }, 500);
}

/**
 * refocusDetailScanner - re-focuses the detail scanner input.
 */

function refocusDetailScanner() {
    setTimeout(() => {
        const inp = document.getElementById('ssccVerifierInputDetail');
        if (inp) inp.focus();
    }, 500);
}


document.addEventListener('DOMContentLoaded', () => {
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


