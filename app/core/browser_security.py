"""Browser-facing response security headers and frontend response hardening."""

from flask import request, session

SOCKET_IO_CDN_TAG = '<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>'
SOCKET_IO_SRI_TAG = (
    '<script src="https://cdn.socket.io/4.7.2/socket.io.min.js" '
    'integrity="sha384-mZLF4UVrpi/QTWPA7BjNPEnkIfRFn4ZEO3Qt/HFklTJBj/gBOV8G3HcKn4NfQblz" '
    'crossorigin="anonymous"></script>'
)
_TEXT_MIMETYPES = {'text/html', 'application/javascript', 'text/javascript'}
_LEGACY_QUEUE_INIT = 'window.OfflineQueue = new OfflineQueueManager();'
_SCOPED_QUEUE_INIT = _LEGACY_QUEUE_INIT + """
if (window.RPOfflineStore) {
    window.RPOfflineStore.whenReady(function () {
        try {
            if (window.OfflineQueue && typeof window.OfflineQueue.updateIndicator === 'function') {
                window.OfflineQueue.updateIndicator();
            }
            if (navigator.onLine && window.OfflineQueue && typeof window.OfflineQueue.sync === 'function') {
                window.OfflineQueue.sync();
            }
        } catch (e) {
            console.warn('[OfflineQueue] Failed to resume persisted queue.', e);
        }
    });
}
"""


def _rewrite_frontend_security(response):
    """Apply narrow compatibility rewrites to legacy browser code.

    Native ``window.eval`` is replaced by the explicit fragment executor. The
    old generic mutation queue still contains synchronous localStorage calls;
    those exact calls are redirected to the user-scoped IndexedDB compatibility
    store exposed by ``offline_store.js``. This preserves the old queue API
    without allowing one user's writes to replay under another user's session.
    """
    if getattr(response, 'direct_passthrough', False):
        return response
    if response.status_code in (204, 304):
        return response

    mimetype = str(getattr(response, 'mimetype', '') or '').lower()
    if mimetype not in _TEXT_MIMETYPES:
        return response

    try:
        original = response.get_data(as_text=True)
    except (RuntimeError, UnicodeError):
        return response

    rewritten = original.replace(
        'window.eval(',
        'window.executeTrustedFragmentScript(',
    )
    if mimetype in {'application/javascript', 'text/javascript'}:
        rewritten = rewritten.replace(
            'localStorage.getItem(this.queueKey)',
            'window.__offlineMutationStorage.getItem(this.queueKey)',
        )
        rewritten = rewritten.replace(
            'localStorage.setItem(this.queueKey, JSON.stringify(queue))',
            'window.__offlineMutationStorage.setItem(this.queueKey, JSON.stringify(queue))',
        )
        rewritten = rewritten.replace(_LEGACY_QUEUE_INIT, _SCOPED_QUEUE_INIT)
        rewritten = rewritten.replace(
            'fetch(item.url, item.options)',
            'fetch(item.url, window.RPOfflineStore.withOwner(item.options))',
        )

    if mimetype == 'text/html':
        rewritten = rewritten.replace(SOCKET_IO_CDN_TAG, SOCKET_IO_SRI_TAG)

    if rewritten != original:
        response.set_data(rewritten)
    return response


def _offline_user_header_value() -> str:
    """Return a non-secret cache partition id for the current authenticated user."""
    if not bool(session.get('zalogowany')):
        return 'anonymous'
    user_id = session.get('user_id')
    candidate = str(user_id or '').strip()
    return candidate if candidate.isdigit() else 'anonymous'


def register_browser_security_headers(app) -> None:
    """Add browser controls and partition offline data by authenticated user."""

    @app.before_request
    def _offline_mutation_owner():
        owner = request.headers.get('X-RP-Offline-Owner')
        if owner is None or request.method in {'GET', 'HEAD', 'OPTIONS'}:
            return None
        from flask import jsonify

        active_owner = _offline_user_header_value()
        if active_owner == 'anonymous' or str(owner).strip() != active_owner:
            return jsonify({'success': False, 'error': 'offline_owner_mismatch'}), 403
        return None

    @app.after_request
    def _browser_security_headers(response):
        response = _rewrite_frontend_security(response)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
        )
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.headers.setdefault(
            'Content-Security-Policy',
            "object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
        )

        path = str(getattr(request, 'path', '') or '')
        is_dynamic = not path.startswith('/static/') and path not in {'/sw.js', '/favicon.ico'}
        if is_dynamic:
            # Browsers and shared proxies must not use their ordinary HTTP cache
            # for authenticated pages. The service worker may keep an explicit
            # per-user copy for offline operation, selected by this header.
            response.headers['Cache-Control'] = 'no-store, private, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.headers['X-RP-Offline-User'] = _offline_user_header_value()

            vary_values = {
                item.strip()
                for item in str(response.headers.get('Vary') or '').split(',')
                if item.strip()
            }
            vary_values.add('Cookie')
            response.headers['Vary'] = ', '.join(sorted(vary_values))

        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains',
            )
        return response
