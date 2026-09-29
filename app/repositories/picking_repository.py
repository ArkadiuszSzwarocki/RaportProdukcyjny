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
        """Bulk-inserts picking allocation rows into magazyn_kompletacja."""
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
                is_mp01 = source_loc == 'MP01'
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
                magazynier_login = (
                    item.get('operator_login') or 'SYSTEM (MP01)'
                ) if status == 'SKOMPLETOWANA' else None

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
        """Fetch all picking items for one order reference."""
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
        """Fetch active picking orders.

        An order is active when it has a pallet waiting for collection OR an unresolved
        shortage placeholder (paleta_id=0, POMINIETA) waiting for future stock.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            base_query = """
                SELECT
                    order_ref,
                    operator_login,
                    MIN(created_at) AS created_at,
                    COUNT(*) AS total_items,
                    SUM(CASE WHEN status = 'SKOMPLETOWANA' THEN 1 ELSE 0 END) AS completed_items,
                    SUM(CASE WHEN status = 'OCZEKUJE' THEN 1 ELSE 0 END) AS pending_items,
                    SUM(CASE WHEN status = 'POMINIETA' THEN 1 ELSE 0 END) AS skipped_items,
                    SUM(CASE WHEN status = 'POMINIETA' AND paleta_id = 0 THEN 1 ELSE 0 END) AS shortage_items
                FROM magazyn_kompletacja
            """
            group_and_having = (
                " GROUP BY order_ref, operator_login "
                "HAVING pending_items > 0 OR shortage_items > 0 "
                "ORDER BY MIN(created_at) DESC"
            )
            if operator_login:
                cursor.execute(base_query + " WHERE operator_login = %s" + group_and_having, (operator_login,))
            else:
                cursor.execute(base_query + group_and_having)

            orders = cursor.fetchall()
            for order in orders:
                if order.get('created_at'):
                    order['created_at'] = order['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            return orders
        finally:
            conn.close()

    @staticmethod
    def get_all_orders(limit=50):
        """Fetch all picking orders (active + completed) for history view."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    order_ref,
                    operator_login,
                    MIN(created_at) AS created_at,
                    MAX(completed_at) AS last_completed_at,
                    COUNT(*) AS total_items,
                    SUM(CASE WHEN status = 'SKOMPLETOWANA' THEN 1 ELSE 0 END) AS completed_items,
                    SUM(CASE WHEN status = 'OCZEKUJE' THEN 1 ELSE 0 END) AS pending_items,
                    SUM(CASE WHEN status = 'POMINIETA' THEN 1 ELSE 0 END) AS skipped_items,
                    SUM(CASE WHEN status = 'POMINIETA' AND paleta_id = 0 THEN 1 ELSE 0 END) AS shortage_items,
                    SUM(CASE WHEN status = 'ANULOWANA' THEN 1 ELSE 0 END) AS cancelled_items
                FROM magazyn_kompletacja
                GROUP BY order_ref, operator_login
                ORDER BY MIN(created_at) DESC
                LIMIT %s
                """,
                (limit,)
            )
            orders = cursor.fetchall()
            for order in orders:
                if order.get('created_at'):
                    order['created_at'] = order['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                if order.get('last_completed_at'):
                    order['last_completed_at'] = order['last_completed_at'].strftime('%Y-%m-%d %H:%M:%S')
            return orders
        finally:
            conn.close()

    @staticmethod
    def mark_item_completed(item_id, magazynier_login):
        """Mark a single pending picking item as completed."""
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
        """Mark a single pending picking item as skipped."""
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
        """Cancel pending pallets and unresolved shortage placeholders."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE magazyn_kompletacja
                SET status = 'ANULOWANA',
                    completed_at = %s
                WHERE order_ref = %s
                  AND (
                      status = 'OCZEKUJE'
                      OR (status = 'POMINIETA' AND paleta_id = 0)
                  )
                """,
                (datetime.now(), order_ref)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def delete_order(order_ref):
        """Permanently delete all rows of a picking order."""
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
        """Find a pending picking item by SSCC within a specific order."""
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
        """Return the next daily sequence without reusing a number after deletion.

        Handles both historical PICK-YYYYMMDD-001 references and the newer
        collision-resistant PICK-YYYYMMDD-001-ABCD form.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            today_prefix = datetime.now().strftime('%Y%m%d')
            pattern = f'PICK-{today_prefix}-%'
            cursor.execute(
                """
                SELECT MAX(
                    CAST(
                        SUBSTRING_INDEX(
                            SUBSTRING_INDEX(order_ref, '-', 3),
                            '-',
                            -1
                        ) AS UNSIGNED
                    )
                ) AS max_seq
                FROM magazyn_kompletacja
                WHERE order_ref LIKE %s
                """,
                (pattern,)
            )
            row = cursor.fetchone() or {}
            return int(row.get('max_seq') or 0) + 1
        finally:
            conn.close()
