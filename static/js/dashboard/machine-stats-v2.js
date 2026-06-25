(function (global) {
    'use strict';

    let pollInterval = null;

    function updateUI(data) {
        // Map numeric status to text if needed
        let statusText = data.status;
        if (statusText === 4) statusText = 'PRACA';
        else if (statusText === 0) statusText = 'STOP';

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
                    const realPallets = Math.max(0, Number(data.pallet_counter || 0) - startPallets);
                    
                    const nrWarstwy = Number(data.nrWarstwy || 0);
                    const nrWorka = Number(data.nrWorka || 0);
                    const currentLayer = Math.max(0, nrWarstwy - 1);
                    
                    stacked = (realPallets * bagsPerPallet) + (currentLayer * bagsPerLayer) + nrWorka;
                }
                
                const diff = Math.max(0, produced - stacked);
                
                document.getElementById('loss-produced').innerHTML = produced + ' <span style="font-size: 0.5em; font-weight: normal;">szt.</span>';
                document.getElementById('loss-stacked').innerHTML = stacked + ' <span style="font-size: 0.5em; font-weight: normal;">szt.</span>';
                document.getElementById('loss-difference').innerHTML = diff + ' <span style="font-size: 0.5em; font-weight: normal;">szt.</span>';
            }
        }
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
