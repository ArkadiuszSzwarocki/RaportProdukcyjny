"""Regression coverage for audit points 51-56."""

from io import BytesIO
from pathlib import Path

from flask import Flask
from werkzeug.datastructures import FileStorage


def _upload(name, content):
    return FileStorage(stream=BytesIO(content), filename=name)


def test_quality_upload_rejects_executable_and_spoofed_pdf():
    from app.core.file_security import _quality_upload_valid

    allowed, _ = _quality_upload_valid(_upload('payload.html', b'<script>alert(1)</script>'))
    assert allowed is False

    allowed, _ = _quality_upload_valid(_upload('fake.pdf', b'not really a pdf'))
    assert allowed is False

    allowed, _ = _quality_upload_valid(_upload('ok.pdf', b'%PDF-1.7\n%%EOF'))
    assert allowed is True


def test_bug_uploads_limit_count_size_and_magic():
    from app.core.file_security import _bug_uploads_valid

    png = b'\x89PNG\r\n\x1a\n' + b'x' * 16
    four = [_upload(f'{index}.png', png) for index in range(4)]
    allowed, _ = _bug_uploads_valid(four)
    assert allowed is False

    allowed, _ = _bug_uploads_valid([_upload('fake.png', b'not-png')])
    assert allowed is False

    allowed, _ = _bug_uploads_valid([_upload('ok.png', png)])
    assert allowed is True


def test_report_attachments_cannot_escape_generated_report_roots(tmp_path, monkeypatch):
    from app.core.file_security import report_attachment_path_allowed
    from app.services import shift_close_service

    reports = tmp_path / 'raporty'
    reports_temp = tmp_path / 'raporty_temp'
    reports.mkdir()
    reports_temp.mkdir()
    allowed_file = reports / 'Raport_PSD_2026-09-30.pdf'
    allowed_file.write_bytes(b'%PDF-1.7\n%%EOF')
    outside = tmp_path / 'secret.pdf'
    outside.write_bytes(b'secret')

    monkeypatch.setattr(shift_close_service, 'RAPORTY_DIR', reports)
    monkeypatch.setattr(shift_close_service, 'RAPORTY_TEMP_DIR', reports_temp)

    assert report_attachment_path_allowed(str(allowed_file)) is True
    assert report_attachment_path_allowed(str(outside)) is False
    assert report_attachment_path_allowed('/etc/passwd') is False


def test_file_guards_are_registered_on_sensitive_routes(app):
    expected = {
        'quality.jakosc_detail': '_audit_quality_upload_guard',
        'main.zglos_blad_systemu': '_audit_bug_upload_guard',
        'main.raport_zakoncz_zmiane_wyslij': '_audit_report_attachment_guard',
    }
    for endpoint, marker in expected.items():
        assert getattr(app.view_functions[endpoint], marker, False) is True


def test_database_swap_script_is_shell_free():
    source = (Path(__file__).resolve().parents[1] / 'scripts' / 'podmien_baze.py').read_text(encoding='utf-8')
    assert 'shell=True' not in source
    assert 'shell=False' in source


def test_native_eval_guard_loads_before_legacy_scripts():
    root = Path(__file__).resolve().parents[1]
    layout = (root / 'templates' / 'layout.html').read_text(encoding='utf-8')
    guard = (root / 'static' / 'js' / 'dynamic_eval_guard.js').read_text(encoding='utf-8')

    assert 'dynamic_eval_guard.js' in layout
    assert layout.index('dynamic_eval_guard.js') < layout.index('_layout_footer_scripts.html')
    assert "Object.defineProperty(window, 'eval'" in guard
    assert 'nativeEval(' not in guard


def test_browser_security_headers_are_added():
    from app.core.browser_security import register_browser_security_headers

    test_app = Flask(__name__)
    test_app.config['SESSION_COOKIE_SECURE'] = True

    @test_app.get('/')
    def index():
        return 'ok'

    register_browser_security_headers(test_app)
    response = test_app.test_client().get('/')

    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert response.headers['Referrer-Policy'] == 'same-origin'
    assert "object-src 'none'" in response.headers['Content-Security-Policy']
    assert 'Strict-Transport-Security' in response.headers
