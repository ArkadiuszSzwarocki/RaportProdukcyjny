function showTab(tabId, btn) {
    // Hide all tab content
    document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');

    // Deactivate all tab buttons
    document.querySelectorAll('.waiting-tab').forEach(b => {
        b.classList.remove('active');
    });

    // Show selected tab and activate button
    document.getElementById(tabId).style.display = 'block';
    if (btn) {
        btn.classList.add('active');
    }

    if (tabId === 'tab-wg') {
        const scanInput = document.getElementById('wgScanInput');
        if (scanInput) {
            setTimeout(() => scanInput.focus(), 40);
        }
    }
    if (tabId === 'tab-dostawy') {
        const scanInput = document.getElementById('transferScanPallet');
        if (scanInput) {
            setTimeout(() => scanInput.focus(), 40);
        }
    }
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (!modal || typeof modal.close !== 'function') {
        return;
    }
    modal.close();

    if (id === 'modalWG') {
        const scanInput = document.getElementById('wgScanInput');
        if (scanInput) {
            setTimeout(() => scanInput.focus(), 40);
        }
    }
}

async function cancelTransferOrder(dostawaId, orderRef) {
    const label = orderRef || dostawaId;
    const ok = await AppDialog.confirm(`Czy na pewno anulować całe zlecenie ${label}?`);
    if (!ok) {
        return;
    }

    try {
        const res = await fetch(`/magazyn-dostawy/api/anuluj/${encodeURIComponent(dostawaId)}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await res.json();
        if (!data.success) {
            AppDialog.alert(data.message || 'Nie udało się anulować zlecenia.');
            return;
        }
        location.reload();
    } catch (e) {
        AppDialog.alert('Błąd połączenia z serwerem.');
    }
}

