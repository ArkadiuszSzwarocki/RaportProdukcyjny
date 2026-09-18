(function (global) {
    'use strict';

    let pollInterval = null;

    function updateUI(data) {
        // Map numeric status to text if needed
        let statusText = data.status;
        if (statusText === 4) statusText = 'PRACA';
        else if (statusText === 0) statusText = 'STOP';
        
        // Auto-refresh page if pallet counter increases (new pallet added by system)
        if (data.pallet_counter !== undefined) {
            if (window.lastMachinePalletCounter !== undefined && data.pallet_counter > window.lastMachinePalletCounter) {
                if (typeof window.performPartialReload === 'function') {
                    window.performPartialReload({ force: true, preserveScroll: true, source: 'auto-pallet-added' });
                } else if (typeof global.performPartialReload === 'function') {
                    global.performPartialReload({ force: true, preserveScroll: true, source: 'auto-pallet-added' });
                } else {
                    window.location.reload();
                }
            }
            window.lastMachinePalletCounter = data.pallet_counter;
        }

        // 1. Update top-bar elements (legacy)
        const topContainer = document.getElementById('machine-stats-container');
        const topSpeed = document.getElementById('machine-speed-value');
        const topStatusDot = document.getElementById('machine-status-dot');
        const topStatusText = document.getElementById('machine-status-text');

        if (topContainer) {
            topContainer.style.display = 'inline-flex';
            if (data.bpm !== undefined && topSpeed) {
                topSpeed.textContent = data.bpm;
                topSpeed.style.color = data.bpm > 0 ? '#2ecc71' : '#e74c3c';
            }
            if (statusText && topStatusText) {
                topStatusText.textContent = 'Maszyna: ' + statusText;
            }
            if (statusText && topStatusDot) {
                topStatusDot.style.backgroundColor = (statusText === 'PRACA' || statusText === 'RUNNING') ? '#2ecc71' : '#f1c40f';
            }
        }

        // 2. Update all pills (new approach)
        const bpmPills = document.querySelectorAll('[data-machine-bpm-pill]');
        bpmPills.forEach(pill => {
            pill.textContent = (data.bpm || 0) + ' BPM';
            pill.style.display = 'inline-block';
            pill.style.background = (data.bpm > 0) ? '#16a34a' : '#94a3b8';
        });

        const statusPills = document.querySelectorAll('[data-machine-status-pill]');
        statusPills.forEach(pill => {
            pill.textContent = statusText || 'ONLINE';
            pill.className = 'machine-status-pill ' + ((statusText === 'PRACA' || statusText === 'RUNNING') ? 'status-running' : 'status-idle');
        });

        const counterPills = document.querySelectorAll('[data-machine-counter-pill]');
        counterPills.forEach(pill => {
            if (data.counter !== undefined) {
                const type = pill.getAttribute('data-counter-type');
                if (type === 'global') {
                    pill.textContent = data.counter + ' szt.';
                } else {
                    if (data.local_counter !== undefined) {
                        pill.textContent = data.local_counter + ' szt.';
                    } else {
                        // Real/Current counter = global - start
                        let startVal = Number(data.start_counter);
                        if (isNaN(startVal) || data.start_counter === undefined) {
                            startVal = Number(pill.getAttribute('data-start-counter') || 0);
                        }
                        const realVal = Math.max(0, Number(data.counter) - startVal);
                        pill.textContent = realVal + ' szt.';
                    }
                }
                pill.style.display = 'inline-block';
            }
        });

        // 3. Update Recipe
        const recipePills = document.querySelectorAll('[data-machine-recipe-pill]');
        recipePills.forEach(pill => {
            if (data.receptura) {
                pill.textContent = data.receptura;
                pill.style.display = 'inline-block';
            }
        });

        // 4. Update Palletizer status
        const warstwaEls = document.querySelectorAll('[data-machine-nr-warstwy]');
        warstwaEls.forEach(el => {
            if (data.nrWarstwy !== undefined) {
                el.textContent = 'W: ' + data.nrWarstwy;
            }
        });
        
        const workiEls = document.querySelectorAll('[data-machine-nr-worka]');
        workiEls.forEach(el => {
            if (data.nrWorka !== undefined) {
                el.textContent = 'Szt: ' + data.nrWorka;
            }
        });

        // 5. Update Wrapped Status
        const wrappedIndicators = document.querySelectorAll('[data-machine-wrapped-indicator]');
        wrappedIndicators.forEach(ind => {
            ind.style.display = 'inline-block';
            if (data.is_wrapped) {
                ind.textContent = 'OWINIĘTA';
                ind.style.backgroundColor = '#10b981'; // Zielony
                ind.style.animation = 'pulse 2s infinite';
                ind.style.opacity = '1';
            } else {
                ind.textContent = 'OWIJARKA...';
                ind.style.backgroundColor = '#94a3b8'; // Szary
                ind.style.animation = 'none';
                ind.style.opacity = '0.6';
            }
        });

        // 6. Loss Calculator
        const lossToggle = document.getElementById('calc-loss-toggle');
        const lossResults = document.getElementById('loss-calc-results');
        if (lossToggle && lossResults) {
            if (!lossToggle.checked) {
                lossResults.style.opacity = '0.3';
            } else {
                lossResults.style.opacity = '1';
                
                const bagsPerLayer = parseInt(document.getElementById('bags-per-layer').value) || 4;
                const bagsPerPallet = parseInt(document.getElementById('bags-per-pallet').value) || 40;
                
                let produced = 0;
                if (data.local_counter !== undefined && data.local_counter > 0) {
                    produced = data.local_counter;
                } else {
                    const realPill = document.querySelector('[data-machine-counter-pill][data-counter-type="real"]');
                    const startVal = Number(realPill ? realPill.getAttribute('data-start-counter') : 0);
                    produced = Math.max(0, Number(data.counter || 0) - startVal);
                }
                
                let stacked = 0;
                const palletPill = document.querySelector('[data-machine-pallet-count-pill]');
                if (palletPill) {
                    const startPallets = Number(palletPill.getAttribute('data-start-pallet') || 0);
                    
                    if (window.palletDeletedOffset === undefined) {
                        const dbPallets = Number(palletPill.getAttribute('data-db-pallets') || 0);
                        const machinePallets = Math.max(0, Number(data.pallet_counter || 0) - startPallets);
                        // The difference between machine counter and database is the number of deleted/missing pallets
                        window.palletDeletedOffset = Math.max(0, machinePallets - dbPallets);
                    }
                    
                    const realPallets = Math.max(0, Number(data.pallet_counter || 0) - startPallets) - window.palletDeletedOffset;
                    
                    const nrWarstwy = Number(data.nrWarstwy || 0);
                    const nrWorka = Number(data.nrWorka || 0);
                    const currentLayer = Math.max(0, nrWarstwy - 1);
                    
                    stacked = (Math.max(0, realPallets) * bagsPerPallet) + (currentLayer * bagsPerLayer) + nrWorka;
                }
                
                const diff = Math.max(0, produced - stacked);
                
                document.getElementById('loss-produced').innerHTML = produced + ' <span style="font-size: 0.5em; font-weight: normal;">szt.</span>';
                document.getElementById('loss-stacked').innerHTML = stacked + ' <span style="font-size: 0.5em; font-weight: normal;">szt.</span>';
                document.getElementById('loss-difference').innerHTML = diff + ' <span style="font-size: 0.5em; font-weight: normal;">szt.</span>';
            }
        }

        // 7. Opróżnianie Paletyzatora (Emptying Palletizer)
        if (data.oproznianie && data.oproznianie_snapshot) {
            const snapTs = data.oproznianie_snapshot.timestamp;
            const lastLocalTs = localStorage.getItem('lastOproznianieTs');
            if (lastLocalTs !== String(snapTs) && window.lastOproznianieTimestamp !== snapTs) {
                window.lastOproznianieTimestamp = snapTs;
                localStorage.setItem('lastOproznianieTs', snapTs);
                
                // Show modal on Workowanie / production / machine pages
                const configElem = document.getElementById('dashboard-config');
                const sekcja = configElem ? configElem.getAttribute('data-sekcja') : null;
                const path = window.location.pathname.toLowerCase();
                const isWorkowanieOrProd = (sekcja === 'Workowanie' || path.includes('workowanie') || path.includes('panel_glowny') || path.includes('zarzad_live') || path.includes('maszyny') || path.includes('produkcja'));
                
                if (isWorkowanieOrProd || !sekcja) {
                    showOproznianieModal(data.oproznianie_snapshot.nrWarstwy, data.oproznianie_snapshot.nrWorka);
                }
            }
        }
    }

    function showOproznianieModal(warstwa, worek) {
        let modal = document.getElementById('oproznianie-modal');
        if (!modal) {
            // Create modal dynamically if it doesn't exist
            modal = document.createElement('div');
            modal.id = 'oproznianie-modal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 99999; backdrop-filter: blur(2px);';
            modal.innerHTML = `
                <div style="background: white; padding: 30px; border-radius: 12px; max-width: 520px; width: 90%; text-align: center; box-shadow: 0 12px 30px rgba(0,0,0,0.3); font-family: inherit;">
                    <h2 style="color: #e74c3c; margin-top: 0; font-size: 1.5rem;">⚠️ Opróżnianie Paletyzatora</h2>
                    <p style="font-size: 1.05em; color: #444; margin-bottom: 12px;">Wykryto sygnał opróżniania paletyzatora. Automatyczne dodanie pełnej palety zostało <strong>zablokowane</strong>.</p>
                    <div style="background: #f8f9fa; padding: 12px 16px; border-radius: 8px; margin: 15px 0; border: 1px solid #dee2e6;">
                        <p style="margin: 0; font-weight: bold; color: #333; font-size: 0.95em;">Stan w momencie kliknięcia opróżniania:</p>
                        <p style="margin: 5px 0 0 0; font-size: 1.25em; color: #2c3e50;">
                            Warstwa: <span style="color: #2980b9; font-weight: bold;">${warstwa}</span> | 
                            Worek: <span style="color: #2980b9; font-weight: bold;">${worek}</span>
                        </p>
                    </div>
                    <p style="font-weight: bold; font-size: 1.15em; margin: 15px 0 10px 0; color: #2c3e50;">Wpisz wagę palety po opróżnieniu (kg):</p>
                    <div style="display: flex; gap: 10px; justify-content: center; margin-top: 15px;">
                        <input type="number" id="oproznianie-waga-input" style="padding: 10px; font-size: 1.3em; width: 140px; border: 2px solid #3498db; border-radius: 6px; text-align: center; font-weight: bold;" placeholder="np. 350" autofocus>
                        <button id="oproznianie-zapisz-btn" style="padding: 10px 24px; font-size: 1.1em; background: #27ae60; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; transition: background 0.2s;">Zapisz paletę</button>
                    </div>
                    <button id="oproznianie-anuluj-btn" style="margin-top: 18px; background: none; border: none; color: #7f8c8d; cursor: pointer; text-decoration: underline; font-size: 0.9em;">Zamknij (nie dodawaj palety)</button>
                </div>
            `;
            document.body.appendChild(modal);

            document.getElementById('oproznianie-anuluj-btn').addEventListener('click', () => {
                modal.style.display = 'none';
            });

            const weightInput = document.getElementById('oproznianie-waga-input');
            weightInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    document.getElementById('oproznianie-zapisz-btn').click();
                }
            });
            
            document.getElementById('oproznianie-zapisz-btn').addEventListener('click', () => {
                const waga = document.getElementById('oproznianie-waga-input').value;
                if (!waga || parseFloat(waga) <= 0) {
                    alert('Podaj prawidłową wagę (kg)!');
                    return;
                }
                
                // If there's an active "Dodaj paletę" form on the page, fill it.
                // Otherwise, if we are on the new dashboard, find the active plan card.
                const addWeightInput = document.querySelector('input[name="waga_palety"]') || document.querySelector('input[name="waga"]');
                const addPalletForm = addWeightInput ? addWeightInput.closest('form') : null;
                
                let actionUrl = null;
                let formData = null;

                if (addPalletForm) {
                    actionUrl = addPalletForm.getAttribute('action');
                    formData = new FormData(addPalletForm);
                    formData.set('waga_palety', waga);
                } else {
                    // Poszukaj aktywnej karty zlecenia (nowy dashboard)
                    const activeCard = document.querySelector('.card[data-is-active="true"][data-sekcja="Workowanie"]') || document.querySelector('.card[data-is-active="true"]');
                    if (activeCard) {
                        const planId = activeCard.getAttribute('data-id');
                        
                        // Spróbuj znaleźć aktualną linię (AGRO)
                        const liniaInput = document.querySelector('input[name="linia"]');
                        const linia = liniaInput ? liniaInput.value : 'AGRO';
                        
                        actionUrl = `/dodaj_palete/${planId}?linia=${linia}`;
                        formData = new FormData();
                        formData.append('waga_palety', waga);
                        formData.append('linia', linia);
                    }
                }
                
                if (actionUrl && formData) {
                    // Disable buttons in modal while loading
                    const saveBtn = document.getElementById('oproznianie-zapisz-btn');
                    const cancelBtn = document.getElementById('oproznianie-anuluj-btn');
                    if (saveBtn) { saveBtn.disabled = true; saveBtn.innerText = 'Dodawanie...'; }
                    if (cancelBtn) cancelBtn.disabled = true;
                    
                    fetch(actionUrl, {
                        method: 'POST',
                        body: formData,
                        credentials: 'same-origin'
                    })
                    .then(response => {
                        if (response.ok) {
                            alert(`Paleta o wadze ${waga} kg została pomyślnie dodana z opróżnienia.`);
                            window.location.reload();
                        } else {
                            response.text().then(text => {
                                alert(`Błąd serwera podczas dodawania palety: ${response.status}\nTreść: ${text.substring(0, 150)}`);
                                if (saveBtn) { saveBtn.disabled = false; saveBtn.innerText = 'Zapisz paletę'; }
                                if (cancelBtn) cancelBtn.disabled = false;
                            });
                        }
                    })
                    .catch(err => {
                        alert(`Błąd sieci podczas dodawania palety: ${err}`);
                        if (saveBtn) { saveBtn.disabled = false; saveBtn.innerText = 'Zapisz paletę'; }
                        if (cancelBtn) cancelBtn.disabled = false;
                    });
                    
                    // Don't close modal yet, wait for reload or error
                    return;
                } else {
                    alert(`Opróżniono: ${waga} kg. Nie znaleziono aktywnego zlecenia na stronie. Utwórz paletę ręcznie.`);
                }
                
                modal.style.display = 'none';
            });
        }
        
        // Update the info in case it was created previously
        const infoEl = modal.querySelector('p > span') ? modal.querySelector('p > span').parentNode : null;
        if (infoEl) {
            infoEl.innerHTML = `
                Warstwa: <span style="color: #2980b9; font-weight: bold;">${warstwa}</span> | 
                Worek: <span style="color: #2980b9; font-weight: bold;">${worek}</span>
            `;
        }
        
        const inp = document.getElementById('oproznianie-waga-input');
        if (inp) {
            inp.value = '';
            setTimeout(() => inp.focus(), 100);
        }
        modal.style.display = 'flex';
    }

    function setGlobalStatus(text, colorClass) {
        const statusPills = document.querySelectorAll('[data-machine-status-pill]');
        statusPills.forEach(pill => {
            pill.textContent = text;
            pill.className = 'machine-status-pill ' + colorClass;
        });
        const topStatusText = document.getElementById('machine-status-text');
        if (topStatusText) topStatusText.textContent = 'Maszyna: ' + text;
    }

    async function fetchTelemetry() {
        try {
            const response = await fetch('/machine-telemetry', {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (response.status === 401) {
                if (pollInterval) clearInterval(pollInterval);
                return;
            }
            if (response.ok) {
                const result = await response.json();
                if (result.success && result.data) {
                    updateUI(result.data);
                }
            }
        } catch (e) {
            console.warn('[TELEMETRY] Błąd pobierania:', e);
        }
    }

    function start() {
        if (pollInterval) clearInterval(pollInterval);
        
        // Pierwsze pobranie
        fetchTelemetry();
        
        // Co 5 sekund odpytujemy nasz serwer (Mostek MQTT)
        pollInterval = setInterval(fetchTelemetry, 5000);
        console.log('[TELEMETRY] Uruchomiono mostek serwerowy (polling 5s)');
    }

    function init() {
        const configElem = document.getElementById('dashboard-config');
        if (!configElem) return;

        const linia = configElem.getAttribute('data-linia');
        if (linia === 'AGRO') {
            start();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.addEventListener('app:partialReload', init);

    global.machineStats = {
        init: init
    };

})(window);
