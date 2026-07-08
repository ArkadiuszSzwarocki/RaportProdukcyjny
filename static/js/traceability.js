function performSearch(event) {
    if (event) event.preventDefault();
    
    const query = document.getElementById('searchInput').value.trim();
    if (!query) return;
    
    const loader = document.getElementById('loader');
    const errorAlert = document.getElementById('errorAlert');
    const container = document.getElementById('resultsContainer');
    const btn = document.getElementById('searchBtn');
    
    loader.style.display = 'block';
    errorAlert.style.display = 'none';
    container.innerHTML = '';
    btn.disabled = true;
    
    fetch(`/api/traceability/search?q=${encodeURIComponent(query)}`)
        .then(res => res.json())
        .then(data => {
            loader.style.display = 'none';
            btn.disabled = false;
            
            if (data.error) {
                showError(data.error);
                return;
            }
            
            if (data.search_type === 'pallet' || data.pallet) {
                renderBottomUp(data);
            } else if (data.search_type === 'lot' || data.deliveries || data.plans) {
                renderTopDown(data);
            } else {
                showError("Nie znaleziono powiązań dla podanego zapytania.");
            }
        })
        .catch(err => {
            loader.style.display = 'none';
            btn.disabled = false;
            showError("Wystąpił błąd podczas komunikacji z serwerem.");
            console.error(err);
        });
}

function showError(msg) {
    const errorAlert = document.getElementById('errorAlert');
    errorAlert.textContent = msg;
    errorAlert.style.display = 'block';
}

function formatDate(dateStr) {
    if (!dateStr) return 'Brak danych';
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleString('pl-PL');
}

function renderBottomUp(data) {
    const container = document.getElementById('resultsContainer');
    
    let html = `<div class="trace-tree">`;
    
    // 1. Wyrób Gotowy
    const pal = data.pallet;
    html += `
        <div class="trace-level">
            <div class="trace-level-title"><i class="fas fa-pallet"></i> 1. Wyrób Gotowy (Paleta)</div>
            <div class="trace-card type-pallet">
                <div class="trace-card-header">
                    <h3 class="trace-card-title">${pal.nr_palety}</h3>
                    <span class="trace-card-badge">${pal.linia}</span>
                </div>
                <div class="trace-card-body">
                    <div class="trace-detail"><span>Produkt</span><strong>${pal.produkt}</strong></div>
                    <div class="trace-detail"><span>Waga netto</span><strong>${pal.waga_netto} kg</strong></div>
                    <div class="trace-detail"><span>Data</span><strong>${formatDate(pal.data_potwierdzenia)}</strong></div>
                </div>
            </div>
        </div>
    `;
    
    // 2. Plan Produkcji
    if (data.plan) {
        const p = data.plan;
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-industry"></i> 2. Zlecenie Produkcyjne</div>
                <div class="trace-card type-plan">
                    <div class="trace-card-header">
                        <h3 class="trace-card-title">Zlecenie #${p.id} - ${p.produkt}</h3>
                        <span class="trace-card-badge">${p.typ_produkcji}</span>
                    </div>
                    <div class="trace-card-body">
                        <div class="trace-detail"><span>Zlecenie</span><strong>${p.nazwa_zlecenia || '-'}</strong></div>
                        <div class="trace-detail"><span>Data planu</span><strong>${formatDate(p.data_planu)}</strong></div>
                    </div>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-industry"></i> 2. Zlecenie Produkcyjne</div>
                <div class="alert alert-warning m-0">Brak powiązanego zlecenia produkcyjnego (brak plan_id).</div>
            </div>
        `;
    }
    
    // 0. Receptura (Wzorzec) — sekcja dodana jeśli istnieje receptura
    if (data.receptura && data.receptura.length > 0) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title" style="color:#16a085;"><i class="fas fa-list-alt"></i> 0. Receptura — Wzorzec Produkcji (Nr: ${data.nr_receptury || '?'})</div>
                <div class="trace-card" style="border-left:4px solid #1abc9c;">
                    <div class="trace-card-header" style="background:linear-gradient(135deg,#e8faf8,#d1f5ef);">
                        <h3 class="trace-card-title" style="color:#16a085;">📋 Składniki receptury nr ${data.nr_receptury}</h3>
                        <span class="trace-card-badge" style="background:#1abc9c;">${data.receptura.length} składników</span>
                    </div>
                    <div class="trace-card-body" style="padding:0;">
                        <table style="width:100%; border-collapse:collapse; font-size:0.88em;">
                            <thead>
                                <tr style="background:#f0faf8; border-bottom:2px solid #1abc9c;">
                                    <th style="text-align:left; padding:7px 12px;">#</th>
                                    <th style="text-align:left; padding:7px 12px;">Składnik</th>
                                    <th style="text-align:right; padding:7px 12px;">Ilość [kg/szarżę]</th>
                                    <th style="text-align:center; padding:7px 12px;">Typ</th>
                                </tr>
                            </thead>
                            <tbody>
        `;
        data.receptura.forEach((s, i) => {
            const ilosc = s.ilosc_kg_szarza !== null && s.ilosc_kg_szarza !== undefined
                ? s.ilosc_kg_szarza + ' kg' : '—';
            html += `
                <tr style="border-bottom:1px solid #e5e7eb; ${i % 2 === 1 ? 'background:#f9fffe;' : ''}">
                    <td style="padding:6px 12px; color:#9ca3af; font-size:0.82em;">${i + 1}</td>
                    <td style="padding:6px 12px; font-weight:600;">${s.skladnik_nazwa}</td>
                    <td style="padding:6px 12px; text-align:right; color:#374151;">${ilosc}</td>
                    <td style="padding:6px 12px; text-align:center;">
                        <span style="background:${s.typ === 'dodatek' ? '#fef3c7' : '#e8faf8'};
                                     color:${s.typ === 'dodatek' ? '#b45309' : '#16a085'};
                                     border-radius:4px; padding:2px 7px; font-size:0.8em; font-weight:600;">
                            ${s.typ || 'surowiec'}
                        </span>
                    </td>
                </tr>`;
        });
        html += `</tbody></table></div></div></div>`;
    } else if (data.plan && data.plan.linia === 'AGRO' && data.nr_receptury) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title" style="color:#16a085;"><i class="fas fa-list-alt"></i> 0. Receptura — Wzorzec Produkcji</div>
                <div class="alert alert-info m-0">Receptura nr <strong>${data.nr_receptury}</strong> nie ma jeszcze zdefiniowanych składników. Dodaj je w panelu Zasyp → 📋 RECEPTURA.</div>
            </div>`;
    }

    // 3. Surowce
    if (data.materials && data.materials.length > 0) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-boxes"></i> 3. Zużyte Surowce (Zasypy)</div>
                <div style="display: flex; flex-direction: column; gap: 10px;">
        `;
        data.materials.forEach(m => {
            html += `
                <div class="trace-card type-material">
                    <div class="trace-card-header">
                        <h3 class="trace-card-title">${m.surowiec_nazwa || 'Nieznany surowiec'}</h3>
                        <span class="trace-card-badge">${m.status}</span>
                    </div>
                    <div class="trace-card-body">
                        <div class="trace-detail"><span>Ilość</span><strong>${Math.abs(m.zuzycie)} kg</strong></div>
                        <div class="trace-detail"><span>Nr Partii (Lot)</span><strong>${m.nr_partii || 'Brak wpisu'}</strong></div>
                        ${m.zbiornik ? `<div class="trace-detail"><span>Lokalizacja / Stacja</span><strong>${m.zbiornik} (${m.typ_ruchu || 'PRODUKCJA'})</strong></div>` : ''}
                        <div class="trace-detail"><span>Data użycia</span><strong>${formatDate(m.autor_data)}</strong></div>
                    </div>
                </div>
            `;
        });
        html += `</div></div>`;
    } else if (data.plan) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-boxes"></i> 3. Zużyte Surowce</div>
                <div class="alert alert-info m-0">Brak zarejestrowanych zużyć surowców w systemie magazynowym dla tego zlecenia.</div>
            </div>
        `;
    }
    
    html += `</div>`;
    container.innerHTML = html;
}

function renderTopDown(data) {
    const container = document.getElementById('resultsContainer');
    
    let html = `<div class="trace-tree">`;
    
    // 1. Dostawy (Przyjęcia)
    if (data.deliveries && data.deliveries.length > 0) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-truck-loading"></i> 1. Przyjęcia z Zewnątrz (Dostawy)</div>
                <div style="display: flex; flex-direction: column; gap: 10px;">
        `;
        data.deliveries.forEach(d => {
            html += `
                <div class="trace-card type-delivery">
                    <div class="trace-card-header">
                        <h3 class="trace-card-title">Dostawca: ${d.supplier || 'Nieznany'}</h3>
                        <span class="trace-card-badge">${d.status}</span>
                    </div>
                    <div class="trace-card-body">
                        <div class="trace-detail"><span>Data dostawy</span><strong>${formatDate(d.delivery_date)}</strong></div>
                        <div class="trace-detail"><span>Przyjął</span><strong>${d.potwierdzone_przez || '-'}</strong></div>
                    </div>
            `;
            if (d.matched_items && d.matched_items.length > 0) {
                html += `<div class="mt-3 pt-3 border-top"><strong class="small text-muted d-block mb-2">Znalezione partie w dostawie:</strong>`;
                d.matched_items.forEach(item => {
                    html += `
                        <div style="background: #f8fafc; padding: 10px; border-radius: 6px; margin-bottom: 5px; font-size: 0.9rem;">
                            <strong>${item.productName}</strong> - ${item.netWeight} ${item.packageForm === 'bags' ? 'kg' : item.packageForm}<br>
                            <span class="text-muted">Partia: ${item.nr_partii}</span>
                        </div>
                    `;
                });
                html += `</div>`;
            }
            html += `</div></div>`;
        });
        html += `</div></div>`;
    } else {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-truck-loading"></i> 1. Przyjęcia z Zewnątrz</div>
                <div class="alert alert-info m-0">Nie znaleziono dostaw dla tej partii w magazynie przyjęć.</div>
            </div>
        `;
    }

    // 2. Zużycia (Produkcja)
    if (data.plans && data.plans.length > 0) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-industry"></i> 2. Zlecenia Produkcyjne używające partii</div>
                <div style="display: flex; flex-direction: column; gap: 10px;">
        `;
        data.plans.forEach(p => {
            html += `
                <div class="trace-card type-plan">
                    <div class="trace-card-header">
                        <h3 class="trace-card-title">Zlecenie #${p.id} - ${p.produkt}</h3>
                        <span class="trace-card-badge">${p.linia}</span>
                    </div>
                    <div class="trace-card-body">
                        <div class="trace-detail"><span>Zlecenie</span><strong>${p.nazwa_zlecenia || '-'}</strong></div>
                        <div class="trace-detail"><span>Data planu</span><strong>${formatDate(p.data_planu)}</strong></div>
                    </div>
                </div>
            `;
        });
        html += `</div></div>`;
    } else {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-industry"></i> 2. Zlecenia Produkcyjne</div>
                <div class="alert alert-warning m-0">System nie odnotował jawnego zużycia tej partii w produkcjach (Brak nr_partii w przesunięciach na PRODUKCJA).</div>
            </div>
        `;
    }

    // 3. Wyroby Gotowe
    if (data.pallets && data.pallets.length > 0) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-pallet"></i> 3. Wyroby Gotowe (Potencjalnie powiązane)</div>
                <div style="display: flex; flex-direction: column; gap: 10px;">
        `;
        data.pallets.forEach(pal => {
            html += `
                <div class="trace-card type-pallet">
                    <div class="trace-card-header">
                        <h3 class="trace-card-title">${pal.nr_palety}</h3>
                        <span class="trace-card-badge">${pal.linia}</span>
                    </div>
                    <div class="trace-card-body">
                        <div class="trace-detail"><span>Produkt</span><strong>${pal.produkt}</strong></div>
                        <div class="trace-detail"><span>Waga</span><strong>${pal.waga_netto} kg</strong></div>
                        <div class="trace-detail"><span>Z planu</span><strong>#${pal.plan_id}</strong></div>
                    </div>
                </div>
            `;
        });
        html += `</div></div>`;
    } else if (data.plans && data.plans.length > 0) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-pallet"></i> 3. Wyroby Gotowe</div>
                <div class="alert alert-info m-0">Zlecenia nie wygenerowały jeszcze żadnych palet z wyrobem gotowym.</div>
            </div>
        `;
    }

    html += `</div>`;
    container.innerHTML = html;
}
