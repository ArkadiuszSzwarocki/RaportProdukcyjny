/* Dedicated AGRO input scanner. Uses the existing stock/traceability transactions. */
(() => {
  const form = document.getElementById('bigbag-scan-form');
  if (!form) return;
  const input = document.getElementById('bigbag-code');
  const button = document.getElementById('bigbag-save');
  const selector = document.getElementById('bigbag-order');
  const feedback = document.getElementById('bigbag-feedback');
  let busy = false;
  function render(settlement) {
    document.getElementById('bigbag-summary').textContent = `Wsad: ${settlement.total_bigbag_kg || 0} kg · Spakowano: ${settlement.total_packed_kg || 0} kg · Bilans: ${settlement.bilans_kg || 0} kg`;
    const body = document.getElementById('bigbag-rows');
    body.replaceChildren();
    (settlement.items || []).forEach(item => {
      const row = document.createElement('tr');
      [item.nr_palety,item.nazwa_produktu,item.nr_partii,item.waga_kg,item.lokalizacja_zrodlowa,
       `${item.autor_login || ''} · ${item.created_at_fmt || ''}`].forEach(value => {
        const cell = document.createElement('td'); cell.textContent = value ?? ''; row.appendChild(cell);
      });
      const action = document.createElement('td');
      const undo = document.createElement('button'); undo.type='button'; undo.textContent='Cofnij skan'; undo.className='btn-action';
      undo.onclick=async () => {
        if (busy) return;
        const confirmed = await AppDialog.confirm(`Wycofać Big Bag ${item.nr_palety}? Stan wróci do magazynu.`);
        if (confirmed && !busy) await send('/agro/workowanie/bigbag/remove', {entry_id:item.id,linia:'AGRO'});
      };
      action.appendChild(undo); row.appendChild(action); body.appendChild(row);
    });
    if (!body.children.length) {
      const row=document.createElement('tr'); const cell=document.createElement('td'); cell.colSpan=7; cell.textContent='Brak zeskanowanych Big Bagów.'; row.appendChild(cell); body.appendChild(row);
    }
  }
  async function send(url, data) {
    busy=true; input.disabled=true; button.disabled=true; selector.disabled=true;
    feedback.textContent='Zapisywanie…';
    try {
      const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      const result=await response.json();
      if (!response.ok || !result.success) throw Error(result.error || result.message || 'Nie zapisano skanu.');
      render(result.settlement); input.value=''; feedback.textContent=result.message || 'Skan zapisany.';
    } catch(error) { feedback.textContent=error.message; }
    finally { busy=false; input.disabled=false; button.disabled=false; selector.disabled=false; input.focus(); }
  }
  function scannedCode(raw) {
    const code=raw.trim();
    if (code.startsWith('{') && code.endsWith('}')) {
      try { const data=JSON.parse(code); return String(data.sscc || data.nr_palety || data.id || code); } catch (_) { return code; }
    }
    return code;
  }
  let debounce;
  input.addEventListener('input', () => {
    clearTimeout(debounce);
    const code=scannedCode(input.value);
    if (/^(?:[A-Z]{2,5}|\(00\))?\d{18}$/i.test(code)) {
      debounce=setTimeout(() => { if (!busy) form.requestSubmit(); },400);
    }
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    clearTimeout(debounce);
    if (busy || !input.value.trim()) return;
    send('/agro/workowanie/bigbag/add',{plan_id:Number(form.dataset.planId),code:scannedCode(input.value),linia:'AGRO'});
  });
  render(JSON.parse(document.getElementById('bigbag-initial').textContent));
})();
