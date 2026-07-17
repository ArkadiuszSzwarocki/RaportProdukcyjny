import re

with open('templates/scanner/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update triggerScan
trigger_scan_old = '''function triggerScan() {
  const code = scanInput.value.trim();
  if (code) {
    lookupPallet(code);
  } else {
    const started = requestHardwareScanTrigger();
    if (started) {
      showToast('Aktywuję skaner... zeskanuj kod.', 'success');
    } else {
      showToast('Nie mogę uruchomić lasera z przeglądarki. Użyj fizycznego spustu skanera.', 'warn');
    }
  }
}'''

trigger_scan_new = '''function triggerScan() {
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

function doMoveFromMainInput(loc) {
  loc = loc.toUpperCase();
  const isProduction = loc.startsWith('BB') || loc.startsWith('MZ') || loc.startsWith('LINIA') || loc.startsWith('Z');
  
  if (isProduction) {
    pendingProductionLoc = loc;
    document.getElementById('dispatchModalLoc').textContent = loc;
    document.getElementById('dispatchModalQty').value = currentPallet.stan_magazynowy;
    document.getElementById('dispatchOverlay').style.display = 'flex';
  } else {
    if (!confirm(`Przenieść paletę [${currentPallet.nazwa}] na lokalizację: ${loc}?`)) {
      scanInput.value = '';
      scanInput.focus();
      return;
    }

    fetch('/agro/scanner/move', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        surowiec_id: currentPallet.id,
        lokalizacja: loc,
        linia: LINIA
      })
    })
    .then(r => r.json())
    .then(d => {
      showToast(d.message, d.success ? 'success' : 'danger');
      if (d.success) {
        lookupPallet(currentPallet.nr_palety || 'SUR-' + currentPallet.id);
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
}'''

html = html.replace(trigger_scan_old, trigger_scan_new)

# 2. Update showPallet to change scan box text
show_pallet_old = '''  document.getElementById('palletCard').classList.add('visible');
  document.getElementById('nopalletMsg').style.display = 'none';'''

show_pallet_new = '''  document.getElementById('palletCard').classList.add('visible');
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
  pendingProductionLoc = null;'''

html = html.replace(show_pallet_old, show_pallet_new)

# 3. Update hidePallet to reset scan box text
hide_pallet_old = '''function hidePallet() {
  currentPallet = null;
  document.getElementById('palletCard').classList.remove('visible');
  document.getElementById('nopalletMsg').style.display = '';
}'''

hide_pallet_new = '''function hidePallet() {
  currentPallet = null;
  document.getElementById('palletCard').classList.remove('visible');
  document.getElementById('nopalletMsg').style.display = '';

  const titleEl = document.querySelector('.scan-title');
  if(titleEl) titleEl.innerHTML = '<span class="material-icons" style="color:var(--primary-color);">barcode_reader</span> Skanuj kod regału lub palety';
  scanInput.placeholder = 'R030101 albo SUR-42';
  scanInput.style.borderColor = '';
  scanInput.style.borderWidth = '';
  const iconEl = document.querySelector('.input-icon');
  if(iconEl) iconEl.style.color = '';
}'''

html = html.replace(hide_pallet_old, hide_pallet_new)

# 4. Add Dispatch Modal HTML
dispatch_modal_html = '''
<!-- DISPATCH MODAL -->
<div class="modal-overlay" id="dispatchOverlay" style="display:none; z-index:9000;">
  <div class="modal-box" style="max-width: 400px;">
    <h2 class="m-0 row items-center gap-8 mb-10" style="color: #d97706; font-size: 18px; margin-bottom: 16px;">
      <span class="material-icons text-primary">local_shipping</span>
      Przekaż na produkcję
    </h2>
    <div style="margin-bottom: 16px; font-size: 14px; color: #475569;">
      Lokalizacja docelowa: <strong id="dispatchModalLoc" style="color: #1e293b; font-size: 16px;"></strong>
    </div>
    
    <label class="form-label small mb-4">Ilość do przesunięcia (kg)</label>
    <input type="number" id="dispatchModalQty" class="form-control" step="0.1" placeholder="0.0" style="margin-bottom: 12px; font-size: 16px; font-weight: bold; width: 100%;">
    
    <label class="form-label small mb-4">Nr zlecenia (opcjonalnie)</label>
    <input type="number" id="dispatchModalPlanId" class="form-control" placeholder="ID planu" style="margin-bottom: 20px; width: 100%;">
    
    <div class="row justify-between mt-20" style="margin-top: 16px;">
      <button class="btn btn-outline" onclick="closeDispatchModal()" style="padding: 8px 16px;">Anuluj</button>
      <button class="btn btn-primary" onclick="doFinalDispatch()" style="padding: 8px 16px; background: #d97706 !important;">Zatwierdź</button>
    </div>
  </div>
</div>
{% endblock %}'''

html = html.replace('{% endblock %}', dispatch_modal_html)

with open('templates/scanner/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
