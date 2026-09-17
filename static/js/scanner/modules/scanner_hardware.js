/* ─── Scanner Hardware, Barcode Parsing & Input Normalization ─── */

function checkPrinter() {
  fetch('/agro/scanner/printer/status')
    .then(r => r.json())
    .then(d => {
      const el = document.getElementById('printerPill');
      if (!el) return;
      if (d.online) {
        el.className = 'pill pill-success';
        el.innerHTML = '<span class="material-icons" style="font-size:14px;">print</span> Drukarka online';
      } else {
        el.className = 'pill pill-warn';
        el.innerHTML = '<span class="material-icons" style="font-size:14px;">print_disabled</span> Drukarka offline';
      }
    }).catch(() => {
      const el = document.getElementById('printerPill');
      if (el) {
        el.className = 'pill pill-danger';
        el.textContent = 'Błąd połączenia';
      }
    });
}

function requestHardwareScanTrigger() {
  const scanInput = document.getElementById('scanInput');
  if (scanInput) scanInput.focus();

  try {
    if (window.Android && typeof window.Android.startBarcodeScan === 'function') {
      window.Android.startBarcodeScan();
      return true;
    }
  } catch (_) {}

  try {
    if (window.EB && window.EB.Barcode && typeof window.EB.Barcode.start === 'function') {
      window.EB.Barcode.start();
      return true;
    }
  } catch (_) {}

  const isAndroid = /Android/i.test((navigator && navigator.userAgent) || '');
  if (!isAndroid) {
    return false;
  }

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
  if (/^\d{10,24}$/.test(s)) return true;
  if (/^PAL-?\d+/i.test(s) || /^SUR-?\d+/i.test(s) || /^OPA-?\d+/i.test(s) || /^DOD-?\d+/i.test(s)) return true;
  
  const isLocation = /^(R0[1-7]\d{4}|BB\d{2}|MZ\d{2}|WZ\d{2}|CZ\d{2}|KO\d{2}|OS\d{2}|MS\d{2}|MP\d{2}|MD\d{2}|MOP\d{2}|MDM\d{2}|PSD\d{0,2}|AGR\d{0,2}|RAMPA|MIX\d{0,2}|BF_|LP\d{0,2}|MASZYNA)/i.test(s);
  if (isLocation) return false;
  if (/^0[1-7]\d{4}$/.test(s)) return false;

  if (s.length >= 8) return true;
  return false;
}
