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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: wgPalletObj.id,
      nr_palety: wgPalletObj.nr_palety,
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
let scannerReturnPallet = null;
function openScannerReturnModal(pallet = currentPallet) {
  if (!pallet) return;
  scannerReturnPallet = { ...pallet };
  const loc = pallet.lokalizacja || 'Nieznana stacja';
  const maxQty = parseFloat(pallet.stan_magazynowy) || 0;

  document.getElementById('scannerReturnLoc').textContent = loc;
  document.getElementById('scannerReturnQty').value = maxQty > 0 ? maxQty : '';
  document.getElementById('scannerReturnMaxQty').textContent = maxQty > 0 ? `Max: ${maxQty.toFixed(1)} kg` : '';

  document.getElementById('scannerReturnOverlay').style.display = 'flex';
  setTimeout(() => document.getElementById('scannerReturnQty').focus(), 100);
}

function closeScannerReturnModal() {
  scannerReturnPallet = null;
  document.getElementById('scannerReturnOverlay').style.display = 'none';
  const scanInput = document.getElementById('scanInput');
  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
}

function submitScannerReturn() {
  const pallet = scannerReturnPallet;
  if (!pallet) return;
  const qtyInput = document.getElementById('scannerReturnQty');
  const qty = parseFloat(qtyInput.value);
  const maxQty = parseFloat(pallet.stan_magazynowy) || 0;

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
      surowiec_id: pallet.id,
      ilosc: qty,
      ruch_produkcja_id: pallet.ruch_produkcja_id || null,
      plan_id: pallet.plan_id || null,
      komentarz: `Zwrot przez skaner ze stacji ${pallet.lokalizacja}`,
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
        hideStation();
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
  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
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
        const isPkg = Boolean(
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
        if (d.split_info && d.split_info.is_split && d.split_info.new_sscc) {
          if (!isPkg) {
            showToast(`✅ Odcięto ${d.split_info.moved_qty} kg na nową paletę (${d.split_info.new_sscc}). Drukowanie etykiety...`, 'success');
            if (typeof window.printSplitPalletLabel === 'function') {
              window.printSplitPalletLabel(d.split_info.new_sscc, typeof LINIA !== 'undefined' ? LINIA : 'AGRO');
            }
          } else {
            showToast(`✅ Pomyślnie odcięto ${d.split_info.moved_qty} szt. opakowania (${d.split_info.new_sscc}).`, 'success');
          }
        }
        if (targetPalletCode) {
          lookupPallet(targetPalletCode);
        }
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

/* ─── Single Sub-Roll Addition Modal (kg / szt) ─────── */
let _scannerTapeSplitMode = 'kg'; // 'kg' | 'szt'

function _parseScannerTapeDecimal(raw) {
  if (raw === null || raw === undefined) return NaN;
  const cleaned = String(raw).trim().replace(/\s+/g, '').replace(',', '.');
  return cleaned ? parseFloat(cleaned) : NaN;
}

function _getScannerTapeSourceQty() {
  if (!currentPallet) return 0;
  if (currentPallet.unassigned_szt !== undefined && currentPallet.unassigned_szt !== null) {
    return Math.max(0, Math.round(Number(currentPallet.unassigned_szt)));
  }
  const raw = parseFloat(currentPallet.stan_magazynowy || 0);
  return isFinite(raw) && raw > 0 ? Math.round(raw) : 0;
}

function _applyScannerTapeSubmitState(canSubmit) {
  const btn = document.getElementById('btnConfirmScannerTapeSplit');
  if (btn) btn.disabled = !canSubmit;
}

function _setSummaryVariant(sumEl, variant) {
  sumEl.classList.remove(
    'subroll-summary-box--warn',
    'subroll-summary-box--error',
    'subroll-summary-box--valid'
  );
  if (variant) sumEl.classList.add(`subroll-summary-box--${variant}`);
}

function _refreshSingleSubrollBadge() {
  const rollInp = document.getElementById('scannerSingleSubrollInput');
  const bagInp = document.getElementById('tapeSplitBagWeightKg');
  const badgeEl = document.getElementById('scannerSingleSubrollPcs');
  if (!badgeEl) return;

  const num = rollInp ? _parseScannerTapeDecimal(rollInp.value) : NaN;
  if (_scannerTapeSplitMode === 'szt') {
    badgeEl.textContent = (isFinite(num) && num > 0)
      ? `${Math.round(num).toLocaleString('pl-PL')} szt`
      : '—';
    return;
  }
  const bagKg = bagInp ? _parseScannerTapeDecimal(bagInp.value) : NaN;
  badgeEl.textContent = (isFinite(num) && num > 0 && isFinite(bagKg) && bagKg > 0)
    ? `= ${Math.round(num / bagKg).toLocaleString('pl-PL')} szt`
    : '—';
}

function setScannerTapeSplitMode(mode) {
  _scannerTapeSplitMode = mode === 'szt' ? 'szt' : 'kg';
  const kgBtn = document.getElementById('tapeSplitModeKgBtn');
  const sztBtn = document.getElementById('tapeSplitModeSztBtn');
  const bagRow = document.getElementById('tapeSplitBagWeightRow');
  const lbl = document.getElementById('scannerTapeRollsLabel');
  const rollInp = document.getElementById('scannerSingleSubrollInput');

  const isKg = _scannerTapeSplitMode === 'kg';
  if (kgBtn) kgBtn.classList.toggle('is-active', isKg);
  if (sztBtn) sztBtn.classList.toggle('is-active', !isKg);
  if (bagRow) bagRow.classList.toggle('is-hidden', !isKg);
  if (lbl) {
    lbl.textContent = isKg
      ? 'Waga dodawanej podrolki (kg):'
      : 'Ilość na dodawanej podrolce (szt):';
  }
  if (rollInp) {
    rollInp.placeholder = isKg ? 'kg...' : 'szt...';
    rollInp.focus();
  }

  _refreshSingleSubrollBadge();
  _updateScannerTapeSummary();
}

function _updateScannerTapeSummary() {
  const bagInp = document.getElementById('tapeSplitBagWeightKg');
  const rollInp = document.getElementById('scannerSingleSubrollInput');
  const sumEl = document.getElementById('scannerTapeSplitSummary');
  if (!sumEl) return;

  const maxPcs = _getScannerTapeSourceQty();
  const nextNr = Number(currentPallet?.subrolls_count || 0) + 1;
  const rawVal = rollInp ? _parseScannerTapeDecimal(rollInp.value) : NaN;

  if (_scannerTapeSplitMode === 'szt') {
    const pcs = (isFinite(rawVal) && rawVal > 0) ? Math.round(rawVal) : 0;
    if (pcs <= 0) {
      _setSummaryVariant(sumEl, null);
      sumEl.textContent = `Wpisz liczbę sztuk (szt) dla dodawanej podrolki (dostępna pula: ${maxPcs.toLocaleString('pl-PL')} szt).`;
      _applyScannerTapeSubmitState(false);
    } else if (pcs > maxPcs) {
      const diff = pcs - maxPcs;
      _setSummaryVariant(sumEl, 'error');
      sumEl.innerHTML = `⛔ Przekroczono dostępną pulę o <strong>${diff.toLocaleString('pl-PL')} szt</strong>! (Wpisano: <strong>${pcs.toLocaleString('pl-PL')} szt</strong> / Wolne: <strong>${maxPcs.toLocaleString('pl-PL')} szt</strong>)`;
      _applyScannerTapeSubmitState(false);
    } else {
      const rem = maxPcs - pcs;
      _setSummaryVariant(sumEl, 'valid');
      const remNote = rem > 0
        ? ` &nbsp;|&nbsp; Nierozpisane zostanie: <strong>${rem.toLocaleString('pl-PL')} szt</strong>`
        : ' &nbsp;(100% wolnej puli przypisane)';
      sumEl.innerHTML = `Podrolka #${nextNr}: <strong>${pcs.toLocaleString('pl-PL')} szt</strong>${remNote}`;
      _applyScannerTapeSubmitState(true);
    }
    return;
  }

  const bagKg = bagInp ? _parseScannerTapeDecimal(bagInp.value) : NaN;
  if (!isFinite(bagKg) || bagKg <= 0) {
    _setSummaryVariant(sumEl, 'warn');
    sumEl.textContent = 'Wpisz wagę 1 worka w kg (np. 0.150), aby przeliczyć podrolkę.';
    _applyScannerTapeSubmitState(false);
    return;
  }

  const kg = (isFinite(rawVal) && rawVal > 0) ? rawVal : 0;
  const pcs = kg > 0 ? Math.round(kg / bagKg) : 0;
  if (pcs <= 0) {
    _setSummaryVariant(sumEl, null);
    sumEl.textContent = `Wpisz wagę (kg) dodawanej podrolki (dzielnik: ${bagKg} kg/worek, wolna pula: ${maxPcs.toLocaleString('pl-PL')} szt).`;
    _applyScannerTapeSubmitState(false);
  } else if (pcs > maxPcs) {
    const diff = pcs - maxPcs;
    _setSummaryVariant(sumEl, 'error');
    sumEl.innerHTML = `⛔ Przekroczono dostępną pulę o <strong>${diff.toLocaleString('pl-PL')} szt</strong>! (${Math.round(kg * 100) / 100} kg → <strong>${pcs.toLocaleString('pl-PL')} szt</strong> / Wolne: <strong>${maxPcs.toLocaleString('pl-PL')} szt</strong>)`;
    _applyScannerTapeSubmitState(false);
  } else {
    const rem = maxPcs - pcs;
    _setSummaryVariant(sumEl, 'valid');
    const remNote = rem > 0
      ? ` &nbsp;|&nbsp; Nierozpisane zostanie: <strong>${rem.toLocaleString('pl-PL')} szt</strong>`
      : ' &nbsp;(100% wolnej puli przypisane)';
    sumEl.innerHTML = `Podrolka #${nextNr}: ${Math.round(kg * 100) / 100} kg → <strong>${pcs.toLocaleString('pl-PL')} szt</strong>${remNote}`;
    _applyScannerTapeSubmitState(true);
  }
}

function _bindSingleSubrollInputs() {
  const bagInp = document.getElementById('tapeSplitBagWeightKg');
  const rollInp = document.getElementById('scannerSingleSubrollInput');

  if (bagInp && !bagInp.dataset.boundTapeSplit) {
    bagInp.dataset.boundTapeSplit = '1';
    bagInp.addEventListener('input', () => {
      _refreshSingleSubrollBadge();
      _updateScannerTapeSummary();
    });
  }

  if (rollInp && !rollInp.dataset.boundSingleSubroll) {
    rollInp.dataset.boundSingleSubroll = '1';
    rollInp.addEventListener('input', () => {
      _refreshSingleSubrollBadge();
      _updateScannerTapeSummary();
    });
    rollInp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const btn = document.getElementById('btnConfirmScannerTapeSplit');
        if (btn && !btn.disabled) submitScannerTapeSplit();
      }
    });
  }
}

function openScannerTapeSplitModal() {
  if (!currentPallet) return;
  const overlay = document.getElementById('scannerTapeSplitOverlay');
  if (!overlay) return;

  const nameEl = document.getElementById('tapeSplitPalletName');
  const ssccEl = document.getElementById('tapeSplitPalletSSCC');
  const locEl = document.getElementById('tapeSplitPalletLoc');
  const qtyEl = document.getElementById('tapeSplitPalletQty');
  const extraInfoEl = document.getElementById('tapeSplitPalletExtra');
  const bagInp = document.getElementById('tapeSplitBagWeightKg');
  const rollInp = document.getElementById('scannerSingleSubrollInput');

  const availPcs = _getScannerTapeSourceQty();
  const totalStock = Math.round(parseFloat(currentPallet.stan_magazynowy || 0));
  const subCount = Number(currentPallet.subrolls_count || 0);
  const subTotal = Number(currentPallet.subrolls_total_szt || 0);

  if (nameEl) nameEl.textContent = currentPallet.nazwa || '—';
  if (ssccEl) ssccEl.textContent = currentPallet.nr_palety || ('OPK-' + currentPallet.id);
  if (locEl) locEl.textContent = currentPallet.lokalizacja || '—';
  if (qtyEl) qtyEl.textContent = availPcs.toLocaleString('pl-PL');
  if (extraInfoEl) {
    if (subCount > 0) {
      extraInfoEl.textContent = `Stan całkowity palety: ${totalStock.toLocaleString('pl-PL')} szt | Przypisane podrolki (${subCount}): ${subTotal.toLocaleString('pl-PL')} szt`;
      extraInfoEl.classList.remove('is-hidden');
    } else {
      extraInfoEl.textContent = '';
      extraInfoEl.classList.add('is-hidden');
    }
  }

  if (bagInp) bagInp.value = '';
  if (rollInp) rollInp.value = '';
  _bindSingleSubrollInputs();
  setScannerTapeSplitMode(_scannerTapeSplitMode);
  overlay.classList.add('is-open');

  fetch('/magazyn/inwentaryzacja/api/tasmy-przeliczniki', { credentials: 'same-origin' })
    .then((r) => r.json())
    .then((d) => {
      if (d.success && d.map && currentPallet && currentPallet.nazwa && bagInp) {
        const key = String(currentPallet.nazwa).trim().toLowerCase();
        if (d.map[key]) {
          bagInp.value = String(d.map[key]);
          _refreshSingleSubrollBadge();
          _updateScannerTapeSummary();
          if (rollInp) rollInp.focus();
        } else if (_scannerTapeSplitMode === 'kg') {
          bagInp.focus();
        }
      }
    })
    .catch(() => { });
}

function closeScannerTapeSplitModal() {
  const overlay = document.getElementById('scannerTapeSplitOverlay');
  if (overlay) overlay.classList.remove('is-open');
  const scanInput = document.getElementById('scanInput');
  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
}

function saveScannerTapeBagWeight() {
  if (!currentPallet || !currentPallet.nazwa) return;
  const bagInp = document.getElementById('tapeSplitBagWeightKg');
  const bagKg = bagInp ? _parseScannerTapeDecimal(bagInp.value) : NaN;
  if (!isFinite(bagKg) || bagKg <= 0) {
    showToast('Podaj poprawną wagę 1 worka > 0 (np. 0.150)', 'warn');
    if (bagInp) bagInp.focus();
    return;
  }
  fetch('/magazyn/inwentaryzacja/api/tasmy-przeliczniki', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ nazwa: currentPallet.nazwa, waga_worka_kg: bagKg })
  })
    .then((r) => r.json())
    .then((d) => {
      if (d.success) {
        showToast(`✅ Zapisano ${bagKg} kg/worek dla ${currentPallet.nazwa}`, 'success');
        _refreshSingleSubrollBadge();
        _updateScannerTapeSummary();
      } else {
        showToast(d.message || 'Błąd zapisu wagi worka', 'danger');
      }
    })
    .catch(() => showToast('Błąd połączenia z serwerem', 'danger'));
}

function submitScannerTapeSplit() {
  if (!currentPallet) return;
  const isSzt = _scannerTapeSplitMode === 'szt';
  const bagInp = document.getElementById('tapeSplitBagWeightKg');
  const rollInp = document.getElementById('scannerSingleSubrollInput');
  const bagKg = bagInp ? _parseScannerTapeDecimal(bagInp.value) : NaN;

  if (!isSzt && (!isFinite(bagKg) || bagKg <= 0)) {
    showToast('Najpierw wpisz wagę 1 worka w kg (np. 0.150)!', 'warn');
    if (bagInp) bagInp.focus();
    return;
  }

  const rawVal = rollInp ? _parseScannerTapeDecimal(rollInp.value) : NaN;
  if (!isFinite(rawVal) || rawVal <= 0) {
    showToast(`Podaj poprawną wartość > 0 ${isSzt ? 'szt' : 'kg'} dla dodawanej podrolki!`, 'warn');
    if (rollInp) rollInp.focus();
    return;
  }

  const pcs = isSzt ? Math.round(rawVal) : Math.round(rawVal / bagKg);
  if (pcs <= 0) {
    showToast('Podrolka ma 0 szt po przeliczeniu!', 'warn');
    return;
  }

  const maxPcs = _getScannerTapeSourceQty();
  if (pcs > maxPcs) {
    showToast(
      `⛔ Ilość podrolki (${pcs.toLocaleString('pl-PL')} szt) przekracza wolną pulę palety (${maxPcs.toLocaleString('pl-PL')} szt)!`,
      'danger'
    );
    _updateScannerTapeSummary();
    return;
  }

  const printChecked = Boolean(document.getElementById('tapeSplitPrintLabels')?.checked);
  const btn = document.getElementById('btnConfirmScannerTapeSplit');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons">hourglass_top</span> Dodawanie...';
  }

  const targetCode = currentPallet.nr_palety || ('OPK-' + currentPallet.id);
  fetch('/agro/scanner/split-tape-rolls', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({
      pallet_id: currentPallet.id,
      nr_palety: currentPallet.nr_palety,
      rolls_szt: [pcs],
      bag_weight_kg: !isSzt ? bagKg : null,
      save_bag_weight: !isSzt,
      print_labels: printChecked
    })
  })
    .then((r) => r.json())
    .then((d) => {
      if (d.success) {
        closeScannerTapeSplitModal();
        const extraMsg = printChecked ? ` (wydrukowano etykiet: ${d.printed_count || 0})` : '';
        showToast(`✅ ${d.message}${extraMsg}`, 'success');
        if (targetCode) lookupPallet(targetCode);
      } else {
        showToast(d.error || d.message || 'Błąd dodawania podrolki', 'danger');
      }
    })
    .catch((e) => showToast('Błąd połączenia z serwerem: ' + e, 'danger'))
    .finally(() => {
      if (btn) {
        btn.innerHTML = '<span class="material-icons">add_circle</span> Dodaj podrolkę';
      }
      _updateScannerTapeSummary();
    });
}
