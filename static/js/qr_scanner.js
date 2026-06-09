/**
 * Universal QR Scanner using device camera
 * Supports: login QR codes, pallet labels, location codes
 * Uses html5-qrcode library
 */

class QRScanner {
    constructor(config = {}) {
        this.scanner = null;
        this.isScanning = false;
        this.config = {
            fps: 10,
            qrbox: { width: 250, height: 250 },
            aspectRatio: 1.0,
            ...config
        };
        this.onSuccess = config.onSuccess || this.defaultSuccessHandler.bind(this);
        this.onError = config.onError || this.defaultErrorHandler.bind(this);
    }

    async start(elementId) {
        if (this.isScanning) {
            console.warn('Scanner już działa');
            return;
        }

        try {
            // Dynamically load html5-qrcode if not already loaded
            if (typeof Html5Qrcode === 'undefined') {
                await this.loadHtml5QrcodeLibrary();
            }

            this.scanner = new Html5Qrcode(elementId);
            
            const config = {
                fps: this.config.fps,
                qrbox: this.config.qrbox,
                aspectRatio: this.config.aspectRatio
            };

            await this.scanner.start(
                { facingMode: "environment" }, // prefer back camera
                config,
                this.onSuccess,
                this.onError
            );

            this.isScanning = true;
            console.log('QR Scanner uruchomiony');
        } catch (err) {
            console.error('Błąd uruchamiania skanera:', err);
            this.showCameraError(err);
        }
    }

    async stop() {
        if (this.scanner && this.isScanning) {
            try {
                await this.scanner.stop();
                this.scanner.clear();
                this.isScanning = false;
                console.log('QR Scanner zatrzymany');
            } catch (err) {
                console.error('Błąd zatrzymywania skanera:', err);
            }
        }
    }

    defaultSuccessHandler(decodedText, decodedResult) {
        console.log('QR zeskanowany:', decodedText);
        // Override in config.onSuccess
    }

    defaultErrorHandler(errorMessage) {
        // Silent - too many errors during normal operation
    }

    showCameraError(err) {
        const errorMsg = document.getElementById('qr-scanner-error');
        if (errorMsg) {
            let message = 'Nie można uruchomić kamery. ';
            
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                message += 'Brak uprawnień do kamery. Sprawdź ustawienia przeglądarki.';
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                message += 'Nie znaleziono kamery w urządzeniu.';
            } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
                message += 'Kamera jest używana przez inną aplikację.';
            } else {
                message += 'Błąd: ' + (err.message || err);
            }
            
            errorMsg.textContent = message;
            errorMsg.style.display = 'block';
        }
    }

    async loadHtml5QrcodeLibrary() {
        return new Promise((resolve, reject) => {
            if (typeof Html5Qrcode !== 'undefined') {
                resolve();
                return;
            }

            const script = document.createElement('script');
            script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
            script.onload = () => resolve();
            script.onerror = () => reject(new Error('Nie udało się załadować biblioteki skanera QR'));
            document.head.appendChild(script);
        });
    }
}

// Global scanner instances
window.QRScanner = QRScanner;
window._activeQrScanner = null;

/**
 * Open QR scanner modal for any field
 */
window.openQrScannerModal = function(targetFieldId, mode = 'generic') {
    const modal = document.getElementById('modalQrCamera');
    if (!modal) {
        console.error('Modal QR Camera nie istnieje');
        return;
    }

    // Store target and mode
    window._qrScanTargetFieldId = targetFieldId;
    window._qrScanMode = mode;

    // Reset UI
    const resultDiv = document.getElementById('qr-scan-result');
    const errorDiv = document.getElementById('qr-scanner-error');
    const confirmBtn = document.getElementById('qr-confirm-btn');
    
    if (resultDiv) resultDiv.textContent = '';
    if (errorDiv) {
        errorDiv.textContent = '';
        errorDiv.style.display = 'none';
    }
    if (confirmBtn) confirmBtn.disabled = true;

    // Open modal
    if (typeof openModal === 'function') {
        openModal('modalQrCamera');
    } else {
        modal.showModal();
    }

    // Start scanner after modal animation
    setTimeout(() => startQrCamera(), 300);
};

/**
 * Start camera scanner
 */
window.startQrCamera = function() {
    if (window._activeQrScanner) {
        window._activeQrScanner.stop();
    }

    window._activeQrScanner = new QRScanner({
        onSuccess: (decodedText) => {
            handleQrScanSuccess(decodedText);
        }
    });

    window._activeQrScanner.start('qr-reader');
};

/**
 * Close QR scanner modal
 */
window.closeQrScannerModal = function() {
    if (window._activeQrScanner) {
        window._activeQrScanner.stop();
        window._activeQrScanner = null;
    }

    const modal = document.getElementById('modalQrCamera');
    if (modal) {
        if (typeof closeModal === 'function') {
            closeModal('modalQrCamera');
        } else {
            modal.close();
        }
    }
};

/**
 * Handle successful QR scan
 */
function handleQrScanSuccess(decodedText) {
    console.log('QR Scanned:', decodedText);

    // Stop scanner
    if (window._activeQrScanner) {
        window._activeQrScanner.stop();
    }

    // Show result
    const resultDiv = document.getElementById('qr-scan-result');
    if (resultDiv) {
        resultDiv.textContent = decodedText;
    }

    // Enable confirm button
    const confirmBtn = document.getElementById('qr-confirm-btn');
    if (confirmBtn) {
        confirmBtn.disabled = false;
    }

    // Auto-confirm after 500ms
    setTimeout(() => confirmQrScan(decodedText), 500);
}

/**
 * Confirm QR scan and apply to target
 */
window.confirmQrScan = function(decodedText) {
    const text = decodedText || document.getElementById('qr-scan-result')?.textContent;
    if (!text) return;

    const mode = window._qrScanMode || 'generic';
    const targetFieldId = window._qrScanTargetFieldId;

    // Close modal
    closeQrScannerModal();

    // Handle different modes
    if (mode === 'login') {
        handleLoginQrCode(text);
    } else if (mode === 'pallet') {
        handlePalletQrCode(text, targetFieldId);
    } else if (mode === 'location') {
        handleLocationQrCode(text, targetFieldId);
    } else {
        // Generic: fill target field
        const targetField = document.getElementById(targetFieldId);
        if (targetField) {
            targetField.value = text;
            targetField.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }
};

/**
 * Handle login QR code
 * Format: LOGIN:username:password or JSON with {login, haslo}
 */
function handleLoginQrCode(qrText) {
    try {
        let credentials = null;

        // Try JSON format first
        if (qrText.startsWith('{')) {
            const data = JSON.parse(qrText);
            if (data.login && data.haslo) {
                credentials = { login: data.login, haslo: data.haslo };
            }
        }
        // Try simple format: LOGIN:user:pass
        else if (qrText.startsWith('LOGIN:')) {
            const parts = qrText.split(':');
            if (parts.length >= 3) {
                credentials = { login: parts[1], haslo: parts[2] };
            }
        }

        if (credentials) {
            // Fill login form
            const loginField = document.getElementById('login') || document.querySelector('input[name="login"]');
            const passwordField = document.getElementById('haslo') || document.querySelector('input[name="haslo"]');

            if (loginField && passwordField) {
                loginField.value = credentials.login;
                passwordField.value = credentials.haslo;

                // Auto-submit after short delay
                setTimeout(() => {
                    const form = loginField.closest('form');
                    if (form) {
                        form.submit();
                    }
                }, 500);
            } else {
                alert('Nie znaleziono formularza logowania');
            }
        } else {
            alert('Nieprawidłowy format kodu QR logowania');
        }
    } catch (err) {
        console.error('Błąd przetwarzania QR logowania:', err);
        alert('Błąd odczytu kodu QR: ' + err.message);
    }
}

/**
 * Handle pallet/label QR code
 * Format: Pallet ID or barcode
 */
function handlePalletQrCode(qrText, targetFieldId) {
    const targetField = document.getElementById(targetFieldId);
    if (targetField) {
        targetField.value = qrText.trim().toUpperCase();
        targetField.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

/**
 * Handle location QR code
 * Format: Location code (e.g., R010101, A-B-01)
 */
function handleLocationQrCode(qrText, targetFieldId) {
    const locationCode = qrText.trim().toUpperCase();
    
    if (targetFieldId === 'usage_location_scan') {
        // Special handler for usage location
        const sel = document.getElementById('usage_surowiec_id');
        if (sel) {
            let matched = false;
            for (let i = 0; i < sel.options.length; i++) {
                if (sel.options[i].textContent.toUpperCase().indexOf(locationCode) !== -1) {
                    sel.selectedIndex = i;
                    matched = true;
                    break;
                }
            }
            if (!matched && typeof showAlert === 'function') {
                showAlert('Nie znaleziono palety dla lokalizacji: ' + locationCode);
            }
        }
    } else {
        // Generic location field
        const targetField = document.getElementById(targetFieldId);
        if (targetField) {
            targetField.value = locationCode;
            targetField.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window._activeQrScanner) {
        window._activeQrScanner.stop();
    }
});
