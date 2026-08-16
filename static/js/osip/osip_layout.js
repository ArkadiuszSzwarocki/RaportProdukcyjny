/**
 * Wizualizacja i obsługa siatki 77 alejek (OS01-OS77) hali OSIP.
 */

window.renderOsipLayout = async function() {
    const gridContainer = document.getElementById('osip-aisles-grid');
    const badgeEl = document.getElementById('layout-occupancy-badge');
    if (!gridContainer) return;

    try {
        gridContainer.innerHTML = `<div class="text-center py-4 text-muted w-100"><i class="fas fa-spinner fa-spin mr-2"></i>Generowanie planu hali OSIP...</div>`;
        const res = await fetch('/osip/api/layout');
        const json = await res.json();

        if (!json.success) return;
        const layoutData = json.data;

        if (badgeEl) {
            badgeEl.textContent = `Zajętych alejek: ${layoutData.total_occupancy} pozycji w hali`;
        }

        const html = layoutData.aisles.map(aisle => {
            const spotsCount = aisle.count;
            const itemsHtml = aisle.items.map(item => {
                const isRaw = item.item_type === 'raw';
                const cls = isRaw ? 'spot-box occupied-raw' : 'spot-box occupied-fg';
                return `
                    <div class="${cls}" title="${item.nazwa} (${item.nr_palety || item.id})">
                        <div class="font-weight-bold text-truncate">${item.nazwa}</div>
                        <div class="d-flex justify-content-between">
                            <span class="small font-weight-bold">${item.nr_palety || item.id}</span>
                            <span class="small opacity-75">${parseFloat(item.ilosc_kg || 0).toFixed(0)}kg</span>
                        </div>
                    </div>
                `;
            }).join('');

            return `
                <div class="aisle-card">
                    <div class="aisle-header text-primary">
                        <span><i class="fas fa-layer-group mr-1"></i>${aisle.id}</span>
                        <span class="badge badge-light border">${spotsCount} poz.</span>
                    </div>
                    <div class="aisle-spots">
                        ${itemsHtml || '<div class="text-muted small py-2 text-center col-span-4" style="grid-column: span 4;">Wolna aleja</div>'}
                    </div>
                </div>
            `;
        }).join('');

        gridContainer.innerHTML = html;
    } catch (e) {
        console.error('Błąd renderowania planu hali OSIP:', e);
        gridContainer.innerHTML = `<div class="alert alert-danger">Wystąpił błąd podczas pobierania układu alejek.</div>`;
    }
};
