(function (global) {
    'use strict';

    if (global.dashboardUi) {
        return;
    }

    var initialized = false;
    var slideLinksBound = false;
    var quickPopupBound = false;

    function ready(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
            return;
        }
        callback();
    }

    function pad(value) {
        return value < 10 ? ('0' + value) : String(value);
    }

    function parseIsoDate(value) {
        var parts = String(value || '').split('-');
        if (parts.length !== 3) {
            return new Date();
        }
        return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    }

    function toIsoDate(date) {
        return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
    }

    function openQuickPopup(html) {
        var popup = document.getElementById('quickPopup');
        var backdrop = document.getElementById('quickBackdrop');
        if (!popup || !backdrop) {
            return;
        }

        var body = document.getElementById('quickPopupBody');
        if (body) {
            body.innerHTML = html || '';
        }

        var popupHtml = String(html || '');
        var isDosypkaPopup = popupHtml.indexOf('dosypka-popup-container') !== -1;
        var hasWideContent = /<(form|table|iframe|section)\b/i.test(popupHtml);

        if (isDosypkaPopup) {
            popup.classList.add('qp-dosypka-full');
        } else {
            popup.classList.remove('qp-dosypka-full');
        }

        if (hasWideContent || isDosypkaPopup) {
            popup.classList.add('qp-wide');
        } else {
            popup.classList.remove('qp-wide');
        }

        backdrop.style.display = 'block';
        backdrop.classList.add('show');
        popup.style.display = 'block';
        global.setTimeout(function () {
            popup.classList.add('open');
            popup.setAttribute('aria-hidden', 'false');
        }, 10);
    }

    function closeQuickPopup() {
        var popup = document.getElementById('quickPopup');
        var backdrop = document.getElementById('quickBackdrop');
        if (!popup) {
            return;
        }

        popup.classList.remove('open');
        popup.setAttribute('aria-hidden', 'true');
        if (backdrop) {
            backdrop.classList.remove('show');
        }

        global.setTimeout(function () {
            popup.style.display = 'none';
            popup.classList.remove('qp-wide', 'qp-dosypka-full');
            if (backdrop) {
                backdrop.style.display = 'none';
            }
            var body = document.getElementById('quickPopupBody');
            if (body) {
                body.innerHTML = '';
            }
        }, 360);
    }

    function removeOpenStopParam() {
        try {
            var params = new URLSearchParams(global.location.search);
            if (!params.has('open_stop')) {
                return;
            }

            if (global.__RP_DEBUG__) {
                console.log('[debug] Removing open_stop from URL to prevent auto modal open. skip_open_stop=', sessionStorage.getItem('skip_open_stop'));
            }

            params.delete('open_stop');
            var newUrl = global.location.pathname + (params.toString() ? ('?' + params.toString()) : '');
            global.history.replaceState({}, document.title, newUrl);
        } catch (error) {
            console.error(error);
        }
    }

    function bindClosePopupActions() {
        if (quickPopupBound) {
            return;
        }
        quickPopupBound = true;

        document.addEventListener('click', function (event) {
            var trigger = event.target.closest('[data-action="close-popup"]');
            if (!trigger) {
                return;
            }
            event.preventDefault();
            closeQuickPopup();
        }, false);
    }

    function bindSlideLinks() {
        if (slideLinksBound || typeof global.showQuickPopup !== 'function') {
            return;
        }
        slideLinksBound = true;

        document.body.addEventListener('click', function (event) {
            var link = event.target.closest && event.target.closest('a[data-slide]');
            if (!link) {
                return;
            }

            var href = link.getAttribute('href');
            if (!href) {
                return;
            }
            if (href.indexOf('http') === 0 && new URL(href, global.location.href).origin !== global.location.origin) {
                return;
            }

            event.preventDefault();
            if (event.stopImmediatePropagation) {
                try {
                    event.stopImmediatePropagation();
                } catch (error) {
                }
            }

            var title = link.getAttribute('title') || ((link.textContent && link.textContent.trim()) ? link.textContent.trim() : '') || 'Szybki popup';
            fetch(href, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then(function (response) {
                    return response.text();
                })
                .then(function (html) {
                    try {
                        global.showQuickPopup(title, html);
                        global.setTimeout(function () {
                            var popup = document.getElementById('quickPopup');
                            if (popup && getComputedStyle(popup).display !== 'none') {
                                popup.setAttribute('aria-hidden', 'false');
                            }
                        }, 0);
                        if (href.indexOf('dosypki_list') !== -1 && typeof global.initDosypkiList === 'function') {
                            var popup = document.querySelector('.quick-popup');
                            if (popup) {
                                global.initDosypkiList(popup);
                            }
                        }
                    } catch (error) {
                        console.error(error);
                        global.alert('Błąd: nie udało się otworzyć popupu');
                    }
                })
                .catch(function (error) {
                    console.error('fetch popup failed', error);
                    global.alert('Błąd ładowania zawartości');
                });
        }, false);
    }

    function updateWpisyForDate(dateStr) {
        var wpisyContainer = document.getElementById('wpisy-container');
        if (!wpisyContainer) {
            return;
        }

        var sekcja = document.querySelector('[data-sekcja]') ? document.querySelector('[data-sekcja]').getAttribute('data-sekcja') : 'Zasyp';
        var errorLoading = wpisyContainer.dataset.msgErrorLoading || 'Błąd ładowania';
        var noNotes = wpisyContainer.dataset.msgNoNotes || 'Brak notatek';
        var editWpis = wpisyContainer.dataset.msgEditWpis || 'Edytuj wpis';

        fetch('/api/wpisy_na_date?data=' + encodeURIComponent(dateStr) + '&sekcja=' + encodeURIComponent(sekcja))
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (!data.success) {
                    console.error('Error loading wpisy:', data.message);
                    wpisyContainer.innerHTML = '<div class="text-muted text-center p-10">' + errorLoading + '</div>';
                    return;
                }

                wpisyContainer.innerHTML = '';

                if (data.wpisy && data.wpisy.length > 0) {
                    data.wpisy.slice(0, 2).forEach(function (entry) {
                        var statusMap = {
                            'zgłoszony': '🔔 Zgłoszony',
                            'czeka_na_czesci': '⚙️ Czeka na części',
                            'zakończony': '✅ Zakończony',
                            'zamknięty': '🔒 Zamknięty',
                        };
                        var statusText = entry[9] ? ('| Status: <strong>' + (statusMap[entry[9]] || entry[9]) + '</strong>') : '';
                        var finishText = entry[10] ? (' | Zakończono: <strong>' + entry[10] + '</strong>') : '';
                        var html = '' +
                            '<div class="alert-warning d-flex justify-between align-center mb-5">' +
                            '  <div>' +
                            '    <span>⚠️ <strong>' + entry[3] + '</strong> [' + entry[5] + ']: ' + entry[2] + '</span>' +
                            '    <div class="small text-muted">' +
                            '      od ' + entry[3] + (entry[4] ? (' — do ' + entry[4]) : '') +
                            '      ' + statusText +
                            '      ' + finishText +
                            '    </div>' +
                            '  </div>' +
                            '  <div class="d-flex gap-8 align-center">' +
                            '    <a href="/edytuj/' + entry[0] + '" title="' + editWpis + '" class="font-bold text-warning-dark no-underline">✎</a>' +
                            '    <form action="/usun_wpis/' + entry[0] + '" method="POST" class="m-0">' +
                            '      <input type="hidden" name="sekcja" value="' + sekcja + '">' +
                            '      <button type="submit" class="btn-icon text-warning-dark" aria-label="Usuń wpis">✖</button>' +
                            '    </form>' +
                            '  </div>' +
                            '</div>';
                        wpisyContainer.insertAdjacentHTML('beforeend', html);
                    });
                    return;
                }

                wpisyContainer.insertAdjacentHTML('beforeend', '<div class="text-muted text-center p-10">' + noNotes + '</div>');
            })
            .catch(function (error) {
                console.error('Failed to update wpisy:', error);
                wpisyContainer.innerHTML = '<div class="text-muted text-center p-10">' + errorLoading + '</div>';
            });
    }

    function bindDateNavigation() {
        var dateDisplay = document.getElementById('current-date-display');
        var dateIso = document.getElementById('current-date-iso');
        var wpisyContainer = document.getElementById('wpisy-container');
        var dayNavButtons = document.querySelectorAll('.day-nav');
        if (!dateDisplay || !dateIso || !wpisyContainer || !dayNavButtons.length) {
            return;
        }

        dayNavButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                var offset = parseInt(button.getAttribute('data-day-offset'), 10);
                var currentDate = parseIsoDate(dateIso.value);
                currentDate.setDate(currentDate.getDate() + offset);

                var newDateStr = toIsoDate(currentDate);
                dateIso.value = newDateStr;
                var day = String(currentDate.getDate()).padStart(2, '0');
                var month = String(currentDate.getMonth() + 1).padStart(2, '0');
                var year = String(currentDate.getFullYear()).slice(-2);
                dateDisplay.textContent = day + '.' + month + '.' + year;
                updateWpisyForDate(newDateStr);
            });
        });
    }

    function init() {
        if (initialized) {
            return;
        }
        initialized = true;

        removeOpenStopParam();
        bindClosePopupActions();
        bindSlideLinks();
    }

    global.openQuickPopup = openQuickPopup;
    global.closeQuickPopup = closeQuickPopup;
    global.dashboardUi = {
        init: init,
        openQuickPopup: openQuickPopup,
        closeQuickPopup: closeQuickPopup,
        updateWpisyForDate: updateWpisyForDate,
    };

    ready(init);
})(window);