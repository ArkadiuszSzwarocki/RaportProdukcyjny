/* ─── Scanner LP01, Print & Restore Operations ─── */

function openLP01Modal(loc) {
  if (!currentPallet) return;
  const scanInput = document.getElementById('scanInput');
  if (scanInput) scanInput.value = '';
  pendingLP01Loc = loc || 'LP01';
  const overlay = document.getElementById('lp01ModalOverlay');
  if (!overlay) return;

  const matNameEl = document.getElementById('lp01ModalMatName');
  const sourceLocEl = document.getElementById('lp01ModalSourceLoc');
  const maxQtyEl = document.getElementById('lp01ModalMaxQty');
  const qtyInput = document.getElementById('lp01ModalQty');
  const unitEl = document.getElementById('lp01ModalUnit');

  const maxQty = parseFloat(currentPallet.stan_magazynowy || 0);
  const unit = currentPallet.jednostka || currentPallet.unit || 'szt.';

  if (matNameEl) matNameEl.textContent = currentPallet.nazwa || currentPallet.produkt || 'Materiał';
  if (sourceLocEl) sourceLocEl.textContent = currentPallet.lokalizacja || 'Magazyn';
  if (maxQtyEl) maxQtyEl.textContent = `${maxQty} ${unit}`;
  if (unitEl) unitEl.textContent = unit;
  if (qtyInput) {
    const defaultQty = (currentPallet.inventory_type === 'Opakowanie' && maxQty >= 1) ? 1 : maxQty;
    qtyInput.value = defaultQty;
    qtyInput.max = maxQty;
  }

  overlay.style.display = 'flex';
  setTimeout(() => {
    if (qtyInput) {
      qtyInput.focus();
      qtyInput.select();
    }
  }, 100);
}

function closeLP01Modal() {
  const overlay = document.getElementById('lp01ModalOverlay');
  if (overlay) overlay.style.display = 'none';
  const scanInput = document.getElementById('scanInput');
  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
}

function setLP01Qty(val) {
  const qtyInput = document.getElementById('lp01ModalQty');
  if (!qtyInput || !currentPallet) return;
  const maxQty = parseFloat(currentPallet.stan_magazynowy || 0);
  if (val === 'max') {
    qtyInput.value = maxQty;
  } else {
    const num = parseFloat(val);
    if (!isNaN(num) && num > 0) {
      qtyInput.value = Math.min(num, maxQty);
    }
  }
}

function submitLP01Modal() {
  if (!currentPallet) return;
  const qtyInput = document.getElementById('lp01ModalQty');
  const maxQty = parseFloat(currentPallet.stan_magazynowy || 0);
  const parsedQty = parseFloat(qtyInput ? qtyInput.value : 0);

  if (isNaN(parsedQty) || parsedQty <= 0 || (maxQty > 0 && parsedQty > maxQty)) {
    showToast(`Nieprawidłowa ilość (dozwolone od 0.01 do ${maxQty})`, 'danger');
    if (qtyInput) qtyInput.focus();
    return;
  }

  const btn = document.getElementById('btnConfirmLP01');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="animation:spin 1s linear infinite;">refresh</span> Trwa wydanie...';
  }

    const isPackaging = Boolean(
      currentPallet && (
        currentPallet.inventory_type === 'Opakowanie' ||
        currentPallet.is_pkg ||
        currentPallet.unit === 'szt.' ||
        currentPallet.unit === 'szt' ||
        currentPallet.jednostka === 'szt.' ||
        currentPallet.jednostka === 'szt'
      )
    );
    const targetPalletCode = currentPallet ? (currentPallet.nr_palety || 'SUR-' + currentPallet.id) : null;

    fetch('/agro/scanner/move', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        surowiec_id: currentPallet.id,
        nr_palety: currentPallet.nr_palety || currentPallet.sscc,
        type: currentPallet.inventory_type,
        lokalizacja: pendingLP01Loc || 'LP01',
        linia: LINIA,
        amount_to_move: parsedQty
      })
    })
    .then(r => r.json())
    .then(d => {
      showToast(d.message, d.success ? 'success' : 'danger');
      closeLP01Modal();
      if (d.success) {
        if (d.split_info && d.split_info.is_split && d.split_info.new_sscc) {
          if (!isPackaging && (pendingLP01Loc || 'LP01') !== 'LP01' && (pendingLP01Loc || 'LP01') !== 'MASZYNA') {
            showToast(`✅ Odcięto ${d.split_info.moved_qty} kg na nową paletę (${d.split_info.new_sscc}). Otwieram etykietę...`, 'success');
            window.open(`/agro/scanner/label/${encodeURIComponent(d.split_info.new_sscc)}?linia=${encodeURIComponent(LINIA)}&autoprint=1`, '_blank');
          } else {
            const unitStr = isPackaging ? 'szt.' : 'kg';
            showToast(`✅ Pomyślnie wydano ${parsedQty} ${unitStr} na ${pendingLP01Loc || 'LP01'}.`, 'success');
          }
        }
        if (targetPalletCode) {
          lookupPallet(targetPalletCode);
        }
      }
    })
  .catch(e => {
    showToast('Błąd połączenia: ' + e, 'danger');
  })
  .finally(() => {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span class="material-icons" style="font-size:18px;">check</span> Wydaj na LP01';
    }
  });
}

/* ─── Printing operations ─────────────────────────────────── */
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
  .catch(() => {
    showToast('❌ Błąd połączenia przy druku', 'danger');
  });
}

/* ─── Pallet Restore (Archived to Active) ─────────────────── */
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
  const scanInput = document.getElementById('scanInput');
  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
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
