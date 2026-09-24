/* ─── Scanner UI Card Views (Pallet Card & Station Card) ─────── */

function showStation(station) {
  hidePallet();
  const stationCard = document.getElementById('stationCard');
  const stationCodeEl = document.getElementById('stationCode');
  const itemsListEl = document.getElementById('stationItemsList');
  const noStationMsg = document.getElementById('nostationMsg');
  const scanInput = document.getElementById('scanInput');

  if (stationCodeEl) stationCodeEl.textContent = station.station_code;
  if (itemsListEl) itemsListEl.innerHTML = '';

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
    if (noStationMsg) noStationMsg.style.display = 'none';
  } else {
    if (noStationMsg) noStationMsg.style.display = 'block';
  }

  if (stationCard) stationCard.style.display = 'block';
  if (scanInput) {
    scanInput.value = '';
    scanInput.focus();
  }
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
  const palletLocEl = document.getElementById('palletLoc');
  if (palletLocEl) {
    if (p.lokalizacja === 'OCZEKUJĄCE' && p.source_location) {
      palletLocEl.innerHTML = `<span style="color: #d97706; font-weight: bold;">OCZEKUJĄCE</span> <span style="font-size: 11px; font-weight: normal; color: #64748b;">(z: ${p.source_location})</span>`;
    } else {
      palletLocEl.textContent = p.lokalizacja || '—';
    }
  }

  const palletNameEl = document.getElementById('palletName');
  if (palletNameEl) palletNameEl.textContent = p.nazwa;

  const idVal = document.getElementById('palletIdVal');
  if (idVal) idVal.textContent = p.id ? `#${p.id}` : '—';

  const histBtn = document.getElementById('palletHistoryBtn');
  if (histBtn) histBtn.style.display = 'inline-flex';

  const qtyContainer = document.querySelector('.pallet-qty');
  if (qtyContainer) {
    if (p.is_bucket) {
      qtyContainer.innerHTML = `<span id="palletQty">${parseInt(p.stan_magazynowy, 10)}</span> ${p.jednostka || 'składniki'}`;
    } else if (p.unit === 'szt.' || p.unit === 'szt' || p.inventory_type === 'Opakowanie' || p.is_pkg) {
      const rawVal = parseFloat(p.stan_magazynowy || 0);
      const qtyFormatted = Number.isInteger(rawVal) ? String(parseInt(rawVal, 10)) : rawVal.toFixed(1);
      qtyContainer.innerHTML = `<span id="palletQty">${qtyFormatted}</span> ${p.unit || 'szt.'}`;
    } else {
      qtyContainer.innerHTML = `<span id="palletQty">${parseFloat(p.stan_magazynowy || 0).toFixed(1)}</span> ${p.unit || 'kg'}`;
    }
  }
  
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
  
  const ssccEl = document.getElementById('palletSSCC');
  if (ssccEl) ssccEl.textContent = p.nr_palety || p.inventory_code || '—';

  const partiaEl = document.getElementById('palletPartia');
  if (partiaEl) partiaEl.textContent = p.nr_partii || '—';

  const dataProdEl = document.getElementById('palletDataProd');
  if (dataProdEl) dataProdEl.textContent = p.data_produkcji || '—';

  const dataWazEl = document.getElementById('palletDataWaz');
  if (dataWazEl) dataWazEl.textContent = p.data_przydatnosci || '—';

  const locUpper = (p.lokalizacja || '').toUpperCase();
  const isProductionStation = !isUsedUp && (locUpper.startsWith('BB') || locUpper.startsWith('MZ') || locUpper.startsWith('WZ') || locUpper.startsWith('Z') || locUpper.startsWith('CZ') || locUpper.startsWith('KO') || locUpper.startsWith('PSD') || locUpper.startsWith('MIX')) && !locUpper.startsWith('BF_') && !locUpper.startsWith('BF');
  
  const returnBtn = document.getElementById('scannerReturnBtnContainer');
  if (returnBtn) {
    returnBtn.style.display = isProductionStation ? 'block' : 'none';
  }

  const restoreBtn = document.getElementById('scannerRestoreBtnContainer');
  if (restoreBtn) {
    const canRestore = Boolean((typeof CAN_RESTORE_PALLET !== 'undefined' ? CAN_RESTORE_PALLET : window.CAN_RESTORE_PALLET) && isUsedUp);
    restoreBtn.style.display = canRestore ? 'block' : 'none';
  }

  const splitBtn = document.getElementById('scannerSplitBtnContainer');
  if (splitBtn) {
    const canSplit = !isUsedUp && !isBlocked && !p.is_bucket && parseFloat(p.stan_magazynowy || 0) > 0;
    splitBtn.style.display = canSplit ? 'block' : 'none';
  }

  const palletCard = document.getElementById('palletCard');
  if (palletCard) palletCard.classList.add('visible');

  const nopalletMsg = document.getElementById('nopalletMsg');
  if (nopalletMsg) nopalletMsg.style.display = 'none';

  const scanInput = document.getElementById('scanInput');
  const mainTitle = document.getElementById('scanTitleText');
  const titleIcon = document.getElementById('scanTitleIcon');
  const iconEl = document.querySelector('.input-icon');

  if (scanInput) {
    if (window.justConfirmedLoc) {
      const confLoc = window.justConfirmedLoc;
      window.justConfirmedLoc = null;
      currentPallet = null;
      if (mainTitle) mainTitle.textContent = `✅ Paleta zatwierdzona na: ${confLoc}`;
      if (titleIcon) {
        titleIcon.textContent = 'check_circle';
        titleIcon.style.color = '#16a34a';
      }
      scanInput.placeholder = 'Skanuj kod kolejnej palety lub regału...';
      scanInput.style.borderColor = '#16a34a';
      scanInput.style.borderWidth = '2px';
      if (iconEl) iconEl.style.color = '#16a34a';
    } else if (isTransferOrder) {
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
  }

  pendingProductionLoc = null;

  // Clear any legacy timeouts and ensure countdown bar is hidden
  if (window.hidePalletTimeout) {
    clearTimeout(window.hidePalletTimeout);
    window.hidePalletTimeout = null;
  }
  window.hideAfterLoad = false;
  const barContainer = document.getElementById('palletTimeoutBarContainer');
  if (barContainer) {
    barContainer.style.display = 'none';
  }
}

function hidePallet() {
  if (window.hidePalletTimeout) {
    clearTimeout(window.hidePalletTimeout);
    window.hidePalletTimeout = null;
  }
  window.hideAfterLoad = false;
  currentPallet = null;
  const palletCard = document.getElementById('palletCard');
  if (palletCard) palletCard.classList.remove('visible');

  const nopalletMsg = document.getElementById('nopalletMsg');
  if (nopalletMsg) nopalletMsg.style.display = '';
  
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
  const scanInput = document.getElementById('scanInput');
  if (scanInput) {
    scanInput.value = '';
    scanInput.placeholder = 'Wpisz lub zeskanuj kod (np. R030101, SSCC, PAL-15)';
    scanInput.style.borderColor = '';
    scanInput.style.borderWidth = '';
    scanInput.focus();
    scanInput.dispatchEvent(new Event('input', { bubbles: true }));
  }
  const iconEl = document.querySelector('.input-icon');
  if (iconEl) iconEl.style.color = '';
}
