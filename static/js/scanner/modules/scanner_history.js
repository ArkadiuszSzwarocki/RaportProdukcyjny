/* ─── Scanner Pallet History and Timeline Rendering ─────────── */

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
