/**
 * Logika widoku tabeli surowców i wyrobów gotowych w Magazynie OSIP.
 */

document.addEventListener('DOMContentLoaded', () => {
    const rawBtn = document.getElementById('tab-raw-btn');
    const fgBtn = document.getElementById('tab-fg-btn');
    const searchInput = document.getElementById('osip-search-input');
    const viewListBtn = document.getElementById('view-list-btn');
    const viewLayoutBtn = document.getElementById('view-layout-btn');
    const listContainer = document.getElementById('osip-list-container');
    const layoutContainer = document.getElementById('osip-layout-container');
    const tbody = document.getElementById('osip-inventory-tbody');
    const rawCountEl = document.getElementById('raw-count');
    const fgCountEl = document.getElementById('fg-count');

    let currentItemType = 'raw';
    let inventoryData = { raw_materials: [], finished_goods: [] };

    async function checkInboundTransfers() {
        try {
            const res = await fetch('/osip/api/transfers');
            const json = await res.json();
            if (json.success && json.transfers) {
                const inTransit = json.transfers.filter(t => t.status === 'IN_TRANSIT' && t.destination_warehouse === 'OSIP');
                const planned = json.transfers.filter(t => t.status === 'PLANNED' && t.destination_warehouse === 'OSIP');
                const alertEl = document.getElementById('inbound-trucks-alert');
                const subEl = document.getElementById('inbound-trucks-sub');
                if (alertEl) {
                    if (inTransit.length > 0) {
                        alertEl.style.display = 'flex';
                        if (subEl) subEl.textContent = `W drodze na OSIP znajduje się ${inTransit.length} zlecenie(ń) transportowych (Ciężarówka 🚛 [O]). Kliknij przycisk obok, aby odebrać palety!`;
                    } else if (planned.length > 0) {
                        alertEl.style.display = 'flex';
                        if (subEl) subEl.textContent = `Zaplanowano ${planned.length} zlecenie(ń) z Centrali na OSIP. Oczekuje na wydanie/załadunek w Centrali.`;
                    } else {
                        alertEl.style.display = 'none';
                    }
                }
            }
        } catch (e) {
            console.warn('Inbound transfers check error:', e);
        }
    }

    async function loadInventory() {
        try {
            const searchTerm = searchInput ? searchInput.value : '';
            const res = await fetch(`/osip/api/inventory?search=${encodeURIComponent(searchTerm)}`);
            const json = await res.json();
            if (json.success) {
                inventoryData = json.data;
                if (rawCountEl) rawCountEl.textContent = inventoryData.total_raw || 0;
                if (fgCountEl) fgCountEl.textContent = inventoryData.total_fg || 0;
                renderTable();
            }
            checkInboundTransfers();
        } catch (e) {
            console.error('Błąd ładowania danych magazynu OSIP:', e);
        }
    }

    function renderTable() {
        if (!tbody) return;
        const items = currentItemType === 'raw' ? inventoryData.raw_materials : inventoryData.finished_goods;

        if (items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-4 text-muted">
                        <i class="fas fa-box-open mr-2"></i>Brak pozycji w magazynie OSIP dla wybranej kategorii.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = items.map(item => {
            const locBadge = item.lokalizacja ? `<span class="badge badge-primary font-weight-bold p-1">${item.lokalizacja}</span>` : '<span class="badge badge-secondary">OSIP</span>';
            const weight = item.ilosc_kg ? `${parseFloat(item.ilosc_kg).toFixed(2)} kg` : '-';
            const expiry = item.data_przydatnosci || '-';
            const batch = item.nr_partii || '-';
            const palletId = item.nr_palety || `#${item.id}`;

            return `
                <tr>
                    <td>${locBadge}</td>
                    <td class="font-weight-bold text-dark">${palletId}</td>
                    <td>${item.nazwa || 'Bez nazwy'}</td>
                    <td class="font-weight-bold text-success">${weight}</td>
                    <td>${expiry}</td>
                    <td>${batch}</td>
                </tr>
            `;
        }).join('');
    }

    if (rawBtn) {
        rawBtn.addEventListener('click', () => {
            currentItemType = 'raw';
            rawBtn.classList.add('active');
            fgBtn.classList.remove('active');
            renderTable();
        });
    }

    if (fgBtn) {
        fgBtn.addEventListener('click', () => {
            currentItemType = 'fg';
            fgBtn.classList.add('active');
            rawBtn.classList.remove('active');
            renderTable();
        });
    }

    if (searchInput) {
        let timer;
        searchInput.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(loadInventory, 300);
        });
    }

    if (viewListBtn && viewLayoutBtn) {
        viewListBtn.addEventListener('click', () => {
            viewListBtn.classList.add('active');
            viewLayoutBtn.classList.remove('active');
            listContainer.classList.remove('d-none');
            layoutContainer.classList.add('d-none');
        });

        viewLayoutBtn.addEventListener('click', () => {
            viewLayoutBtn.classList.add('active');
            viewListBtn.classList.remove('active');
            layoutContainer.classList.remove('d-none');
            listContainer.classList.add('d-none');
            if (window.renderOsipLayout) window.renderOsipLayout();
        });
    }

    loadInventory();
});
