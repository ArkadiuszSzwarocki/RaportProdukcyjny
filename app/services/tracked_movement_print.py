"""Render canonical warehouse reports, submit once, then only read job status."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import tempfile
import threading
from urllib.parse import quote
from flask import url_for
from app.repositories.movement_document_repository import MovementDocumentRepository
from app.repositories.movement_print_job_repository import MovementPrintJobRepository as Jobs
from printer_server.office_config import office_printers

EXECUTOR = ThreadPoolExecutor(max_workers=2,thread_name_prefix='movement-pdf')
SLOTS = threading.BoundedSemaphore(8)
TERMINAL = {'DEVICE_COMPLETED','DEVICE_WARNING','FAILED','CANCELLED'}
STATUSES = TERMINAL | {'PREPARING','BRIDGE_QUEUED','SUBMITTING','QUEUED','PRINTING','ATTENTION','SENT_TO_PRINTER','DEVICE_PROCESSING','UNKNOWN'}
STATUS_NAMES = {
    'PREPARING':'Przygotowanie PDF','BRIDGE_QUEUED':'Przyjęto przez mostek',
    'SUBMITTING':'Przekazywanie do Windows','QUEUED':'W kolejce Windows','PRINTING':'Drukowanie według Windows',
    'ATTENTION':'Drukarka wymaga sprawdzenia','SENT_TO_PRINTER':'Obsłużono w Windows — wydruk niepotwierdzony',
    'DEVICE_PROCESSING':'Drukarka przetwarza zadanie','DEVICE_COMPLETED':'Drukarka zgłosiła zakończenie',
    'DEVICE_WARNING':'Zakończenie z ostrzeżeniami','FAILED':'Błąd','CANCELLED':'Anulowano','UNKNOWN':'Brak potwierdzenia'}


def _bridge(method, path, **kwargs):
    from app.services.print_server import get_printer
    printer = get_printer()
    # A status request never starts a bridge or retries a print submission.
    import requests
    response = requests.request(method,printer.bridge_url+path,headers=printer._bridge_headers(),
                                verify=printer.bridge_tls_verify,allow_redirects=False,
                                timeout=(printer.bridge_connect_timeout,30),**kwargs)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    body = response.json()
    if not body.get('success') or not isinstance(body.get('job'),dict):
        raise RuntimeError('Mostek nie zwrócił statusu zadania.')
    job = body['job']
    if job.get('status') not in STATUSES:
        raise RuntimeError('Nieznany status mostka.')
    return job


def _render_reports(paths, output):
    from app.services.office_print_service import _render_pdf
    if len(paths) == 1:
        _render_pdf(paths[0],output)
        return
    import pymupdf
    combined = pymupdf.open()
    try:
        for path in paths:
            handle, temporary = tempfile.mkstemp(suffix='.pdf')
            os.close(handle)
            try:
                _render_pdf(path,temporary)
                with pymupdf.open(temporary) as part:
                    if len(combined)+len(part) > 100:
                        raise ValueError('Zestaw przekracza 100 stron. Podziel wydruk.')
                    combined.insert_pdf(part)
            finally:
                os.remove(temporary)
        combined.save(output)
    finally:
        combined.close()


def _work(app, request_id, printer_key, paths):
    try:
        with app.app_context():
            handle, pdf = tempfile.mkstemp(suffix='.pdf')
            os.close(handle)
            submitted = False
            try:
                _render_reports(paths,pdf)
                with open(pdf,'rb') as stream:
                    submitted = True
                    job = _bridge('POST','/office-jobs',files={'file':('movement.pdf',stream,'application/pdf')},
                                  data={'request_id':request_id,'printer_key':printer_key})
                if not job or job.get('request_id') != request_id:
                    raise RuntimeError('Mostek nie zwrócił właściwego zadania.')
                Jobs.update(request_id,job['status'],job['note'],job.get('spool_id'))
            except Exception:
                app.logger.exception('Tracked movement print failed: %s',request_id)
                Jobs.update(request_id,'UNKNOWN' if submitted else 'FAILED',
                            'Niepewny wynik wysłania. Sprawdź status i kolejkę przed ponowieniem.' if submitted else 'Nie przygotowano PDF; nic nie wysłano do mostka.')
            finally:
                os.remove(pdf)
    finally:
        SLOTS.release()


def submit(app, request_id, printer_key, login, documents):
    printers = office_printers()
    if printer_key not in printers:
        raise ValueError('Brak skonfigurowanej drukarki A4. Uzupełnij konfigurację po sprawdzeniu IP.')
    if not 1 <= len(documents) <= 20:
        raise ValueError('Jedno zadanie może obejmować od 1 do 20 dokumentów.')
    paths = [url_for('magazyn_dostawy.raport_przesuniecia',dostawa_id=identifier) if kind == 'delivery'
             else url_for('osip.transfer_details_view',transfer_id=identifier) for kind,identifier,_ref in documents]
    if not SLOTS.acquire(blocking=False):
        raise ValueError('Trwa przygotowanie wielu raportów. Poczekaj i spróbuj ponownie.')
    created = False
    try:
        created, row = Jobs.create(request_id,printer_key,printers[printer_key]['label'],login,documents)
        if not created:
            SLOTS.release()
            return row
        MovementDocumentRepository.record_print_requests(documents,request_id,login,'button')
        EXECUTOR.submit(_work,app,request_id,printer_key,paths)
        return row
    except Exception:
        SLOTS.release()
        if created:
            Jobs.update(request_id,'FAILED','Nie zakolejkowano przygotowania PDF. Nic nie wysłano do mostka.')
        raise


def refresh(row):
    if row['status'] in TERMINAL:
        return row
    age = (datetime.now(timezone.utc).replace(tzinfo=None)-row['created_at']).total_seconds()
    if row['status'] == 'PREPARING' and age < 90:
        return row
    try:
        job = _bridge('GET','/office-jobs/'+quote(row['request_id'],safe=''))
        if job and job.get('request_id') == row['request_id']:
            Jobs.update(row['request_id'],job['status'],job['note'],job.get('spool_id'))
        else:
            Jobs.update(row['request_id'],'UNKNOWN','Mostek nie zna zadania. Nie ponawiaj automatycznie; sprawdź kolejkę.')
    except Exception:
        # Preserve the last observed status, but do not disguise lost connectivity.
        Jobs.update(row['request_id'],'UNKNOWN','Brak kontaktu z mostkiem; wynik druku niepotwierdzony. Sprawdź kolejkę przed ponowieniem.')
    return Jobs.get(row['request_id'])


def public_job(row):
    return dict(request_id=row['request_id'],status=row['status'],status_name=STATUS_NAMES.get(row['status'],'Brak potwierdzenia'),
                note=row['note'],printer_label=row['printer_label'],spool_id=row.get('spool_id'))
