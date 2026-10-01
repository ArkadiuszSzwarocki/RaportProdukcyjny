from functools import wraps
from flask import session, redirect, request, jsonify, current_app, render_template


def _is_authenticated():
    """Return True only when the session explicitly represents a logged-in user."""
    return bool(session.get('zalogowany'))


def _valid_internal_print_request():
    """Allow only a short-lived HMAC supplied in a header, never in the URL."""
    token = str(request.headers.get('X-Internal-Print-Token') or '').strip()
    if not token:
        return False
    from app.utils.security_tokens import verify_internal_print_token
    return bool(verify_internal_print_token(request.path, token))


def _wants_json_response():
    try:
        is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        accepts_json = request.accept_mimetypes.best_match(
            ['application/json', 'text/html']
        ) == 'application/json'
        return bool(is_xhr or accepts_json or request.is_json)
    except Exception:
        return False


def _unauthenticated_response():
    if _wants_json_response():
        return jsonify({'success': False, 'error': 'unauthenticated'}), 401
    return redirect('/login')


def _forbidden_response(allowed_roles=None):
    if _wants_json_response():
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    return render_template(
        'errors/403.html',
        page_url=request.path,
        user_role=str(session.get('rola') or '').lower().strip(),
        allowed_roles=list(allowed_roles or []),
    ), 403


def login_required_response():
    """Return an authentication error response, or ``None`` for an allowed request.

    Internal headless printing may bypass the browser session only with a
    cryptographic token carried in ``X-Internal-Print-Token``.  Tokens are not
    accepted from query strings to avoid leaking credentials via URLs/logs.
    """
    if _valid_internal_print_request():
        return None

    if _is_authenticated():
        return None

    try:
        current_app.logger.info(
            '[login_required] Unauthenticated request to %s from %s',
            request.path,
            request.remote_addr,
        )
    except Exception:
        pass
    return _unauthenticated_response()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_response = login_required_response()
        if auth_response is not None:
            return auth_response
        return f(*args, **kwargs)
    return decorated_function


def zarzad_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            return _unauthenticated_response()

        allowed = ['zarzad', 'admin', 'planista', 'lider', 'laborant', 'masteradmin']
        if str(session.get('rola') or '').lower().strip() not in allowed:
            return _forbidden_response(allowed)
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            return _unauthenticated_response()

        allowed = ['admin', 'masteradmin']
        if str(session.get('rola') or '').lower().strip() not in allowed:
            try:
                current_app.logger.warning(
                    '[ADMIN_CHECK] Access denied for admin_required - login=%s role=%s',
                    session.get('login'),
                    session.get('rola'),
                )
            except Exception:
                pass
            return _forbidden_response(allowed)
        return f(*args, **kwargs)
    return decorated_function


def masteradmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            return _unauthenticated_response()
        if str(session.get('rola') or '').lower().strip() != 'masteradmin':
            return _forbidden_response(['masteradmin'])
        return f(*args, **kwargs)
    return decorated_function


def _normalize_role(raw_role):
    role = str(raw_role or '').lower().strip()
    aliases = {
        'master admin': 'masteradmin',
        'master_admin': 'masteradmin',
        'master-admin': 'masteradmin',
        'laboratorium': 'laborant',
    }
    role = aliases.get(role, role)
    if role.isdigit():
        roles_order = [
            'admin', 'planista', 'pracownik', 'magazynier',
            'dur', 'zarzad', 'laborant',
        ]
        try:
            idx = int(role)
            if 0 <= idx < len(roles_order):
                role = roles_order[idx]
        except (TypeError, ValueError):
            pass
    return role


def roles_required(*roles, groups=None):
    """Require one of the supplied roles and, optionally, one of the groups."""
    if len(roles) == 1 and isinstance(roles[0], (list, tuple)):
        roles = tuple(roles[0])

    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not _is_authenticated():
                return _unauthenticated_response()

            user_role = _normalize_role(session.get('rola'))
            # Administrative roles retain their intended global access, but the
            # role comes from the authenticated DB-backed session, not the login name.
            if user_role in ('admin', 'masteradmin'):
                return f(*args, **kwargs)

            roles_lower = [str(item).lower() for item in roles] if roles else []
            if roles and user_role not in roles_lower:
                current_app.logger.warning(
                    '[roles_required] Access denied: role=%s required=%s path=%s',
                    user_role,
                    roles_lower,
                    request.path,
                )
                return _forbidden_response(roles)

            if groups and session.get('grupa') not in groups:
                if _wants_json_response():
                    return jsonify({'success': False, 'error': 'forbidden'}), 403
                return redirect('/')
            return f(*args, **kwargs)
        return decorated
    return wrapper


def hall_restricted(f):
    """Restrict access to a hall when the user's group is not global."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_authenticated():
            return _unauthenticated_response()

        role = _normalize_role(session.get('rola'))
        user_grupa = str(session.get('grupa') or 'ALL').upper()
        if user_grupa == 'ALL' or (
            role in ['admin', 'zarzad', 'planista', 'lider', 'laborant', 'masteradmin']
            and user_grupa != 'OSIP'
        ):
            return f(*args, **kwargs)

        req_linia = request.args.get('linia') or request.form.get('linia')
        target_linia = str(req_linia or 'PSD').upper()
        if target_linia != user_grupa:
            current_app.logger.warning(
                '[HALL_RESTRICTED] Access denied for user %s (hall=%s) to %s',
                session.get('login'),
                user_grupa,
                target_linia,
            )
            if _wants_json_response():
                return jsonify({'success': False, 'error': 'Brak dostępu do tej hali'}), 403
            return redirect('/')
        return f(*args, **kwargs)
    return decorated


def dynamic_role_required(page_name):
    """Require dynamic permission configured for ``page_name``."""
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not _is_authenticated():
                return _unauthenticated_response()

            from app.core.contexts import inject_role_permissions
            role_checker = inject_role_permissions().get('role_has_access')
            if role_checker and role_checker(page_name):
                return f(*args, **kwargs)

            if _wants_json_response():
                return jsonify({'success': False, 'error': 'forbidden'}), 403

            import os
            import json
            user_role = _normalize_role(session.get('rola'))
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')
            if not os.path.exists(cfg_path) or os.path.getsize(cfg_path) == 0:
                fallback_path = os.path.join(project_root, 'config_fallback', 'role_permissions.json')
                if os.path.exists(fallback_path):
                    cfg_path = fallback_path

            allowed_roles = []
            try:
                if os.path.exists(cfg_path):
                    with open(cfg_path, 'r', encoding='utf-8') as file:
                        perms = json.load(file)
                    page_key = page_name
                    page_aliases = {'podsumowanie_zasypow': 'podsumowanie_szarz'}
                    if page_key not in perms and page_key in page_aliases:
                        page_key = page_aliases[page_key]
                    if page_key in perms:
                        for role_name, role_cfg in perms[page_key].items():
                            if role_cfg.get('access'):
                                allowed_roles.append(role_name)
            except Exception as exc:
                current_app.logger.error(
                    'Error reading role_permissions in dynamic_role_required: %s',
                    exc,
                )

            return render_template(
                'errors/403.html',
                page_url=request.path,
                user_role=user_role,
                allowed_roles=allowed_roles,
            ), 403
        return decorated
    return wrapper
