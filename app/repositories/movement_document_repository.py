"""Durable print requests and one completion notification per warehouse document."""
import threading
import json
from app.db import get_db_connection


class MovementDocumentRepository:
    _ready = set()
    _lock = threading.Lock()

    @classmethod
    def ensure_schema(cls):
        # Separate connection: schema initialization must never commit stock writes.
        conn = get_db_connection()
        try:
            database = conn.database
            with cls._lock:
                if database in cls._ready:
                    return
                cursor = conn.cursor()
                cursor.execute("""CREATE TABLE IF NOT EXISTS warehouse_print_requests (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    event_id CHAR(36) NOT NULL,
                    document_kind VARCHAR(12) NOT NULL,
                    document_id VARCHAR(64) NOT NULL,
                    document_ref VARCHAR(160) NOT NULL,
                    user_login VARCHAR(100) NOT NULL,
                    trigger_name VARCHAR(20) NOT NULL,
                    created_at DATETIME(6) NOT NULL,
                    UNIQUE KEY one_request (event_id,document_kind,document_id),
                    KEY document_history (document_kind,document_id,id),
                    KEY requested_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS warehouse_completion_emails (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    document_kind VARCHAR(12) NOT NULL,
                    document_id VARCHAR(64) NOT NULL,
                    document_ref VARCHAR(160) NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
                    created_at DATETIME(6) NOT NULL,
                    started_at DATETIME(6) NULL,
                    finished_at DATETIME(6) NULL,
                    result_note VARCHAR(500) NULL,
                    UNIQUE KEY one_completion (document_kind,document_id),
                    KEY pending_mail (status,id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                conn.commit()
                cursor.close()
                cls._ready.add(database)
        finally:
            conn.close()

    @classmethod
    def queue_completed(cls, connection, kind, document_id):
        """Insert in the caller's stock transaction; never discover historical backlog."""
        if kind not in ('delivery', 'osip'):
            raise ValueError('Nieprawidłowy rodzaj przesunięcia.')
        if kind != 'delivery':
            return
        cls.ensure_schema()
        cursor = connection.cursor(dictionary=True)
        try:
            if kind == 'delivery':
                cursor.execute('SELECT * FROM magazyn_dostawy WHERE id=%s', (document_id,))
                row = cursor.fetchone()
                supplier = str((row or {}).get('supplier') or '').strip()
                if supplier not in ('', '-', 'None') and not supplier.upper().startswith(('PRZESUNI', 'TRANSFER')):
                    return
                from app.services.warehouse_reports.warehouse_document_classifier import WarehouseDocumentClassifier
                items = json.loads((row or {}).get('items') or '[]')
                if not row or not WarehouseDocumentClassifier.is_automatic_mp01_mm(row, items):
                    return
                ref = (row or {}).get('order_ref') or str(document_id)
            else:
                cursor.execute('SELECT status,transfer_code FROM osip_transfers WHERE id=%s', (document_id,))
                row = cursor.fetchone()
                ref = (row or {}).get('transfer_code') or str(document_id)
            if not row or str(row['status']).upper() != 'COMPLETED':
                return
            cursor.execute("""INSERT IGNORE INTO warehouse_completion_emails
                (document_kind,document_id,document_ref,status,created_at)
                VALUES(%s,%s,%s,'PENDING',UTC_TIMESTAMP(6))""", (kind,str(document_id),str(ref)[:160]))
        finally:
            cursor.close()

    @classmethod
    def record_print_requests(cls, documents, event_id, login, trigger):
        cls.ensure_schema()
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            for kind, document_id, ref in documents:
                cursor.execute("""INSERT IGNORE INTO warehouse_print_requests
                    (event_id,document_kind,document_id,document_ref,user_login,trigger_name,created_at)
                    VALUES(%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))""",
                    (event_id,kind,str(document_id),str(ref)[:160],str(login)[:100],trigger))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def monitor(cls, query='', page=1):
        cls.ensure_schema()
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""SELECT d.*,COALESCE(p.clicks,0) AS print_clicks,p.last_click,
                (SELECT user_login FROM warehouse_print_requests pr
                 WHERE pr.document_kind=d.document_kind AND pr.document_id=d.document_id
                 ORDER BY pr.id DESC LIMIT 1) AS printed_by,
                CASE WHEN d.email_sent_at IS NOT NULL THEN 'SENT' ELSE e.status END AS email_status,
                CASE WHEN d.email_sent_at IS NOT NULL AND e.status <> 'SENT' THEN NULL ELSE e.finished_at END AS email_finished,
                CASE WHEN d.email_sent_at IS NOT NULL THEN NULL ELSE e.result_note END AS result_note
                FROM (
                    SELECT 'delivery' AS document_kind,CAST(id AS CHAR) AS document_id,
                           COALESCE(order_ref,CAST(id AS CHAR)) AS document_ref,status,created_at,email_sent_at
                    FROM magazyn_dostawy WHERE supplier IS NULL OR TRIM(supplier) IN ('','-','None')
                        OR UPPER(supplier) LIKE 'PRZESUNI%%' OR UPPER(supplier) LIKE 'TRANSFER%%'
                    UNION ALL
                    SELECT 'osip',CAST(id AS CHAR),transfer_code,status,created_at,email_sent_at FROM osip_transfers
                ) d LEFT JOIN (
                    SELECT document_kind,document_id,COUNT(*) AS clicks,MAX(created_at) AS last_click
                    FROM warehouse_print_requests GROUP BY document_kind,document_id
                ) p ON p.document_kind=d.document_kind AND p.document_id=d.document_id
                LEFT JOIN warehouse_completion_emails e ON e.document_kind=d.document_kind AND e.document_id=d.document_id
                WHERE d.document_ref LIKE %s ORDER BY d.created_at DESC,d.document_kind,d.document_id
                LIMIT 100 OFFSET %s""", ('%' + query + '%',(page-1)*100))
            documents = cursor.fetchall()
            cursor.execute("""SELECT * FROM warehouse_print_requests WHERE document_ref LIKE %s
                ORDER BY id DESC LIMIT 200""", ('%' + query + '%',))
            return documents, cursor.fetchall()
        finally:
            conn.close()
