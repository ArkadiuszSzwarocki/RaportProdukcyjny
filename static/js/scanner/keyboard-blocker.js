/**
 * Universal Virtual Keyboard Blocker & Touch-Screen Scanner Controller
 * Prevents on-screen virtual keyboard (OSK) from popping up automatically on touch terminals
 * when scanning barcodes or focusing input fields.
 * Enables OSK only when user explicitly clicks the keyboard icon.
 */

(function() {
    'use strict';

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

        // Exclude system search dropdowns, dosypka weight inputs or inputs marked no-kb-icon
        if (input.classList.contains('select2-search__field') || 
            input.classList.contains('dt-input') ||
            input.classList.contains('dosypka-actual-kg') ||
            input.classList.contains('no-kb-icon') ||
            input.classList.contains('no-kb-block')) {
            return false;
        }

        return true;
    }

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

        // Create keyboard toggle icon
        const parent = input.parentElement;
        if (!parent) return;

        // If parent is already a relative container with just this input, check if we need a wrapper
        let wrapper = parent;
        const parentStyle = window.getComputedStyle(parent);
        const needsWrapper = !parent.classList.contains('kb-input-wrapper') && (parent.children.length > 1 || parentStyle.position === 'static');

        if (needsWrapper) {
            wrapper = document.createElement('div');
            wrapper.className = 'kb-input-wrapper';
            wrapper.style.position = 'relative';
            wrapper.style.display = 'inline-flex';
            wrapper.style.alignItems = 'center';
            wrapper.style.width = input.style.width || (parentStyle.display === 'flex' ? '100%' : (input.classList.contains('w-full') ? '100%' : 'auto'));
            if (input.classList.contains('form-control') || input.style.width === '100%') {
                wrapper.style.width = '100%';
            }

            parent.insertBefore(wrapper, input);
            wrapper.appendChild(input);
        } else {
            wrapper.classList.add('kb-input-wrapper');
            wrapper.style.position = 'relative';
        }

        // Add padding right to input so text doesn't overlap the icon
        const currentPaddingRight = parseInt(window.getComputedStyle(input).paddingRight || '0', 10);
        if (currentPaddingRight < 34) {
            input.style.paddingRight = '34px';
        }

        // Keyboard icon element
        const icon = document.createElement('span');
        icon.className = 'material-icons kb-toggle-icon';
        icon.textContent = 'keyboard';
        icon.title = 'Dotknij, aby włączyć klawiaturę ekranową';
        icon.setAttribute('role', 'button');
        icon.setAttribute('aria-label', 'Włącz klawiaturę ekranową');
        icon.style.cssText = `
            position: absolute;
            right: 6px;
            top: 50%;
            transform: translateY(-50%);
            cursor: pointer;
            color: #94a3b8;
            font-size: 20px;
            padding: 3px;
            border-radius: 6px;
            z-index: 15;
            user-select: none;
            -webkit-user-select: none;
            transition: color 0.15s, background-color 0.15s;
            line-height: 1;
        `;

        icon.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleKeyboard(input, icon);
        });

        wrapper.appendChild(icon);
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
