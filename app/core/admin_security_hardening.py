"""Security replacements for sensitive legacy administration endpoints."""

import json
import os
import subprocess
import sys
import tempfile
from functools import wraps

from flask import current_app, jsonify, redirect, render_template, request, session

from app.core.network_security import smtp_target_allowed as _smtp_target_allowed


_ALLOWED_PERMISSION_FIELDS = {'access', 'readonly'}


def _normalized_role():
    return str(session.get('rola') or '').lower().replace(' ', '').replace('_', '').strip()


def _masteradmin_required_json():
    if not bool(session.get('zalogowany')) or _normalized_role() != 'masteradmin':
        return jsonify({'success': False, 'message': 'Wymagana rola masteradmin.'}), 403
    return None


def _permissions_path():
    return os.path.join(current_app.root_path, 'config', 'role_permissions.json')


def _validate_permissions_payload(payload, current_permissions):
    if not isinstance(payload, dict) or not payload:
        return False, 'Konfiguracja uprawnień musi być niepustym obiektem JSON.'
    if not isinstance(current_permissions, dict) or not current_permissions:
        return False, 'Nie można zweryfikować bieżącego schematu uprawnień.'

    expected_pages = set(current_permissions)
    if set(payload) != expected_pages:
        return False, 'Nie wolno dodawać, usuwać ani pomijać kluczy stron w edytorze uprawnień.'

    for page, page_config in payload.items():
        if not isinstance(page, str) or len(page) > 120:
            return False, 'Nieprawidłowy klucz strony.'
        current_page_config = current_permissions.get(page)
        if not isinstance(current_page_config, dict) or not current_page_config:
            return False, f'Nie można zweryfikować schematu ról dla {page}.'
        expected_roles = set(current_page_config)
        if not isinstance(page_config, dict) or set(page_config) != expected_roles:
            return False, f'Nieprawidłowy zestaw ról dla {page}.'
        for role, values in page_config.items():
            if role not in expected_roles or not isinstance(values, dict):
                return False, f'Nieprawidłowa konfiguracja roli dla {page}.'
            if set(values) != _ALLOWED_PERMISSION_FIELDS:
                return False, f'Nieprawidłowe pola uprawnień dla {page}/{role}.'
            if not all(isinstance(values[key], bool) for key in _ALLOWED_PERMISSION_FIELDS):
                return False, f'Uprawnienia {page}/{role} muszą być wartościami logicznymi.'
    return True, ''


def secure_permissions_save():
    """Validate the complete RBAC document and replace it atomically."""
    denied = _masteradmin_required_json()
    if denied is not None:
        return denied

    payload = request.get_json(silent=True)
    path = _permissions_path()
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            current_permissions = json.load(handle)
    except Exception:
        current_app.logger.exception('Could not load current role permissions for validation.')
        return jsonify({'success': False, 'message': 'Nie można bezpiecznie odczytać bieżących uprawnień.'}), 500

    valid, error = _validate_permissions_payload(payload, current_permissions)
    if not valid:
        return jsonify({'success': False, 'message': error}), 400

    directory = os.path.dirname(path)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=directory,
            prefix='.role_permissions.',
            suffix='.tmp',
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
        current_app.logger.warning('Role permissions updated by masteradmin %s', session.get('login'))
        return jsonify({'success': True, 'message': 'Uprawnienia zostały zapisane pomyślnie.'})
    except Exception:
        current_app.logger.exception('Atomic role-permissions update failed.')
        return jsonify({'success': False, 'message': 'Nie udało się bezpiecznie zapisać uprawnień.'}), 500
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def secure_verify_app():
    """Run the fixed verifier without returning or logging stdout/stderr."""
    denied = _masteradmin_required_json()
    if denied is not None:
        return denied

    script_path = os.path.join(current_app.root_path, 'scripts', 'verify_app.py')
    if not os.path.isfile(script_path):
        return jsonify({'success': False, 'message': 'Narzędzie weryfikacyjne jest niedostępne.'}), 404

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=current_app.root_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0:
            return jsonify({'success': True, 'message': 'Weryfikacja aplikacji zakończyła się poprawnie.'})
        current_app.logger.error('verify_app.py failed with code %s.', result.returncode)
        return jsonify({'success': False, 'message': 'Weryfikacja aplikacji wykryła problemy. Szczegóły zapisano w logu serwera.'}), 500
    except subprocess.TimeoutExpired:
        current_app.logger.error('verify_app.py exceeded 30-second timeout.')
        return jsonify({'success': False, 'message': 'Weryfikacja przekroczyła limit czasu.'}), 504
    except Exception:
        current_app.logger.exception('verify_app.py execution failed.')
        return jsonify({'success': False, 'message': 'Nie udało się uruchomić weryfikacji.'}), 500


def _request_payload():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else (request.form or {})


def _smtp_target_guard(original_view):
    """Block SMTP SSRF/port-scanning targets before legacy handlers connect or save them."""
    @wraps(original_view)
    def guarded(*args, **kwargs):
        payload = _request_payload()
        allowed, message = _smtp_target_allowed(
            payload.get('smtp_server'),
            payload.get('smtp_port'),
            payload.get('smtp_security'),
        )
        if not allowed:
            return jsonify({'success': False, 'message': message}), 400
        return original_view(*args, **kwargs)
    return guarded


def secure_email_settings_page():
    """Keep personal SMTP self-service while hiding global SMTP/recipient data from non-admins."""
    if not bool(session.get('zalogowany')):
        return redirect('/login')

    from app.core.database import get_db_connection
    from app.models.user_email_settings_model import UserEmailSettingsModel
    from app.repositories.user_email_settings_repository import UserEmailSettingsRepository

    session_user_id = session.get('user_id')
    user_login = str(session.get('login') or '').strip()
    is_admin = _normalized_role() in {'admin', 'masteradmin'}

    if not session_user_id and user_login:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM uzytkownicy WHERE LOWER(login) = LOWER(%s) LIMIT 1', (user_login,))
            row = cursor.fetchone()
            if row:
                session_user_id = int(row[0])
                session['user_id'] = session_user_id
        finally:
            conn.close()

    if not session_user_id:
        return redirect('/login')

    target_user_id = request.args.get('user_id', type=int) if is_admin else None
    edit_user_id = target_user_id or int(session_user_id)
    repo = UserEmailSettingsRepository()
    user_cfg = repo.get_by_user_id(edit_user_id)

    user_accounts_list = []
    if is_admin:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT u.id, u.login, u.rola, s.smtp_username "
                "FROM uzytkownicy u "
                "LEFT JOIN uzytkownik_email_settings s ON u.id = s.user_id "
                "WHERE u.rola IN ('lider','admin','masteradmin','zarzad','planista') "
                "ORDER BY (s.smtp_username IS NOT NULL) DESC, u.login ASC"
            )
            user_accounts_list = cursor.fetchall() or []
        finally:
            conn.close()
        system_cfg = repo.get_system_config()
        all_recipients = repo.get_all_recipients(only_active=False)
    else:
        system_cfg = UserEmailSettingsModel(
            user_id=0,
            smtp_server='',
            smtp_port=465,
            smtp_security='SSL',
            smtp_username='',
            smtp_password='',
            sender_name='',
        )
        all_recipients = []

    edit_user_login = user_login
    for item in user_accounts_list:
        if int(item.get('id') or 0) == int(edit_user_id):
            edit_user_login = item.get('login') or user_login
            break

    return render_template(
        'ustawienia_email.html',
        user_email_cfg=user_cfg,
        system_config=system_cfg,
        all_recipients=all_recipients,
        default_scope='user' if not is_admin or user_cfg is not None else 'system',
        current_user_login=user_login,
        edit_user_id=edit_user_id,
        edit_user_login=edit_user_login,
        user_accounts_list=user_accounts_list,
        is_admin_user=is_admin,
    )


def _wrap_once(app, endpoint, wrapper, marker):
    original = app.view_functions.get(endpoint)
    if original is None or getattr(original, marker, False):
        return
    guarded = wrapper(original)
    setattr(guarded, marker, True)
    app.view_functions[endpoint] = guarded


def register_admin_security_hardening(app):
    """Replace sensitive legacy admin handlers after blueprint registration."""
    replacements = {
        'admin.admin_master_permissions_save': secure_permissions_save,
        'admin.admin_master_verify': secure_verify_app,
        'admin.admin_ustawienia_email': secure_email_settings_page,
    }
    missing = [name for name in replacements if name not in app.view_functions]
    if missing:
        raise RuntimeError('Admin security hardening missing endpoints: ' + ', '.join(sorted(missing)))
    for endpoint, replacement in replacements.items():
        app.view_functions[endpoint] = replacement

    for endpoint in (
        'admin.api_email_test',
        'admin.api_email_config_save',
        'admin.admin_save_email_settings_magazyn',
        'admin.admin_test_email_settings_magazyn',
    ):
        _wrap_once(app, endpoint, _smtp_target_guard, '_audit_smtp_target_guard')
