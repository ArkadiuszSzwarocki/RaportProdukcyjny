/** A single owner for order completion forms, including forms loaded in popups. */
(function () {
    'use strict';
    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!form || !form.matches('form[data-order-close="true"]')) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (form.dataset.submitting === 'true') return;
        if (typeof form.reportValidity === 'function' && !form.reportValidity()) return;
        form.dataset.submitting = 'true';
        var button = form.querySelector('button[type="submit"]');
        var originalText = button ? button.textContent : '';
        if (button) { button.disabled = true; button.textContent = 'Zamykanie...'; }
        function notify(message, success) {
            if (typeof window.showToast === 'function') window.showToast(message, success ? 'success' : 'danger');
            else if (window.dashboardToasts && window.dashboardToasts.notify) window.dashboardToasts.notify(message, success ? 'success' : 'error');
            else if (!success) window.alert(message);
        }
        fetch(form.action, {
            method: 'POST', credentials: 'same-origin', body: new FormData(form),
            headers: {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'}
        }).then(function (response) {
            if (response.status === 401) { window.location.href = '/login'; return; }
            return response.json().then(function (data) {
                if (!response.ok || !data || data.success !== true) {
                    throw new Error((data && data.message) || 'Nie udało się zakończyć zlecenia.');
                }
                notify(data.message || 'Zlecenie zakończone.', true);
                if (typeof window.closeQuickPopup === 'function') window.closeQuickPopup();
                else {
                    var close = form.querySelector('[data-action="close-popup"]');
                    if (close) close.click();
                }
                window.setTimeout(function () { window.location.reload(); }, 300);
            });
        }).catch(function (error) {
            notify(error.message || 'Błąd połączenia podczas zamykania zlecenia.', false);
            form.dataset.submitting = 'false';
            if (button) { button.disabled = false; button.textContent = originalText; }
        });
    }, true);
})();
