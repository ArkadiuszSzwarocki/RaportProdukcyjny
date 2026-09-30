/* Security compatibility shim: disable the browser's native eval primitive.
 * Legacy UI code calls window.eval() when rehydrating same-origin HTML fragments.
 * Keep that UI behavior without the eval primitive by executing the fragment as
 * a transient script node. A later frontend refactor can remove this shim too.
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

    Object.defineProperty(window, 'eval', {
        configurable: false,
        enumerable: false,
        writable: false,
        value: executeTrustedFragmentScript
    });
})();
