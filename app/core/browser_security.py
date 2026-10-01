"""Browser-facing response security headers and frontend response hardening."""

from flask import request

SOCKET_IO_CDN_TAG = '<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>'
SOCKET_IO_SRI_TAG = (
    '<script src="https://cdn.socket.io/4.7.2/socket.io.min.js" '
    'integrity="sha384-mZLF4UVrpi/QTWPA7BjNPEnkIfRFn4ZEO3Qt/HFklTJBj/gBOV8G3HcKn4NfQblz" '
    'crossorigin="anonymous"></script>'
)
_TEXT_MIMETYPES = {'text/html', 'application/javascript', 'text/javascript'}


def _rewrite_frontend_security(response):
    """Apply narrow, deterministic compatibility rewrites to browser code.

    The legacy UI still contains a few ``window.eval(...)`` calls in very large
    files. Rewriting them at the response boundary avoids native eval without a
    risky whole-file rewrite. The explicit helper is installed before legacy JS.

    The legacy generic offline mutation queue also used persistent localStorage.
    Its exact storage calls are rewritten to the in-memory security store exposed
    by ``dynamic_eval_guard.js`` so queued writes cannot survive a user/session
    change in the browser.

    Socket.IO is currently loaded from a versioned CDN URL. Attach an SRI hash
    so a modified CDN response is rejected by the browser.
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
            'window.__ephemeralMutationStorage.getItem(this.queueKey)',
        )
        rewritten = rewritten.replace(
            'localStorage.setItem(this.queueKey, JSON.stringify(queue))',
            'window.__ephemeralMutationStorage.setItem(this.queueKey, JSON.stringify(queue))',
        )
    if mimetype == 'text/html':
        rewritten = rewritten.replace(SOCKET_IO_CDN_TAG, SOCKET_IO_SRI_TAG)

    if rewritten != original:
        response.set_data(rewritten)
    return response


def register_browser_security_headers(app) -> None:
    """Add browser controls and forbid client/proxy caching of dynamic responses."""

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

        # Dynamic/authenticated responses must never be retained by a browser,
        # service worker or shared proxy. Static assets keep their normal cache
        # policy and are the only resources the service worker may persist.
        path = str(getattr(request, 'path', '') or '')
        if not path.startswith('/static/') and path not in {'/sw.js', '/favicon.ico'}:
            response.headers['Cache-Control'] = 'no-store, private, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains',
            )
        return response
