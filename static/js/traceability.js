/**
 * @file traceability.js
 * @description Frontend logic for pallet and lot traceability with 3D graphical timeline flow.
 */

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

function getActionBadgeStyle(actionRaw) {
    const a = String(actionRaw || '').toUpperCase();
    // WMS 4-step workflow events must be matched before generic labels.
    if (a.includes('PZ_STREFA_PRZYJEC')) {
        return {
            bg: '#ecfdf5',
            border: '#86efac',
            text: '#166534',
            icon: 'move_to_inbox',
            nodeClass: 'active',
            label: 'PZ: DOSTAWA → STREFA PRZYJĘĆ'
        };
    }
    if (a.includes('SSCC') || a.includes('NADANIE')) {
        return {
            bg: '#fdf4ff',
            border: '#e879f9',
            text: '#86198f',
            icon: 'qr_code_2',
            nodeClass: '',
            label: 'NADANIE ETYKIETY SSCC (STREFA PRZYJĘĆ)'
        };
    }
    if (a.includes('PUTAWAY_POTW') || a.includes('PUTAWAY_CONFIRM')) {
        return {
            bg: '#f0fdf4',
            border: '#4ade80',
            text: '#166534',
            icon: 'where_to_vote',
            nodeClass: 'active',
            label: 'PUTAWAY: OCZEKUJĄCE → LOKALIZACJA'
        };
    }
    if (a.includes('PUTAWAY')) {
        return {
            bg: '#eef2ff',
            border: '#a5b4fc',
            text: '#3730a3',
            icon: 'forklift',
            nodeClass: '',
            label: 'PUTAWAY: STREFA PRZYJĘĆ → OCZEKUJĄCE'
        };
    }
    if (a.includes('AWIZACJA')) {
        return {
            bg: '#fefce8',
            border: '#fde047',
            text: '#854d0e',
            icon: 'fact_check',
            nodeClass: 'warning',
            label: 'AWIZACJA (WERYFIKACJA WZ)'
        };
    }

    if (a.includes('ODRZU') || a.includes('REJECT') || a.includes('ANULOW')) {
        const isMM = a.includes('MM');
        return {
            bg: '#fff1f2',
            border: '#fda4af',
            text: '#9f1239',
            icon: 'highlight_off',
            nodeClass: 'danger',
            label: isMM ? 'ODRZUCENIE (MM)' : 'ODRZUCENIE (PZ / DOSTAWA)'
        };
    }
    if (a.includes('ZUZYCIE') || a.includes('ARCHIW') || a.includes('USUN')) {
        return {
            bg: '#fef2f2',
            border: '#fca5a5',
            text: '#991b1b',
            icon: 'delete_forever',
            nodeClass: 'danger',
            label: 'ROZCHÓD / ZUŻYCIE 0 KG'
        };
    }
    if ((a.includes('ZLECENIE') && !a.includes('PUTAWAY')) || a.includes('PLAN')) {
        return {
            bg: '#fffbeb',
            border: '#fcd34d',
            text: '#92400e',
            icon: 'assignment',
            nodeClass: 'warning',
            label: 'ZLECENIE PRZESUNIĘCIA (MM)'
        };
    }
    if (a.includes('PRZESUN') || a.includes('RELOKAC') || (a.includes('MM') && !a.includes('ZLECENIE'))) {
        return {
            bg: '#eff6ff',
            border: '#93c5fd',
            text: '#1e40af',
            icon: 'swap_horiz',
            nodeClass: 'active',
            label: 'PRZESUNIĘCIE (MM)'
        };
    }
    if (a.includes('POTWIERDZ')) {
        return {
            bg: '#f0fdf4',
            border: '#86efac',
            text: '#14532d',
            icon: 'verified',
            nodeClass: 'active',
            label: 'POTWIERDZENIE / REJESTRACJA'
        };
    }
    if (a.includes('PRZYJ') || a.includes('DOSTAWA') || a.includes('PZ')) {
        return {
            bg: '#ecfdf5',
            border: '#86efac',
            text: '#166534',
            icon: 'input',
            nodeClass: 'active',
            label: 'PRZYJĘCIE (PZ / DOSTAWA)'
        };
    }
    if (a.includes('UTWORZ') || a.includes('PW')) {
        return {
            bg: '#faf5ff',
            border: '#d8b4fe',
            text: '#6b21a8',
            icon: 'add_circle',
            nodeClass: '',
            label: 'UTWORZENIE PALETY'
        };
    }
    if (a.includes('RUCH')) {
        return {
            bg: '#eff6ff',
            border: '#93c5fd',
            text: '#1e40af',
            icon: 'swap_horiz',
            nodeClass: '',
            label: 'RUCH MAGAZYNOWY'
        };
    }
    return {
        bg: '#f8fafc',
        border: '#cbd5e1',
        text: '#334155',
        icon: 'history',
        nodeClass: '',
        label: a.replace(/_/g, ' ') || 'RUCH'
    };
}

function renderPalletHero(pallet) {
    const isArchived = (pallet.type === 'ARCHIWUM') || (Number(pallet.waga_netto || 0) <= 0);
    return `
        <div class="pallet-hero-summary">
            <div class="phs-head">
                <div>
                    <div style="font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; color:#94a3b8; font-weight:700;">Identyfikator Palety</div>
                    <h2 class="phs-title">
                        ${pallet.produkt || 'Nieznany materiał'}
                        <span class="phs-sscc">${pallet.nr_palety}</span>
                    </h2>
                </div>
                <div>
                    ${isArchived 
                        ? `<span style="background:#ef4444; color:#ffffff; padding:6px 14px; border-radius:999px; font-size:0.82rem; font-weight:800; display:inline-flex; align-items:center; gap:6px;"><span class="material-icons" style="font-size:16px;">archive</span> ZARCHIWIZOWANA (0 KG)</span>`
                        : `<span style="background:#10b981; color:#ffffff; padding:6px 14px; border-radius:999px; font-size:0.82rem; font-weight:800; display:inline-flex; align-items:center; gap:6px;"><span class="material-icons" style="font-size:16px;">check_circle</span> NA STANIE AKTYWNYM</span>`
                    }
                </div>
            </div>
            <div class="phs-grid">
                <div class="phs-card">
                    <div class="lbl">Aktualny stan / waga</div>
                    <div class="val">${pallet.waga_netto || 0} kg</div>
                </div>
                <div class="phs-card">
                    <div class="lbl">Typ zasobu</div>
                    <div class="val">${pallet.type || 'SUROWIEC'}</div>
                </div>
                <div class="phs-card">
                    <div class="lbl">Hala / Linia</div>
                    <div class="val">Hala ${pallet.linia || 'AGRO'}</div>
                </div>
                <div class="phs-card">
                    <div class="lbl">Ostatnia rejestracja</div>
                    <div class="val" style="font-size:0.9rem;">${formatDate(pallet.data_potwierdzenia)}</div>
                </div>
            </div>
        </div>
    `;
}

function renderTimeline3D(timeline) {
    if (!timeline || timeline.length === 0) {
        return `
            <div class="trace-timeline-wrap">
                <div class="trace-timeline-header">
                    <div class="trace-timeline-title"><span class="material-icons" style="color:#2563eb;">timeline</span> ⏱️ Chronologia zdarzeń palety (Traceability)</div>
                </div>
                <div style="padding:20px; text-align:center; color:#64748b; font-weight:600;">Brak zarejestrowanych ruchów dla tej palety.</div>
            </div>
        `;
    }

    let itemsHtml = '';
    timeline.forEach(step => {
        const actionType = step.typ_ruchu || step.typ || 'RUCH';
        const badge = getActionBadgeStyle(actionType);
        const dateStr = step.autor_data || step.data || '—';
        const user = step.autor_login || step.user || 'system';
        const src = step.lokalizacja_zrodlowa || step.skad || '';
        const dst = step.lokalizacja_docelowa || step.dokad || '';
        const comment = step.komentarz || '';

        let routeBanner = '';
        if (src || dst) {
            routeBanner = `
                <div class="flow-route-banner">
                    <span class="loc-box">${src || '—'}</span>
                    <span class="material-icons" style="font-size:16px; color:#2563eb;">arrow_forward</span>
                    <span class="loc-box">${dst || '—'}</span>
                </div>
            `;
        }

        itemsHtml += `
            <div class="flow-step-row">
                <div class="flow-step-node ${badge.nodeClass}"></div>
                <div class="flow-step-card">
                    <div class="flow-step-top">
                        <span class="flow-action-badge" style="background:${badge.bg}; color:${badge.text}; border:1px solid ${badge.border};">
                            <span class="material-icons" style="font-size:16px;">${badge.icon}</span>
                            ${badge.label}
                        </span>
                        <span class="flow-time"><span class="material-icons" style="font-size:14px; vertical-align:middle;">schedule</span> ${dateStr}</span>
                    </div>
                    ${routeBanner}
                    ${comment ? `<div class="flow-desc">${comment}</div>` : ''}
                    <div class="flow-actor">
                        <span class="material-icons" style="font-size:15px; color:#64748b;">person</span>
                        Użytkownik: <strong style="color:#0f172a; margin-left:3px;">@${user}</strong>
                    </div>
                </div>
            </div>
        `;
    });

    return `
        <div class="trace-timeline-wrap">
            <div class="trace-timeline-header">
                <div class="trace-timeline-title">
                    <span class="material-icons" style="color:#2563eb; font-size:24px;">route</span>
                    Chronologia Zdarzeń Palety (Ścieżka Ruchów & Audyt)
                </div>
                <span style="font-size:0.85rem; font-weight:700; color:#475569; background:#f1f5f9; padding:4px 10px; border-radius:8px;">
                    Zdarzeń: ${timeline.length}
                </span>
            </div>
            <div class="timeline-3d-flow">
                ${itemsHtml}
            </div>
        </div>
    `;
}

function renderBottomUp(data) {
    const container = document.getElementById('resultsContainer');
    const pal = data.pallet;
    
    let html = '';
    
    // 1. Pallet Hero Summary
    html += renderPalletHero(pal);

    // 2. Timeline 3D Flow with Arrows & Actors
    html += renderTimeline3D(data.timeline || data.lifecycle);

    html += `<div class="trace-tree">`;

    // 3. Plan Produkcji (jeśli istnieje)
    if (data.plan) {
        const p = data.plan;
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-industry"></i> Zlecenie Produkcyjne</div>
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
    }

    // 4. Receptura (Wzorzec)
    if (data.receptura && data.receptura.length > 0) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title" style="color:#16a085;"><i class="fas fa-list-alt"></i> Receptura — Wzorzec Produkcji (Nr: ${data.nr_receptury || '?'})</div>
                <div class="trace-card" style="border-left:4px solid #1abc9c;">
                    <div class="trace-card-header" style="background:linear-gradient(135deg,#e8faf8,#d1f5ef);">
                        <h3 class="trace-card-title" style="color:#16a085;">📋 Składniki receptury nr ${data.nr_receptury}</h3>
                        <span class="trace-card-badge" style="background:#1abc9c; color:#fff;">${data.receptura.length} składników</span>
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
            const ilosc = s.ilosc_kg_szarza !== null && s.ilosc_kg_szarza !== undefined ? s.ilosc_kg_szarza + ' kg' : '—';
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
    }

    // 5. Surowce powiązane
    if (data.materials && data.materials.length > 0) {
        html += `
            <div class="trace-level">
                <div class="trace-level-title"><i class="fas fa-boxes"></i> Zużyte Surowce (Zasypy)</div>
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
    }

    html += `</div>`;
    container.innerHTML = html;
}
