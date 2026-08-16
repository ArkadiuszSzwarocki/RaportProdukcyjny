function performSilentRefresh() {
    // Nie odświeżaj, jeśli otwarty jest jakikolwiek modal
    if (document.body.classList.contains('modal-open') ||
        document.querySelector('.modal.show') ||
        document.querySelector('.modal[style*="display: block"]')) {
        return;
    }
    // Nie odświeżaj, jeśli użytkownik wpisuje kod z palca w skaner
    const activeElement = document.activeElement;
    if (activeElement && activeElement.id === 'globalScannerInput' && activeElement.value !== '') {
        return;
    }
    // Ciche odświeżanie przez AJAX
    const url = new URL(window.location.href);
    url.searchParams.set('_t', new Date().getTime()); // Bypassing browser cache
    return fetch(url.toString(), { headers: { 'X-Requested-With': 'XMLHttpRequest' }, cache: 'no-store' })
        .then(res => res.text())
        .then(html => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');

            const newDostawy = doc.getElementById('tab-dostawy');
            const oldDostawy = document.getElementById('tab-dostawy');
            if (newDostawy && oldDostawy && newDostawy.innerHTML !== oldDostawy.innerHTML) {
                oldDostawy.innerHTML = newDostawy.innerHTML;
            }

            const newWg = doc.getElementById('tab-wg');
            const oldWg = document.getElementById('tab-wg');
            if (newWg && oldWg && newWg.innerHTML !== oldWg.innerHTML) {
                oldWg.innerHTML = newWg.innerHTML;
            }

            const newTabs = doc.querySelector('.waiting-tabs');
            const oldTabs = document.querySelector('.waiting-tabs');
            if (newTabs && oldTabs && newTabs.innerHTML !== oldTabs.innerHTML) {
                oldTabs.innerHTML = newTabs.innerHTML;
            }

            const newBadge = doc.querySelector('.nav-pending-badge');
            const oldBadge = document.querySelector('.nav-pending-badge');
            if (newBadge && oldBadge && newBadge.innerHTML !== oldBadge.innerHTML) {
                oldBadge.innerHTML = newBadge.innerHTML;
            } else if (!newBadge && oldBadge) {
                oldBadge.remove();
            }

            const newConfigEl = doc.getElementById('magazyn-config-data');
            if (newConfigEl) {
                try {
                    pendingTransferItems = JSON.parse(newConfigEl.dataset.pendingItems || '[]');
                    window.MAGAZYN_CONFIG.pendingTransferItems = pendingTransferItems;
                } catch (e) {
                    console.error("Failed to parse pendingItems", e);
                }
            }
        })
        .catch(e => console.log('Silent refresh failed', e));
}

