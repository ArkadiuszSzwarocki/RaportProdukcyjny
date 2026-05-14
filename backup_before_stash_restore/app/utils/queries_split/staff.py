"""
Wersja: 1.1.0
Opis: Zapytania SQL dla kadr i obsady zmian.
"""
from app.db import get_db_connection
from datetime import date

class StaffQueries:
    @staticmethod
    def get_pracownicy(cursor=None):
        """Fetch all employees ordered by name."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM pracownicy ORDER BY imie_nazwisko")
        result = cursor.fetchall()
        
        if conn:
            conn.close()
        return result
    
    @staticmethod
    def get_obsada_zmiany(data_wpisu, sekcja=None, linia='PSD', cursor=None):
        """Get assigned staff (obsada) for a given day."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
        
        if sekcja:
            cursor.execute(
                "SELECT o.id, p.imie_nazwisko FROM obsada_zmiany o "
                "JOIN pracownicy p ON o.pracownik_id = p.id "
                "WHERE o.data_wpisu = %s AND o.sekcja = %s AND o.linia = %s",
                (data_wpisu, sekcja, linia)
            )
        else:
            cursor.execute(
                "SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s AND linia = %s",
                (data_wpisu, linia)
            )
        result = cursor.fetchall()
        
        if conn:
            conn.close()
        return result

    @staticmethod
    def get_obsada_for_date(data_wpisu, linia='PSD'):
        """Get staff assignment (obsada) for a specific date/line, grouped by sekcja."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT oz.sekcja, p.id, p.imie_nazwisko FROM obsada_zmiany oz "
            "JOIN pracownicy p ON oz.pracownik_id = p.id "
            "WHERE oz.data_wpisu = %s AND oz.linia = %s ORDER BY oz.sekcja, p.imie_nazwisko",
            (data_wpisu, linia)
        )
        rows = cursor.fetchall()
        obsady_map = {}
        for r in rows:
            sekc, pid, name = r[0], r[1], r[2]
            obsady_map.setdefault(sekc, []).append((pid, name))
        conn.close()
        return obsady_map
    
    @staticmethod
    def get_unassigned_pracownicy(data_wpisu, linia='PSD'):
        """Get workers not assigned to any sekcja on a specific date/line."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, imie_nazwisko FROM pracownicy "
            "WHERE id NOT IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu=%s AND linia=%s) "
            "AND id NOT IN (SELECT pracownik_id FROM uzytkownicy WHERE rola IN ('admin','zarzad') AND pracownik_id IS NOT NULL) "
            "ORDER BY imie_nazwisko",
            (data_wpisu, linia)
        )
        result = cursor.fetchall()
        conn.close()
        return result
