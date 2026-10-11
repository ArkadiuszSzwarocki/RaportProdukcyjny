"""Authorize scanner operations against hall grants and server-owned stock."""
from flask import current_app, g, jsonify, request, session
from app.core.production_permissions import _page_allowed
from app.db import get_db_connection, get_table_name


def scanner_resource_read_allowed(resource):
    """Check the actual resource hall after a lookup with legacy fallbacks."""
    if not session.get('zalogowany'):
        return request.endpoint in {'scanner.label', 'scanner.label_location'}
    payload = request.get_json(silent=True) if request.is_json else {}
    payload = payload if isinstance(payload, dict) else {}
    line = str(resource.get('linia') or payload.get('linia') or
               request.args.get('linia') or 'AGRO').strip().upper()
    return line in {'PSD', 'AGRO', 'OSIP'} and _page_allowed(line, 'magazyn', write=False)


def enforce_scanner_permissions():
    endpoint = str(request.endpoint or '')
    payload = request.get_json(silent=True) if request.is_json else {}
    if not isinstance(payload, dict):
        return jsonify(success=False, error='invalid_payload'), 400
    line = str(payload.get('linia') or request.args.get('linia') or 'AGRO').strip().upper()
    if line not in {'PSD', 'AGRO', 'OSIP'}:
        return jsonify(success=False, error='forbidden'), 403
    if payload.get('linia') and request.args.get('linia') and str(request.args['linia']).upper() != line:
        return jsonify(success=False, error='hall_mismatch'), 400
    read_only = request.method in {'GET', 'HEAD', 'OPTIONS'} or endpoint in {
        'scanner.lookup', 'scanner.validate_station', 'scanner.pallet_suggestions',
    }
    section = 'zasyp' if endpoint == 'scanner.dispatch' else 'magazyn'
    if not _page_allowed(line, section, write=not read_only):
        return jsonify(success=False, error='forbidden'), 403
    if endpoint not in {'scanner.move', 'scanner.dispatch', 'scanner.restore_pallet'}:
        return None

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if endpoint == 'scanner.restore_pallet':
            identifier = payload.get('archive_id') or payload.get('nr_palety')
            column = 'id' if payload.get('archive_id') else 'nr_palety'
            cursor.execute(f'SELECT * FROM magazyn_archiwum WHERE {column}=%s', (identifier,))
            row = cursor.fetchone()
        else:
            kind = payload.get('pallet_type') if endpoint == 'scanner.dispatch' else payload.get('type')
            kind = kind or 'Surowiec'
            if kind == 'TRANSFER':
                kind = 'Surowiec'
            bases = {'Surowiec': 'magazyn_surowce', 'Opakowanie': 'magazyn_opakowania',
                     'Dodatek': 'magazyn_dodatki', 'Wyrób Gotowy': 'magazyn_palety'}
            if kind not in bases:
                return jsonify(success=False, error='invalid_pallet_type'), 400
            table = get_table_name(bases[kind], line)
            identifier = payload.get('surowiec_id') or payload.get('nr_palety')
            column = 'id' if str(identifier).isdigit() else 'nr_palety'
            cursor.execute(f'SELECT * FROM {table} WHERE {column}=%s', (identifier,))
            row = cursor.fetchone()
            if row:
                expected_code = payload.get('nr_palety') or payload.get('sscc')
                if expected_code and str(row.get('nr_palety')) != str(expected_code):
                    return jsonify(success=False, error='pallet_identity_mismatch'), 400
                g.warehouse_resource = {'table': table, 'id': row['id'], 'nr_palety': row.get('nr_palety')}
        if not row:
            return jsonify(success=False, error='pallet_not_found'), 404
        if str(row.get('linia') or line).upper() != line:
            return jsonify(success=False, error='forbidden'), 403
    except Exception:
        current_app.logger.exception('Scanner resource authorization failed closed')
        return jsonify(success=False, error='authorization_unavailable'), 503
    finally:
        if conn is not None:
            conn.close()
    return None
