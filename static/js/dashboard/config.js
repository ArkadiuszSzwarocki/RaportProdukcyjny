(function (global) {
    'use strict';

    var state = {
        currentRole: '',
        linia: 'PSD',
        isAgroZasypOperator: false,
        isAgroDosypkiObserver: false,
        isAgroLaborant: false,
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
        state.isAgroZasypOperator = !['laborant', 'laboratorium', 'magazyn', 'magazynier', 'planista'].includes(roleLower);
        state.isAgroDosypkiObserver = ['admin', 'zarzad', 'laborant', 'laboratorium'].includes(roleLower);
        state.isAgroLaborant = ['laborant', 'laboratorium'].includes(roleLower);
        state.linia = node.getAttribute('data-linia') || 'PSD';
    }

    init();

    global.dashboardConfig = {
        init: init,
        getState: getState,
        state: state,
    };
})(window);