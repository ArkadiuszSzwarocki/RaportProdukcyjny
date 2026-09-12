function openPalletHistoryModal() {
    const modal = document.getElementById('palletFullHistoryModal');
    if (modal) {
        modal.style.display = 'flex';
    }
}

function closePalletHistoryModal() {
    const modal = document.getElementById('palletFullHistoryModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function fetchHistory() {
    if (!currentPallet || (!currentPallet.id && !currentPallet.displayId)) return;

    openPalletHistoryModal();

    const subtitleEl = document.getElementById('palletHistoryModalSubtitle');
    if (subtitleEl) {
        subtitleEl.textContent = `${currentPallet.displayId || ('#' + currentPallet.id)} • ${currentPallet.productName || ''} • ${currentPallet.amount || ''} ${currentPallet.unit || 'kg'}`;
    }

    const loadingEl = document.getElementById('palletHistoryLoading');
    const emptyEl = document.getElementById('palletHistoryEmpty');
    const tableContainerEl = document.getElementById('palletHistoryTableContainer');
    const tbody = document.getElementById('palletHistoryTableBody');

    if (loadingEl) loadingEl.style.display = 'block';
    if (emptyEl) emptyEl.style.display = 'none';
    if (tableContainerEl) tableContainerEl.style.display = 'none';
    if (tbody) tbody.innerHTML = '';

    const queryParams = new URLSearchParams({
        id: currentPallet.id || '',
        sscc: currentPallet.displayId || '',
        type: currentPallet.type || '',
        linia: currentPallet.linia || 'PSD'
    });

    fetch(`/warehouse-v2/api/pallet/history?${queryParams.toString()}`)
    .then(r => r.json())
    .then(data => {
        if (loadingEl) loadingEl.style.display = 'none';

        if (data.success && data.history && data.history.length > 0) {
            if (tableContainerEl) tableContainerEl.style.display = 'block';
            if (emptyEl) emptyEl.style.display = 'none';

            let html = '';
            data.history.forEach((h, idx) => {
                const typ = String(h.typ_ruchu || '').toUpperCase();
                let badgeStyle = 'background: #f1f5f9; color: #475569;';
                let label = h.typ_ruchu || 'RUCH';

                if (typ.includes('UTWORZ')) {
                    badgeStyle = 'background: #fef9c3; color: #854d0e; border: 1px solid #fef08a;';
                    label = 'Utworzenie Palety';
                } else if (typ.includes('POTWIERDZ') || typ.includes('PRZYJECIE') || typ.includes('PW')) {
                    badgeStyle = 'background: #dcfce7; color: #166534; border: 1px solid #bbf7d0;';
                    label = 'Przyjęcie / PW';
                } else if (typ.includes('PODZIAL_ODJECIE')) {
                    badgeStyle = 'background: #ffedd5; color: #9a3412; border: 1px solid #fed7aa;';
                    label = 'Podział (Odcięcie)';
                } else if (typ.includes('PODZIAL')) {
                    badgeStyle = 'background: #f3e8ff; color: #6b21a8; border: 1px solid #e9d5ff;';
                    label = 'Podział palety';
                } else if (typ.includes('PRZESUNI') || typ.includes('TRANSFER') || typ.includes('RELOKAC')) {
                    badgeStyle = 'background: #ede9fe; color: #5b21b6; border: 1px solid #ddd6fe;';
                    label = 'Przesunięcie';
                } else if (typ.includes('WYDANIE')) {
                    badgeStyle = 'background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe;';
                    label = 'Wydanie na produkcję';
                }

                let routeHtml = '-';
                const trasa = h.stacja_trasa || '';
                if (trasa && trasa.includes('->')) {
                    const parts = trasa.split('->').map(p => p.trim());
                    routeHtml = `<div style="display:inline-flex; align-items:center; gap:5px; font-weight:700;">
                        <span style="background:#f1f5f9; color:#475569; padding:2px 7px; border-radius:4px; font-size:11px; border:1px solid #e2e8f0;">${parts[0]}</span>
                        <span class="material-icons" style="font-size:14px; color:#6366f1;">arrow_forward</span>
                        <span style="background:#e0f2fe; color:#0369a1; padding:2px 7px; border-radius:4px; font-size:11px; border:1px solid #bae6fd;">${parts[1]}</span>
                    </div>`;
                } else if (trasa && trasa !== '-') {
                    routeHtml = `<span style="font-weight:700; color:#0284c7; background:#f0f9ff; padding:2px 7px; border-radius:4px; border:1px solid #e0f2fe;">${trasa}</span>`;
                }

                const bgRow = idx % 2 === 0 ? 'background: #ffffff;' : 'background: #f8fafc;';
                html += `
                    <tr style="${bgRow} border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 10px 12px; font-family: monospace; font-size: 11px; font-weight: 700; color: #334155; white-space: nowrap;">${h.autor_data || '-'}</td>
                        <td style="padding: 10px 12px;"><span style="display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 800; ${badgeStyle}">${label}</span></td>
                        <td style="padding: 10px 12px;">${routeHtml}</td>
                        <td style="padding: 10px 12px; color: #475569; max-width: 320px; line-height: 1.35;">${h.komentarz || '-'}</td>
                        <td style="padding: 10px 12px; font-weight: 600; color: #64748b; white-space: nowrap;">${h.autor_login || '-'}</td>
                    </tr>
                `;
            });
            if (tbody) tbody.innerHTML = html;
        } else {
            if (tableContainerEl) tableContainerEl.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'block';
        }
    })
    .catch(err => {
        if (loadingEl) loadingEl.style.display = 'none';
        if (emptyEl) {
            emptyEl.style.display = 'block';
            emptyEl.innerHTML = `<span class="material-icons" style="color:#dc2626; font-size:36px; display:block; margin-bottom:8px;">error</span>
            <div style="font-weight:700; color:#dc2626;">Błąd ładowania historii</div>
            <div style="font-size:12px; color:#64748b; margin-top:4px;">${err.message || 'Nie udało się połączyć z serwerem.'}</div>`;
        }
    });
}
