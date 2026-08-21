/**
 * Ultra-fast scanner controller for Maluchy weighing module.
 * Automatic raw material resolution, instant item addition, autoenter on bucket scan,
 * and bucket deletion for in-progress/completed buckets.
 * Adheres to Zero System Modals rule (uses in-app toasts and styled confirmation modals).
 */
(function () {
    'use strict';

    let currentBucket = null;

    const container = document.getElementById('maluchyAppContainer');
    const linia = (container && container.getAttribute('data-linia')) || 'PSD';

    const inputKodWiadra = document.getElementById('inputKodWiadra');
    const selectPlanId = document.getElementById('selectPlanId');
    const btnStartBucket = document.getElementById('btnStartBucket');
    const cardNawazanie = document.getElementById('cardNawazanie');
    const cardBucketDetails = document.getElementById('cardBucketDetails');
    const activeBucketDisplay = document.getElementById('activeBucketDisplay');
    const detailsBucketCode = document.getElementById('detailsBucketCode');
    const detailsItemsCount = document.getElementById('detailsItemsCount');
    const bucketItemsBody = document.getElementById('bucketItemsBody');
    const btnCompleteBucket = document.getElementById('btnCompleteBucket');
    const btnDeleteActiveBucket = document.getElementById('btnDeleteActiveBucket');
    const inputStacjaKod = document.getElementById('inputStacjaKod');
    const planBucketsList = document.getElementById('planBucketsList');

    // ── TOAST NOTIFICATIONS (Zero alert()) ──
    function showToast(message, type = 'info') {
        const toastContainer = document.getElementById('mToastContainer');
        if (!toastContainer) return;

        const toast = document.createElement('div');
        toast.className = `m-toast m-toast-${type}`;
        const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : 'ℹ️');
        toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }

    // ── CONFIRMATION MODAL (Zero confirm()) ──
    function showConfirm(title, message) {
        return new Promise((resolve) => {
            const modal = document.getElementById('mConfirmModal');
            const titleEl = document.getElementById('mConfirmTitle');
            const msgEl = document.getElementById('mConfirmMsg');
            const btnOk = document.getElementById('mConfirmOk');
            const btnCancel = document.getElementById('mConfirmCancel');

            if (!modal) {
                resolve(true);
                return;
            }

            titleEl.textContent = title || 'Potwierdzenie';
            msgEl.textContent = message || '';
            modal.style.display = 'flex';

            function cleanUp(result) {
                modal.style.display = 'none';
                btnOk.removeEventListener('click', onOk);
                btnCancel.removeEventListener('click', onCancel);
                resolve(result);
            }

            function onOk() { cleanUp(true); }
            function onCancel() { cleanUp(false); }

            btnOk.addEventListener('click', onOk);
            btnCancel.addEventListener('click', onCancel);
        });
    }

    // ── 1. SCANNER AUTO-ENTER ON BUCKET CODE ──
    let bucketInputTimeout = null;
    if (inputKodWiadra) {
        inputKodWiadra.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(bucketInputTimeout);
                btnStartBucket.click();
            }
        });

        // Auto-submit after 2 digits scanned (e.g. "04")
        inputKodWiadra.addEventListener('input', function () {
            clearTimeout(bucketInputTimeout);
            const val = (this.value || '').trim();
            if (/^\d{2}$/.test(val) || /^w\d{2}$/i.test(val)) {
                bucketInputTimeout = setTimeout(() => {
                    btnStartBucket.click();
                }, 120);
            }
        });
    }

    // ── 2. START / OPEN BUCKET ──
    btnStartBucket.addEventListener('click', async function () {
        const kod_wiadra = (inputKodWiadra.value || '').trim();
        const plan_id = selectPlanId.value;

        if (!kod_wiadra) {
            showToast('Zeskanuj lub wpisz kod wiadra (01–99)!', 'error');
            inputKodWiadra.focus();
            return;
        }
        if (!plan_id) {
            showToast('Wybierz aktywne zlecenie produkcyjne!', 'error');
            return;
        }

        try {
            btnStartBucket.disabled = true;
            btnStartBucket.textContent = '⏳ Ładowanie...';

            const res = await fetch('/maluchy/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ kod_wiadra, plan_id, linia })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                currentBucket = data.bucket;
                loadPlanBuckets(plan_id);

                if (currentBucket.status === 'skompletowane' || currentBucket.status === 'wrzucone_do_mieszalnika') {
                    cardNawazanie.style.display = 'none';
                    cardBucketDetails.style.display = 'none';
                    showToast(`Wiadro ${currentBucket.kod_wiadra} jest już skompletowane (${(currentBucket.pozycje || []).length} składników).`, 'info');
                    inputKodWiadra.value = '';
                    inputKodWiadra.focus();
                } else {
                    renderActiveBucket(currentBucket);
                    showToast(data.message || `Otwarto wiadro ${currentBucket.kod_wiadra}`, 'success');
                    if (inputStacjaKod) {
                        inputStacjaKod.value = '';
                        inputStacjaKod.focus();
                    }
                }
            } else {
                showToast(data.message || 'Błąd otwierania wiadra', 'error');
                inputKodWiadra.focus();
                inputKodWiadra.select();
            }
        } catch (e) {
            console.error('Error starting bucket:', e);
            showToast('Błąd sieci podczas łączenia z serwerem', 'error');
        } finally {
            btnStartBucket.disabled = false;
            btnStartBucket.textContent = '▶ Rozpocznij / Otwórz Wiadro (Enter)';
        }
    });

    // ── 3. AUTOMATIC STATION SCAN & ITEM ADDITION ──
    async function scanAndAddStation(rawStationCode) {
        if (!currentBucket || !currentBucket.id) {
            showToast('Najpierw otwórz lub rozpocznij wiadro!', 'error');
            if (inputKodWiadra) inputKodWiadra.focus();
            return;
        }

        let stacja_kod = (rawStationCode || '').trim();
        if (!stacja_kod) return;

        // Auto normalize e.g. "4" -> "KO04", "ko12" -> "KO12"
        if (/^\d+$/.test(stacja_kod)) {
            stacja_kod = 'KO' + String(stacja_kod).padStart(2, '0');
        } else if (/^ko\d+$/i.test(stacja_kod)) {
            const num = stacja_kod.replace(/[^0-9]/g, '');
            stacja_kod = 'KO' + String(num).padStart(2, '0');
        }

        try {
            if (inputStacjaKod) inputStacjaKod.disabled = true;

            const res = await fetch('/maluchy/api/item/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({
                    bucket_id: currentBucket.id,
                    stacja_kod: stacja_kod,
                    linia: linia
                })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                currentBucket = data.bucket;
                renderActiveBucket(currentBucket);
                showToast(data.message || `Dodano: ${stacja_kod}`, 'success');
                loadPlanBuckets(selectPlanId.value);
            } else {
                showToast(data.message || `Błąd dodawania stacji ${stacja_kod}`, 'error');
            }
        } catch (e) {
            console.error('Error adding station item:', e);
            showToast('Błąd połączenia z serwerem', 'error');
        } finally {
            if (inputStacjaKod) {
                inputStacjaKod.disabled = false;
                inputStacjaKod.value = '';
                inputStacjaKod.focus();
            }
        }
    }

    // Auto-scan on Enter in station input
    if (inputStacjaKod) {
        inputStacjaKod.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                scanAndAddStation(this.value);
            }
        });
    }

    // Touch click on station buttons (KO01 - KO40)
    document.querySelectorAll('.m-st-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const stacja = this.getAttribute('data-stacja');
            scanAndAddStation(stacja);
        });
    });

    // ── 4. COMPLETE BUCKET ──
    btnCompleteBucket.addEventListener('click', async function () {
        if (!currentBucket || !currentBucket.id) return;
        const count = (currentBucket.pozycje || []).length;
        if (count === 0) {
            showToast('Zeskanuj przynajmniej jeden zbiornik KO przed skompletowaniem!', 'error');
            if (inputStacjaKod) inputStacjaKod.focus();
            return;
        }

        const confirmed = await showConfirm(
            'Zakończenie kompletacji',
            `Czy na pewno zakończyć kompletację wiadra ${currentBucket.kod_wiadra} (${count} składników)?`
        );
        if (!confirmed) return;

        try {
            btnCompleteBucket.disabled = true;
            btnCompleteBucket.textContent = '⏳ Zamykanie...';

            const res = await fetch('/maluchy/api/complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ bucket_id: currentBucket.id })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                showToast(`Wiadro ${data.bucket.kod_wiadra} zostało skompletowane! Można je wsypać na Zasypie.`, 'success');
                currentBucket = null;
                cardNawazanie.style.display = 'none';
                cardBucketDetails.style.display = 'none';
                inputKodWiadra.value = '';
                inputKodWiadra.focus();
                loadPlanBuckets(selectPlanId.value);
            } else {
                showToast(data.message || 'Błąd kompletacji wiadra', 'error');
            }
        } catch (e) {
            console.error('Error completing bucket:', e);
            showToast('Błąd połączenia z serwerem', 'error');
        } finally {
            btnCompleteBucket.disabled = false;
            btnCompleteBucket.textContent = '📦 ZAKOŃCZ KOMPLETACJĘ WIADRA';
        }
    });

    // ── 5. DELETE ACTIVE BUCKET ──
    if (btnDeleteActiveBucket) {
        btnDeleteActiveBucket.addEventListener('click', async function () {
            if (!currentBucket || !currentBucket.id) return;

            const confirmed = await showConfirm(
                'Usuwanie wiadra',
                `Czy na pewno chcesz usunąć wiadro ${currentBucket.kod_wiadra} wraz ze wszystkimi składnikami?`
            );
            if (!confirmed) return;

            try {
                btnDeleteActiveBucket.disabled = true;
                const res = await fetch('/maluchy/api/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                    body: JSON.stringify({ bucket_id: currentBucket.id })
                });
                const data = await res.json();

                if (res.ok && data.success) {
                    showToast(data.message || `Usunięto wiadro ${currentBucket.kod_wiadra}`, 'info');
                    currentBucket = null;
                    cardNawazanie.style.display = 'none';
                    cardBucketDetails.style.display = 'none';
                    inputKodWiadra.value = '';
                    inputKodWiadra.focus();
                    loadPlanBuckets(selectPlanId.value);
                } else {
                    showToast(data.message || 'Błąd usuwania wiadra', 'error');
                }
            } catch (e) {
                console.error('Error deleting bucket:', e);
                showToast('Błąd połączenia z serwerem', 'error');
            } finally {
                btnDeleteActiveBucket.disabled = false;
            }
        });
    }

    // ── RENDER ACTIVE BUCKET ──
    function renderActiveBucket(bucket) {
        if (!bucket) return;
        cardNawazanie.style.display = 'block';
        cardBucketDetails.style.display = 'block';
        activeBucketDisplay.textContent = bucket.kod_wiadra;
        detailsBucketCode.textContent = bucket.kod_wiadra;
        const items = bucket.pozycje || [];
        if (detailsItemsCount) {
            detailsItemsCount.textContent = `${items.length} pozycji`;
        }

        if (items.length === 0) {
            bucketItemsBody.innerHTML = '<tr><td colspan="3" class="text-center text-muted" style="padding: 16px;">Brak dodanych pozycji. Zeskanuj pierwszy zbiornik KO!</td></tr>';
            return;
        }

        bucketItemsBody.innerHTML = items.map(it => `
            <tr>
                <td><strong style="color: #1e3a8a; font-size: 14px;">${it.stacja_kod}</strong></td>
                <td style="font-weight: 700;">${it.surowiec_nazwa}</td>
                <td style="text-align: center;">
                    <button type="button" class="remove-item-btn" data-item-id="${it.id}" 
                            title="Usuń pozycję"
                            style="background: none; border: none; cursor: pointer; font-weight: bold; color: #dc2626; font-size: 16px;">✕</button>
                </td>
            </tr>
        `).join('');

        // Attach remove buttons
        document.querySelectorAll('.remove-item-btn').forEach(btn => {
            btn.addEventListener('click', async function () {
                const itemId = this.getAttribute('data-item-id');
                const conf = await showConfirm('Usunięcie pozycji', 'Czy na pewno usunąć tę pozycję z wiadra?');
                if (!conf) return;

                const res = await fetch('/maluchy/api/item/remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                    body: JSON.stringify({ item_id: itemId, bucket_id: currentBucket.id })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    currentBucket = data.bucket;
                    renderActiveBucket(currentBucket);
                    showToast('Usunięto pozycję', 'info');
                    loadPlanBuckets(selectPlanId.value);
                    if (inputStacjaKod) inputStacjaKod.focus();
                }
            });
        });
    }

    // ── LOAD PLAN BUCKETS ──
    async function loadPlanBuckets(planId) {
        if (!planId) {
            planBucketsList.innerHTML = '<p class="text-muted text-center" style="padding: 20px;">Wybierz aktywne zlecenie, aby zobaczyć wiaderka.</p>';
            return;
        }
        try {
            const res = await fetch(`/maluchy/api/plan/${planId}?linia=${linia}`);
            const data = await res.json();
            if (!res.ok || !data.success) return;

            const summary = data.data;
            const buckets = summary.all_buckets || [];

            if (buckets.length === 0) {
                planBucketsList.innerHTML = '<p class="text-muted text-center" style="padding: 20px;">Brak przygotowanych wiaderek dla tego zlecenia.</p>';
                return;
            }

            planBucketsList.innerHTML = buckets.map(b => {
                const badgeClass = 'status-' + b.status;
                const statusLabel = b.status === 'wrzucone_do_mieszalnika' 
                    ? `✓ Wsypano (${b.mieszalnik_kod || 'MI01'})` 
                    : (b.status === 'skompletowane' ? '📦 Skompletowane' : '⏳ W trakcie');
                const items = b.pozycje || [];
                const itemsCount = items.length;
                const canDelete = b.status !== 'wrzucone_do_mieszalnika';
                const deleteBtn = canDelete
                    ? `<button type="button" class="btn-delete-plan-bucket" data-bucket-id="${b.id}" data-bucket-code="${b.kod_wiadra}" 
                              title="Usuń wiadro ${b.kod_wiadra}"
                              style="background: none; border: none; color: #dc2626; font-size: 15px; cursor: pointer; padding: 4px 6px; margin-left: 6px;">🗑</button>`
                    : '';

                const itemsHtml = items.length > 0 
                    ? items.map(p => `
                        <div style="display: flex; align-items: center; justify-content: space-between; background: #ffffff; padding: 6px 10px; border-radius: 6px; border: 1px solid #e2e8f0; margin-bottom: 4px;">
                            <span style="font-weight: 800; color: #1e3a8a; font-size: 13px;">${p.stacja_kod}</span>
                            <span style="font-weight: 700; color: #0f172a; margin-left: 10px; flex: 1; font-size: 13px;">${p.surowiec_nazwa}</span>
                        </div>
                    `).join('')
                    : '<div style="color: #94a3b8; font-style: italic; font-size: 12px;">Brak składników w wiadrze</div>';

                const ssccInfo = b.nr_sscc ? `<div style="font-family: monospace; font-size: 11px; background: #e0e7ff; color: #3730a3; padding: 4px 8px; border-radius: 4px; margin-bottom: 6px; font-weight: 700;">SSCC: ${b.nr_sscc}</div>` : '';
                const prodDate = b.data_produkcji || b.data_rozpoczecia || '—';
                const expDate = b.data_przydatnosci || '— (+24h)';

                return `
                    <div class="m-plan-bucket-card" data-bucket-id="${b.id}" style="background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 12px; padding: 12px 14px; margin-bottom: 12px; cursor: pointer; transition: all 0.2s;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <span class="m-bucket-pill" style="font-size: 14px;">${b.kod_wiadra}</span>
                                <span style="font-weight: 700; margin-left: 8px; font-size: 13px; color: #1e293b;">${itemsCount} składników</span>
                                <span style="font-size: 12px; color: #2563eb; margin-left: 6px; font-weight: 700;" class="m-toggle-indicator">▾ zawartość</span>
                                <div style="font-size: 12px; color: #64748b; margin-top: 4px;">
                                    Prod: ${prodDate} | Ważność: ${expDate}
                                </div>
                            </div>
                            <div style="display: flex; align-items: center;">
                                <span class="status-badge ${badgeClass}">${statusLabel}</span>
                                ${deleteBtn}
                            </div>
                        </div>
                        <div class="m-bucket-items-preview" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #cbd5e1;">
                            ${ssccInfo}
                            <div style="font-weight: 800; color: #475569; font-size: 11px; text-transform: uppercase; margin-bottom: 6px;">
                                Składniki w wiadrze ${b.kod_wiadra}:
                            </div>
                            ${itemsHtml}
                        </div>
                    </div>
                `;
            }).join('');

            // Attach card click to toggle preview of items directly underneath
            document.querySelectorAll('.m-plan-bucket-card').forEach(card => {
                card.addEventListener('click', function (e) {
                    if (e.target.closest('.btn-delete-plan-bucket')) return;
                    if (e.target.closest('.btn-resume-bucket')) return;

                    const previewEl = this.querySelector('.m-bucket-items-preview');
                    const indicator = this.querySelector('.m-toggle-indicator');
                    if (previewEl) {
                        const isHidden = previewEl.style.display === 'none';
                        previewEl.style.display = isHidden ? 'block' : 'none';
                        if (indicator) {
                            indicator.textContent = isHidden ? '▴ zwiń' : '▾ zawartość';
                        }
                    }
                });
            });

            // Attach resume button for in-progress buckets
            document.querySelectorAll('.btn-resume-bucket').forEach(btn => {
                btn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    const bId = parseInt(this.getAttribute('data-bucket-id'), 10);
                    const selected = buckets.find(b => b.id === bId);
                    if (selected && selected.status === 'w_trakcie_nawazania') {
                        currentBucket = selected;
                        renderActiveBucket(selected);
                        if (inputStacjaKod) inputStacjaKod.focus();
                    }
                });
            });

            // Attach delete buttons in list
            document.querySelectorAll('.btn-delete-plan-bucket').forEach(btn => {
                btn.addEventListener('click', async function (e) {
                    e.stopPropagation();
                    const bId = this.getAttribute('data-bucket-id');
                    const bCode = this.getAttribute('data-bucket-code');
                    const conf = await showConfirm('Usuwanie wiadra', `Czy na pewno usunąć wiadro ${bCode}?`);
                    if (!conf) return;

                    const res = await fetch('/maluchy/api/delete', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                        body: JSON.stringify({ bucket_id: bId })
                    });
                    const data = await res.json();
                    if (res.ok && data.success) {
                        showToast(data.message || `Usunięto wiadro ${bCode}`, 'info');
                        if (currentBucket && currentBucket.id == bId) {
                            currentBucket = null;
                            cardNawazanie.style.display = 'none';
                            cardBucketDetails.style.display = 'none';
                        }
                        loadPlanBuckets(selectPlanId.value);
                    } else {
                        showToast(data.message || 'Błąd usuwania wiadra', 'error');
                    }
                });
            });
        } catch (e) {
            console.error('Error loading plan buckets:', e);
        }
    }

    // On plan change, reload buckets
    if (selectPlanId) {
        selectPlanId.addEventListener('change', function () {
            loadPlanBuckets(this.value);
        });

        if (selectPlanId.value) {
            loadPlanBuckets(selectPlanId.value);
        }
    }
})();
