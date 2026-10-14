(function (global) {
    'use strict';

    if (global.dashboardEtapy) {
        return;
    }

    var initialized = false;
    var pendingZasypForm = null;
    var pendingStopForm = null;
    var szarzaValues = [1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000];
    var etapyTimesLimits = { nawazanie_min: 20, mieszanie_min: 10, dosypka_min: 5, oproznianie_min: 10 };


    function ready(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
            return;
        }
        callback();
    }

    function ensureSzarzaModal() {
        var existingModal = document.getElementById('szarza-modal');
        if (existingModal) {
            return existingModal;
        }

        if (!document.getElementById('dashboard-szarza-modal-style')) {
            var style = document.createElement('style');
            style.id = 'dashboard-szarza-modal-style';
            style.textContent = '' +
                '#szarza-modal { position:fixed; inset:0; display:none; align-items:center; justify-content:center; background:rgba(0,0,0,0.5); z-index:9999; backdrop-filter: blur(4px); }' +
                '#szarza-modal.open { display:flex; }' +
                '#szarza-modal .modal-card { background:#fff; border-radius:12px; padding:24px; width:400px; box-shadow:0 15px 35px rgba(0,0,0,0.3); border:1px solid #ddd; }' +
                '#szarza-modal h3 { margin:0 0 15px 0; font-size:1.2em; color:#2c3e50; text-align:center; }' +
                '#szarza-grid { display:grid; grid-template-columns: repeat(3, 1fr); gap:10px; margin-bottom:20px; }' +
                '#szarza-grid .quick-btn { padding:12px 5px; background:#f8f9fa; border:1px solid #dee2e6; border-radius:8px; cursor:pointer; font-weight:bold; color:#495057; transition:all 0.2s; font-size:0.9em; }' +
                '#szarza-grid .quick-btn:hover { background:#e9ecef; border-color:#ced4da; transform: translateY(-1px); }' +
                '#szarza-grid .quick-btn.active { background:#27ae60; color:#fff; border-color:#27ae60; }' +
                '#szarza-modal .input-wrapper { margin-bottom:20px; }' +
                '#szarza-modal .input-wrapper label { display:block; margin-bottom:5px; font-size:0.85em; color:#7f8c8d; }' +
                '#szarza-modal input[type="number"] { width:100%; padding:12px; font-size:1.1em; border-radius:8px; border:2px solid #eee; outline:none; transition:border-color 0.2s; text-align:center; font-weight:bold; }' +
                '#szarza-modal input[type="number"]:focus { border-color:#27ae60; }' +
                '#szarza-modal .modal-actions { display:flex; gap:12px; justify-content:stretch; }' +
                '#szarza-modal .btn { flex:1; padding:14px; border-radius:8px; cursor:pointer; border:none; font-weight:bold; font-size:1em; }' +
                '#szarza-modal .btn-prim { background:#27ae60; color:#fff; box-shadow:0 4px 6px rgba(39, 174, 96, 0.2); }' +
                '#szarza-modal .btn-prim:hover { background:#219150; }' +
                '#szarza-modal .btn-sec { background:#f1f2f6; color:#2f3542; }' +
                '#szarza-modal .btn-sec:hover { background:#dfe4ea; }';
            document.head.appendChild(style);
        }

        var gridHtml = szarzaValues.map(function (value) {
            return '<button type="button" class="quick-btn" data-value="' + value + '">' + value + '</button>';
        }).join('');

        var modalHtml = '' +
            '<div id="szarza-modal" role="dialog" aria-modal="true">' +
            '  <div class="modal-card">' +
            '    <h3>Wybierz wielkość szarży (kg)</h3>' +
            '    <div id="szarza-grid">' + gridHtml + '</div>' +
            '    <div class="input-wrapper">' +
            '      <label>Inna wartość:</label>' +
            '      <input name="modal_wielkosc_szarzy_kg" type="number" step="0.1" min="0.1" placeholder="Wpisz wagę...">' +
            '    </div>' +
            '    <div class="modal-actions">' +
            '      <button type="button" class="btn btn-sec" id="szarza-cancel">Anuluj</button>' +
            '      <button type="button" class="btn btn-prim" id="szarza-confirm">Zatwierdź START</button>' +
            '    </div>' +
            '  </div>' +
            '</div>';

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        return document.getElementById('szarza-modal');
    }

    function ensureStopDecisionModal() {
        var existingModal = document.getElementById('stop-decision-modal');
        if (existingModal) {
            return existingModal;
        }

        if (!document.getElementById('dashboard-stop-decision-style')) {
            var stopStyle = document.createElement('style');
            stopStyle.id = 'dashboard-stop-decision-style';
            stopStyle.textContent = '' +
                '#stop-decision-modal { position:fixed; inset:0; display:none; align-items:center; justify-content:center; background:rgba(0,0,0,0.5); z-index:10000; }' +
                '#stop-decision-modal.open { display:flex !important; }' +
                '#stop-decision-modal .card { background:#fff; border-radius:12px; padding:18px; width:560px !important; max-width:92vw !important; margin:auto !important; box-shadow:0 15px 35px rgba(0,0,0,0.25); border:1px solid #e6eef2; flex-shrink: 0; }' +
                '#stop-decision-modal h3 { margin:0 0 10px 0; font-size:1.1em; text-align:center; }' +
                '#stop-decision-modal .actions { display:grid; grid-template-columns:1fr; gap:10px; margin-top:12px; }' +
                '#stop-decision-modal .action-group { border:1px solid #e7edf3; border-radius:10px; padding:10px; background:#fbfdff; }' +
                '#stop-decision-modal .action-desc { margin:8px 2px 0; color:#5b6b7b; font-size:0.86em; line-height:1.3; }' +
                '#stop-decision-modal .actions .btn { padding:12px; border-radius:8px; font-weight:700; cursor:pointer; border:none; }' +
                '#stop-decision-modal .btn-primary { background:#10b981; color:#fff; }' +
                '#stop-decision-modal .btn-warning { background:#f59e0b; color:#fff; }' +
                '#stop-decision-modal .btn-danger { background:#ef4444; color:#fff; }' +
                '#stop-decision-modal .btn-cancel { background:#f1f2f6; color:#2f3542; }';
            document.head.appendChild(stopStyle);
        }

        var decisionHtml = '' +
            '<div id="stop-decision-modal" role="dialog" aria-modal="true">' +
            '  <div class="card">' +
            '    <h3 id="stop-decision-title">Co teraz zrobić po STOP mieszania?</h3>' +
            '    <div id="stop-decision-subtitle" class="small text-muted">Wybierz jedną z opcji, aby kontynuować proces produkcji.</div>' +
            '    <div class="actions">' +
            '      <div id="stop-group-add-pair" class="action-group">' +
            '        <button type="button" id="stop-add-pair" class="btn btn-primary">Dodaj parę: dosypka + mieszanie</button>' +
            '        <div id="stop-add-pair-desc" class="action-desc">Tworzy kolejny cykl: nowa dosypka i od razu kolejny etap mieszania.</div>' +
            '      </div>' +
            '      <div id="stop-group-empty-continue" class="action-group">' +
            '        <button type="button" id="stop-oprozniamy" class="btn btn-warning">Opróżniamy (kontynuuj opróżnianie)</button>' +
            '        <div id="stop-oprozniamy-desc" class="action-desc">Kończy mieszanie i przechodzi do opróżniania aktualnego punktu kontrolnego.</div>' +
            '      </div>' +
            '      <div id="stop-group-empty-end" class="action-group">' +
            '        <button type="button" id="stop-oprozniamy-end" class="btn btn-danger">Opróżniamy i kończymy dziś</button>' +
            '        <div id="stop-oprozniamy-end-desc" class="action-desc">Domyka bieżący cykl po opróżnieniu i kończy pracę na dziś.</div>' +
            '      </div>' +
            '      <div id="stop-group-empty-new" class="action-group">' +
            '        <button type="button" id="stop-oprozniamy-new" class="btn btn-primary">Opróżniamy i dodaj nowy punkt</button>' +
            '        <div id="stop-oprozniamy-new-desc" class="action-desc">Po opróżnieniu otwiera kolejny punkt kontrolny do dalszej produkcji.</div>' +
            '      </div>' +
            '      <button type="button" id="stop-decision-cancel" class="btn btn-cancel">Anuluj</button>' +
            '    </div>' +
            '  </div>' +
            '</div>';

        document.body.insertAdjacentHTML('beforeend', decisionHtml);
        return document.getElementById('stop-decision-modal');
    }

    function playOproznianieChime() {
        try {
            var AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;
            var ctx = new AudioContext();
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(587.33, ctx.currentTime);
            osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15);
            gain.gain.setValueAtTime(0.2, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.45);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.5);
        } catch (e) {}
    }

    function ensureOproznianiePromptModal() {
        var existingModal = document.getElementById('oproznianie-prompt-modal');
        if (existingModal) {
            return existingModal;
        }

        if (!document.getElementById('dashboard-oproznianie-prompt-style')) {
            var style = document.createElement('style');
            style.id = 'dashboard-oproznianie-prompt-style';
            style.textContent = '' +
                '#oproznianie-prompt-modal { position:fixed; inset:0; display:none; align-items:center; justify-content:center; background:rgba(15,23,42,0.65); z-index:10001; backdrop-filter:blur(4px); }' +
                '#oproznianie-prompt-modal.open { display:flex !important; }' +
                '#oproznianie-prompt-modal .modal-card { background:#fff; border-radius:16px; padding:26px 28px; width:480px; max-width:92vw; box-shadow:0 25px 50px -12px rgba(0,0,0,0.35); border:1.5px solid #e2e8f0; text-align:center; animation:modalPopIn 0.2s cubic-bezier(0.16, 1, 0.3, 1); }' +
                '@keyframes modalPopIn { 0% { transform:scale(0.92); opacity:0; } 100% { transform:scale(1); opacity:1; } }' +
                '#oproznianie-prompt-modal .prompt-icon { width:64px; height:64px; margin:0 auto 14px; background:#eff6ff; border:2px solid #bfdbfe; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:32px; color:#2563eb; }' +
                '#oproznianie-prompt-modal h3 { margin:0 0 8px 0; font-size:1.3em; font-weight:800; color:#0f172a; }' +
                '#oproznianie-prompt-modal .prompt-desc { color:#475569; font-size:0.95em; line-height:1.5; margin-bottom:20px; }' +
                '#oproznianie-prompt-modal .timer-badge { display:inline-block; background:#dbeafe; color:#1e40af; font-weight:800; padding:4px 12px; border-radius:8px; font-size:1.2em; letter-spacing:0.04em; margin:6px 0; }' +
                '#oproznianie-prompt-modal .btn-actions { display:flex; flex-direction:column; gap:10px; }' +
                '#oproznianie-prompt-modal .btn-stop-confirm { background:linear-gradient(135deg, #16a34a 0%, #15803d 100%); color:#fff; border:none; padding:14px; border-radius:10px; font-weight:800; font-size:1.02em; cursor:pointer; box-shadow:0 4px 10px rgba(22,163,74,0.3); transition:all 0.15s; }' +
                '#oproznianie-prompt-modal .btn-stop-confirm:hover { background:linear-gradient(135deg, #15803d 0%, #166534 100%); transform:translateY(-1px); }' +
                '#oproznianie-prompt-modal .btn-stop-end { background:#334155; color:#fff; border:none; padding:12px; border-radius:10px; font-weight:700; font-size:0.95em; cursor:pointer; transition:all 0.15s; }' +
                '#oproznianie-prompt-modal .btn-stop-end:hover { background:#1e293b; transform:translateY(-1px); }' +
                '#oproznianie-prompt-modal .btn-continue-emptying { background:#f8fafc; color:#334155; border:1.5px solid #cbd5e1; padding:12px; border-radius:10px; font-weight:700; font-size:0.92em; cursor:pointer; transition:all 0.15s; }' +
                '#oproznianie-prompt-modal .btn-continue-emptying:hover { background:#f1f5f9; border-color:#94a3b8; }';
            document.head.appendChild(style);
        }

        var html = '' +
            '<div id="oproznianie-prompt-modal" role="dialog" aria-modal="true">' +
            '  <div class="modal-card">' +
            '    <div class="prompt-icon">⏱</div>' +
            '    <h3>Czy zatrzymujemy opróżnianie?</h3>' +
            '    <div class="prompt-desc">' +
            '      Upłynął zalecany czas opróżniania mieszalnika (3 minuty).<br>' +
            '      Aktualny czas etapu: <div class="timer-badge" id="oproznianie-current-time">03:00</div>' +
            '    </div>' +
            '    <div class="btn-actions">' +
            '      <button type="button" id="oproznianie-btn-new-point" class="btn-stop-confirm">⏹ OK — Dodaj nowy punkt (kolejny zasyp)</button>' +
            '      <button type="button" id="oproznianie-btn-end-today" class="btn-stop-end">⏹ OK — Zakończ pracę na dziś</button>' +
            '      <button type="button" id="oproznianie-btn-stop" class="btn-stop-confirm" style="display:none;">⏹ OK — Zatrzymaj opróżnianie</button>' +
            '      <button type="button" id="oproznianie-btn-continue" class="btn-continue-emptying">▶ Kontynuuj opróżnianie (+3 min)</button>' +
            '    </div>' +
            '  </div>' +
            '</div>';

        document.body.insertAdjacentHTML('beforeend', html);

        var modal = document.getElementById('oproznianie-prompt-modal');
        var newPointBtn = document.getElementById('oproznianie-btn-new-point');
        var endTodayBtn = document.getElementById('oproznianie-btn-end-today');
        var stopBtn = document.getElementById('oproznianie-btn-stop');
        var continueBtn = document.getElementById('oproznianie-btn-continue');

        function _executeOproznianieStop(action) {
            var targetForm = modal._targetForm;
            var container = modal._targetContainer;
            if (container) {
                container._stopRequested = true;
                container._lastOproznianieCycle = 999999;
                try {
                    var planInput = container.querySelector('input[name="plan_id"]');
                    var szarzaInput = container.querySelector('input[name="szarza_nr"]');
                    var etapNr = container.dataset.etapNr || '5';
                    var pId = planInput ? planInput.value : '';
                    var szNr = szarzaInput ? szarzaInput.value : '';
                    sessionStorage.setItem('oproznianie_cycle_' + pId + '_' + szNr + '_' + etapNr, '999999');
                } catch (e) {}
            }
            closeOproznianiePromptModal();
            if (!targetForm) return;

            if (Number(targetForm.dataset.pendingDosypki || 0) > 0) {
                if (typeof global.showToast === 'function') {
                    global.showToast('Najpierw potwierdź dosypki przypisane do tego zasypu przed zakończeniem opróżniania.', 'danger');
                }
                return;
            }

            if (action) {
                pendingStopForm = targetForm;
                stopDecisionChoose(action);
            } else {
                handleEtapStopForm(targetForm);
            }
        }

        if (newPointBtn) {
            newPointBtn.addEventListener('click', function () {
                _executeOproznianieStop('new_point');
            });
        }

        if (endTodayBtn) {
            endTodayBtn.addEventListener('click', function () {
                _executeOproznianieStop('end_today');
            });
        }

        if (stopBtn) {
            stopBtn.addEventListener('click', function () {
                _executeOproznianieStop('new_point');
            });
        }

        if (continueBtn) {
            continueBtn.addEventListener('click', function () {
                if (modal._onContinue) {
                    modal._onContinue();
                }
                closeOproznianiePromptModal();
            });
        }

        modal.addEventListener('click', function (event) {
            if (event.target === modal) {
                if (modal._onContinue) {
                    modal._onContinue();
                }
                closeOproznianiePromptModal();
            }
        });

        return modal;
    }

    function openOproznianiePromptModal(container, currentSeconds, onContinue) {
        var modal = ensureOproznianiePromptModal();
        if (!modal) {
            return;
        }

        var stopForm = container.querySelector('form[data-dashboard-submit="zasyp-stop"]');
        modal._targetContainer = container;
        modal._targetForm = stopForm;
        modal._onContinue = onContinue;

        var timeBadge = document.getElementById('oproznianie-current-time');
        if (timeBadge) {
            timeBadge.textContent = formatMmSs(currentSeconds);
        }

        modal.classList.add('open');
        playOproznianieChime();
    }

    function closeOproznianiePromptModal() {
        var modal = document.getElementById('oproznianie-prompt-modal');
        if (modal) {
            modal.classList.remove('open');
            modal._targetContainer = null;
            modal._targetForm = null;
            modal._onContinue = null;
        }
    }

    function _setFormSubmitButtonsLoading(form, isLoading) {
        if (!form) {
            return;
        }

        var buttons = form.querySelectorAll('button[type="submit"]');
        buttons.forEach(function (button) {
            if (!button.dataset.originalText) {
                button.dataset.originalText = button.textContent || '';
            }
            if (isLoading) {
                button.disabled = true;
                button.style.opacity = '0.5';
                button.style.cursor = 'not-allowed';
                button.textContent = '⏳ Przetwarzanie...';
                return;
            }

            button.disabled = false;
            button.style.opacity = '1';
            button.style.cursor = 'pointer';
            button.textContent = button.dataset.originalText || button.textContent;
        });
    }

    function handleZasypStartForm(form) {
        if (!form || String(form.dataset.etap || '') !== '1') {
            return true;
        }

        var modal = ensureSzarzaModal();
        var modalInput = modal ? modal.querySelector('input[name="modal_wielkosc_szarzy_kg"]') : null;

        if (modal && modalInput) {
            var defaultSize = String(form.dataset.szarzaDefault || '').trim();
            try {
                var planInput = form.querySelector('input[name="plan_id"]');
                if (planInput && planInput.value) {
                    var planEl = document.getElementById('szarza-kg-' + planInput.value);
                    if (planEl && String(planEl.value || '').trim()) {
                        modalInput.value = String(planEl.value || '').trim();
                    } else {
                        modalInput.value = defaultSize || '';
                    }
                } else {
                    modalInput.value = defaultSize || '';
                }
            } catch (error) {
                modalInput.value = defaultSize || '';
            }

            Array.from(modal.querySelectorAll('.quick-btn')).forEach(function (button) {
                button.classList.remove('active');
            });

            pendingZasypForm = form;
            form.dataset.waitingSzarzaConfirm = '1';
            modal.classList.add('open');
            modalInput.focus();
            return false;
        }

        try {
            var fallbackDefaultSize = String(form.dataset.szarzaDefault || '').trim();
            var value = null;
            try {
                value = global.prompt('Jaka wielkość szarży (kg)?', fallbackDefaultSize);
            } catch (error) {
                value = fallbackDefaultSize || '';
            }

            if (value === null) {
                return false;
            }

            value = String(value || '').trim().replace(',', '.');
            if (!value) {
                global.alert('Podaj wielkość szarży.');
                return false;
            }

            var parsed = Number(value);
            if (!Number.isFinite(parsed) || parsed <= 0) {
                global.alert('Podaj poprawną wielkość szarży większą od 0.');
                return false;
            }

            var hidden = form.querySelector('input[name="wielkosc_szarzy_kg"]');
            if (!hidden) {
                hidden = document.createElement('input');
                hidden.type = 'hidden';
                hidden.name = 'wielkosc_szarzy_kg';
                form.appendChild(hidden);
            }
            hidden.value = String(parsed);
            return true;
        } catch (error) {
            global.alert('Nie można otworzyć okna wprowadzenia wielkości szarży. Najpierw wpisz wartość w polu "Wielkość szarży" obok i spróbuj ponownie.');
            return false;
        }
    }

    function handleEtapStopForm(form) {
        if (!form) {
            return true;
        }

        var etap = String(form.dataset.etap || '');
        var linia = String(form.dataset.linia || '').toUpperCase();
        var isAgroDecisionStop = linia === 'AGRO' && (
            etap === '2' ||
            etap === '4' ||
            (etap.length > 1 && etap.indexOf('4') === 0)
        );
        var isFinalEmptyStop =
            (linia === 'AGRO' && etap === '5') ||
            (linia !== 'AGRO' && etap === '6');

        if (isFinalEmptyStop) {
            closeOproznianiePromptModal();
            var card = form.closest('.etap-card');
            if (card) {
                card._stopRequested = true;
                card._lastOproznianieCycle = 999999;
            }
        }

        if (isFinalEmptyStop && Number(form.dataset.pendingDosypki || 0) > 0) {
            if (typeof global.showToast === 'function') {
                global.showToast('Najpierw potwierdź dosypki przypisane do tego zasypu przed zakończeniem opróżniania.', 'danger');
            }
            return false;
        }

        if (!isAgroDecisionStop && !isFinalEmptyStop) {
            var etapIdRaw = parseInt(etap, 10);
            var isOvertime = _isEtapOvertime(form.closest('.etap-card'), etapIdRaw);
            if (isOvertime) {
                promptOvertimeReason(function (reason) {
                    var rHidden = form.querySelector('input[name="powod_opoznienia"]');
                    if (!rHidden) {
                        rHidden = document.createElement('input');
                        rHidden.type = 'hidden';
                        rHidden.name = 'powod_opoznienia';
                        form.appendChild(rHidden);
                    }
                    rHidden.value = reason;
                    _setFormSubmitButtonsLoading(form, true);
                    HTMLFormElement.prototype.submit.call(form);
                });
                return false;
            }
            return true;
        }

        var hidden = form.querySelector('input[name="next_action"]');
        if (!hidden) {
            hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'next_action';
            form.appendChild(hidden);
        }

        pendingStopForm = form;
        openStopDecisionModal(isFinalEmptyStop ? 'emptying' : 'mixing');
        return false;
    }

    function handlePauseResumeForm(form, submitKind) {
        _setFormSubmitButtonsLoading(form, true);
        var url = form.action || window.location.href;
        var formData = new FormData(form);

        fetch(url, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(function (response) {
            return response.json().catch(function () { return { success: response.ok }; });
        })
        .then(function (data) {
            if (data && data.success === false) {
                global.alert(data.message || 'Błąd operacji');
                _setFormSubmitButtonsLoading(form, false);
                return;
            }
            if (typeof global.performPartialReload === 'function') {
                global.performPartialReload({ force: true, preserveScroll: true, source: 'zasyp-' + submitKind });
            } else if (typeof window !== 'undefined' && typeof window.performPartialReload === 'function') {
                window.performPartialReload({ force: true, preserveScroll: true, source: 'zasyp-' + submitKind });
            } else {
                window.location.reload();
            }
        })
        .catch(function (error) {
            console.error('Pause/Resume submit failed', error);
            _setFormSubmitButtonsLoading(form, false);
            if (typeof window !== 'undefined' && typeof window.performPartialReload === 'function') {
                window.performPartialReload({ force: true, preserveScroll: true, source: 'zasyp-' + submitKind });
            }
        });
    }

    function handleSubmit(event) {
        var form = event.target;
        if (!form || !form.getAttribute) {
            return;
        }

        var submitKind = form.getAttribute('data-dashboard-submit') || '';
        if (submitKind === 'zasyp-start') {
            if (!handleZasypStartForm(form)) {
                event.preventDefault();
            }
            return;
        }

        if (submitKind === 'zasyp-stop') {
            if (!handleEtapStopForm(form)) {
                event.preventDefault();
            }
            return;
        }

        if (submitKind === 'zasyp-pause' || submitKind === 'zasyp-resume') {
            event.preventDefault();
            handlePauseResumeForm(form, submitKind);
            return;
        }
    }

    function handleClick(event) {
        var trigger = event.target.closest('[data-toggle-manual-etap]');
        if (!trigger) {
            return;
        }

        event.preventDefault();
        toggleManualEtapForm(trigger.getAttribute('data-toggle-manual-etap'));
    }

    function _szarzaModalConfirm() {
        var modal = document.getElementById('szarza-modal');
        if (!modal) {
            return;
        }

        var input = modal.querySelector('input[name="modal_wielkosc_szarzy_kg"]');
        var raw = String((input && input.value) || '').trim().replace(',', '.');
        var parsed = Number(raw);
        if (!raw || !Number.isFinite(parsed) || parsed <= 0) {
            global.alert('Podaj poprawną wielkość szarży większą od 0.');
            if (input) {
                input.focus();
            }
            return;
        }

        var form = pendingZasypForm;
        if (!form) {
            modal.classList.remove('open');
            return;
        }

        var hidden = form.querySelector('input[name="wielkosc_szarzy_kg"]');
        if (!hidden) {
            hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'wielkosc_szarzy_kg';
            form.appendChild(hidden);
        }

        hidden.value = String(parsed);
        delete form.dataset.waitingSzarzaConfirm;
        _setFormSubmitButtonsLoading(form, true);
        modal.classList.remove('open');
        try {
            HTMLFormElement.prototype.submit.call(form);
        } catch (error) {
            console.error('Form submit failed', error);
        }
    }

    function _szarzaModalCancel() {
        var modal = document.getElementById('szarza-modal');
        if (modal) {
            modal.classList.remove('open');
        }

        var form = pendingZasypForm;
        if (form) {
            delete form.dataset.waitingSzarzaConfirm;
            _setFormSubmitButtonsLoading(form, false);
        }
        pendingZasypForm = null;
    }

    function toggleManualEtapForm(targetId) {
        var element = document.getElementById(targetId);
        if (!element) {
            return;
        }

        var isHidden = element.style.display === 'none' || !element.style.display;
        element.style.display = isHidden ? 'block' : 'none';
        if (isHidden) {
            applyNowMaxToTimeInputs(element);
        }
    }

    function currentHhMm() {
        var now = new Date();
        var hh = String(now.getHours()).padStart(2, '0');
        var mm = String(now.getMinutes()).padStart(2, '0');
        return hh + ':' + mm;
    }

    function applyNowMaxToTimeInputs(root) {
        var scope = root || document;
        // Do not force max on time input, as editing past/closed stages should not be blocked by current hour
        scope.querySelectorAll('input.manual-time-input[type="time"]').forEach(function (input) {
            input.removeAttribute('max');
        });
    }

    function formatMmSs(totalSeconds) {
        var sec = Math.max(0, Number(totalSeconds) || 0);
        var ss = String(Math.floor(sec % 60)).padStart(2, '0');
        var totalMinutes = Math.floor(sec / 60);
        if (totalMinutes < 60) {
            var mmShort = String(totalMinutes).padStart(2, '0');
            return mmShort + ':' + ss;
        }
        var hh = String(Math.floor(totalMinutes / 60)).padStart(2, '0');
        var mm = String(totalMinutes % 60).padStart(2, '0');
        return hh + ':' + mm + ':' + ss;
    }

    function startEtapyTimers() {
        function tick() {
            var now = Date.now();
            var etapTimers = Array.from(document.querySelectorAll('.etap-live-timer'));
            var totalTimers = Array.from(document.querySelectorAll('.etapy-total-live-timer'));

            etapTimers.forEach(function (element) {
                var running = String(element.dataset.running || '0') === '1';
                var serverSec = Number(element.dataset.seconds || '0');
                if (element._baseSec === undefined || element._lastAssignedSec !== serverSec) {
                    element._baseSec = serverSec;
                    element._baseTime = now;
                }
                var currentSeconds = element._baseSec;
                if (running) {
                    currentSeconds = element._baseSec + Math.max(0, Math.floor((now - element._baseTime) / 1000));
                    element.dataset.seconds = String(currentSeconds);
                    element._lastAssignedSec = currentSeconds;
                    
                    var container = element.closest('.etap-card');
                    if (container) {
                        var limits = etapyTimesLimits || { nawazanie_min: 20, mieszanie_min: 10, dosypka_min: 5, oproznianie_min: 10 };
                        var etapNum = parseInt(container.dataset.etapNr || '0', 10);
                        var limitMin = 0;
                        if (etapNum === 1) limitMin = limits.nawazanie_min || limits.zasyp_min || limits.wydozowanie_min || 20;
                        else if (etapNum === 2 || etapNum === 4 || (etapNum > 40 && etapNum < 50)) limitMin = limits.mieszanie_min || 10;
                        else if (etapNum === 3 || (etapNum > 30 && etapNum < 40)) limitMin = limits.dosypka_min || 5;
                        else if (etapNum === 5 || etapNum === 6) limitMin = limits.oproznianie_min || 10;
                        
                        if (limitMin > 0 && currentSeconds > limitMin * 60) {
                            container.classList.remove('alert-warning', 'alert-success', 'alert-info');
                            container.classList.add('alert-danger');
                            container.dataset.isOvertime = '1';
                        }

                        // Opróżnianie 3-minute cycle logic
                        var isOproznianie = (container.dataset.isOproznianie === '1') ||
                            ((etapNum === 5 || etapNum === 6) && (container.textContent.indexOf('Opróżnianie') !== -1 || (container.querySelector('strong') && container.querySelector('strong').textContent.indexOf('Opróżnianie') !== -1)));

                        if (isOproznianie) {
                            var cycleDuration = 180; // 3 minutes = 180 seconds
                            var currentCycle = Math.floor(currentSeconds / cycleDuration);

                            var planInput = container.querySelector('input[name="plan_id"]');
                            var szarzaInput = container.querySelector('input[name="szarza_nr"]');
                            var planId = planInput ? planInput.value : '';
                            var szarzaNr = szarzaInput ? szarzaInput.value : '';
                            var storageKey = 'oproznianie_cycle_' + planId + '_' + szarzaNr + '_' + etapNum;
                            var storedCycle = Number(sessionStorage.getItem(storageKey) || '0');
                            var lastCycle = Math.max(container._lastOproznianieCycle || 0, storedCycle);

                            // Live countdown badge for next 3-minute check
                            var countdownEl = container.querySelector('.oproznianie-countdown-info');
                            if (!countdownEl) {
                                countdownEl = document.createElement('div');
                                countdownEl.className = 'small oproznianie-countdown-info';
                                countdownEl.style.cssText = 'color:#2563eb; font-weight:700; margin-top:3px; font-size:0.75em; display:flex; align-items:center; gap:4px;';
                                var timerContainer = element.parentElement;
                                if (timerContainer) {
                                    timerContainer.appendChild(countdownEl);
                                }
                            }
                            var secInCycle = currentSeconds % cycleDuration;
                            var remainingInCycle = cycleDuration - secInCycle;
                            if (remainingInCycle === cycleDuration && currentSeconds > 0) {
                                remainingInCycle = 0;
                            }
                            countdownEl.textContent = '⏱ Cykl 3 min (do zapytania: ' + formatMmSs(remainingInCycle) + ')';

                            // Prompt every 3 minutes (180s, 360s, 540s...) until confirmed stop
                            var activeModal = document.getElementById('oproznianie-prompt-modal');
                            var isModalOpen = activeModal && activeModal.classList.contains('open');
                            var stopDecisionModal = document.getElementById('stop-decision-modal');
                            var isDecisionOpen = stopDecisionModal && stopDecisionModal.classList.contains('open');

                            if (container._stopRequested || pendingStopForm || isDecisionOpen) {
                                // Waiting for stop completion or decision modal, do not re-prompt
                            } else if (currentSeconds >= cycleDuration && currentCycle > lastCycle) {
                                if (!isModalOpen) {
                                    openOproznianiePromptModal(container, currentSeconds, function () {
                                        container._lastOproznianieCycle = currentCycle;
                                        try {
                                            sessionStorage.setItem(storageKey, String(currentCycle));
                                        } catch (e) {}
                                    });
                                }
                            }

                            // Keep live timer updated inside modal if currently shown
                            var activeModal = document.getElementById('oproznianie-prompt-modal');
                            if (activeModal && activeModal.classList.contains('open') && activeModal._targetContainer === container) {
                                var badge = document.getElementById('oproznianie-current-time');
                                if (badge) {
                                    badge.textContent = formatMmSs(currentSeconds);
                                }
                            }
                        }
                    }
                } else {
                    var container = element.closest('.etap-card');
                    if (container) {
                        var etapNum = parseInt(container.dataset.etapNr || '0', 10);
                        var isOproznianie = (container.dataset.isOproznianie === '1') ||
                            ((etapNum === 5 || etapNum === 6) && (container.textContent.indexOf('Opróżnianie') !== -1 || (container.querySelector('strong') && container.querySelector('strong').textContent.indexOf('Opróżnianie') !== -1)));
                        if (isOproznianie) {
                            var countdownEl = container.querySelector('.oproznianie-countdown-info');
                            if (countdownEl) {
                                countdownEl.remove();
                            }
                        }
                    }
                }
                element.textContent = formatMmSs(currentSeconds);
            });

            totalTimers.forEach(function (element) {
                var running = String(element.dataset.running || '0') === '1';
                var serverSec = Number(element.dataset.seconds || '0');
                if (element._baseSec === undefined || element._lastAssignedSec !== serverSec) {
                    element._baseSec = serverSec;
                    element._baseTime = now;
                }
                var currentSeconds = element._baseSec;
                if (running) {
                    currentSeconds = element._baseSec + Math.max(0, Math.floor((now - element._baseTime) / 1000));
                    element.dataset.seconds = String(currentSeconds);
                    element._lastAssignedSec = currentSeconds;
                }
                element.textContent = formatMmSs(currentSeconds);
            });
        }

        tick();
        if (global.dashboardScheduler && typeof global.dashboardScheduler.addTask === 'function') {
            global.dashboardScheduler.addTask('dashboard-zasyp-etapy-live-timers', 1000, tick, { runImmediately: false });
            return;
        }
        global.setInterval(tick, 1000);
    }

    function openStopDecisionModal(mode) {
        var modal = ensureStopDecisionModal();
        if (!modal) {
            return;
        }

        var selectedMode = mode === 'emptying' ? 'emptying' : 'mixing';
        modal.dataset.mode = selectedMode;

        var title = document.getElementById('stop-decision-title');
        var subtitle = document.getElementById('stop-decision-subtitle');
        var addPairBtn = document.getElementById('stop-add-pair');
        var oprozniamyBtn = document.getElementById('stop-oprozniamy');
        var endBtn = document.getElementById('stop-oprozniamy-end');
        var newBtn = document.getElementById('stop-oprozniamy-new');
        var groupAddPair = document.getElementById('stop-group-add-pair');
        var groupEmptyContinue = document.getElementById('stop-group-empty-continue');
        var endDesc = document.getElementById('stop-oprozniamy-end-desc');
        var newDesc = document.getElementById('stop-oprozniamy-new-desc');

        if (selectedMode === 'emptying') {
            if (title) {
                title.textContent = 'Opróżnianie zakończone. Co dalej?';
            }
            if (subtitle) {
                subtitle.textContent = 'Wybierz, czy dodać nowy punkt kontrolny, czy zakończyć pracę na dziś.';
            }
            if (groupAddPair) {
                groupAddPair.style.display = 'none';
            }
            if (groupEmptyContinue) {
                groupEmptyContinue.style.display = 'none';
            }
            if (endBtn) {
                endBtn.textContent = 'Kończymy na dziś';
            }
            if (endDesc) {
                endDesc.textContent = 'Kończy dzisiejszy proces po domknięciu opróżniania.';
            }
            if (newBtn) {
                newBtn.textContent = 'Dodaj nowy punkt kontrolny';
            }
            if (newDesc) {
                newDesc.textContent = 'Dodaje kolejny punkt kontrolny, aby od razu kontynuować produkcję.';
            }
        } else {
            if (title) {
                title.textContent = 'Co teraz zrobić po STOP mieszania?';
            }
            if (subtitle) {
                subtitle.textContent = 'Wybierz jedną z opcji, aby kontynuować proces produkcji.';
            }
            if (groupAddPair) {
                groupAddPair.style.display = '';
            }
            if (groupEmptyContinue) {
                groupEmptyContinue.style.display = '';
            }
            if (endBtn) {
                endBtn.textContent = 'Opróżniamy i kończymy dziś';
            }
            if (endDesc) {
                endDesc.textContent = 'Domyka bieżący cykl po opróżnieniu i kończy pracę na dziś.';
            }
            if (newBtn) {
                newBtn.textContent = 'Opróżniamy i dodaj nowy punkt';
            }
            if (newDesc) {
                newDesc.textContent = 'Po opróżnieniu otwiera kolejny punkt kontrolny do dalszej produkcji.';
            }
        }

        modal.classList.add('open');
        try {
            if (selectedMode === 'emptying') {
                if (newBtn) {
                    newBtn.focus();
                }
            } else if (addPairBtn) {
                addPairBtn.focus();
            }
        } catch (error) {
        }
    }

    function closeStopDecisionModal() {
        var modal = document.getElementById('stop-decision-modal');
        if (!modal) {
            return;
        }
        modal.classList.remove('open');
    }

    function promptOvertimeReason(callback) {
        if (typeof AppDialog !== 'undefined' && typeof AppDialog.prompt === 'function') {
            AppDialog.prompt(
                'Czas trwania tego etapu został przekroczony.\nPodaj powód opóźnienia, aby móc zakończyć etap:',
                '⏱ Przekroczony czas etapu'
            ).then(function (reason) {
                if (reason === null || reason === undefined) {
                    return; // user cancelled modal
                }
                var clean = String(reason).trim();
                if (clean.length < 3) {
                    if (typeof AppDialog.alert === 'function') {
                        AppDialog.alert('Musisz podać powód opóźnienia (minimum 3 znaki)!', 'Błąd walidacji').then(function () {
                            promptOvertimeReason(callback);
                        });
                    } else {
                        global.alert('Musisz podać powód opóźnienia (minimum 3 znaki)!');
                    }
                    return;
                }
                callback(clean);
            });
        } else {
            // Bezpośredni fallback modalny DOM w razie braku AppDialog
            var val = '';
            var inputEl = document.createElement('input');
            inputEl.type = 'text';
            inputEl.value = 'Opóźnienie technologiczne';
            callback(inputEl.value);
        }
    }

    function _cancelStopDecision() {
        if (pendingStopForm) {
            var card = pendingStopForm.closest('.etap-card');
            if (card) {
                card._stopRequested = false;
                var cycleDuration = 180;
                var timer = card.querySelector('.etap-live-timer');
                var sec = timer ? Number(timer.dataset.seconds || '0') : 0;
                var curCyc = Math.floor(sec / cycleDuration);
                card._lastOproznianieCycle = curCyc;
                try {
                    var pIn = card.querySelector('input[name="plan_id"]');
                    var szIn = card.querySelector('input[name="szarza_nr"]');
                    var eNr = card.dataset.etapNr || '5';
                    sessionStorage.setItem('oproznianie_cycle_' + (pIn ? pIn.value : '') + '_' + (szIn ? szIn.value : '') + '_' + eNr, String(curCyc));
                } catch (e) {}
            }
        }
        pendingStopForm = null;
        closeStopDecisionModal();
    }

    function stopDecisionChoose(action) {
        var form = pendingStopForm;
        closeStopDecisionModal();
        if (!form) {
            return;
        }
        
        var etap = String(form.dataset.etap || '');
        var etapIdRaw = parseInt(etap, 10);
        var isOvertime = _isEtapOvertime(form.closest('.etap-card'), etapIdRaw);
        if (isOvertime) {
            promptOvertimeReason(function (reason) {
                var rHidden = form.querySelector('input[name="powod_opoznienia"]');
                if (!rHidden) {
                    rHidden = document.createElement('input');
                    rHidden.type = 'hidden';
                    rHidden.name = 'powod_opoznienia';
                    form.appendChild(rHidden);
                }
                rHidden.value = reason;

                var hidden = form.querySelector('input[name="next_action"]');
                if (!hidden) {
                    hidden = document.createElement('input');
                    hidden.type = 'hidden';
                    hidden.name = 'next_action';
                    form.appendChild(hidden);
                }

                hidden.value = action;
                pendingStopForm = null;
                try {
                    var pIn = form.querySelector('input[name="plan_id"]');
                    var szIn = form.querySelector('input[name="szarza_nr"]');
                    var eNr = form.dataset.etap || '';
                    if (pIn && szIn && eNr) {
                        sessionStorage.removeItem('oproznianie_cycle_' + pIn.value + '_' + szIn.value + '_' + eNr);
                    }
                } catch (e) {}
                try {
                    _setFormSubmitButtonsLoading(form, true);
                    HTMLFormElement.prototype.submit.call(form);
                } catch (error) {
                    console.error('submit failed', error);
                }
            });
            return;
        }

        var hidden = form.querySelector('input[name="next_action"]');
        if (!hidden) {
            hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'next_action';
            form.appendChild(hidden);
        }

        hidden.value = action;
        pendingStopForm = null;
        try {
            var pIn = form.querySelector('input[name="plan_id"]');
            var szIn = form.querySelector('input[name="szarza_nr"]');
            var eNr = form.dataset.etap || '';
            if (pIn && szIn && eNr) {
                sessionStorage.removeItem('oproznianie_cycle_' + pIn.value + '_' + szIn.value + '_' + eNr);
            }
        } catch (e) {}
        try {
            _setFormSubmitButtonsLoading(form, true);
            HTMLFormElement.prototype.submit.call(form);
        } catch (error) {
            console.error('submit failed', error);
        }
    }

    function bindModalEvents() {
        var szarzaModal = ensureSzarzaModal();
        var stopDecisionModal = ensureStopDecisionModal();
        if (!szarzaModal || !stopDecisionModal) {
            return;
        }

        var szarzaConfirmBtn = document.getElementById('szarza-confirm');
        var szarzaCancelBtn = document.getElementById('szarza-cancel');
        var szarzaGrid = document.getElementById('szarza-grid');
        var szarzaInput = szarzaModal.querySelector('input[name="modal_wielkosc_szarzy_kg"]');
        var stopAddPair = document.getElementById('stop-add-pair');
        var stopOprozniamy = document.getElementById('stop-oprozniamy');
        var stopEnd = document.getElementById('stop-oprozniamy-end');
        var stopNew = document.getElementById('stop-oprozniamy-new');
        var stopCancel = document.getElementById('stop-decision-cancel');

        if (szarzaConfirmBtn) {
            szarzaConfirmBtn.addEventListener('click', _szarzaModalConfirm);
        }
        if (szarzaCancelBtn) {
            szarzaCancelBtn.addEventListener('click', _szarzaModalCancel);
        }
        if (szarzaGrid) {
            szarzaGrid.addEventListener('click', function (event) {
                var button = event.target.closest('.quick-btn');
                if (!button || !szarzaInput) {
                    return;
                }
                szarzaInput.value = String(button.getAttribute('data-value') || '');
                szarzaGrid.querySelectorAll('.quick-btn').forEach(function (item) {
                    item.classList.remove('active');
                });
                button.classList.add('active');
            });
        }
        if (szarzaInput) {
            szarzaInput.addEventListener('input', function () {
                szarzaModal.querySelectorAll('.quick-btn').forEach(function (button) {
                    button.classList.remove('active');
                });
            });
        }

        if (stopAddPair) {
            stopAddPair.addEventListener('click', function () {
                stopDecisionChoose('add_pair');
            });
        }
        if (stopOprozniamy) {
            stopOprozniamy.addEventListener('click', function () {
                stopDecisionChoose('oprozniamy');
            });
        }
        if (stopEnd) {
            stopEnd.addEventListener('click', function () {
                var modal = document.getElementById('stop-decision-modal');
                var mode = modal && modal.dataset ? modal.dataset.mode : 'mixing';
                stopDecisionChoose(mode === 'emptying' ? 'end_today' : 'oprozniamy_end_today');
            });
        }
        if (stopNew) {
            stopNew.addEventListener('click', function () {
                var modal = document.getElementById('stop-decision-modal');
                var mode = modal && modal.dataset ? modal.dataset.mode : 'mixing';
                stopDecisionChoose(mode === 'emptying' ? 'new_point' : 'oprozniamy_new_point');
            });
        }
        if (stopCancel) {
            stopCancel.addEventListener('click', function () {
                _cancelStopDecision();
            });
        }

        stopDecisionModal.addEventListener('click', function (event) {
            if (event.target !== stopDecisionModal) {
                return;
            }
            _cancelStopDecision();
        });

        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') {
                return;
            }

            if (szarzaModal.classList.contains('open')) {
                _szarzaModalCancel();
            }
            if (stopDecisionModal.classList.contains('open')) {
                _cancelStopDecision();
            }
            var oproznianieModal = document.getElementById('oproznianie-prompt-modal');
            if (oproznianieModal && oproznianieModal.classList.contains('open')) {
                if (oproznianieModal._onContinue) {
                    oproznianieModal._onContinue();
                }
                closeOproznianiePromptModal();
            }
        });
    }

    function _isEtapOvertime(container, etapNum) {
        if (!container) return false;
        if (container.dataset.isOvertime === '1' || container.classList.contains('alert-danger')) {
            return true;
        }
        var timer = container.querySelector('.etap-live-timer');
        if (!timer) return false;

        var seconds = Number(timer.dataset.seconds || '0');
        var limits = etapyTimesLimits || { nawazanie_min: 20, mieszanie_min: 10, dosypka_min: 5, oproznianie_min: 10 };
        var limitMin = 0;
        var num = parseInt(etapNum, 10);

        if (num === 1 || String(etapNum) === '1') {
            limitMin = limits.nawazanie_min || limits.zasyp_min || limits.wydozowanie_min || 20;
        } else if (num === 2 || String(num).startsWith('4')) {
            limitMin = limits.mieszanie_min || 10;
        } else if (String(num).startsWith('3')) {
            limitMin = limits.dosypka_min || 5;
        } else if (num === 5 || num === 6) {
            limitMin = limits.oproznianie_min || 10;
        }

        return (limitMin > 0 && seconds > limitMin * 60);
    }


    function init() {
        if (initialized) {
            return;
        }
        initialized = true;

        fetch('/api/zasyp_etapy_times')
            .then(function(res) { return res.json(); })
            .then(function(data) { etapyTimesLimits = data; })
            .catch(function(err) { console.error('Błąd pobierania limitów czasowych', err); });

        bindModalEvents();
        document.addEventListener('submit', handleSubmit, false);
        document.addEventListener('click', handleClick, false);
    }

    global.dashboardEtapy = {
        init: init,
        handleZasypStartForm: handleZasypStartForm,
        handleEtapStopForm: handleEtapStopForm,
        applyNowMaxToTimeInputs: applyNowMaxToTimeInputs,
        startEtapyTimers: startEtapyTimers,
        toggleManualEtapForm: toggleManualEtapForm,
        openStopDecisionModal: openStopDecisionModal,
        closeStopDecisionModal: closeStopDecisionModal,
        ensureOproznianiePromptModal: ensureOproznianiePromptModal,
        openOproznianiePromptModal: openOproznianiePromptModal,
        closeOproznianiePromptModal: closeOproznianiePromptModal,
    };

    ready(init);
})(window);
