// LINIA is injected globally in HTML
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

function extractSSCCFromScan(value) {
  if (!value) return '';
  let s = String(value).trim();
  if ((s.startsWith('{') && s.endsWith('}')) || (s.includes('"sscc"') || s.includes('"prod"'))) {
    try {
      const match = s.match(/\{[\s\S]*\}/);
      if (match) {
        const parsed = JSON.parse(match[0]);
        if (parsed.sscc) return String(parsed.sscc).trim();
        if (parsed.nr_palety) return String(parsed.nr_palety).trim();
        if (parsed.id) return String(parsed.id).trim();
      }
    } catch (e) {
      const ssccMatch = s.match(/"sscc"\s*:\s*"([^"]+)"/i);
      if (ssccMatch) return ssccMatch[1].trim();
      const nrMatch = s.match(/"nr_palety"\s*:\s*"([^"]+)"/i);
      if (nrMatch) return nrMatch[1].trim();
    }
  }
  return s;
}

function isPalletCode(code) {
  if (!code) return false;
  const s = String(code).trim().toUpperCase();
  const palletPrefixes = ['SUR', 'OPA', 'DOD', 'AGR', 'PSD', 'QA', 'PAL', 'SSCC', 'WYR'];
  if (palletPrefixes.some(p => s.startsWith(p))) return true;
  // Numerical SSCC format (e.g. 10-24 digits)
  if (/^\d{10,24}$/.test(s)) return true;
  // Specific pallet formats
  if (/^PAL-?\d+/i.test(s) || /^SUR-?\d+/i.test(s) || /^OPA-?\d+/i.test(s) || /^DOD-?\d+/i.test(s)) return true;
  
  // Locations regex - if matched, it is a target warehouse/station location
  const isLocation = /^(R0[1-7]\d{4}|BB\d{2}|MZ\d{2}|WZ\d{2}|CZ\d{2}|KO\d{2}|OS\d{2}|MS\d{2}|MP\d{2}|MD\d{2}|MOP\d{2}|MDM\d{2}|PSD\d{0,2}|AGR\d{0,2}|RAMPA|MIX\d{0,2}|BF_)/i.test(s);
  if (isLocation) return false;
  // 6-digit rack code like 020701
  if (/^0[1-7]\d{4}$/.test(s)) return false;

  if (s.length >= 8) return true;
  return false;
}

function resetScanner() {
  hidePallet();
  hideStation();
  scanInput.value = '';
  scanInput.style.borderColor = '';
  scanInput.style.borderWidth = '';
  scanInput.placeholder = 'Wpisz lub zeskanuj kod (np. R030101, SSCC, PAL-15)';
  
  const mainTitle = document.getElementById('scanTitleText');
  if (mainTitle) mainTitle.textContent = 'Skanuj kod regału lub palety';
  const titleIcon = document.getElementById('scanTitleIcon');
  if (titleIcon) {
    titleIcon.textContent = 'barcode_reader';
    titleIcon.style.color = 'var(--primary-color, #3b82f6)';
  }
  const iconEl = document.querySelector('.input-icon');
  if (iconEl) iconEl.style.color = '';
  
  scanInput.focus();
  showToast('🔄 Skaner zresetowany — gotowy do nowego skanu', 'info');
}

function triggerScan() {
  const rawCode = scanInput.value.trim();
  const code = extractSSCCFromScan(rawCode);
  if (code !== rawCode) {
    scanInput.value = code;
  }
  if (code) {
    if (currentPallet) {
      if (isPalletCode(code)) {
        // Użytkownik skanuje kolejną paletę – przełącz na jej podgląd
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

  if (currentPallet && !currentPallet.is_transfer && (currentPallet.is_used_up || parseFloat(currentPallet.stan_magazynowy || 0) <= 0)) {
    showToast('❌ Ta paleta została już zużyta do 0 kg i zarchiwizowana. Nie można jej przenieść ani wydać.', 'danger');
    scanInput.value = '';
    scanInput.focus();
    return;
  }

  if (currentPallet && currentPallet.is_bucket) {
    const cleanLoc = (loc || '').trim().toUpperCase().replace(/[\s\-_]/g, '');
    if (cleanLoc !== 'MI01' && cleanLoc !== 'MI1') {
      showToast(`❌ Nieprawidłowy kod '${loc}'! Wiadro można wrzucić wyłącznie do mieszalnika MI01. Nie można go przenosić na magazyn ani do innych lokalizacji.`, 'danger');
      scanInput.value = '';
      scanInput.focus();
      return;
    }
    // Skanowanie mieszalnika po uprzednim zeskanowaniu wiadra (MI01)
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
    return;
  }

  const isTransfer = Boolean(currentPallet && (currentPallet.is_transfer || currentPallet.is_magazyn_dostawy || currentPallet.transfer));
  if (currentPallet && currentPallet.is_blocked && !isTransfer) {
    showToast('⛔ Ta paleta jest zablokowana ręcznie (blokada magazynowa) i nie może być przesuwana!', 'danger');
    scanInput.value = '';
    scanInput.focus();
    return;
  }

  const isProduction = (loc.startsWith('BB') || loc.startsWith('MZ') || loc.startsWith('WZ') || loc.startsWith('LINIA') || loc.startsWith('Z') || loc.startsWith('CZ') || loc.startsWith('KO') || loc.startsWith('PSD') || loc.startsWith('MIX')) && !loc.startsWith('BF_') && !loc.startsWith('BF');
  
  if (isProduction) {
    // Wyroby gotowe nie mogą być przekazywane na produkcję
    if (currentPallet.inventory_type === 'Wyrób Gotowy') {
      showToast('❌ Wyrobów gotowych nie można przekazać na produkcję', 'danger');
      scanInput.value = '';
      scanInput.focus();
      return;
    }
    if (currentPallet.inventory_type === 'Opakowanie') {
      showToast('❌ Opakowań nie można przekazać do stacji produkcyjnej', 'danger');
      scanInput.value = '';
      scanInput.focus();
      return;
    }

    // Walidacja stacji / zbiornika przed otwarciem modala przekazania na produkcję
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
        scanInput.value = '';
        scanInput.focus();
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
    fetch('/agro/scanner/move', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        surowiec_id: currentPallet.id,
        nr_palety: currentPallet.nr_palety || currentPallet.sscc,
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
        if (loc && loc.length >= 6) {
          lookupPallet(loc);
          return;
        }
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
  const raw = this.value;
  const cleaned = extractSSCCFromScan(raw);
  if (cleaned !== raw) {
    this.value = cleaned;
  }
  clearTimeout(scanTimeout);
  scanTimeout = setTimeout(() => {
    const code = this.value.trim();
    if (code && code.length >= 5 && !document.getElementById('palletCard').classList.contains('visible')) {
      // Wywołaj automatycznie jeśli skaner Zebra po prostu wrzuca tekst
      triggerScan();
    }
  }, 1200);
});

scanInput.addEventListener('paste', function(e) {
  setTimeout(() => {
    const cleaned = extractSSCCFromScan(scanInput.value);
    if (cleaned !== scanInput.value) {
      scanInput.value = cleaned;
    }
  }, 10);
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
  .catch(e => showToast('Błąd sieci: ' + e, 'danger'));
}

function showStation(station) {
  hidePallet();
  const stationCard = document.getElementById('stationCard');
  const stationCodeEl = document.getElementById('stationCode');
  const itemsListEl = document.getElementById('stationItemsList');
  const noStationMsg = document.getElementById('nostationMsg');

  stationCodeEl.textContent = station.station_code;
  itemsListEl.innerHTML = '';

  if (station.items && station.items.length > 0) {
    station.items.forEach(item => {
      const itemEl = document.createElement('div');
      itemEl.className = 'station-item';
      itemEl.onclick = () => showPallet(item);
      
      itemEl.innerHTML = `
        <div class="station-item-name">${item.nazwa}</div>
        <div class="station-item-details">
          <span><strong>Ilość:</strong> ${parseFloat(item.stan_magazynowy).toFixed(1)} kg</span>
          <span><strong>ID:</strong> ${item.inventory_code}</span>
          ${item.nr_partii ? `<span><strong>Partia:</strong> ${item.nr_partii}</span>` : ''}
        </div>
      `;
      itemsListEl.appendChild(itemEl);
    });
    noStationMsg.style.display = 'none';
  } else {
    noStationMsg.style.display = 'block';
  }

  stationCard.style.display = 'block';
  scanInput.value = '';
  scanInput.focus();
}

function hideStation() {
  const stationCard = document.getElementById('stationCard');
  if (stationCard) {
    stationCard.style.display = 'none';
  }
}

function showPallet(p) {
  if (p.is_unconfirmed_wg) {
    openWgAcceptModal(p);
    return;
  }
  currentPallet = p;
  if (p.lokalizacja === 'OCZEKUJĄCE' && p.source_location) {
    document.getElementById('palletLoc').innerHTML = `<span style="color: #d97706; font-weight: bold;">OCZEKUJĄCE</span> <span style="font-size: 11px; font-weight: normal; color: #64748b;">(z: ${p.source_location})</span>`;
  } else {
    document.getElementById('palletLoc').textContent  = p.lokalizacja || '—';
  }
  document.getElementById('palletName').textContent = p.nazwa;
  const idVal = document.getElementById('palletIdVal');
  if (idVal) {
    idVal.textContent = p.id ? `#${p.id}` : '—';
  }
  const histBtn = document.getElementById('palletHistoryBtn');
  if (histBtn) {
    histBtn.style.display = 'inline-flex';
  }
  if (p.is_bucket) {
    document.querySelector('.pallet-qty').innerHTML = `<span id="palletQty">${parseInt(p.stan_magazynowy, 10)}</span> ${p.jednostka || 'składniki'}`;
  } else if (p.unit === 'szt.' || p.unit === 'szt' || p.inventory_type === 'Opakowanie' || p.is_pkg) {
    const rawVal = parseFloat(p.stan_magazynowy || 0);
    const qtyFormatted = Number.isInteger(rawVal) ? String(parseInt(rawVal, 10)) : rawVal.toFixed(1);
    document.querySelector('.pallet-qty').innerHTML = `<span id="palletQty">${qtyFormatted}</span> ${p.unit || 'szt.'}`;
  } else {
    document.querySelector('.pallet-qty').innerHTML = `<span id="palletQty">${parseFloat(p.stan_magazynowy || 0).toFixed(1)}</span> ${p.unit || 'kg'}`;
  }
  
  // Badge typu palety
  const isTransferOrder = Boolean(p.is_transfer || p.is_magazyn_dostawy || p.transfer);
  const isUsedUp = !isTransferOrder && (p.is_used_up || parseFloat(p.stan_magazynowy || 0) <= 0);
  const isBlocked = Boolean(p.is_blocked) && !isTransferOrder;
  const isPending = isTransferOrder || (p.lokalizacja && (p.lokalizacja.toUpperCase().includes('OCZEK') || p.lokalizacja.toUpperCase().includes('TRANZYT')));
  const typePill = document.getElementById('palletTypePill');
  if (typePill) {
    const invType = p.inventory_type || 'Surowiec';
    if (isTransferOrder) {
      const trfCode = (p.transfer && p.transfer.transfer_code) || 'ZLECENIE';
      typePill.textContent = `📦 W ZLECENIU: ${trfCode} (PRZYJĘCIE W LOCIE)`;
      typePill.className = 'pill';
      typePill.style.background = '#0284c7';
      typePill.style.color = '#fff';
    } else if (isBlocked) {
      typePill.textContent = '⛔ ZABLOKOWANA (BLOKADA MAGAZYNOWA)';
      typePill.className = 'pill';
      typePill.style.background = '#dc2626';
      typePill.style.color = '#fff';
    } else if (isUsedUp) {
      typePill.textContent = 'Zużyta / Rozchodowana';
      typePill.className = 'pill';
      typePill.style.background = '#ef4444';
      typePill.style.color = '#fff';
    } else if (isPending) {
      typePill.className = 'pill';
      typePill.style.background = '#f59e0b';
      typePill.style.color = '#fff';
      typePill.textContent = p.status_info ? `⏳ ${p.status_pl || 'Oczekuje na przyjęcie'} (${p.status_info})` : `⏳ ${p.status_pl || 'Oczekuje na przyjęcie'}`;
    } else if (p.is_bucket) {
      typePill.className = 'pill';
      typePill.style.background = '#8b5cf6';
      typePill.style.color = '#fff';
      typePill.textContent = p.status_pl || invType;
    } else if (invType === 'Wyrób Gotowy') {
      typePill.className = 'pill';
      typePill.style.background = '#10b981';
      typePill.style.color = '#fff';
      typePill.textContent = invType;
    } else if (invType === 'Surowiec') {
      typePill.className = 'pill';
      typePill.style.background = '#3b82f6';
      typePill.style.color = '#fff';
      typePill.textContent = invType;
    } else if (invType === 'Opakowanie') {
      typePill.className = 'pill';
      typePill.style.background = '#f59e0b';
      typePill.style.color = '#fff';
      typePill.textContent = invType;
    } else {
      typePill.className = 'pill';
      typePill.style.background = '#64748b';
      typePill.style.color = '#fff';
      typePill.textContent = invType;
    }
    typePill.style.display = 'inline-block';
  }
  
  // Extra details
  document.getElementById('palletSSCC').textContent = p.nr_palety || p.inventory_code || '—';
  document.getElementById('palletPartia').textContent = p.nr_partii || '—';
  document.getElementById('palletDataProd').textContent = p.data_produkcji || '—';
  document.getElementById('palletDataWaz').textContent = p.data_przydatnosci || '—';

  // Check if pallet is on a production station
  const locUpper = (p.lokalizacja || '').toUpperCase();
  const isProductionStation = !isUsedUp && (locUpper.startsWith('BB') || locUpper.startsWith('MZ') || locUpper.startsWith('WZ') || locUpper.startsWith('Z') || locUpper.startsWith('CZ') || locUpper.startsWith('KO') || locUpper.startsWith('PSD') || locUpper.startsWith('MIX')) && !locUpper.startsWith('BF_') && !locUpper.startsWith('BF');
  
  const returnBtn = document.getElementById('scannerReturnBtnContainer');
  if (returnBtn) {
    returnBtn.style.display = isProductionStation ? 'block' : 'none';
  }

  // Obsługa przycisku przywracania palety ze stanu zużycia (MasterAdmin i Liderzy)
  const restoreBtn = document.getElementById('scannerRestoreBtnContainer');
  if (restoreBtn) {
    const canRestore = Boolean((typeof CAN_RESTORE_PALLET !== 'undefined' ? CAN_RESTORE_PALLET : window.CAN_RESTORE_PALLET) && isUsedUp);
    restoreBtn.style.display = canRestore ? 'block' : 'none';
  }

  document.getElementById('palletCard').classList.add('visible');
  document.getElementById('nopalletMsg').style.display = 'none';

  // Zmień główny input skanera na tryb lokalizacji lub tryb nowej palety jeśli zużyta
  const mainTitle = document.getElementById('scanTitleText');
  const titleIcon = document.getElementById('scanTitleIcon');
  const iconEl = document.querySelector('.input-icon');

  if (isTransferOrder) {
    if (mainTitle) mainTitle.textContent = 'Zeskanuj regał docelowy (przyjęcie w locie)';
    if (titleIcon) {
      titleIcon.textContent = 'move_to_inbox';
      titleIcon.style.color = '#0284c7';
    }
    scanInput.placeholder = 'Zeskanuj regał docelowy (np. R040101 lub MP01)...';
    scanInput.style.borderColor = '#0284c7';
    scanInput.style.borderWidth = '2px';
    if (iconEl) iconEl.style.color = '#0284c7';
  } else if (isBlocked) {
    if (mainTitle) mainTitle.textContent = '⛔ Paleta zablokowana — nie można przesunąć!';
    if (titleIcon) {
      titleIcon.textContent = 'block';
      titleIcon.style.color = '#dc2626';
    }
    scanInput.placeholder = 'Paleta zablokowana ręcznie — zeskanuj inną...';
    scanInput.style.borderColor = '#dc2626';
    scanInput.style.borderWidth = '2px';
    if (iconEl) iconEl.style.color = '#dc2626';
  } else if (isUsedUp) {
    if (mainTitle) mainTitle.textContent = 'Paleta zużyta (0 kg) — zeskanuj nową paletę';
    if (titleIcon) {
      titleIcon.textContent = 'block';
      titleIcon.style.color = '#ef4444';
    }
    scanInput.placeholder = 'Paleta zużyta (0 kg) — zeskanuj inny kod...';
    scanInput.style.borderColor = '#ef4444';
    scanInput.style.borderWidth = '2px';
    if (iconEl) iconEl.style.color = '#ef4444';
  } else {
    if (mainTitle) mainTitle.textContent = 'Zeskanuj lokalizację docelową';
    if (titleIcon) {
      titleIcon.textContent = 'place';
      titleIcon.style.color = '#2563eb';
    }
    scanInput.placeholder = 'np. R040101 lub BB01 (lub zeskanuj inną paletę)';
    scanInput.style.borderColor = '#2563eb';
    scanInput.style.borderWidth = '2px';
    if (iconEl) iconEl.style.color = '#2563eb';
  }

  scanInput.value = '';
  scanInput.focus();
  pendingProductionLoc = null;

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
  
  const idVal = document.getElementById('palletIdVal');
  if (idVal) idVal.textContent = '—';

  const histBtn = document.getElementById('palletHistoryBtn');
  if (histBtn) histBtn.style.display = 'none';
  closeScannerHistoryModal();

  const typePill = document.getElementById('palletTypePill');
  if (typePill) typePill.style.display = 'none';

  const restoreBtn = document.getElementById('scannerRestoreBtnContainer');
  if (restoreBtn) restoreBtn.style.display = 'none';
  
  const barContainer = document.getElementById('palletTimeoutBarContainer');
  if (barContainer) barContainer.style.display = 'none';

  const mainTitle = document.getElementById('scanTitleText');
  if (mainTitle) mainTitle.textContent = 'Skanuj kod regału lub palety';
  const titleIcon = document.getElementById('scanTitleIcon');
  if (titleIcon) {
    titleIcon.textContent = 'barcode_reader';
    titleIcon.style.color = 'var(--primary-color, #3b82f6)';
  }
  scanInput.placeholder = 'Wpisz lub zeskanuj kod (np. R030101, SSCC, PAL-15)';
  scanInput.style.borderColor = '';
  scanInput.style.borderWidth = '';
  const iconEl = document.querySelector('.input-icon');
  if(iconEl) iconEl.style.color = '';
}
hidePallet();
hideStation();

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
    sscc: currentPallet.nr_palety || currentPallet.sscc || '',
    nr_palety: currentPallet.nr_palety || currentPallet.sscc || '',
    surowiec_id: currentPallet.id,
    pallet_type: currentPallet.inventory_type || currentPallet.typ || '',
    type: currentPrintType,
    linia: currentPallet.linia || LINIA
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
  const overlay = document.getElementById('wgAcceptOverlay');
  const palletNoEl = document.getElementById('wgPalletNo');
  const palletNameEl = document.getElementById('wgPalletName');
  const weightInput = document.getElementById('wgWeightInput');
  const locInput = document.getElementById('wgLocInput');

  if (palletNoEl) palletNoEl.textContent = p.nr_palety || 'ID: ' + p.id;
  if (palletNameEl) palletNameEl.textContent = p.nazwa || '';
  if (weightInput) weightInput.value = parseFloat(p.stan_magazynowy || 0).toFixed(1);
  if (locInput) locInput.value = '';
  
  backToWgStep1();
  
  if (overlay) {
    overlay.style.display = 'flex';
    setTimeout(() => {
      if (weightInput) {
        weightInput.focus();
        weightInput.select();
      }
    }, 100);
  }
}

function closeWgAcceptModal() {
  const overlay = document.getElementById('wgAcceptOverlay');
  if (overlay) overlay.style.display = 'none';
  wgPalletObj = null;
  scanInput.value = '';
  scanInput.focus();
}

function goToWgStep2() {
  const weightInput = document.getElementById('wgWeightInput');
  const wVal = weightInput ? parseFloat(weightInput.value) : 0;
  if (!wVal || wVal <= 0) {
    showToast('Wprowadź prawidłową wagę', 'warn');
    return;
  }
  const stepWeight = document.getElementById('wgStepWeight');
  const stepLoc = document.getElementById('wgStepLocation');
  const backBtn = document.getElementById('wgBackBtn');
  const nextBtn = document.getElementById('wgNextBtn');
  const confirmBtn = document.getElementById('wgConfirmBtn');

  if (stepWeight) stepWeight.style.display = 'none';
  if (stepLoc) stepLoc.style.display = 'block';
  if (backBtn) backBtn.style.display = 'inline-block';
  if (nextBtn) nextBtn.style.display = 'none';
  if (confirmBtn) confirmBtn.style.display = 'inline-block';
  
  setTimeout(() => {
    const locInp = document.getElementById('wgLocInput');
    if (locInp) {
      locInp.focus();
      locInp.select();
    }
  }, 100);
}

function backToWgStep1() {
  const stepWeight = document.getElementById('wgStepWeight');
  const stepLoc = document.getElementById('wgStepLocation');
  const backBtn = document.getElementById('wgBackBtn');
  const nextBtn = document.getElementById('wgNextBtn');
  const confirmBtn = document.getElementById('wgConfirmBtn');

  if (stepWeight) stepWeight.style.display = 'block';
  if (stepLoc) stepLoc.style.display = 'none';
  if (backBtn) backBtn.style.display = 'none';
  if (nextBtn) nextBtn.style.display = 'inline-block';
  if (confirmBtn) confirmBtn.style.display = 'none';
  
  setTimeout(() => {
    const wInp = document.getElementById('wgWeightInput');
    if (wInp) {
      wInp.focus();
      wInp.select();
    }
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
function showToast(msg, type) {
  playBeep(type);
  const container = document.getElementById('toast-container');
  if (!container) return; // Zabezpieczenie, gdyby brakowało kontenera na innej stronie

  const el = document.createElement('div');
  el.className = 'toast-msg';
  
  const colors = {success:'#166534', warn:'#92400e', danger:'#991b1b'};
  el.style.background = colors[type] || '#0f172a';
  el.innerHTML = msg;

  container.appendChild(el);

  // Usuń powiadomienie po 10 sekundach
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 500); // 500ms to czas transition: opacity w CSS
  }, 10000);
}

/* ─── Scanner Return to Warehouse ─────────────────────────── */
function openScannerReturnModal() {
  if (!currentPallet) return;
  
  const loc = currentPallet.lokalizacja || 'Nieznana stacja';
  const maxQty = parseFloat(currentPallet.stan_magazynowy) || 0;
  
  document.getElementById('scannerReturnLoc').textContent = loc;
  document.getElementById('scannerReturnQty').value = maxQty > 0 ? maxQty : '';
  document.getElementById('scannerReturnMaxQty').textContent = maxQty > 0 ? `Max: ${maxQty.toFixed(1)} kg` : '';
  
  document.getElementById('scannerReturnOverlay').style.display = 'flex';
  setTimeout(() => document.getElementById('scannerReturnQty').focus(), 100);
}

function closeScannerReturnModal() {
  document.getElementById('scannerReturnOverlay').style.display = 'none';
  scanInput.focus();
}

function submitScannerReturn() {
  if (!currentPallet) return;
  
  const qtyInput = document.getElementById('scannerReturnQty');
  const qty = parseFloat(qtyInput.value);
  const maxQty = parseFloat(currentPallet.stan_magazynowy) || 0;
  
  if (isNaN(qty) || qty <= 0) {
    showToast('Podaj prawidłową ilość większą od 0', 'warn');
    return;
  }
  
  if (maxQty > 0 && qty > maxQty) {
    showToast(`Ilość nie może być większa niż ${maxQty.toFixed(1)} kg`, 'danger');
    return;
  }
  
  fetch('/agro/api/return', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      surowiec_id: currentPallet.id,
      ilosc: qty,
      ruch_produkcja_id: null,
      komentarz: `Zwrot przez skaner ze stacji ${currentPallet.lokalizacja}`,
      linia: LINIA,
      lokalizacja: 'ZWROT'
    })
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      const ssccMsg = d.new_sscc ? ` (Nowy SSCC: ${d.new_sscc})` : '';
      showToast(`Pomyślnie zwrócono ${qty} kg${ssccMsg}. Paleta trafiła do Oczekujących.`, 'success');
      closeScannerReturnModal();
      hidePallet();
    } else {
      showToast('Błąd: ' + (d.error || 'Nieznany błąd'), 'danger');
    }
  })
  .catch(e => {
    console.error('Błąd zwrotu:', e);
    showToast('Błąd połączenia z serwerem', 'danger');
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Przywracanie palety z zużycia (MasterAdmin & Liderzy)
// ─────────────────────────────────────────────────────────────────────────────

function openScannerRestoreModal() {
  if (!currentPallet) return;
  const overlay = document.getElementById('scannerRestoreOverlay');
  if (!overlay) return;

  const nameEl = document.getElementById('restoreModalPalletName');
  if (nameEl) nameEl.textContent = currentPallet.nazwa || 'Paleta';

  const ssccEl = document.getElementById('restoreModalSSCC');
  if (ssccEl) ssccEl.textContent = currentPallet.nr_palety || currentPallet.inventory_code || '-';

  const batchEl = document.getElementById('restoreModalBatch');
  if (batchEl) batchEl.textContent = currentPallet.nr_partii || '-';

  const wInput = document.getElementById('restoreModalWeight');
  if (wInput) {
    const w = parseFloat(currentPallet.waga_ostatnia || 0);
    wInput.value = w > 0 ? w : '';
  }

  const lInput = document.getElementById('restoreModalLocation');
  if (lInput) {
    let loc = currentPallet.lokalizacja_ostatnia || currentPallet.lokalizacja || 'MP01';
    loc = loc.replace(/^ZUZYTA\s*\(/i, '').replace(/\)$/, '').trim();
    lInput.value = loc || 'MP01';
  }

  overlay.style.display = 'flex';
  setTimeout(() => {
    if (wInput) wInput.focus();
  }, 100);
}

function closeScannerRestoreModal() {
  const overlay = document.getElementById('scannerRestoreOverlay');
  if (overlay) overlay.style.display = 'none';
}

async function confirmScannerRestore() {
  if (!currentPallet) return;

  const btn = document.getElementById('btnConfirmScannerRestore');
  const wInput = document.getElementById('restoreModalWeight');
  const lInput = document.getElementById('restoreModalLocation');

  const weightVal = parseFloat(wInput.value);
  if (isNaN(weightVal) || weightVal < 0) {
    showToast('Podaj poprawną wagę palety (większą lub równą 0 kg).', 'warning');
    wInput.focus();
    return;
  }

  const locVal = (lInput.value || '').trim().toUpperCase();
  if (!locVal) {
    showToast('Podaj lokalizację docelową dla przywracanej palety.', 'warning');
    lInput.focus();
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="animation:spin 1s linear infinite;">refresh</span> Trwa przywracanie...';
  }

  try {
    const res = await fetch('/agro/scanner/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        archive_id: currentPallet.archive_id,
        nr_palety: currentPallet.nr_palety,
        waga: weightVal,
        lokalizacja: locVal
      })
    });

    const data = await res.json();
    if (!data.success) {
      showToast(data.error || 'Błąd przywracania palety', 'danger');
      return;
    }

    showToast(data.message || 'Paleta została pomyślnie przywrócona!', 'success');
    closeScannerRestoreModal();

    // Automatycznie odśwież widok w skanerze, aby pokazać aktywną paletę
    const targetCode = currentPallet.nr_palety || locVal;
    setTimeout(() => {
      lookupPallet(targetCode);
    }, 400);

  } catch (err) {
    console.error('Błąd przywracania:', err);
    showToast('Błąd połączenia z serwerem podczas przywracania palety.', 'danger');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span class="material-icons" style="font-size:18px;">check</span> Przywróć na stan';
    }
  }
}

/* ─── Pallet History Modal ───────────────────────────────── */
function openScannerHistoryModal() {
  if (!currentPallet) {
    showToast('Najpierw zeskanuj paletę', 'info');
    return;
  }
  const overlay = document.getElementById('scannerHistoryOverlay');
  if (!overlay) return;

  overlay.style.display = 'flex';

  const nameEl = document.getElementById('histModalPalletName');
  if (nameEl) nameEl.textContent = currentPallet.nazwa || 'Nieznany produkt';

  const ssccEl = document.getElementById('histModalSSCC');
  if (ssccEl) ssccEl.textContent = currentPallet.nr_palety || '—';

  const idEl = document.getElementById('histModalId');
  if (idEl) idEl.textContent = currentPallet.id ? `#${currentPallet.id}` : '—';

  const qtyEl = document.getElementById('histModalQty');
  if (qtyEl) {
    const rawVal = parseFloat(currentPallet.stan_magazynowy || 0);
    const qtyFormatted = Number.isInteger(rawVal) ? String(parseInt(rawVal, 10)) : rawVal.toFixed(1);
    qtyEl.textContent = `${qtyFormatted} ${currentPallet.unit || 'kg'}`;
  }

  const locEl = document.getElementById('histModalLoc');
  if (locEl) locEl.textContent = currentPallet.lokalizacja || '—';

  fetchScannerHistory();
}

function closeScannerHistoryModal() {
  const overlay = document.getElementById('scannerHistoryOverlay');
  if (overlay) overlay.style.display = 'none';
}

function fetchScannerHistory() {
  if (!currentPallet) return;

  const loadingEl = document.getElementById('histModalLoading');
  const emptyEl = document.getElementById('histModalEmpty');
  const timelineEl = document.getElementById('histModalTimeline');
  const countEl = document.getElementById('histModalCount');

  if (loadingEl) loadingEl.style.display = 'block';
  if (emptyEl) emptyEl.style.display = 'none';
  if (timelineEl) {
    timelineEl.style.display = 'none';
    timelineEl.innerHTML = '';
  }

  const palletId = currentPallet.id || currentPallet.nr_palety;
  const palletType = currentPallet.inventory_type || currentPallet.typ || currentPallet.type || 'Surowiec';
  const liniaVal = typeof LINIA !== 'undefined' ? LINIA : (currentPallet.linia || 'AGRO');

  const url = `/agro/scanner/pallet/history?id=${encodeURIComponent(palletId)}&type=${encodeURIComponent(palletType)}&linia=${encodeURIComponent(liniaVal)}`;

  fetch(url)
    .then(r => r.json())
    .then(data => {
      if (loadingEl) loadingEl.style.display = 'none';
      if (data.success && data.history && data.history.length > 0) {
        if (countEl) countEl.textContent = `Wpisów: ${data.history.length}`;
        if (timelineEl) {
          timelineEl.style.display = 'flex';
          timelineEl.innerHTML = renderHistoryTimeline(data.history);
        }
      } else {
        if (countEl) countEl.textContent = 'Wpisów: 0';
        if (emptyEl) emptyEl.style.display = 'block';
      }
    })
    .catch(err => {
      console.error('Błąd pobierania historii:', err);
      if (loadingEl) loadingEl.style.display = 'none';
      if (emptyEl) {
        emptyEl.style.display = 'block';
        emptyEl.innerHTML = `
          <span class="material-icons" style="font-size:32px; color:#ef4444;">error_outline</span>
          <div style="font-size:13px; font-weight:600; color:#ef4444; margin-top:8px;">Błąd pobierania historii: ${err.message || err}</div>
        `;
      }
    });
}

function renderHistoryTimeline(items) {
  const getActionConfig = (actionRaw) => {
    const a = String(actionRaw || '').toUpperCase();
    if (a.includes('ZWROT')) {
      return { label: a.replace(/_/g, ' '), bg: '#ecfdf5', border: '#a7f3d0', text: '#065f46', icon: 'keyboard_return' };
    }
    if (a.includes('WYDANIE') || a.includes('PRODUKCJA')) {
      return { label: a.replace(/_/g, ' '), bg: '#fffbeb', border: '#fde68a', text: '#92400e', icon: 'precision_manufacturing' };
    }
    if (a.includes('PRZYJECIE') || a.includes('DOSTAWA')) {
      return { label: a.replace(/_/g, ' '), bg: '#f0fdf4', border: '#bbf7d0', text: '#15803d', icon: 'inventory_2' };
    }
    if (a.includes('PODZIAL')) {
      return { label: a.replace(/_/g, ' '), bg: '#faf5ff', border: '#e9d5ff', text: '#6b21a8', icon: 'call_split' };
    }
    if (a.includes('PRZESUNIECIE')) {
      return { label: a.replace(/_/g, ' '), bg: '#eff6ff', border: '#bfdbfe', text: '#1d4ed8', icon: 'swap_horiz' };
    }
    if (a.includes('PRZYWROC')) {
      return { label: a.replace(/_/g, ' '), bg: '#f0fdfa', border: '#99f6e4', text: '#0f766e', icon: 'restore' };
    }
    if (a.includes('EDYCJA') || a.includes('KOREKTA')) {
      return { label: a.replace(/_/g, ' '), bg: '#fff1f2', border: '#fecdd3', text: '#be123c', icon: 'edit' };
    }
    return { label: a.replace(/_/g, ' ') || 'RUCH', bg: '#f1f5f9', border: '#cbd5e1', text: '#334155', icon: 'history' };
  };

  return items.map((item) => {
    const cfg = getActionConfig(item.typ_ruchu);
    const dateStr = item.autor_data || '—';
    const userStr = item.autor_login ? `@${item.autor_login}` : '';
    const commentStr = item.komentarz || '';

    let routeHtml = '';
    if (item.lokalizacja_zrodlowa || item.lokalizacja_docelowa) {
      routeHtml = `
        <div style="display:inline-flex; align-items:center; gap:4px; font-size:11px; font-weight:700; color:#2563eb; background:#eff6ff; padding:2px 8px; border-radius:4px; margin-top:4px;">
          <span>${item.lokalizacja_zrodlowa || '—'}</span>
          <span class="material-icons" style="font-size:12px;">arrow_forward</span>
          <span>${item.lokalizacja_docelowa || '—'}</span>
        </div>
      `;
    }

    return `
      <div style="position:relative; padding-left:24px; border-left:2px solid #e2e8f0; padding-bottom:6px;">
        <div style="position:absolute; left:-7px; top:3px; width:12px; height:12px; border-radius:50%; background:${cfg.text}; border:2px solid #ffffff; box-shadow:0 0 0 1px #cbd5e1;"></div>
        
        <div style="background:#ffffff; border:1px solid ${cfg.border}; border-radius:10px; padding:10px 12px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:4px;">
            <div style="display:inline-flex; align-items:center; gap:4px; background:${cfg.bg}; color:${cfg.text}; border:1px solid ${cfg.border}; border-radius:4px; padding:2px 6px; font-size:11px; font-weight:800;">
              <span class="material-icons" style="font-size:13px;">${cfg.icon}</span>
              <span>${cfg.label}</span>
            </div>
            <div style="font-size:11px; color:#64748b; font-weight:600;">
              <span>${dateStr}</span>
              ${userStr ? `<span style="color:#0f172a; margin-left:4px;">(${userStr})</span>` : ''}
            </div>
          </div>
          
          ${routeHtml}
          
          ${commentStr ? `<div style="font-size:12px; color:#334155; margin-top:5px; line-height:1.4; word-break:break-word;">${commentStr}</div>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

// Zamknięcie modala historii przy kliknięciu poza okno
window.addEventListener('click', function(e) {
  const overlay = document.getElementById('scannerHistoryOverlay');
  if (e.target === overlay) {
    closeScannerHistoryModal();
  }
});
