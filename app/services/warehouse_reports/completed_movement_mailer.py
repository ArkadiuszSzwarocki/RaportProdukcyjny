"""Consume only committed completion events; local copies cannot send implicitly."""
import logging
import os
import time
import threading
import json
from functools import wraps
from hashlib import sha256
from app.db import get_db_connection
from app.repositories.movement_document_repository import MovementDocumentRepository

logger = logging.getLogger(__name__)


def document_mail_guard(kind):
    """Serialize manual and automatic SMTP attempts across processes."""
    def decorate(method):
        @wraps(method)
        def guarded(self, document_id):
            conn = get_db_connection()
            cursor = conn.cursor()
            acquired = False
            name = None
            try:
                canonical_id = document_id
                if kind == 'osip':
                    cursor.execute('SELECT id FROM osip_transfers WHERE CAST(id AS CHAR)=%s OR transfer_code=%s LIMIT 1',
                                   (str(document_id),str(document_id)))
                    identity = cursor.fetchone()
                    if identity:
                        canonical_id = identity[0]
                name = 'movement-mail:' + sha256(f'{conn.database}:{kind}:{canonical_id}'.encode()).hexdigest()[:48]
                cursor.execute('SELECT GET_LOCK(%s,0)', (name,))
                result = cursor.fetchone()
                acquired = bool(result and result[0] == 1)
                if not acquired:
                    return False, 'Wysyłka tego dokumentu jest już w toku.'
                return method(self, document_id)
            finally:
                try:
                    if acquired:
                        cursor.execute('SELECT RELEASE_LOCK(%s)', (name,))
                        cursor.fetchone()
                    cursor.close()
                finally:
                    conn.close()
        return guarded
    return decorate


class CompletedMovementMailer:
    _last_poll = 0.0
    _worker_lock = threading.Lock()

    @classmethod
    def kick(cls, app):
        # PDF/SMTP must not delay the scheduled production report minute.
        if str(os.getenv('ENABLE_AUTO_REPORT_SCHEDULER', '')).lower() not in ('true','1','yes','on'):
            return
        if time.monotonic() - cls._last_poll < 30 or not cls._worker_lock.acquire(blocking=False):
            return
        def worker():
            try:
                with app.app_context():
                    cls.dispatch_pending()
            except Exception:
                logger.exception('Completion mail queue could not be processed')
            finally:
                cls._worker_lock.release()
        try:
            threading.Thread(target=worker,daemon=True,name='movement-completion-mail').start()
        except Exception:
            cls._worker_lock.release()
            raise

    @classmethod
    def dispatch_pending(cls, *, local_test=False):
        if local_test:
            from app.core.database import DB_CONFIG
            if (DB_CONFIG.get('host') != '127.0.0.1' or int(DB_CONFIG.get('port') or 0) != 13317
                    or not str(DB_CONFIG.get('database') or '').startswith('rp_pr17_lifecycle_')):
                raise RuntimeError('Tryb testowego maila wymaga odseparowanej lokalnej bazy.')
        elif str(os.getenv('ENABLE_AUTO_REPORT_SCHEDULER', '')).lower() not in ('true','1','yes','on'):
            return
        # Use the existing elected report owner; do not start another daemon.
        now = time.monotonic()
        if now - cls._last_poll < 30:
            return
        cls._last_poll = now
        MovementDocumentRepository.ensure_schema()
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM warehouse_completion_emails WHERE status='PENDING' ORDER BY id LIMIT 20")
            pending = cursor.fetchall()
            for event in pending:
                # Recheck pending events created under a previous, broader policy.
                eligible = False
                if event['document_kind'] == 'delivery':
                    cursor.execute('SELECT * FROM magazyn_dostawy WHERE id=%s', (event['document_id'],))
                    document = cursor.fetchone()
                    from app.services.warehouse_reports.warehouse_document_classifier import WarehouseDocumentClassifier
                    eligible = bool(document) and str(document.get('status') or '').upper() == 'COMPLETED' and WarehouseDocumentClassifier.is_automatic_mp01_mm(
                        document, json.loads(document.get('items') or '[]'))
                if not eligible:
                    cursor.execute("UPDATE warehouse_completion_emails SET status='SKIPPED',finished_at=UTC_TIMESTAMP(6),result_note=%s WHERE id=%s AND status='PENDING'",
                                   ('Pominięto: automatyczny pojedynczy raport dotyczy wyłącznie MM w MP01.',event['id']))
                    conn.commit()
                    continue
                cursor.execute("UPDATE warehouse_completion_emails SET status='SENDING',started_at=UTC_TIMESTAMP(6) "
                               "WHERE id=%s AND status='PENDING'", (event['id'],))
                claimed = cursor.rowcount == 1
                conn.commit()
                if not claimed:
                    continue
                sent = False
                try:
                    table = 'magazyn_dostawy' if event['document_kind'] == 'delivery' else 'osip_transfers'
                    cursor.execute(f'SELECT email_sent_at FROM {table} WHERE id=%s', (event['document_id'],))
                    existing = cursor.fetchone()
                    if existing and existing.get('email_sent_at'):
                        sent, message = True, 'Wcześniej wysłano raport tego dokumentu.'
                    else:
                        from app.services.osip_report_email_service import OsipReportEmailService
                        service = OsipReportEmailService()
                        sender = service.send_central_delivery_osip_report if event['document_kind'] == 'delivery' else service.send_osip_transfer_report
                        sent, message = sender(event['document_id'])
                except Exception:
                    logger.exception('Completed movement mail failed: event=%s', event['id'])
                    message = 'Błąd wysyłki. Sprawdź konfigurację poczty i log serwera.'
                if not sent:
                    conn.commit()
                    cursor.execute(f'SELECT email_sent_at FROM {table} WHERE id=%s', (event['document_id'],))
                    confirmed = cursor.fetchone()
                    if confirmed and confirmed.get('email_sent_at'):
                        sent, message = True, 'Raport wysłano w równoległej operacji.'
                cursor.execute("UPDATE warehouse_completion_emails SET status=%s,finished_at=UTC_TIMESTAMP(6),result_note=%s WHERE id=%s",
                               ('SENT' if sent else 'FAILED',str(message)[:500],event['id']))
                conn.commit()
        finally:
            conn.close()
        # FAILED/SENDING are not blindly retried: a lost SMTP acknowledgement
        # can mean the recipient already has the mail. Manual review is required.
