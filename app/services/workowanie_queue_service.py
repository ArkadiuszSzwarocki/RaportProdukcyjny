import logging
from datetime import date
from typing import Dict, Set

from app.db import get_db_connection, get_table_name

_logger = logging.getLogger(__name__)

class WorkowanieQueueService:
    """Service responsible for determining which Workowanie orders can be started."""

    @staticmethod
    def get_allowed_start_ids(dzisiaj: date, aktywna_linia: str, work_first_map: Dict[str, int], logger=None) -> Set[int]:
        """Resolve Workowanie plans that may expose START based on current buffer queue.

        FIFO is resolved primarily by zasyp_id (physical batch flow), with product-name
        fallback kept only for legacy rows that may miss zasyp_id.
        """
        log = logger or _logger
        allowed_work_start_ids = set()
        try:
            table_bufor = get_table_name('bufor', aktywna_linia)
            table_plan = get_table_name('plan_produkcji', aktywna_linia)
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                f"""
                SELECT MIN(b.kolejka) as global_min_queue
                FROM {table_bufor} b
                WHERE DATE(b.data_planu) = %s AND b.status = 'aktywny'
                  AND EXISTS (
                      SELECT 1 FROM {table_plan} w
                      WHERE w.sekcja IN ('Workowanie', 'Czyszczenie') AND w.status IN ('zaplanowane', 'w toku') AND w.is_deleted = 0
                        AND DATE(w.data_planu) = %s
                        AND (w.zasyp_id = b.zasyp_id OR LOWER(TRIM(w.produkt)) = LOWER(TRIM(b.produkt)))
                  )
                """,
                (dzisiaj, dzisiaj),
            )
            result = cursor.fetchone()
            global_min_queue = result[0] if result and result[0] is not None else None
            log.info('[DEBUG-START] GLOBAL MIN kolejka w %s: %s', table_bufor, global_min_queue)

            if global_min_queue is None:
                log.info('[DEBUG-START] global_min_queue is None. Using work_first_map fallback.')
                for wid in work_first_map.values():
                    allowed_work_start_ids.add(wid)
            else:
                cursor.execute(
                    f"""
                    SELECT DISTINCT zasyp_id, produkt
                    FROM {table_bufor}
                    WHERE DATE(data_planu) = %s AND status = 'aktywny' AND kolejka = %s
                    """,
                    (dzisiaj, global_min_queue),
                )
                queue_rows = cursor.fetchall() or []
                log.info('[DEBUG-START] Wiersze z kolejka=%s: %s', global_min_queue, queue_rows)

                for row in queue_rows:
                    zasyp_id = row[0]
                    produkt = row[1] if len(row) > 1 else None

                    if zasyp_id:
                        cursor.execute(
                            f"""
                            SELECT id FROM {table_plan}
                            WHERE sekcja IN ('Workowanie', 'Czyszczenie')
                              AND status IN ('zaplanowane', 'w toku')
                              AND zasyp_id = %s
                              AND is_deleted = 0
                              AND DATE(data_planu) = %s
                            ORDER BY CASE status WHEN 'w toku' THEN 1 ELSE 2 END, data_planu DESC, kolejnosc ASC, id ASC
                            LIMIT 1
                            """,
                            (zasyp_id, dzisiaj),
                        )
                        plan_row = cursor.fetchone()
                        if plan_row:
                            allowed_work_start_ids.add(plan_row[0])
                            continue

                    # Legacy fallback for rows without zasyp_id linkage.
                    if not produkt:
                        continue
                    matched_key = next((key for key in work_first_map if key.strip().casefold() == produkt.strip().casefold()), None)
                    if matched_key:
                        allowed_work_start_ids.add(work_first_map[matched_key])
                        continue

                    try:
                        cursor.execute(
                            f"""
                            SELECT id FROM {table_plan}
                            WHERE sekcja IN ('Workowanie', 'Czyszczenie')
                              AND status IN ('zaplanowane', 'w toku')
                              AND LOWER(TRIM(produkt)) = LOWER(TRIM(%s))
                              AND is_deleted = 0
                              AND DATE(data_planu) = %s
                            ORDER BY CASE status WHEN 'w toku' THEN 1 ELSE 2 END, data_planu DESC, kolejnosc ASC, id ASC
                            LIMIT 1
                            """,
                            (produkt, dzisiaj),
                        )
                        row = cursor.fetchone()
                        if row:
                            allowed_work_start_ids.add(row[0])
                    except Exception as fallback_error:
                        log.error("[DEBUG-START] Błąd fallback dla '%s': %s", produkt, fallback_error)

            cursor.close()
            conn.close()
        except Exception as error:
            log.error('[ERROR-START] Błąd: %s', error)
            allowed_work_start_ids = set()

        return allowed_work_start_ids
