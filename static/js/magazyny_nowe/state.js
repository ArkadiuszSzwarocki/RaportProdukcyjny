/**
 * Magazyny Nowe - Logika Interfejsu
 * Obsługuje filtrowanie, sortowanie, modale i operacje na paletach.
 */

// ---- STATE MANAGEMENT ----
let currentWarehouseId = 'all';
let currentSubWarehouseId = 'all';
let currentSearchQuery = '';
let currentPallet = {}; 
let scanBuffer = '';
let scanTimeout = null;

let currentFilteredItems = [];
let currentRenderedCount = 0;
const PAGE_SIZE = 100;

// ---- TOAST NOTIFICATIONS ----
function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:99999;display:flex;flex-direction:column;gap:10px;max-width:340px;';
        document.body.appendChild(container);
    }
    const colors = { success: '#10b981', error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' };
    const icons  = { success: 'check_circle', error: 'error', warning: 'warning', info: 'info' };
    const toast = document.createElement('div');
    toast.style.cssText = `background:${colors[type]||colors.info};color:#fff;padding:14px 18px;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,0.25);display:flex;align-items:center;gap:10px;font-size:14px;font-weight:600;opacity:0;transform:translateX(40px);transition:all 0.3s ease;`;
    toast.innerHTML = `<span class="material-icons" style="font-size:20px;">${icons[type]||icons.info}</span>${message}`;
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.style.opacity='1'; toast.style.transform='translateX(0)'; });
    setTimeout(() => {
        toast.style.opacity='0'; toast.style.transform='translateX(40px)';
        setTimeout(() => toast.remove(), 350);
    }, 4000);
}

// Funkcja synchronizująca stan z widokiem (DOM)
function syncStateFromDOM() {
    const checkedWh = document.querySelector('input[name="main_wh"]:checked');
    if (checkedWh) {
        currentWarehouseId = checkedWh.id.replace('radio-', '');
    }
    
    const checkedRack = document.querySelector('input[name="rack_select"]:checked');
    if (checkedRack) {
        currentSubWarehouseId = checkedRack.id.replace('rack-', '');
    }
    
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        currentSearchQuery = searchInput.value;
    }
    
    console.log("Zsynchronizowano stan z DOM:", { warehouse: currentWarehouseId, sub: currentSubWarehouseId });
}

// ---- SCANNER HANDLER ----
document.addEventListener('keydown', function(e) {
    if(e.key === 'Enter' && scanBuffer.length > 3) {
        handleScan(scanBuffer);
        scanBuffer = '';
    } else {
        if(e.key.length === 1) scanBuffer += e.key;
        clearTimeout(scanTimeout);
        scanTimeout = setTimeout(() => { scanBuffer = ''; }, 200); 
    }
});

function handleScan(barcode) {
    AppDialog.alert("Zeskanowano kod: " + barcode + ". Tutaj wdrożymy logikę rozpoznawania po ID z biblioteki.");
}


