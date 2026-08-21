/**
 * Ultra-fast scanner modal for dumping Maluchy buckets into active Zasyp mixer.
 * Supports auto-enter and instant submission on scanner barcode input.
 */
(function (global) {
    'use strict';

    function ensureModal() {
        let modal = document.getElementById('modalSkanWiadroZasyp');
        if (modal) return modal;

        modal = document.createElement('div');
        modal.id = 'modalSkanWiadroZasyp';
        modal.style.cssText = `
            display: none;
            position: fixed;
            z-index: 10000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(15, 23, 42, 0.75);
            backdrop-filter: blur(3px);
            align-items: center;
            justify-content: center;
        `;

        modal.innerHTML = `
            <div style="
                background: #ffffff;
                border-radius: 14px;
                box-shadow: 0 20px 25px -5px rgba(0,0,0,0.3);
                width: 92%;
                max-width: 480px;
                padding: 24px;
                border: 2px solid #3b82f6;
                position: relative;
            ">
                <button type="button" id="closeSkanWiadroModal" style="
                    position: absolute;
                    top: 14px;
                    right: 14px;
                    background: none;
                    border: none;
                    font-size: 20px;
                    font-weight: bold;
                    color: #94a3b8;
                    cursor: pointer;
                ">✕</button>

                <h3 style="margin: 0 0 8px 0; font-size: 18px; font-weight: 800; color: #1e293b; display: flex; align-items: center; gap: 8px;">
                    🪣 Wrzucenie Wiadra do Mieszalnika
                </h3>
                <p style="margin: 0 0 16px 0; font-size: 13px; color: #64748b;">
                    Zeskanuj kod wiadra oraz lokalizację mieszalnika (np. <strong>MI01</strong>).
                </p>

                <input type="hidden" id="zasypPlanIdHidden" value="" />
                <input type="hidden" id="zasypSzarzaIdHidden" value="" />
                <input type="hidden" id="zasypLiniaHidden" value="PSD" />

                <div style="margin-bottom: 14px;">
                    <label style="display: block; font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 4px;">
                        1. Kod Wiadra (01–99 / Skaner)
                    </label>
                    <input type="text" id="inputModalKodWiadra" class="form-control" placeholder="np. 04" 
                           style="width: 100%; padding: 10px 12px; font-size: 16px; font-weight: 800; text-transform: uppercase; border: 2px solid #cbd5e1; border-radius: 8px;" />
                </div>

                <div style="margin-bottom: 18px;">
                    <label style="display: block; font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 4px;">
                        2. Lokalizacja Mieszalnika (Skaner)
                    </label>
                    <input type="text" id="inputModalMieszalnik" class="form-control" placeholder="np. MI01" value="MI01" 
                           style="width: 100%; padding: 10px 12px; font-size: 16px; font-weight: 800; text-transform: uppercase; border: 2px solid #cbd5e1; border-radius: 8px;" />
                </div>

                <div id="zasypWiadroStatusMsg" style="margin-bottom: 14px; font-size: 13px; font-weight: 700; display: none;"></div>

                <div style="display: flex; gap: 10px;">
                    <button type="button" id="btnConfirmDumpWiadro" style="
                        flex: 1;
                        padding: 12px;
                        background: #10b981;
                        color: #ffffff;
                        border: none;
                        border-radius: 8px;
                        font-weight: 800;
                        font-size: 15px;
                        cursor: pointer;
                        box-shadow: 0 4px 6px -1px rgba(16, 185, 129, 0.3);
                    ">✓ POTWIERDŹ WRZUCENIE (Enter)</button>
                    <button type="button" id="btnCancelDumpWiadro" style="
                        padding: 12px 18px;
                        background: #f1f5f9;
                        color: #475569;
                        border: 1px solid #cbd5e1;
                        border-radius: 8px;
                        font-weight: 700;
                        cursor: pointer;
                    ">Anuluj</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Bind modal events
        const inputWiadro = modal.querySelector('#inputModalKodWiadra');
        const inputMixer = modal.querySelector('#inputModalMieszalnik');
        const btnConfirm = modal.querySelector('#btnConfirmDumpWiadro');
        const btnCancel = modal.querySelector('#btnCancelDumpWiadro');
        const btnClose = modal.querySelector('#closeSkanWiadroModal');

        function hideModal() {
            modal.style.display = 'none';
        }

        btnCancel.addEventListener('click', hideModal);
        btnClose.addEventListener('click', hideModal);

        // Auto-enter on bucket scan jumps to mixer scan
        inputWiadro.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                if ((inputWiadro.value || '').trim()) {
                    inputMixer.focus();
                    inputMixer.select();
                }
            }
        });

        // Auto-enter on mixer scan submits instantly
        inputMixer.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                btnConfirm.click();
            }
        });

        btnConfirm.addEventListener('click', async function () {
            const planId = modal.querySelector('#zasypPlanIdHidden').value;
            const szarzaId = modal.querySelector('#zasypSzarzaIdHidden').value;
            const linia = modal.querySelector('#zasypLiniaHidden').value;
            const kodWiadra = (inputWiadro.value || '').trim();
            const mieszalnikKod = (inputMixer.value || 'MI01').trim();
            const msgDiv = modal.querySelector('#zasypWiadroStatusMsg');

            if (!kodWiadra) {
                msgDiv.style.display = 'block';
                msgDiv.style.color = '#dc2626';
                msgDiv.textContent = 'Zeskanuj lub wpisz kod wiadra!';
                inputWiadro.focus();
                return;
            }

            try {
                btnConfirm.disabled = true;
                btnConfirm.textContent = '⏳ Zapisywanie...';
                msgDiv.style.display = 'none';

                const res = await fetch('/maluchy/api/dump-to-mixer', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        kod_wiadra: kodWiadra,
                        plan_id: planId,
                        szarza_id: szarzaId,
                        mieszalnik_kod: mieszalnikKod,
                        linia: linia || 'PSD'
                    })
                });

                const data = await res.json();
                if (res.ok && data.success) {
                    hideModal();
                    if (typeof global.performPartialReload === 'function') {
                        global.performPartialReload({ preserveScroll: true, source: 'wiaderko-dumped' });
                    } else {
                        global.location.reload();
                    }
                } else {
                    msgDiv.style.display = 'block';
                    msgDiv.style.color = '#dc2626';
                    msgDiv.textContent = data.message || 'Błąd zatwierdzania wiadra';
                    inputWiadro.focus();
                    inputWiadro.select();
                }
            } catch (err) {
                console.error('Error dumping bucket to mixer:', err);
                msgDiv.style.display = 'block';
                msgDiv.style.color = '#dc2626';
                msgDiv.textContent = 'Błąd połączenia z serwerem';
            } finally {
                btnConfirm.disabled = false;
                btnConfirm.textContent = '✓ POTWIERDŹ WRZUCENIE (Enter)';
            }
        });

        return modal;
    }

    global.skanujWiadroDoMieszalnika = function (planId, szarzaId, linia) {
        const modal = ensureModal();
        modal.querySelector('#zasypPlanIdHidden').value = planId || '';
        modal.querySelector('#zasypSzarzaIdHidden').value = szarzaId || '';
        modal.querySelector('#zasypLiniaHidden').value = linia || 'PSD';

        const inputWiadro = modal.querySelector('#inputModalKodWiadra');
        const inputMixer = modal.querySelector('#inputModalMieszalnik');
        const msgDiv = modal.querySelector('#zasypWiadroStatusMsg');

        inputWiadro.value = '';
        inputMixer.value = 'MI01';
        msgDiv.style.display = 'none';

        modal.style.display = 'flex';
        setTimeout(() => {
            inputWiadro.focus();
        }, 100);
    };

})(typeof window !== 'undefined' ? window : this);
