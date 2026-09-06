from typing import List, Dict, Any, Optional
from datetime import datetime
from app.db import get_db_connection, get_table_name

class LabQualityRepository:
    """
    Data Access Repository for Quality Control Laboratory Holds (Blokada LAB) and QA Releases.
    """

    @staticmethod
    def _get_target_table(pallet_type: str, linia: str = 'PSD') -> str:
        p_type = str(pallet_type or 'surowiec').lower()
        if 'opak' in p_type:
            return get_table_name('magazyn_opakowania', linia)
        elif 'dodat' in p_type:
            return 'magazyn_dodatki'
        elif 'wyrob' in p_type or 'palet' in p_type:
            return get_table_name('magazyn_palety', linia)
        return get_table_name('magazyn_surowce', linia)

    @staticmethod
    def block_pallet_in_lab(
        pallet_id: int,
        pallet_code: str,
        pallet_type: str,
        linia: str,
        reason: str,
        user_login: str
    ) -> int:
        """Record lab quality hold and flag the source pallet as blocked."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Insert into lab_blokady
            query_insert = """
                INSERT INTO lab_blokady (
                    pallet_id, pallet_code, pallet_type, linia, status,
                    powod_blokady, zablokowal_login, data_blokady
                ) VALUES (%s, %s, %s, %s, 'BLOKADA_LAB', %s, %s, NOW())
            """
            cursor.execute(query_insert, (
                pallet_id,
                str(pallet_code).strip().upper(),
                pallet_type.lower(),
                linia.upper(),
                reason,
                user_login
            ))
            block_id = cursor.lastrowid

            # 2. Update is_blocked in source table
            table = LabQualityRepository._get_target_table(pallet_type, linia)
            try:
                cursor.execute(f"UPDATE {table} SET is_blocked = 1 WHERE id = %s", (pallet_id,))
            except Exception:
                pass

            conn.commit()
            return block_id
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def release_pallet_from_lab(
        pallet_code: str,
        pallet_type: str,
        linia: str,
        user_login: str,
        comment: str = ''
    ) -> bool:
        """Release pallet from Lab hold, setting status to ZWOLNIONY_LAB and is_blocked = 0."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            norm_code = str(pallet_code).strip().upper()

            # 1. Update lab_blokady
            query_update = """
                UPDATE lab_blokady 
                SET status = 'ZWOLNIONY_LAB', zwolnil_login = %s, komentarz_lab = %s, data_zwolnienia = NOW()
                WHERE pallet_code = %s AND status = 'BLOKADA_LAB'
            """
            cursor.execute(query_update, (user_login, comment, norm_code))
            affected = cursor.rowcount > 0

            # 2. Unblock in source table
            table = LabQualityRepository._get_target_table(pallet_type, linia)
            try:
                cursor.execute(
                    f"UPDATE {table} SET is_blocked = 0 WHERE UPPER(nr_palety) = %s OR id = %s",
                    (norm_code, norm_code if norm_code.isdigit() else -1)
                )
            except Exception:
                pass

            conn.commit()
            return affected
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def is_pallet_blocked(pallet_code: str) -> Optional[Dict[str, Any]]:
        """Check if pallet is currently blocked by LAB."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT id, pallet_id, pallet_code, pallet_type, linia, status,
                       powod_blokady, zablokowal_login, data_blokady
                FROM lab_blokady
                WHERE pallet_code = %s AND status = 'BLOKADA_LAB'
                ORDER BY id DESC
                LIMIT 1
            """
            cursor.execute(query, (str(pallet_code).strip().upper(),))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_active_lab_blocks(linia: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all currently active LAB blocked pallets."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if linia:
                query = """
                    SELECT id, pallet_id, pallet_code, pallet_type, linia, status,
                           powod_blokady, zablokowal_login, data_blokady
                    FROM lab_blokady
                    WHERE status = 'BLOKADA_LAB' AND UPPER(linia) = %s
                    ORDER BY data_blokady DESC
                """
                cursor.execute(query, (linia.upper(),))
            else:
                query = """
                    SELECT id, pallet_id, pallet_code, pallet_type, linia, status,
                           powod_blokady, zablokowal_login, data_blokady
                    FROM lab_blokady
                    WHERE status = 'BLOKADA_LAB'
                    ORDER BY data_blokady DESC
                """
                cursor.execute(query)
            return cursor.fetchall() or []
        finally:
            cursor.close()
            conn.close()
