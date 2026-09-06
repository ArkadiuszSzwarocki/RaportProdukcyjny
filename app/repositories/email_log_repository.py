# File: app/repositories/email_log_repository.py
"""
EmailLogRepository - Repository for persisting and querying sent email history.
Provides data access methods without business logic.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)


class EmailLogRepository:
    """Repository handling email logs persistence in database."""

    _ensured: bool = False

    @classmethod
    def ensure_table(cls) -> None:
        """Ensures the email_logs table exists and is populated with past history."""
        if cls._ensured:
            return

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS email_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sender VARCHAR(255) NOT NULL,
                    recipients TEXT NOT NULL,
                    subject VARCHAR(255) NOT NULL,
                    source VARCHAR(100) NOT NULL DEFAULT 'Inne',
                    linia VARCHAR(20) DEFAULT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
                    error_message TEXT DEFAULT NULL,
                    attachments TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_created (created_at),
                    INDEX idx_status (status),
                    INDEX idx_source (source),
                    INDEX idx_linia (linia)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            conn.commit()

            # Bezpieczna synchronizacja wcześniejszych wpisów z auto_report_history
            try:
                cursor.execute("SHOW COLUMNS FROM auto_report_history LIKE 'status'")
                has_status_col = bool(cursor.fetchone())

                status_expr = "IF(h.status = 'SENT', 'SUCCESS', 'FAILED')" if has_status_col else "'SUCCESS'"
                status_where = "AND h.status = 'SENT'" if has_status_col else ""

                cursor.execute(f"""
                    INSERT INTO email_logs (sender, recipients, subject, source, linia, status, attachments, created_at)
                    SELECT 
                        'Konto Systemowe' as sender,
                        h.odbiorcy as recipients,
                        CONCAT('📊 Raport Produkcyjny ', h.linia, ' — ', h.typ_raportu, ' — ', h.data_raportu) as subject,
                        CONCAT('Auto-Raport ', h.typ_raportu) as source,
                        h.linia as linia,
                        {status_expr} as status,
                        'Raport_PDF_XLS.zip' as attachments,
                        h.created_at as created_at
                    FROM auto_report_history h
                    LEFT JOIN email_logs e ON e.created_at = h.created_at AND e.linia = h.linia
                    WHERE e.id IS NULL {status_where}
                """)
                conn.commit()
            except Exception as sync_err:
                logger.warning("Pomijanie synchronizacji historii auto-raportów: %s", sync_err)

            cls._ensured = True
            cursor.close()
        except Exception as e:
            logger.error("Błąd podczas ensure_table w EmailLogRepository: %s", e)
        finally:
            conn.close()

    @classmethod
    def create_log(
        cls,
        sender: str,
        recipients: str,
        subject: str,
        source: str = 'Inne',
        linia: Optional[str] = None,
        status: str = 'SUCCESS',
        error_message: Optional[str] = None,
        attachments: Optional[str] = None
    ) -> int:
        """Inserts a new email log entry and returns its ID."""
        cls.ensure_table()
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO email_logs 
                (sender, recipients, subject, source, linia, status, error_message, attachments, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (sender, recipients, subject, source, linia, status, error_message, attachments))
            log_id = cursor.lastrowid
            conn.commit()
            cursor.close()
            return log_id
        finally:
            conn.close()

    @classmethod
    def get_logs(
        cls,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None,
        linia: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Retrieves filtered email logs ordered by most recent."""
        cls.ensure_table()
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            conditions = ["1=1"]
            params = []

            if start_date:
                conditions.append("DATE(created_at) >= %s")
                params.append(start_date)
            if end_date:
                conditions.append("DATE(created_at) <= %s")
                params.append(end_date)
            if status and status != 'ALL':
                conditions.append("status = %s")
                params.append(status.upper())
            if linia and linia not in ('ALL', 'WSZYSTKO', 'NONE', ''):
                conditions.append("(linia = %s OR linia = 'ALL' OR linia IS NULL)")
                params.append(linia.upper())
            if search_query:
                conditions.append("(subject LIKE %s OR recipients LIKE %s OR sender LIKE %s OR source LIKE %s)")
                q_param = f"%{search_query}%"
                params.extend([q_param, q_param, q_param, q_param])

            where_clause = " AND ".join(conditions)

            # Count total
            cursor.execute(f"SELECT COUNT(id) as total FROM email_logs WHERE {where_clause}", tuple(params))
            total_count = (cursor.fetchone() or {}).get('total', 0)

            # Select page
            query = f"""
                SELECT id, sender, recipients, subject, source, linia, status, error_message, attachments, created_at
                FROM email_logs
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            page_params = list(params) + [limit, offset]
            cursor.execute(query, tuple(page_params))
            rows = cursor.fetchall()
            cursor.close()

            return rows, total_count
        finally:
            conn.close()

    @classmethod
    def get_daily_stats(cls, date_str: str) -> Dict[str, Any]:
        """Calculates email stats for a given day."""
        cls.ensure_table()
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT 
                    COUNT(id) as total,
                    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_count,
                    MAX(created_at) as last_sent_at
                FROM email_logs
                WHERE DATE(created_at) = %s
            """, (date_str,))
            row = cursor.fetchone() or {}
            cursor.close()

            return {
                'total': int(row.get('total') or 0),
                'success': int(row.get('success_count') or 0),
                'failed': int(row.get('failed_count') or 0),
                'last_sent_at': str(row.get('last_sent_at')) if row.get('last_sent_at') else None
            }
        finally:
            conn.close()
