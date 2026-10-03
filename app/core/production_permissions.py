# cspell:words bigbagi
"""Resolve production write permissions from server-owned resources."""
from flask import current_app, g, jsonify, request, session
from app.db import get_db_connection, get_table_name

ORDER_ACTIONS = {'start_zlecenie', 'koniec_zlecenie', 'zawies_zlecenie', 'zapisz_wyjasnienie'}
ZASYP_PLAN_ACTIONS = {
    'zasyp_etap_start', 'zasyp_etap_stop', 'zasyp_etap_manual_set',
    'zasyp_etap_reset', 'zasyp_etap_delete', 'zasyp_etapy_set_szarza',
    'zasyp_kolejny_pomiar', 'zasyp_dodaj_pare_dosypki',
    'zasyp_usun_ostatnia_pare_dosypki', 'zasyp_usun_punkt_kontrolny',
    'dodaj_dosypke',
}
FIXED_SECTIONS = {
    'agro_folio_add_roll': 'workowanie', 'agro_folio_close_roll': 'workowanie',
    'agro_folio_undo_close_roll': 'workowanie', 'agro_folio_edit_active_roll': 'workowanie',
    'agro_mix_rozliczenie_add': 'zasyp', 'agro_workowanie_rozliczenie_add': 'workowanie',
    'agro_mix_consume': 'zasyp', 'api_workowanie_bigbag_add': 'workowanie',
    'api_workowanie_bigbag_remove': 'workowanie',
}
# Laboratory release retains its laboratory-role guard and configurable function
# ACL. It does not grant operators write access to production orders.


def _deny(message='Brak uprawnień do tej sekcji.', status=403):
    return jsonify(success=False, error='forbidden', message=message), status


def _page_allowed(line, section):
    from app.core.contexts import inject_role_permissions
    role = str(session.get('rola') or '').strip().lower()
    if role == 'masteradmin':
        return True
    group = str(session.get('grupa') or 'ALL').upper()
    # Keep the established hall policy; a page grant does not override a hall restriction.
    if group != 'ALL' and (group == 'OSIP' or role not in
            {'admin', 'zarzad', 'planista', 'lider', 'laborant', 'masteradmin'}):
        if group != line:
            return False
    helpers = inject_role_permissions()
    page = line.lower() + '.' + section
    if session.get('user_id'):
        from app.repositories.user_permission_override_repository import user_permission_override_repository
        try:
            overrides = user_permission_override_repository.get_user_overrides(int(session['user_id']), strict=True)
        except Exception:
            current_app.logger.exception('Cannot verify individual production page permissions')
            return False
        if page in overrides:
            return overrides[page]['access'] and not overrides[page]['readonly']
    return helpers['role_has_access'](page) and not helpers['role_is_readonly'](page)


def enforce_production_write():
    """Never use an optional UI section to authorize an existing order."""
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return None
    endpoint = str(request.endpoint or '')
    if not endpoint.startswith('production.'):
        return None
    action = endpoint.split('.', 1)[1]
    if action in {'zglos_przestoj_page', 'edytuj_przestoj_page', 'usun_przestoj'}:
        return _enforce_downtime_write(action)
    resource_actions = ORDER_ACTIONS | ZASYP_PLAN_ACTIONS | {
        'potwierdz_dosypke', 'anuluj_dosypke', 'szarza_notatka_save', 'zasyp_notatka_save',
        'api_workowanie_bigbag_add', 'api_workowanie_bigbag_remove', 'agro_mix_consume'}
    if action not in resource_actions and action not in FIXED_SECTIONS:
        return None
    if request.is_json and action not in {'api_workowanie_bigbag_add', 'api_workowanie_bigbag_remove'}:
        # These handlers consume forms, not JSON. Never authorize a different parser.
        return _deny('Ta operacja wymaga danych formularza.', 415)
    data = request.get_json(silent=True) if request.is_json else {}
    data = data if isinstance(data, dict) else {}
    submitted_lines = {str(value).strip().upper() for value in (
        request.args.get('linia'), request.form.get('linia'), data.get('linia')) if value}
    if len(submitted_lines) > 1:
        return _deny('Sprzeczne wskazanie hali.')
    line = str(request.args.get('linia') or request.form.get('linia') or data.get('linia')
               or (session.get('selected_hall_view') if action not in FIXED_SECTIONS else None) or
               ('AGRO' if action in FIXED_SECTIONS or action == 'zawies_zlecenie' else 'PSD')).upper()
    if line not in {'AGRO', 'PSD', 'OSIP'}:
        return _deny()
    section = FIXED_SECTIONS.get(action)
    if (action.startswith('agro_') or action in {'api_workowanie_bigbag_add', 'api_workowanie_bigbag_remove'}) and line != 'AGRO':
        return _deny()
    if action in resource_actions:
        connection = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            args = request.view_args or {}
            plan_id = args.get('id') if action in ORDER_ACTIONS else (
                args.get('plan_id') or request.form.get('plan_id') or data.get('plan_id'))
            if action in {'potwierdz_dosypke', 'anuluj_dosypke'}:
                cursor.execute(f"SELECT plan_id FROM {get_table_name('dosypki', line)} WHERE id=%s",
                               (args.get('dosypka_id'),))
                row = cursor.fetchone()
                plan_id = row[0] if row else None
            elif action in {'szarza_notatka_save', 'zasyp_notatka_save'}:
                cursor.execute(f"SELECT plan_id FROM {get_table_name('szarze', line)} WHERE id=%s",
                               (args.get('szarza_id'),))
                row = cursor.fetchone()
                plan_id = row[0] if row else None
            elif action == 'api_workowanie_bigbag_remove':
                cursor.execute('SELECT plan_id FROM agro_workowanie_bigbagi WHERE id=%s',
                               (data.get('entry_id'),))
                row = cursor.fetchone()
                if not row:
                    return _deny()
                plan_id = row[0]
            if not plan_id:
                return _deny('Nie znaleziono zlecenia.', 404)
            cursor.execute(f"SELECT sekcja FROM {get_table_name('plan_produkcji', line)} WHERE id=%s",
                           (int(plan_id),))
            row = cursor.fetchone()
            section = str(row[0]).strip().lower() if row else None
            # Cleaning is carried out through the Zasyp controls.
            if section == 'czyszczenie':
                section = 'zasyp'
            if section not in {'zasyp', 'workowanie', 'bufor', 'magazyn'}:
                return _deny('Nie znaleziono sekcji zlecenia.', 404)
            if action in ZASYP_PLAN_ACTIONS and section != 'zasyp':
                return _deny()
            if action in FIXED_SECTIONS and section != FIXED_SECTIONS[action]:
                return _deny()
        except Exception:
            current_app.logger.exception('Cannot verify production resource permission')
            return _deny('Nie można zweryfikować uprawnień zlecenia.', 503)
        finally:
            if connection is not None:
                connection.close()
    if not _page_allowed(line, section):
        return _deny()
    for supplied_section in (request.args.get('sekcja'), request.form.get('sekcja'), data.get('sekcja')):
        if supplied_section and str(supplied_section).strip().lower() not in {section, 'czyszczenie' if section == 'zasyp' else section}:
            return _deny('Sekcja żądania nie odpowiada zleceniu.')
    g.production_section = section.capitalize()
    g.production_line = line
    return None


def _enforce_downtime_write(action):
    """Check the stored downtime before edits/deletes; creation checks its destination."""
    line = str(request.form.get('linia') or 'AGRO').strip().upper()
    section = str(request.form.get('sekcja') or 'Workowanie').strip().lower()
    if action != 'zglos_przestoj_page':
        from app.repositories.downtime_repository import DowntimeRepository
        selector = (request.form.get('sekcja') or request.args.get('sekcja')) if action == 'usun_przestoj' else request.args.get('sekcja')
        try:
            row = DowntimeRepository().get_downtime_by_id((request.view_args or {}).get('id'), sekcja=selector)
        except Exception:
            current_app.logger.exception('Cannot verify downtime resource permission')
            return _deny('Nie można zweryfikować uprawnień przestoju.', 503)
        if not row:
            return _deny('Nie znaleziono przestoju.', 404)
        original_line = str(row['linia']).strip().upper()
        original_section = str(row['sekcja']).strip().lower()
        if not _page_allowed(original_line, original_section):
            return _deny()
        line = str(request.form.get('linia') or original_line).strip().upper()
        section = str(request.form.get('sekcja') or original_section).strip().lower()
    if line not in {'AGRO', 'PSD', 'OSIP'} or section not in {'zasyp', 'workowanie', 'bufor', 'magazyn'}:
        return _deny()
    if not _page_allowed(line, section):
        return _deny()
    return None
