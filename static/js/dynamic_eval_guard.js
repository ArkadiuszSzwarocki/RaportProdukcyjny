/* Security compatibility shim for legacy fragment scripts.
 * The application no longer permits the browser's native eval primitive.
 * Legacy responses are rewritten server-side from window.eval(...) to the
 * explicit helper below. Any eval call that escapes rewriting fails closed.
 *
 * This file is loaded before legacy scripts and also exposes a tiny in-memory
 * store for security-sensitive offline mutation queues. Such queues must not be
 * persisted in localStorage because they could otherwise be replayed under a
 * different authenticated user after logout/login on the same workstation.
 */
(function () {
    'use strict';

    const MAX_DYNAMIC_SCRIPT_CHARS = 256 * 1024;
    const SENSITIVE_MUTATION_KEYS = [
        'agromes_offline_queue',
        'rp_offline_scan_buffer'
    ];
    const ephemeralMutationMap = new Map();

    // Remove any queues written by pre-hardening application versions.
    try {
        SENSITIVE_MUTATION_KEYS.forEach((key) => localStorage.removeItem(key));
    } catch (e) {
        // Storage may be unavailable in hardened/private browser contexts.
    }

    const ephemeralMutationStorage = Object.freeze({
        getItem(key) {
            const normalized = String(key || '');
            return ephemeralMutationMap.has(normalized)
                ? ephemeralMutationMap.get(normalized)
                : null;
        },
        setItem(key, value) {
            const normalized = String(key || '');
            if (!SENSITIVE_MUTATION_KEYS.includes(normalized)) {
                throw new Error('Persistent mutation storage key is not allowed.');
            }
            ephemeralMutationMap.set(normalized, String(value));
        },
        removeItem(key) {
            ephemeralMutationMap.delete(String(key || ''));
        },
        clear() {
            ephemeralMutationMap.clear();
        }
    });

    Object.defineProperty(window, '__ephemeralMutationStorage', {
        configurable: false,
        enumerable: false,
        writable: false,
        value: ephemeralMutationStorage
    });

    // A queued mutation is valid only for the lifetime of the current page.
    // This also clears memory before a page can be restored from the BFCache.
    window.addEventListener('pagehide', () => {
        ephemeralMutationStorage.clear();
    });

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
