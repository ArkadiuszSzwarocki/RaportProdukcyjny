"""Shared hall and write checks for legacy delivery and AGRO entry points."""
from flask import current_app, has_request_context, jsonify, request
from app.core.production_permissions import _page_allowed
from app.db import get_db_connection


def logistics_stock_write_allowed(table, row):
    """Authorize resolved stock, including cross-hall legacy lookup fallbacks."""
    if not has_request_context():
        return True  # Trusted jobs and migrations do not run as browser requests.
    if table in {'magazyn_surowce', 'magazyn_agro_surowce'}:
        from app.core.shared_raw_stock_permissions import shared_raw_stock_allowed
        payload = request.get_json(silent=True) if request.is_json else request.form
        payload = payload if hasattr(payload, 'get') else {}
        context_line = payload.get('linia') or request.args.get('linia') or 'AGRO'
        return shared_raw_stock_allowed(row, context_line, write=True)
    fixed_halls = {
        'magazyn_opakowania': 'PSD',
        'magazyn_agro_opakowania': 'AGRO',
        'magazyn_palety_agro': 'AGRO',
    }
    if table == 'magazyn_dodatki':
        # Shared additives are available only within the already authorized request scope.
        payload = request.get_json(silent=True) if request.is_json else request.form
        payload = payload if hasattr(payload, 'get') else {}
        line = str(payload.get('linia') or request.args.get('linia') or 'AGRO').upper()
    else:
        line = fixed_halls.get(table) or str(row.get('linia') or '').upper()
    halls = ('PSD', 'AGRO', 'OSIP') if line == 'ALL' else (line,)
    return all(hall in {'PSD', 'AGRO', 'OSIP'} and
               _page_allowed(hall, 'magazyn', write=True) for hall in halls)


def enforce_logistics_permissions(default_line='ALL'):
    if request.endpoint in {'magazyn_dostawy.record_document_print', 'magazyn_dostawy.movement_print_history'}:
        # These routes enforce per-document read ACL / MasterAdmin respectively.
        return None
    payload = request.get_json(silent=True) if request.is_json else request.form
    if not isinstance(payload, dict) and request.is_json:
        return jsonify(success=False, error='invalid_payload'), 400
    if request.endpoint == 'magazyn_dostawy.api_draft_check':
        # This read-only endpoint authorizes each draft separately and filters denied halls.
        return None
    saving = request.endpoint == 'magazyn_dostawy.zapisz_dostawe'
    body_defaults = {
        'magazyn_dostawy.zapisz_dostawe': 'PSD',
        'magazyn_dostawy.przyjmij_wg': 'PSD',
        'magazyn_dostawy.api_draft_lock': 'AGRO',
        'magazyn_dostawy.api_draft_unlock': 'AGRO',
        'magazyn_dostawy.api_draft_sync': 'AGRO',
        'magazyn_dostawy.api_live_transfer_init': 'AGRO',
        'magazyn_dostawy.api_live_transfer_add_item': 'AGRO',
        'magazyn_dostawy.api_live_transfer_remove_item': 'AGRO',
    }
    body_default = body_defaults.get(request.endpoint)
    line = str((payload.get('linia') or body_default) if body_default else
               (payload.get('linia') or request.args.get('linia') or default_line)).upper()
    if line not in {'PSD', 'AGRO', 'OSIP', 'ALL'}:
        return jsonify(success=False, error='forbidden'), 403
    if request.args.get('linia') and (payload.get('linia') or body_default) and str(request.args['linia']).upper() != line:
        return jsonify(success=False, error='hall_mismatch'), 400
    document_id = (request.view_args or {}).get('dostawa_id') or payload.get('dostawa_id')
    if saving:
        document_id = payload.get('id')
    elif request.endpoint == 'magazyn_dostawy.edycja_dostawy':
        document_id = document_id or request.args.get('id')
    if document_id and document_id != 'nowe':
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT linia FROM magazyn_dostawy WHERE id=%s', (document_id,))
            row = cursor.fetchone()
            if not row and not saving:
                return jsonify(success=False, error='document_not_found'), 404
            if row:
                document_line = str(row.get('linia') or '').upper()
                if line != 'ALL' and line != document_line:
                    return jsonify(success=False, error='hall_mismatch'), 403
                line = document_line
        except Exception:
            current_app.logger.exception('Delivery authorization failed closed')
            return jsonify(success=False, error='authorization_unavailable'), 503
        finally:
            if conn is not None:
                conn.close()
    if line not in {'PSD', 'AGRO', 'OSIP', 'ALL'}:
        return jsonify(success=False, error='forbidden'), 403
    write = request.method not in {'GET', 'HEAD', 'OPTIONS'}
    if request.endpoint in {'magazyn_dostawy.api_draft_check', 'agro_warehouse.suggest_location'}:
        write = False
    halls = ('PSD', 'AGRO', 'OSIP') if line == 'ALL' else (line,)
    if not all(_page_allowed(hall, 'magazyn', write=write) for hall in halls):
        return jsonify(success=False, error='forbidden'), 403
    return None
