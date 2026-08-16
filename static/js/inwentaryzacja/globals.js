let currentLocationPallets = [];

/**
 * safeToast - wrapper for showing toast notifications.
 * Falls back to AppDialog.alert when showToast is unavailable.
 */

let currentPallets = [];
let lastLocation = '';
let rackData = {}; // Map location -> [items]
let currentRackPrefix = '';

// Load state on page load
window.addEventListener('load', () => {
    const currentSessionId = window.INVENTORY_CONFIG.sesjaId;
    const lastSessionId = localStorage.getItem('lastInventorySessionId');
    
    // Jeśli zmieniliśmy sesję, czyścimy stare zapamiętane lokalizacje
    if (lastSessionId !== currentSessionId) {
        localStorage.removeItem('lastInventoryLoc');
        localStorage.removeItem('lastInventoryRack');
        localStorage.setItem('lastInventorySessionId', currentSessionId);
    }

    const savedLoc = localStorage.getItem('lastInventoryLoc');
    const savedRack = localStorage.getItem('lastInventoryRack');
    
    fetchProductNames();

    if(savedRack) {
        document.getElementById('lokalizacjaInput').value = savedRack;
        document.getElementById('locationSearchCard').style.display = 'none';
        loadRack(savedRack);
    } else if(savedLoc) {
        document.getElementById('lokalizacjaInput').value = savedLoc;
        document.getElementById('locationSearchCard').style.display = 'none';
        searchLocation();
    } else {
        // Jeśli to nowa sesja i nie ma nic w localStorage, spróbuj automatycznie załadować obszar sesji
        const target = (window.INVENTORY_CONFIG.targetLokalizacja || "").trim().toUpperCase();
        if (target && target !== 'WSZYSTKO' && target !== 'WSZYSTKIE') {
            document.getElementById('lokalizacjaInput').value = target;
            document.getElementById('locationSearchCard').style.display = 'none';
            if (target.startsWith('R') && target.length >= 3 && target.length <= 4) {
                loadRack(target);
            } else {
                searchLocation();
            }
        } else {
            // Ukryj baner zakończenia na czystym ekranie wyszukiwania
            const banner = document.getElementById('floatingFinishBanner');
            if (banner) banner.style.display = 'none';
        }
    }
});




let currentBlindPallet = null;


let lookedUpPalletId = null;
let lookedUpSystemWeight = 0;
let lookupTimeout = null;


let currentMovePallet = null;
let currentMoveOriginalLoc = null;


let currentPrintPalletId = null;
let currentPrintPalletType = null;


