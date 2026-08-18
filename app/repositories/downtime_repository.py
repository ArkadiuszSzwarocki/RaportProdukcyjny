"""
Repozytorium do obsługi operacji bazodanowych dla przestojów produkcyjnych (Workowanie) oraz przestojów zasypów (Zasyp).
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, date

from app.db import get_db_connection, get_table_name


class DowntimeRepository:
    """Repozytorium dla przestoje_produkcyjne oraz przestoje_zasyp."""

    @staticmethod
    def get_table_name_by_section(sekcja: Optional[str] = None) -> str:
        """Determinuje docelową tabelę w zależności od sekcji."""
        if sekcja and sekcja.strip().lower() == 'zasyp':
            return 'przestoje_zasyp'
        return 'przestoje_produkcyjne'

    def insert_downtime(
        self,
        linia: str,
        sekcja: str,
        plan_id: Optional[int],
        produkt: Optional[str],
        data_przestoju: str,
        godzina_start: str,
        godzina_stop: Optional[str],
        czas_trwania_min: Optional[int],
        kategoria: str,
        opis: str,
        zglaszajacy: str,
        zdjecie_url: Optional[str] = None
    ) -> int:
        table_name = self.get_table_name_by_section(sekcja)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = f"""
                INSERT INTO {table_name}
                (linia, sekcja, plan_id, produkt, data_przestoju, godzina_start, godzina_stop, czas_trwania_min, kategoria, opis, zdjecie_url, zglaszajacy, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """
            cursor.execute(query, (linia, sekcja, plan_id, produkt, data_przestoju, godzina_start, godzina_stop, czas_trwania_min, kategoria, opis, zdjecie_url, zglaszajacy))
            inserted_id = cursor.lastrowid
            conn.commit()
            return inserted_id
        finally:
            conn.close()

    def update_downtime(
        self,
        downtime_id: int,
        linia: str,
        sekcja: str,
        plan_id: Optional[int],
        produkt: Optional[str],
        data_przestoju: str,
        godzina_start: str,
        godzina_stop: Optional[str],
        czas_trwania_min: Optional[int],
        kategoria: str,
        opis: str,
        zdjecie_url: Optional[str] = None
    ) -> bool:
        table_name = self.get_table_name_by_section(sekcja)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if zdjecie_url is not None:
                query = f"""
                    UPDATE {table_name}
                    SET linia = %s, sekcja = %s, plan_id = %s, produkt = %s,
                        data_przestoju = %s, godzina_start = %s, godzina_stop = %s,
                        czas_trwania_min = %s, kategoria = %s, opis = %s, zdjecie_url = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (linia, sekcja, plan_id, produkt, data_przestoju, godzina_start, godzina_stop, czas_trwania_min, kategoria, opis, zdjecie_url, downtime_id))
            else:
                query = f"""
                    UPDATE {table_name}
                    SET linia = %s, sekcja = %s, plan_id = %s, produkt = %s,
                        data_przestoju = %s, godzina_start = %s, godzina_stop = %s,
                        czas_trwania_min = %s, kategoria = %s, opis = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (linia, sekcja, plan_id, produkt, data_przestoju, godzina_start, godzina_stop, czas_trwania_min, kategoria, opis, downtime_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_downtime_by_id(self, downtime_id: int, sekcja: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            tables = [self.get_table_name_by_section(sekcja)] if sekcja else ['przestoje_zasyp', 'przestoje_produkcyjne']
            for table in tables:
                cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (downtime_id,))
                row = cursor.fetchone()
                if row:
                    return row
            return None
        finally:
            conn.close()

    def delete_downtime(self, downtime_id: int, sekcja: Optional[str] = None) -> bool:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            tables = [self.get_table_name_by_section(sekcja)] if sekcja else ['przestoje_zasyp', 'przestoje_produkcyjne']
            deleted = False
            for table in tables:
                cursor.execute(f"DELETE FROM {table} WHERE id = %s", (downtime_id,))
                if cursor.rowcount > 0:
                    deleted = True
                    break
            conn.commit()
            return deleted
        finally:
            conn.close()

    def get_downtimes(self, linia: str, data_od: str, data_do: str, sekcja: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            results = []
            
            if sekcja and sekcja.strip().lower() in ('zasyp', 'workowanie'):
                table = self.get_table_name_by_section(sekcja)
                query = f"SELECT * FROM {table} WHERE linia = %s AND data_przestoju BETWEEN %s AND %s ORDER BY data_przestoju DESC, godzina_start DESC"
                cursor.execute(query, (linia, data_od, data_do))
                results = cursor.fetchall() or []
            else:
                q1 = f"SELECT * FROM przestoje_produkcyjne WHERE linia = %s AND data_przestoju BETWEEN %s AND %s"
                q2 = f"SELECT * FROM przestoje_zasyp WHERE linia = %s AND data_przestoju BETWEEN %s AND %s"
                cursor.execute(q1, (linia, data_od, data_do))
                r1 = cursor.fetchall() or []
                cursor.execute(q2, (linia, data_od, data_do))
                r2 = cursor.fetchall() or []
                results = r1 + r2
                results.sort(key=lambda x: (x.get('data_przestoju') or date.min, str(x.get('godzina_start') or '')), reverse=True)

            return results
        finally:
            conn.close()

    def get_downtime_summary_map(self, plan_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Zwraca mapę sumy przestojów dla podanych identyfikatorów plan_id: {plan_id: {'total_min': int, 'count': int}}."""
        if not plan_ids:
            return {}
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            valid_ids = [int(p) for p in plan_ids if str(p).isdigit()]
            if not valid_ids:
                return {}

            fmt_ids = ','.join(['%s'] * len(valid_ids))
            summary_map = {pid: {'total_min': 0, 'count': 0, 'items': []} for pid in valid_ids}

            for table in ['przestoje_produkcyjne', 'przestoje_zasyp']:
                try:
                    query = f"""
                        SELECT id, plan_id, sekcja, kategoria, opis, data_przestoju, godzina_start, godzina_stop, czas_trwania_min
                        FROM {table}
                        WHERE plan_id IN ({fmt_ids})
                    """
                    cursor.execute(query, tuple(valid_ids))
                    rows = cursor.fetchall() or []
                    for r in rows:
                        pid = r['plan_id']
                        if pid in summary_map:
                            duration = r.get('czas_trwania_min')
                            if duration is None and r.get('godzina_start') and r.get('godzina_stop'):
                                try:
                                    t1 = datetime.strptime(str(r['godzina_start'])[:5], '%H:%M')
                                    t2 = datetime.strptime(str(r['godzina_stop'])[:5], '%H:%M')
                                    diff = int((t2 - t1).total_seconds() / 60)
                                    if diff < 0:
                                        diff += 1440
                                    duration = diff
                                except Exception:
                                    duration = 0
                            elif duration is None and r.get('godzina_start'):
                                try:
                                    t1 = datetime.strptime(str(r['godzina_start'])[:5], '%H:%M')
                                    now = datetime.now()
                                    t2 = datetime.strptime(now.strftime('%H:%M'), '%H:%M')
                                    diff = int((t2 - t1).total_seconds() / 60)
                                    if diff < 0:
                                        diff += 1440
                                    duration = diff
                                except Exception:
                                    duration = 0

                            dur_val = int(duration or 0)
                            summary_map[pid]['total_min'] += dur_val
                            summary_map[pid]['count'] += 1
                            summary_map[pid]['items'].append(r)
                except Exception:
                    pass

            return summary_map
        finally:
            conn.close()

