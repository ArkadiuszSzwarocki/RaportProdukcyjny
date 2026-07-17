function safeToast(msg, kind) {
    if (typeof showToast === 'function') {
        showToast(msg, kind || 'info');
    } else if (typeof AppDialog !== 'undefined') {
        AppDialog.alert(msg);
    }
}

/**
 * isLocationCode - checks if scanned code looks like a rack location.
 * Location codes: R followed by 4+ digits (e.g., R030101).
 */
function isLocationCode(code) {
    const normalized = code.replace(/-/g, '');
    return /^R\d{4,}$/.test(normalized);
}

/**
 * normalizeLocationCode - removes hyphens for consistent matching.
 */
function normalizeLocationCode(code) {
    return code.replace(/-/g, '');
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


