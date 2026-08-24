/**
 * High-Bay Camera Scanner (Skaner Aparatem na Żywo z Zoomem do 7m)
 * Działa w trybie ciągłym na żywo: najeżdżasz aparatem na kod na regale (z zoomem do 10x),
 * kod jest natychmiast automatycznie wykrywany, odczytywany i przekazywany do systemu.
 */

(function () {
  'use strict';

  let html5QrCodeScanner = null;
  let activeVideoTrack = null;
  let isScannerRunning = false;
  let currentZoom = 1.0;
  let zoomCapabilities = { min: 1.0, max: 10.0, step: 0.1, supported: false };
  let isTorchActive = false;
  let torchSupported = false;
  let availableCameras = [];
  let currentCameraIndex = 0;

  // Pinch-to-zoom
  let initialPinchDistance = 0;
  let initialPinchZoom = 1.0;

  /**
   * Ładuje bibliotekę Html5Qrcode jeśli nie jest załadowana
   */
  async function ensureHtml5QrcodeLoaded() {
    if (typeof Html5Qrcode !== 'undefined') {
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('Nie udało się załadować biblioteki skanera.'));
      document.head.appendChild(script);
    });
  }

  /**
   * Otwiera skaner wideo na żywo (Live Viewfinder)
   */
  window.openHighBayCameraScanner = async function () {
    const modal = document.getElementById('highBayCameraModal');
    if (!modal) return;

    modal.classList.add('active');

    // Sprawdzenie czy przeglądarka wspiera strumień na żywo
    const hasMediaDevices = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

    if (!hasMediaDevices) {
      showHttpWarningOverlay(true);
      return;
    }

    showHttpWarningOverlay(false);

    try {
      await ensureHtml5QrcodeLoaded();
      await startLiveCameraStream();
    } catch (err) {
      console.warn('[HIGH_BAY_CAMERA] Błąd uruchomienia wideo na żywo:', err);
      showHttpWarningOverlay(true);
    }
  };

  /**
   * Pokazuje / ukrywa instrukcję odblokowania kamery dla HTTP w sieci LAN
   */
  function showHttpWarningOverlay(show) {
    let warningBox = document.getElementById('highBayHttpWarning');
    if (!warningBox) {
      const viewport = document.querySelector('.high-bay-viewport-wrap');
      if (viewport) {
        warningBox = document.createElement('div');
        warningBox.id = 'highBayHttpWarning';
        warningBox.style.cssText = `
          position: absolute; inset: 0; background: rgba(15, 23, 42, 0.96);
          z-index: 20; display: flex; flex-direction: column; align-items: center;
          justify-content: center; padding: 20px; text-align: center; color: #f8fafc;
          box-sizing: border-box; overflow-y: auto;
        `;
        const currentOrigin = window.location.origin;
        warningBox.innerHTML = `
          <div style="max-width: 440px; background: #1e293b; border: 1.5px solid #3b82f6; border-radius: 16px; padding: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
            <span class="material-icons" style="font-size: 48px; color: #3b82f6; margin-bottom: 8px;">videocam</span>
            <h3 style="margin: 0 0 10px 0; font-size: 1.15rem; font-weight: 800; color: #60a5fa;">Skaner na żywo (Kamera)</h3>
            <p style="font-size: 0.85rem; color: #cbd5e1; line-height: 1.5; margin-bottom: 16px;">
              Aby skanować kody na żywo bez robienia zdjęć przez adres IP (HTTP), Chrome na telefonie wymaga jednorazowego odblokowania kamery dla adresu:<br>
              <strong style="color: #fbbf24; font-family: monospace; font-size: 0.95rem;">${currentOrigin}</strong>
            </p>
            
            <div style="background: #0f172a; border-radius: 10px; padding: 12px; text-align: left; font-size: 0.8rem; color: #94a3b8; margin-bottom: 18px; line-height: 1.6;">
              <strong style="color: #f8fafc;">Jak włączyć w 30 sekund w Chrome na telefonie:</strong><br>
              1. Wpisz w pasek adresu Chrome: <br><span style="color:#60a5fa; font-family: monospace;">chrome://flags/#unsafely-treat-insecure-origin-as-secure</span><br>
              2. Zmień na <strong>Enabled</strong>.<br>
              3. W pole poniżej wpisz: <strong style="color:#fbbf24;">${currentOrigin}</strong><br>
              4. Kliknij <strong>Relaunch</strong> (Uruchom ponownie).
            </div>

            <div style="display: flex; flex-direction: column; gap: 10px;">
              <button type="button" onclick="window.openNativeCameraCapture(); window.closeHighBayCameraScanner();" 
                      style="background: linear-gradient(135deg, #1d4ed8, #2563eb); color: #fff; border: none; border-radius: 8px; padding: 12px 16px; font-weight: 800; font-size: 0.9rem; cursor: pointer;">
                📷 Użyj trybu zdjęcia z zoomem (działa od razu)
              </button>
              <button type="button" onclick="window.closeHighBayCameraScanner()" 
                      style="background: transparent; border: 1px solid #475569; color: #94a3b8; border-radius: 8px; padding: 8px 16px; font-weight: 600; font-size: 0.85rem; cursor: pointer;">
                Zamknij
              </button>
            </div>
          </div>
        `;
        viewport.appendChild(warningBox);
      }
    }

    if (warningBox) {
      warningBox.style.display = show ? 'flex' : 'none';
    }
  }

  /**
   * Zatrzymuje i zamyka skaner
   */
  window.closeHighBayCameraScanner = async function () {
    const modal = document.getElementById('highBayCameraModal');
    if (modal) modal.classList.remove('active');

    if (activeVideoTrack && isTorchActive) {
      try {
        await activeVideoTrack.applyConstraints({ advanced: [{ torch: false }] });
      } catch (_) {}
      isTorchActive = false;
    }

    if (html5QrCodeScanner && isScannerRunning) {
      try {
        await html5QrCodeScanner.stop();
        html5QrCodeScanner.clear();
      } catch (err) {
        console.warn('Stop camera error:', err);
      }
    }

    isScannerRunning = false;
    activeVideoTrack = null;
    currentZoom = 1.0;
  };

  /**
   * Startuje strumień wideo na żywo z ciągłym dekodowaniem
   */
  async function startLiveCameraStream() {
    const previewContainerId = 'camera-preview-container';
    const container = document.getElementById(previewContainerId);
    if (!container) return;

    try {
      availableCameras = await Html5Qrcode.getCameras();
    } catch (e) {
      availableCameras = [];
    }

    let cameraIdOrConfig = { facingMode: { ideal: 'environment' } };
    if (availableCameras && availableCameras.length > 0) {
      const rearCam = availableCameras.find(c => /back|rear|environment/i.test(c.label));
      if (rearCam) {
        cameraIdOrConfig = rearCam.id;
      } else {
        cameraIdOrConfig = availableCameras[0].id;
      }
    }

    const formatsToSupport = [
      Html5QrcodeSupportedFormats.QR_CODE,
      Html5QrcodeSupportedFormats.DATA_MATRIX,
      Html5QrcodeSupportedFormats.CODE_128,
      Html5QrcodeSupportedFormats.CODE_39,
      Html5QrcodeSupportedFormats.EAN_13,
      Html5QrcodeSupportedFormats.EAN_8,
      Html5QrcodeSupportedFormats.UPC_A,
      Html5QrcodeSupportedFormats.UPC_E,
      Html5QrcodeSupportedFormats.ITF
    ];

    html5QrCodeScanner = new Html5Qrcode(previewContainerId, {
      formatsToSupport: formatsToSupport,
      verbose: false
    });

    const cameraConfig = {
      fps: 25, // Ciągłe skanowanie 25 klatek na sekundę
      qrbox: function (w, h) {
        const qrWidth = Math.floor(Math.min(w * 0.9, 440));
        const qrHeight = Math.floor(Math.min(h * 0.65, 280));
        return { width: qrWidth, height: qrHeight };
      },
      aspectRatio: 1.777778,
      videoConstraints: {
        facingMode: { ideal: 'environment' },
        width: { min: 1280, ideal: 1920, max: 4096 },
        height: { min: 720, ideal: 1080, max: 2160 },
        focusMode: 'continuous'
      }
    };

    // Uruchomienie skanera w trybie ciągłym
    await html5QrCodeScanner.start(
      cameraIdOrConfig,
      cameraConfig,
      onHighBayBarcodeDecoded, // Wywoływane natychmiast po najechaniu na kod
      () => {} // Ignoruj pojedyncze klatki bez kodu
    );

    isScannerRunning = true;
    setTimeout(initTrackCapabilities, 400);
    setupTouchPinchEvents();
  }

  /**
   * Wykrywa możliwości sprzętowego zoomu i latarki
   */
  function initTrackCapabilities() {
    const videoElem = document.querySelector('#camera-preview-container video');
    if (!videoElem || !videoElem.srcObject) return;

    const stream = videoElem.srcObject;
    const tracks = stream.getVideoTracks();
    if (!tracks || tracks.length === 0) return;

    activeVideoTrack = tracks[0];

    if (typeof activeVideoTrack.getCapabilities === 'function') {
      const caps = activeVideoTrack.getCapabilities();

      if (caps.zoom) {
        zoomCapabilities.min = caps.zoom.min || 1.0;
        zoomCapabilities.max = Math.max(caps.zoom.max || 10.0, 5.0);
        zoomCapabilities.step = caps.zoom.step || 0.1;
        zoomCapabilities.supported = true;
      } else {
        zoomCapabilities.min = 1.0;
        zoomCapabilities.max = 10.0;
        zoomCapabilities.step = 0.1;
        zoomCapabilities.supported = false;
      }

      torchSupported = Boolean(caps.torch);
      const torchBtn = document.getElementById('cameraTorchBtn');
      if (torchBtn) {
        torchBtn.style.display = torchSupported ? 'inline-flex' : 'none';
      }

      const slider = document.getElementById('cameraZoomSlider');
      if (slider) {
        slider.min = zoomCapabilities.min;
        slider.max = zoomCapabilities.max;
        slider.step = zoomCapabilities.step;
        slider.value = 1.0;
      }
    }

    window.applyHighBayZoom(1.0);
  }

  /**
   * Zmiana przybliżenia na żywo (Hardware + Digital)
   */
  window.applyHighBayZoom = async function (zoomValue) {
    const parsed = parseFloat(zoomValue);
    if (isNaN(parsed)) return;

    currentZoom = Math.max(zoomCapabilities.min, Math.min(zoomCapabilities.max, parsed));

    const slider = document.getElementById('cameraZoomSlider');
    if (slider) slider.value = currentZoom;

    const badge = document.getElementById('cameraZoomFloatingBadge');
    if (badge) badge.textContent = '🔍 ' + currentZoom.toFixed(1) + 'x';

    document.querySelectorAll('.btn-zoom-preset').forEach(btn => {
      const p = parseFloat(btn.getAttribute('data-zoom'));
      if (Math.abs(p - currentZoom) < 0.15) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    if (activeVideoTrack && typeof activeVideoTrack.applyConstraints === 'function') {
      try {
        await activeVideoTrack.applyConstraints({
          advanced: [{ zoom: currentZoom }]
        });
      } catch (e) {
        console.warn('Hardware zoom constraint error:', e);
      }
    }

    const videoElem = document.querySelector('#camera-preview-container video');
    if (videoElem) {
      if (!zoomCapabilities.supported) {
        videoElem.style.transform = `scale(${currentZoom})`;
        videoElem.style.transformOrigin = 'center center';
      } else {
        videoElem.style.transform = 'none';
      }
    }
  };

  window.stepHighBayZoom = function (delta) {
    const nextZoom = currentZoom + delta;
    window.applyHighBayZoom(nextZoom);
  };

  window.toggleHighBayTorch = async function () {
    if (!activeVideoTrack || !torchSupported) return;

    try {
      isTorchActive = !isTorchActive;
      await activeVideoTrack.applyConstraints({
        advanced: [{ torch: isTorchActive }]
      });

      const torchBtn = document.getElementById('cameraTorchBtn');
      if (torchBtn) {
        if (isTorchActive) {
          torchBtn.style.background = '#f59e0b';
          torchBtn.style.color = '#000000';
          torchBtn.innerHTML = '<span class="material-icons" style="font-size:16px;">flash_on</span> Latarka (WŁ)';
        } else {
          torchBtn.style.background = 'rgba(30, 41, 59, 0.8)';
          torchBtn.style.color = '#f8fafc';
          torchBtn.innerHTML = '<span class="material-icons" style="font-size:16px;">flash_off</span> Latarka';
        }
      }
    } catch (err) {
      console.warn('Torch error:', err);
    }
  };

  window.switchHighBayCamera = async function () {
    if (!availableCameras || availableCameras.length < 2) return;

    currentCameraIndex = (currentCameraIndex + 1) % availableCameras.length;
    const nextCamId = availableCameras[currentCameraIndex].id;

    if (html5QrCodeScanner && isScannerRunning) {
      try {
        await html5QrCodeScanner.stop();
      } catch (_) {}

      const cameraConfig = {
        fps: 25,
        qrbox: function (w, h) {
          return { width: Math.floor(Math.min(w * 0.9, 440)), height: Math.floor(Math.min(h * 0.65, 280)) };
        },
        aspectRatio: 1.777778
      };

      await html5QrCodeScanner.start(
        nextCamId,
        cameraConfig,
        onHighBayBarcodeDecoded,
        () => {}
      );

      setTimeout(initTrackCapabilities, 400);
    }
  };

  function setupTouchPinchEvents() {
    const container = document.getElementById('camera-preview-container');
    if (!container || container._pinchAttached) return;

    container._pinchAttached = true;

    container.addEventListener('touchstart', (e) => {
      if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        initialPinchDistance = Math.sqrt(dx * dx + dy * dy);
        initialPinchZoom = currentZoom;
      }
    }, { passive: true });

    container.addEventListener('touchmove', (e) => {
      if (e.touches.length === 2 && initialPinchDistance > 0) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const currentDistance = Math.sqrt(dx * dx + dy * dy);
        const factor = currentDistance / initialPinchDistance;
        const targetZoom = Math.max(1.0, Math.min(zoomCapabilities.max, initialPinchZoom * factor));
        window.applyHighBayZoom(targetZoom);
      }
    }, { passive: true });

    container.addEventListener('touchend', (e) => {
      if (e.touches.length < 2) {
        initialPinchDistance = 0;
      }
    }, { passive: true });
  }

  /**
   * Automatyczne wywołanie natychmiast po wykryciu kodu
   */
  function onHighBayBarcodeDecoded(decodedText) {
    if (!decodedText) return;

    const rawCode = decodedText.trim();
    console.log('[HIGH_BAY_CAMERA] Natychmiast zeskanowano kod na żywo:', rawCode);

    if (typeof playScannerBeep === 'function') {
      playScannerBeep('success');
    }

    if (navigator.vibrate) {
      navigator.vibrate([120, 60, 120]);
    }

    window.closeHighBayCameraScanner();

    let cleanCode = rawCode;
    if (typeof extractSSCCFromScan === 'function') {
      cleanCode = extractSSCCFromScan(rawCode);
    }

    const scanInput = document.getElementById('scanInput');
    if (scanInput) {
      scanInput.value = cleanCode;
    }

    if (typeof showToast === 'function') {
      showToast(`🎯 Zeskanowano na żywo: ${cleanCode}`, 'success');
    }

    // Automatyczne zatwierdzenie i wysłanie do systemu
    if (typeof triggerScan === 'function') {
      triggerScan();
    }
  }

  /**
   * Otwiera aparat systemowy
   */
  window.openNativeCameraCapture = function () {
    const fileInput = document.getElementById('highBayNativeCameraInput');
    if (fileInput) {
      fileInput.value = '';
      fileInput.click();
    }
  };

  /**
   * Obsługa zdjęcia (tryb zapasowy)
   */
  window.handleHighBayNativePhotoCapture = async function (input) {
    if (!input || !input.files || input.files.length === 0) return;

    const file = input.files[0];
    if (typeof showToast === 'function') {
      showToast('🔍 Odczytuję kod...', 'info');
    }

    try {
      await ensureHtml5QrcodeLoaded();

      let scanContainer = document.getElementById('camera-file-scanner-temp');
      if (!scanContainer) {
        scanContainer = document.createElement('div');
        scanContainer.id = 'camera-file-scanner-temp';
        scanContainer.style.position = 'fixed';
        scanContainer.style.left = '-9999px';
        document.body.appendChild(scanContainer);
      }

      const fileScanner = new Html5Qrcode('camera-file-scanner-temp', {
        formatsToSupport: [
          Html5QrcodeSupportedFormats.QR_CODE,
          Html5QrcodeSupportedFormats.DATA_MATRIX,
          Html5QrcodeSupportedFormats.CODE_128,
          Html5QrcodeSupportedFormats.CODE_39,
          Html5QrcodeSupportedFormats.EAN_13,
          Html5QrcodeSupportedFormats.EAN_8,
          Html5QrcodeSupportedFormats.UPC_A,
          Html5QrcodeSupportedFormats.UPC_E,
          Html5QrcodeSupportedFormats.ITF
        ],
        verbose: false
      });

      const decodedText = await fileScanner.scanFile(file, false);
      if (decodedText) {
        onHighBayBarcodeDecoded(decodedText);
      }
    } catch (err) {
      if (typeof showToast === 'function') {
        showToast('⚠️ Nie udało się odczytać kodu. Zrób zdjęcie bliżej etykiety.', 'warning');
      }
    } finally {
      input.value = '';
    }
  };

})();
