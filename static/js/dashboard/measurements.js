(function () {
    'use strict';
    var panel = document.getElementById('agroMeasurements');
    if (!panel || !window.dashboardScheduler) return;
    window.dashboardScheduler.addTask('agro-measurements', 60000, function () {
        return fetch(panel.dataset.url, {credentials: 'same-origin', redirect: 'error'})
            .then(function (response) {
                if (!response.ok) throw new Error('Measurements unavailable');
                return response.text();
            }).then(function (html) {
                var expanded = Array.from(panel.querySelectorAll('details')).map(function (item) { return item.open; });
                panel.innerHTML = html;
                panel.querySelectorAll('details').forEach(function (item, index) { item.open = !!expanded[index]; });
            }).catch(function () {
                // Keep the dated last reading when access or connectivity changes.
                var warning = panel.querySelector('[data-refresh-error]');
                if (!warning) {
                    warning = document.createElement('div');
                    warning.dataset.refreshError = 'true';
                    warning.className = 'text-warning small';
                    warning.textContent = 'Nie udało się odświeżyć pomiarów';
                    panel.appendChild(warning);
                }
            });
    }, {runImmediately: false});
})();
