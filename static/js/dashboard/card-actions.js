(function (global) {
    'use strict';

    var initialized = false;

    function notify(message, type) {
        if (global.dashboardToasts && typeof global.dashboardToasts.notify === 'function') {
            global.dashboardToasts.notify(message, type);
            return;
        }
        if (typeof global.showToast === 'function') {
            global.showToast(message, type);
            return;
        }
        if (type === 'error' || type === 'danger') {
            console.error(message);
            return;
        }
        console.log(message);
    }

    function confirmAction(element) {
        if (!element) {
            return true;
        }

        var message = element.getAttribute('data-confirm');
        if (!message) {
            return true;
        }

        return global.confirm(message);
    }

    function debugLog() {
        if (!global.__RP_DEBUG__) {
            return;
        }
        console.log.apply(console, arguments);
    }

    function parseJsonResponse(response) {
        return response.text().then(function (text) {
            try {
                return {
                    ok: response.ok,
                    status: response.status,
                    data: text ? JSON.parse(text) : {},
                };
            } catch (error) {
                return {
                    ok: false,
                    status: response.status,
                    data: {
                        success: false,
                        message: 'Błąd parsowania JSON: ' + error.message,
                    },
                };
            }
        });
    }

    function roleAssignmentMessage(actionLabel) {
        var action = actionLabel || 'tej operacji';
        return 'Brak uprawnien do ' + action + '. To wynika z przydzialu rol. Skontaktuj sie z liderem lub administratorem.';
    }

    function resolveRequestMessage(result, actionLabel, fallbackMessage) {
        var status = result ? result.status : 0;
        var payload = (result && result.data) ? result.data : {};
        var apiMessage = payload.message || payload.error || '';

        if (status === 401 || payload.error === 'unauthenticated') {
            return 'Sesja wygasla. Zaloguj sie ponownie.';
        }

        if (status === 403 || payload.error === 'forbidden') {
            return roleAssignmentMessage(actionLabel);
        }

        if (apiMessage) {
            return apiMessage;
        }

        return fallbackMessage;
    }

    function resolveCurrentPlanDate() {
        var isoInput = document.getElementById('current-date-iso');
        if (isoInput && isoInput.value) {
            return isoInput.value;
        }

        try {
            var params = new URLSearchParams(global.location.search);
            if (params.has('data')) {
                return params.get('data');
            }
        } catch (error) {
        }

        return '';
    }

    function getDashboardContext() {
        var config = document.getElementById('dashboard-config');
        if (!config) {
            return { sekcja: '', linia: '' };
        }

        return {
            sekcja: String(config.getAttribute('data-sekcja') || '').trim(),
            linia: String(config.getAttribute('data-linia') || '').trim().toUpperCase(),
        };
    }

    function isAgroWorkowanieContext() {
        var context = getDashboardContext();
        return context.sekcja === 'Workowanie' && context.linia === 'AGRO';
    }

    function scrollToProductionSection() {
        var target = document.getElementById('dashboard-production-section');
        if (!target) {
            return;
        }

        try {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (error) {
            try {
                target.scrollIntoView(true);
            } catch (fallbackError) {
            }
        }
    }

    function submitWniosekForm(form, event) {
        event.preventDefault();

        var url = form.getAttribute('action');
        var row = form.closest('tr');
        var button = form.querySelector('.wn-btn');
        if (button) {
            button.disabled = true;
        }

        fetch(url, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams(),
        })
            .then(function (response) {
                try {
                    return response.json();
                } catch (error) {
                    return {};
                }
            })
            .then(function (payload) {
                if (payload && payload.success) {
                    if (row) {
                        row.remove();
                    }
                    notify(payload.message || 'Wniosek przetworzony', 'success');
                    return;
                }
                notify((payload && payload.message) ? payload.message : 'Błąd', 'danger');
                if (button) {
                    button.disabled = false;
                }
            })
            .catch(function (error) {
                console.error(error);
                notify('Błąd sieci', 'danger');
                if (button) {
                    button.disabled = false;
                }
            });
    }

    function submitConfirmPaletaForm(form, event) {
        event.preventDefault();
        debugLog('[dashboard.actions] confirm-paleta-form submit intercepted');

        var button = form.querySelector('button[type="submit"]');
        if (button) {
            button.disabled = true;
        }

        var attempts = 0;
        var maxAttempts = 3;

        function doFetch() {
            attempts += 1;
            fetch(form.action, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then(function (response) {
                    if (response.ok) {
                        notify('Potwierdzono paletę', 'success');
                        var item = form.closest('li');
                        if (item) {
                            item.remove();
                        }
                        global.setTimeout(function () {
                            global.location.href = global.location.href;
                        }, 300);
                        return;
                    }

                    if (attempts < maxAttempts) {
                        global.setTimeout(doFetch, 300 * Math.pow(2, attempts - 1));
                        return;
                    }

                    notify('Błąd potwierdzenia (server)', 'error');
                    if (button) {
                        button.disabled = false;
                    }
                })
                .catch(function () {
                    if (attempts < maxAttempts) {
                        global.setTimeout(doFetch, 300 * Math.pow(2, attempts - 1));
                        return;
                    }

                    notify('Błąd sieci podczas potwierdzania', 'error');
                    if (button) {
                        button.disabled = false;
                    }
                });
        }

        doFetch();
    }

    function submitDodajPaleteForm(form, event) {
        event.preventDefault();

        var submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.classList.add('btn-disabled');
        }

        var overlays = Array.from(document.querySelectorAll('[id^="stop-"]'));
        overlays.forEach(function (element) {
            element.dataset._savedPe = element.style.pointerEvents || '';
            element.style.pointerEvents = 'none';
        });

        var restored = false;
        function restoreOverlays() {
            if (restored) {
                return;
            }
            restored = true;
            overlays.forEach(function (element) {
                if (element.dataset._savedPe !== undefined) {
                    element.style.pointerEvents = element.dataset._savedPe;
                    delete element.dataset._savedPe;
                    return;
                }
                element.style.pointerEvents = '';
            });
        }

        var timeoutId = global.setTimeout(restoreOverlays, 3000);
        global.sessionStorage.setItem('skip_open_stop', '1');

        fetch(form.getAttribute('action'), {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
        })
            .then(function (response) {
                global.clearTimeout(timeoutId);
                restoreOverlays();

                if (!response.ok) {
                    return response.text().then(function (errorText) {
                        notify(errorText || ('Błąd ' + response.status + ': Nie udało się dodać przedmiotu'), 'error');
                        if (submitButton) {
                            submitButton.disabled = false;
                            submitButton.classList.remove('btn-disabled');
                        }
                    });
                }

                if (isAgroWorkowanieContext() && typeof global.performPartialReload === 'function') {
                    try {
                        if (typeof global.closeQuickPopup === 'function') {
                            global.closeQuickPopup();
                        }
                    } catch (popupError) {
                    }

                    return global.performPartialReload({ force: true, preserveScroll: true, source: 'add-pallet-workowanie-agro' })
                        .then(function () {
                            global.setTimeout(scrollToProductionSection, 140);
                        })
                        .catch(function (reloadError) {
                            console.error('Silent partial reload failed after add pallet', reloadError);
                            global.location.reload();
                        });
                }

                if (response.redirected) {
                    global.location.href = response.url;
                    return;
                }

                global.location.href = global.location.href;
            })
            .catch(function (error) {
                global.clearTimeout(timeoutId);
                restoreOverlays();
                console.error('AJAX dodaj_palete failed, falling back to normal submit', error);
                notify('Błąd sieci: ' + error.message, 'error');
                form.submit();
            });
    }

    function editPalet(id, waga) {
        var newWaga = global.prompt('Nowa waga (kg):', waga);
        if (!newWaga || newWaga === waga) {
            return;
        }

        var config = document.getElementById('dashboard-config');
        var linia = config ? config.getAttribute('data-linia') : 'PSD';

        fetch('/api/edytuj_palete_ajax', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: id,
                waga: newWaga,
                linia: linia,
                data_planu: resolveCurrentPlanDate(),
            }),
        })
            .then(parseJsonResponse)
            .then(function (result) {
                var payload = result.data;
                if (result.ok && payload && payload.success) {
                    global.location.reload();
                    return;
                }
                global.alert(resolveRequestMessage(result, 'edycji palety', 'Nie udalo sie edytowac palety.'));
            })
            .catch(function (error) {
                global.alert('Blad polaczenia: ' + error.message);
            });
    }

    function deletePalet(id, data) {
        var config = document.getElementById('dashboard-config');
        var linia = config ? config.getAttribute('data-linia') : 'PSD';

        fetch('/api/usun_palete_ajax', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                id: id, 
                linia: linia,
                data_planu: data 
            }),
        })
            .then(parseJsonResponse)
            .then(function (result) {
                var payload = result.data;
                if (result.ok && payload && payload.success) {
                    global.location.reload();
                    return;
                }
                global.alert(resolveRequestMessage(result, 'usuniecia palety', 'Nie udalo sie usunac palety.'));
            })
            .catch(function (error) {
                global.alert('Blad polaczenia: ' + error.message);
            });
    }

    function deletePlan(id, data) {
        debugLog('[dashboard.actions] deletePlan()', id, data);
        if (!global.confirm('Na pewno usunąć zlecenie?')) {
            return;
        }

        var config = document.getElementById('dashboard-config');
        var linia = config ? config.getAttribute('data-linia') : 'PSD';

        fetch('/api/usun_plan_ajax/' + id, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                data_planu: data,
                linia: linia
            }),
        })
            .then(parseJsonResponse)
            .then(function (result) {
                var payload = result.data;
                if (result.ok && payload && payload.success) {
                    global.alert(payload.message || 'Zlecenie usunięte');
                    global.location.reload();
                    return;
                }
                global.alert(resolveRequestMessage(result, 'usuniecia zlecenia', 'Nie udalo sie usunac zlecenia.'));
            })
            .catch(function (error) {
                global.alert('Blad sieci: ' + error.message);
            });
    }

    function dashboardTonazEdit(id) {
        var row = document.querySelector('tr[data-plan-id="' + id + '"]');
        if (!row) {
            return;
        }

        var tonaz = row.children[2].innerText.replace(/[^0-9\.,]/g, '') || 0;
        var newTonaz = global.prompt('Wpisz nowy tonaż (kg):', tonaz);
        if (newTonaz === null) {
            return;
        }

        try {
            newTonaz = parseFloat(newTonaz.replace(',', '.'));
            if (isNaN(newTonaz) || newTonaz < 0) {
                global.alert('Nieprawidłowa wartość');
                return;
            }
        } catch (error) {
            global.alert('Błąd: ' + error.message);
            return;
        }

        var config = document.getElementById('dashboard-config');
        var linia = config ? config.getAttribute('data-linia') : 'PSD';

        fetch('/api/edytuj_plan_ajax', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                id: id, 
                tonaz: newTonaz,
                linia: linia
            }),
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (payload) {
                if (payload && payload.success) {
                    global.alert('Tonaż zaktualizowany');
                    global.location.reload();
                    return;
                }
                global.alert((payload && payload.message) || 'Błąd');
            })
            .catch(function () {
                global.alert('Błąd sieci');
            });
    }

    function promptProductionDate(defaultValue) {
        var suggested = String(defaultValue || resolveCurrentPlanDate() || '').trim();
        var userInput = global.prompt('Podaj date produkcji (RRRR-MM-DD):', suggested);
        if (userInput === null) {
            return null;
        }

        var trimmed = String(userInput || '').trim();
        if (!trimmed) {
            global.alert('Data produkcji nie moze byc pusta.');
            return '';
        }

        var dateRegex = /^\d{4}-\d{2}-\d{2}$/;
        if (!dateRegex.test(trimmed)) {
            global.alert('Nieprawidlowy format daty. Uzyj RRRR-MM-DD.');
            return '';
        }

        return trimmed;
    }

    function editWorkowanieProductionDate(planId) {
        if (!planId) {
            return;
        }

        var selectedDate = promptProductionDate();
        if (selectedDate === null || selectedDate === '') {
            return;
        }

        var config = document.getElementById('dashboard-config');
        var linia = config ? config.getAttribute('data-linia') : 'PSD';

        fetch('/api/workowanie/update_data_produkcji', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                plan_id: planId,
                data_produkcji: selectedDate,
                linia: linia,
            }),
        })
            .then(parseJsonResponse)
            .then(function (result) {
                var payload = result.data;
                if (result.ok && payload && payload.success) {
                    notify(payload.message || 'Zmieniono date produkcji', 'success');

                    if (isAgroWorkowanieContext() && typeof global.performPartialReload === 'function') {
                        global.performPartialReload({ force: true, preserveScroll: true, source: 'edit-workowanie-data-produkcji' })
                            .catch(function () {
                                global.location.reload();
                            });
                        return;
                    }

                    global.location.reload();
                    return;
                }

                global.alert(resolveRequestMessage(result, 'zmiany daty produkcji', 'Nie udalo sie zmienic daty produkcji.'));
            })
            .catch(function (error) {
                global.alert('Blad polaczenia: ' + error.message);
            });
    }

    function handleSubmit(event) {
        if (event.defaultPrevented) {
            return;
        }

        var form = event.target;
        if (!form || !form.getAttribute) {
            return;
        }

        if (form.classList.contains('wn-form')) {
            submitWniosekForm(form, event);
            return;
        }

        if (form.classList.contains('confirm-paleta-form')) {
            submitConfirmPaletaForm(form, event);
            return;
        }

        var action = form.getAttribute('action') || '';
        if (action.indexOf('/dodaj_palete') !== -1) {
            submitDodajPaleteForm(form, event);
        }
    }

    function handleClick(event) {
        var paletButton = event.target.closest('[data-action="edit-palet"], [data-action="delete-palet"]');
        if (paletButton) {
            event.preventDefault();

            if (!confirmAction(paletButton)) {
                return;
            }

            var paletAction = paletButton.getAttribute('data-action');
            var paletId = paletButton.getAttribute('data-palet-id');
            if (paletAction === 'edit-palet') {
                editPalet(paletId, paletButton.getAttribute('data-palet-waga') || '');
                return;
            }

            if (paletAction === 'delete-palet') {
                deletePalet(paletId, paletButton.getAttribute('data-plan-date') || '');
                return;
            }
        }

        var deleteButton = event.target.closest('.delete-plan-btn');
        if (deleteButton) {
            event.preventDefault();
            deletePlan(deleteButton.getAttribute('data-plan-id'), deleteButton.getAttribute('data-plan-date'));
            return;
        }

        var tonazButton = event.target.closest('[data-action="dashboard-tonaz-edit"]');
        if (tonazButton) {
            event.preventDefault();
            var planId = tonazButton.getAttribute('data-plan-id');
            if (planId) {
                dashboardTonazEdit(planId);
            }
            return;
        }

        var prodDateButton = event.target.closest('[data-action="edit-workowanie-production-date"]');
        if (prodDateButton) {
            event.preventDefault();
            var orderId = prodDateButton.getAttribute('data-plan-id');
            if (orderId) {
                editWorkowanieProductionDate(orderId);
            }
        }
    }

    function handleChange(event) {
        var odrzutyInput = event.target.closest('.odrzuty-input');
        if (odrzutyInput) {
            var planId = odrzutyInput.getAttribute('data-plan-id');
            var linia = odrzutyInput.getAttribute('data-linia') || 'PSD';
            var val = parseFloat(odrzutyInput.value) || 0;

            fetch('/api/update_odrzuty_przesiewacz', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    plan_id: planId,
                    linia: linia,
                    odrzuty_przesiewacz: val
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if(data.success) {
                    odrzutyInput.style.backgroundColor = '#f8d7da';
                    setTimeout(function() { odrzutyInput.style.backgroundColor = ''; }, 1000);
                } else {
                    notify('Błąd: ' + data.message, 'danger');
                }
            })
            .catch(function(err) {
                notify('Błąd sieci podczas zapisu odrzutów', 'danger');
            });
        }
    }

    function init() {
        if (initialized) {
            return;
        }
        initialized = true;

        document.addEventListener('submit', handleSubmit, false);
        document.addEventListener('click', handleClick, false);
        document.addEventListener('change', handleChange, false);
    }

    global.dashboardCardActions = {
        init: init,
        deletePlan: deletePlan,
        dashboardTonazEdit: dashboardTonazEdit,
        editWorkowanieProductionDate: editWorkowanieProductionDate,
        editPalet: editPalet,
        deletePalet: deletePalet,
        resolveCurrentPlanDate: resolveCurrentPlanDate,
    };
})(window);