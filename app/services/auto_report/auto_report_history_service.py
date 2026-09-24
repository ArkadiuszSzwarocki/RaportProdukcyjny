"""
Moduł zarządzania historią wysyłek oraz atomową blokadą współbieżności auto-raportów.
"""
import logging
from typing import Optional
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)


class AutoReportHistoryService:
    @staticmethod
    def ensure_history_tables(conn=None):
        """Zapewnia istnienie tabeli historii wysyłek auto-raportów oraz powiązanych schematów."""
        own_conn = False
        if conn is None:
            conn = get_db_connection()
            own_conn = True

        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_report_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    data_raportu DATE NOT NULL,
                    linia VARCHAR(20) NOT NULL,
                    typ_raportu VARCHAR(50) NOT NULL,
                    odbiorcy TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'SENT',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY idx_unique_report (data_raportu, linia, typ_raportu),
                    INDEX idx_rep (data_raportu, linia, typ_raportu)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            try:
                cursor.execute("ALTER TABLE auto_report_history ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'SENT'")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE auto_report_history ADD UNIQUE KEY idx_unique_report (data_raportu, linia, typ_raportu)")
            except Exception:
                pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_report_schedule (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    data_dnia DATE NOT NULL,
                    linia VARCHAR(20) NOT NULL,
                    scheduled_time TIME NOT NULL DEFAULT '15:00:00',
                    is_paused TINYINT(1) NOT NULL DEFAULT 0,
                    postponed_by VARCHAR(100) DEFAULT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY idx_linia_data (data_dnia, linia)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_report_config (
                    id INT PRIMARY KEY,
                    active_days VARCHAR(50) NOT NULL DEFAULT '0,1,2,3,4',
                    enabled_lines VARCHAR(50) NOT NULL DEFAULT 'AGRO',
                    updated_by VARCHAR(100) DEFAULT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                INSERT IGNORE INTO auto_report_config (id, active_days, enabled_lines, updated_by)
                VALUES (1, '0,1,2,3,4', 'AGRO', 'System');
            """)
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.warning("[AUTO_REPORT_HISTORY] Nie udało się zainicjować tabel historii: %s", e)
        finally:
            if own_conn and conn:
                conn.close()

    @classmethod
    def is_report_sent(cls, linia: str, date_str: str, typ_raportu: str = '15:00') -> bool:
        """Sprawdza, czy raport danego typu został już wysłany (lub pominięty z braku danych) w danym dniu."""
        conn = None
        try:
            conn = get_db_connection()
            cls.ensure_history_tables(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id FROM auto_report_history 
                WHERE data_raportu = %s AND linia = %s AND typ_raportu = %s AND status IN ('SENT', 'SKIPPED_EMPTY')
                LIMIT 1
                """,
                (date_str, linia, typ_raportu)
            )
            row = cursor.fetchone()
            cursor.close()
            return bool(row)
        except Exception as e:
            logger.error("[AUTO_REPORT_HISTORY] Błąd sprawdzania statusu wysyłki: %s", e)
            return False
        finally:
            if conn:
                conn.close()

    @classmethod
    def claim_report_execution(cls, linia: str, date_str: str, typ_raportu: str = '15:00') -> bool:
        """
        Atomowo rezerwuje prawo do wykonania i wysyłki raportu.
        Gwarantuje jednorazową wysyłkę:
        - Jeśli status to 'SENT' lub 'SKIPPED_EMPTY', ZAWSZE zwraca False.
        - Jeśli status to 'IN_PROGRESS', blokuje współbieżne wykonania.
        - Jeśli status to 'FAILED', nie ponawia automatycznie co 10 minut w pętli.
        """
        conn = None
        try:
            conn = get_db_connection()
            cls.ensure_history_tables(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id, status, TIMESTAMPDIFF(MINUTE, created_at, NOW()) AS age_min
                FROM auto_report_history
                WHERE data_raportu = %s AND linia = %s AND typ_raportu = %s
                ORDER BY CASE WHEN status IN ('SENT', 'SKIPPED_EMPTY') THEN 0 ELSE 1 END, id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (date_str, linia, typ_raportu)
            )
            row = cursor.fetchone()

            if row:
                st = str(row.get('status') or '').upper()
                age_min = int(row.get('age_min') or 0)
                if st in ('SENT', 'SKIPPED_EMPTY'):
                    cursor.close()
                    return False
                if st == 'IN_PROGRESS' and age_min < 30:
                    cursor.close()
                    return False
                if st == 'FAILED':
                    cursor.close()
                    return False

                cursor.execute(
                    """
                    UPDATE auto_report_history
                    SET status = 'IN_PROGRESS', created_at = NOW()
                    WHERE id = %s AND status != 'SENT'
                    """,
                    (row['id'],)
                )
                conn.commit()
                cursor.close()
                return True
            else:
                try:
                    cursor.execute(
                        """
                        INSERT INTO auto_report_history (data_raportu, linia, typ_raportu, odbiorcy, status, created_at)
                        VALUES (%s, %s, %s, '', 'IN_PROGRESS', NOW())
                        """,
                        (date_str, linia, typ_raportu)
                    )
                    conn.commit()
                    cursor.close()
                    return True
                except Exception:
                    cursor.close()
                    return False
        except Exception as e:
            logger.error("[AUTO_REPORT_HISTORY] Błąd rezerwacji wysyłki raportu: %s", e)
            return False
        finally:
            if conn:
                conn.close()

    @classmethod
    def mark_report_sent(cls, linia: str, date_str: str, typ_raportu: str, recipients_str: str):
        """Rejestruje udane wysłanie raportu w historii (status SENT)."""
        conn = None
        try:
            conn = get_db_connection()
            cls.ensure_history_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO auto_report_history (data_raportu, linia, typ_raportu, odbiorcy, status, created_at)
                VALUES (%s, %s, %s, %s, 'SENT', NOW())
                ON DUPLICATE KEY UPDATE
                    odbiorcy = VALUES(odbiorcy),
                    status = 'SENT',
                    created_at = NOW()
                """,
                (date_str, linia, typ_raportu, recipients_str)
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error("[AUTO_REPORT_HISTORY] Błąd zapisu do auto_report_history: %s", e)
        finally:
            if conn:
                conn.close()

    @classmethod
    def mark_report_failed(cls, linia: str, date_str: str, typ_raportu: str, error_msg: str):
        """Oznacza próbę wysłania raportu jako nieudaną z zachowaniem cooldownu (status FAILED, tylko jeśli wcześniej nie było SENT)."""
        conn = None
        try:
            conn = get_db_connection()
            cls.ensure_history_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO auto_report_history (data_raportu, linia, typ_raportu, odbiorcy, status, created_at)
                VALUES (%s, %s, %s, %s, 'FAILED', NOW())
                ON DUPLICATE KEY UPDATE
                    odbiorcy = IF(status = 'SENT', odbiorcy, VALUES(odbiorcy)),
                    status = IF(status = 'SENT', 'SENT', 'FAILED'),
                    created_at = IF(status = 'SENT', created_at, NOW())
                """,
                (date_str, linia, typ_raportu, str(error_msg)[:255])
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error("[AUTO_REPORT_HISTORY] Błąd zapisu błędu do auto_report_history: %s", e)
        finally:
            if conn:
                conn.close()

    @classmethod
    def mark_report_skipped_empty(cls, linia: str, date_str: str, typ_raportu: str, reason: str = 'Brak danych produkcyjnych'):
        """Oznacza próbę wysłania raportu jako pominiętą ze względu na brak danych (status SKIPPED_EMPTY)."""
        conn = None
        try:
            conn = get_db_connection()
            cls.ensure_history_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO auto_report_history (data_raportu, linia, typ_raportu, odbiorcy, status, created_at)
                VALUES (%s, %s, %s, %s, 'SKIPPED_EMPTY', NOW())
                ON DUPLICATE KEY UPDATE
                    odbiorcy = IF(status = 'SENT', odbiorcy, VALUES(odbiorcy)),
                    status = IF(status = 'SENT', 'SENT', 'SKIPPED_EMPTY'),
                    created_at = IF(status = 'SENT', created_at, NOW())
                """,
                (date_str, linia, typ_raportu, str(reason)[:255])
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error("[AUTO_REPORT_HISTORY] Błąd zapisu pominięcia pustego raportu: %s", e)
        finally:
            if conn:
                conn.close()
