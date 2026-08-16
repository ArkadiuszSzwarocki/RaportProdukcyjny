import sys
import re

with open('templates/scanner/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add CSS
css_to_add = '''
/* Printer Modal */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.modal-box {
  background: #fff; width: 90%; max-width: 450px;
  border-radius: 16px; padding: 24px;
  box-shadow: 0 20px 40px rgba(0,0,0,0.2);
}
.printer-option {
  display: flex; align-items: center; gap: 12px;
  padding: 12px; background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s;
}
.printer-option:hover {
  background: #eff6ff; border-color: #bfdbfe;
}
.printer-option .material-icons { color: #3b82f6; }
.printer-option-title { font-weight: 700; color: #1e293b; font-size: 14px; }
.printer-option-ip { font-size: 12px; color: #64748b; }
'''
html = html.replace('</style>', css_to_add + '\n</style>')

# 2. Remove Header
header_match = re.search(r'<!-- Header -->.*?</div>\s*</div>', html, re.DOTALL)
if header_match:
    html = html.replace(header_match.group(0), '')

# 3. Add Pallet Details UI to palletCard and remove old buttons
old_pallet_info = '''        <div class="row gap-8">
          <button class="btn btn-outline btn-sm row items-center gap-4" onclick="printLabel('pallet')">
            <span class="material-icons" style="font-size:16px;">print</span> Etykieta
          </button>
          <button class="btn btn-outline btn-sm row items-center gap-4" onclick="printLabel('location')">
            <span class="material-icons" style="font-size:16px;">place</span> Etykieta regału
          </button>
        </div>'''
new_pallet_info = '''        <div class="row gap-8 align-start">
          <button class="btn btn-outline btn-sm row items-center gap-4" onclick="printLabel('pallet')" style="background:#1e293b; color:#fff; padding:10px 16px; border-radius:8px;">
            <span class="material-icons" style="font-size:20px;">print</span> Drukuj etykietę ZPL
          </button>
        </div>'''
html = html.replace(old_pallet_info, new_pallet_info)

html = html.replace('<div class="pallet-qty"><span id="palletQty">1600.0</span> kg</div>', 
'''<div class="pallet-qty"><span id="palletQty">1600.0</span> kg</div>
          <!-- Szczegóły palety -->
          <div id="palletDetails" style="margin-top: 10px; font-size: 0.85em; color: #1e293b; font-weight: 500; line-height: 1.6;">
            <div><strong>Nr/SSCC:</strong> <span id="palletSSCC">—</span></div>
            <div><strong>Partia:</strong> <span id="palletPartia">—</span></div>
            <div><strong>Data prod.:</strong> <span id="palletDataProd">—</span></div>
            <div><strong>Ważność:</strong> <span id="palletDataWaz">—</span></div>
          </div>''')

# 4. Remove Dispatch Section
html = re.sub(r'<!-- DISPATCH -->.*?</div>\n', '', html, flags=re.DOTALL)
html = re.sub(r'<!-- SPLIT -->.*?<!-- /splitSection -->\n', '', html, flags=re.DOTALL)

# 5. Remove doDispatch, etc from JS
html = re.sub(r'/\* ─── Dispatch ───.*?/\* ─── Print ───', '/* ─── Print ───', html, flags=re.DOTALL)

# 6. Replace JS printLabel
old_print_label = '''/* ─── Print ───────────────────────────────────────────────── */
function printLabel(type) {
  if (!currentPallet) return showToast('Brak palety — zeskanuj najpierw', 'warn');

  if (type === 'location') {
    // Etykieta regału — otwórz w aplikacji
    const loc = currentPallet.lokalizacja || document.getElementById('barcodeInput').value.trim();
    const url = `/agro/scanner/label_location?loc=${loc}&linia=${LINIA}`;
    window.openInApp ? openInApp(url, 'Etykieta regału') : window.open(url, '_blank');
    return;
  }

  // Etykieta palety — najpierw spróbuj TCP, zawsze otwórz HTML
  fetch('/agro/scanner/print', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({surowiec_id: currentPallet.id, type, linia: LINIA})
  })
  .then(r => r.json())
  .then(d => {
    if (d.label_url) {
      window.openInApp ? openInApp(d.label_url, 'Etykieta palety') : window.open(d.label_url, '_blank');
    }
    if (d.success) {
      showToast('✅ ' + d.message, 'success');
    } else {
      showToast('📄 Etykieta otwarta w aplikacji', 'success');
    }
  })
  .catch(() => {
    const url = `/agro/scanner/label/${currentPallet.id}?linia=${LINIA}&autoprint=1`;
    window.openInApp ? openInApp(url, 'Etykieta palety') : window.open(url, '_blank');
    showToast('📄 Etykieta otwarta w aplikacji', 'success');
  });
}'''

new_print_label = '''/* ─── Print ───────────────────────────────────────────────── */
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
}'''

html = html.replace(old_print_label, new_print_label)

# 7. Add Modal HTML at the end
modal_html = '''
<!-- PRINTER MODAL -->
<div class="modal-overlay" id="printerOverlay" style="display:none; z-index:9000;">
  <div class="modal-box" style="max-width: 400px;">
    <h2 class="m-0 row items-center gap-8 mb-10" style="color: #1e293b; font-size: 18px; margin-bottom: 16px;">
      <span class="material-icons text-primary">print</span>
      Wybierz drukarkę ZPL
    </h2>
    <div id="printerList" style="max-height: 300px; overflow-y: auto; margin-top: 16px;">
      <!-- Printer options loaded here -->
    </div>
    <div class="row justify-end mt-20" style="margin-top: 16px; text-align: right;">
      <button class="btn btn-outline" onclick="closePrinterModal()" style="padding: 8px 16px;">Anuluj</button>
    </div>
  </div>
</div>
{% endblock %}
'''
html = html.replace('{% endblock %}', modal_html)

# 8. Update showPallet details binding
show_pallet_old = '''  document.getElementById('palletLoc').textContent  = p.lokalizacja || '—';
  document.getElementById('palletName').textContent = p.nazwa;
  document.getElementById('palletQty').textContent  = parseFloat(p.stan_magazynowy).toFixed(1);
  document.getElementById('palletCard').classList.add('visible');
  document.getElementById('nopalletMsg').style.display = 'none';

  // show action sections
  document.getElementById('dispatchSection').style.display = '';
  document.getElementById('dispatchQty').value = parseFloat(p.stan_magazynowy).toFixed(1);
  document.getElementById('splitSection').style.display = '';
  document.getElementById('splitAvail').textContent = parseFloat(p.stan_magazynowy).toFixed(1);

  // clear bags
  document.getElementById('bagsBody').innerHTML = '';
  bagCount = 0;
  addBagRow();'''

show_pallet_new = '''  document.getElementById('palletLoc').textContent  = p.lokalizacja || '—';
  document.getElementById('palletName').textContent = p.nazwa;
  document.getElementById('palletQty').textContent  = parseFloat(p.stan_magazynowy).toFixed(1);
  
  // Extra details
  document.getElementById('palletSSCC').textContent = p.nr_palety || p.inventory_code || '—';
  document.getElementById('palletPartia').textContent = p.nr_partii || '—';
  document.getElementById('palletDataProd').textContent = p.data_produkcji || '—';
  document.getElementById('palletDataWaz').textContent = p.data_przydatnosci || '—';

  document.getElementById('palletCard').classList.add('visible');
  document.getElementById('nopalletMsg').style.display = 'none';'''
html = html.replace(show_pallet_old, show_pallet_new)

# 9. hidePallet
hide_pallet_old = '''  document.getElementById('palletCard').classList.remove('visible');
  document.getElementById('nopalletMsg').style.display = '';
  document.getElementById('dispatchSection').style.display = 'none';
  document.getElementById('splitSection').style.display   = 'none';'''
hide_pallet_new = '''  document.getElementById('palletCard').classList.remove('visible');
  document.getElementById('nopalletMsg').style.display = '';'''
html = html.replace(hide_pallet_old, hide_pallet_new)

# Remove the checkPrinter interval
html = html.replace('setInterval(checkPrinter, 30000);', '')

# Remove print hint
html = html.replace('<p class="small text-muted mt-8">Przyłóż skaner i naciśnij fizyczny spust. Przycisk obok pola przy pustym kodzie spróbuje uruchomić skanowanie programowo (jeśli urządzenie to wspiera).</p>', '')

with open('templates/scanner/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
