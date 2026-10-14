function getPendingTransferDraft() {
    const hall = (new URLSearchParams(window.location.search).get('linia') || 'PSD').toUpperCase();
    const candidates = [];
    for (let index = 0; index < window.localStorage.length; index++) {
        const key = window.localStorage.key(index);
        const match = key && key.match(/^magazyn_dostawy_draft_([^_]+)_(.+)$/);
        if (!match || (match[1] !== hall && !(hall === 'ALL' && ['AGRO', 'PSD'].includes(match[1])))) continue;
        try {
            const draft = JSON.parse(window.localStorage.getItem(key));
            const count = draft && Array.isArray(draft.items) ? draft.items.filter(item => item &&
                !item.accepted && !item.rejected && (item.nr_palety || item.sourcePalletNo || item.productName || parseFloat(item.quantity) > 0)).length : 0;
            if (count) candidates.push({draft, key, count, hall: match[1]});
        } catch (_) { /* Ignore malformed drafts individually. */ }
    }
    candidates.sort((a,b) => String(b.draft.saved_at || '').localeCompare(String(a.draft.saved_at || '')));
    return candidates[0] || null;
}

let draftButtonsRevision = 0;
async function refreshOczekujaceDraftButtons() {
    const revision = ++draftButtonsRevision;
    const info = getPendingTransferDraft();
    const continueBtn = document.getElementById('continue_transfer_btn');
    const continueLabel = document.getElementById('continue_transfer_label');
    const discardBtn = document.getElementById('discard_transfer_draft_btn');
    let count = info ? info.count : 0;
    if (info && info.draft.dostawa_id) {
        try {
            const response = await fetch('/magazyn-dostawy/api/draft/check', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({drafts:[{hall:info.hall, document_id:info.draft.dostawa_id, items:info.draft.items}]})
            });
            const data = await response.json();
            if (response.ok && data.success) count = Number(data.counts[info.hall] || 0);
        } catch (_) { /* Offline: retain the latest local snapshot. */ }
    }
    if (revision !== draftButtonsRevision) return;
    if (continueBtn) {
        continueBtn.style.display = count ? 'inline-flex' : 'none';
        if (count) {
            const target = new URL(continueBtn.href);
            target.searchParams.set('linia',info.hall);
            target.searchParams.set('draft','continue');
            if (info.draft.dostawa_id) target.searchParams.set('id',info.draft.dostawa_id);
            else target.searchParams.delete('id');
            continueBtn.href = target.href;
        }
    }
    if (continueLabel && count) continueLabel.textContent = `Kontynuuj ${info.draft.dostawa_id ? 'otwarte przesunięcie' : 'szkic'} (${count} pal.)`;
    if (discardBtn) discardBtn.style.display = count && !info.draft.dostawa_id ? 'inline-flex' : 'none';
}

async function discardPendingTransferDraftOczekujace() {
    const info = getPendingTransferDraft();
    if (!info || info.draft.dostawa_id) return;
    const confirmed = typeof AppDialog !== 'undefined' ? await AppDialog.confirm('Usunąć wybrany lokalny szkic przesunięcia?') : confirm('Usunąć wybrany lokalny szkic przesunięcia?');
    if (!confirmed) return;
    window.localStorage.removeItem(info.key);
    refreshOczekujaceDraftButtons();
    window.dispatchEvent(new CustomEvent('draftStateChanged', {detail: {hasDraft: Boolean(getPendingTransferDraft())}}));
    if (typeof window.refreshSidebarBadges === 'function') window.refreshSidebarBadges();
}

refreshOczekujaceDraftButtons();
window.addEventListener('storage',refreshOczekujaceDraftButtons);
window.addEventListener('draftStateChanged',refreshOczekujaceDraftButtons);

let palletPreviewTimer = null;
let hoverIndicator = null;
let countdownInterval = null;

