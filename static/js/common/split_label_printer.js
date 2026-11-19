/* Shared direct ZPL label printing helper for pallet split operations. */
(function () {
    'use strict';

    async function printSplitPalletLabel(sscc, linia, options) {
        if (!sscc) return { success: false, message: 'Brak kodu SSCC nowej palety.' };
        const opts = options || {};
        const notify = typeof window.showToast === 'function' ? window.showToast : null;
        try {
            const resp = await fetch('/agro/scanner/print', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sscc: String(sscc).trim(),
                    linia: String(linia || 'AGRO').trim().toUpperCase(),
                    pallet_type: opts.palletType || '',
                    copies: Number(opts.copies || 2)
                })
            });
            const data = await resp.json().catch(() => ({}));
            if (resp.ok && data.success) {
                if (notify) {
                    notify(`🖨️ Wysłano etykietę (${sscc}) na drukarkę ZPL.`, 'success');
                }
                return data;
            }
            const errMsg = data.message || data.error || 'Drukarka ZPL nie odpowiedziała.';
            if (notify) {
                notify(`⚠️ Podział zapisany, ale błąd wydruku ZPL: ${errMsg}`, 'warning');
            }
            return { success: false, message: errMsg };
        } catch (err) {
            if (notify) {
                notify('⚠️ Podział zapisany, ale wystąpił błąd połączenia z drukarką ZPL.', 'warning');
            }
            return { success: false, message: String(err) };
        }
    }

    window.printSplitPalletLabel = printSplitPalletLabel;
})();
