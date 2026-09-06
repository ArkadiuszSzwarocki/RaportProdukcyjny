from typing import List, Dict, Any, Optional
from datetime import datetime
from app.db import get_db_connection

class WarehouseMovementLedgerRepository:
    """
    Repository for recording and querying unified stock movements (PZ, WZ, MM, RW, PW, INW).
    Follows Clean Architecture & CQRS principles.
    """

    @staticmethod
    def record_movement(
        movement_type: str,
        pallet_code: str,
        product_name: str = '',
        batch_number: str = '',
        source_location: str = '',
        target_location: str = '',
        quantity: float = 0.0,
        unit: str = 'kg',
        user_login: str = 'system',
        reference_id: str = '',
        notes: Optional[str] = None,
        pallet_id: Optional[int] = None,
        external_conn=None
    ) -> int:
        """
        Records a movement event in the unified ledger.
        Accepts an optional external_conn to participate in an ambient ACID transaction.
        """
        conn = external_conn or get_db_connection()
        cursor = conn.cursor()
        should_close = external_conn is None

        query = """
            INSERT INTO magazyn_ruchy_unified (
                movement_type, pallet_id, pallet_code, product_name, batch_number,
                source_location, target_location, quantity, unit, user_login,
                reference_id, notes, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        now_ts = datetime.now()
        cursor.execute(
            query,
            (
                movement_type.upper(),
                pallet_id,
                str(pallet_code or '').strip().upper(),
                str(product_name or '').strip(),
                str(batch_number or '').strip(),
                str(source_location or '').strip().upper(),
                str(target_location or '').strip().upper(),
                float(quantity or 0.0),
                str(unit or 'kg').strip().lower(),
                str(user_login or 'system').strip(),
                str(reference_id or '').strip(),
                notes,
                now_ts
            )
        )
        inserted_id = cursor.lastrowid
        cursor.close()

        if should_close:
            conn.commit()
            conn.close()

        return inserted_id

    @staticmethod
    def get_movements_by_pallet(pallet_code: str) -> List[Dict[str, Any]]:
        """Fetch chronological movement history for a given pallet / SSCC code."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT id, movement_type, pallet_id, pallet_code, product_name, batch_number,
                   source_location, target_location, quantity, unit, user_login,
                   reference_id, notes, created_at
            FROM magazyn_ruchy_unified
            WHERE pallet_code = %s
            ORDER BY created_at DESC, id DESC
        """
        cursor.execute(query, (str(pallet_code or '').strip().upper(),))
        rows = cursor.fetchall() or []
        cursor.close()
        conn.close()
        return rows

    @staticmethod
    def get_recent_movements(limit: int = 50, movement_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch the most recent stock ledger movements."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if movement_type:
            query = """
                SELECT id, movement_type, pallet_id, pallet_code, product_name, batch_number,
                       source_location, target_location, quantity, unit, user_login,
                       reference_id, notes, created_at
                FROM magazyn_ruchy_unified
                WHERE movement_type = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
            """
            cursor.execute(query, (movement_type.upper(), limit))
        else:
            query = """
                SELECT id, movement_type, pallet_id, pallet_code, product_name, batch_number,
                       source_location, target_location, quantity, unit, user_login,
                       reference_id, notes, created_at
                FROM magazyn_ruchy_unified
                ORDER BY created_at DESC, id DESC
                LIMIT %s
            """
            cursor.execute(query, (limit,))

        rows = cursor.fetchall() or []
        cursor.close()
        conn.close()
        return rows
