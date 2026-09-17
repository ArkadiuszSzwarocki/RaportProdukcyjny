/* ─── Scanner Modal Handlers (WG Acceptance, LP01, Split, Return, Restore, Print) ─── */

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
  const scanInput = document.getElementById('scanInput');
  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
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
      if (d.open_report_url) {
        var win = window.open(d.open_report_url, '_blank');
        if (!win || win.closed || typeof win.closed === 'undefined') {
          window.location.href = d.open_report_url;
        }
      }
    } else {
      showToast('❌ ' + (d.error || d.message || 'Błąd zapisu'), 'danger');
    }
  })
  .catch(e => showToast('Błąd: ' + e, 'danger'));
}

/* ─── Scanner Return to Warehouse Modal ───────────────────── */
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
  const scanInput = document.getElementById('scanInput');
  if (scanInput) scanInput.focus();
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

/* ─── Scanner Pallet Split (Odcięcie z nową etykietą) ──────── */
function openScannerSplitModal() {
  if (!currentPallet) return;
  const maxQty = parseFloat(currentPallet.stan_magazynowy) || 0;
  const availEl = document.getElementById('scannerSplitAvailableQty');
  if (availEl) availEl.textContent = maxQty.toFixed(1);
  const qtyInput = document.getElementById('scannerSplitQty');
  if (qtyInput) qtyInput.value = '';
  const locInput = document.getElementById('scannerSplitTargetLoc');
  if (locInput) locInput.value = '';
  const overlay = document.getElementById('scannerSplitOverlay');
  if (overlay) overlay.style.display = 'flex';
  setTimeout(() => {
    if (locInput) locInput.focus();
  }, 100);
}

function closeScannerSplitModal() {
  const overlay = document.getElementById('scannerSplitOverlay');
  if (overlay) overlay.style.display = 'none';
  const scanInput = document.getElementById('scanInput');
  if (scanInput) scanInput.focus();
}

function submitScannerSplit() {
  if (!currentPallet) return;
  const locInput = document.getElementById('scannerSplitTargetLoc');
  const targetLoc = locInput ? locInput.value.trim().toUpperCase() : '';
  const qtyInput = document.getElementById('scannerSplitQty');
  const qty = parseFloat(qtyInput.value);
  const maxQty = parseFloat(currentPallet.stan_magazynowy) || 0;

  if (!targetLoc) {
    showToast('Wpisz lub zeskanuj lokalizację docelową!', 'warn');
    if (locInput) locInput.focus();
    return;
  }
  if (isNaN(qty) || qty <= 0) {
    showToast('Podaj wagę do odcięcia większą od 0!', 'warn');
    if (qtyInput) qtyInput.focus();
    return;
  }
  if (qty >= maxQty) {
    showToast(`Ilość do odcięcia (${qty} kg) musi być mniejsza niż dostępna masa (${maxQty} kg). Aby przenieść całość, użyj zwykłego przesunięcia.`, 'warn');
    return;
  }

  const btn = document.getElementById('btnConfirmScannerSplit');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="animation:spin 1s linear infinite;">refresh</span> Trwa podział...';
  }

  fetch('/agro/scanner/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      surowiec_id: currentPallet.id,
      nr_palety: currentPallet.nr_palety || currentPallet.sscc,
      type: currentPallet.inventory_type || 'Surowiec',
      lokalizacja: targetLoc,
      linia: LINIA,
      amount_to_move: qty
    })
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      closeScannerSplitModal();
      if (d.split_info && d.split_info.is_split && d.split_info.new_sscc) {
        showToast(`✅ Odcięto ${d.split_info.moved_qty} kg na nową paletę (${d.split_info.new_sscc}). Otwieram nową etykietę...`, 'success');
        window.open(`/agro/scanner/label/${encodeURIComponent(d.split_info.new_sscc)}?linia=${encodeURIComponent(LINIA)}&autoprint=1`, '_blank');
      } else {
        showToast(d.message || 'Podzielono paletę', 'success');
      }
      window.hideAfterLoad = true;
      lookupPallet(currentPallet.nr_palety || 'SUR-' + currentPallet.id);
    } else {
      showToast(d.message || d.error || 'Błąd podziału palety', 'danger');
    }
  })
  .catch(e => {
    showToast('Błąd połączenia z serwerem: ' + e, 'danger');
  })
  .finally(() => {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span class="material-icons" style="font-size:18px;">print</span> Podziel i drukuj etykietę';
    }
  });
}
