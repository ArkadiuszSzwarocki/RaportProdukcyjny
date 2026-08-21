// ---- PRODUCTION CONSUMPTION (Zużycie w produkcji do 0 kg) ----

let currentLoadedPallet = null;

document.addEventListener('DOMContentLoaded', function() {
    const inputEl = document.getElementById('consumptionScanInput');
    const clearBtn = document.getElementById('clearScanBtn');

    if (inputEl) {
        inputEl.focus();
        inputEl.addEventListener('input', function() {
            if (clearBtn) {
                clearBtn.style.display = this.value.length > 0 ? 'block' : 'none';
            }
        });

        // Obsługa skanerów sprzętowych (wysyłających Enter)
        inputEl.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleConsumptionLookup();
            }
        });
    }
});

function clearConsumptionInput() {
    const inputEl = document.getElementById('consumptionScanInput');
    const clearBtn = document.getElementById('clearScanBtn');
    if (inputEl) {
        inputEl.value = '';
        inputEl.focus();
    }
    if (clearBtn) clearBtn.style.display = 'none';
    const statusMsg = document.getElementById('scanStatusMsg');
    if (statusMsg) {
        statusMsg.innerText = 'Gotowy do skanowania czytnikiem ręcznym Zebra lub wpisania ręcznego.';
        statusMsg.style.color = '#64748b';
    }
}

async function handleConsumptionLookup(e) {
    if (e && e.preventDefault) e.preventDefault();

    const inputEl = document.getElementById('consumptionScanInput');
    const statusMsg = document.getElementById('scanStatusMsg');
    const confirmCard = document.getElementById('consumptionConfirmCard');

    if (!inputEl) return;
    const code = (inputEl.value || '').trim();

    if (!code) {
        if (typeof showToast === 'function') {
            showToast('warning', 'Wpisz lub zeskanuj kod palety');
        } else {
            alert('Wpisz lub zeskanuj kod palety');
        }
        inputEl.focus();
        return;
    }

    if (statusMsg) {
        statusMsg.innerText = `🔍 Szukanie palety: "${code}"...`;
        statusMsg.style.color = '#2563eb';
    }

    try {
        const resp = await fetch('/warehouse-v2/api/zuzycie/lookup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code })
        });

        const data = await resp.json();

        if (!data.success || !data.pallet) {
            currentLoadedPallet = null;
            if (confirmCard) confirmCard.style.display = 'none';
            if (statusMsg) {
                statusMsg.innerText = `❌ ${data.message || 'Nie znaleziono palety.'}`;
                statusMsg.style.color = '#dc2626';
            }
            if (typeof showToast === 'function') {
                showToast('error', data.message || 'Nie znaleziono palety');
            }
            inputEl.select();
            return;
        }

        // Paleta znaleziona - wypełnij kartę potwierdzenia
        currentLoadedPallet = data.pallet;
        populateConfirmCard(data.pallet);

        if (statusMsg) {
            statusMsg.innerText = `✅ Znaleziono: ${data.pallet.productName} (${data.pallet.displayId})`;
            statusMsg.style.color = '#16a34a';
        }

        if (confirmCard) {
            confirmCard.style.display = 'block';
            confirmCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        // Fokus na przycisku potwierdzenia
        setTimeout(() => {
            const btn = document.getElementById('btnExecuteConsumption');
            if (btn) btn.focus();
        }, 100);

    } catch (err) {
        console.error('Błąd lookup:', err);
        if (statusMsg) {
            statusMsg.innerText = '❌ Błąd połączenia z serwerem.';
            statusMsg.style.color = '#dc2626';
        }
    }
}

function populateConfirmCard(p) {
    document.getElementById('confirmPalletName').innerText = p.productName || 'Brak nazwy';
    document.getElementById('confirmPalletSSCC').innerText = p.displayId || p.nr_palety || '-';
    document.getElementById('confirmPalletAmount').innerText = `${parseFloat(p.amount || 0).toFixed(1)} ${p.unit || 'kg'}`;
    document.getElementById('confirmPalletBatch').innerText = p.batch || '-';
    document.getElementById('confirmPalletLocation').innerText = `${p.location || '-'} (${p.linia || 'PSD'})`;

    const badge = document.getElementById('confirmPalletTypeBadge');
    if (badge) {
        badge.innerText = `${p.type} • ${p.linia || 'PSD'}`;
        if (p.type === 'Surowiec') {
            badge.style.background = '#0284c7';
        } else if (p.type === 'Opakowanie') {
            badge.style.background = '#d97706';
        } else if (p.type === 'Dodatek') {
            badge.style.background = '#7c3aed';
        } else {
            badge.style.background = '#16a34a';
        }
    }
}

function cancelConsumptionConfirm() {
    currentLoadedPallet = null;
    const confirmCard = document.getElementById('consumptionConfirmCard');
    if (confirmCard) confirmCard.style.display = 'none';
    clearConsumptionInput();
}

async function executeConsumption() {
    if (!currentLoadedPallet) {
        alert('Brak wybranej palety do zużycia.');
        return;
    }

    const btn = document.getElementById('btnExecuteConsumption');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="material-icons" style="animation: spin 1s linear infinite;">refresh</span> TRWA ZUŻYWANIE...';
    }

    try {
        const resp = await fetch('/warehouse-v2/api/zuzycie/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pallet_id: currentLoadedPallet.id,
                pallet_type: currentLoadedPallet.type,
                linia: currentLoadedPallet.linia || 'PSD'
            })
        });

        const data = await resp.json();

        if (!data.success) {
            alert(`Błąd: ${data.message}`);
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<span class="material-icons">done_all</span> ZUŻYJ I ZARCHIWIZUJ PALETĘ';
            }
            return;
        }

        // Sukces!
        if (typeof showToast === 'function') {
            showToast('success', data.message);
        }

        // Dodaj pozycję do tabeli na żywo
        if (data.archived) {
            prependHistoryRow(data.archived);
        }

        // Schowaj kartę i wyczyść skaner
        cancelConsumptionConfirm();

        // Odtwórz dźwięk sukcesu jeśli dostępny
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
            osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.1); // A5
            gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.3);
        } catch (e) {}

    } catch (err) {
        console.error('Błąd zapisu zużycia:', err);
        alert('Błąd połączenia z serwerem podczas zapisywania zużycia.');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span class="material-icons">done_all</span> ZUŻYJ I ZARCHIWIZUJ PALETĘ';
        }
    }
}

function prependHistoryRow(row) {
    const tbody = document.getElementById('consumptionHistoryBody');
    const emptyRow = document.getElementById('emptyHistoryRow');
    if (emptyRow) emptyRow.remove();

    if (!tbody) return;

    const tr = document.createElement('tr');
    tr.style.animation = 'fadeInScale 0.3s ease-out';
    tr.innerHTML = `
        <td style="padding: 10px 14px; font-family: monospace; font-weight: 700; color: #0284c7;">${row.time || '-'}</td>
        <td style="padding: 10px 14px; font-family: monospace; font-weight: 800;">${row.nr_palety || '-'}</td>
        <td style="padding: 10px 14px;"><span class="badge" style="background:#e2e8f0; color:#334155; font-size:11px; padding:3px 8px; border-radius:6px;">${row.typ_palety || '-'}</span></td>
        <td style="padding: 10px 14px; font-weight: 700; color: #0f172a;">${row.nazwa || '-'}</td>
        <td style="padding: 10px 14px; font-size: 12px; color: #475569;">${row.nr_partii || '-'}</td>
        <td style="padding: 10px 14px; text-align: right; font-weight: 800; color: #dc2626;">${parseFloat(row.waga_ostatnia || 0).toFixed(1)} kg</td>
        <td style="padding: 10px 14px; text-align: center; font-weight: 700; font-size: 12px;">${row.lokalizacja_ostatnia || '-'}</td>
        <td style="padding: 10px 14px; font-size: 12px; color: #64748b;">${row.user_login || '-'}</td>
    `;

    tbody.insertBefore(tr, tbody.firstChild);

    // Zaktualizuj licznik pozycji
    const countBadge = document.getElementById('historyCountBadge');
    if (countBadge) {
        const total = tbody.querySelectorAll('tr:not(#emptyHistoryRow)').length;
        countBadge.innerText = `Pozycji: ${total}`;
    }
}

async function refreshConsumptionHistory() {
    try {
        const resp = await fetch('/warehouse-v2/api/zuzycie/history');
        const data = await resp.json();
        if (data.success && data.history) {
            const tbody = document.getElementById('consumptionHistoryBody');
            if (!tbody) return;

            if (data.history.length === 0) {
                tbody.innerHTML = `
                    <tr id="emptyHistoryRow">
                        <td colspan="8" style="text-align: center; padding: 30px; color: #94a3b8;">
                            <span class="material-icons" style="font-size: 36px; color: #cbd5e1; display: block; margin-bottom: 6px;">inbox</span>
                            <strong>Brak zarejestrowanych zużyć dzisiejszego dnia</strong>
                            <div style="font-size: 12px; margin-top: 2px;">Zeskanuj etykietę powyżej, aby dodać pierwsze zużycie.</div>
                        </td>
                    </tr>
                `;
            } else {
                tbody.innerHTML = '';
                data.history.forEach(row => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="padding: 10px 14px; font-family: monospace; font-weight: 700; color: #0284c7;">${row.time || '-'}</td>
                        <td style="padding: 10px 14px; font-family: monospace; font-weight: 800;">${row.nr_palety || '-'}</td>
                        <td style="padding: 10px 14px;"><span class="badge" style="background:#e2e8f0; color:#334155; font-size:11px; padding:3px 8px; border-radius:6px;">${row.typ_palety || '-'}</span></td>
                        <td style="padding: 10px 14px; font-weight: 700; color: #0f172a;">${row.nazwa || '-'}</td>
                        <td style="padding: 10px 14px; font-size: 12px; color: #475569;">${row.nr_partii || '-'}</td>
                        <td style="padding: 10px 14px; text-align: right; font-weight: 800; color: #dc2626;">${parseFloat(row.waga_ostatnia || 0).toFixed(1)} kg</td>
                        <td style="padding: 10px 14px; text-align: center; font-weight: 700; font-size: 12px;">${row.lokalizacja_ostatnia || '-'}</td>
                        <td style="padding: 10px 14px; font-size: 12px; color: #64748b;">${row.user_login || '-'}</td>
                    `;
                    tbody.appendChild(tr);
                });
            }

            const countBadge = document.getElementById('historyCountBadge');
            if (countBadge) {
                countBadge.innerText = `Pozycji: ${data.history.length}`;
            }
        }
    } catch (e) {
        console.error('Błąd odświeżania historii:', e);
    }
}
