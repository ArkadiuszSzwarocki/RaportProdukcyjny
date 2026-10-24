"""Separate durable audit for tracked A4 jobs; never touches warehouse stock."""
import json
import threading
from app.db import get_db_connection


class MovementPrintJobRepository:
    _ready = set()
    _lock = threading.Lock()

    @classmethod
    def ensure_schema(cls):
        c = get_db_connection()
        try:
            with cls._lock:
                if c.database in cls._ready:
                    return
                q = c.cursor()
                q.execute("""CREATE TABLE IF NOT EXISTS warehouse_document_print_jobs (
                    request_id CHAR(36) PRIMARY KEY, printer_key VARCHAR(80) NOT NULL,
                    printer_label VARCHAR(100) NOT NULL, user_login VARCHAR(100) NOT NULL,
                    documents_json TEXT NOT NULL, status VARCHAR(32) NOT NULL,
                    note VARCHAR(500) NOT NULL, spool_id BIGINT NULL,
                    created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
                    KEY print_job_date(created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                q.execute("""CREATE TABLE IF NOT EXISTS warehouse_document_print_links (
                    request_id CHAR(36) NOT NULL, document_kind VARCHAR(12) NOT NULL,
                    document_id VARCHAR(64) NOT NULL,
                    PRIMARY KEY(request_id,document_kind,document_id),
                    KEY document_print_job(document_kind,document_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                c.commit()
                cls._ready.add(c.database)
        finally:
            c.close()

    @classmethod
    def create(cls, request_id, printer_key, printer_label, login, documents):
        cls.ensure_schema()
        serialized = json.dumps(sorted(documents),separators=(',',':'))
        c = get_db_connection()
        try:
            q = c.cursor(dictionary=True)
            q.execute("""INSERT IGNORE INTO warehouse_document_print_jobs
                (request_id,printer_key,printer_label,user_login,documents_json,status,note,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,'PREPARING','Przygotowanie PDF.',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))""",
                (request_id,printer_key,printer_label,login,serialized))
            created = q.rowcount == 1
            q.execute('SELECT * FROM warehouse_document_print_jobs WHERE request_id=%s FOR UPDATE',(request_id,))
            row = q.fetchone()
            if row['user_login'] != login or row['printer_key'] != printer_key or row['documents_json'] != serialized:
                raise ValueError('Identyfikator należy do innego żądania druku.')
            if created:
                for kind, identifier, _ref in documents:
                    q.execute('INSERT INTO warehouse_document_print_links VALUES (%s,%s,%s)',(request_id,kind,identifier))
            c.commit()
            return created, row
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    @classmethod
    def get(cls, request_id):
        cls.ensure_schema()
        c = get_db_connection()
        try:
            q = c.cursor(dictionary=True)
            q.execute('SELECT * FROM warehouse_document_print_jobs WHERE request_id=%s',(request_id,))
            return q.fetchone()
        finally:
            c.close()

    @staticmethod
    def update(request_id, status, note, spool_id=None):
        c = get_db_connection()
        try:
            q = c.cursor()
            q.execute("UPDATE warehouse_document_print_jobs SET status=%s,note=%s,spool_id=COALESCE(%s,spool_id),updated_at=UTC_TIMESTAMP(6) WHERE request_id=%s AND status NOT IN ('DEVICE_COMPLETED','DEVICE_WARNING','FAILED','CANCELLED')",
                      (status,str(note)[:500],spool_id,request_id))
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    @classmethod
    def latest_for_documents(cls, documents):
        if not documents:
            return {}
        cls.ensure_schema()
        c = get_db_connection()
        try:
            q = c.cursor(dictionary=True)
            predicates = ','.join(['(%s,%s)']*len(documents))
            params = tuple(value for row in documents for value in (row['document_kind'],str(row['document_id'])))
            q.execute(f"""SELECT j.*,l.document_kind,l.document_id FROM warehouse_document_print_jobs j
                JOIN warehouse_document_print_links l ON l.request_id=j.request_id
                WHERE (l.document_kind,l.document_id) IN ({predicates})
                ORDER BY j.created_at DESC,j.request_id DESC""",params)
            result = {}
            for row in q.fetchall():
                result.setdefault((row['document_kind'],row['document_id']),row)
            return result
        finally:
            c.close()
