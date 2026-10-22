"""Authorize scanner operations against hall grants and server-owned stock."""
from flask import current_app, g, jsonify, request, session
from app.core.production_permissions import _page_allowed
from app.db import get_db_connection, get_table_name
from app.core.shared_inventory_permissions import (
    SHARED_MATERIAL_TYPES, SHARED_MATERIAL_TABLES, is_shared_material, shared_material_access,
)
from app.core.shared_raw_stock_permissions import shared_raw_stock_allowed


def scanner_resource_read_allowed(resource):
    """Check the actual resource hall after a lookup with legacy fallbacks."""
    if not session.get('zalogowany'):
        return request.endpoint in {'scanner.label', 'scanner.label_location'}
    payload = request.get_json(silent=True) if request.is_json else {}
    payload = payload if isinstance(payload, dict) else {}
    if resource.get('is_shelf') or (resource.get('is_station') and not resource.get('is_production_station')):
        return shared_material_access()
    if is_shared_material(resource):
        return shared_material_access()
    line = str(resource.get('linia') or payload.get('linia') or
               request.args.get('linia') or 'AGRO').strip().upper()
    return line in {'PSD', 'AGRO', 'OSIP'} and _page_allowed(line, 'magazyn', write=False)


def enforce_scanner_permissions():
    endpoint = str(request.endpoint or '')
    payload = request.get_json(silent=True) if request.is_json else {}
    if not isinstance(payload, dict):
        return jsonify(success=False, error='invalid_payload'), 400
    shared_move = endpoint == 'scanner.move' and (payload.get('type') or 'Surowiec') in (SHARED_MATERIAL_TYPES | {'TRANSFER'})
    shared_read = endpoint in {
        'scanner.lookup', 'scanner.pallet_suggestions',
        'scanner.label', 'scanner.label_location', 'scanner.scanner_ui',
        'scanner.printer_status', 'scanner.get_printers', 'scanner.get_pallet_history',
    }
    shared_operation = shared_move or shared_read
    if shared_operation and not shared_material_access():
        return jsonify(success=False, error='unauthenticated'), 401
    line = str(payload.get('linia') or request.args.get('linia') or 'AGRO').strip().upper()
    if shared_operation and line == 'ALL':
        line = 'AGRO'
        payload['linia'] = line
    if line not in {'PSD', 'AGRO', 'OSIP'}:
        return jsonify(success=False, error='forbidden'), 403
    if not shared_operation and payload.get('linia') and request.args.get('linia') and str(request.args['linia']).upper() != line:
        return jsonify(success=False, error='hall_mismatch'), 400
    read_only = request.method in {'GET', 'HEAD', 'OPTIONS'} or endpoint in {
        'scanner.lookup', 'scanner.validate_station', 'scanner.pallet_suggestions',
    }
    section = 'zasyp' if endpoint == 'scanner.dispatch' else 'magazyn'
    if not shared_operation and not _page_allowed(line, section, write=not read_only):
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
            if endpoint == 'scanner.dispatch' and payload.get('type') and payload.get('pallet_type') and payload['type'] != payload['pallet_type']:
                return jsonify(success=False, error='pallet_type_mismatch'), 400
            kind = (payload.get('type') or payload.get('pallet_type')) if endpoint == 'scanner.dispatch' else payload.get('type')
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
        if shared_move and table in SHARED_MATERIAL_TABLES:
            from app.utils.location_validator import is_production_tank_code
            # Moving into a production station is a production operation.
            if is_production_tank_code(str(payload.get('lokalizacja') or '').strip().upper()) and not _page_allowed(line, 'zasyp', write=True):
                return jsonify(success=False, error='forbidden'), 403
            return None
        raw_stock = (endpoint != 'scanner.restore_pallet' and table == 'magazyn_surowce') or (
            endpoint == 'scanner.restore_pallet' and str(row.get('typ_palety') or row.get('typ') or row.get('type') or '').casefold() == 'surowiec')
        if raw_stock:
            resource = dict(row, lokalizacja=row.get('lokalizacja_ostatnia')) if endpoint == 'scanner.restore_pallet' else row
            if not shared_raw_stock_allowed(resource, line, write=True):
                return jsonify(success=False, error='forbidden'), 403
            return None
        resource_line = str(row.get('linia') or line).strip().upper()
        if resource_line != line:
            # Shared stock retains its source hall when issued to another line.
            # Authorize the stock and destination independently using stored data.
            if endpoint != 'scanner.dispatch' or resource_line not in {'PSD', 'AGRO', 'OSIP'} or not _page_allowed(resource_line, 'magazyn', write=True):
                return jsonify(success=False, error='forbidden'), 403
    except Exception:
        current_app.logger.exception('Scanner resource authorization failed closed')
        return jsonify(success=False, error='authorization_unavailable'), 503
    finally:
        if conn is not None:
            conn.close()
    return None
