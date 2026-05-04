(function (global) {
    'use strict';

    function notify(message, type) {
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

    global.dashboardToasts = {
        notify: notify,
    };
})(window);