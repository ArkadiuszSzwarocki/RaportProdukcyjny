from typing import List, Dict, Any, Optional
from datetime import datetime
from app.db import get_db_connection

class ProductionBomVarianceRepository:
    """
    Repository for managing production recipe BOM variances and tolerance thresholds.
    """

    @staticmethod
    def record_variance(
        plan_id: int,
        linia: str,
        kod_produktu: str,
        skladnik: str,
        waga_recepturowa: float,
        waga_rzeczywista: float,
        odchylka_kg: float,
        odchylka_procent: float,
        tolerancja_procent: float,
        is_exceeded: bool,
        user_login: str = 'system',
        conn=None
    ) -> int:
        """Persist recipe component variance log."""
        connection = conn or get_db_connection()
        cursor = connection.cursor()
        should_close = conn is None

        query = """
            INSERT INTO produkcja_odchylki_recepturowe (
                plan_id, linia, kod_produktu, skladnik,
                waga_recepturowa, waga_rzeczywista, odchylka_kg,
                odchylka_procent, tolerancja_procent, is_exceeded,
                user_login, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        now_ts = datetime.now()
        cursor.execute(
            query,
            (
                int(plan_id),
                str(linia or 'PSD').upper(),
                str(kod_produktu or '').strip(),
                str(skladnik or '').strip(),
                float(waga_recepturowa),
                float(waga_rzeczywista),
                float(odchylka_kg),
                float(odchylka_procent),
                float(tolerancja_procent),
                1 if is_exceeded else 0,
                str(user_login or 'system'),
                now_ts
            )
        )
        inserted_id = cursor.lastrowid
        cursor.close()

        if should_close:
            connection.commit()
            connection.close()

        return inserted_id

    @staticmethod
    def get_variances_by_plan(plan_id: int, linia: str = 'PSD') -> List[Dict[str, Any]]:
        """Fetch all recorded variances for a specific production plan."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT id, plan_id, linia, kod_produktu, skladnik,
                   waga_recepturowa, waga_rzeczywista, odchylka_kg,
                   odchylka_procent, tolerancja_procent, is_exceeded,
                   user_login, created_at
            FROM produkcja_odchylki_recepturowe
            WHERE plan_id = %s AND linia = %s
            ORDER BY created_at ASC
        """
        cursor.execute(query, (plan_id, linia.upper()))
        rows = cursor.fetchall() or []
        cursor.close()
        conn.close()
        return rows
