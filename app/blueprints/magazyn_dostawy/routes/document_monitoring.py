"""Print request capture for warehouse users; monitoring is MasterAdmin-only."""
from datetime import timezone
from zoneinfo import ZoneInfo
from uuid import UUID
from flask import current_app, jsonify, render_template, request, session
from app.db import get_db_connection
from app.decorators import login_required, masteradmin_required
from app.core.production_permissions import _page_allowed
from app.repositories.movement_document_repository import MovementDocumentRepository
from ..base import magazyn_dostawy_bp


@magazyn_dostawy_bp.route('/api/print-requests', methods=['POST'])
@login_required
def record_document_print():
    payload = request.get_json(silent=True) or {}
    try:
        event_id = str(UUID(str(payload.get('event_id') or '')))
        documents = payload.get('documents')
        trigger = payload.get('trigger', 'button')
        if trigger not in ('button','browser','auto') or not isinstance(documents,list) or not 1 <= len(documents) <= 200:
            raise ValueError('Nieprawidłowe żądanie historii wydruku.')
        conn = get_db_connection()
        verified = []
        try:
            cursor = conn.cursor(dictionary=True)
            for document in documents:
                kind = document.get('kind')
                identifier = str(document.get('id') or '').strip()
                if kind not in ('delivery','osip') or not identifier or len(identifier) > 64:
                    raise ValueError('Nieprawidłowy dokument wydruku.')
                if kind == 'delivery':
                    cursor.execute('SELECT id,order_ref,linia FROM magazyn_dostawy WHERE id=%s', (identifier,))
                    row = cursor.fetchone()
                    halls = ('PSD','AGRO','OSIP') if (row or {}).get('linia') == 'ALL' else (str((row or {}).get('linia') or '').upper(),)
                    permitted = bool(row) and all(hall in ('PSD','AGRO','OSIP') and _page_allowed(hall,'magazyn',write=False) for hall in halls)
                    ref = (row or {}).get('order_ref') or identifier
                else:
                    cursor.execute('SELECT id,transfer_code,source_warehouse,destination_warehouse FROM osip_transfers WHERE id=%s', (identifier,))
                    row = cursor.fetchone()
                    halls = {'OSIP' if str((row or {}).get(field) or '').upper() == 'OSIP' else 'AGRO'
                             for field in ('source_warehouse','destination_warehouse')}
                    permitted = bool(row) and any(_page_allowed(hall,'magazyn',write=False) for hall in halls)
                    ref = (row or {}).get('transfer_code') or identifier
                if not permitted:
                    return jsonify(success=False, error='Brak dostępu do dokumentu.'), 403
                verified.append((kind,identifier,ref))
        finally:
            conn.close()
        MovementDocumentRepository.record_print_requests(verified,event_id,session.get('login'),trigger)
        return jsonify(success=True)
    except (ValueError, TypeError, AttributeError):
        return jsonify(success=False,error='Nieprawidłowe dane wydruku.'), 400
    except Exception:
        current_app.logger.exception('Could not persist document print request')
        return jsonify(success=False,error='Nie zapisano historii wydruku. Spróbuj ponownie.'), 503


@magazyn_dostawy_bp.route('/historia-druku')
@masteradmin_required
def movement_print_history():
    query = str(request.args.get('q') or '').strip()[:160]
    page = max(1,min(request.args.get('page',1,type=int) or 1,10000))
    documents, clicks = MovementDocumentRepository.monitor(query,page)
    for row in documents + clicks:
        for field in ('last_click','email_finished') if 'last_click' in row else ('created_at',):
            value = row.get(field)
            if value:
                row[field] = value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/Warsaw')).strftime('%d.%m.%Y %H:%M:%S')
    return render_template('magazyn_dostawy/historia_druku.html',documents=documents,clicks=clicks,query=query,page=page)
