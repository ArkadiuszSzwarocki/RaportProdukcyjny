/* ─── Scanner Flow Controller, Dispatch & Main Input Listener ─── */

let currentPallet = null;
let bagCount = 0;
let pendingProductionLoc = null;
let pendingLP01Loc = 'LP01';
let scanTimeout = null;
let locationBurstStartedAt = 0;
let lastLocationInputTs = 0;
let lastLocationInputLen = 0;
let locationAutoSubmitArmed = false;
let locationManualTypingDetected = false;

const scanInput = document.getElementById('scanInput');

function refreshSidebarBadgesSilently() {
  if (typeof window.refreshSidebarBadges === 'function') {
    window.refreshSidebarBadges();
  }
}

function resetLocationInputDetection() {
  locationBurstStartedAt = 0;
  lastLocationInputTs = 0;
  lastLocationInputLen = 0;
  locationAutoSubmitArmed = false;
  locationManualTypingDetected = false;
}

function resetScanner() {
  hidePallet();
  hideStation();
  resetLocationInputDetection();
  if (scanInput) {
    scanInput.value = '';
    scanInput.style.borderColor = '';
    scanInput.style.borderWidth = '';
    scanInput.placeholder = 'Wpisz lub zeskanuj kod (np. R030101, SSCC, PAL-15)';
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
  
  showToast('🔄 Skaner zresetowany — gotowy do nowego skanu', 'info');
}

let lastTriggerScanTime = 0;
let lastTriggerScanCode = '';

function triggerScan() {
  clearTimeout(scanTimeout);
  if (!scanInput) return;
  const rawCode = scanInput.value.trim();
  const code = extractSSCCFromScan(rawCode);
  if (code !== rawCode) {
    scanInput.value = code;
  }
  const now = Date.now();
  if (code && code === lastTriggerScanCode && (now - lastTriggerScanTime) < 500) {
    return;
  }
  lastTriggerScanCode = code;
  lastTriggerScanTime = now;

  if (code) {
    if (currentPallet) {
      if (isPalletCode(code)) {
        lookupPallet(code);
      } else {
        doMoveFromMainInput(code);
      }
    } else {
      const upper = code.toUpperCase();
      if (upper === 'LP01' || upper === 'MASZYNA') {
        showToast('ℹ️ Wyświetlono stację LP01. Aby wydać materiał na LP01, najpierw zeskanuj paletę/materiał.', 'info');
      }
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

async function doMoveFromMainInput(loc) {
  loc = loc.toUpperCase();
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
      showToast('❌ Nie udało się ustalić pozycji dostawy do przyjęcia.', 'danger');
      if (scanInput) {
        scanInput.focus();
      }
      return;
    }

    const trStatus = String((currentPallet.transfer && currentPallet.transfer.status) || '').toUpperCase();
    const itDetails = (currentPallet.transfer && currentPallet.transfer.item_details) || {};
    const palletStatus = String(itDetails.pallet_status || '').toUpperCase();
    const isPutawayFlow = trStatus === 'PUTAWAY_IN_PROGRESS' || palletStatus === 'PUTAWAY_PENDING';

    try {
      let res;
      if (isPutawayFlow) {
        res = await fetch(`/magazyn-dostawy/api/dostawy/${encodeURIComponent(dostawaId)}/confirm-putaway`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            item_id: itemId,
            lokalizacja: loc,
            strict_mode: false
          })
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
          })
        });
      }

      const d = await res.json();
      showToast(d.message || d.error || (d.success ? 'Pozycja przyjęta.' : 'Błąd operacji.'), d.success ? 'success' : 'danger');
      if (d.success) {
        window.hideAfterLoad = true;
        hidePallet();
        if (scanInput) {
          scanInput.value = '';
          scanInput.focus();
        }
        resetLocationInputDetection();
        refreshSidebarBadgesSilently();
      } else if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
    } catch (e) {
      showToast('Błąd: ' + e, 'danger');
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
    }
    return;
  }

  if (currentPallet && !currentPallet.is_transfer && (currentPallet.is_used_up || parseFloat(currentPallet.stan_magazynowy || 0) <= 0)) {
    showToast('❌ Ta paleta została już zużyta do 0 kg i zarchiwizowana. Nie można jej przenieść ani wydać.', 'danger');
    if (scanInput) {
      scanInput.value = '';
      scanInput.focus();
    }
    return;
  }

  if (currentPallet && currentPallet.is_bucket) {
    const cleanLoc = (loc || '').trim().toUpperCase().replace(/[\s\-_]/g, '');
    if (cleanLoc !== 'MI01' && cleanLoc !== 'MI1') {
      showToast(`❌ Nieprawidłowy kod '${loc}'! Wiadro można wrzucić wyłącznie do mieszalnika MI01.`, 'danger');
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
      return;
    }
    fetch('/maluchy/api/dump-to-mixer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
      body: JSON.stringify({
        kod_wiadra: currentPallet.kod_wiadra,
        plan_id: currentPallet.plan_id,
        mieszalnik_kod: 'MI01',
        linia: currentPallet.linia || LINIA
      })
    })
    .then(r => r.json())
    .then(d => {
      showToast(d.message, d.success ? 'success' : 'danger');
      if (d.success) {
        window.hideAfterLoad = true;
        hidePallet();
        if (scanInput) {
          scanInput.value = '';
          scanInput.focus();
        }
        resetLocationInputDetection();
        refreshSidebarBadgesSilently();
      } else if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
    })
    .catch(e => {
      showToast('Błąd: ' + e, 'danger');
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
    });
    return;
  }

  const isTransfer = Boolean(currentPallet && (currentPallet.is_transfer || currentPallet.is_magazyn_dostawy || currentPallet.transfer));
  if (currentPallet && currentPallet.is_blocked && !isTransfer) {
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
      showToast('❌ Wyrobów gotowych nie można przekazać na produkcję', 'danger');
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
      return;
    }
    if (currentPallet.inventory_type === 'Opakowanie') {
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
    
    pendingProductionLoc = loc;
    document.getElementById('dispatchModalLoc').textContent = loc;
    document.getElementById('dispatchModalQty').value = currentPallet.stan_magazynowy;
    document.getElementById('dispatchOverlay').style.display = 'flex';
  } else {
    const isLP01 = (loc === 'LP01' || loc === 'MASZYNA');
    if (isLP01) {
      openLP01Modal(loc);
      return;
    }

    fetch('/agro/scanner/move', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        surowiec_id: currentPallet.id,
        nr_palety: currentPallet.nr_palety || currentPallet.sscc,
        type: currentPallet.inventory_type,
        lokalizacja: loc,
        linia: LINIA,
        amount_to_move: null
      })
    })
    .then(r => r.json())
    .then(d => {
      showToast(d.message, d.success ? 'success' : 'danger');
      if (d.success) {
        if (d.split_info && d.split_info.is_split && d.split_info.new_sscc) {
          showToast(`✅ Odcięto ${d.split_info.moved_qty} kg na nową paletę (${d.split_info.new_sscc}). Otwieram etykietę...`, 'success');
          window.open(`/agro/scanner/label/${encodeURIComponent(d.split_info.new_sscc)}?linia=${encodeURIComponent(LINIA)}&autoprint=1`, '_blank');
        }
        hidePallet();
        currentPallet = null;
        if (scanInput) {
          scanInput.value = '';
          scanInput.focus();
          scanInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        resetLocationInputDetection();
        refreshSidebarBadgesSilently();
      } else {
        if (loc && loc.length >= 6) {
          lookupPallet(loc);
          return;
        }
        if (scanInput) {
          scanInput.value = '';
          scanInput.focus();
        }
      }
    })
    .catch(e => {
      showToast('Błąd: ' + e, 'danger');
      if (scanInput) {
        scanInput.value = '';
        scanInput.focus();
      }
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
      refreshSidebarBadgesSilently();
    }
  })
  .catch(e => showToast('Błąd: ' + e, 'danger'));
}

function closeDispatchModal() {
  document.getElementById('dispatchOverlay').style.display = 'none';
  pendingProductionLoc = null;
  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
}

let currentLookupCode = null;
let currentLookupPromise = null;

function lookupPallet(code) {
  if (!code) return;
  code = code.trim();
  if (currentLookupCode === code && currentLookupPromise) {
    return currentLookupPromise;
  }
  currentLookupCode = code;
  currentLookupPromise = fetch('/agro/scanner/lookup', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({code, linia: LINIA})
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      if (d.pallet.is_station) {
        showStation(d.pallet);
        showToast(`✅ Znaleziono stację: ${d.pallet.station_code}`, 'success');
      } else {
        showPallet(d.pallet);
        showToast('✅ Znaleziono: ' + d.pallet.nazwa, 'success');
      }
    } else {
      hidePallet();
      hideStation();
      showToast('❌ ' + d.error, 'danger');
    }
  })
  .catch(e => showToast('Błąd sieci: ' + e, 'danger'))
  .finally(() => {
    setTimeout(() => {
      if (currentLookupCode === code) {
        currentLookupCode = null;
        currentLookupPromise = null;
      }
    }, 400);
  });
  return currentLookupPromise;
}

if (scanInput) {
  scanInput.addEventListener('keydown', function(e) {
    if (currentPallet) {
      const key = e.key || '';
      const isManualEditKey = key.length === 1 || key === 'Backspace' || key === 'Delete' || key === 'Spacebar';
      if (isManualEditKey) {
        locationManualTypingDetected = true;
      }
    }

    if (e.key === 'Enter' || e.keyCode === 13 || e.which === 13) {
      e.preventDefault();
      resetLocationInputDetection();
      triggerScan();
    }
  });

  scanInput.addEventListener('input', function() {
    const raw = this.value;
    const cleaned = extractSSCCFromScan(raw);
    if (cleaned !== raw) {
      this.value = cleaned;
    }
    clearTimeout(scanTimeout);

    // Tryb wpisu lokalizacji: autosubmit tylko dla skanu (szybki strumień znaków),
    // bez autosubmitu przy wpisie ręcznym z klawiatury.
    if (currentPallet) {
      const now = Date.now();
      const currLen = this.value.trim().length;

      if (currLen === 0) {
        resetLocationInputDetection();
        return;
      }

      if (locationManualTypingDetected) {
        return;
      }

      const dt = lastLocationInputTs ? (now - lastLocationInputTs) : 0;
      const sameBurst = dt > 0 && dt <= 140 && currLen >= lastLocationInputLen;

      if (!sameBurst || currLen <= 1) {
        locationBurstStartedAt = now;
        locationAutoSubmitArmed = false;
      }

      lastLocationInputTs = now;
      lastLocationInputLen = currLen;

      const burstDuration = Math.max(1, now - locationBurstStartedAt);
      const avgMsPerChar = currLen > 1 ? (burstDuration / (currLen - 1)) : 999;
      const scannerLikeSpeed = currLen >= 4 && avgMsPerChar <= 35;

      if (scannerLikeSpeed && !locationAutoSubmitArmed) {
        locationAutoSubmitArmed = true;
        scanTimeout = setTimeout(() => {
          const code = (scanInput.value || '').trim();
          if (currentPallet && code.length >= 4) {
            triggerScan();
          }
        }, 90);
      }
      return;
    }

    scanTimeout = setTimeout(() => {
      const code = this.value.trim();
      if (!code) return;
      if (!currentPallet && code.length >= 4) {
        triggerScan();
      }
    }, 600);
  });

  scanInput.addEventListener('paste', function() {
    setTimeout(() => {
      const cleaned = extractSSCCFromScan(scanInput.value);
      if (cleaned !== scanInput.value) {
        scanInput.value = cleaned;
      }

      if (currentPallet) {
        locationManualTypingDetected = false;
        locationAutoSubmitArmed = false;
        const code = (scanInput.value || '').trim();
        if (code.length >= 4) {
          triggerScan();
        }
      }
    }, 10);
  });
}

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
