// File: static/js/common/print-toast.js
/**
 * static/js/common/print-toast.js
 * Global print notification component.
 * Tracks and visualizes print jobs in real-time:
 * 1. Sending: Shows printer target and attempt 1/3.
 * 2. Verification: Checks if bridge/printer received the job.
 * 3. Retries: Displays live retry counter (Próba 2/3, 3/3).
 * 4. Success: Shows sensor/buffer OK confirmation, auto-dismisses after 4s.
 * 5. Error: Shows exact error message and stays visible until dismissed.
 */
(function (global) {
    'use strict';

    var CONTAINER_ID = 'printToastContainer';
    var toastCounter = 0;

    function getContainer() {
        var el = document.getElementById(CONTAINER_ID);
        if (!el) {
            el = document.createElement('div');
            el.id = CONTAINER_ID;
            el.style.cssText = [
                'position: fixed',
                'bottom: 24px',
                'right: 24px',
                'z-index: 999999',
                'display: flex',
                'flex-direction: column-reverse',
                'gap: 10px',
                'pointer-events: none',
                'max-width: 420px',
                'width: calc(100vw - 48px)'
            ].join(';');
            if (document.body) {
                document.body.appendChild(el);
            } else {
                document.addEventListener('DOMContentLoaded', function () {
                    document.body.appendChild(el);
                });
            }
        }
        return el;
    }

    var STATUS_CONFIG = {
        sending: {
            icon: '🖨️',
            bg: 'linear-gradient(135deg, #0f172a, #1e293b)',
            border: '#3b82f6',
            color: '#f8fafc',
            badgeBg: '#1e3a8a',
            badgeColor: '#93c5fd',
            pulseColor: 'rgba(59, 130, 246, 0.5)'
        },
        checking: {
            icon: '📡',
            bg: 'linear-gradient(135deg, #1e1b4b, #312e81)',
            border: '#6366f1',
            color: '#e0e7ff',
            badgeBg: '#3730a3',
            badgeColor: '#c7d2fe',
            pulseColor: 'rgba(99, 102, 241, 0.5)'
        },
        retry: {
            icon: '🔄',
            bg: 'linear-gradient(135deg, #451a03, #92400e)',
            border: '#f59e0b',
            color: '#fffbeb',
            badgeBg: '#78350f',
            badgeColor: '#fde68a',
            pulseColor: 'rgba(245, 158, 11, 0.5)'
        },
        success: {
            icon: '✅',
            bg: 'linear-gradient(135deg, #064e3b, #047857)',
            border: '#10b981',
            color: '#ecfdf5',
            badgeBg: '#065f46',
            badgeColor: '#a7f3d0',
            pulseColor: null
        },
        error: {
            icon: '❌',
            bg: 'linear-gradient(135deg, #450a0a, #991b1b)',
            border: '#ef4444',
            color: '#fef2f2',
            badgeBg: '#7f1d1d',
            badgeColor: '#fca5a5',
            pulseColor: null
        }
    };

    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    function createToast(printerName, status, message, attempt, totalAttempts) {
        var id = 'print-toast-' + (++toastCounter);
        var cfg = STATUS_CONFIG[status] || STATUS_CONFIG.sending;

        var toast = document.createElement('div');
        toast.id = id;
        toast.setAttribute('data-print-toast', 'true');
        toast.style.cssText = [
            'pointer-events: auto',
            'background: ' + cfg.bg,
            'border: 1.5px solid ' + cfg.border,
            'border-radius: 12px',
            'padding: 12px 16px',
            'color: ' + cfg.color,
            'font-family: Inter, system-ui, -apple-system, sans-serif',
            'font-size: 0.88rem',
            'box-shadow: 0 10px 30px rgba(0,0,0,0.35), 0 2px 8px rgba(0,0,0,0.2)',
            'transform: translateX(120%)',
            'transition: transform 0.35s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.35s ease',
            'opacity: 0',
            'display: flex',
            'align-items: center',
            'gap: 12px',
            'min-width: 280px',
            'cursor: default',
            'backdrop-filter: blur(12px)',
            '-webkit-backdrop-filter: blur(12px)'
        ].join(';');

        var pulseAnim = '';
        if (cfg.pulseColor) {
            pulseAnim = 'animation: printToastPulse 1.5s ease-in-out infinite;';
        }

        var attemptBadge = '';
        if (totalAttempts && totalAttempts > 1) {
            attemptBadge = '<span class="pt-attempt" style="font-size:0.72rem;font-weight:700;background:' + cfg.badgeBg + ';color:' + cfg.badgeColor + ';padding:2px 7px;border-radius:6px;margin-left:6px;">Próba ' + attempt + '/' + totalAttempts + '</span>';
        }

        var closeBtn = '';
        if (status === 'error') {
            closeBtn = '<button class="pt-close-btn" style="background:rgba(255,255,255,0.18);border:none;color:inherit;cursor:pointer;border-radius:6px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;flex-shrink:0;margin-left:auto;transition:background 0.15s;" aria-label="Zamknij">✕</button>';
        }

        toast.innerHTML = [
            '<div class="pt-icon" style="font-size:1.4rem;line-height:1;flex-shrink:0;' + pulseAnim + '">' + cfg.icon + '</div>',
            '<div class="pt-content" style="flex:1;min-width:0;">',
            '  <div style="display:flex;align-items:center;margin-bottom:3px;">',
            '    <div class="pt-msg" style="font-weight:800;font-size:0.9rem;line-height:1.2;color:#ffffff;">' + escapeHtml(message) + '</div>',
            attemptBadge,
            '  </div>',
            '  <div class="pt-printer" style="font-size:0.78rem;color:rgba(255,255,255,0.75);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">🖨️ ' + escapeHtml(printerName || 'Drukarka domyślna') + '</div>',
            '</div>',
            closeBtn
        ].join('');

        if (status === 'error') {
            var btn = toast.querySelector('.pt-close-btn');
            if (btn) {
                btn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    dismissToast(toast);
                });
            }
        }

        return toast;
    }

    function showToastElement(toast) {
        var container = getContainer();
        container.appendChild(toast);
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                toast.style.transform = 'translateX(0)';
                toast.style.opacity = '1';
            });
        });
    }

    function dismissToast(toast) {
        if (!toast) return;
        toast.style.transform = 'translateX(120%)';
        toast.style.opacity = '0';
        setTimeout(function () {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 400);
    }

    function autoDismiss(toast, delayMs) {
        if (!toast) return;
        setTimeout(function () {
            dismissToast(toast);
        }, delayMs || 4000);
    }

    function updateToast(toast, status, message, printerName, attempt, totalAttempts) {
        if (!toast) return;
        var cfg = STATUS_CONFIG[status] || STATUS_CONFIG.sending;
        toast.style.background = cfg.bg;
        toast.style.borderColor = cfg.border;
        toast.style.color = cfg.color;

        var iconEl = toast.querySelector('.pt-icon');
        if (iconEl) {
            iconEl.textContent = cfg.icon;
            iconEl.style.animation = cfg.pulseColor ? 'printToastPulse 1.5s ease-in-out infinite' : 'none';
        }

        var msgEl = toast.querySelector('.pt-msg');
        if (msgEl) msgEl.textContent = message;

        var printerEl = toast.querySelector('.pt-printer');
        if (printerEl && printerName) printerEl.innerHTML = '🖨️ ' + escapeHtml(printerName);

        var attemptEl = toast.querySelector('.pt-attempt');
        if (totalAttempts && totalAttempts > 1) {
            if (attemptEl) {
                attemptEl.textContent = 'Próba ' + attempt + '/' + totalAttempts;
                attemptEl.style.background = cfg.badgeBg;
                attemptEl.style.color = cfg.badgeColor;
                attemptEl.style.display = '';
            } else {
                var contentDiv = toast.querySelector('.pt-content > div:first-child');
                if (contentDiv) {
                    var newBadge = document.createElement('span');
                    newBadge.className = 'pt-attempt';
                    newBadge.style.cssText = 'font-size:0.72rem;font-weight:700;background:' + cfg.badgeBg + ';color:' + cfg.badgeColor + ';padding:2px 7px;border-radius:6px;margin-left:6px;';
                    newBadge.textContent = 'Próba ' + attempt + '/' + totalAttempts;
                    contentDiv.appendChild(newBadge);
                }
            }
        } else if (attemptEl) {
            attemptEl.style.display = 'none';
        }

        if (status === 'error' && !toast.querySelector('.pt-close-btn')) {
            var closeBtn = document.createElement('button');
            closeBtn.className = 'pt-close-btn';
            closeBtn.style.cssText = 'background:rgba(255,255,255,0.18);border:none;color:inherit;cursor:pointer;border-radius:6px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;flex-shrink:0;margin-left:auto;';
            closeBtn.textContent = '✕';
            closeBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                dismissToast(toast);
            });
            toast.appendChild(closeBtn);
        }
    }

    // ---- Inject CSS keyframes for pulse animation ----
    (function injectStyles() {
        if (document.getElementById('printToastStyles')) return;
        var style = document.createElement('style');
        style.id = 'printToastStyles';
        style.textContent = [
            '@keyframes printToastPulse {',
            '  0%, 100% { transform: scale(1); }',
            '  50% { transform: scale(1.18); }',
            '}',
            '#' + CONTAINER_ID + ' { transition: all 0.3s ease; }'
        ].join('\n');
        if (document.head) {
            document.head.appendChild(style);
        } else {
            document.addEventListener('DOMContentLoaded', function () {
                document.head.appendChild(style);
            });
        }
    })();

    /**
     * Polls the backend status for an asynchronous print job.
     * @param {number} jobId 
     * @param {Object} toastHandle 
     * @param {string} fallbackPrinter 
     */
    function trackPrintJob(jobId, toastHandle, fallbackPrinter) {
        if (!jobId || !toastHandle) return;

        var startTime = Date.now();
        var maxDurationMs = 20000; // 20s timeout
        var intervalMs = 800;

        function poll() {
            if (Date.now() - startTime > maxDurationMs) {
                toastHandle.update({
                    status: 'error',
                    message: 'Przekroczono limit czasu oczekiwania na drukarkę',
                    printerName: fallbackPrinter
                });
                return;
            }

            fetch('/api/print_job_status/' + encodeURIComponent(jobId), {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data || !data.success || !data.job) {
                    setTimeout(poll, intervalMs);
                    return;
                }

                var job = data.job;
                var currentStatus = job.status;
                var pName = job.printer_name || job.printer_ip || fallbackPrinter;
                var retryCount = (job.retry_count || 0) + 1;

                if (currentStatus === 'DONE') {
                    var successNote = 'Wydrukowano pomyślnie';
                    if (job.error_message && job.error_message.indexOf('Licznik') !== -1) {
                        successNote = 'Wydrukowano (potwierdzone przez czujnik)';
                    }
                    toastHandle.update({
                        status: 'success',
                        message: successNote,
                        printerName: pName,
                        attempt: retryCount,
                        totalAttempts: 3
                    });
                } else if (currentStatus === 'ERROR' && job.retry_count >= 3) {
                    var errMsg = job.error_message || 'Błąd komunikacji z drukarką';
                    toastHandle.update({
                        status: 'error',
                        message: 'Błąd druku: ' + errMsg,
                        printerName: pName,
                        attempt: 3,
                        totalAttempts: 3
                    });
                } else if (currentStatus === 'ERROR' && job.retry_count < 3) {
                    toastHandle.update({
                        status: 'retry',
                        message: 'Drukarka zajęta, ponawianie...',
                        printerName: pName,
                        attempt: retryCount,
                        totalAttempts: 3
                    });
                    setTimeout(poll, intervalMs);
                } else if (currentStatus === 'PRINTING') {
                    toastHandle.update({
                        status: 'checking',
                        message: 'Sprawdzam czy dotarło do drukarki...',
                        printerName: pName,
                        attempt: retryCount,
                        totalAttempts: 3
                    });
                    setTimeout(poll, intervalMs);
                } else {
                    // PENDING
                    toastHandle.update({
                        status: 'sending',
                        message: 'Wysyłanie do kolejki druku...',
                        printerName: pName,
                        attempt: 1,
                        totalAttempts: 3
                    });
                    setTimeout(poll, intervalMs);
                }
            })
            .catch(function () {
                setTimeout(poll, intervalMs);
            });
        }

        setTimeout(poll, 600);
    }

    // ========================
    // PUBLIC API
    // ========================

    /**
     * Show a print notification toast.
     * @param {Object} opts
     * @param {string} opts.printerName - Name of the target printer
     * @param {string} opts.printerIp - IP of the target printer
     * @param {string} [opts.status='sending'] - One of: sending, checking, success, error, retry
     * @param {string} [opts.message] - Custom message text
     * @param {number} [opts.attempt=1] - Current attempt number
     * @param {number} [opts.totalAttempts=3] - Total planned attempts
     * @param {number} [opts.jobId] - Optional job ID to automatically poll status
     * @returns {Object} Handle with update() and dismiss() methods
     */
    function printToast(opts) {
        opts = opts || {};
        var status = opts.status || 'sending';
        var printerLabel = opts.printerName || opts.printerIp || 'Drukarka domyślna';
        var message = opts.message || (status === 'sending' ? 'Wysyłanie do drukarki...' : 'Drukowanie');
        var attempt = opts.attempt || 1;
        var totalAttempts = opts.totalAttempts || 3;

        var toast = createToast(printerLabel, status, message, attempt, totalAttempts);
        showToastElement(toast);

        if (status === 'success') {
            autoDismiss(toast, 4000);
        }

        var handle = {
            element: toast,
            update: function (newOpts) {
                newOpts = newOpts || {};
                var newStatus = newOpts.status || status;
                var newMessage = newOpts.message || message;
                var newPrinter = newOpts.printerName || newOpts.printerIp || printerLabel;
                var newAttempt = newOpts.attempt || attempt;
                var newTotal = newOpts.totalAttempts || totalAttempts;

                status = newStatus;
                message = newMessage;
                printerLabel = newPrinter;
                attempt = newAttempt;
                totalAttempts = newTotal;

                updateToast(toast, newStatus, newMessage, newPrinter, newAttempt, newTotal);

                if (newStatus === 'success') {
                    autoDismiss(toast, 4000);
                }
            },
            dismiss: function () {
                dismissToast(toast);
            }
        };

        if (opts.jobId) {
            trackPrintJob(opts.jobId, handle, printerLabel);
        }

        return handle;
    }

    global.PrintToast = {
        show: printToast,
        trackJob: trackPrintJob
    };

    // ========================================================
    // GLOBAL AUTOMATIC FETCH INTERCEPTOR FOR ALL PRINT REQUESTS
    // ========================================================
    (function installGlobalInterceptor() {
        if (!global.fetch || global._printToastInterceptorInstalled) return;
        global._printToastInterceptorInstalled = true;

        var originalFetch = global.fetch;

        function isPrintUrl(urlStr) {
            if (!urlStr || typeof urlStr !== 'string') return false;
            var lower = urlStr.toLowerCase();
            return (
                lower.indexOf('/print') !== -1 ||
                lower.indexOf('/drukuj') !== -1 ||
                lower.indexOf('/drukuj_etykiete_zpl') !== -1 ||
                lower.indexOf('/drukuj-zpl') !== -1 ||
                lower.indexOf('/print_location') !== -1 ||
                lower.indexOf('/pallet/print') !== -1
            ) && lower.indexOf('/printer-server/status') === -1
              && lower.indexOf('/printer/status') === -1
              && lower.indexOf('/printers') === -1
              && lower.indexOf('/active-printers') === -1
              && lower.indexOf('/print_job_status') === -1;
        }

        global.fetch = function (resource, init) {
            var urlStr = (typeof resource === 'string') ? resource : (resource && resource.url ? resource.url : '');

            // Skip if explicit flag or not a print URL
            if (!isPrintUrl(urlStr) || (init && init._handledByPrintToast)) {
                return originalFetch.apply(this, arguments);
            }

            // Extract printer info from params or body
            var printerHint = '';
            try {
                if (urlStr.indexOf('?') !== -1) {
                    var u = new URL(urlStr, window.location.origin);
                    printerHint = u.searchParams.get('printer_name') || u.searchParams.get('printer_ip') || '';
                }
                if (!printerHint && init && init.body) {
                    if (typeof init.body === 'string') {
                        var parsed = JSON.parse(init.body);
                        printerHint = parsed.printer_name || parsed.override_name || parsed.printer_ip || parsed.override_ip || '';
                    }
                }
            } catch (e) {}

            // Check active UI dropdowns on the page (e.g. #printerSelect in pallet modal)
            if (!printerHint) {
                try {
                    var sel = document.querySelector('#printerSelect, select[name="printer_id"], #preprint_printer, .printer-select');
                    if (sel && sel.selectedOptions && sel.selectedOptions.length > 0) {
                        var optText = (sel.selectedOptions[0].textContent || '').trim();
                        if (optText && optText.indexOf('Wybierz') === -1 && optText.indexOf('--') === -1) {
                            printerHint = optText;
                        }
                    }
                } catch (e) {}
            }

            if (!printerHint) {
                try {
                    printerHint = localStorage.getItem('agromes_preferred_zpl_printer_name') || localStorage.getItem('agromes_preferred_zpl_printer_ip') || 'Drukarka domyślna';
                } catch (e) {
                    printerHint = 'Drukarka domyślna';
                }
            }

            var pt = printToast({
                printerName: printerHint,
                status: 'sending',
                message: 'Wysyłanie do drukarki...',
                attempt: 1,
                totalAttempts: 3
            });

            return originalFetch.apply(this, arguments).then(function (response) {
                var cloned = response.clone();
                cloned.json().then(function (data) {
                    var pName = (data && (data.printer_name || data.printer_ip)) || printerHint;
                    if (data && data.job_id) {
                        pt.update({
                            status: 'checking',
                            message: 'Sprawdzam czy dotarło do drukarki...',
                            printerName: pName,
                            attempt: 1,
                            totalAttempts: 3
                        });
                        trackPrintJob(data.job_id, pt, pName);
                    } else if (data && data.success === true) {
                        var successMsg = data.message || 'Wydrukowano pomyślnie';
                        if (successMsg === 'Dodano do kolejki druku') successMsg = 'Wydrukowano pomyślnie';
                        pt.update({
                            status: 'success',
                            message: successMsg,
                            printerName: pName
                        });
                    } else if (data && data.local_bridge_fallback) {
                        pt.update({
                            status: 'retry',
                            message: 'Próba połączenia lokalnego...',
                            printerName: pName,
                            attempt: 2,
                            totalAttempts: 3
                        });
                    } else {
                        var errMsg = (data && (data.error || data.message)) ? (data.error || data.message) : 'Błąd druku (' + response.status + ')';
                        pt.update({
                            status: 'error',
                            message: 'Błąd: ' + errMsg,
                            printerName: pName
                        });
                    }
                }).catch(function () {
                    if (response.ok) {
                        pt.update({ status: 'success', message: 'Wydrukowano pomyślnie', printerName: printerHint });
                    } else {
                        pt.update({ status: 'error', message: 'Błąd odpowiedzi serwera (' + response.status + ')', printerName: printerHint });
                    }
                });

                return response;
            }).catch(function (err) {
                pt.update({
                    status: 'error',
                    message: 'Brak połączenia z drukarką',
                    printerName: printerHint
                });
                throw err;
            });
        };
    })();

})(window);
