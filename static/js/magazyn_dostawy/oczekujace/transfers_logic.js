function getPendingTransferDraft() {
    try {
        const params = new URLSearchParams(window.location.search || '');
        const linia = (params.get('linia') || 'PSD').toUpperCase();
        const primaryKey = `magazyn_dostawy_draft_${linia}_new`;
        const raw = window.localStorage.getItem(primaryKey);
        if (raw) {
            const draft = JSON.parse(raw);
            if (draft && Array.isArray(draft.items) && draft.items.length > 0) {
                const hasData = draft.items.some(i => (i && (i.nr_palety || i.sourcePalletNo || i.productName || parseFloat(i.quantity) > 0)));
                if (hasData) return draft;
            }
        }
        // Fallback: check any matching draft in localStorage
        for (let i = 0; i < window.localStorage.length; i++) {
            const k = window.localStorage.key(i);
            if (k && k.startsWith('magazyn_dostawy_draft_') && k.endsWith('_new')) {
                const d = JSON.parse(window.localStorage.getItem(k));
                if (d && Array.isArray(d.items) && d.items.length > 0) {
                    const hasData = d.items.some(i => (i && (i.nr_palety || i.sourcePalletNo || i.productName || parseFloat(i.quantity) > 0)));
                    if (hasData) return d;
                }
            }
        }
    } catch (error) {
        return null;
    }
    return null;
}

const pendingDraftOczekujace = getPendingTransferDraft();
const continueBtn = document.getElementById('continue_transfer_btn');
const continueLabel = document.getElementById('continue_transfer_label');
if (continueBtn && pendingDraftOczekujace) {
    continueBtn.style.display = 'inline-flex';
    const validCount = (pendingDraftOczekujace.items || []).filter(i => (i && (i.nr_palety || i.sourcePalletNo || i.productName || parseFloat(i.quantity) > 0))).length;
    if (continueLabel && validCount > 0) {
        continueLabel.textContent = `Kontynuuj wpis (${validCount} pal.)`;
    }
}

let palletPreviewTimer = null;
let hoverIndicator = null;
let countdownInterval = null;

