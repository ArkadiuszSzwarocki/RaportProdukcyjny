"""Group switches restrict navigation and requests without granting page privileges."""
from pathlib import Path
from flask import current_app, g, jsonify, render_template, request, session
from app.decorators import _normalize_role
from app.core.hall_roles import HALL_ROLES
from app.core.navigation_entries import ENTRY_KEYS, entry_switches

GROUPS = {
    'scanner': 'Skaner & Drukarka',
    'planning': 'Plan produkcji',
    'psd': 'Produkcja PSD',
    'agro': 'Produkcja AGRO',
    'warehouse': 'Magazyny',
    'osip': 'Magazyn OSIP',
    'inventory': 'Inwentaryzacja',
    'settlements': 'Rozliczenia i partie',
    'reports': 'Raporty',
    'analysis': 'Administracja & analiza',
    'quality': 'Jakość',
    'incidents': 'Awarie i usterki',
    'admin': 'Administracja',
    'diagnostics': 'System & diagnostyka',
    'agro_packaging': 'Opakowania i LP01',
    'agro_lp01': 'Stanowisko LP01',
    'agro_packaging_stock': 'Opakowania Agro',
    'agro_station_history': 'Historia Stacji (BB/MZ/WZ)',
    'agro_picking': 'Dyspozycje Kompletacji',
    'reports_agro': 'AGRO',
    'reports_psd': 'PSD',
    'reports_general': 'Pozostałe raporty',
}
GROUP_KEYS = {f'group.{group}' for group in GROUPS} | {f'group.entry_{entry}' for entry in ENTRY_KEYS}

AGRO_SUBGROUPS = {
    'agro_lp01': ('agro_packaging', 'agro'),
    'agro_packaging_stock': ('agro_packaging', 'agro'),
    'agro_station_history': ('agro',),
    'agro_picking': ('agro',),
}


def group_allowed(group):
    from app.core.contexts import _get_role_permissions
    role = _normalize_role(session.get('rola'))
    if role == 'masteradmin':
        return True
    if role in HALL_ROLES and group in HALL_ROLES and role != group:
        return False
    if role in {'operator', 'stepnpio'}:
        role = 'pracownik'
    key = f'group.{group}'
    if 'navigation_group_overrides' not in g:
        user_id = session.get('user_id')
        try:
            if user_id:
                from app.repositories.user_permission_override_repository import user_permission_override_repository
                g.navigation_group_overrides = user_permission_override_repository.get_user_overrides(int(user_id), strict=True)
            else:
                g.navigation_group_overrides = {}
        except Exception:
            current_app.logger.exception('Cannot verify navigation group overrides')
            g.navigation_group_overrides = None
    overrides = g.navigation_group_overrides
    if overrides is None:
        return False
    if key in overrides:
        return bool(overrides[key]['access'])
    config = _get_role_permissions(str(Path(__file__).resolve().parents[2] / 'config' / 'role_permissions.json'))
    return bool(config.get(key, {}).get(role, {}).get('access', True))


def request_group():
    endpoint = request.endpoint or ''
    blueprint, _, action = endpoint.partition('.')
    path = request.path.lower()
    data = request.get_json(silent=True) if request.is_json else request.form
    data = data if hasattr(data, 'get') else {}
    line = str(data.get('linia') or request.args.get('linia') or
               session.get('selected_hall_view') or session.get('grupa') or 'PSD').lower()
    osip_requested = any(str(value).strip().upper() == 'OSIP' for value in (
        data.get('linia'), request.args.get('linia'), request.args.get('zakladka'),
        request.args.get('scope'), data.get('scope'),
    ))

    if blueprint == 'osip' or endpoint == 'warehouse_v2.transfers_osip_view':
        return 'osip'
    if endpoint == 'production.agro_station_history' or path.startswith('/warehouse-v2/historia-stacji'):
        return 'agro_station_history'
    if blueprint == 'warehouse_v2' and (action in {'kompletacja', 'api_orders_start_picking'} or action.startswith('api_orders_picking_')):
        return 'agro_picking'
    if blueprint == 'agro_warehouse' and '/lp01' in path:
        return 'agro_lp01'
    if blueprint == 'agro_warehouse' and '/opakowania' in path:
        return 'agro_packaging_stock'
    if blueprint in {'warehouse_v2', 'magazyn_dostawy', 'scanner'} and osip_requested:
        return 'osip'
    if blueprint in {'inwentaryzacja', 'inwentaryzacja_produkcji'} or '/inwentaryzacja-produkcji' in path:
        return 'inventory'
    if blueprint in {'mom', 'traceability'}:
        return 'settlements'
    if blueprint == 'scanner':
        return 'diagnostics' if action == 'scanner_simulator' else 'scanner'
    if 'przestoj' in action or path.startswith('/dur/awarie'):
        return 'incidents'
    if action == 'panel_performance_page' or path.startswith(('/admin/master/', '/admin/centrum', '/zarzad/live-line', '/zebra-sim')) or (
        blueprint == 'admin' and action in {'admin_ustawienia_logs', 'ustawienia_errors', 'system_performance', 'admin_secret_db'}
    ):
        return 'diagnostics'
    if blueprint == 'zarzad' or path.startswith(('/agro/report', '/raporty/zasypy-dosypki')) or (
        blueprint in {'agro_warehouse', 'warehouse_v2', 'warehouse', 'production', 'magazyn_dostawy', 'quality'}
        and (action in {'raport', 'zasyp_etapy_podsumowanie', 'jakosc_podsumowanie_zasypow'}
             or action.startswith(('raport_palet', 'podsumowanie_zasypow')))
    ):
        return 'reports'
    if blueprint in {'quality', 'magnet_cleaning', 'separator_cleaning'}:
        return 'quality'
    if blueprint == 'admin':
        return 'admin'
    if action == 'moje_godziny' or path.startswith('/maszyny'):
        return 'analysis'
    if blueprint in {'planning', 'planista'} and not path.startswith('/bufor'):
        return 'planning'
    if blueprint == 'maluchy' or endpoint == 'main.index' or blueprint == 'production' or path.startswith('/bufor'):
        if action.startswith('agro_'):
            return 'agro'
        return 'agro' if line == 'agro' else 'psd'
    if blueprint == 'agro_warehouse' and action == 'surowce_w_produkcji':
        return 'agro'
    if blueprint in {'warehouse_v2', 'magazyn_dostawy', 'warehouse', 'agro_warehouse'}:
        return 'warehouse'
    return None


def enforce_group_permission():
    if not session.get('zalogowany') or not request.endpoint:
        return None
    group = request_group()
    payload = request.get_json(silent=True) if request.is_json else request.form
    payload = payload if hasattr(payload, 'get') else {}
    line = str(payload.get('linia') or request.args.get('linia') or request.args.get('zakladka') or '').strip().lower()
    entries = entry_switches(request.endpoint, request.path.lower(), line)
    entries_allowed = all(group_allowed(f'entry_{entry}') for entry in entries)
    if group == 'reports':
        from app.core.navigation_entries import report_sections
        entries_allowed = entries_allowed and all(
            group_allowed(section) for section in report_sections(request.endpoint, request.path.lower(), line)
        )
    if request.endpoint == 'scanner.move' and payload.get('amount_to_move') not in (None, ''):
        entries_allowed = entries_allowed and group_allowed('entry_split')
    if entries_allowed and (group is None or all(group_allowed(key) for key in (group, *AGRO_SUBGROUPS.get(group, ())))):
        # The scanner also needs its own switch when running in OSIP mode.
        if group != 'osip' or request.blueprint != 'scanner' or group_allowed('scanner'):
            return None
    if request.is_json or request.path.startswith('/api/') or '/api/' in request.path:
        return jsonify(success=False, error='forbidden', message='Brak dostępu do tej grupy.'), 403
    return render_template('errors/403.html', page_url=request.path,
                           user_role=session.get('rola'), allowed_roles=[]), 403
