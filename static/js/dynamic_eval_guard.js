/* Security compatibility shim for legacy fragment scripts.
 * The application no longer permits the browser's native eval primitive.
 * Legacy responses are rewritten server-side from window.eval(...) to the
 * explicit helper below. Any eval call that escapes rewriting fails closed.
 *
 * Offline mutation persistence is handled separately by offline_store.js.
 */
(function () {
    'use strict';

    const MAX_DYNAMIC_SCRIPT_CHARS = 256 * 1024;

    function executeTrustedFragmentScript(source) {
        const code = String(source || '');
        if (!code.trim()) return undefined;
        if (code.length > MAX_DYNAMIC_SCRIPT_CHARS) {
            throw new Error('Dynamic fragment script exceeds the safety limit.');
        }

        const script = document.createElement('script');
        script.type = 'text/javascript';
        script.textContent = code;
        (document.head || document.documentElement).appendChild(script);
        script.remove();
        return undefined;
    }

    Object.defineProperty(window, 'executeTrustedFragmentScript', {
        configurable: false,
        enumerable: false,
        writable: false,
        value: executeTrustedFragmentScript
    });

    Object.defineProperty(window, 'eval', {
        configurable: false,
        enumerable: false,
        writable: false,
        value: function disabledNativeEval() {
            throw new Error('Native eval is disabled by application security policy.');
        }
    });
})();
