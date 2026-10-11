/* Pallet search by the last six digits; choosing a match only loads its details. */
let palletSuggestionTimer = null;
let palletSuggestionVersion = 0;

function clearPalletSuggestions() {
  clearTimeout(palletSuggestionTimer);
  palletSuggestionVersion += 1;
  const list = document.getElementById('palletSuggestions');
  if (list) { list.replaceChildren(); list.hidden = true; }
}

function schedulePalletSuggestions(code) {
  clearPalletSuggestions();
  if (/^[0-9]{6}$/.test(code)) {
    palletSuggestionTimer = setTimeout(() => requestPalletSuggestions(code), 250);
  }
}

async function requestPalletSuggestions(code) {
  clearPalletSuggestions();
  if (!/^[0-9]{6}$/.test(code)) return;
  const version = palletSuggestionVersion;
  const input = document.getElementById('scanInput');
  if (!input) return;
  let list = document.getElementById('palletSuggestions');
  if (!list) {
    list = document.createElement('div');
    list.id = 'palletSuggestions';
    list.setAttribute('aria-live', 'polite');
    list.style.cssText = 'margin-top:8px;max-height:280px;overflow-y:auto;background:white;border:1px solid #cbd5e1;border-radius:8px;padding:8px;';
    input.parentNode.appendChild(list);
  }
  list.hidden = false;
  list.textContent = 'Szukam palet…';
  try {
    const line = typeof LINIA !== 'undefined' ? LINIA : 'AGRO';
    const response = await fetch('/agro/scanner/pallet-suggestions?digits=' + encodeURIComponent(code) + '&linia=' + encodeURIComponent(line));
    const data = await response.json();
    if (version !== palletSuggestionVersion || input.value.trim() !== code) return;
    list.replaceChildren();
    if (!data.success) {
      list.textContent = scannerResponseMessage(data);
      return;
    }
    const pallets = data.pallets || [];
    if (!pallets.length) { list.textContent = 'Nie znaleziono palet z taką końcówką numeru.'; return; }
    const title = document.createElement('div');
    title.textContent = 'Wybierz paletę (' + pallets.length + '):';
    list.appendChild(title);
    pallets.forEach(pallet => {
      const button = document.createElement('button');
      button.type = 'button';
      button.style.cssText = 'display:block;width:100%;text-align:left;margin-top:6px;padding:10px;border:1px solid #cbd5e1;border-radius:6px;background:#f8fafc;cursor:pointer;';
      button.textContent = pallet.nr_palety + ' — ' + (pallet.nazwa || '') + ' — ' + (pallet.lokalizacja || 'Brak lokalizacji') + ' — ' + pallet.ilosc + (pallet.inventory_type === 'Opakowanie' ? ' szt.' : ' kg');
      button.addEventListener('click', () => {
        clearPalletSuggestions();
        input.value = pallet.nr_palety;
        lookupPallet(pallet.nr_palety);
      });
      list.appendChild(button);
    });
  } catch (_) {
    if (version === palletSuggestionVersion) list.textContent = 'Nie udało się pobrać listy palet. Spróbuj ponownie.';
  }
}
