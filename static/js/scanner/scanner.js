const LINIA = '{{ linia }}';
let currentPallet = null;
let bagCount = 0;

/* ─── Printer status ──────────────────────────────────────── */
function checkPrinter() {
  fetch('/agro/scanner/printer/status')
    .then(r => r.json())
    .then(d => {
      const el = document.getElementById('printerPill');
      if (d.online) {
        el.className = 'pill pill-success';
        el.innerHTML = '<span class="material-icons" style="font-size:14px;">print</span> Drukarka online';
      } else {
        el.className = 'pill pill-warn';
        el.innerHTML = '<span class="material-icons" style="font-size:14px;">print_disabled</span> Drukarka offline';
      }
    }).catch(() => {
      document.getElementById('printerPill').className = 'pill pill-danger';
      document.getElementById('printerPill').textContent = 'Błąd połączenia';
    });
}
checkPrinter();


const scanInput = document.getElementById('scanInput');

function requestHardwareScanTrigger() {
  scanInput.focus();

  // Native bridge (jeśli strona działa w WebView z wystawionym API).
  try {
    if (window.Android && typeof window.Android.startBarcodeScan === 'function') {
      window.Android.startBarcodeScan();
      return true;
    }
  } catch (_) {}

  // Zebra Enterprise Browser API (jeśli dostępne).
  try {
    if (window.EB && window.EB.Barcode && typeof window.EB.Barcode.start === 'function') {
      window.EB.Barcode.start();
      return true;
    }
  } catch (_) {}

  // Nie próbujemy Android intent na desktopie.
  const isAndroid = /Android/i.test((navigator && navigator.userAgent) || '');
  if (!isAndroid) {
    return false;
  }

  // Best effort: DataWedge Soft Scan Trigger przez Android intent URI.
  try {
    const intentUri = 'intent:#Intent;action=com.symbol.datawedge.api.ACTION;S.com.symbol.datawedge.api.SOFT_SCAN_TRIGGER=START_SCANNING;end';
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    iframe.src = intentUri;
    document.body.appendChild(iframe);
    setTimeout(() => {
      if (iframe.parentNode) {
        iframe.parentNode.removeChild(iframe);
      }
    }, 250);
    return true;
  } catch (_) {
    return false;
  }
}

function triggerScan() {
  const code = scanInput.value.trim();
  if (code) {
    if (currentPallet) {
      const isPalletPrefix = code.startsWith('SUR-') || code.startsWith('OPA-') || code.startsWith('DOD-') || code.startsWith('QA-');
      if (code.length > 10 || isPalletPrefix) {
        lookupPallet(code);
      } else {
        doMoveFromMainInput(code);
      }
    } else {
      lookupPallet(code);
    }
  } else {
    const started = requestHardwareScanTrigger();
    if (started) {
      showToast('Aktywuję skaner... zeskanuj kod.', 'success');
    } else {
      showToast('Nie mogę uruchomić lasera z przeglądarki. Użyj fizycznego spustu skanera.', 'warn');
    }
  }
}

let pendingProductionLoc = null;

async function doMoveFromMainInput(loc) {
  loc = loc.toUpperCase();
  const isProduction = loc.startsWith('BB') || loc.startsWith('MZ') || loc.startsWith('WZ') || loc.startsWith('LINIA') || loc.startsWith('Z') || loc.startsWith('CZ');
  
  if (isProduction) {
    pendingProductionLoc = loc;
    document.getElementById('dispatchModalLoc').textContent = loc;
    document.getElementById('dispatchModalQty').value = currentPallet.stan_magazynowy;
    document.getElementById('dispatchOverlay').style.display = 'flex';
  } else {
    fetch('/agro/scanner/move', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        surowiec_id: currentPallet.id,
        type: currentPallet.inventory_type,
        lokalizacja: loc,
        linia: LINIA
      })
    })
    .then(r => r.json())
    .then(d => {
      showToast(d.message, d.success ? 'success' : 'danger');
      if (d.success) {
        window.hideAfterLoad = true;
        lookupPallet(currentPallet.nr_palety || 'SUR-' + currentPallet.id);
        
        // Odśwież też w tle licznik (badge) w sidebarze!
        fetch(window.location.href, {headers: {'X-Requested-With': 'XMLHttpRequest'}, cache: 'no-store'})
          .then(res => res.text())
          .then(html => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            
            // Update badge
            const newBadge = doc.querySelector('.nav-pending-badge');
            const oldBadge = document.querySelector('.nav-pending-badge');
            if (newBadge && oldBadge) {
              oldBadge.outerHTML = newBadge.outerHTML;
            } else if (!newBadge && oldBadge) {
              oldBadge.remove();
            } else if (newBadge && !oldBadge) {
              const subLabel = document.querySelector('a[href*="oczekujace"] .nav-sub-label');
              if (subLabel) subLabel.appendChild(newBadge.cloneNode(true));
            }
            
            // Update red dot on "MAGAZYNY"
            const newDot = doc.querySelector('.nav-main-dot');
            const oldDot = document.querySelector('.nav-main-dot');
            if (newDot && oldDot) {
              oldDot.outerHTML = newDot.outerHTML;
            } else if (!newDot && oldDot) {
              oldDot.remove();
            } else if (newDot && !oldDot) {
              const labelList = document.querySelectorAll('.nav-main-label');
              labelList.forEach(lbl => {
                  if(lbl.textContent.includes('MAGAZYNY')) {
                      lbl.appendChild(newDot.cloneNode(true));
                  }
              });
            }
          }).catch(() => {});
          
      } else {
        scanInput.value = '';
        scanInput.focus();
      }
    })
    .catch(e => {
      showToast('Błąd: ' + e, 'danger');
      scanInput.value = '';
      scanInput.focus();
    });
  }
}

function doFinalDispatch() {
  const qty = parseFloat(document.getElementById('dispatchModalQty').value);
  if (!qty || qty <= 0) return showToast('Podaj prawidłową ilość', 'warn');

  fetch('/agro/scanner/dispatch', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      surowiec_id: currentPallet.id,
      type: currentPallet.inventory_type,
      ilosc: qty,
      linia: LINIA,
      zbiornik: pendingProductionLoc,
      plan_id: document.getElementById('dispatchModalPlanId').value || null
    })
  })
  .then(r => r.json())
  .then(d => {
    showToast(d.message, d.success ? 'success' : 'danger');
    if (d.success) {
      closeDispatchModal();
      hidePallet();
    }
  })
  .catch(e => showToast('Błąd: ' + e, 'danger'));
}

function closeDispatchModal() {
  document.getElementById('dispatchOverlay').style.display = 'none';
  pendingProductionLoc = null;
  scanInput.value = '';
  scanInput.focus();
}

// Skanery Zebra (DataWedge) na Androidzie często lepiej reagują na 'keyup'
scanInput.addEventListener('keyup', function(e) {
  if (e.key === 'Enter' || e.keyCode === 13 || e.which === 13) {
    e.preventDefault();
    triggerScan();
  }
});

// Zabezpieczenie (debounce) jeśli skaner tylko "wkleja" tekst bez Entera
let scanTimeout;
scanInput.addEventListener('input', function(e) {
  clearTimeout(scanTimeout);
  scanTimeout = setTimeout(() => {
    const code = this.value.trim();
    if (code && code.length >= 5 && !document.getElementById('palletCard').classList.contains('visible')) {
      // Wywołaj automatycznie jeśli skaner Zebra po prostu wrzuca tekst
      triggerScan();
    }
  }, 1200);
});

function lookupPallet(code) {
  fetch('/agro/scanner/lookup', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({code, linia: LINIA})
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      showPallet(d.pallet);
      showToast('✅ Znaleziono: ' + d.pallet.nazwa, 'success');
    } else {
      hidePallet();
      showToast('❌ ' + d.error, 'danger');
    }
  })
  .catch(e => showToast('Błąd sieci: ' + e, 'danger'));
}

function showPallet(p) {
  if (p.is_unconfirmed_wg) {
    openWgAcceptModal(p);
    return;
  }
  currentPallet = p;
  document.getElementById('palletLoc').textContent  = p.lokalizacja || '—';
  document.getElementById('palletName').textContent = p.nazwa;
  document.getElementById('palletQty').textContent  = parseFloat(p.stan_magazynowy).toFixed(1);
  
  // Extra details
  document.getElementById('palletSSCC').textContent = p.nr_palety || p.inventory_code || '—';
  document.getElementById('palletPartia').textContent = p.nr_partii || '—';
  document.getElementById('palletDataProd').textContent = p.data_produkcji || '—';
  document.getElementById('palletDataWaz').textContent = p.data_przydatnosci || '—';

  document.getElementById('palletCard').classList.add('visible');
  document.getElementById('nopalletMsg').style.display = 'none';

  // Zmień główny input skanera na tryb lokalizacji
  const titleEl = document.querySelector('.scan-title');
  if(titleEl) titleEl.innerHTML = '<span class="material-icons" style="color:#2563eb;">place</span> Zeskanuj lokalizację docelową';
  scanInput.placeholder = 'np. R040101 lub BB01';
  scanInput.style.borderColor = '#2563eb';
  scanInput.style.borderWidth = '2px';
  const iconEl = document.querySelector('.input-icon');
  if(iconEl) iconEl.style.color = '#2563eb';

  scanInput.value = '';
  scanInput.focus();
  pendingProductionLoc = null;

  scanInput.value = '';
  scanInput.focus();

  if (window.hidePalletTimeout) {
    clearTimeout(window.hidePalletTimeout);
    window.hidePalletTimeout = null;
  }
  
  if (window.hideAfterLoad) {
    const barContainer = document.getElementById('palletTimeoutBarContainer');
    const bar = document.getElementById('palletTimeoutBar');
    if (barContainer && bar) {
        barContainer.style.display = 'block';
        bar.style.transition = 'none';
        bar.style.width = '100%';
        void bar.offsetWidth; // Force reflow
        bar.style.transition = 'width 6s linear';
        bar.style.width = '0%';
    }

    window.hidePalletTimeout = setTimeout(() => {
      hidePallet();
    }, 6000);
    window.hideAfterLoad = false;
  } else {
    const barContainer = document.getElementById('palletTimeoutBarContainer');
    if (barContainer) barContainer.style.display = 'none';
  }
}

function hidePallet() {
  if (window.hidePalletTimeout) {
    clearTimeout(window.hidePalletTimeout);
    window.hidePalletTimeout = null;
  }
  currentPallet = null;
  document.getElementById('palletCard').classList.remove('visible');
  document.getElementById('nopalletMsg').style.display = '';
  
  const barContainer = document.getElementById('palletTimeoutBarContainer');
  if (barContainer) barContainer.style.display = 'none';

  const titleEl = document.querySelector('.scan-title');
  if(titleEl) titleEl.innerHTML = '<span class="material-icons" style="color:var(--primary-color);">barcode_reader</span> Skanuj kod regału lub palety';
  scanInput.placeholder = 'R030101 albo SUR-42';
  scanInput.style.borderColor = '';
  scanInput.style.borderWidth = '';
  const iconEl = document.querySelector('.input-icon');
  if(iconEl) iconEl.style.color = '';
}
hidePallet();

/* ─── Print ───────────────────────────────────────────────── */
let currentPrintType = 'pallet';

function printLabel(type) {
  if (!currentPallet) return showToast('Brak palety — zeskanuj najpierw', 'warn');
  
  if (type === 'location') {
    const loc = currentPallet.lokalizacja || '';
    if (!loc) return showToast('Brak lokalizacji', 'warn');
    const url = `/agro/scanner/label_location?loc=${loc}&linia=${LINIA}`;
    window.openInApp ? openInApp(url, 'Etykieta regału') : window.open(url, '_blank');
    return;
  }

  currentPrintType = type;
  
  fetch('/agro/scanner/printers')
    .then(r => r.json())
    .then(printers => {
      if (!printers || printers.length === 0) {
        return sendPrintRequest();
      }
      if (printers.length === 1) {
        return sendPrintRequest(printers[0].ip, printers[0].nazwa);
      }
      
      const list = document.getElementById('printerList');
      list.innerHTML = '';
      printers.forEach(p => {
        const div = document.createElement('div');
        div.className = 'printer-option';
        div.onclick = () => {
          closePrinterModal();
          sendPrintRequest(p.ip, p.nazwa);
        };
        div.innerHTML = `
          <span class="material-icons">print</span>
          <div>
            <div class="printer-option-title">${p.nazwa}</div>
            <div class="printer-option-ip">${p.ip} ${p.lokalizacja ? ' | ' + p.lokalizacja : ''}</div>
          </div>
        `;
        list.appendChild(div);
      });
      document.getElementById('printerOverlay').style.display = 'flex';
    })
    .catch(() => {
      sendPrintRequest();
    });
}

function closePrinterModal() {
  document.getElementById('printerOverlay').style.display = 'none';
}

function sendPrintRequest(overrideIp = null, overrideName = null) {
  const payload = {
    surowiec_id: currentPallet.id,
    type: currentPrintType,
    linia: LINIA
  };
  if (overrideIp) payload.override_ip = overrideIp;
  if (overrideName) payload.override_name = overrideName;

  fetch('/agro/scanner/print', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      showToast('✅ Zlecono wydruk ' + (overrideName ? 'na ' + overrideName : ''), 'success');
    } else {
      showToast('❌ Błąd druku: ' + (d.error || 'nieznany'), 'danger');
    }
  })
  .catch((e) => {
    showToast('❌ Błąd połączenia przy druku', 'danger');
  });
}


/* ─── Finished Goods (WG) Acceptance Flow ───────────────────── */
let wgPalletObj = null;

function openWgAcceptModal(p) {
  wgPalletObj = p;
  document.getElementById('wgPalletNo').textContent = p.nr_palety || 'ID: ' + p.id;
  document.getElementById('wgPalletName').textContent = p.nazwa;
  document.getElementById('wgWeightInput').value = parseFloat(p.stan_magazynowy || 0).toFixed(1);
  document.getElementById('wgLocInput').value = '';
  
  backToWgStep1();
  
  document.getElementById('wgAcceptOverlay').style.display = 'flex';
  setTimeout(() => {
    const wInput = document.getElementById('wgWeightInput');
    wInput.focus();
    wInput.select();
  }, 100);
}

function closeWgAcceptModal() {
  document.getElementById('wgAcceptOverlay').style.display = 'none';
  wgPalletObj = null;
  scanInput.value = '';
  scanInput.focus();
}

function goToWgStep2() {
  const wVal = parseFloat(document.getElementById('wgWeightInput').value);
  if (!wVal || wVal <= 0) {
    showToast('Wprowadź prawidłową wagę', 'warn');
    return;
  }
  document.getElementById('wgStepWeight').style.display = 'none';
  document.getElementById('wgStepLocation').style.display = 'block';
  
  document.getElementById('wgBackBtn').style.display = 'inline-block';
  document.getElementById('wgNextBtn').style.display = 'none';
  document.getElementById('wgConfirmBtn').style.display = 'inline-block';
  
  setTimeout(() => {
    const locInp = document.getElementById('wgLocInput');
    locInp.focus();
    locInp.select();
  }, 100);
}

function backToWgStep1() {
  document.getElementById('wgStepWeight').style.display = 'block';
  document.getElementById('wgStepLocation').style.display = 'none';
  
  document.getElementById('wgBackBtn').style.display = 'none';
  document.getElementById('wgNextBtn').style.display = 'inline-block';
  document.getElementById('wgConfirmBtn').style.display = 'none';
  
  setTimeout(() => {
    const wInp = document.getElementById('wgWeightInput');
    wInp.focus();
    wInp.select();
  }, 100);
}

function submitWgAccept() {
  if (!wgPalletObj) return;
  const wVal = parseFloat(document.getElementById('wgWeightInput').value);
  const loc = document.getElementById('wgLocInput').value.trim().toUpperCase();
  
  if (!wVal || wVal <= 0) {
    showToast('Wprowadź prawidłową wagę', 'warn');
    return;
  }
  if (!loc) {
    showToast('Podaj lub zeskanuj lokalizację docelową', 'warn');
    return;
  }
  
  fetch('/magazyn-dostawy/api/przyjmij-wg', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      id: wgPalletObj.id,
      lokalizacja: loc,
      linia: LINIA,
      waga: wVal
    })
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      showToast('✅ Paleta przyjęta pomyślnie na ' + loc, 'success');
      closeWgAcceptModal();
      hidePallet();
    } else {
      showToast('❌ ' + (d.error || d.message || 'Błąd zapisu'), 'danger');
    }
  })
  .catch(e => showToast('Błąd: ' + e, 'danger'));
}

// Hook up automated Enter key listener for location input
document.addEventListener('DOMContentLoaded', () => {
  const locInp = document.getElementById('wgLocInput');
  if (locInp) {
    locInp.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.keyCode === 13) {
        e.preventDefault();
        submitWgAccept();
      }
    });
    // Auto-submit on scan (debounce 600ms) — skanery Zebra często nie wysyłają Enter
    let locScanTimeout;
    locInp.addEventListener('input', function() {
      clearTimeout(locScanTimeout);
      const val = this.value.trim();
      if (val.length >= 4) {
        locScanTimeout = setTimeout(() => {
          submitWgAccept();
        }, 600);
      }
    });
  }
});


/* ─── Audio Notifications ─────────────────────────────────── */
const AudioContext = window.AudioContext || window.webkitAudioContext;
const audioCtx = AudioContext ? new AudioContext() : null;

function playBeep(type) {
  if (!audioCtx) return;
  try {
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    osc.connect(gainNode);
    gainNode.connect(audioCtx.destination);

    if (type === 'success') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(800, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1200, audioCtx.currentTime + 0.1);
      gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.1);
      osc.start(audioCtx.currentTime);
      osc.stop(audioCtx.currentTime + 0.1);
    } else {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(300, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(150, audioCtx.currentTime + 0.3);
      gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
      osc.start(audioCtx.currentTime);
      osc.stop(audioCtx.currentTime + 0.3);
    }
  } catch (e) {
    console.warn("Audio play failed", e);
  }
}

/* ─── Toast ───────────────────────────────────────────────── */
let toastTimer;
function showToast(msg, type) {
  playBeep(type);
  const el = document.getElementById('toast');
  const colors = {success:'#166534', warn:'#92400e', danger:'#991b1b'};
  el.style.background = colors[type] || '#0f172a';
  el.textContent = msg;
  el.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.style.display = 'none', 4000);
}
