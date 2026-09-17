
function getExpiryStatus(dateExpStr) {
    if (!dateExpStr || dateExpStr === '-' || dateExpStr === 'brak') {
        return {
            monthsLeft: null,
            daysLeft: null,
            borderColor: '#cbd5e1',
            badgeBg: '#f1f5f9',
            badgeColor: '#64748b',
            textColor: '#64748b',
            label: ''
        };
    }

    const expDate = new Date(dateExpStr);
    if (isNaN(expDate.getTime())) {
        return {
            monthsLeft: null,
            daysLeft: null,
            borderColor: '#cbd5e1',
            badgeBg: '#f1f5f9',
            badgeColor: '#64748b',
            textColor: '#64748b',
            label: ''
        };
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diffTime = expDate.getTime() - today.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    const diffMonths = diffDays / 30.44;

    if (diffDays < 0) {
        return {
            isExpired: true,
            isSystemBlocked: true,
            monthsLeft: 0,
            daysLeft: diffDays,
            borderColor: '#dc2626', // Deep red: expired
            badgeBg: '#fee2e2',
            badgeColor: '#991b1b',
            textColor: '#dc2626',
            label: 'ZABLOKOWANA: PO TERMINIE'
        };
    } else if (diffMonths <= 2) {
        // <= 2 months: Red
        return {
            isExpired: false,
            monthsLeft: Math.max(0, Math.round(diffMonths * 10) / 10),
            daysLeft: diffDays,
            borderColor: '#ef4444',
            badgeBg: '#fee2e2',
            badgeColor: '#b91c1c',
            textColor: '#ef4444',
            label: `${diffDays} dni`
        };
    } else if (diffMonths <= 3) {
        // 2 - 3 months: Orange
        return {
            isExpired: false,
            monthsLeft: Math.round(diffMonths * 10) / 10,
            daysLeft: diffDays,
            borderColor: '#f97316',
            badgeBg: '#ffedd5',
            badgeColor: '#c2410c',
            textColor: '#ea580c',
            label: `${Math.round(diffMonths)} mies.`
        };
    } else if (diffMonths <= 5) {
        // 3 - 5 months: Yellow / Amber
        return {
            isExpired: false,
            monthsLeft: Math.round(diffMonths * 10) / 10,
            daysLeft: diffDays,
            borderColor: '#eab308',
            badgeBg: '#fef9c3',
            badgeColor: '#854d0e',
            textColor: '#ca8a04',
            label: `${Math.round(diffMonths)} mies.`
        };
    } else {
        // > 5 months: Neutral gray
        return {
            isExpired: false,
            monthsLeft: Math.round(diffMonths * 10) / 10,
            daysLeft: diffDays,
            borderColor: '#cbd5e1',
            badgeBg: '#f8fafc',
            badgeColor: '#64748b',
            textColor: '#475569',
            label: ''
        };
    }
}

function formatPackagingBadge(pkgType, palletId, type, linia) {
    const raw = String(pkgType || '').toUpperCase();
    const clickAttr = palletId 
        ? `onclick="event.stopPropagation(); if(typeof openChangePackagingForPallet==='function'){openChangePackagingForPallet('${palletId}', '${(pkgType || 'Worek (25kg)').replace(/'/g, "\\'")}', '${type || ''}', '${linia || ''}');}" style="cursor: pointer; transition: transform 0.15s ease;" onmouseover="this.style.transform='scale(1.04)'" onmouseout="this.style.transform='scale(1)'" title="Kliknij, aby zmienić rodzaj opakowania"`
        : '';

    if (raw.includes('BIG') || raw.includes('BB') || raw.includes('1000')) {
        return `<span class="badge badge-packaging-bb" ${clickAttr} style="background: #fef3c7; color: #b45309; border: 1px solid #fde68a; font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; ${palletId ? 'cursor:pointer;' : ''}">
            <span class="material-icons" style="font-size: 12px; color: #d97706;">shopping_bag</span> Big Bag (1000kg)
        </span>`;
    }
    if (raw.includes('50KG')) {
        return `<span class="badge badge-packaging-bag50" ${clickAttr} style="background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; ${palletId ? 'cursor:pointer;' : ''}">
            <span class="material-icons" style="font-size: 12px; color: #22c55e;">inventory_2</span> Worek (50kg)
        </span>`;
    }
    if (raw.includes('KARTON') || raw.includes('OPAKOWANIE')) {
        return `<span class="badge badge-packaging-box" ${clickAttr} style="background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; ${palletId ? 'cursor:pointer;' : ''}">
            <span class="material-icons" style="font-size: 12px; color: #64748b;">all_inbox</span> Karton / Opak.
        </span>`;
    }
    if (raw.includes('ROLKA') || raw.includes('FOLIA')) {
        return `<span class="badge badge-packaging-roll" ${clickAttr} style="background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; ${palletId ? 'cursor:pointer;' : ''}">
            <span class="material-icons" style="font-size: 12px; color: #0ea5e9;">rotate_90_degrees_cw</span> Rolka / Folia
        </span>`;
    }
    return `<span class="badge badge-packaging-bag" ${clickAttr} style="background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; ${palletId ? 'cursor:pointer;' : ''}">
        <span class="material-icons" style="font-size: 12px; color: #10b981;">inventory_2</span> ${pkgType || 'Worek (25kg)'}
    </span>`;
}

function formatOrderBadge(item) {
    if (!item.order_doc_label && !item.order_ref && !item.order_id) {
        return '<span style="color: #94a3b8; font-size: 11px;">—</span>';
    }

    const docType = String(item.order_doc_type || 'MM').toUpperCase();
    const docLabel = item.order_doc_label || (docType + ': #' + String(item.order_id || '').substring(0, 8));
    const source = item.order_source || '';

    let badgeBg = '#f1f5f9';
    let badgeColor = '#475569';
    let borderColor = '#cbd5e1';
    let iconName = 'description';

    if (docType === 'PZ') {
        badgeBg = '#dbeafe';
        badgeColor = '#1e40af';
        borderColor = '#93c5fd';
        iconName = 'archive'; // Przyjęcie z zewnątrz
    } else if (docType === 'MM') {
        badgeBg = '#fef3c7';
        badgeColor = '#b45309';
        borderColor = '#fde68a';
        iconName = 'swap_horiz'; // Przesunięcie wewnętrzne
    } else if (docType === 'WZ') {
        badgeBg = '#fee2e2';
        badgeColor = '#991b1b';
        borderColor = '#fca5a5';
        iconName = 'unarchive'; // Wydanie
    } else if (docType === 'PROD') {
        badgeBg = '#ede9fe';
        badgeColor = '#6d28d9';
        borderColor = '#ddd6fe';
        iconName = 'precision_manufacturing'; // Produkcja / Plan
    }

    const dateStr = item.order_date ? `<span style="color: #475569; font-weight: 600;">${item.order_date}</span>` : '';
    const sourceStr = source ? `z: <strong style="color: #334155;">${source}</strong>` : '';
    const subInfo = [dateStr, sourceStr].filter(Boolean).join(' • ');
    const sourceHtml = subInfo ? `<div style="font-size: 10px; color: #64748b; margin-top: 2px; white-space: nowrap;">${subInfo}</div>` : '';

    return `<div style="display: inline-flex; flex-direction: column; align-items: flex-start;">
        <span class="badge" style="background: ${badgeBg}; color: ${badgeColor}; border: 1px solid ${borderColor}; font-size: 10px; font-weight: 800; padding: 2px 7px; border-radius: 5px; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;">
            <span class="material-icons" style="font-size: 11px;">${iconName}</span> ${docLabel}
        </span>
        ${sourceHtml}
    </div>`;
}

function generateTableRow(item, index) {
    const expiry = getExpiryStatus(item.date_exp);
    const isExpired = Boolean(expiry.isExpired);
    const isBlocked = Boolean(item.is_blocked) || isExpired;
    const isFirstFifo = Boolean(item.is_first_fifo) && !isBlocked && !isExpired;

    const isBlockedCls = isBlocked ? 'is-blocked-row' : '';
    const rowStyle = `cursor: pointer; background: ${isBlocked ? '#fff1f2' : '#ffffff'} !important; border-left: 4px solid ${expiry.borderColor} !important;`;

    const icon = isBlocked 
        ? '<span class="material-icons" style="color: #dc2626; font-size: 16px;" title="Paleta zablokowana systemowo">block</span>' 
        : (isFirstFifo 
            ? '<span class="material-icons" style="color: #ea580c; font-size: 16px;" title="Pierwsza partia do zużycia (FIFO)">bolt</span>'
            : '<span class="material-icons" style="color: #10b981; font-size: 16px;">check_circle</span>');
    
    // Clean, compact FIFO tag without artificial batch numbering (strictly for eligible non-expired pallets)
    const fifoBadge = isFirstFifo
        ? `<span class="badge fifo-tag" style="background: #ea580c; color: #ffffff; font-size: 9px; font-weight: 800; padding: 1px 6px; border-radius: 4px; display: inline-flex; align-items: center; gap: 2px; vertical-align: middle; white-space: nowrap; margin-left: 5px; width: auto; max-width: fit-content; box-shadow: none;">
                <span class="material-icons" style="font-size: 11px;">bolt</span> FIFO
           </span>`
        : '';

    const batchSubtitle = (item.batch && item.batch !== '-' && item.batch !== 'brak')
        ? `<span class="batch-subtitle-wrapper" style="font-size: 11px; color: #64748b; font-weight: 600;">Partia: <span style="font-family: monospace; color: #334155; font-weight: 700;">${item.batch}</span></span>`
        : '';

    const displayName = (item.productName && item.productName !== '-' && item.productName.trim() !== '') ? item.productName : (item.produkt || item.nazwa || 'Nieznany produkt');

    return `<tr class="pallet-row ${isBlockedCls}"
                style="${rowStyle}"
                data-display-id="${item.displayId}"
                data-product="${displayName.replace(/"/g, '&quot;')}"
                data-packaging="${(item.packaging_type || 'Worek (25kg)').replace(/"/g, '&quot;')}"
                data-amount="${item.amount}"
                data-unit="${item.unit || 'kg'}"
                data-location="${item.location}"
                data-type="${item.type}"
                data-date="${item.date_prod}"
                data-date-exp="${item.date_exp || '-'}"
                data-batch="${(item.batch || '-').replace(/"/g, '&quot;')}"
                data-id="${item.id}"
                data-linia="${item.linia}"
                data-blocked="${isBlocked ? '1' : '0'}"
                data-date-added="${item.date_added}">
        <td style="text-align: center; color: #94a3b8; font-weight: 700; background: #f8fafc; font-size: 11px;">${index}</td>
        <td class="pallet-id-cell" style="color: #64748b; font-weight: 700; font-family: monospace; font-size: 11px;">
            <div class="pallet-id-header-flow" style="display: flex; align-items: center; gap: 6px;">
                <span class="pallet-id-number">#${item.id || '-'}</span>
                ${fifoBadge ? `<span class="mobile-header-badge">${fifoBadge}</span>` : ''}
                ${expiry.label ? `<span class="mobile-header-badge badge expiry-status-pill" style="background: ${expiry.badgeBg}; color: ${expiry.badgeColor}; border: 1px solid ${expiry.borderColor}; font-size: 9px; font-weight: 800; padding: 1px 5px; border-radius: 3px; display: inline-flex; align-items: center; gap: 2px; width: fit-content; text-transform: uppercase;">${isExpired ? '<span class="material-icons" style="font-size: 10px;">block</span> ' : ''}${expiry.label}</span>` : ''}
            </div>
        </td>
        <td class="font-bold desktop-sscc-cell">
            <div style="display: flex; align-items: center; gap: 6px;">
                ${icon}
                ${item.displayId}
            </div>
        </td>
        <td data-label="Produkt" class="product-cell">
            <div class="product-inline-flow" style="display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px;">
                <strong class="text-primary product-title" style="font-size: 13px; font-weight: 700; color: #0f172a;">${displayName}</strong>
                ${fifoBadge ? `<span class="desktop-only-fifo">${fifoBadge}</span>` : ''}
                <span class="mobile-sscc-badge" style="display: none; align-items: center; gap: 4px; font-family: ui-monospace, monospace; font-size: 12px; font-weight: 700; color: #1e293b;">
                    ${icon}
                    <span>${item.displayId}</span>
                </span>
                ${batchSubtitle}
            </div>
        </td>
        <td data-label="Opakowanie" class="packaging-cell">
            ${formatPackagingBadge(item.packaging_type, item.id, item.type, item.linia)}
        </td>
        <td data-label="Ilość" class="amount-cell">
            <div class="amount-box-inner">
                <strong class="amount-val">${item.amount}</strong>
                <span class="amount-unit">${item.unit || 'kg'}</span>
            </div>
        </td>
        <td data-label="Lokalizacja" class="location-cell" data-loc-raw="${item.location}">
            <div class="location-box-inner">
                <span class="material-icons" style="font-size: 14px; color: #2563eb;">place</span>
                <span class="loc-text">${formatLocation(item.location)}</span>
            </div>
        </td>
        <td data-label="Typ">
            <span class="status-badge" style="font-size: 10px; padding: 2px 8px;">${item.type}</span>
        </td>
        <td data-label="Zlecenie / Dok." class="order-doc-cell">
            ${formatOrderBadge(item)}
        </td>
        <td data-label="Produkcja" class="time-display">${item.date_prod}</td>
        <td data-label="Ważność" class="time-display expiry-cell" style="white-space: nowrap;">
            <div class="expiry-box-inner">
                <span class="expiry-date-val" style="color: ${expiry.textColor}; font-weight: 700; font-size: 12px;">${item.date_exp || '-'}</span>
                ${expiry.label ? `<span class="desktop-only-expiry-pill badge expiry-status-pill" style="background: ${expiry.badgeBg}; color: ${expiry.badgeColor}; border: 1px solid ${expiry.borderColor}; font-size: 9px; font-weight: 800; padding: 1px 5px; border-radius: 3px; display: inline-flex; align-items: center; gap: 2px; width: fit-content; text-transform: uppercase;">${isExpired ? '<span class="material-icons" style="font-size: 10px;">block</span> ' : ''}${expiry.label}</span>` : ''}
            </div>
        </td>
    </tr>`;
}

function generateGridCard(item) {
    const expiry = getExpiryStatus(item.date_exp);
    const isExpired = Boolean(expiry.isExpired);
    const isBlocked = Boolean(item.is_blocked) || isExpired;
    const isFirstFifo = Boolean(item.is_first_fifo) && !isBlocked && !isExpired;

    const isBlockedCls = isBlocked ? 'is-blocked-card' : '';
    const cardFifoStyle = `border-left: 4px solid ${expiry.borderColor} !important; background: ${isBlocked ? '#fff1f2' : '#ffffff'} !important;`;
    const icon = isBlocked 
        ? '<span class="material-icons text-danger" style="font-size: 18px;" title="Paleta zablokowana">block</span>' 
        : (isFirstFifo 
            ? '<span class="badge fifo-tag" style="background: #ea580c; color: white; font-size: 9px; font-weight: 800; padding: 1px 5px; border-radius: 4px; display: inline-flex; align-items: center; gap: 2px;"><span class="material-icons" style="font-size: 10px;">bolt</span> FIFO</span>' 
            : '');

    let loc_code = (item.location || '').toUpperCase();
    let loc_html = item.location || '???';
    if (loc_code.length >= 7 && loc_code.startsWith('R')) {
        loc_html = `<span class="location-part-rack">${loc_code.substring(0,3)}</span>
                    <span class="location-separator"> </span>
                    <span class="location-part-place">${loc_code.substring(3,5)}</span>
                    <span class="location-separator"> </span>
                    <span class="location-part-row">${loc_code.substring(5,7)}</span>`;
    }

    const batchSubtitle = (item.batch && item.batch !== '-' && item.batch !== 'brak')
        ? `<div style="font-size: 11px; color: #64748b; font-weight: 600; margin-top: 2px;">Partia: <span style="font-family: monospace; color: #334155; font-weight: 700;">${item.batch}</span></div>`
        : '';

    const displayName = (item.productName && item.productName !== '-' && item.productName.trim() !== '') ? item.productName : (item.produkt || item.nazwa || 'Nieznany produkt');

    return `<div class="pallet-card ${isBlockedCls}"
                 style="cursor: pointer; ${cardFifoStyle}"
                 data-display-id="${item.displayId}"
                 data-product="${displayName.replace(/"/g, '&quot;')}"
                 data-packaging="${(item.packaging_type || 'Worek (25kg)').replace(/"/g, '&quot;')}"
                 data-amount="${item.amount}"
                 data-unit="${item.unit || 'kg'}"
                 data-location="${item.location}"
                 data-type="${item.type}"
                 data-date="${item.date_prod}"
                 data-date-exp="${item.date_exp || '-'}"
                 data-batch="${(item.batch || '-').replace(/"/g, '&quot;')}"
                 data-id="${item.id}"
                 data-linia="${item.linia}"
                 data-blocked="${item.is_blocked}"
                 data-date-added="${item.date_added}">
        <div class="card-header">
            <span class="loc-tag" data-loc-raw="${item.location}">
                <span class="material-icons" style="font-size: 13px; color: #2563eb; vertical-align: middle; margin-right: 2px;">place</span>
                ${loc_html}
            </span>
            <span class="id-tag">#${item.displayId}</span>
        </div>
        <div class="card-body">
            <div class="product-name">${displayName}</div>
            <div style="margin: 4px 0;">${formatPackagingBadge(item.packaging_type, item.id, item.type, item.linia)}</div>
            ${batchSubtitle}
            <div class="amount-row">
                <span class="val">${item.amount}</span>
                <span class="unit">${item.unit}</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: #64748b; margin-top: 6px; padding-top: 4px; border-top: 1px dashed #e2e8f0;">
                <span>Prod: <strong style="color: #334155;">${item.date_prod}</strong></span>
                <span>Ważn: <strong style="color: ${expiry.textColor};">${item.date_exp}</strong> ${expiry.label ? `<span class="badge" style="background: ${expiry.badgeBg}; color: ${expiry.badgeColor}; font-size: 9px; font-weight: 700; padding: 1px 4px; border-radius: 3px; margin-left: 2px;">${expiry.label}</span>` : ''}</span>
            </div>
        </div>
        <div class="card-footer" style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">
            <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <span class="type-label">${item.type}</span>
                ${(item.order_doc_label || item.order_ref || item.order_id) ? formatOrderBadge(item) : ''}
            </div>
            ${icon}
        </div>
    </div>`;
}

function _updateFilterBanner(filter, visible, total) {
    let banner = document.getElementById('filterStatusBanner');
    const tableWrapper = document.querySelector('.list-view-wrapper');
    if (!tableWrapper) return;

    const hasSearch = filter && filter.length > 0;
    const hasWarehouse = currentWarehouseId && currentWarehouseId !== 'all';
    const hasRack = currentSubWarehouseId && currentSubWarehouseId !== 'all';
    const checkboxes = document.querySelectorAll('.loc-checkbox');
    const totalCheckboxes = checkboxes.length;
    const hasLocationFilter = Array.isArray(selectedLocations) && totalCheckboxes > 0 && selectedLocations.length < totalCheckboxes;
    const isFiltered = Boolean(hasSearch || hasWarehouse || hasRack || hasLocationFilter || visible < total);

    if (!isFiltered) {
        if (banner) banner.style.display = 'none';
        return;
    }

    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'filterStatusBanner';
        banner.style.cssText = [
            'display:flex', 'align-items:center', 'gap:8px',
            'padding:8px 12px', 'margin-bottom:10px',
            'background:#eff6ff',
            'border:1px solid #bfdbfe',
            'border-radius:10px',
            'font-size:13px', 'font-weight:500', 'color:#1e40af',
            'flex-wrap:wrap', 'justify-content:space-between'
        ].join(';');
        tableWrapper.insertAdjacentElement('beforebegin', banner);
    }

    // Build filter badges
    const parts = [];
    if (hasSearch) parts.push(`Szukaj: <strong>"${filter}"</strong>`);
    if (hasWarehouse) parts.push(`Magazyn: <strong>${currentWarehouseId}</strong>`);
    if (hasRack) parts.push(`Regał: <strong>${currentSubWarehouseId}</strong>`);
    if (hasLocationFilter) parts.push(`Wybrane lokacje: <strong>${selectedLocations.length}/${totalCheckboxes}</strong>`);

    const hidden = total - visible;
    const resultInfo = hidden > 0
        ? `<span style="background:#1d4ed8;color:#fff;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;">Wyświetlono ${visible} z ${total} palet (${hidden} ukrytych)</span>`
        : `<span style="background:#10b981;color:#fff;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;">Wszystkie ${total} palet</span>`;

    banner.style.display = 'flex';
    banner.innerHTML = `
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <span>${parts.length > 0 ? parts.join(' | ') : 'Filtrowanie aktywne'}</span>
            ${resultInfo}
        </div>
        <button onclick="clearAllFilters()" style="border:none;background:none;cursor:pointer;color:#64748b;font-size:16px;padding:2px 6px;line-height:1;display:flex;align-items:center;border-radius:4px;" title="Wyczyść wszystkie filtry">
            <span class="material-icons" style="font-size:18px;">close</span>
        </button>
    `;
}

function clearAllFilters() {
    const input = document.getElementById('searchInput');
    if (input) { 
        input.value = ''; 
        localStorage.removeItem('warehouse_search'); 
    }
    const clearBtn = document.getElementById('clearSearchBtn');
    if (clearBtn) clearBtn.style.display = 'none';
    currentSearchQuery = '';

    // Reset radio buttons
    const allWh = document.getElementById('radio-all');
    if (allWh) { 
        allWh.checked = true; 
        currentWarehouseId = 'all'; 
        localStorage.setItem('warehouse_tab', 'all');
        if (typeof updateWhLabel === 'function') updateWhLabel('Wszystkie');
    }
    const allRack = document.getElementById('rack-all');
    if (allRack) { 
        allRack.checked = true; 
        currentSubWarehouseId = 'all'; 
        localStorage.setItem('warehouse_subtab', 'all');
        if (typeof updateRackLabel === 'function') updateRackLabel('Wszystkie Lokalizacje');
    }

    // Reset location checkboxes
    localStorage.removeItem('warehouse_locations');
    const checkboxes = document.querySelectorAll('.loc-checkbox');
    checkboxes.forEach(cb => cb.checked = true);
    selectedLocations = Array.from(checkboxes).map(cb => cb.value);
    if (typeof updateLocationDropdownLabel === 'function') {
        updateLocationDropdownLabel(checkboxes.length);
    }

    // Reset sorting
    currentSortCol = null;
    currentSortDir = 'asc';
    localStorage.removeItem('warehouse_sort_col');
    localStorage.removeItem('warehouse_sort_dir');
    if (typeof updateSortHeaderIndicators === 'function') {
        updateSortHeaderIndicators();
    }

    filterTable();
}

function isMatch(allText, locText, filter, locationFiltersArray) {
    const filterText = (filter || '').toUpperCase().trim();
    const textMatch = (filterText === "" || allText.indexOf(filterText) > -1);
    const slotMatch = (filterText !== "" && matchesLocationSlots(locText, filterText));

    if (!(textMatch || slotMatch)) return false;
    
    if (Array.isArray(locationFiltersArray)) {
        if (locationFiltersArray.length === 0) {
            return false;
        }
        const upLoc = (locText || '').toUpperCase().trim();
        if (!upLoc) {
            const allowsEmpty = locationFiltersArray.includes('BRAK') || 
                                locationFiltersArray.includes('OCZEKUJĄCE') ||
                                locationFiltersArray.includes('BEZ LOKACJI');
            if (!allowsEmpty) return false;
        } else {
            const matched = locationFiltersArray.some(f => {
                const uf = (f || '').toUpperCase().trim();
                return upLoc === uf || upLoc.startsWith(uf);
            });
            if (!matched) return false;
        }
    }

    const locNormalized = normalizeLocationCode(locText);
    const locParts = parseLocationCode(locText);
    const upLoc = (locText || '').toUpperCase();
    const isOsip = upLoc.includes('OSIP') || upLoc.startsWith('OS') || upLoc.startsWith('A') || upLoc === 'BFOS';

    // 0. Magazyn OSIP widzi WYŁĄCZNIE własne lokalizacje (OS*, OSIP)
    if (currentWarehouseId === 'OSIP') {
        if (!isOsip) return false;
        
        if (currentSubWarehouseId && currentSubWarehouseId !== 'all') {
            if (currentSubWarehouseId === 'OS01') return upLoc.includes('OS01');
            if (currentSubWarehouseId === 'A') return upLoc.startsWith('A');
            return upLoc.includes(currentSubWarehouseId.toUpperCase());
        }
        return true;
    }

    // 1. Jeśli wybrano konkretny regał/podlokalizację lub bufor - to jest priorytet
    if (currentSubWarehouseId && currentSubWarehouseId !== 'all') {
        const subUpper = currentSubWarehouseId.toUpperCase();
        if (subUpper === 'OCZEKUJĄCE' || subUpper === 'OCZEKUJACE') {
            return upLoc.includes('OCZEKUJ');
        }
        if (subUpper === 'BUFORY' || subUpper === 'BUFOR') {
            return upLoc.startsWith('BF') || upLoc.startsWith('MGW') || upLoc.startsWith('MS') || upLoc.startsWith('MP') || upLoc.includes('BUFOR') || upLoc.includes('OCZEKUJ') || !locText || upLoc.trim() === '';
        }
        if (subUpper === 'BFOS') {
            return upLoc.includes('BFOS') || upLoc.includes('BUFOR OSIP') || upLoc.includes('BUFOR CENTR');
        }
        if (subUpper === 'MGW01') {
            return upLoc.includes('MGW01') || upLoc.startsWith('MGW01');
        }
        if (subUpper === 'MGW02') {
            return upLoc.includes('MGW02') || upLoc.startsWith('MGW02');
        }
        if (subUpper === 'MP01') {
            return upLoc.includes('MP01') || upLoc.startsWith('MP01');
        }
        if (subUpper === 'MS01') {
            return upLoc.includes('MS01') || upLoc.startsWith('MS01');
        }
        if (subUpper === 'A' || subUpper === 'A01-A99') {
            return upLoc.startsWith('A');
        }
        if (subUpper === 'OS01' || subUpper === 'OS01-77') {
            return upLoc.includes('OS01') || upLoc.startsWith('OS');
        }
        const selectedRack = normalizeLocationCode(currentSubWarehouseId);
        if (!selectedRack) return true;
        if (locParts) {
            return locParts.rack === selectedRack;
        }
        return locNormalized.includes(selectedRack);
    }

    // 2. Jeśli nie wybrano regału, filtrujemy po magazynie głównym
    if (!currentWarehouseId || currentWarehouseId === 'all') {
        // "Wszystkie Magazyny" must include every location, including OSIP (A*/OS*/BFOS).
        return true;
    }
    
    if (currentWarehouseId === 'MS01') {
        // MS01 to magazyn surowcowy - miejsca podłogowe MS01
        return locText.includes('MS01') || (!['R01','R02','R03','R04','R05','R06','R07','R09'].some(r => (locParts ? locParts.rack === r : locText.includes(r))) && allText.includes('SUROWIEC'));
    }
    
    if (currentWarehouseId === 'MP01') {
        // MP01 to magazyn produkcyjny z regałami R01-R07 i R09 oraz strefą podłogową
        return locText.includes('MP01') || locText.includes('PODŁOGA') || 
               ['R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07', 'R09'].some(r => (locParts ? locParts.rack === r : locText.includes(r)));
    }

    // Inne magazyny (MGW, PSD, MDO, MOP)
    const searchPart = currentWarehouseId.toUpperCase().replace('BF_', '');
    if (locText.includes(searchPart)) return true;

    // Obsługa magazynów rodzajowych dla asortymentów na regałach (np. R09)
    if (currentWarehouseId === 'MOP01' && allText.includes('OPAKOWANIE')) return true;
    if (currentWarehouseId === 'MDO01' && allText.includes('DODATEK')) return true;
    if ((currentWarehouseId === 'MGW01' || currentWarehouseId === 'MGW02') && allText.includes('WYRÓB GOTOWY')) return true;
    if (currentWarehouseId === 'MS01' && allText.includes('SUROWIEC')) return true;
    return false;
}

console.log("[warehouse_v2] Logika filtrowania zainicjowana.");

