(function (global) {
    'use strict';

    var state = {
        currentRole: '',
        linia: 'PSD',
        sekcja: '',
        isZasypOperator: false,
        isDosypkiObserver: false,
        isLaborant: false,
    };

    function getConfigNode() {
        return document.getElementById('dashboard-config');
    }

    function getState() {
        return state;
    }

    function init() {
        var node = getConfigNode();
        if (!node) {
            return;
        }

        var role = String(node.getAttribute('data-current-role') || '').trim();
        var roleLower = role.toLowerCase();

        state.currentRole = role;
        state.isZasypOperator = !['laborant', 'laboratorium', 'magazyn', 'magazynier', 'planista'].includes(roleLower);
        state.isDosypkiObserver = ['admin', 'zarzad', 'laborant', 'laboratorium'].includes(roleLower);
        state.isLaborant = ['laborant', 'laboratorium'].includes(roleLower);
        state.linia = node.getAttribute('data-linia') || 'PSD';
        state.sekcja = node.getAttribute('data-sekcja') || '';
    }

    init();

    global.dashboardConfig = {
        init: init,
        getState: getState,
        state: state,
    };
})(window);