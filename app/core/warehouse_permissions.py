# cspell:words sscc
"""Authorize warehouse pallet mutations independently of optional UI fields."""
from flask import current_app, g, jsonify, request
from app.db import get_db_connection, get_table_name
from app.core.production_permissions import _page_allowed


def _deny(message='Brak uprawnień do operacji magazynowej.', status=403):
    return jsonify(success=False, error='forbidden', message=message), status


def enforce_warehouse_write():
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return None
    endpoint = str(request.endpoint or '')
    if not endpoint.startswith('warehouse_v2.'):
        return None
    if '/api/pallet/' not in request.path and endpoint != 'warehouse_v2.restore_from_archive':
        return None
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _deny('Wymagane dane JSON.', 400)
    line = str(data.get('linia') or 'PSD').strip().upper()
    if line not in {'PSD', 'AGRO', 'OSIP'}:
        return _deny()
    for hint in (request.args.get('linia'), request.form.get('linia')):
        if hint and str(hint).strip().upper() != line:
            return _deny('Sprzeczne wskazanie hali.')
    if endpoint != 'warehouse_v2.restore_from_archive' and not _page_allowed(line, 'magazyn'):
        return _deny()
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if endpoint == 'warehouse_v2.restore_from_archive':
            cursor.execute('SELECT linia FROM magazyn_archiwum WHERE id=%s',
                           ((request.view_args or {}).get('archive_id'),))
            row = cursor.fetchone()
            if not row:
                return _deny('Nie znaleziono palety.', 404)
            line = str(row.get('linia') or 'PSD').upper()
            if not _page_allowed(line, 'magazyn'):
                return _deny()
        else:
            kind = data.get('type')
            bases = {'Surowiec': 'magazyn_surowce', 'Opakowanie': 'magazyn_opakowania',
                     'Dodatek': 'magazyn_dodatki', 'Wyrób Gotowy': 'magazyn_palety'}
            if kind not in bases:
                return _deny('Nieprawidłowy typ palety.', 400)
            table = get_table_name(bases[kind], line)
            identifiers = data.get('ids') if 'ids' in data else [data.get('id')]
            if not isinstance(identifiers, list) or not identifiers or len(identifiers) > 1000:
                return _deny('Nieprawidłowe identyfikatory palet.', 400)
            for identifier in identifiers:
                if identifier is None or str(identifier).strip() == '':
                    return _deny('Brak identyfikatora palety.', 400)
                if str(identifier).isdigit():
                    cursor.execute(f'SELECT * FROM {table} WHERE id=%s', (int(identifier),))
                else:
                    cursor.execute(f'SELECT * FROM {table} WHERE nr_palety=%s', (str(identifier),))
                row = cursor.fetchone()
                if not row:
                    # Never let a service silently search another hall or pending delivery.
                    return _deny('Nie znaleziono palety w wybranym magazynie.', 404)
                resource_line = str(row.get('linia') or line).strip().upper()
                if resource_line != line or not _page_allowed(resource_line, 'magazyn'):
                    return _deny()
                if data.get('sscc') and str(row.get('nr_palety')) != str(data['sscc']):
                    return _deny('Kod palety nie odpowiada identyfikatorowi.', 400)
            g.warehouse_resource = {'table': table, 'id': row['id'], 'nr_palety': row.get('nr_palety')}
            if endpoint == 'warehouse_v2.toggle_block':
                # This action synchronizes the quality lock across all stock representations.
                if not all(_page_allowed(hall, 'magazyn') for hall in ('PSD', 'AGRO', 'OSIP')):
                    return _deny()
        # All JSON handlers consume this same cached object, including their default line.
        data['linia'] = line
    except Exception:
        current_app.logger.exception('Cannot verify warehouse pallet permission')
        return _deny('Nie można zweryfikować uprawnień palety.', 503)
    finally:
        if connection is not None:
            connection.close()
    return None
