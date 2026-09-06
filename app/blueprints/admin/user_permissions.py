"""Routes for managing per-user permission overrides (User ACL Overrides).
Allows administrators to override default role permissions for individual users.
"""

import os
import json
from flask import request, jsonify, session, current_app
from app.decorators import dynamic_role_required
from app.core.database import get_db_connection
from app.repositories.user_permission_override_repository import user_permission_override_repository
from app.core.audit import security_audit_log


def register_user_permissions_routes(admin_bp):
    """Register user-specific permissions management routes."""

    @admin_bp.route('/admin/api/user/<int:user_id>/permissions', methods=['GET'])
    @dynamic_role_required('ustawienia')
    def get_user_permissions(user_id):
        """Get all modules, role defaults, and current overrides for a user."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, login, rola FROM uzytkownicy WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            return jsonify({'success': False, 'message': 'Nie znaleziono użytkownika.'}), 404

        user_role = (user.get('rola') or 'pracownik').lower().strip()

        # Load all pages and role configurations from role_permissions.json
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')
        role_perms = {}
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    role_perms = json.load(f)
        except Exception as e:
            current_app.logger.error("Failed to load role_permissions.json: %s", e)

        # Get existing user overrides
        user_overrides = user_permission_override_repository.get_user_overrides(user_id)

        modules = []
        for page_key, perms in role_perms.items():
            role_cfg = perms.get(user_role, {})
            role_access = bool(role_cfg.get('access', False))
            role_readonly = bool(role_cfg.get('readonly', False))

            override = user_overrides.get(page_key)
            effective_access = override['access'] if override is not None else role_access
            effective_readonly = override['readonly'] if override is not None else role_readonly

            modules.append({
                'page_key': page_key,
                'role_access': role_access,
                'role_readonly': role_readonly,
                'has_override': override is not None,
                'override_access': override['access'] if override else None,
                'override_readonly': override['readonly'] if override else None,
                'effective_access': effective_access,
                'effective_readonly': effective_readonly
            })

        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'login': user['login'],
                'rola': user_role
            },
            'modules': modules
        })

    @admin_bp.route('/admin/api/user/<int:user_id>/permissions', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def save_user_permissions(user_id):
        """Save permission overrides for a user."""
        data = request.get_json() or {}
        overrides = data.get('overrides', {})  # Dict[page_key, {'mode': 'inherit'|'allow'|'deny', 'readonly': bool}]

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT login FROM uzytkownicy WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            return jsonify({'success': False, 'message': 'Nie znaleziono użytkownika.'}), 404

        updated_count = 0
        deleted_count = 0

        for page_key, cfg in overrides.items():
            if cfg is None or cfg.get('mode') == 'inherit':
                if user_permission_override_repository.delete_user_override(user_id, page_key):
                    deleted_count += 1
            else:
                mode = cfg.get('mode')
                access = (mode == 'allow')
                readonly = bool(cfg.get('readonly', False))
                if user_permission_override_repository.set_user_override(user_id, page_key, access, readonly):
                    updated_count += 1

        security_audit_log(
            'USER_PERMISSIONS_OVERRIDE_CHANGED',
            f'TargetUser={user["login"]} (ID={user_id}), Updated={updated_count}, Reverted={deleted_count}',
            user_login=session.get('login')
        )

        return jsonify({
            'success': True,
            'message': 'Indywidualne uprawnienia zostały zaktualizowane.'
        })
