"""
Wersja: 1.1.0
Opis: Zapytania SQL dla HR i wniosków urlopowych.
"""
from app.db import get_db_connection
from datetime import date, timedelta

class HRQueries:
    @staticmethod
    def get_presence_records(data_wpisu):
        """Get attendance/presence records for a given day."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz, "
                "o.wyjscie_od, o.wyjscie_do FROM obecnosc o "
                "JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s",
                (data_wpisu,)
            )
            result = cursor.fetchall()
        except Exception:
            cursor.execute(
                "SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz "
                "FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id "
                "WHERE o.data_wpisu = %s",
                (data_wpisu,)
            )
            rows = cursor.fetchall()
            result = [tuple(list(r) + [None, None]) for r in rows]
        
        conn.close()
        return result
    
    @staticmethod
    def get_presence_types(data_wpisu):
        """Get presence type entries for a given day."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pracownik_id, typ FROM obecnosc WHERE data_wpisu = %s",
            (data_wpisu,)
        )
        result = cursor.fetchall()
        conn.close()
        return result

    @staticmethod
    def get_presence_records_for_day(data_wpisu, linia='PSD', cursor=None):
        """Get all presence/absence records (obecnosc) for a day."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            
        try:
            cursor.execute(
                "SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz, o.wyjscie_od, o.wyjscie_do FROM obecnosc o "
                "JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s",
                (data_wpisu,)
            )
            result = cursor.fetchall()
        except Exception:
            try:
                cursor.execute(
                    "SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz FROM obecnosc o "
                    "JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s",
                    (data_wpisu,)
                )
                rows = cursor.fetchall()
                result = [tuple(list(r) + [None, None]) for r in rows]
            except Exception:
                result = []
        
        if conn:
            conn.close()
        return result
    
    @staticmethod
    def get_absence_ids_for_day(data_wpisu, cursor=None):
        """Get all workers with absence/presence records on a day."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            
        cursor.execute(
            "SELECT pracownik_id, typ FROM obecnosc WHERE data_wpisu = %s",
            (data_wpisu,)
        )
        result = cursor.fetchall()
        
        if conn:
            conn.close()
        return result

    @staticmethod
    def get_pending_leave_requests(limit=50):
        """Get pending leave/time-off requests."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, w.czas_od, "
            "w.czas_do, w.powod, w.zlozono FROM wnioski_wolne w "
            "JOIN pracownicy p ON w.pracownik_id = p.id "
            "WHERE w.status = 'pending' ORDER BY w.zlozono DESC LIMIT %s",
            (limit,)
        )
        raw = cursor.fetchall()
        conn.close()
        
        wnioski = []
        for r in raw:
            wnioski.append({
                'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data_od': r[3],
                'data_do': r[4], 'czas_od': r[5], 'czas_do': r[6],
                'powod': r[7], 'zlozono': r[8]
            })
        return wnioski

    @staticmethod
    def get_planned_leaves(days=60, limit=500, cursor=None):
        """Get planned/scheduled leaves for the next N days."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            
        end_date = date.today() + timedelta(days=days)
        cursor.execute(
            "SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, w.czas_od, w.czas_do, w.status "
            "FROM wnioski_wolne w JOIN pracownicy p ON w.pracownik_id = p.id "
            "WHERE w.data_od <= %s AND w.data_do >= %s "
            "ORDER BY w.data_od ASC LIMIT %s",
            (end_date, date.today(), limit)
        )
        raw = cursor.fetchall()
        result = []
        for r in raw:
            result.append({
                'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data_od': r[3],
                'data_do': r[4], 'czas_od': r[5], 'czas_do': r[6], 'status': r[7]
            })
            
        if conn:
            conn.close()
        return result
    
    @staticmethod
    def get_recent_absences(days=30, limit=500, cursor=None):
        """Get recent absence records (excludes regular attendance)."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            
        since = date.today() - timedelta(days=days)
        until = date.today() + timedelta(days=30)
        cursor.execute(
            "SELECT o.id, p.imie_nazwisko, o.typ, o.data_wpisu, o.ilosc_godzin, o.komentarz "
            "FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id "
            "WHERE o.data_wpisu BETWEEN %s AND %s AND LOWER(TRIM(COALESCE(o.typ,''))) NOT LIKE 'obec%' "
            "ORDER BY o.data_wpisu DESC LIMIT %s",
            (since, until, limit)
        )
        raw = cursor.fetchall()
        result = []
        for r in raw:
            result.append({
                'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data_wpisu': r[3],
                'ilosc_godzin': r[4], 'komentarz': r[5]
            })
            
        if conn:
            conn.close()
        return result
