from pathlib import Path

from flask import Flask, Response

from app.core.browser_security import (
    SOCKET_IO_CDN_TAG,
    SOCKET_IO_SRI_TAG,
    register_browser_security_headers,
)


def _build_test_app():
    app = Flask(__name__, static_folder=None)

    @app.get('/audit-html')
    def audit_html():
        return Response(
            SOCKET_IO_CDN_TAG + '<script>window.eval("window.__audit = true")</script>',
            mimetype='text/html',
        )

    @app.get('/audit-js')
    def audit_js():
        return Response(
            'window.eval("window.__audit = true");',
            mimetype='application/javascript',
        )

    @app.get('/audit-legacy-queue.js')
    def audit_legacy_queue_js():
        return Response(
            "const data = localStorage.getItem(this.queueKey);\n"
            "localStorage.setItem(this.queueKey, JSON.stringify(queue));",
            mimetype='application/javascript',
        )

    @app.get('/static/audit.js')
    def audit_static_js():
        return Response('window.__staticAudit = true;', mimetype='application/javascript')

    register_browser_security_headers(app)
    return app


def test_legacy_window_eval_is_rewritten_at_response_boundary():
    app = _build_test_app()
    client = app.test_client()

    html = client.get('/audit-html').get_data(as_text=True)
    js = client.get('/audit-js').get_data(as_text=True)

    assert 'window.eval(' not in html
    assert 'window.eval(' not in js
    assert 'window.executeTrustedFragmentScript(' in html
    assert 'window.executeTrustedFragmentScript(' in js

    guard = Path('static/js/dynamic_eval_guard.js').read_text(encoding='utf-8')
    assert "Object.defineProperty(window, 'executeTrustedFragmentScript'" in guard
    assert "Object.defineProperty(window, 'eval'" in guard
    assert 'disabledNativeEval' in guard
    assert 'Native eval is disabled by application security policy.' in guard


def test_socket_io_cdn_tag_receives_subresource_integrity():
    app = _build_test_app()
    client = app.test_client()

    html = client.get('/audit-html').get_data(as_text=True)

    assert SOCKET_IO_CDN_TAG not in html
    assert SOCKET_IO_SRI_TAG in html
    assert 'integrity="sha384-mZLF4UVrpi/QTWPA7BjNPEnkIfRFn4ZEO3Qt/HFklTJBj/gBOV8G3HcKn4NfQblz"' in html
    assert 'crossorigin="anonymous"' in html


def test_dynamic_responses_are_explicitly_non_cacheable():
    app = _build_test_app()
    client = app.test_client()

    response = client.get('/audit-html')

    assert response.headers['Cache-Control'] == 'no-store, private, max-age=0'
    assert response.headers['Pragma'] == 'no-cache'
    assert response.headers['Expires'] == '0'

    static_response = client.get('/static/audit.js')
    assert static_response.headers.get('Cache-Control') != 'no-store, private, max-age=0'


def test_legacy_mutation_queue_is_rewritten_to_ephemeral_memory():
    app = _build_test_app()
    client = app.test_client()

    js = client.get('/audit-legacy-queue.js').get_data(as_text=True)

    assert 'localStorage.getItem(this.queueKey)' not in js
    assert 'localStorage.setItem(this.queueKey, JSON.stringify(queue))' not in js
    assert 'window.__ephemeralMutationStorage.getItem(this.queueKey)' in js
    assert 'window.__ephemeralMutationStorage.setItem(this.queueKey, JSON.stringify(queue))' in js

    guard = Path('static/js/dynamic_eval_guard.js').read_text(encoding='utf-8')
    assert "'agromes_offline_queue'" in guard
    assert "'rp_offline_scan_buffer'" in guard
    assert 'localStorage.removeItem(key)' in guard
    assert "window.addEventListener('pagehide'" in guard


def test_service_worker_never_caches_authenticated_navigation():
    sw = Path('static/sw.js').read_text(encoding='utf-8')

    assert "const CACHE_NAME = 'rp-pwa-static-v3';" in sw
    assert "    '/'," not in sw
    assert "url.pathname.startsWith('/static/')" in sw
    assert "fetch(request, { cache: 'no-store' })" in sw
    assert "if (!isSameOriginStatic(url))" in sw
    assert "caches.match('/static/offline_fallback.html')" in sw


def test_scanner_offline_mutations_are_memory_only():
    scanner = Path('static/js/offline_scan_buffer.js').read_text(encoding='utf-8')

    assert 'localStorage.setItem' not in scanner
    assert 'localStorage.getItem' not in scanner
    assert 'sessionStorage.setItem' not in scanner
    assert 'sessionStorage.getItem' not in scanner
    assert 'this.queue = []' in scanner
    assert "window.addEventListener('pagehide'" in scanner
    assert 'response.status === 401 || response.status === 403' in scanner
