(function (global) {
    'use strict';

    if (global.dashboardKgph) {
        return;
    }

    var initialized = false;

    function ready(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
            return;
        }
        callback();
    }

    function formatDurationFromSeconds(totalSeconds) {
        var sec = parseInt(totalSeconds, 10);
        if (!Number.isFinite(sec) || sec <= 0) {
            return '0s';
        }

        var hours = Math.floor(sec / 3600);
        var minutes = Math.floor((sec % 3600) / 60);
        var seconds = sec % 60;
        var output = [];

        if (hours > 0) {
            output.push(hours + 'h');
        }
        if (minutes > 0 || hours > 0) {
            output.push(minutes + 'm');
        }
        output.push(seconds + 's');
        return output.join(' ');
    }

    function openKgphExplain(element) {
        if (!element) {
            return false;
        }

        try {
            var data = element.dataset || {};
            var kind = data.kind === 'timeline' ? 'timeline' : 'real';
            var planId = data.planId || '-';
            var value = data.value ? (data.value + ' kg/h') : '-';
            var mass = data.mass ? (data.mass + ' kg') : '-';
            var seconds = parseInt(data.seconds || '0', 10);
            if (!Number.isFinite(seconds) || seconds < 0) {
                seconds = 0;
            }

            var timeHuman = formatDurationFromSeconds(seconds);
            var timeHours = seconds > 0 ? (seconds / 3600.0).toFixed(4) : '0.0000';
            var title = kind === 'timeline'
                ? 'Wydajność produkcyjna - rozbicie wzoru'
                : 'Wydajność rzeczywista - rozbicie wzoru';
            var modeInfo = '';

            if (kind === 'timeline') {
                modeInfo = data.mode === 'closed_sessions'
                    ? ('Tryb: suma zakończonych punktów kontrolnych. Liczba punktów: ' + (data.closedSessions || '0') + '.')
                    : 'Tryb: bieżąca sesja punktu kontrolnego.';
            } else {
                modeInfo = 'Tryb: wykonanie zlecenia / czas rzeczywisty od startu planu.';
            }

            var formula = data.mass && seconds > 0
                ? (data.mass + ' / (' + seconds + ' / 3600) = ' + (data.value || '-'))
                : 'Brak kompletu danych do wyliczenia.';

            var titleElement = document.getElementById('kgphExplainTitle');
            var planElement = document.getElementById('kgphExplainPlan');
            var valueElement = document.getElementById('kgphExplainValue');
            var massElement = document.getElementById('kgphExplainMass');
            var timeElement = document.getElementById('kgphExplainTime');
            var formulaElement = document.getElementById('kgphExplainFormula');
            var modeElement = document.getElementById('kgphExplainModeInfo');
            var backdrop = document.getElementById('kgphExplainBackdrop');
            var modal = document.getElementById('kgphExplainModal');

            if (!backdrop || !modal) {
                return false;
            }

            if (titleElement) {
                titleElement.textContent = title;
            }
            if (planElement) {
                planElement.textContent = '#' + planId;
            }
            if (valueElement) {
                valueElement.textContent = value;
            }
            if (massElement) {
                massElement.textContent = mass;
            }
            if (timeElement) {
                timeElement.textContent = seconds + ' s (' + timeHuman + ', ' + timeHours + ' h)';
            }
            if (formulaElement) {
                formulaElement.textContent = formula;
            }
            if (modeElement) {
                modeElement.textContent = modeInfo;
            }

            backdrop.style.display = 'block';
            backdrop.classList.add('show');
            modal.style.display = 'block';
            modal.classList.add('open');
            modal.setAttribute('aria-hidden', 'false');
        } catch (error) {
            console.error('kgph modal open failed', error);
        }

        return false;
    }

    function closeKgphExplain() {
        var backdrop = document.getElementById('kgphExplainBackdrop');
        var modal = document.getElementById('kgphExplainModal');

        if (modal) {
            modal.classList.remove('open');
            modal.setAttribute('aria-hidden', 'true');
        }
        if (backdrop) {
            backdrop.classList.remove('show');
        }

        global.setTimeout(function () {
            if (modal) {
                modal.style.display = 'none';
            }
            if (backdrop) {
                backdrop.style.display = 'none';
            }
        }, 160);
    }

    function handleClick(event) {
        var pill = event.target.closest('.js-kgph-explain');
        if (pill) {
            event.preventDefault();
            openKgphExplain(pill);
            return;
        }

        if (event.target && event.target.id === 'kgphExplainBackdrop') {
            closeKgphExplain();
        }
    }

    function handleKeydown(event) {
        if (event.key === 'Escape') {
            closeKgphExplain();
            return;
        }

        var active = document.activeElement;
        if ((event.key === 'Enter' || event.key === ' ') && active && active.classList && active.classList.contains('js-kgph-explain')) {
            event.preventDefault();
            openKgphExplain(active);
        }
    }

    function init() {
        if (initialized) {
            return;
        }
        initialized = true;

        document.addEventListener('click', handleClick, false);
        document.addEventListener('keydown', handleKeydown, false);

        var closeButton = document.getElementById('kgphExplainCloseBtn');
        if (closeButton) {
            closeButton.addEventListener('click', closeKgphExplain);
        }
    }

    global.forceOpenKgphExplain = openKgphExplain;
    global.openKgphExplainFromPill = openKgphExplain;
    global.closeKgphExplainModal = closeKgphExplain;
    global.dashboardKgph = {
        init: init,
        open: openKgphExplain,
        close: closeKgphExplain,
    };

    ready(init);
})(window);