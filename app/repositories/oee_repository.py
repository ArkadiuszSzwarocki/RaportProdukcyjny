from typing import Dict, Any, List
from datetime import datetime, date
from app.db import get_db_connection, get_table_name

class OeeRepository:
    """
    Data Access Repository for real-time Overall Equipment Effectiveness (OEE) metrics.
    """

    @staticmethod
    def get_shift_production_data(target_date: str, linia: str = 'PSD') -> Dict[str, Any]:
        """Fetch planned vs actual production tonnage for the specified date."""
        table_plan = get_table_name('plan_produkcji', linia)
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            query = f"""
                SELECT 
                    COUNT(*) as total_orders,
                    COALESCE(SUM(tonaz), 0) as planned_tonnage,
                    COALESCE(SUM(tonaz_rzeczywisty), 0) as actual_tonnage,
                    COALESCE(SUM(CASE WHEN status = 'zakonczone' THEN 1 ELSE 0 END), 0) as completed_orders
                FROM {table_plan}
                WHERE data_planu = %s
            """
            cursor.execute(query, (target_date,))
            row = cursor.fetchone() or {}
            return {
                'total_orders': int(row.get('total_orders') or 0),
                'planned_tonnage': float(row.get('planned_tonnage') or 0.0),
                'actual_tonnage': float(row.get('actual_tonnage') or 0.0),
                'completed_orders': int(row.get('completed_orders') or 0)
            }
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_shift_downtime_minutes(target_date: str, linia: str = 'PSD') -> int:
        """Fetch total recorded downtime duration in minutes for the given line and date."""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            query = """
                SELECT COALESCE(SUM(czas_trwania_min), 0)
                FROM przestoje_produkcyjne
                WHERE data_przestoju = %s AND UPPER(linia) = %s
            """
            cursor.execute(query, (target_date, linia.upper()))
            res = cursor.fetchone()
            return int(res[0]) if res and res[0] else 0
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_shift_quality_losses_kg(target_date: str, linia: str = 'PSD') -> float:
        """Fetch total quality loss / rework tonnage from BOM variance errors for the date."""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            query = """
                SELECT COALESCE(SUM(ABS(odchylka_kg)), 0)
                FROM produkcja_odchylki_recepturowe
                WHERE DATE(created_at) = %s AND UPPER(linia) = %s AND is_exceeded = 1
            """
            cursor.execute(query, (target_date, linia.upper()))
            res = cursor.fetchone()
            return float(res[0]) if res and res[0] else 0.0
        finally:
            cursor.close()
            conn.close()
