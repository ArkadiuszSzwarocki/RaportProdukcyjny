/* ─── Scanner Flow Controller, Dispatch & Main Input Listener ─── */

let currentPallet = null;
let bagCount = 0;
let pendingProductionLoc = null;
let pendingLP01Loc = 'LP01';
let scanTimeout = null;
let isProcessingScan = false;
let processingSafetyTimer = null;
let lastScannedCode = '';
let lastScannedTime = 0;

const scanInput = document.getElementById('scanInput');

function refreshSidebarBadgesSilently() {
  if (typeof window.refreshSidebarBadges === 'function') {
    try {
      window.refreshSidebarBadges();
    } catch (_) {}
  }
}

function resetLocationInputDetection() {
  clearTimeout(scanTimeout);
  scanTimeout = null;
}

function resetScanner() {
  clearTimeout(scanTimeout);
  scanTimeout = null;
  isProcessingScan = false;
  if (processingSafetyTimer) {
    clearTimeout(processingSafetyTimer);
    processingSafetyTimer = null;
  }
  lastScannedCode = '';
  lastScannedTime = 0;

  hidePallet();
  hideStation();
  resetLocationInputDetection();

  if (scanInput) {
    scanInput.value = '';
    scanInput.style.borderColor = '';
    scanInput.style.borderWidth = '';
    scanInput.placeholder = 'Wpisz lub zeskanuj kod (np. R030101, SSCC, PAL-15)';
    scanInput.disabled = false;
    scanInput.focus();
  }
  
  const mainTitle = document.getElementById('scanTitleText');
  if (mainTitle) mainTitle.textContent = 'Skanuj kod regału lub palety';
  const titleIcon = document.getElementById('scanTitleIcon');
  if (titleIcon) {
    titleIcon.textContent = 'barcode_reader';
    titleIcon.style.color = 'var(--primary-color, #3b82f6)';
  }
  const iconEl = document.querySelector('.input-icon');
  if (iconEl) iconEl.style.color = '';
  
  showToast('🔄 Skaner gotowy do nowego skanu', 'info');
}

function setProcessingState(processing) {
  isProcessingScan = processing;
  if (processingSafetyTimer) {
    clearTimeout(processingSafetyTimer);
    processingSafetyTimer = null;
  }
  if (processing) {
    // Safety fallback: never allow scanner to stay locked longer than 7 seconds
    processingSafetyTimer = setTimeout(() => {
      if (isProcessingScan) {
        console.warn('Scanner processing safety timeout reached - unlocking.');
        isProcessingScan = false;
        if (scanInput) {
          scanInput.focus();
        }
      }
    }, 7000);
  }
}

function triggerScan() {
  clearTimeout(scanTimeout);
  scanTimeout = null;
  if (!scanInput) return;

  const rawCode = scanInput.value.trim();
  const code = extractSSCCFromScan(rawCode);
  if (code !== rawCode) {
    scanInput.value = code;
  }

  if (!code) {
    const started = requestHardwareScanTrigger();
    if (started) {
      showToast('Aktywuję laser skanera...', 'success');
    } else {
      showToast('Wpisz lub zeskanuj kod (użyj spustu skanera).', 'warn');
    }
    return;
  }

  const now = Date.now();
  // Prevent duplicate execution within 150ms for identical code
  if (code === lastScannedCode && (now - lastScannedTime) < 150) {
    return;
  }
  lastScannedCode = code;
  lastScannedTime = now;

  if (currentPallet) {
    if (isPalletCode(code)) {
      lookupPallet(code);
    } else {
      doMoveFromMainInput(code);
    }
  } else {
    const upper = code.toUpperCase();
    if (upper === 'LP01' || upper === 'MASZYNA') {
      showToast('ℹ️ Wyświetlono stację LP01. Aby wydać materiał, najpierw zeskanuj paletę.', 'info');
    }
    lookupPallet(code);
  }
}

async function doMoveFromMainInput(loc) {
  loc = String(loc || '').trim().toUpperCase();
  if (!loc) return;

  if (isProcessingScan) {
    // Allow queueing / unlocking if previous finished
    return;
  }
  setProcessingState(true);

  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
  resetLocationInputDetection();

  const isDeliveryTransfer = Boolean(
    currentPallet
    && currentPallet.is_transfer
    && currentPallet.transfer
    && currentPallet.transfer.is_magazyn_dostawy
  );

  if (isDeliveryTransfer) {
    const dostawaId = currentPallet.dostawa_id || (currentPallet.transfer && currentPallet.transfer.id);
    const itemId = currentPallet.item_id || (currentPallet.transfer && currentPallet.transfer.item_details && currentPallet.transfer.item_details.id) || currentPallet.id;
    if (!dostawaId || !itemId) {
      setProcessingState(false);
      showToast('❌ Nie udało się ustalić pozycji dostawy do przyjęcia.', 'danger');
      if (scanInput) scanInput.focus();
      return;
    }

    const trStatus = String((currentPallet.transfer && currentPallet.transfer.status) || '').toUpperCase();
    const itDetails = (currentPallet.transfer && currentPallet.transfer.item_details) || {};
    const palletStatus = String(itDetails.pallet_status || '').toUpperCase();
    const isPutawayFlow = trStatus === 'PUTAWAY_IN_PROGRESS' || palletStatus === 'PUTAWAY_PENDING';

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);

      let res;
      if (isPutawayFlow) {
        res = await fetch(`/magazyn-dostawy/api/dostawy/${encodeURIComponent(dostawaId)}/confirm-putaway`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            item_id: itemId,
            lokalizacja: loc,
            strict_mode: false
          }),
          signal: controller.signal
        });
      } else {
        res = await fetch(`/magazyn-dostawy/api/przyjmij-pozycje/${encodeURIComponent(dostawaId)}`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            item_id: itemId,
            lokalizacja: loc,
            nr_partii: currentPallet.nr_partii || null,
            data_produkcji: currentPallet.data_produkcji || null,
            data_przydatnosci: currentPallet.data_przydatnosci || null,
            printer_id: null
          }),
          signal: controller.signal
        });
      }
      clearTimeout(timeoutId);

      const d = await res.json();
      showToast(d.message || d.error || (d.success ? 'Pozycja przyjęta.' : 'Błąd operacji.'), d.success ? 'success' : 'danger');
      if (d.success) {
        hidePallet();
        refreshSidebarBadgesSilently();
      }
    } catch (e) {
      showToast('Błąd komunikacji: ' + (e.name === 'AbortError' ? 'Przekroczono limit czasu' : e), 'danger');
    } finally {
      setProcessingState(false);
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
    }
    return;
  }

  if (currentPallet && !currentPallet.is_transfer && (currentPallet.is_used_up || parseFloat(currentPallet.stan_magazynowy || 0) <= 0)) {
    setProcessingState(false);
    showToast('❌ Ta paleta została już zużyta do 0 kg i zarchiwizowana. Nie można jej przenieść.', 'danger');
    if (scanInput) {
      scanInput.value = '';
      scanInput.focus();
    }
    return;
  }

  if (currentPallet && currentPallet.is_bucket) {
    const cleanLoc = (loc || '').trim().toUpperCase().replace(/[\s\-_]/g, '');
    if (cleanLoc !== 'MI01' && cleanLoc !== 'MI1') {
      setProcessingState(false);
      showToast(`❌ Nieprawidłowy kod '${loc}'! Wiadro można wrzucić wyłącznie do mieszalnika MI01.`, 'danger');
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
      return;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);
      const res = await fetch('/maluchy/api/dump-to-mixer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        body: JSON.stringify({
          kod_wiadra: currentPallet.kod_wiadra,
          plan_id: currentPallet.plan_id,
          mieszalnik_kod: 'MI01',
          linia: currentPallet.linia || (typeof LINIA !== 'undefined' ? LINIA : 'AGRO')
        }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      const d = await res.json();
      showToast(d.message, d.success ? 'success' : 'danger');
      if (d.success) {
        hidePallet();
        refreshSidebarBadgesSilently();
      }
    } catch (e) {
      showToast('Błąd: ' + e, 'danger');
    } finally {
      setProcessingState(false);
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
    }
    return;
  }

  const isTransfer = Boolean(currentPallet && (currentPallet.is_transfer || currentPallet.is_magazyn_dostawy || currentPallet.transfer));
  if (currentPallet && currentPallet.is_blocked && !isTransfer) {
    setProcessingState(false);
    showToast('⛔ Ta paleta jest zablokowana ręcznie (blokada magazynowa) i nie może być przesuwana!', 'danger');
    if (scanInput) {
      scanInput.value = '';
      scanInput.focus();
    }
    return;
  }

  const isProduction = (loc.startsWith('BB') || loc.startsWith('MZ') || loc.startsWith('WZ') || loc.startsWith('LINIA') || loc.startsWith('Z') || loc.startsWith('CZ') || loc.startsWith('KO') || loc.startsWith('PSD') || loc.startsWith('MIX')) && !loc.startsWith('BF_') && !loc.startsWith('BF');
  
  if (isProduction) {
    if (currentPallet.inventory_type === 'Wyrób Gotowy') {
      setProcessingState(false);
      showToast('❌ Wyrobów gotowych nie można przekazać na produkcję', 'danger');
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
      return;
    }
    if (currentPallet.inventory_type === 'Opakowanie') {
      setProcessingState(false);
      showToast('❌ Opakowań nie można przekazać do stacji produkcyjnej', 'danger');
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
      return;
    }

    try {
      const vRes = await fetch('/agro/scanner/validate-station', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          zbiornik: loc,
          surowiec_nazwa: currentPallet.nazwa || currentPallet.produkt || '',
          surowiec_id: currentPallet.id,
          pallet_type: currentPallet.inventory_type || 'Surowiec',
          linia: currentPallet.linia || (typeof LINIA !== 'undefined' ? LINIA : 'AGRO')
        })
      });
      const vData = await vRes.json();
      if (!vData.success) {
        setProcessingState(false);
        showToast(vData.error || vData.message || `⛔ BŁĄD: Stacja ${loc} jest niezgodna z tym surowcem!`, 'danger');
        if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
        if (scanInput) {
          scanInput.value = '';
          scanInput.focus();
        }
        return;
      }
    } catch (err) {
      console.error('Błąd walidacji stacji:', err);
    }
    
    setProcessingState(false);
    pendingProductionLoc = loc;
    const locEl = document.getElementById('dispatchModalLoc');
    if (locEl) locEl.textContent = loc;
    const qtyEl = document.getElementById('dispatchModalQty');
    if (qtyEl) qtyEl.value = currentPallet.stan_magazynowy;
    const overlay = document.getElementById('dispatchOverlay');
    if (overlay) overlay.style.display = 'flex';
  } else {
    const isLP01 = (loc === 'LP01' || loc === 'MASZYNA');
    if (isLP01) {
      setProcessingState(false);
      openLP01Modal(loc);
      return;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);
      const res = await fetch('/agro/scanner/move', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          surowiec_id: currentPallet.id,
          nr_palety: currentPallet.nr_palety || currentPallet.sscc,
          type: currentPallet.inventory_type,
          lokalizacja: loc,
          linia: (typeof LINIA !== 'undefined' ? LINIA : 'AGRO'),
          amount_to_move: null
        }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      const d = await res.json();
      showToast(d.message, d.success ? 'success' : 'danger');

      if (d.success) {
        const isPkg = currentPallet && (
          currentPallet.inventory_type === 'Opakowanie' ||
          currentPallet.is_pkg ||
          currentPallet.unit === 'szt.' ||
          currentPallet.unit === 'szt' ||
          currentPallet.jednostka === 'szt.' ||
          currentPallet.jednostka === 'szt'
        );
        if (d.split_info && d.split_info.is_split && d.split_info.new_sscc) {
          if (!isPkg) {
            showToast(`✅ Odcięto ${d.split_info.moved_qty} kg na nową paletę (${d.split_info.new_sscc}). Otwieram etykietę...`, 'success');
            window.open(`/agro/scanner/label/${encodeURIComponent(d.split_info.new_sscc)}?linia=${encodeURIComponent(typeof LINIA !== 'undefined' ? LINIA : 'AGRO')}&autoprint=1`, '_blank');
          } else {
            showToast(`✅ Pobrano ${d.split_info.moved_qty || ''} szt. opakowania.`, 'success');
          }
        }
        hidePallet();
        currentPallet = null;
        refreshSidebarBadgesSilently();
      } else if (loc && loc.length >= 6) {
        setProcessingState(false);
        lookupPallet(loc);
        return;
      }
    } catch (e) {
      showToast('Błąd przesunięcia: ' + (e.name === 'AbortError' ? 'Przekroczono limit czasu' : e), 'danger');
    } finally {
      setProcessingState(false);
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
    }
  }
}

function doFinalDispatch() {
  const qty = parseFloat(document.getElementById('dispatchModalQty').value);
  if (!qty || qty <= 0) return showToast('Podaj prawidłową ilość', 'warn');

  setProcessingState(true);
  fetch('/agro/scanner/dispatch', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      surowiec_id: currentPallet.id,
      type: currentPallet.inventory_type,
      ilosc: qty,
      linia: (typeof LINIA !== 'undefined' ? LINIA : 'AGRO'),
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
      refreshSidebarBadgesSilently();
    }
  })
  .catch(e => showToast('Błąd: ' + e, 'danger'))
  .finally(() => {
    setProcessingState(false);
  });
}

function closeDispatchModal() {
  const overlay = document.getElementById('dispatchOverlay');
  if (overlay) overlay.style.display = 'none';
  pendingProductionLoc = null;
  setProcessingState(false);
  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
}

async function lookupPallet(code) {
  if (!code) return;
  code = String(code).trim();
  if (!code) return;

  setProcessingState(true);

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);

    const res = await fetch('/agro/scanner/lookup', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        code: code,
        linia: (typeof LINIA !== 'undefined' ? LINIA : 'AGRO')
      }),
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    const d = await res.json();
    if (d.success && d.pallet) {
      if (d.pallet.is_station) {
        showStation(d.pallet);
        showToast(`✅ Znaleziono stację: ${d.pallet.station_code}`, 'success');
      } else {
        showPallet(d.pallet);
        showToast('✅ Znaleziono: ' + (d.pallet.nazwa || d.pallet.nr_palety || code), 'success');
      }
    } else {
      hidePallet();
      hideStation();
      showToast('❌ ' + (d.error || 'Nie znaleziono pozycji'), 'danger');
    }
  } catch (e) {
    showToast('Błąd połączenia: ' + (e.name === 'AbortError' ? 'Przekroczono limit czasu' : e), 'danger');
  } finally {
    setProcessingState(false);
    if (scanInput) {
      scanInput.value = '';
      scanInput.focus();
    }
  }
}

if (scanInput) {
  // Keydown listener: on Enter immediate trigger
  scanInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.keyCode === 13 || e.which === 13) {
      e.preventDefault();
      clearTimeout(scanTimeout);
      scanTimeout = null;
      triggerScan();
    }
  });

  // Input listener: adaptive debounce ensures all hardware scanners and typing auto-trigger
  scanInput.addEventListener('input', function() {
    const raw = this.value;
    const cleaned = extractSSCCFromScan(raw);
    if (cleaned !== raw) {
      this.value = cleaned;
    }
    clearTimeout(scanTimeout);

    const code = (this.value || '').trim();
    if (!code) return;

    // Determine debounce delay:
    // If it's a long code (like SSCC or standard pallet ID >= 6 chars), auto-submit fast (120ms).
    // If short (3-5 chars), give 300ms so user can finish typing or scanner burst finishes.
    const delay = code.length >= 6 ? 120 : 300;

    if (code.length >= 3) {
      scanTimeout = setTimeout(() => {
        const currVal = (scanInput ? scanInput.value : '').trim();
        if (currVal.length >= 3 && !isProcessingScan) {
          triggerScan();
        }
      }, delay);
    }
  });

  // Paste listener: fast auto-submit on paste
  scanInput.addEventListener('paste', function() {
    clearTimeout(scanTimeout);
    setTimeout(() => {
      if (scanInput) {
        const cleaned = extractSSCCFromScan(scanInput.value);
        if (cleaned !== scanInput.value) {
          scanInput.value = cleaned;
        }
        const code = scanInput.value.trim();
        if (code.length >= 3) {
          triggerScan();
        }
      }
    }, 20);
  });
}

// Global refocus / barcode capture helper:
// If the user scans with a barcode reader while scanInput is accidentally unfocused
// (e.g. after tapping the screen or clicking outside inputs), redirect focus and typing to scanInput.
window.addEventListener('keydown', function(e) {
  const activeEl = document.activeElement;
  const isInputActive = activeEl && (
    activeEl.tagName === 'INPUT' || 
    activeEl.tagName === 'TEXTAREA' || 
    activeEl.tagName === 'SELECT' || 
    activeEl.isContentEditable
  );

  if (!isInputActive && scanInput && !scanInput.disabled) {
    // Only capture printable ASCII characters
    if (e.key && e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
      scanInput.focus();
    }
  }
});

window.addEventListener('click', function(e) {
  const overlay = document.getElementById('scannerHistoryOverlay');
  if (e.target === overlay) {
    closeScannerHistoryModal();
  }
});

// Initial boot
checkPrinter();
hidePallet();
hideStation();
