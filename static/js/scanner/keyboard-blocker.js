/**
 * Universal Virtual Keyboard Blocker & Touch-Screen Scanner Controller
 * Prevents on-screen virtual keyboard (OSK) from popping up automatically on touch terminals
 * when scanning barcodes or focusing input fields.
 * Enables OSK only when user explicitly clicks the keyboard icon.
 */

(function() {
    'use strict';

    // Inject dedicated CSS for keyboard and clear button positioning
    if (!document.getElementById('kb-controller-style')) {
        const style = document.createElement('style');
        style.id = 'kb-controller-style';
        style.textContent = `
            .kb-input-wrapper {
                position: relative !important;
            }
            .kb-input-wrapper input {
                padding-right: 38px !important;
            }
            .kb-input-wrapper .kb-toggle-icon,
            .kb-input-wrapper .kb-clear-icon,
            .kb-input-wrapper #btnResetScannerInput,
            .kb-input-wrapper #clearScanBtn,
            .kb-input-wrapper #searchClearBtn,
            .kb-input-wrapper .zaladunki-clear-btn,
            .kb-input-wrapper .btn-clear-scan,
            .kb-input-wrapper .btn-clear-input,
            .kb-input-wrapper .clear-btn,
            .kb-input-wrapper .input-clear-btn,
            .kb-input-wrapper .search-clear-btn {
                position: absolute !important;
                right: 8px !important;
                top: 50% !important;
                transform: translateY(-50%) !important;
                cursor: pointer !important;
                padding: 3px !important;
                border-radius: 6px !important;
                line-height: 1 !important;
                user-select: none !important;
                -webkit-user-select: none !important;
                transition: color 0.15s, background-color 0.15s !important;
                align-items: center !important;
                justify-content: center !important;
                width: 26px !important;
                height: 26px !important;
                box-sizing: border-box !important;
            }
            .kb-input-wrapper .kb-toggle-icon {
                color: #94a3b8 !important;
                font-size: 20px !important;
                z-index: 15 !important;
                display: inline-flex;
            }
            .kb-input-wrapper .kb-clear-icon {
                display: none;
            }
            .kb-input-wrapper .kb-clear-icon,
            .kb-input-wrapper #btnResetScannerInput,
            .kb-input-wrapper #clearScanBtn,
            .kb-input-wrapper #searchClearBtn,
            .kb-input-wrapper .zaladunki-clear-btn,
            .kb-input-wrapper .btn-clear-scan,
            .kb-input-wrapper .btn-clear-input,
            .kb-input-wrapper .clear-btn,
            .kb-input-wrapper .input-clear-btn,
            .kb-input-wrapper .search-clear-btn {
                color: #94a3b8 !important;
                font-size: 18px !important;
                z-index: 16 !important;
            }
            .kb-input-wrapper .kb-clear-icon:hover,
            .kb-input-wrapper #btnResetScannerInput:hover,
            .kb-input-wrapper #clearScanBtn:hover,
            .kb-input-wrapper #searchClearBtn:hover,
            .kb-input-wrapper .zaladunki-clear-btn:hover,
            .kb-input-wrapper .input-clear-btn:hover {
                color: #ef4444 !important;
                background-color: rgba(239, 68, 68, 0.12) !important;
            }
            .kb-input-wrapper input::-webkit-calendar-picker-indicator {
                opacity: 0.4;
                cursor: pointer;
                margin-right: 22px;
            }
            .kb-input-wrapper input::-webkit-search-cancel-button {
                display: none;
            }
        `;
        document.head.appendChild(style);
    }

    // Enable W3C VirtualKeyboard API manual policy if supported by browser
    if ('virtualKeyboard' in navigator) {
        try {
            navigator.virtualKeyboard.overlaysContent = true;
        } catch(e) {}
    }

    function toggleKeyboard(input, icon) {
        const isForced = input.dataset.forceKb === 'true';
        if (isForced) {
            // Turn OFF keyboard
            input.dataset.forceKb = 'false';
            input.setAttribute('inputmode', 'none');
            input.setAttribute('virtualkeyboardpolicy', 'manual');
            icon.style.color = '#94a3b8';
            icon.style.background = 'transparent';
            if ('virtualKeyboard' in navigator && navigator.virtualKeyboard.hide) {
                navigator.virtualKeyboard.hide();
            }
            input.blur();
        } else {
            // Turn ON keyboard
            input.dataset.forceKb = 'true';
            const targetMode = input.type === 'number' || input.dataset.type === 'number' ? 'numeric' : 'text';
            input.removeAttribute('inputmode');
            input.setAttribute('inputmode', targetMode);
            input.setAttribute('virtualkeyboardpolicy', 'auto');
            icon.style.color = '#2563eb';
            icon.style.background = 'rgba(37, 99, 235, 0.12)';
            
            input.focus();
            if ('virtualKeyboard' in navigator && navigator.virtualKeyboard.show) {
                navigator.virtualKeyboard.show();
            }
        }
    }

    function isEligibleInput(input) {
        if (!input || input.dataset.kbAttached === 'true') return false;
        if (input.dataset.noKbBlock === 'true' || input.hasAttribute('data-no-kb-block')) return false;
        if (input.readOnly || input.disabled) return false;

        const type = (input.getAttribute('type') || 'text').toLowerCase();
        if (['hidden', 'checkbox', 'radio', 'submit', 'button', 'date', 'time', 'datetime-local', 'file', 'color', 'range'].includes(type)) {
            return false;
        }

        // Exclude system search dropdowns, inputs with datalist, dosypka weight inputs or inputs marked no-kb-icon
        if (input.classList.contains('select2-search__field') || 
            input.classList.contains('dt-input') ||
            input.classList.contains('dosypka-actual-kg') ||
            input.classList.contains('no-kb-icon') ||
            input.classList.contains('no-kb-block') ||
            input.hasAttribute('list')) {
            return false;
        }

        return true;
    }

    const CLEAR_SELECTORS = [
        '#btnResetScannerInput',
        '#clearScanBtn',
        '#searchClearBtn',
        '.zaladunki-clear-btn',
        '.btn-clear-scan',
        '.btn-clear-input',
        '.input-clear-btn',
        '.search-clear-btn',
        '.kb-clear-icon',
        '[data-action="clear-input"]'
    ].join(', ');

    function attachKeyboardController(input) {
        if (!isEligibleInput(input)) return;

        input.dataset.kbAttached = 'true';
        input.dataset.forceKb = 'false';

        // Default to inputmode none so virtual keyboard never auto-opens
        input.setAttribute('inputmode', 'none');
        input.setAttribute('virtualkeyboardpolicy', 'manual');

        // Prevent virtual keyboard popup on touch / pointer events unless user explicitly enabled forceKb
        const suppressOsk = (e) => {
            if (input.dataset.forceKb !== 'true') {
                input.setAttribute('inputmode', 'none');
                input.setAttribute('virtualkeyboardpolicy', 'manual');
            }
        };

        input.addEventListener('focus', suppressOsk, { passive: true });
        input.addEventListener('touchstart', suppressOsk, { passive: true });
        input.addEventListener('pointerdown', suppressOsk, { passive: true });
        input.addEventListener('click', suppressOsk, { passive: true });

        const parent = input.parentElement;
        if (!parent) return;

        const parentStyle = window.getComputedStyle(parent);

        let wrapper = parent;
        const needsWrapper = !parent.classList.contains('kb-input-wrapper');

        if (needsWrapper) {
            wrapper = document.createElement('div');
            wrapper.className = 'kb-input-wrapper';
            wrapper.style.position = 'relative';
            wrapper.style.display = 'inline-flex';
            wrapper.style.alignItems = 'center';
            wrapper.style.width = input.style.width || (parentStyle.display === 'flex' ? '100%' : (input.classList.contains('w-full') ? '100%' : '100%'));
            if (input.classList.contains('form-control') || input.style.width === '100%') {
                wrapper.style.width = '100%';
            }

            parent.insertBefore(wrapper, input);
            wrapper.appendChild(input);
        } else {
            wrapper.classList.add('kb-input-wrapper');
            wrapper.style.position = 'relative';
        }

        let clearBtn = wrapper.querySelector(CLEAR_SELECTORS);
        const maxQtyLabel = wrapper.querySelector('#scannerReturnMaxQty');
        const iconRight = maxQtyLabel ? '60px' : '8px';

        input.style.setProperty('padding-right', maxQtyLabel ? '90px' : '38px', 'important');

        if (!clearBtn) {
            clearBtn = document.createElement('span');
            clearBtn.className = 'material-icons kb-clear-icon';
            clearBtn.textContent = 'close';
            clearBtn.title = 'Wyczyść pole';
            clearBtn.setAttribute('role', 'button');
            clearBtn.setAttribute('aria-label', 'Wyczyść pole');
            clearBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                input.value = '';
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.focus();
                updateVisibility();
            });
            wrapper.appendChild(clearBtn);
        } else {
            clearBtn.addEventListener('click', () => {
                setTimeout(() => {
                    updateVisibility();
                }, 20);
            });
        }

        // Keyboard icon element
        const icon = document.createElement('span');
        icon.className = 'material-icons kb-toggle-icon';
        icon.textContent = 'keyboard';
        icon.title = 'Dotknij, aby włączyć klawiaturę ekranową';
        icon.setAttribute('role', 'button');
        icon.setAttribute('aria-label', 'Włącz klawiaturę ekranową');

        icon.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleKeyboard(input, icon);
        });

        wrapper.appendChild(icon);

        function updateVisibility() {
            const val = (input.value !== undefined && input.value !== null) ? String(input.value).trim() : '';
            const hasText = val.length > 0;
            if (hasText) {
                icon.style.setProperty('display', 'none', 'important');
                if (clearBtn) {
                    clearBtn.style.setProperty('display', 'inline-flex', 'important');
                    clearBtn.style.setProperty('right', iconRight, 'important');
                }
            } else {
                icon.style.setProperty('display', 'inline-flex', 'important');
                icon.style.setProperty('right', iconRight, 'important');
                if (clearBtn) {
                    clearBtn.style.setProperty('display', 'none', 'important');
                }
            }
        }

        input.addEventListener('input', updateVisibility);
        input.addEventListener('change', updateVisibility);
        input.addEventListener('keyup', updateVisibility);
        input.addEventListener('paste', () => setTimeout(updateVisibility, 0));
        input.addEventListener('cut', () => setTimeout(updateVisibility, 0));
        input.addEventListener('focus', updateVisibility);
        input.addEventListener('blur', updateVisibility);

        // Keep state synchronized safely without overriding native input property descriptors
        setInterval(updateVisibility, 150);

        updateVisibility();
    }

    function scanAndAttachKeyboards() {
        // Query text and number inputs across the entire document
        const selector = 'input[type="text"]:not([readonly]), input[type="number"]:not([readonly]), input[type="search"]:not([readonly]), input:not([type]):not([readonly])';
        const inputs = document.querySelectorAll(selector);
        inputs.forEach(attachKeyboardController);
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scanAndAttachKeyboards);
    } else {
        scanAndAttachKeyboards();
    }

    // Dynamic inputs observer (modals, AJAX content, dynamically loaded rows)
    const mutationObserver = new MutationObserver((mutations) => {
        let hasNewElements = false;
        for (const m of mutations) {
            if (m.addedNodes && m.addedNodes.length > 0) {
                for (const node of m.addedNodes) {
                    if (node.nodeType === 1) {
                        if (node.tagName === 'INPUT' || (node.querySelector && node.querySelector('input'))) {
                            hasNewElements = true;
                            break;
                        }
                    }
                }
            }
            if (hasNewElements) break;
        }
        if (hasNewElements) {
            scanAndAttachKeyboards();
        }
    });

    mutationObserver.observe(document.documentElement || document.body, {
        childList: true,
        subtree: true
    });

    // Re-check after window load to capture late renders
    window.addEventListener('load', scanAndAttachKeyboards);
})();
