(function (global) {
    'use strict';

    if (global.dashboardEtapy) {
        return;
    }

    var initialized = false;
    var pendingZasypForm = null;
    var pendingStopForm = null;
    var szarzaValues = [1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000];

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
                '#stop-decision-modal.open { display:flex; }' +
                '#stop-decision-modal .card { background:#fff; border-radius:12px; padding:18px; width:560px; max-width:92vw; box-shadow:0 15px 35px rgba(0,0,0,0.25); border:1px solid #e6eef2; }' +
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

        if (!isAgroDecisionStop && !isFinalEmptyStop) {
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

        if (submitKind === 'zasyp-stop' && !handleEtapStopForm(form)) {
            event.preventDefault();
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
        var maxVal = currentHhMm();
        scope.querySelectorAll('input.manual-time-input[type="time"]').forEach(function (input) {
            input.max = maxVal;
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
        var etapTimers = Array.from(document.querySelectorAll('.etap-live-timer'));
        var totalTimers = Array.from(document.querySelectorAll('.etapy-total-live-timer'));
        if (!etapTimers.length && !totalTimers.length) {
            return;
        }

        function tick() {
            etapTimers.forEach(function (element) {
                var running = String(element.dataset.running || '0') === '1';
                var seconds = Number(element.dataset.seconds || '0');
                if (running) {
                    seconds += 1;
                    element.dataset.seconds = String(seconds);
                }
                element.textContent = formatMmSs(seconds);
            });

            totalTimers.forEach(function (element) {
                var running = String(element.dataset.running || '0') === '1';
                var seconds = Number(element.dataset.seconds || '0');
                if (running) {
                    seconds += 1;
                    element.dataset.seconds = String(seconds);
                }
                element.textContent = formatMmSs(seconds);
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

    function stopDecisionChoose(action) {
        var form = pendingStopForm;
        closeStopDecisionModal();
        if (!form) {
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
                pendingStopForm = null;
                closeStopDecisionModal();
            });
        }

        stopDecisionModal.addEventListener('click', function (event) {
            if (event.target !== stopDecisionModal) {
                return;
            }
            pendingStopForm = null;
            closeStopDecisionModal();
        });

        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') {
                return;
            }

            if (szarzaModal.classList.contains('open')) {
                _szarzaModalCancel();
            }
            if (stopDecisionModal.classList.contains('open')) {
                pendingStopForm = null;
                closeStopDecisionModal();
            }
        });
    }

    function init() {
        if (initialized) {
            return;
        }
        initialized = true;

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
    };

    ready(init);
})(window);