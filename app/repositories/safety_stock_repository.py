from typing import List, Dict, Any, Optional
from app.db import get_db_connection, get_table_name

class SafetyStockRepository:
    """
    Data Access Repository for Safety Stock, Reorder Points, and stock level thresholds.
    """

    @staticmethod
    def upsert_safety_threshold(
        kod_pozycji: str,
        nazwa: str,
        typ: str,
        linia: str,
        stan_minimalny: float,
        punkt_zamowienia: float,
        jednostka: str = 'kg',
        czas_dostawy_dni: int = 7
    ) -> bool:
        """Create or update safety stock threshold for a product/material."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO magazyn_stany_bezpieczenstwa (
                    kod_pozycji, nazwa, typ, linia, stan_minimalny,
                    punkt_zamowienia, jednostka, czas_dostawy_dni, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    nazwa = VALUES(nazwa),
                    typ = VALUES(typ),
                    stan_minimalny = VALUES(stan_minimalny),
                    punkt_zamowienia = VALUES(punkt_zamowienia),
                    jednostka = VALUES(jednostka),
                    czas_dostawy_dni = VALUES(czas_dostawy_dni),
                    updated_at = NOW()
            """
            cursor.execute(query, (
                str(kod_pozycji).strip().upper(),
                str(nazwa).strip(),
                typ.lower(),
                linia.upper(),
                float(stan_minimalny),
                float(punkt_zamowienia),
                jednostka.lower(),
                int(czas_dostawy_dni)
            ))
            conn.commit()
            return True
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_configured_thresholds(linia: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all configured safety stock rules."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if linia:
                query = """
                    SELECT id, kod_pozycji, nazwa, typ, linia, stan_minimalny,
                           punkt_zamowienia, jednostka, czas_dostawy_dni, updated_at
                    FROM magazyn_stany_bezpieczenstwa
                    WHERE UPPER(linia) = %s
                    ORDER BY typ ASC, nazwa ASC
                """
                cursor.execute(query, (linia.upper(),))
            else:
                query = """
                    SELECT id, kod_pozycji, nazwa, typ, linia, stan_minimalny,
                           punkt_zamowienia, jednostka, czas_dostawy_dni, updated_at
                    FROM magazyn_stany_bezpieczenstwa
                    ORDER BY linia ASC, typ ASC, nazwa ASC
                """
                cursor.execute(query)
            return cursor.fetchall() or []
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_actual_stock_for_material(nazwa: str, typ: str = 'surowiec', linia: str = 'PSD') -> float:
        """Calculate current total available stock for a product/material across warehouse."""
        norm_line = linia.upper()
        p_type = typ.lower()
        if 'opak' in p_type:
            table = get_table_name('magazyn_opakowania', norm_line)
        elif 'dodat' in p_type:
            table = 'magazyn_dodatki'
        else:
            table = get_table_name('magazyn_surowce', norm_line)

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = f"""
                SELECT COALESCE(SUM(stan_magazynowy), 0)
                FROM {table}
                WHERE UPPER(nazwa) = UPPER(%s) 
                  AND stan_magazynowy > 0
                  AND COALESCE(is_blocked, 0) = 0
            """
            cursor.execute(query, (nazwa,))
            res = cursor.fetchone()
            return float(res[0]) if res and res[0] else 0.0
        finally:
            cursor.close()
            conn.close()
