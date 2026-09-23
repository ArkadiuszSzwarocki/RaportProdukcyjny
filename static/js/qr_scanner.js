/**
 * Universal QR Scanner using device camera and native photo fallback
 * Supports: login QR codes, pallet labels, location codes
 * Compatible with all desktop and mobile browsers (iOS / Android)
 */

class QRScanner {
    constructor(config = {}) {
        this.scanner = null;
        this.isScanning = false;
        this.activeVideoTrack = null;
        this.torchSupported = false;
        this.isTorchOn = false;
        this.availableCameras = [];
        this.currentCameraIndex = 0;
        this.config = {
            fps: 15,
            aspectRatio: 1.0,
            ...config
        };
        this.onSuccess = config.onSuccess || this.defaultSuccessHandler.bind(this);
        this.onError = config.onError || this.defaultErrorHandler.bind(this);
    }

    async start(elementId) {
        if (this.isScanning) {
            console.warn('[QRScanner] Scanner already running');
            return;
        }

        const errorMsg = document.getElementById('qr-scanner-error');
        if (errorMsg) {
            errorMsg.style.display = 'none';
            errorMsg.innerHTML = '';
        }

        try {
            await this.loadHtml5QrcodeLibrary();

            const isMediaSupported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
            const isSecure = window.isSecureContext || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

            if (!isMediaSupported && !isSecure) {
                this.showInsecureContextError();
                return;
            }

            try {
                this.availableCameras = await Html5Qrcode.getCameras();
            } catch (camErr) {
                console.warn('[QRScanner] getCameras error:', camErr);
                this.availableCameras = [];
            }

            let cameraTarget = { facingMode: { ideal: "environment" } };
            
            if (this.availableCameras && this.availableCameras.length > 0) {
                const rearCamIndex = this.availableCameras.findIndex(c => 
                    /back|rear|tył|environment|otoczenie/i.test(c.label || '')
                );
                if (rearCamIndex !== -1) {
                    this.currentCameraIndex = rearCamIndex;
                    cameraTarget = this.availableCameras[rearCamIndex].id;
                } else {
                    this.currentCameraIndex = this.availableCameras.length - 1;
                    cameraTarget = this.availableCameras[this.currentCameraIndex].id;
                }

                const switchBtn = document.getElementById('qr-switch-cam-btn');
                if (switchBtn && this.availableCameras.length > 1) {
                    switchBtn.style.display = 'inline-flex';
                }
            }

            const formatsToSupport = [
                Html5QrcodeSupportedFormats.QR_CODE,
                Html5QrcodeSupportedFormats.DATA_MATRIX,
                Html5QrcodeSupportedFormats.CODE_128,
                Html5QrcodeSupportedFormats.CODE_39,
                Html5QrcodeSupportedFormats.EAN_13,
                Html5QrcodeSupportedFormats.EAN_8,
                Html5QrcodeSupportedFormats.UPC_A
            ];

            this.scanner = new Html5Qrcode(elementId, {
                formatsToSupport: formatsToSupport,
                verbose: false
            });

            const scanConfig = {
                fps: this.config.fps,
                qrbox: function(viewfinderWidth, viewfinderHeight) {
                    const minEdge = Math.min(viewfinderWidth, viewfinderHeight);
                    const boxSize = Math.floor(minEdge * 0.75);
                    return {
                        width: Math.max(boxSize, 160),
                        height: Math.max(boxSize, 160)
                    };
                },
                aspectRatio: this.config.aspectRatio,
                videoConstraints: {
                    facingMode: { ideal: "environment" }
                }
            };

            await this.scanner.start(
                cameraTarget,
                scanConfig,
                (decodedText, decodedResult) => {
                    this.onSuccess(decodedText, decodedResult);
                },
                (errorMessage) => {
                    this.onError(errorMessage);
                }
            );

            this.isScanning = true;
            console.log('[QRScanner] Started successfully');
            setTimeout(() => this.detectTrackFeatures(), 500);

        } catch (err) {
            console.error('[QRScanner] Start error:', err);
            this.showCameraError(err);
        }
    }

    detectTrackFeatures() {
        try {
            const videoElem = document.querySelector('#qr-reader video');
            if (!videoElem || !videoElem.srcObject) return;

            const tracks = videoElem.srcObject.getVideoTracks();
            if (!tracks || tracks.length === 0) return;

            this.activeVideoTrack = tracks[0];
            if (typeof this.activeVideoTrack.getCapabilities === 'function') {
                const caps = this.activeVideoTrack.getCapabilities();
                this.torchSupported = Boolean(caps.torch);
                const torchBtn = document.getElementById('qr-torch-btn');
                if (torchBtn) {
                    torchBtn.style.display = this.torchSupported ? 'inline-flex' : 'none';
                }
            }
        } catch (e) {
            console.warn('[QRScanner] Track capabilities detection error:', e);
        }
    }

    async toggleTorch() {
        if (!this.activeVideoTrack || !this.torchSupported) return;
        try {
            this.isTorchOn = !this.isTorchOn;
            await this.activeVideoTrack.applyConstraints({
                advanced: [{ torch: this.isTorchOn }]
            });
            const torchBtn = document.getElementById('qr-torch-btn');
            if (torchBtn) {
                torchBtn.innerHTML = this.isTorchOn ? '🔦 Latarka (WŁ)' : '💡 Latarka';
                torchBtn.style.background = this.isTorchOn ? '#f59e0b' : 'rgba(15, 23, 42, 0.75)';
                torchBtn.style.color = this.isTorchOn ? '#000000' : '#f8fafc';
            }
        } catch (err) {
            console.warn('[QRScanner] Torch toggle error:', err);
        }
    }

    async switchCamera() {
        if (!this.availableCameras || this.availableCameras.length < 2) return;
        if (!this.scanner || !this.isScanning) return;

        try {
            await this.scanner.stop();
            this.isScanning = false;

            this.currentCameraIndex = (this.currentCameraIndex + 1) % this.availableCameras.length;
            const nextCamId = this.availableCameras[this.currentCameraIndex].id;

            const scanConfig = {
                fps: this.config.fps,
                qrbox: function(w, h) {
                    const minEdge = Math.min(w, h);
                    const size = Math.floor(minEdge * 0.75);
                    return { width: Math.max(size, 160), height: Math.max(size, 160) };
                },
                aspectRatio: this.config.aspectRatio
            };

            await this.scanner.start(
                nextCamId,
                scanConfig,
                (decodedText, decodedResult) => this.onSuccess(decodedText, decodedResult),
                (errorMessage) => this.onError(errorMessage)
            );

            this.isScanning = true;
            setTimeout(() => this.detectTrackFeatures(), 500);
        } catch (err) {
            console.error('[QRScanner] Switch camera error:', err);
        }
    }

    async stop() {
        if (this.scanner && this.isScanning) {
            try {
                if (this.activeVideoTrack && this.isTorchOn) {
                    try {
                        await this.activeVideoTrack.applyConstraints({ advanced: [{ torch: false }] });
                    } catch (_) {}
                    this.isTorchOn = false;
                }
                await this.scanner.stop();
                this.scanner.clear();
                this.isScanning = false;
                this.activeVideoTrack = null;
                console.log('[QRScanner] Stopped successfully');
            } catch (err) {
                console.warn('[QRScanner] Stop warning:', err);
            }
        }
    }

    defaultSuccessHandler(decodedText) {
        console.log('[QRScanner] Scanned:', decodedText);
    }

    defaultErrorHandler() {}

    showInsecureContextError() {
        const errorMsg = document.getElementById('qr-scanner-error');
        if (!errorMsg) return;

        const origin = window.location.origin;
        errorMsg.innerHTML = `
            <div style="font-size:0.85rem; line-height:1.45;">
                <strong style="color:#b91c1c;">⚠️ Kamera na żywo wymaga zezwolenia dla adresu IP</strong><br>
                Przeglądarki mobilne blokują bezpośredni strumień kamery dla HTTP w sieci LAN.<br>
                <div style="margin-top:6px; background:#fff; padding:6px 10px; border-radius:6px; border:1px solid #fecaca; font-size:0.8rem;">
                    👉 <strong>Kliknij niebieski przycisk poniżej:</strong> <em>"Użyj aparatu systemowego"</em> (działa natychmiast bez konfiguracji).
                </div>
            </div>
        `;
        errorMsg.style.display = 'block';
    }

    showCameraError(err) {
        const errorMsg = document.getElementById('qr-scanner-error');
        if (!errorMsg) return;

        let message = '';
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
            message = `
                <div>
                    <strong style="color: #b91c1c;">⛔ Brak uprawnień do kamery</strong><br>
                    <span>Kliknij kłódkę/ikonę obok adresu strony w telefonie i włącz <strong>Aparat / Kamera: Zezwalaj</strong>.</span>
                </div>
            `;
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
            message = '<strong>📷 Nie wykryto aparatu</strong> w tym urządzeniu.';
        } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
            message = '<strong>⚠️ Kamera zajęta</strong> przez inną aplikację.';
        } else {
            message = '<strong>Informacja:</strong> ' + (err.message || 'Wybierz zdjęcie lub użyj aparatu systemowego poniżej.');
        }

        errorMsg.innerHTML = message;
        errorMsg.style.display = 'block';
    }

    async loadHtml5QrcodeLibrary() {
        if (typeof Html5Qrcode !== 'undefined') {
            return Promise.resolve();
        }

        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
            script.onload = () => resolve();
            script.onerror = () => reject(new Error('Nie udało się pobrać biblioteki skanera QR.'));
            document.head.appendChild(script);
        });
    }
}

// Global scope initialization
window.QRScanner = QRScanner;
window._activeQrScanner = null;

/**
 * Open QR scanner modal
 */
window.openQrScannerModal = function(targetFieldId, mode = 'generic') {
    const modal = document.getElementById('modalQrCamera');
    if (!modal) {
        console.error('Modal QR Camera not found');
        return;
    }

    window._qrScanTargetFieldId = targetFieldId;
    window._qrScanMode = mode;

    const resultDiv = document.getElementById('qr-scan-result');
    const resultBox = document.getElementById('qr-scan-result-container');
    const errorDiv = document.getElementById('qr-scanner-error');
    const confirmBtn = document.getElementById('qr-confirm-btn');
    const manualInput = document.getElementById('qr-manual-input');
    const torchBtn = document.getElementById('qr-torch-btn');
    const switchBtn = document.getElementById('qr-switch-cam-btn');
    
    if (resultDiv) resultDiv.textContent = '';
    if (resultBox) resultBox.style.display = 'none';
    if (errorDiv) {
        errorDiv.textContent = '';
        errorDiv.style.display = 'none';
    }
    if (confirmBtn) confirmBtn.disabled = true;
    if (manualInput) manualInput.value = '';
    if (torchBtn) torchBtn.style.display = 'none';
    if (switchBtn) switchBtn.style.display = 'none';

    if (typeof openModal === 'function') {
        openModal('modalQrCamera');
    } else if (typeof modal.showModal === 'function') {
        try {
            modal.showModal();
        } catch (e) {
            modal.setAttribute('open', '');
        }
    } else {
        modal.style.display = 'block';
    }

    setTimeout(() => window.startQrCamera(), 250);
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
 * Torch toggle
 */
window.toggleQrScannerTorch = function() {
    if (window._activeQrScanner) {
        window._activeQrScanner.toggleTorch();
    }
};

/**
 * Camera switch
 */
window.switchQrScannerCamera = function() {
    if (window._activeQrScanner) {
        window._activeQrScanner.switchCamera();
    }
};

/**
 * Close modal
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
        } else if (typeof modal.close === 'function') {
            try {
                modal.close();
            } catch (e) {
                modal.removeAttribute('open');
            }
        } else {
            modal.style.display = 'none';
        }
    }
};

/**
 * Native photo capture fallback (works 100% on any mobile device)
 */
window.handleQrNativePhotoFile = async function(fileInput) {
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) return;

    const file = fileInput.files[0];
    const errorDiv = document.getElementById('qr-scanner-error');
    if (errorDiv) {
        errorDiv.style.display = 'block';
        errorDiv.innerHTML = '<span style="color:#0284c7;">🔍 Analizuję zdjęcie kodu QR...</span>';
    }

    try {
        if (typeof Html5Qrcode === 'undefined') {
            const script = document.createElement('script');
            script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
            await new Promise((res, rej) => {
                script.onload = res;
                script.onerror = rej;
                document.head.appendChild(script);
            });
        }

        let tempScannerDiv = document.getElementById('qr-temp-file-scanner');
        if (!tempScannerDiv) {
            tempScannerDiv = document.createElement('div');
            tempScannerDiv.id = 'qr-temp-file-scanner';
            tempScannerDiv.style.display = 'none';
            document.body.appendChild(tempScannerDiv);
        }

        const fileScanner = new Html5Qrcode('qr-temp-file-scanner', {
            formatsToSupport: [
                Html5QrcodeSupportedFormats.QR_CODE,
                Html5QrcodeSupportedFormats.DATA_MATRIX,
                Html5QrcodeSupportedFormats.CODE_128,
                Html5QrcodeSupportedFormats.CODE_39,
                Html5QrcodeSupportedFormats.EAN_13,
                Html5QrcodeSupportedFormats.EAN_8,
                Html5QrcodeSupportedFormats.UPC_A
            ],
            verbose: false
        });

        const decodedText = await fileScanner.scanFile(file, false);
        if (decodedText) {
            if (errorDiv) errorDiv.style.display = 'none';
            handleQrScanSuccess(decodedText);
        } else {
            throw new Error('Nie znaleziono kodu na zdjęciu.');
        }
    } catch (err) {
        if (errorDiv) {
            errorDiv.style.display = 'block';
            errorDiv.innerHTML = '<strong>⚠️ Nie udało się odczytać kodu ze zdjęcia.</strong> Zrób zdjęcie bliżej i wyraźniej.';
        }
    } finally {
        fileInput.value = '';
    }
};

/**
 * Handle scan success
 */
function handleQrScanSuccess(decodedText) {
    if (!decodedText) return;
    const text = decodedText.trim();
    console.log('[QRScanner] Success:', text);

    if (navigator.vibrate) {
        try { navigator.vibrate([100, 50, 100]); } catch (_) {}
    }

    if (window._activeQrScanner) {
        window._activeQrScanner.stop();
    }

    const resultDiv = document.getElementById('qr-scan-result');
    const resultBox = document.getElementById('qr-scan-result-container');
    if (resultDiv) resultDiv.textContent = text;
    if (resultBox) resultBox.style.display = 'block';

    const confirmBtn = document.getElementById('qr-confirm-btn');
    if (confirmBtn) confirmBtn.disabled = false;

    // Auto-confirm after 350ms
    setTimeout(() => window.confirmQrScan(text), 350);
}

/**
 * Confirm QR scan and execute target action
 */
window.confirmQrScan = function(decodedText) {
    const text = decodedText || document.getElementById('qr-scan-result')?.textContent;
    if (!text) return;

    const mode = window._qrScanMode || 'generic';
    const targetFieldId = window._qrScanTargetFieldId;

    window.closeQrScannerModal();

    if (mode === 'login') {
        handleLoginQrCode(text);
    } else if (mode === 'pallet') {
        handlePalletQrCode(text, targetFieldId);
    } else if (mode === 'location') {
        handleLocationQrCode(text, targetFieldId);
    } else {
        const targetField = document.getElementById(targetFieldId);
        if (targetField) {
            targetField.value = text;
            targetField.dispatchEvent(new Event('input', { bubbles: true }));
            targetField.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }
};

/**
 * Safe notification helper
 */
function safeNotify(message, type = 'info') {
    if (typeof AppDialog !== 'undefined' && AppDialog && typeof AppDialog.alert === 'function') {
        AppDialog.alert(message);
    } else if (typeof showToast === 'function') {
        showToast(message, type);
    } else if (typeof showAlert === 'function') {
        showAlert(message);
    } else {
        alert(message);
    }
}

/**
 * Login QR handler
 */
function handleLoginQrCode(qrText) {
    try {
        let credentials = null;
        const cleanText = qrText.trim();

        // 1. JSON format: {"login":"...","haslo":"..."}
        if (cleanText.startsWith('{') && cleanText.endsWith('}')) {
            try {
                const data = JSON.parse(cleanText);
                const u = data.login || data.username || data.user;
                const p = data.haslo || data.pass || data.password;
                if (u && p !== undefined) {
                    credentials = { login: String(u).trim(), haslo: String(p) };
                }
            } catch (_) {}
        }
        
        // 2. Format: LOGIN:username:password
        if (!credentials && cleanText.toUpperCase().startsWith('LOGIN:')) {
            const parts = cleanText.split(':');
            if (parts.length >= 3) {
                credentials = { login: parts[1].trim(), haslo: parts.slice(2).join(':') };
            }
        }

        // 3. Format: username:password
        if (!credentials && cleanText.includes(':')) {
            const parts = cleanText.split(':');
            if (parts.length === 2) {
                credentials = { login: parts[0].trim(), haslo: parts[1] };
            }
        }

        // 4. Plain username only
        if (!credentials && cleanText.length > 0 && !cleanText.includes(' ') && !cleanText.includes('\n')) {
            credentials = { login: cleanText, haslo: '' };
        }

        if (credentials && credentials.login) {
            const loginField = document.getElementById('login') || document.querySelector('input[name="login"]');
            const passwordField = document.getElementById('haslo') || document.querySelector('input[name="haslo"]');

            if (loginField) {
                loginField.value = credentials.login;
                loginField.dispatchEvent(new Event('input', { bubbles: true }));

                if (passwordField && credentials.haslo) {
                    passwordField.value = credentials.haslo;
                    passwordField.dispatchEvent(new Event('input', { bubbles: true }));

                    // Trigger form submit
                    setTimeout(() => {
                        const form = loginField.closest('form');
                        if (form) {
                            const submitBtn = form.querySelector('button[type="submit"]');
                            if (submitBtn) {
                                submitBtn.click();
                            } else {
                                form.submit();
                            }
                        }
                    }, 400);
                } else if (passwordField) {
                    passwordField.focus();
                }
            } else {
                safeNotify('Nie znaleziono pola logowania w formularzu.');
            }
        } else {
            safeNotify('Nieprawidłowy format kodu QR logowania.');
        }
    } catch (err) {
        console.error('[QRScanner] Login error:', err);
        safeNotify('Błąd odczytu kodu QR: ' + err.message);
    }
}

/**
 * Pallet QR handler
 */
function handlePalletQrCode(qrText, targetFieldId) {
    const targetField = document.getElementById(targetFieldId);
    if (targetField) {
        targetField.value = qrText.trim().toUpperCase();
        targetField.dispatchEvent(new Event('input', { bubbles: true }));
        targetField.dispatchEvent(new Event('change', { bubbles: true }));
    }
}

/**
 * Location QR handler
 */
function handleLocationQrCode(qrText, targetFieldId) {
    const locationCode = qrText.trim().toUpperCase();
    
    if (targetFieldId === 'usage_location_scan') {
        const sel = document.getElementById('usage_surowiec_id');
        if (sel) {
            let matched = false;
            for (let i = 0; i < sel.options.length; i++) {
                if (sel.options[i].textContent.toUpperCase().includes(locationCode)) {
                    sel.selectedIndex = i;
                    matched = true;
                    break;
                }
            }
            if (!matched) {
                safeNotify('Nie znaleziono palety dla lokalizacji: ' + locationCode);
            }
        }
    } else {
        const targetField = document.getElementById(targetFieldId);
        if (targetField) {
            targetField.value = locationCode;
            targetField.dispatchEvent(new Event('input', { bubbles: true }));
            targetField.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }
}

// Cleanup when navigating away
window.addEventListener('beforeunload', () => {
    if (window._activeQrScanner) {
        window._activeQrScanner.stop();
    }
});
