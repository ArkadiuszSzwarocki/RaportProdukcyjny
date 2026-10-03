"""Additional, configurable endpoint restrictions shared by UI and server."""
from flask import current_app, request, session, jsonify, render_template

# Deliberate operator actions only. Polling, lookups and automatic acknowledgements
# must never become configurable function restrictions.
OPERATOR_ACTIONS = {
    'production.start_zlecenie': 'Rozpoczęcie zlecenia',
    'production.koniec_zlecenie': 'Zakończenie zlecenia',
    'production.zawies_zlecenie': 'Wstrzymanie zlecenia',
    'production.zapisz_wyjasnienie': 'Zapis wyjaśnienia',
    'production.dodaj_dosypke': 'Dodanie dosypki',
    'production.potwierdz_dosypke': 'Potwierdzenie dosypki',
    'production.anuluj_dosypke': 'Anulowanie dosypki',
    'production.agro_folio_add_roll': 'Podpięcie rolki folii',
    'production.agro_folio_close_roll': 'Rozliczenie rolki folii',
    'production.agro_folio_undo_close_roll': 'Cofnięcie rozliczenia folii',
    'production.agro_folio_edit_active_roll': 'Edycja rolki folii',
    'production.agro_mix_rozliczenie_add': 'Rozliczenie mieszanki',
    'production.agro_workowanie_rozliczenie_add': 'Rozliczenie workowania',
    'production.agro_mix_consume': 'Zużycie mieszanki',
    'production.api_workowanie_bigbag_add': 'Dodanie big baga do workowania',
    'production.api_workowanie_bigbag_remove': 'Usunięcie big baga z workowania',
    'production.api_zwolnij_mieszalnik': 'Zwolnienie mieszalnika',
    'production.zglos_przestoj_page': 'Zgłoszenie przestoju',
    'production.edytuj_przestoj_page': 'Edycja przestoju',
    'production.usun_przestoj': 'Usunięcie przestoju',
    'warehouse_v2.move_pallet': 'Przesunięcie palety',
    'warehouse_v2.archive_pallet': 'Archiwizacja palety',
    'warehouse_v2.dispatch_pallet': 'Wydanie palety',
    'warehouse_v2.rename_pallet': 'Zmiana nazwy palety',
    'warehouse_v2.update_weight': 'Zmiana wagi palety',
    'warehouse_v2.update_packaging': 'Zmiana opakowania palety',
    'warehouse_v2.toggle_block': 'Blokowanie palety',
    'warehouse_v2.pallet_return_to_raw': 'Zwrot palety do surowców',
    'warehouse_v2.print_pallet_label': 'Drukowanie etykiety palety',
    'warehouse_v2.delete_pallet': 'Usunięcie palety',
    'warehouse_v2.restore_from_archive': 'Przywrócenie palety z archiwum',
    'warehouse_v2.api_orders_create': 'Utworzenie zamówienia',
    'warehouse_v2.api_orders_confirm': 'Potwierdzenie zamówienia',
    'warehouse_v2.api_orders_delete': 'Usunięcie zamówienia',
    'warehouse_v2.api_orders_start_picking': 'Rozpoczęcie kompletacji',
    'warehouse_v2.api_orders_picking_confirm': 'Potwierdzenie kompletacji',
    'warehouse_v2.api_orders_picking_cancel': 'Anulowanie kompletacji',
    'warehouse_v2.api_orders_picking_delete': 'Usunięcie kompletacji',
}


def function_catalog():
    if 'function_permission_catalog' in current_app.extensions:
        return current_app.extensions['function_permission_catalog']
    result = {}
    for rule in current_app.url_map.iter_rules():
        endpoint = rule.endpoint
        if endpoint not in OPERATOR_ACTIONS:
            continue
        key = 'function.' + endpoint
        result[key] = {'label': OPERATOR_ACTIONS[endpoint],
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
        if not session.get('zalogowany'):
            return None
        key = 'function.' + str(request.endpoint or '')
        if session.get('rola') != 'masteradmin' and key in function_catalog() and configured_function_permission() is False:
            return jsonify(success=False, error='forbidden', message='Brak uprawnień do tej funkcji.'), 403
        from app.core.production_permissions import enforce_production_write
        production_denial = enforce_production_write()
        if production_denial is not None:
            return production_denial
        from app.core.warehouse_permissions import enforce_warehouse_write
        warehouse_denial = enforce_warehouse_write()
        if warehouse_denial is not None:
            return warehouse_denial
        if session.get('rola') == 'masteradmin':
            return None
        if request.endpoint == 'main.index':
            from app.core.contexts import inject_role_permissions
            helpers = inject_role_permissions()
            line = str(request.args.get('linia') or session.get('selected_hall_view') or session.get('grupa') or 'PSD').lower()
            if line not in {'psd', 'agro', 'osip'}:
                line = 'psd'
            section = str(request.args.get('sekcja') or 'Dashboard').lower()
            if section == 'dashboard' and not helpers['role_has_access'](line + '.' + section):
                # Let index redirect to an explicitly allowed section; it does not render the dashboard.
                if any(helpers['role_has_access'](line + '.' + candidate)
                       for candidate in ('zasyp', 'workowanie', 'bufor', 'magazyn')):
                    return None
            if not helpers['role_has_access'](line + '.' + section):
                return render_template('errors/403.html', page_url=request.path,
                                       user_role=session.get('rola'), allowed_roles=[]), 403
            return None
        if key not in function_catalog():
            return None
        if str(request.endpoint or '').startswith('production.'):
            # Production guards already resolved the actual resource/default destination.
            return None
        section = request.args.get('sekcja') or request.form.get('sekcja')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and section in {'Zasyp', 'Workowanie', 'Bufor', 'Magazyn'}:
            from app.core.contexts import inject_role_permissions
            helpers = inject_role_permissions()
            line = str(request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD').lower()
            page = line + '.' + section.lower()
            if not helpers['role_has_access'](page) or helpers['role_is_readonly'](page):
                return jsonify(success=False, error='forbidden', message='Ta sekcja jest niedostępna lub tylko do odczytu.'), 403
