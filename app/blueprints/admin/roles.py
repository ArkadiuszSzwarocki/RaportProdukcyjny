import json
import os

from flask import current_app, jsonify, render_template, request, session

from app.core.audit import audit_log
from app.db import get_db_connection
from app.decorators import dynamic_role_required, login_required, masteradmin_required


ROLES_PAGES = [
    'dashboard',
    'ustawienia',
    'jakosc',
    'planista',
    'plan',
    'zasyp',
    'workowanie',
    'magazyn',
    'agro_magazyn',
    'bufor',
    'moje_godziny',
    'awarie',
    'wyniki',
    'podsumowanie_zasypow',
    'dosypki',
    'logs',
    'errors',
    'centrum',
    'performance',
    'baza_danych',
]

ROLES_PAGE_ALIASES = {
    'podsumowanie_zasypow': 'podsumowanie_szarz',
}

ROLES_USERS_PAGES = ['dashboard', 'ustawienia', 'jakosc', 'planista', 'plan', 'zasyp', 'workowanie', 'magazyn', 'bufor', 'moje_godziny', 'awarie', 'wyniki']

ROLE_NAME_MAPPING = {
    'laborant': 'laborant',
}


def _project_config_path(*parts):
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(project_root, *parts)


def _load_role_permissions():
    cfg_path = _project_config_path('config', 'role_permissions.json')
    try:
        with open(cfg_path, 'r', encoding='utf-8') as file_handle:
            return json.load(file_handle), cfg_path
    except Exception:
        return {}, cfg_path


def _normalize_permissions_pages(perms):
    if not isinstance(perms, dict):
        return {}
    normalized = dict(perms)
    for new_key, legacy_key in ROLES_PAGE_ALIASES.items():
        if new_key not in normalized and legacy_key in normalized:
            normalized[new_key] = normalized.get(legacy_key, {})
        elif legacy_key not in normalized and new_key in normalized:
            normalized[legacy_key] = normalized.get(new_key, {})
    return normalized


def register_admin_roles_routes(admin_bp):
    @admin_bp.route('/admin/ustawienia/roles')
    @masteradmin_required
    def admin_ustawienia_roles():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name, label FROM roles ORDER BY id ASC")
            roles = cursor.fetchall()
        except Exception:
            roles = [
                ('admin', 'admin'),
                ('planista', 'planista'),
                ('pracownik', 'pracownik'),
                ('magazynier', 'magazynier'),
                ('dur', 'dur'),
                ('zarzad', 'zarzad'),
                ('laborant', 'laborant'),
                ('produkcja', 'produkcja'),
                ('lider', 'lider'),
            ]
        conn.close()

        perms, cfg_path = _load_role_permissions()
        perms = _normalize_permissions_pages(perms)
        if perms == {}:
            try:
                current_app.logger.error('Error loading role_permissions.json from %s', cfg_path)
            except Exception:
                pass

        ordered_perms = {}
        for page in ROLES_PAGES:
            if page in perms:
                ordered_perms[page] = perms[page]
            else:
                ordered_perms[page] = {}

        json_role_keys = set()
        for page_values in ordered_perms.values():
            if isinstance(page_values, dict):
                json_role_keys.update(page_values.keys())

        for page in ROLES_PAGES:
            for role in roles:
                role_name = role[0]
                json_key = role_name if role_name in json_role_keys else ROLE_NAME_MAPPING.get(role_name, role_name)
                source = ordered_perms[page].get(json_key, {'access': False, 'readonly': False})
                if role_name not in ordered_perms[page]:
                    ordered_perms[page][role_name] = {'access': bool(source.get('access')), 'readonly': bool(source.get('readonly'))}

        try:
            current_app.logger.debug('[ROLES_UI] roles from DB: %s', [role[0] for role in roles])
            current_app.logger.debug('[ROLES_UI] perms pages keys: %s', list(ordered_perms.keys()))
            first_page = ROLES_PAGES[0]
            current_app.logger.debug('[ROLES_UI] sample perms for page %s: %s', first_page, list(ordered_perms.get(first_page, {}).keys()))
        except Exception:
            pass

        return render_template('ustawienia_roles.html', pages=ROLES_PAGES, roles=roles, perms_json=ordered_perms)

    @admin_bp.route('/admin/ustawienia/roles/users')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_roles_users():
        """Show effective permissions per user (for admin verification)."""
        try:
            current_app.logger.debug('[ROLES_USERS] invoked by session: %s', {'login': session.get('login'), 'rola': session.get('rola')})
        except Exception:
            pass
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, login, COALESCE(rola, '') FROM uzytkownicy ORDER BY login")
        users_raw = cursor.fetchall()
        perms, _cfg_path = _load_role_permissions()

        users = []
        for user in users_raw:
            user_id, login, role = user[0], user[1], (user[2] or '').strip()
            row = {'id': user_id, 'login': login, 'role': role, 'perms': {}}
            for page in ROLES_USERS_PAGES:
                page_perms = perms.get(page, {}) if perms else {}
                if role in page_perms:
                    role_perms = page_perms.get(role, {})
                else:
                    mapped = ROLE_NAME_MAPPING.get(role)
                    role_perms = page_perms.get(mapped, {}) if mapped else {}
                access = bool(role_perms.get('access')) if isinstance(role_perms, dict) else False
                readonly = bool(role_perms.get('readonly')) if isinstance(role_perms, dict) else False
                row['perms'][page] = {'access': access, 'readonly': readonly}
            users.append(row)

        conn.close()
        return render_template('roles_by_user.html', users=users, pages=ROLES_USERS_PAGES)

    @admin_bp.route('/admin/ustawienia/roles/save', methods=['POST'])
    @login_required
    def admin_ustawienia_roles_save():
        session_rola = str(session.get('rola') or '').lower()
        session_login = session.get('login') or '?'
        current_app.logger.debug('[ROLES_SAVE] Save attempt: login=%s rola=%s', session_login, session_rola)
        if session_rola not in ['admin', 'masteradmin']:
            current_app.logger.warning('[ROLES_SAVE] Rejected: not authorized. login=%s rola=%s', session_login, session_rola)
            return jsonify({'error': f'Brak uprawnień (twoja rola: {session_rola}, wymagana: admin/masteradmin)'}), 403
        try:
            current_app.logger.debug('admin_ustawienia_roles_save invoked by user=%s remote=%s', session_login, request.remote_addr)
            data = request.get_json(force=True)
        except Exception:
            data = None
        if data is None:
            return ('Bad request', 400)
        try:
            cleaned_data = {}
            for page, roles in data.items():
                if isinstance(roles, dict) and len(roles) > 0:
                    cleaned_data[page] = roles
            data = cleaned_data
        except Exception:
            pass

        try:
            def _payload_has_access(payload):
                if not isinstance(payload, dict):
                    return False
                for _page, roles in payload.items():
                    if isinstance(roles, dict):
                        for _role, perms in roles.items():
                            if isinstance(perms, dict):
                                try:
                                    if bool(perms.get('access')):
                                        return True
                                except Exception:
                                    continue
                return False

            if not _payload_has_access(data):
                current_app.logger.warning('Rejected roles save: payload contains no access=true entries (user=%s)', session.get('login'))
                return jsonify({'error': 'Payload contains no access=true entries; refusing to overwrite config.'}), 400
        except Exception:
            current_app.logger.exception('Error validating roles payload; rejecting save request')
            return jsonify({'error': 'Validation error'}), 400

        cfg_dir = _project_config_path('config')
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_path = os.path.join(cfg_dir, 'role_permissions.json')

        existing_config = {}
        try:
            with open(cfg_path, 'r', encoding='utf-8') as file_handle:
                existing_config = json.load(file_handle)
        except Exception:
            existing_config = {}

        merged_config = _normalize_permissions_pages(existing_config)
        for page, roles in data.items():
            if isinstance(roles, dict):
                merged_config[page] = roles

        merged_config = _normalize_permissions_pages(merged_config)

        ordered_merged = {}
        for page in ROLES_PAGES:
            if page in merged_config:
                ordered_merged[page] = merged_config[page]
        for page in merged_config:
            if page not in ordered_merged:
                ordered_merged[page] = merged_config[page]
        merged_config = ordered_merged

        current_app.logger.debug('Reordered config pages: %s', list(merged_config.keys()))

        try:
            import shutil
            from datetime import datetime as _dt

            backup_name = None
            if os.path.exists(cfg_path):
                backup_name = cfg_path + '.bak.' + _dt.now().strftime('%Y%m%d-%H%M%S')
                try:
                    shutil.copy2(cfg_path, backup_name)
                    current_app.logger.debug('Created backup of role_permissions: %s', backup_name)
                except Exception:
                    current_app.logger.exception('Failed to create backup of role_permissions')

            with open(cfg_path, 'w', encoding='utf-8') as file_handle:
                json.dump(merged_config, file_handle, ensure_ascii=False, indent=2)

            with open(cfg_path, 'r', encoding='utf-8') as file_handle:
                verify_order = json.load(file_handle)
                saved_order = list(verify_order.keys())
                current_app.logger.debug('Verified config page order after save: %s', saved_order)

            try:
                current_app.logger.info('Uprawnienia ról zapisane przez %s', session.get('login'))
                audit_log('Zmienił uprawnienia ról')
            except Exception:
                current_app.logger.info('Uprawnienia ról zapisane')
            return jsonify({'ok': True, 'backup': backup_name}), 200
        except Exception as error:
            try:
                current_app.logger.exception('Failed to save role_permissions to %s', cfg_path)
            except Exception:
                pass
            return jsonify({'error': str(error)}), 500

    @admin_bp.route('/admin/ustawienia/roles/add', methods=['POST'])
    @masteradmin_required
    def admin_ustawienia_roles_add():
        """Dodaj nową rolę."""
        try:
            data = request.get_json(force=True)
            role_name = data.get('role_name', '').strip().lower()

            if not role_name:
                return jsonify({'success': False, 'error': 'Nazwa roli nie może być pusta'}), 400

            if not all(character.isalnum() or character == '_' for character in role_name):
                return jsonify({'success': False, 'error': 'Nazwa roli może zawierać tylko litery, liczby i podkreślnik'}), 400

            cfg_path = _project_config_path('config', 'role_permissions.json')

            config = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as file_handle:
                    try:
                        config = json.load(file_handle)
                    except Exception:
                        config = {}

            if not config:
                config = {page: {} for page in ROLES_USERS_PAGES}

            for page in config.values():
                if isinstance(page, dict) and role_name in page:
                    return jsonify({'success': False, 'error': f'Rola "{role_name}" już istnieje'}), 400

            for page in config:
                if isinstance(config[page], dict):
                    config[page][role_name] = {'access': False, 'readonly': False}

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute("INSERT INTO roles (name, label) VALUES (%s, %s)", (role_name, role_name))
                    conn.commit()
                    current_app.logger.debug('Inserted new role "%s" into roles table', role_name)
                except Exception:
                    conn.rollback()
                finally:
                    conn.close()
            except Exception:
                pass

            import shutil
            from datetime import datetime as _dt

            if os.path.exists(cfg_path):
                backup_path = cfg_path + '.bak.' + _dt.now().strftime('%Y%m%d-%H%M%S')
                shutil.copy2(cfg_path, backup_path)

            with open(cfg_path, 'w', encoding='utf-8') as file_handle:
                json.dump(config, file_handle, ensure_ascii=False, indent=2)

            current_app.logger.info('Dodano nową rolę "%s" przez %s', role_name, session.get('login'))
            audit_log('Dodał rolę', f'nazwa={role_name}')
            return jsonify({'success': True, 'message': f'Rola "{role_name}" została dodana'}), 200
        except Exception as error:
            current_app.logger.exception('Error adding new role')
            return jsonify({'success': False, 'error': str(error)}), 500