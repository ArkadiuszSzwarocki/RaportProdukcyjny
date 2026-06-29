from datetime import date, datetime
from typing import List, Optional
from app.db import get_db_connection
from app.models.separator_cleaning_record import SeparatorCleaningRecord

class SeparatorCleaningRepository:
    def get_by_date_and_line(self, data_planu: date, linia: str) -> Optional[SeparatorCleaningRecord]:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM czyszczenie_separatorow WHERE data_planu = %s AND linia = %s",
                (data_planu, linia)
            )
            row = cursor.fetchone()
            if row:
                return SeparatorCleaningRecord.from_dict(row)
            return None
        finally:
            cursor.close()
            conn.close()

    def get_pending_cleanings(self, max_date: date) -> List[SeparatorCleaningRecord]:
        """Pobiera wszystkie niepotwierdzone (status='pending') wpisy czyszczeń do podanej daty."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM czyszczenie_separatorow WHERE status = 'pending' AND data_planu <= %s ORDER BY data_planu DESC",
                (max_date,)
            )
            rows = cursor.fetchall()
            return [SeparatorCleaningRecord.from_dict(row) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def create(self, record: SeparatorCleaningRecord) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO czyszczenie_separatorow 
                (linia, data_planu, data_wykonania, login_wykonawcy, status, komentarz)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (record.linia, record.data_planu, record.data_wykonania, record.login_wykonawcy, record.status, record.komentarz)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            cursor.close()
            conn.close()

    def mark_as_completed(self, id: int, login_wykonawcy: str, data_wykonania: datetime, komentarz: str = None) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE czyszczenie_separatorow 
                SET status = 'completed', login_wykonawcy = %s, data_wykonania = %s, komentarz = %s
                WHERE id = %s AND status = 'pending'
                """,
                (login_wykonawcy, data_wykonania, komentarz, id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def get_all(self, limit: int = 100) -> List[SeparatorCleaningRecord]:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM czyszczenie_separatorow ORDER BY data_planu DESC, id DESC LIMIT %s",
                (limit,)
            )
            rows = cursor.fetchall()
            return [SeparatorCleaningRecord.from_dict(row) for row in rows]
        finally:
            cursor.close()
            conn.close()
