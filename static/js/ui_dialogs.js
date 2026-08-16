/**
 * ui_dialogs.js
 * AppDialog - Asynchroniczne pop-upy systemowe zastępujące alert(), confirm() i prompt()
 * Działanie oparte na stylach premium AgroMES
 */

const AppDialog = (function() {
    function createDialogHTML(type, message, title, defaultValue = '') {
        const icon = type === 'alert' ? 'info' : (type === 'confirm' ? 'help_outline' : 'edit');
        const iconColor = type === 'alert' ? '#3b82f6' : (type === 'confirm' ? '#f59e0b' : '#10b981');
        
        let contentHtml = `
            <div style="font-size: 15px; color: #334155; margin-bottom: 20px; line-height: 1.5;">
                ${message.replace(/\n/g, '<br>')}
            </div>
        `;

        if (type === 'prompt') {
            contentHtml += `
                <div style="margin-bottom: 20px;">
                    <input type="text" id="appDialogPromptInput" class="form-control" value="${defaultValue}" style="width: 100%; font-size: 16px; padding: 10px;" autocomplete="off">
                </div>
            `;
        }

        let buttonsHtml = '';
        if (type === 'alert') {
            buttonsHtml = `<button id="appDialogBtnOk" class="btn-action btn-blue" style="min-width: 100px;">OK</button>`;
        } else {
            buttonsHtml = `
                <button id="appDialogBtnCancel" class="btn-action btn-secondary" style="margin-right: 10px; min-width: 100px;">Anuluj</button>
                <button id="appDialogBtnOk" class="btn-action btn-blue" style="min-width: 100px;">OK</button>
            `;
        }

        return `
            <div id="appDialogOverlay" class="modal-premium-overlay" style="position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(4px); display: flex; z-index: 9999; align-items: center; justify-content: center;">
                <div class="modal-premium-content" style="background: #ffffff; border-radius: 16px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04); padding: 24px; max-width: 450px; width: 90%; transform: scale(1); opacity: 1; transition: all 0.2s ease;">
                    <div class="modal-premium-header" style="border-bottom: 2px solid #f1f5f9; padding-bottom: 15px; margin-bottom: 15px;">
                        <h3 style="margin: 0; display: flex; align-items: center; gap: 10px; font-weight: 800; color: #0f172a;">
                            <span class="material-icons" style="color: ${iconColor}">${icon}</span> ${title || 'Informacja'}
                        </h3>
                    </div>
                    <div class="modal-premium-body">
                        ${contentHtml}
                        <div style="display: flex; justify-content: flex-end; margin-top: 15px;">
                            ${buttonsHtml}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    function showDialog(type, message, title, defaultValue = '') {
        return new Promise((resolve) => {
            const existing = document.getElementById('appDialogOverlay');
            if (existing) existing.remove();

            const html = createDialogHTML(type, message, title, defaultValue);
            document.body.insertAdjacentHTML('beforeend', html);

            const overlay = document.getElementById('appDialogOverlay');
            const btnOk = document.getElementById('appDialogBtnOk');
            const btnCancel = document.getElementById('appDialogBtnCancel');
            const promptInput = document.getElementById('appDialogPromptInput');

            if (promptInput) {
                promptInput.focus();
                promptInput.select();
                promptInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') btnOk.click();
                });
            } else {
                btnOk.focus();
            }

            const cleanup = () => {
                overlay.style.opacity = '0';
                overlay.querySelector('.modal-premium-content').style.transform = 'scale(0.95)';
                setTimeout(() => {
                    if (overlay.parentNode) overlay.remove();
                }, 200);
            };

            btnOk.addEventListener('click', () => {
                cleanup();
                if (type === 'prompt') {
                    resolve(promptInput.value);
                } else {
                    resolve(true);
                }
            });

            if (btnCancel) {
                btnCancel.addEventListener('click', () => {
                    cleanup();
                    if (type === 'prompt') {
                        resolve(null);
                    } else {
                        resolve(false);
                    }
                });
            }
        });
    }

    return {
        alert: function(message, title = 'Komunikat') {
            return showDialog('alert', message, title);
        },
        confirm: function(message, title = 'Potwierdzenie') {
            return showDialog('confirm', message, title);
        },
        prompt: function(message, defaultValue = '', title = 'Wprowadź dane') {
            return showDialog('prompt', message, title, defaultValue);
        }
    };
})();
