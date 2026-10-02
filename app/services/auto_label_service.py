"""Recoverable auto-label intent stored on the pallet, including MyISAM pallets."""
import logging

from app.db import get_db_connection, get_table_name

logger = logging.getLogger(__name__)


def ensure_auto_label_schema(cursor):
    """Run at schema migration, never in a production registration transaction."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS print_jobs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            printer_ip VARCHAR(255) NOT NULL, printer_name VARCHAR(255),
            zpl_content TEXT NOT NULL, status VARCHAR(50) DEFAULT 'PENDING',
            retry_count INT DEFAULT 0, error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            job_key VARCHAR(150) NULL, UNIQUE KEY uq_print_job_key (job_key),
            INDEX idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cursor.execute("SHOW COLUMNS FROM print_jobs LIKE 'job_key'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE print_jobs ADD COLUMN job_key VARCHAR(150) NULL')
    cursor.execute("SHOW INDEX FROM print_jobs WHERE Key_name = 'uq_print_job_key'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE print_jobs ADD UNIQUE KEY uq_print_job_key (job_key)')
    for table in ('palety_agro', 'palety_workowanie'):
        cursor.execute(f"SHOW COLUMNS FROM {table} LIKE 'auto_label_state'")
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN auto_label_state VARCHAR(16) NOT NULL DEFAULT 'none'")


class AutoLabelService:
    @staticmethod
    def queue_for_pallet(conn, cursor, pallet_id, linia='AGRO'):
        """Caller holds agro_pallet_register. Commit job BEFORE marking intent fulfilled."""
        from app.utils.pallet_label import prepare_pallet_label_data
        from app.repositories.settings_repository import SettingsRepository
        from app.services.print_server import get_printer

        table = get_table_name('palety_workowanie', linia)
        key = f'auto-label:{str(linia).upper()}:{int(pallet_id)}'
        cursor.execute('SELECT id FROM print_jobs WHERE job_key=%s', (key,))
        existing = cursor.fetchone()
        if not existing:
            label = prepare_pallet_label_data(cursor, pallet_id, linia, source_table='workowanie')
            if not label:
                raise RuntimeError(f'Brak danych etykiety palety {pallet_id}')
            printer = SettingsRepository.get_default_printer_for_line(linia)
            if not printer:
                raise RuntimeError(f'Brak aktywnej drukarki dla linii {linia}')
            zpl = get_printer().build_finished_product_label_zpl(label, copies=2)
            cursor.execute("""
                INSERT INTO print_jobs (printer_ip, printer_name, zpl_content, status, job_key)
                VALUES (%s, %s, %s, 'PENDING', %s)
                ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
            """, (printer.get('ip') or '', printer.get('nazwa'), zpl, key))
        # An interrupted acknowledgement leaves pending intent + existing unique job.
        conn.commit()
        cursor.execute(f"UPDATE {table} SET auto_label_state='queued' WHERE id=%s AND auto_label_state='pending'", (pallet_id,))
        conn.commit()

    @staticmethod
    def recover_pending(linia='AGRO', limit=50):
        conn = get_db_connection()
        acquired = False
        recovered = 0
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT GET_LOCK('agro_pallet_register', 0)")
            row = cursor.fetchone()
            acquired = bool(row and row[0] == 1)
            if not acquired:
                return 0
            table = get_table_name('palety_workowanie', linia)
            cursor.execute(f"SELECT id FROM {table} WHERE auto_label_state='pending' ORDER BY id ASC LIMIT %s", (int(limit),))
            pending_ids = [row[0] for row in cursor.fetchall()]
            for pallet_id in pending_ids:
                try:
                    AutoLabelService.queue_for_pallet(conn, cursor, pallet_id, linia)
                    recovered += 1
                except Exception:
                    conn.rollback()
                    logger.exception('Auto-label intent remains pending for pallet %s', pallet_id)
            return recovered
        finally:
            try:
                if acquired:
                    cursor.execute("SELECT RELEASE_LOCK('agro_pallet_register')")
                    cursor.fetchone()
            finally:
                conn.close()
