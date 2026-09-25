function openPalletHistoryModal() {
    const modal = document.getElementById('palletFullHistoryModal');
    if (modal) modal.style.display = 'flex';
}

function closePalletHistoryModal() {
    const modal = document.getElementById('palletFullHistoryModal');
    if (modal) modal.style.display = 'none';
}

function historyElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
}

function historySetText(id, value, fallback = '—') {
    const element = document.getElementById(id);
    if (element) element.textContent = value === undefined || value === null || value === '' ? fallback : String(value);
}

function historyNormalizeLocation(value) {
    const raw = String(value || '').trim();
    if (!raw || raw === '-' || raw.toLowerCase() === 'none' || raw.toLowerCase() === 'null') return '';
    const normalized = raw.toUpperCase();
    if (normalized === 'OCZEKUJACE') return 'OCZEKUJĄCE';
    if (normalized === 'W_TRANZYCIE_OSIP') return 'TRANZYT OSIP';
    if (normalized === 'STREFA_PRZYJEC_01') return 'STREFA PRZYJĘĆ';
    return raw;
}

function historyDateParts(value) {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
    if (!match) return { dayKey: 'unknown', dayLabel: 'Bez daty', time: '—' };
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return {
        dayKey: `${match[1]}-${match[2]}-${match[3]}`,
        dayLabel: date.toLocaleDateString('pl-PL', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }),
        time: match[4] ? `${match[4]}:${match[5]}` : '—'
    };
}

function historyEventPresentation(rawType) {
    const type = String(rawType || '').toUpperCase();
    if (type.includes('ODRZU')) return { label: 'Odrzucono', icon: 'cancel', color: '#dc2626', soft: '#fef2f2', description: 'Paleta lub operacja została odrzucona.' };
    if (type.includes('PODZIAL_ODJECIE')) return { label: 'Odcięcie z palety', icon: 'call_split', color: '#ea580c', soft: '#fff7ed', description: 'Zmniejszono ilość na palecie źródłowej.' };
    if (type.includes('PODZIAL') || type.includes('UTWORZENIE_Z_PODZIALU')) return { label: 'Podział palety', icon: 'call_split', color: '#9333ea', soft: '#faf5ff', description: 'Utworzono osobną paletę z części materiału.' };
    if (type.includes('ZLECENIE') || type.includes('PUTAWAY')) return { label: 'Zlecono przesunięcie', icon: 'assignment', color: '#475569', soft: '#f1f5f9', description: 'Utworzono zlecenie zmiany lokalizacji.' };
    if (type.includes('INWENT') || type.includes('KOREKT')) return { label: 'Korekta stanu', icon: 'fact_check', color: '#d97706', soft: '#fffbeb', description: 'Stan palety został zweryfikowany lub skorygowany.' };
    if (type.includes('DOSTAWA')) return { label: 'Dostawa', icon: 'local_shipping', color: '#0284c7', soft: '#f0f9ff', description: 'Paleta została zarejestrowana w dostawie.' };
    if (type.includes('PRZYJ') || type.includes('POTWIERDZ') || type === 'PW' || type === 'PZ') return { label: 'Przyjęcie', icon: 'move_to_inbox', color: '#16a34a', soft: '#f0fdf4', description: 'Paleta została przyjęta do wskazanej lokalizacji.' };
    if (type.includes('WYDA') || type.includes('PRODUKC') || type.includes('ZUZYCIE') || type.includes('POBRANIE')) return { label: 'Wydanie na produkcję', icon: 'outbox', color: '#4f46e5', soft: '#eef2ff', description: 'Materiał został przekazany do produkcji.' };
    if (type.includes('PRZESUN') || type.includes('TRANSFER') || type.includes('RELOKAC') || type.includes('RUCH') || type === 'MM') return { label: 'Przesunięcie', icon: 'sync_alt', color: '#7c3aed', soft: '#f5f3ff', description: 'Zmieniono lokalizację palety.' };
    if (type.includes('UTWORZ') || type.includes('NADANIE') || type.includes('SSCC')) return { label: 'Utworzenie palety', icon: 'add_box', color: '#ca8a04', soft: '#fefce8', description: 'Paleta została utworzona i otrzymała identyfikator.' };
    if (type.includes('USUN') || type.includes('ARCHIW')) return { label: 'Archiwizacja', icon: 'archive', color: '#64748b', soft: '#f8fafc', description: 'Paleta została wycofana z aktywnego magazynu.' };
    return { label: 'Zdarzenie magazynowe', icon: 'inventory_2', color: '#6366f1', soft: '#eef2ff', description: 'Zarejestrowano zmianę dotyczącą palety.' };
}

function historyRoute(event) {
    let source = historyNormalizeLocation(event.lokalizacja_zrodlowa);
    let destination = historyNormalizeLocation(event.lokalizacja_docelowa);
    const route = String(event.stacja_trasa || '');
    if ((!source || !destination) && /->|→/.test(route)) {
        const parts = route.split(/->|→/).map(historyNormalizeLocation);
        source = source || parts[0] || '';
        destination = destination || parts[1] || '';
    } else if (!source && !destination) {
        destination = historyNormalizeLocation(route);
    }
    return { source, destination };
}

function historyAppendTechnicalRow(container, label, value) {
    if (value === undefined || value === null || value === '') return;
    const row = historyElement('div');
    const labelElement = historyElement('strong', '', `${label}: `);
    row.append(labelElement, document.createTextNode(String(value)));
    container.appendChild(row);
}

function historyBuildEvent(event) {
    const presentation = historyEventPresentation(event.typ_ruchu);
    const date = historyDateParts(event.autor_data);
    const wrapper = historyElement('article', 'pallet-history-event');
    wrapper.style.setProperty('--event-color', presentation.color);
    wrapper.style.setProperty('--event-soft', presentation.soft);

    wrapper.appendChild(historyElement('time', 'pallet-history-time', date.time));
    const rail = historyElement('div', 'pallet-history-rail');
    rail.appendChild(historyElement('span', 'pallet-history-dot'));
    wrapper.appendChild(rail);

    const card = historyElement('div', 'pallet-history-card');
    const head = historyElement('div', 'pallet-history-card-head');
    const title = historyElement('div', 'pallet-history-event-title');
    const iconBox = historyElement('span', 'pallet-history-event-icon');
    iconBox.appendChild(historyElement('span', 'material-icons', presentation.icon));
    title.append(iconBox, historyElement('span', '', presentation.label));
    head.append(title, historyElement('span', 'pallet-history-user', event.autor_login || 'System'));
    card.appendChild(head);

    const route = historyRoute(event);
    if (route.source || route.destination) {
        const routeElement = historyElement('div', 'pallet-history-route');
        if (route.source && route.destination && route.source !== route.destination) {
            routeElement.append(
                historyElement('span', 'pallet-history-location', route.source),
                historyElement('span', 'material-icons', 'arrow_forward'),
                historyElement('span', 'pallet-history-location', route.destination)
            );
        } else {
            routeElement.append(
                historyElement('span', 'material-icons', 'place'),
                historyElement('span', 'pallet-history-location', route.destination || route.source)
            );
        }
        card.appendChild(routeElement);
    }

    card.appendChild(historyElement('p', 'pallet-history-description', presentation.description));

    let hasQuantity = event.quantity_before !== null && event.quantity_before !== undefined && event.quantity_before !== ''
        && event.quantity_after !== null && event.quantity_after !== undefined && event.quantity_after !== '';
    let before = Number(event.quantity_before);
    let after = Number(event.quantity_after);
    let estimated = Boolean(event.quantity_is_estimated);
    const currentAmount = Number(currentPallet.amount);
    if (!hasQuantity && Number.isFinite(currentAmount)) {
        before = currentAmount;
        after = currentAmount;
        hasQuantity = true;
        estimated = true;
    }
    if (hasQuantity && Number.isFinite(before) && Number.isFinite(after)) {
        const unit = currentPallet.unit || 'kg';
        const delta = after - before;
        let quantityText;
        if (delta === 0) {
            quantityText = `Stan po zdarzeniu: ${estimated ? 'około ' : ''}${after.toLocaleString('pl-PL')} ${unit}`;
        } else {
            const deltaText = `${delta > 0 ? '+' : ''}${delta.toLocaleString('pl-PL')} ${unit}`;
            quantityText = `Ilość: ${estimated ? 'około ' : ''}${before.toLocaleString('pl-PL')} → ${after.toLocaleString('pl-PL')} ${unit} (${deltaText})`;
        }
        const quantityElement = historyElement('div', 'pallet-history-quantity', quantityText);
        if (estimated) quantityElement.title = 'Wartość odtworzona na podstawie aktualnego stanu i kolejności zdarzeń.';
        card.appendChild(quantityElement);
    }

    const details = historyElement('details', 'pallet-history-details');
    details.appendChild(historyElement('summary', '', 'Pokaż szczegóły techniczne'));
    const technical = historyElement('div', 'pallet-history-technical');
    historyAppendTechnicalRow(technical, 'Komentarz', event.komentarz);
    historyAppendTechnicalRow(technical, 'Typ źródłowy', event.typ_ruchu);
    historyAppendTechnicalRow(technical, 'Pełna data', event.autor_data);
    historyAppendTechnicalRow(technical, 'ID operacji', event.operation_id);
    historyAppendTechnicalRow(technical, 'ID zdarzenia', event.event_id);
    details.appendChild(technical);
    card.appendChild(details);

    wrapper.appendChild(card);
    return { element: wrapper, date };
}

function historyShowError(message) {
    const empty = document.getElementById('palletHistoryEmpty');
    if (!empty) return;
    empty.replaceChildren();
    const icon = historyElement('span', 'material-icons', 'error');
    icon.style.color = '#dc2626';
    empty.append(icon, historyElement('strong', '', 'Błąd ładowania historii'), historyElement('span', '', message));
    empty.style.display = 'flex';
}

function fetchHistory() {
    if (!currentPallet || (!currentPallet.id && !currentPallet.displayId)) return;
    openPalletHistoryModal();

    historySetText('palletHistoryModalSubtitle', `${currentPallet.displayId || ('#' + currentPallet.id)} • ${currentPallet.productName || 'Nieznany produkt'}`);
    historySetText('palletHistoryCurrentLocation', historyNormalizeLocation(currentPallet.location));
    historySetText('palletHistoryCurrentAmount', `${currentPallet.amount || 0} ${currentPallet.unit || 'kg'}`);
    historySetText('palletHistoryEventCount', '…');

    const loading = document.getElementById('palletHistoryLoading');
    const empty = document.getElementById('palletHistoryEmpty');
    const timeline = document.getElementById('palletHistoryTimeline');
    if (loading) loading.style.display = 'flex';
    if (empty) empty.style.display = 'none';
    if (timeline) {
        timeline.style.display = 'none';
        timeline.replaceChildren();
    }

    const queryParams = new URLSearchParams({
        id: currentPallet.id || '',
        sscc: currentPallet.displayId || '',
        type: currentPallet.type || '',
        linia: currentPallet.linia || 'PSD'
    });

    fetch(`/warehouse-v2/api/pallet/history?${queryParams.toString()}`)
        .then(response => {
            if (!response.ok) throw new Error(`Serwer zwrócił błąd ${response.status}`);
            return response.json();
        })
        .then(data => {
            if (loading) loading.style.display = 'none';
            const events = data.success && Array.isArray(data.history) ? data.history : [];
            historySetText('palletHistoryEventCount', events.length);
            if (!events.length) {
                if (empty) empty.style.display = 'flex';
                return;
            }

            let currentDay = null;
            events.forEach(event => {
                const built = historyBuildEvent(event);
                if (built.date.dayKey !== currentDay) {
                    currentDay = built.date.dayKey;
                    timeline.appendChild(historyElement('div', 'pallet-history-day', built.date.dayLabel));
                }
                timeline.appendChild(built.element);
            });
            timeline.style.display = 'block';
        })
        .catch(error => {
            if (loading) loading.style.display = 'none';
            historySetText('palletHistoryEventCount', '—');
            historyShowError(error && error.message ? error.message : 'Nie udało się połączyć z serwerem.');
        });
}
