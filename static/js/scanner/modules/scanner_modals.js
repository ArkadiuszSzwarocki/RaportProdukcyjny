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

/* ─── Direct Tape Split into Individual Rolls (kg -> szt) ─────── */
let _scannerTapeRolls = ['', ''];

function _parseScannerTapeDecimal(raw) {
  if (raw === null || raw === undefined) return NaN;
  const cleaned = String(raw).trim().replace(/\s+/g, '').replace(',', '.');
  return cleaned ? parseFloat(cleaned) : NaN;
}

function _updateScannerTapeSummary() {
  const bagInp = document.getElementById('tapeSplitBagWeightKg');
  const sumEl = document.getElementById('scannerTapeSplitSummary');
  if (!bagInp || !sumEl) return;
  const bagKg = _parseScannerTapeDecimal(bagInp.value);
  if (!isFinite(bagKg) || bagKg <= 0) {
    sumEl.style.color = '#fbbf24';
    sumEl.textContent = 'Wpisz wagę 1 worka w kg (np. 0.150), aby przeliczyć rolki.';
    return;
  }
  let totalKg = 0;
  let totalPcs = 0;
  let count = 0;
  _scannerTapeRolls.forEach((v) => {
    const kg = _parseScannerTapeDecimal(v);
    if (isFinite(kg) && kg > 0) {
      totalKg += kg;
      totalPcs += Math.round(kg / bagKg);
      count += 1;
    }
  });
  if (count === 0) {
    sumEl.style.color = '#93c5fd';
    sumEl.textContent = `Wpisz wagę (kg) dla co najmniej 2 rolek (dzielnik: ${bagKg} kg/worek).`;
  } else {
    sumEl.style.color = count >= 2 ? '#34d399' : '#fbbf24';
    sumEl.innerHTML = `Razem: <strong>${count} ${count === 1 ? 'rolka' : (count < 5 ? 'rolki' : 'rolek')}</strong> | ${Math.round(totalKg * 100) / 100} kg → <strong>${totalPcs.toLocaleString('pl-PL')} szt</strong>`;
  }
}

function _renderScannerTapeRolls() {
  const listEl = document.getElementById('scannerTapeRollsList');
  const bagInp = document.getElementById('tapeSplitBagWeightKg');
  if (!listEl) return;
  const bagKg = bagInp ? _parseScannerTapeDecimal(bagInp.value) : NaN;

  listEl.innerHTML = _scannerTapeRolls.map((val, idx) => {
    const kg = _parseScannerTapeDecimal(val);
    const pcsText = (isFinite(kg) && kg > 0 && isFinite(bagKg) && bagKg > 0)
      ? `= ${Math.round(kg / bagKg).toLocaleString('pl-PL')} szt`
      : '—';
    return `
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="font-size:12px; font-weight:800; color:#94a3b8; width:62px; flex-shrink:0;">Rolka #${idx + 1}</span>
        <input type="text" inputmode="decimal" class="scanner-tape-roll-kg" data-idx="${idx}"
               value="${String(val || '').replace(/"/g, '&quot;')}" placeholder="kg..."
               style="flex:1; min-width:0; padding:9px 10px; font-size:16px; font-weight:800; background:#0f172a; border:2px solid #475569; border-radius:8px; color:#fff; outline:none;">
        <span class="scanner-tape-roll-pcs" style="font-size:13px; font-weight:800; color:#34d399; min-width:86px; text-align:right;">${pcsText}</span>
        ${_scannerTapeRolls.length > 2 ? `<button type="button" class="scanner-tape-remove-roll" data-idx="${idx}" style="background:#7f1d1d; color:#fecaca; border:none; border-radius:8px; width:30px; height:34px; font-weight:900; cursor:pointer; flex-shrink:0;">&times;</button>` : ''}
      </div>
    `;
  }).join('');

  listEl.querySelectorAll('.scanner-tape-roll-kg').forEach((inp) => {
    inp.addEventListener('input', () => {
      const idx = parseInt(inp.dataset.idx, 10);
      _scannerTapeRolls[idx] = inp.value;
      const bKg = bagInp ? _parseScannerTapeDecimal(bagInp.value) : NaN;
      const kg = _parseScannerTapeDecimal(inp.value);
      const pcsEl = inp.parentElement && inp.parentElement.querySelector('.scanner-tape-roll-pcs');
      if (pcsEl) {
        pcsEl.textContent = (isFinite(kg) && kg > 0 && isFinite(bKg) && bKg > 0)
          ? `= ${Math.round(kg / bKg).toLocaleString('pl-PL')} szt`
          : '—';
      }
      _updateScannerTapeSummary();
    });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const idx = parseInt(inp.dataset.idx, 10);
        const next = listEl.querySelector(`.scanner-tape-roll-kg[data-idx="${idx + 1}"]`);
        if (next) next.focus();
      }
    });
  });

  listEl.querySelectorAll('.scanner-tape-remove-roll').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx, 10);
      if (_scannerTapeRolls.length > 2) {
        _scannerTapeRolls.splice(idx, 1);
        _renderScannerTapeRolls();
        _updateScannerTapeSummary();
      }
    });
  });
}

function addScannerTapeRoll() {
  _scannerTapeRolls.push('');
  _renderScannerTapeRolls();
  _updateScannerTapeSummary();
  const inputs = document.querySelectorAll('#scannerTapeRollsList .scanner-tape-roll-kg');
  if (inputs.length) inputs[inputs.length - 1].focus();
}

function openScannerTapeSplitModal() {
  if (!currentPallet) return;
  const overlay = document.getElementById('scannerTapeSplitOverlay');
  if (!overlay) return;

  _scannerTapeRolls = ['', ''];
  const nameEl = document.getElementById('tapeSplitPalletName');
  const ssccEl = document.getElementById('tapeSplitPalletSSCC');
  const locEl = document.getElementById('tapeSplitPalletLoc');
  const qtyEl = document.getElementById('tapeSplitPalletQty');
  const bagInp = document.getElementById('tapeSplitBagWeightKg');

  if (nameEl) nameEl.textContent = currentPallet.nazwa || '—';
  if (ssccEl) ssccEl.textContent = currentPallet.nr_palety || ('OPK-' + currentPallet.id);
  if (locEl) locEl.textContent = currentPallet.lokalizacja || '—';
  if (qtyEl) qtyEl.textContent = Math.round(parseFloat(currentPallet.stan_magazynowy || 0));
  if (bagInp) {
    bagInp.value = '';
    if (!bagInp.dataset.boundTapeSplit) {
      bagInp.dataset.boundTapeSplit = '1';
      bagInp.addEventListener('input', () => {
        _renderScannerTapeRolls();
        _updateScannerTapeSummary();
      });
    }
  }

  _renderScannerTapeRolls();
  _updateScannerTapeSummary();
  overlay.style.display = 'flex';

  // Fetch saved bag weight for this tape
  fetch('/magazyn/inwentaryzacja/api/tasmy-przeliczniki', { credentials: 'same-origin' })
    .then((r) => r.json())
    .then((d) => {
      if (d.success && d.map && currentPallet && currentPallet.nazwa && bagInp) {
        const key = String(currentPallet.nazwa).trim().toLowerCase();
        if (d.map[key]) {
          bagInp.value = String(d.map[key]);
          _renderScannerTapeRolls();
          _updateScannerTapeSummary();
          const firstRoll = document.querySelector('#scannerTapeRollsList .scanner-tape-roll-kg');
          if (firstRoll) firstRoll.focus();
        } else {
          bagInp.focus();
        }
      }
    })
    .catch(() => {});
}

function closeScannerTapeSplitModal() {
  const overlay = document.getElementById('scannerTapeSplitOverlay');
  if (overlay) overlay.style.display = 'none';
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
        _renderScannerTapeRolls();
        _updateScannerTapeSummary();
      } else {
        showToast(d.message || 'Błąd zapisu wagi worka', 'danger');
      }
    })
    .catch(() => showToast('Błąd połączenia z serwerem', 'danger'));
}

function submitScannerTapeSplit() {
  if (!currentPallet) return;
  const bagInp = document.getElementById('tapeSplitBagWeightKg');
  const bagKg = bagInp ? _parseScannerTapeDecimal(bagInp.value) : NaN;
  if (!isFinite(bagKg) || bagKg <= 0) {
    showToast('Najpierw wpisz wagę 1 worka w kg (np. 0.150)!', 'warn');
    if (bagInp) bagInp.focus();
    return;
  }

  const rollsSzt = [];
  for (let i = 0; i < _scannerTapeRolls.length; i += 1) {
    const raw = String(_scannerTapeRolls[i] || '').trim();
    if (!raw) continue;
    const kg = _parseScannerTapeDecimal(raw);
    if (!isFinite(kg) || kg <= 0) {
      showToast(`Podaj poprawną wagę > 0 kg dla rolki #${i + 1}`, 'warn');
      return;
    }
    const pcs = Math.round(kg / bagKg);
    if (pcs <= 0) {
      showToast(`Rolka #${i + 1} ma 0 szt po przeliczeniu`, 'warn');
      return;
    }
    rollsSzt.push(pcs);
  }

  if (rollsSzt.length < 2) {
    showToast('Wpisz wagę (kg) dla co najmniej 2 rolek!', 'warn');
    return;
  }

  const printChecked = Boolean(document.getElementById('tapeSplitPrintLabels')?.checked);
  const btn = document.getElementById('btnConfirmScannerTapeSplit');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="animation:spin 1s linear infinite;">refresh</span> Rozbijanie...';
  }

  const targetCode = currentPallet.nr_palety || ('OPK-' + currentPallet.id);
  fetch('/agro/scanner/split-tape-rolls', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({
      pallet_id: currentPallet.id,
      nr_palety: currentPallet.nr_palety,
      rolls_szt: rollsSzt,
      bag_weight_kg: bagKg,
      save_bag_weight: true,
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
        showToast(d.error || d.message || 'Błąd rozbijania taśmy', 'danger');
      }
    })
    .catch((e) => showToast('Błąd połączenia z serwerem: ' + e, 'danger'))
    .finally(() => {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:18px;">call_split</span> Rozbij na rolki';
      }
    });
}
