/** One submit handler for resume forms in both popup implementations. */
(function () {
    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!form.matches('form[data-success-navigate="true"]')) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (form.dataset.submitting === 'true') return;
        form.dataset.submitting = 'true';
        var buttons = form.querySelectorAll('button[type="submit"]');
        buttons.forEach(function (button) { button.disabled = true; });
        fetch(form.action, {
            method: 'POST', body: new FormData(form), credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (response) {
            if (response.status === 401) { window.location.href = '/login'; return; }
            return response.json().then(function (data) {
                if (!response.ok || !data.success) throw new Error(data.message || 'Błąd wznowienia zlecenia.');
                if (!data.redirect_url) throw new Error('Brak adresu wznowionego zlecenia.');
                var target = new URL(data.redirect_url, window.location.origin);
                if (target.origin !== window.location.origin) throw new Error('Nieprawidłowy adres powrotu.');
                window.location.href = target.href;
            });
        }).catch(function (error) {
            if (typeof window.showToast === 'function') window.showToast(error.message, 'danger');
            buttons.forEach(function (button) { button.disabled = false; });
            form.dataset.submitting = 'false';
        });
    }, true);
})();
