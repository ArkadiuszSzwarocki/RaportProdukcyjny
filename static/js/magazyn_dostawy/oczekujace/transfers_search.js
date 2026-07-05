function findTransferByScannedCode(rawCode) {
    const code = normalizeScanCode(rawCode);
    if (!code) return { status: 'empty' };
    if (!Array.isArray(pendingTransferItems) || pendingTransferItems.length === 0) {
        return { status: 'none' };
    }
    const matches = pendingTransferItems.filter(item => {
        const nr = normalizeScanCode(item.nr_palety);
        if (!nr) return false;
        return nr === code || code.includes(nr) || nr.includes(code);
    });
    if (matches.length === 1) return { status: 'single', item: matches[0] };
    if (matches.length > 1) return { status: 'many' };
    return { status: 'none' };
}

function findWGByScannedCode(rawCode) {
    const code = normalizeScanCode(rawCode);
    if (!code) return { status: 'empty' };

    const buttons = Array.from(document.querySelectorAll('button[data-wg-id][data-wg-nr]'));
    if (!buttons.length) return { status: 'none' };

    const rows = buttons.map(btn => ({
        id: String(btn.dataset.wgId || '').trim(),
        nr: normalizeScanCode(btn.dataset.wgNr),
        waga: btn.dataset.wgWaga,
    }));

    const directMatch = rows.find(item => item.nr === code || item.id === code);
    if (directMatch) return { status: 'single', item: directMatch };

    const containsMatch = rows.filter(item => item.nr && (code.includes(item.nr) || item.nr.includes(code)));
    if (containsMatch.length === 1) return { status: 'single', item: containsMatch[0] };
    if (containsMatch.length > 1) return { status: 'many' };

    return { status: 'none' };
}

