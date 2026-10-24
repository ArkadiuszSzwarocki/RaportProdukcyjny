"""Print request capture for warehouse users; monitoring is available to warehouse management."""
from datetime import timezone
from zoneinfo import ZoneInfo
from uuid import UUID
from flask import current_app, jsonify, render_template, request, session
from app.db import get_db_connection
from app.decorators import login_required, roles_required
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
@roles_required('admin', 'masteradmin', 'zarzad', 'lider')
def movement_print_history():
    query = str(request.args.get('q') or '').strip()[:160]
    page = max(1,min(request.args.get('page',1,type=int) or 1,10000))
    archived = request.args.get('archive') == '1'
    documents, clicks = MovementDocumentRepository.monitor(query,page,archived=archived)
    from app.repositories.movement_print_job_repository import MovementPrintJobRepository as Jobs
    from app.services.tracked_movement_print import STATUS_NAMES
    jobs = Jobs.latest_for_documents(documents)
    for document in documents:
        job = jobs.get((document['document_kind'],str(document['document_id'])))
        # A newer browser print must never inherit an older device confirmation.
        document['tracked_print'] = job if job and document.get('last_print_event_id') == job['request_id'] else None
    for row in documents + clicks:
        for field in ('last_click','email_finished') if 'last_click' in row else ('created_at',):
            value = row.get(field)
            if value:
                row[field] = value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/Warsaw')).strftime('%d.%m.%Y %H:%M:%S')
    return render_template('magazyn_dostawy/historia_druku.html',documents=documents,clicks=clicks,query=query,page=page,archived=archived,status_names=STATUS_NAMES)


def _tracked_print_documents(documents):
    if not isinstance(documents,list) or not 1 <= len(documents) <= 20:
        raise ValueError('Wybierz od 1 do 20 dokumentów.')
    connection = get_db_connection()
    verified = []
    seen = set()
    try:
        cursor = connection.cursor(dictionary=True)
        for document in documents:
            if not isinstance(document,dict):
                raise ValueError('Nieprawidłowy dokument.')
            kind = document.get('kind')
            identifier = str(document.get('id') or '').strip()
            if kind not in ('delivery','osip') or not identifier or len(identifier)>64:
                raise ValueError('Nieprawidłowy dokument.')
            if (kind,identifier) in seen:
                continue
            seen.add((kind,identifier))
            if kind == 'delivery':
                cursor.execute('SELECT id,order_ref FROM magazyn_dostawy WHERE id=%s',(identifier,))
                row = cursor.fetchone()
                ref = (row or {}).get('order_ref') or identifier
            else:
                cursor.execute('SELECT id,transfer_code FROM osip_transfers WHERE id=%s',(identifier,))
                row = cursor.fetchone()
                ref = (row or {}).get('transfer_code') or identifier
            if not row or not _page_allowed('ALL','magazyn',write=False):
                raise PermissionError('Brak dostępu do dokumentu.')
            verified.append((kind,identifier,str(ref)))
    finally:
        connection.close()
    return verified


@magazyn_dostawy_bp.route('/api/tracked-print/options')
@login_required
def tracked_print_options():
    from printer_server.office_config import office_printers
    try:
        printers = office_printers()
        return jsonify(success=True,printers=[dict(key=key,label=value['label']) for key,value in printers.items()])
    except (ValueError,TypeError,OSError):
        current_app.logger.exception('Office printer configuration invalid')
        return jsonify(success=False,error='Nieprawidłowa konfiguracja drukarek A4.'),503


@magazyn_dostawy_bp.route('/api/tracked-print',methods=['POST'])
@login_required
def tracked_print_submit():
    from app.services.tracked_movement_print import submit,public_job
    payload = request.get_json(silent=True) or {}
    try:
        request_id = str(UUID(str(payload.get('event_id') or '')))
        documents = _tracked_print_documents(payload.get('documents'))
        row = submit(current_app._get_current_object(),request_id,str(payload.get('printer_key') or ''),str(session.get('login') or ''),documents)
        return jsonify(success=True,job=public_job(row)),202
    except PermissionError:
        return jsonify(success=False,error='Brak dostępu do dokumentu.'),403
    except (ValueError,TypeError,AttributeError):
        return jsonify(success=False,error='Nieprawidłowe dane lub drukarka A4 nie jest skonfigurowana.'),400
    except Exception:
        current_app.logger.exception('Could not queue tracked print')
        return jsonify(success=False,error='Niepewny wynik. Sprawdź historię i kolejkę przed ponowieniem.'),503


@magazyn_dostawy_bp.route('/api/tracked-print/<uuid:request_id>')
@login_required
def tracked_print_status(request_id):
    from app.repositories.movement_print_job_repository import MovementPrintJobRepository as Jobs
    from app.services.tracked_movement_print import refresh,public_job
    row = Jobs.get(str(request_id))
    if not row:
        return jsonify(success=False,error='Nie znaleziono zadania.'),404
    role = str(session.get('rola') or '').strip().lower()
    if row['user_login'] != session.get('login') and role not in ('admin','masteradmin','zarzad','lider'):
        return jsonify(success=False,error='Brak dostępu.'),403
    return jsonify(success=True,job=public_job(refresh(row)))
