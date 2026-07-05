function hasPendingTransferDraft() {
    const draftKey = "magazyn_dostawy_draft_{{ linia }}_new";
    try {
        const raw = window.localStorage.getItem(draftKey);
        if (!raw) {
            return false;
        }
        const draft = JSON.parse(raw);
        return !!(draft && Array.isArray(draft.items) && draft.items.length > 0);
    } catch (error) {
        return false;
    }
}

const continueBtn = document.getElementById('continue_transfer_btn');
if (continueBtn && hasPendingTransferDraft()) {
    continueBtn.style.display = 'inline-flex';
}

let palletPreviewTimer = null;
let hoverIndicator = null;
let countdownInterval = null;

