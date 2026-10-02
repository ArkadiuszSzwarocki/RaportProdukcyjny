"""Additional, configurable endpoint restrictions shared by UI and server."""
from flask import current_app, request, session, jsonify, render_template


def function_catalog():
    if 'function_permission_catalog' in current_app.extensions:
        return current_app.extensions['function_permission_catalog']
    result = {}
    for rule in current_app.url_map.iter_rules():
        endpoint = rule.endpoint
        if '.' not in endpoint or endpoint.startswith(('static', 'auth.')):
            continue
        if endpoint.startswith('admin.') or endpoint.startswith('debug'):
            continue  # Administration retains its separate security boundary.
        key = 'function.' + endpoint
        result[key] = {'label': endpoint.split('.', 1)[1].replace('_', ' '),
                       'route': rule.rule,
                       'write': bool(set(rule.methods) & {'POST', 'PUT', 'PATCH', 'DELETE'})}
    return dict(sorted(result.items()))


def configured_function_permission():
    from app.core.contexts import _get_role_permissions, inject_role_permissions
    import os
    key = 'function.' + str(request.endpoint or '')
    config = _get_role_permissions(os.path.join(current_app.root_path, 'config', 'role_permissions.json'))
    overrides = {}
    if session.get('user_id'):
        from app.repositories.user_permission_override_repository import user_permission_override_repository
        try:
            overrides = user_permission_override_repository.get_user_overrides(int(session['user_id']), strict=True)
        except Exception:
            current_app.logger.exception('Cannot verify individual function permissions')
            return False
    if key in overrides:
        permission = overrides[key]
        return permission['access'] and not (
            request.method not in {'GET', 'HEAD', 'OPTIONS'} and permission['readonly'])
    if key not in config and key not in overrides:
        return None
    helpers = inject_role_permissions()
    return helpers['role_has_access'](key) and not (
        request.method not in {'GET', 'HEAD', 'OPTIONS'} and helpers['role_is_readonly'](key))


def register_function_permissions(app):
    with app.app_context():
        app.extensions['function_permission_catalog'] = function_catalog()
    @app.before_request
    def enforce_function_permissions():
        if not session.get('zalogowany') or session.get('rola') == 'masteradmin':
            return None
        key = 'function.' + str(request.endpoint or '')
        if key not in function_catalog():
            return None
        if configured_function_permission() is False:
            return jsonify(success=False, error='forbidden', message='Brak uprawnień do tej funkcji.'), 403
        section = request.args.get('sekcja') or request.form.get('sekcja')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and section in {'Zasyp', 'Workowanie', 'Bufor', 'Magazyn'}:
            from app.core.contexts import inject_role_permissions
            helpers = inject_role_permissions()
            line = str(request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD').lower()
            page = line + '.' + section.lower()
            if not helpers['role_has_access'](page) or helpers['role_is_readonly'](page):
                return jsonify(success=False, error='forbidden', message='Ta sekcja jest niedostępna lub tylko do odczytu.'), 403
        # Enforce page access and read-only status on the shared production dashboard.
        if request.endpoint == 'main.index':
            from app.core.contexts import inject_role_permissions
            helpers = inject_role_permissions()
            line = str(request.args.get('linia') or session.get('selected_hall_view') or 'PSD').lower()
            section = str(request.args.get('sekcja') or 'Dashboard').lower()
            page = line + '.' + section
            if not helpers['role_has_access'](page):
                return render_template('errors/403.html', page_url=request.path,
                                       user_role=session.get('rola'), allowed_roles=[]), 403
