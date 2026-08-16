import logging
from datetime import date
from typing import Set

from app.db import get_db_connection, get_table_name

_logger = logging.getLogger(__name__)

class ZasypQueueService:
    """Service responsible for determining which Zasyp orders can be started."""

    @staticmethod
    def get_allowed_start_ids(dzisiaj: date, aktywna_linia: str, logger=None) -> Set[int]:
        """
        Return the set of plan IDs that are allowed to start in Zasyp.
        The logic enforces a FIFO queue: only the first 'zaplanowane' order 
        is available to start.
        """
        log = logger or _logger
        allowed_zasyp_start_ids = set()
        try:
            table_plan = get_table_name('plan_produkcji', aktywna_linia)
            conn = get_db_connection()
            cursor = conn.cursor()

            # Zwróć tylko pierwsze zlecenie 'zaplanowane' na liście
            cursor.execute(
                f"""
                SELECT id FROM {table_plan}
                WHERE sekcja = 'Zasyp'
                  AND status = 'zaplanowane'
                  AND DATE(data_planu) = %s
                  AND is_deleted = 0
                ORDER BY kolejnosc ASC, id ASC
                LIMIT 1
                """,
                (dzisiaj,)
            )
            row = cursor.fetchone()
            if row:
                allowed_zasyp_start_ids.add(row[0])

            cursor.close()
            conn.close()
        except Exception as error:
            log.error('[ERROR-START] Błąd w ZasypQueueService: %s', error)
            allowed_zasyp_start_ids = set()

        return allowed_zasyp_start_ids
