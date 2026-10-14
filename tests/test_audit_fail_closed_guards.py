"""Regression tests for fail-closed guards found during the second audit."""

from flask import Flask, session


def test_false_logged_in_flag_is_cleared_before_legacy_guards():
    from app.core.security_hardening import register_role_integrity_check

    app = Flask(__name__)
    app.secret_key = 'audit-test-secret'
    app.config['TESTING'] = True
    register_role_integrity_check(app)

    @app.get('/probe')
    def probe():
        return 'logged-in' if session.get('zalogowany') else 'anonymous'

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['zalogowany'] = False
        sess['rola'] = 'admin'
        sess['login'] = 'stale-user'

    response = client.get('/probe')
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'anonymous'

    with client.session_transaction() as sess:
        assert 'zalogowany' not in sess
        assert 'rola' not in sess
        assert 'login' not in sess


def test_raw_material_dictionary_db_failure_fails_closed(monkeypatch):
    from app.utils import surowiec_validator as validator

    validator.invalidate_cache()

    def _raise_db_error():
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(validator, 'get_db_connection', _raise_db_error)

    assert validator.is_valid_surowiec('Dowolny surowiec') is False
    ok, message = validator.validate_surowiec_name('Dowolny surowiec')
    assert ok is False
    assert 'Nie można teraz zweryfikować surowca' in message


def test_empty_raw_material_dictionary_fails_closed(monkeypatch):
    from app.utils import surowiec_validator as validator

    class EmptyCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchall(self):
            return []

        def close(self):
            return None

    class EmptyConnection:
        def cursor(self, **_kwargs):
            return EmptyCursor()

        def close(self):
            return None

    validator.invalidate_cache()
    monkeypatch.setattr(validator, 'get_db_connection', lambda: EmptyConnection())

    assert validator.is_valid_surowiec('Dowolny surowiec') is False
    ok, message = validator.validate_surowiec_name('Dowolny surowiec')
    assert ok is False
    assert 'Słownik surowców jest pusty' in message
