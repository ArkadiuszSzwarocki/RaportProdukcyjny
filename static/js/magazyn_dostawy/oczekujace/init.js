document.addEventListener('DOMContentLoaded', function () {
    ensureLocationSuggestionsList();

    const globalScannerInput = document.getElementById('globalScannerInput');
    if (globalScannerInput) {
        globalScannerInput.focus();

        // Klasyczny Enter ze skanera/klawiatury
        globalScannerInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                handleGlobalScannerSubmit();
            }
        });

        // Obsługa wklejania (np. Ctrl+V lub "Wklej" na telefonie)
        globalScannerInput.addEventListener('paste', function(event) {
            setTimeout(() => {
                handleGlobalScannerSubmit();
            }, 50);
        });

        // Opcjonalny auto-submit dla pełnych kodów SSCC (18 cyfr) lub po chwili nieaktywności
        let typingTimer;
        globalScannerInput.addEventListener('input', function(event) {
            const val = this.value.trim();
            if (!val) return;

            // Jeśli jesteśmy w trybie podawania lokalizacji, wywołaj autouzupełnianie
            if (activeTransferItem) {
                handleLocationSuggestInput(this);
            }

            // Jeśli to 18-znakowy SSCC, submituj od razu
            if (!activeTransferItem && val.length === 18 && /^\d+$/.test(val)) {
                handleGlobalScannerSubmit();
                return;
            }

            // W przeciwnym razie odczekaj 350ms żeby skaner zdążył wpisać całość
            clearTimeout(typingTimer);
            if (val.length > 3 && !activeTransferItem) {
                typingTimer = setTimeout(() => {
                    handleGlobalScannerSubmit();
                }, 350);
            }
        });

        // Handling Escape to cancel active scan
        globalScannerInput.addEventListener('keyup', function(event) {
            if (event.key === 'Escape' && activeTransferItem) {
                activeGlobalItemType = null;
                activeTransferItem = null;
                globalScannerInput.value = '';
                globalScannerInput.placeholder = "1. Zeskanuj paletę (SSCC) i naciśnij Enter";
                globalScannerInput.removeAttribute('list');
                updateGlobalScanHint('Anulowano skanowanie lokalizacji. Zeskanuj kolejną paletę.', 'error');
            }
        });
    }

    const wgWaga = document.getElementById('wgWaga');
    if (wgWaga) {
        wgWaga.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                const locInput = document.getElementById('wgLokalizacja');
                if (locInput) {
                    locInput.focus();
                }
            }
        });
    }

    const wgLokalizacja = document.getElementById('wgLokalizacja');
    if (wgLokalizacja) {
        wgLokalizacja.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                submitAcceptWG();
            }
        });
    }

    // Automatyczne odświeżanie co 15 sekund
    // Całkowicie ciche odświeżanie w tle (np. co 5 sekund),
    // niezbędne by zobaczyć dostawy dodane na innych komputerach
    setInterval(() => {
        performSilentRefresh();
    }, 5000);
});
