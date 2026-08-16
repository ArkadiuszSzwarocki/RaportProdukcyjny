    window.openQrScanner = function(targetFieldId) {
        _qrTargetFieldId = targetFieldId;
        const inp = document.getElementById('qrScanInput');
        inp.value = '';
        document.getElementById('qrConfirmBtn').disabled = true;
        openModal('modalQr');
        setTimeout(() => inp.focus(), 80);
    };

    window.closeQrScanner = function() { closeModal('modalQr'); };

    document.addEventListener('DOMContentLoaded', function() {
        const inp = document.getElementById('qrScanInput');
        if (inp) {
            inp.addEventListener('input', () => {
                const val = inp.value.trim().toUpperCase();
                inp.value = val;
                document.getElementById('qrConfirmBtn').disabled = val.length === 0;
            });
            inp.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const val = inp.value.trim().toUpperCase();
                    if (val) applyQrResult(val);
                }
            });
        }

        openInventoryEntryFromUrl();
    });

    function openInventoryEntryFromUrl() {
        try {
            const params = new URLSearchParams(window.location.search || '');
            const mode = String(params.get('inventory') || '').toLowerCase().trim();
            if (!mode) return;

            if (mode === 'production' || mode === 'prod') {
                if (typeof window.openBulkInventoryModal === 'function') {
                    window.openBulkInventoryModal();
                }
            } else if (mode === 'standard' || mode === 'regular') {
                if (typeof window.openStandardInventoryModal === 'function') {
                    window.openStandardInventoryModal();
                }
            }

            params.delete('inventory');
            const nextQuery = params.toString();
            const nextUrl = window.location.pathname + (nextQuery ? ('?' + nextQuery) : '') + (window.location.hash || '');
            if (window.history && typeof window.history.replaceState === 'function') {
                window.history.replaceState({}, document.title, nextUrl);
            }
        } catch (e) {
            console.warn('Unable to auto-open inventory view from URL', e);
        }
    }

    function applyQrResult(val) {
        closeQrScanner();
        if (!_qrTargetFieldId || !val) return;
        if (_qrTargetFieldId === 'usage_location_scan') {
            const sel = document.getElementById('usage_surowiec_id');
            let matched = false;
            for (let i = 0; i < sel.options.length; i++) {
                if (sel.options[i].textContent.toUpperCase().indexOf(val) !== -1) {
                    sel.selectedIndex = i;
                    matched = true;
                    break;
                }
            }
            if (!matched) showAlert('Nie znaleziono palety dla lokalizacji: ' + val);
        } else {
            const el = document.getElementById(_qrTargetFieldId);
            if (el) { el.value = val; el.dispatchEvent(new Event('input')); }
        }
    }

    window.confirmQrManual = function() {
        const val = document.getElementById('qrScanInput').value.trim().toUpperCase();
        if (val) applyQrResult(val);
    };

    // RETURN & ISSUE
