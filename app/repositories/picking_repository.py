"""
Repository for warehouse picking (completion) orders.

Responsibility: CRUD operations on magazyn_kompletacja table.
Zero business logic — data access layer only.
"""
from datetime import datetime
from app.core.database import get_db_connection


class PickingRepository:
    """Data access layer for picking order records."""

    @staticmethod
    def create_picking_items(items):
        """Bulk-inserts picking allocation rows into magazyn_kompletacja.

        Args:
            items: List of dicts with keys:
                order_ref, surowiec_nazwa, paleta_id, nr_palety,
                lokalizacja_zrodlowa, ilosc_kg, nr_partii, fifo_rank,
                is_blocked, powod_blokady, operator_login.

        Returns:
            int: Number of inserted rows.
        """
        if not items:
            return 0

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            insert_sql = """
                INSERT INTO magazyn_kompletacja
                    (order_ref, surowiec_nazwa, paleta_id, nr_palety,
                     lokalizacja_zrodlowa, lokalizacja_docelowa, ilosc_kg,
                     nr_partii, fifo_rank, is_blocked, powod_blokady,
                     status, operator_login, magazynier_login, created_at, completed_at)
                VALUES (%s, %s, %s, %s, %s, 'MP01', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            now = datetime.now()
            rows = []
            for item in items:
                source_loc = str(item.get('lokalizacja_zrodlowa') or '').strip().upper()
                is_mp01 = (source_loc == 'MP01')
                is_blocked = bool(item.get('is_blocked'))

                if item.get('status'):
                    status = item['status']
                elif is_blocked:
                    status = 'POMINIETA'
                elif is_mp01:
                    status = 'SKOMPLETOWANA'
                else:
                    status = 'OCZEKUJE'

                completed_at = now if status == 'SKOMPLETOWANA' else None
                magazynier_login = (item.get('operator_login') or 'SYSTEM (MP01)') if status == 'SKOMPLETOWANA' else None

                rows.append((
                    item['order_ref'],
                    item['surowiec_nazwa'],
                    item['paleta_id'],
                    item['nr_palety'],
                    source_loc,
                    item['ilosc_kg'],
                    item.get('nr_partii', ''),
                    item.get('fifo_rank'),
                    1 if is_blocked else 0,
                    item.get('powod_blokady', ''),
                    status,
                    item.get('operator_login', ''),
                    magazynier_login,
                    now,
                    completed_at,
                ))
            cursor.executemany(insert_sql, rows)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def get_by_order_ref(order_ref):
        """Fetches all picking items for a given order reference.

        Args:
            order_ref: Unique picking order reference string.

        Returns:
            list[dict]: Picking items sorted by surowiec + fifo_rank.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT * FROM magazyn_kompletacja
                WHERE order_ref = %s
                ORDER BY surowiec_nazwa ASC, fifo_rank ASC, id ASC
                """,
                (order_ref,)
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_active_orders(operator_login=None):
        """Fetches distinct active picking orders (having at least one OCZEKUJE item).

        Args:
            operator_login: Optional filter by operator who created the order.

        Returns:
            list[dict]: Distinct order references with summary stats.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            base_query = """
                SELECT
                    order_ref,
                    operator_login,
                    MIN(created_at) as created_at,
                    COUNT(*) as total_items,
                    SUM(CASE WHEN status = 'SKOMPLETOWANA' THEN 1 ELSE 0 END) as completed_items,
                    SUM(CASE WHEN status = 'OCZEKUJE' THEN 1 ELSE 0 END) as pending_items,
                    SUM(CASE WHEN status = 'POMINIETA' THEN 1 ELSE 0 END) as skipped_items
                FROM magazyn_kompletacja
            """
            if operator_login:
                base_query += " WHERE operator_login = %s"
                base_query += " GROUP BY order_ref, operator_login HAVING completed_items < total_items ORDER BY MIN(created_at) DESC"
                cursor.execute(base_query, (operator_login,))
            else:
                base_query += " GROUP BY order_ref, operator_login HAVING completed_items < total_items ORDER BY MIN(created_at) DESC"
                cursor.execute(base_query)

            orders = cursor.fetchall()
            for o in orders:
                if o.get('created_at'):
                    o['created_at'] = o['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            return orders
        finally:
            conn.close()

    @staticmethod
    def get_all_orders(limit=50):
        """Fetches all picking orders (active + completed) for history view.

        Args:
            limit: Maximum number of distinct orders to return.

        Returns:
            list[dict]: Distinct order references with summary stats.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    order_ref,
                    operator_login,
                    MIN(created_at) as created_at,
                    MAX(completed_at) as last_completed_at,
                    COUNT(*) as total_items,
                    SUM(CASE WHEN status = 'SKOMPLETOWANA' THEN 1 ELSE 0 END) as completed_items,
                    SUM(CASE WHEN status = 'OCZEKUJE' THEN 1 ELSE 0 END) as pending_items,
                    SUM(CASE WHEN status = 'POMINIETA' THEN 1 ELSE 0 END) as skipped_items,
                    SUM(CASE WHEN status = 'ANULOWANA' THEN 1 ELSE 0 END) as cancelled_items
                FROM magazyn_kompletacja
                GROUP BY order_ref, operator_login
                ORDER BY MIN(created_at) DESC
                LIMIT %s
                """,
                (limit,)
            )
            orders = cursor.fetchall()
            for o in orders:
                if o.get('created_at'):
                    o['created_at'] = o['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                if o.get('last_completed_at'):
                    o['last_completed_at'] = o['last_completed_at'].strftime('%Y-%m-%d %H:%M:%S')
            return orders
        finally:
            conn.close()

    @staticmethod
    def mark_item_completed(item_id, magazynier_login):
        """Marks a single picking item as completed.

        Args:
            item_id: ID of the magazyn_kompletacja row.
            magazynier_login: Login of the warehouse worker who scanned.

        Returns:
            int: Number of updated rows (0 if not found or already completed).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE magazyn_kompletacja
                SET status = 'SKOMPLETOWANA',
                    magazynier_login = %s,
                    completed_at = %s
                WHERE id = %s AND status = 'OCZEKUJE'
                """,
                (magazynier_login, datetime.now(), item_id)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def mark_item_skipped(item_id, reason=''):
        """Marks a single picking item as skipped.

        Args:
            item_id: ID of the magazyn_kompletacja row.
            reason: Reason for skipping.

        Returns:
            int: Number of updated rows.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE magazyn_kompletacja
                SET status = 'POMINIETA',
                    powod_blokady = CONCAT(COALESCE(powod_blokady, ''), %s),
                    completed_at = %s
                WHERE id = %s AND status = 'OCZEKUJE'
                """,
                (reason, datetime.now(), item_id)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def cancel_order(order_ref):
        """Cancels all pending items in a picking order.

        Args:
            order_ref: Picking order reference.

        Returns:
            int: Number of cancelled rows.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE magazyn_kompletacja
                SET status = 'ANULOWANA',
                    completed_at = %s
                WHERE order_ref = %s AND status = 'OCZEKUJE'
                """,
                (datetime.now(), order_ref)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def delete_order(order_ref):
        """Trwale usuwa wszystkie pozycje dyspozycji kompletacji.

        Args:
            order_ref: Unikalny identyfikator dyspozycji (np. PICK-20260919-001).

        Returns:
            int: Liczba usuniętych wierszy.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM magazyn_kompletacja WHERE order_ref = %s",
                (order_ref,)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def find_item_by_sscc(order_ref, sscc_code):
        """Finds a pending picking item by SSCC code within a specific order.

        Args:
            order_ref: Picking order reference.
            sscc_code: Scanned SSCC barcode.

        Returns:
            dict | None: Matching picking item or None.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT * FROM magazyn_kompletacja
                WHERE order_ref = %s
                  AND TRIM(nr_palety) = TRIM(%s)
                  AND status = 'OCZEKUJE'
                LIMIT 1
                """,
                (order_ref, sscc_code)
            )
            return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_next_order_sequence():
        """Generates the next sequential number for today's picking orders.

        Returns:
            int: Next sequence number (1-based).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            today_prefix = datetime.now().strftime('%Y%m%d')
            pattern = f'PICK-{today_prefix}-%'
            cursor.execute(
                "SELECT COUNT(DISTINCT order_ref) as cnt FROM magazyn_kompletacja WHERE order_ref LIKE %s",
                (pattern,)
            )
            row = cursor.fetchone()
            return (row.get('cnt', 0) if row else 0) + 1
        finally:
            conn.close()
