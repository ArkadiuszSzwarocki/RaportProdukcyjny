// file: static/js/scanner/keyboard-blocker.js
document.addEventListener('DOMContentLoaded', function() {
    // Check if current page is a scanner interface
    const isScanner = window.location.pathname.toLowerCase().includes('skaner') || 
                      window.location.pathname.toLowerCase().includes('scanner') ||
                      document.getElementById('scanInput') !== null ||
                      document.querySelector('.scanner-wrap') !== null ||
                      document.querySelector('.inventory-scanner') !== null ||
                      document.getElementById('splitScannerInput') !== null ||
                      document.getElementById('globalScannerInput') !== null;

    if (!isScanner) return;

    function toggleKeyboard(input, icon) {
        if (input.dataset.forceKb === 'true') {
            input.dataset.forceKb = 'false';
            input.setAttribute('inputmode', 'none');
            icon.style.color = '#94a3b8';
            input.blur();
        } else {
            input.dataset.forceKb = 'true';
            input.removeAttribute('inputmode');
            input.setAttribute('inputmode', 'text');
            icon.style.color = '#3b82f6';
            input.focus();
        }
    }

    function initScannerKeyboards() {
        // Find all text/number inputs that are not readonly
        const inputs = document.querySelectorAll('input[type="text"]:not([readonly]), input[type="number"]:not([readonly]), input:not([type]):not([readonly])');
        inputs.forEach(input => {
            if (input.dataset.kbAttached) return;
            if (input.type === 'hidden' || input.type === 'checkbox' || input.type === 'radio' || input.type === 'submit' || input.type === 'date' || input.type === 'time') return;
            
            input.dataset.kbAttached = 'true';
            
            // Force inputmode none so virtual keyboard doesn't pop up
            input.setAttribute('inputmode', 'none');
            
            // If user taps the input while forceKb is not active, ensure it stays none
            input.addEventListener('click', () => {
                if (input.dataset.forceKb !== 'true') {
                    input.setAttribute('inputmode', 'none');
                }
            });

            // Wrap the input to position the icon
            const parent = input.parentElement;
            
            // If the parent is already a relative flex wrapper with just this input and an icon, we might not need to wrap.
            // But wrapping is universally safer if we copy dimensions.
            const wrapper = document.createElement('div');
            wrapper.className = 'kb-wrapper';
            wrapper.style.position = 'relative';
            const displayStyle = window.getComputedStyle(input).display;
            wrapper.style.display = displayStyle === 'block' ? 'block' : (displayStyle.includes('inline') ? 'inline-block' : 'flex');
            
            wrapper.style.width = input.style.width || window.getComputedStyle(input).width;
            if (wrapper.style.width === '0px' || wrapper.style.width === 'auto') {
                if (input.classList.contains('w-full') || input.classList.contains('form-control') || input.style.width === '100%') {
                    wrapper.style.width = '100%';
                }
            }
            if (input.style.flex) wrapper.style.flex = input.style.flex;
            if (input.style.flexGrow) wrapper.style.flexGrow = input.style.flexGrow;
            
            // Move margins from input to wrapper
            if (input.style.marginBottom) { wrapper.style.marginBottom = input.style.marginBottom; input.style.marginBottom = '0'; }
            if (input.style.marginTop) { wrapper.style.marginTop = input.style.marginTop; input.style.marginTop = '0'; }
            if (input.style.marginLeft) { wrapper.style.marginLeft = input.style.marginLeft; input.style.marginLeft = '0'; }
            if (input.style.marginRight) { wrapper.style.marginRight = input.style.marginRight; input.style.marginRight = '0'; }
            
            parent.insertBefore(wrapper, input);
            wrapper.appendChild(input);
            
            if (wrapper.style.width === '100%') {
                input.style.width = '100%';
            }

            // Make space for the icon inside the input
            const currentPaddingRight = parseInt(window.getComputedStyle(input).paddingRight || '0');
            if (currentPaddingRight < 36) {
                input.style.paddingRight = '36px';
            }

            const icon = document.createElement('span');
            icon.className = 'material-icons';
            icon.textContent = 'keyboard';
            icon.title = "Pokaż/Ukryj Klawiaturę";
            icon.style.position = 'absolute';
            icon.style.right = '8px';
            icon.style.top = '50%';
            icon.style.transform = 'translateY(-50%)';
            icon.style.cursor = 'pointer';
            icon.style.color = '#94a3b8'; // Slate color
            icon.style.fontSize = '22px';
            icon.style.zIndex = '10';
            icon.style.userSelect = 'none';

            icon.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                toggleKeyboard(input, icon);
            });

            wrapper.appendChild(icon);
        });
    }

    // Initialize on page load
    initScannerKeyboards();
    
    // Observer for dynamically added inputs (like modals)
    const observer = new MutationObserver((mutations) => {
        let added = false;
        for (let m of mutations) {
            if (m.addedNodes.length > 0) { added = true; break; }
        }
        if (added) {
            setTimeout(initScannerKeyboards, 100);
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
});
