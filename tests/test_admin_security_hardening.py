"""Regression coverage for audit points 45-50."""

from types import SimpleNamespace


def _sample_permissions():
    return {
        'page.one': {
            'admin': {'access': True, 'readonly': False},
            'pracownik': {'access': False, 'readonly': True},
        },
        'page.two': {
            'admin': {'access': True, 'readonly': False},
            'pracownik': {'access': True, 'readonly': False},
        },
    }


def test_permission_editor_rejects_schema_changes_and_non_boolean_values():
    from app.core.admin_security_hardening import _validate_permissions_payload

    current = _sample_permissions()
    valid, _ = _validate_permissions_payload(current, current)
    assert valid is True

    missing_page = {'page.one': current['page.one']}
    valid, _ = _validate_permissions_payload(missing_page, current)
    assert valid is False

    injected = _sample_permissions()
    injected['page.one']['admin']['access'] = 'yes'
    valid, _ = _validate_permissions_payload(injected, current)
    assert valid is False


def test_permission_editor_preserves_each_pages_existing_role_set():
    from app.core.admin_security_hardening import _validate_permissions_payload

    current = _sample_permissions()
    current['page.two'].pop('pracownik')
    payload = _sample_permissions()
    payload['page.two'].pop('pracownik')

    valid, _ = _validate_permissions_payload(payload, current)
    assert valid is True


def test_sensitive_admin_endpoints_are_replaced(app):
    from app.core.admin_security_hardening import (
        secure_email_settings_page,
        secure_permissions_save,
        secure_verify_app,
    )

    assert app.view_functions['admin.admin_master_permissions_save'] is secure_permissions_save
    assert app.view_functions['admin.admin_master_verify'] is secure_verify_app
    assert app.view_functions['admin.admin_ustawienia_email'] is secure_email_settings_page


def test_backup_download_accepts_only_generated_sql_backup_names():
    from app.blueprints.admin.backups import _is_valid_backup_filename

    assert _is_valid_backup_filename('db-backup-20260930-190000.sql') is True
    assert _is_valid_backup_filename('../db-backup-file.sql') is False
    assert _is_valid_backup_filename('other.sql') is False
    assert _is_valid_backup_filename('db-backup-20260930.zip') is False
    assert _is_valid_backup_filename('db-backup-../../file.sql') is False


def test_verify_endpoint_never_returns_subprocess_output(app, monkeypatch):
    from flask import session
    from app.core import admin_security_hardening as hardening

    monkeypatch.setattr(hardening.os.path, 'isfile', lambda _path: True)
    monkeypatch.setattr(
        hardening.subprocess,
        'run',
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout='SENSITIVE_VALUE\n/home/app/private/path',
            stderr='internal diagnostic detail',
        ),
    )

    with app.test_request_context('/admin/master/verify'):
        session['zalogowany'] = True
        session['rola'] = 'masteradmin'
        response, status = hardening.secure_verify_app()

    assert status == 500
    body = response.get_json()
    assert body['success'] is False
    serialized = str(body)
    assert 'SENSITIVE_VALUE' not in serialized
    assert '/home/app/private/path' not in serialized
    assert 'internal diagnostic detail' not in serialized


def test_smtp_defaults_do_not_embed_real_provider_or_account():
    from app.models.user_email_settings_model import UserEmailSettingsModel
    from app.repositories.user_email_settings_repository import UserEmailSettingsRepository

    defaults = UserEmailSettingsRepository.DEFAULT_SYSTEM_CONFIG
    assert defaults['smtp_server'] != 'smtp.wp.pl'
    assert '@' not in defaults['smtp_username']
    assert UserEmailSettingsModel().smtp_server == ''


def test_non_admin_email_page_does_not_load_global_smtp_or_recipients(app, monkeypatch):
    from flask import session
    from app.core import admin_security_hardening as hardening
    from app.models.user_email_settings_model import UserEmailSettingsModel
    from app.repositories.user_email_settings_repository import UserEmailSettingsRepository

    monkeypatch.setattr(
        UserEmailSettingsRepository,
        'get_by_user_id',
        lambda self, _user_id: UserEmailSettingsModel(
            user_id=7,
            smtp_server='smtp.user.example',
            smtp_username='user@example.com',
            smtp_password='placeholder',
        ),
    )
    monkeypatch.setattr(
        UserEmailSettingsRepository,
        'get_system_config',
        lambda self: (_ for _ in ()).throw(AssertionError('global SMTP must not be loaded')),
    )
    monkeypatch.setattr(
        UserEmailSettingsRepository,
        'get_all_recipients',
        lambda self, only_active=False: (_ for _ in ()).throw(AssertionError('recipient directory must not be loaded')),
    )

    captured = {}

    def fake_render(_template, **kwargs):
        captured.update(kwargs)
        return 'ok'

    monkeypatch.setattr(hardening, 'render_template', fake_render)

    with app.test_request_context('/moje_konto_email'):
        session['zalogowany'] = True
        session['user_id'] = 7
        session['login'] = 'worker'
        session['rola'] = 'pracownik'
        assert hardening.secure_email_settings_page() == 'ok'

    assert captured['all_recipients'] == []
    assert captured['system_config'].smtp_username == ''
    assert captured['system_config'].smtp_password == ''
    assert captured['is_admin_user'] is False


def test_smtp_target_policy_blocks_internal_network_and_non_smtp_ports(monkeypatch):
    from app.core import network_security

    monkeypatch.delenv('SMTP_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('SMTP_ALLOW_PRIVATE_HOSTS', raising=False)
    monkeypatch.delenv('SMTP_ALLOW_PLAINTEXT', raising=False)
    monkeypatch.setattr(
        network_security.socket,
        'getaddrinfo',
        lambda *args, **kwargs: [
            (network_security.socket.AF_INET, network_security.socket.SOCK_STREAM, 6, '', ('127.0.0.1', 465))
        ],
    )

    allowed, _ = network_security.smtp_target_allowed('localhost', 465, 'SSL')
    assert allowed is False

    allowed, _ = network_security.smtp_target_allowed('mail.example.com', 22, 'SSL')
    assert allowed is False

    allowed, _ = network_security.smtp_target_allowed('mail.example.com', 25, 'NONE')
    assert allowed is False


def test_smtp_private_host_requires_explicit_allowlist(monkeypatch):
    from app.core import network_security

    monkeypatch.setenv('SMTP_ALLOWED_HOSTS', 'mail.internal.example')
    monkeypatch.setattr(
        network_security.socket,
        'getaddrinfo',
        lambda *args, **kwargs: [
            (network_security.socket.AF_INET, network_security.socket.SOCK_STREAM, 6, '', ('10.10.10.10', 587))
        ],
    )

    allowed, _ = network_security.smtp_target_allowed('mail.internal.example', 587, 'TLS')
    assert allowed is True


def test_smtp_mutation_and_test_routes_have_target_guard(app):
    for endpoint in (
        'admin.api_email_test',
        'admin.api_email_config_save',
        'admin.admin_save_email_settings_magazyn',
        'admin.admin_test_email_settings_magazyn',
    ):
        assert getattr(app.view_functions[endpoint], '_audit_smtp_target_guard', False) is True


def test_email_service_rechecks_stored_smtp_target_before_sending(monkeypatch):
    from app.services.email_service import EmailService

    service = EmailService()
    monkeypatch.setattr(
        service,
        'get_smtp_config_for_user',
        lambda _user_id=None: {
            'server': '127.0.0.1',
            'port': 25,
            'security': 'TLS',
            'username': 'user@example.com',
            'password': 'placeholder',
            'sender_name': 'Audit',
            'is_custom': True,
            'configured': True,
        },
    )
    monkeypatch.setattr(
        'app.services.email_service.smtp_target_allowed',
        lambda *_args, **_kwargs: (False, 'blocked'),
    )

    ok, message = service.send_report_email(['dest@example.com'], 'Test', '<p>Test</p>')
    assert ok is False
    assert 'zablokowana' in message.lower()
