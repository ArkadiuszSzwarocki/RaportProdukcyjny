function performSilentRefresh() {
    // Nie odświeżaj, jeśli otwarty jest jakikolwiek modal
    if (document.body.classList.contains('modal-open') ||
        document.querySelector('.modal.show') ||
        document.querySelector('.modal[style*="display: block"]') ||
        document.querySelector('dialog[open]')) {
        return;
    }
    // Nie odświeżaj, jeśli użytkownik wpisuje kod ze skanera/ręcznie
    const activeElement = document.activeElement;
    if (activeElement && activeElement.id === 'globalScannerInput' && activeElement.value !== '') {
        return;
    }
    // Nie odświeżaj, jeśli trwa aktywny proces skanowania lokalizacji
    if (typeof activeTransferItem !== 'undefined' && activeTransferItem) {
        return;
    }
    // Nie przerywaj wpisywania w wyszukiwarkę
    const searchInput = document.getElementById('tableSearchInput');
    if (searchInput && searchInput.value.trim() !== '' && document.activeElement === searchInput) {
        return;
    }

    // Ciche pobranie aktualnego stanu przez AJAX
    const url = new URL(window.location.href);
    url.searchParams.set('_t', new Date().getTime()); // Bypassing browser cache
    return fetch(url.toString(), { headers: { 'X-Requested-With': 'XMLHttpRequest' }, cache: 'no-store' })
        .then(res => res.text())
        .then(html => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');

            const newConfigEl = doc.getElementById('magazyn-config-data');
            const oldConfigEl = document.getElementById('magazyn-config-data');
            const newPendingItemsStr = newConfigEl ? (newConfigEl.dataset.pendingItems || '[]') : '[]';
            const oldPendingItemsStr = oldConfigEl ? (oldConfigEl.dataset.pendingItems || '[]') : '[]';

            const newWgTbody = doc.querySelector('#tab-wg tbody');
            const oldWgTbody = document.querySelector('#tab-wg tbody');
            const newWgHtml = newWgTbody ? newWgTbody.innerHTML.trim() : (doc.getElementById('tab-wg')?.innerHTML || '');
            const oldWgHtml = oldWgTbody ? oldWgTbody.innerHTML.trim() : (document.getElementById('tab-wg')?.innerHTML || '');

            // Jeśli dane w bazie nie uległy zmianie, NIC nie ruszaj w DOM
            if (newPendingItemsStr === oldPendingItemsStr && newWgHtml === oldWgHtml) {
                return;
            }

            // Ustalamy, która zakładka jest aktualnie aktywna na ekranie użytkownika
            const tabWg = document.getElementById('tab-wg');
            const isWgActive = tabWg && (tabWg.style.display === 'block' || (!tabWg.style.display.includes('none') && tabWg.offsetParent !== null));
            const activeTabId = isWgActive ? 'tab-wg' : 'tab-dostawy';

            // Cicha podmiana zawartości tabeli Dostawy
            const newDostawy = doc.getElementById('tab-dostawy');
            const oldDostawy = document.getElementById('tab-dostawy');
            if (newDostawy && oldDostawy) {
                oldDostawy.innerHTML = newDostawy.innerHTML;
                oldDostawy.style.display = (activeTabId === 'tab-dostawy') ? 'block' : 'none';
            }

            // Cicha podmiana zawartości tabeli Wyroby Gotowe (WG)
            const newWg = doc.getElementById('tab-wg');
            const oldWg = document.getElementById('tab-wg');
            if (newWg && oldWg) {
                oldWg.innerHTML = newWg.innerHTML;
                oldWg.style.display = (activeTabId === 'tab-wg') ? 'block' : 'none';
            }

            // Aktualizacja samych etykiet z liczbami na przyciskach zakładek (bez ruszania klasy active)
            const newTabBtns = doc.querySelectorAll('.waiting-tab');
            const oldTabBtns = document.querySelectorAll('.waiting-tab');
            if (newTabBtns.length === oldTabBtns.length) {
                newTabBtns.forEach((newBtn, idx) => {
                    const oldBtn = oldTabBtns[idx];
                    oldBtn.textContent = newBtn.textContent;
                });
            }

            // Aktualizacja pozycji menu "Oczekujące Przyjęcia" wraz ze stackiem badge
            const oldPendingLink = Array.from(document.querySelectorAll('.nav-sub-item')).find((el) => {
                const href = el.getAttribute('href') || '';
                return href.includes('/magazyn-dostawy/oczekujace');
            });
            const newPendingLink = Array.from(doc.querySelectorAll('.nav-sub-item')).find((el) => {
                const href = el.getAttribute('href') || '';
                return href.includes('/magazyn-dostawy/oczekujace');
            });
            if (oldPendingLink && newPendingLink) {
                oldPendingLink.innerHTML = newPendingLink.innerHTML;
            }

            // Aktualizacja dataset i listy palet dla skanera w pamięci JS
            if (newConfigEl && oldConfigEl) {
                oldConfigEl.dataset.pendingItems = newPendingItemsStr;
                try {
                    pendingTransferItems = JSON.parse(newPendingItemsStr);
                    if (window.MAGAZYN_CONFIG) {
                        window.MAGAZYN_CONFIG.pendingTransferItems = pendingTransferItems;
                    }
                } catch (e) {
                    console.error("Failed to parse pendingItems", e);
                }
            }

            // Jeśli filtr wyszukiwania był wpisany, aplikujemy go do nowo wstawionych wierszy
            if (typeof filterTableRows === 'function') {
                filterTableRows();
            }
        })
        .catch(e => console.log('Silent refresh error', e));
}
