from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from app.db import get_db_connection, get_table_name

class WarehousePalletRepository:
    """
    Data Access Repository for warehouse pallets and workowanie buffers.
    Encapsulates raw SQL queries, transaction management, and pessimistic row locks (FOR UPDATE).
    """

    @staticmethod
    def get_plan_info(plan_id: int, linia: str = 'PSD', conn=None) -> Optional[Dict[str, Any]]:
        """Fetch production plan details required for pallet allocation."""
        table_plan = get_table_name('plan_produkcji', linia)
        connection = conn or get_db_connection()
        cursor = connection.cursor(dictionary=True)
        should_close = conn is None

        query = f"SELECT id, sekcja, data_planu, produkt, data_produkcji, zasyp_id FROM {table_plan} WHERE id = %s"
        cursor.execute(query, (plan_id,))
        row = cursor.fetchone()
        cursor.close()

        if should_close:
            connection.close()
        return row

    @staticmethod
    def find_reserved_pallet(plan_id: int, linia: str = 'PSD', lock_for_update: bool = False, conn=None) -> Optional[Dict[str, Any]]:
        """Find the oldest reserved label for the plan with optional row locking."""
        table_pal = get_table_name('palety_workowanie', linia)
        connection = conn or get_db_connection()
        cursor = connection.cursor(dictionary=True)
        should_close = conn is None

        lock_clause = "FOR UPDATE" if lock_for_update else ""
        query = f"""
            SELECT id, nr_palety, status, plan_id 
            FROM {table_pal} 
            WHERE plan_id = %s AND COALESCE(status, '') = 'rezerwacja' 
            ORDER BY id ASC 
            LIMIT 1 {lock_clause}
        """
        cursor.execute(query, (plan_id,))
        row = cursor.fetchone()
        cursor.close()

        if should_close:
            connection.close()
        return row

    @staticmethod
    def find_cleaning_sscc(plan_id: int, zasyp_id: Optional[int], linia: str = 'PSD', conn=None) -> Optional[str]:
        """Resolve SSCC code for cleaning product if present."""
        table_plan = get_table_name('plan_produkcji', linia)
        connection = conn or get_db_connection()
        cursor = connection.cursor()
        should_close = conn is None

        cursor.execute(
            f"SELECT skan_sscc FROM {table_plan} WHERE id IN (%s, %s) AND skan_sscc IS NOT NULL LIMIT 1",
            (plan_id, zasyp_id or -1)
        )
        row = cursor.fetchone()
        cursor.close()

        if should_close:
            connection.close()
        return row[0] if (row and row[0]) else None

    @staticmethod
    def update_reserved_pallet(
        pallet_id: int,
        linia: str,
        waga: float,
        data_dodania: datetime,
        user_login: str,
        nr_palety: str,
        nr_plomby: Optional[str],
        conn=None
    ) -> bool:
        """Update existing reserved pallet to active workowanie status."""
        table_pal = get_table_name('palety_workowanie', linia)
        connection = conn or get_db_connection()
        cursor = connection.cursor()
        should_close = conn is None

        query = f"""
            UPDATE {table_pal} 
            SET waga = %s, tara = 25, waga_brutto = 0, data_dodania = %s, 
                status = 'do_przyjecia', dodal_login = %s, nr_palety = %s, 
                nr_plomby = COALESCE(%s, nr_plomby) 
            WHERE id = %s
        """
        cursor.execute(query, (waga, data_dodania, user_login, nr_palety, nr_plomby, pallet_id))
        affected = cursor.rowcount > 0
        cursor.close()

        if should_close:
            connection.commit()
            connection.close()
        return affected

    @staticmethod
    def insert_new_pallet(
        plan_id: int,
        linia: str,
        waga: float,
        data_dodania: datetime,
        user_login: str,
        nr_palety: str,
        nr_plomby: Optional[str],
        conn=None
    ) -> int:
        """Insert newly declared pallet into workowanie table."""
        table_pal = get_table_name('palety_workowanie', linia)
        connection = conn or get_db_connection()
        cursor = connection.cursor()
        should_close = conn is None

        query = f"""
            INSERT INTO {table_pal} 
            (plan_id, waga, tara, waga_brutto, data_dodania, status, dodal_login, nr_palety, nr_plomby) 
            VALUES (%s, %s, 25, 0, %s, 'do_przyjecia', %s, %s, %s)
        """
        cursor.execute(query, (plan_id, waga, data_dodania, user_login, nr_palety, nr_plomby))
        new_id = cursor.lastrowid
        cursor.close()

        if should_close:
            connection.commit()
            connection.close()
        return new_id

    @staticmethod
    def get_pallet_by_id_locked(pallet_id: int, linia: str = 'PSD', conn=None) -> Optional[Dict[str, Any]]:
        """Fetch a pallet with pessimistic row-locking (FOR UPDATE) to prevent concurrency races."""
        table_pal = get_table_name('palety_workowanie', linia)
        connection = conn or get_db_connection()
        cursor = connection.cursor(dictionary=True)
        should_close = conn is None

        query = f"SELECT * FROM {table_pal} WHERE id = %s FOR UPDATE"
        cursor.execute(query, (pallet_id,))
        row = cursor.fetchone()
        cursor.close()

        if should_close:
            connection.close()
        return row
