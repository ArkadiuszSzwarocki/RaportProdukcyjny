from pathlib import Path

from flask import Flask, Response

from app.core.browser_security import (
    SOCKET_IO_CDN_TAG,
    SOCKET_IO_SRI_TAG,
    register_browser_security_headers,
)


def _build_test_app():
    app = Flask(__name__)

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
