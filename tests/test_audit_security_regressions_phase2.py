"""Second-pass audit regression tests for findings 39-44."""

from pathlib import Path
import yaml
import pytest


ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path):
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_k8s_requires_explicit_tested_image_and_disallows_latest():
    manifest = _text('k8s/02-app.yaml')
    assert ':latest' not in manifest
    assert manifest.count('sha-REPLACE_WITH_TESTED_COMMIT') == 2
    assert 'imagePullPolicy: IfNotPresent' in manifest


def test_k8s_rwo_storage_does_not_ship_with_multi_replica_hpa():
    storage = _text('k8s/00-namespace-config.yaml')
    app = _text('k8s/02-app.yaml')
    assert storage.count('ReadWriteOnce') >= 3
    assert 'kind: HorizontalPodAutoscaler' not in app
    assert 'replicas: 1' in app


def test_k8s_and_image_use_consistent_non_root_identity_and_seccomp():
    manifest = _text('k8s/02-app.yaml')
    dockerfile = _text('Dockerfile')
    deployment = next(doc for doc in yaml.safe_load_all(manifest) if doc['kind'] == 'Deployment')
    pod = deployment['spec']['template']['spec']
    assert pod['securityContext']['runAsNonRoot'] is True
    assert pod['securityContext']['runAsUser'] == 1000
    assert pod['securityContext']['runAsGroup'] == 1000
    assert pod['securityContext']['seccompProfile']['type'] == 'RuntimeDefault'
    assert {container['name'] for container in pod['containers']} == {'app', 'daemons'}
    for container in pod['containers']:
        security = {**pod['securityContext'], **container.get('securityContext', {})}
        assert security['runAsUser'] == 1000
        assert security['runAsGroup'] == 1000
        assert security['seccompProfile']['type'] == 'RuntimeDefault'
        assert security['allowPrivilegeEscalation'] is False
        assert security['capabilities']['drop'] == ['ALL']
    assert 'groupadd --gid 1000 appgroup' in dockerfile
    assert 'useradd --uid 1000 --gid appgroup --create-home appuser' in dockerfile
    assert 'USER appuser' in dockerfile


def test_non_admin_cannot_modify_system_smtp_config(app):
    from flask import session

    view = app.view_functions['admin.api_email_config_save']
    with app.test_request_context(
        '/api/email/config',
        method='POST',
        json={
            'is_system': True,
            'smtp_server': 'smtp.example.invalid',
            'smtp_username': 'system@example.invalid',
            'smtp_password': 'not-used',
        },
    ):
        session['zalogowany'] = True
        session['user_id'] = 12
        session['login'] = 'ordinary-user'
        session['rola'] = 'pracownik'
        response, status = view()

    assert status == 403
    assert response.get_json()['success'] is False


def test_non_admin_cannot_test_another_users_saved_smtp_secret(app):
    from flask import session

    view = app.view_functions['admin.api_email_test']
    with app.test_request_context(
        '/api/email/test',
        method='POST',
        json={
            'target_user_id': 999,
            'smtp_server': 'attacker.example.invalid',
            'smtp_username': 'victim@example.invalid',
            'smtp_password': '********',
        },
    ):
        session['zalogowany'] = True
        session['user_id'] = 12
        session['login'] = 'ordinary-user'
        session['rola'] = 'pracownik'
        response, status = view()

    assert status == 403
    assert response.get_json()['success'] is False


@pytest.mark.parametrize('endpoint,path,payload,logged_in,expected', [
    ('admin.api_email_config_save', '/api/email/config', {'is_system': True}, True, 403),
    ('admin.api_email_test', '/api/email/test', {'target_user_id': 999}, True, 403),
    ('admin.api_email_test', '/api/email/test', {}, False, 401),
])
def test_smtp_denial_precedes_network_and_saved_secret_lookups(
    app, monkeypatch, endpoint, path, payload, logged_in, expected,
):
    from flask import session

    def forbidden_lookup(*_args, **_kwargs):
        pytest.fail('Unauthorized SMTP request performed a network or secret lookup')

    monkeypatch.setattr('app.core.admin_security_hardening._smtp_target_allowed', forbidden_lookup)
    monkeypatch.setattr('app.core.audit_phase3_hardening._smtp_target_is_safe', forbidden_lookup)
    monkeypatch.setattr(
        'app.repositories.user_email_settings_repository.UserEmailSettingsRepository.get_by_user_id',
        forbidden_lookup,
    )
    with app.test_request_context(path, method='POST', json={
        'smtp_server': 'mail.example.com', 'smtp_port': 587, 'smtp_security': 'TLS',
        'smtp_password': '********', **payload,
    }):
        session.update(zalogowany=logged_in, user_id=12, login='ordinary-user', rola='pracownik')
        response, status = app.view_functions[endpoint]()
    assert status == expected
    assert response.get_json()['success'] is False


def test_global_email_recipient_dictionary_requires_admin(app):
    from flask import session

    view = app.view_functions['admin.api_email_recipient_add']
    with app.test_request_context(
        '/api/email/recipient/add',
        method='POST',
        json={'nazwa': 'Audit', 'email': 'audit@example.invalid'},
    ):
        session['zalogowany'] = True
        session['user_id'] = 12
        session['login'] = 'ordinary-user'
        session['rola'] = 'pracownik'
        response, status = view()

    assert status == 403
    assert response.get_json()['success'] is False


def test_diagnostic_output_redacts_credentials_and_personal_email():
    from app.core.runtime_security_hardening import _redact_sensitive_text

    raw = (
        'mail=user@example.com Authorization: Bearer abcDEF123 '
        'password=SuperSecret123 token=anotherSecret '
        'https://user:password@example.internal/path'
    )
    safe = _redact_sensitive_text(raw)

    assert 'user@example.com' not in safe
    assert 'abcDEF123' not in safe
    assert 'SuperSecret123' not in safe
    assert 'anotherSecret' not in safe
    assert 'user:password@' not in safe
    assert '[REDACTED' in safe


def test_diagnostic_routes_have_final_response_redaction(app):
    assert getattr(
        app.view_functions['admin.admin_ustawienia_logs'],
        '_audit_diagnostic_redaction',
        False,
    )
    assert getattr(
        app.view_functions['admin.ustawienia_errors'],
        '_audit_diagnostic_redaction',
        False,
    )


def test_production_route_local_json_500_is_masked(app):
    from flask import jsonify

    endpoint = '/__audit_route_local_500'
    if 'audit_route_local_500' not in app.view_functions:
        app.add_url_rule(
            endpoint,
            'audit_route_local_500',
            lambda: (jsonify({'success': False, 'message': 'mysql password=leaked-db-secret'}), 500),
            methods=['GET'],
        )

    previous_testing = app.config.get('TESTING')
    previous_debug = app.debug
    app.config['TESTING'] = False
    app.testing = False
    app.debug = False
    try:
        response = app.test_client().get(endpoint)
    finally:
        app.config['TESTING'] = previous_testing
        app.testing = bool(previous_testing)
        app.debug = previous_debug

    assert response.status_code == 500
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['error_code'].startswith('ERR-')
    assert 'leaked-db-secret' not in response.get_data(as_text=True)
