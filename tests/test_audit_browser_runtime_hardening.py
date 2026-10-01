from pathlib import Path

from flask import Flask, Response

from app.core.browser_security import (
    SOCKET_IO_CDN_TAG,
    SOCKET_IO_SRI_TAG,
    register_browser_security_headers,
)


def _build_test_app():
    app = Flask(__name__, static_folder=None)
    app.secret_key = 'audit-test-secret'

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
            "localStorage.setItem(this.queueKey, JSON.stringify(queue));\n"
            "window.OfflineQueue = new OfflineQueueManager();",
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


def test_dynamic_responses_are_non_cacheable_but_identify_offline_owner():
    app = _build_test_app()
    client = app.test_client()

    anonymous_response = client.get('/audit-html')
    assert anonymous_response.headers['Cache-Control'] == 'no-store, private, max-age=0'
    assert anonymous_response.headers['Pragma'] == 'no-cache'
    assert anonymous_response.headers['Expires'] == '0'
    assert anonymous_response.headers['X-RP-Offline-User'] == 'anonymous'
    assert 'Cookie' in anonymous_response.headers['Vary']

    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['user_id'] = 17

    authenticated_response = client.get('/audit-html')
    assert authenticated_response.headers['X-RP-Offline-User'] == '17'

    static_response = client.get('/static/audit.js')
    assert static_response.headers.get('Cache-Control') != 'no-store, private, max-age=0'
    assert static_response.headers.get('X-RP-Offline-User') is None


def test_legacy_generic_queue_is_redirected_to_indexeddb_compatibility_store():
    app = _build_test_app()
    client = app.test_client()

    js = client.get('/audit-legacy-queue.js').get_data(as_text=True)

    assert 'localStorage.getItem(this.queueKey)' not in js
    assert 'localStorage.setItem(this.queueKey, JSON.stringify(queue))' not in js
    assert 'window.__offlineMutationStorage.getItem(this.queueKey)' in js
    assert 'window.__offlineMutationStorage.setItem(this.queueKey, JSON.stringify(queue))' in js
    assert 'window.RPOfflineStore.whenReady' in js
    assert 'window.OfflineQueue.sync()' in js

    store = Path('static/js/offline_store.js').read_text(encoding='utf-8')
    assert "const DB_NAME = 'raportprodukcyjny_offline_v2';" in store
    assert "'agromes_offline_queue'" in store
    assert "'rp_offline_scan_buffer'" in store
    assert 'owner_user_id: ownerUserId' in store
    assert "global.indexedDB.open(DB_NAME, DB_VERSION)" in store
    assert "Object.defineProperty(global, '__offlineMutationStorage'" in store


def test_layout_loads_indexeddb_store_before_legacy_runtime():
    layout = Path('templates/layout.html').read_text(encoding='utf-8')

    assert 'window.__RP_OFFLINE_USER_ID' in layout
    assert "filename='js/offline_store.js'" in layout
    assert "filename='js/dynamic_eval_guard.js'" in layout
    assert layout.index("filename='js/offline_store.js'") < layout.index("filename='js/dynamic_eval_guard.js'")


def test_service_worker_partitions_cached_navigation_by_user():
    sw = Path('static/sw.js').read_text(encoding='utf-8')

    assert "const STATIC_CACHE_NAME = 'rp-pwa-static-v4';" in sw
    assert "const PAGE_CACHE_PREFIX = 'rp-pwa-pages-v2-user-';" in sw
    assert "const META_CACHE_NAME = 'rp-pwa-meta-v2';" in sw
    assert "    '/'," not in sw
    assert "'/static/js/offline_store.js'" in sw
    assert "url.pathname.startsWith('/static/')" in sw
    assert "fetch(request, { cache: 'no-store' })" in sw
    assert "networkResponse.headers.get('X-RP-Offline-User')" in sw
    assert 'pageCacheName(userId)' in sw
    assert 'await setActiveUser(null)' in sw
    assert 'const cachedPage = await getCachedNavigation(request)' in sw
    assert "data.type !== 'RP_SET_OFFLINE_USER'" in sw


def test_scanner_queue_is_durable_and_user_scoped():
    scanner = Path('static/js/offline_scan_buffer.js').read_text(encoding='utf-8')

    assert "const QUEUE_KEY = 'rp_offline_scan_buffer';" in scanner
    assert 'global.RPOfflineStore.getQueue(QUEUE_KEY)' in scanner
    assert 'global.RPOfflineStore.setQueue(QUEUE_KEY, this.queue)' in scanner
    assert 'localStorage.setItem' not in scanner
    assert 'localStorage.getItem' not in scanner
    assert 'sessionStorage.setItem' not in scanner
    assert 'sessionStorage.getItem' not in scanner
    assert "window.addEventListener('pagehide'" in scanner
    assert 'this.queue = []' not in scanner.split("window.addEventListener('pagehide'", 1)[1]
    assert 'response.status === 401 || response.status === 403' in scanner
    assert 'this.authBlocked = true' in scanner


def test_pwa_initializer_publishes_user_scope_to_service_worker():
    pwa = Path('static/js/pwa_init.js').read_text(encoding='utf-8')

    assert 'window.__RP_OFFLINE_USER_ID' in pwa
    assert "type: 'RP_SET_OFFLINE_USER'" in pwa
    assert 'worker.postMessage(payload)' in pwa
    assert "navigator.serviceWorker.register('/sw.js', { scope: '/' })" in pwa
