"""
Wersja: 1.1.0
Opis: Zapytania SQL dla produkcji i dziennika zmiany.
"""
from app.db import get_db_connection, get_table_name
from datetime import date

class ProductionQueries:
    @staticmethod
    def get_dziennik_zmiany(data_wpisu, sekcja, linia='PSD'):
        """Get shift log entries (non-finished status only) for a given day/section/line."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT d.id, p.imie_nazwisko, d.problem, d.czas_start, d.czas_stop, d.kategoria, "
            "TIMESTAMPDIFF(MINUTE, d.czas_start, d.czas_stop), d.pracownik_id, d.sekcja, d.data_zakonczenia "
            "FROM dziennik_zmiany d LEFT JOIN pracownicy p ON d.pracownik_id = p.id "
            "WHERE d.data_wpisu = %s AND d.sekcja = %s AND d.linia = %s AND d.status != 'zakończone' "
            "ORDER BY d.id DESC",
            (data_wpisu, sekcja, linia)
        )
        rows = cursor.fetchall()
        result = [list(r) for r in rows]

        try:
            if sekcja.lower() == 'workowanie' and result:
                for p in result:
                    try:
                        prod = p[1]
                        table_plan = get_table_name('plan_produkcji', linia)
                        cursor.execute(
                            f"SELECT COALESCE(tonaz_rzeczywisty, 0) FROM {table_plan} "
                            "WHERE DATE(data_planu) = %s AND sekcja = 'Zasyp' AND produkt = %s "
                            "ORDER BY COALESCE(real_stop, real_start, id) ASC LIMIT 1",
                            (data_wpisu, prod)
                        )
                        zasyp_row = cursor.fetchone()
                        if zasyp_row and zasyp_row[0] is not None:
                            p[2] = zasyp_row[0]

                        table_bufor = get_table_name('bufor', linia)
                        cursor.execute(
                            f"SELECT COALESCE(MAX(spakowano), 0) FROM {table_bufor} WHERE data_planu = %s AND produkt = %s AND status = 'aktywny'",
                            (data_wpisu, prod)
                        )
                        buf_row = cursor.fetchone()
                        if buf_row and buf_row[0] is not None:
                            while len(p) <= 7:
                                p.append(None)
                            p[7] = buf_row[0]
                    except Exception:
                        continue
        except Exception:
            pass

        conn.close()
        return result
    
    @staticmethod
    def get_plan_produkcji(data_planu, sekcja, linia='PSD', cursor=None):
        """Get production plans for a given day/section/line."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
        
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT id, produkt, tonaz, status, real_start, real_stop, "
            "TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, kolejnosc, "
            "typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0), COALESCE(nazwa_zlecenia, ''), "
            "data_planu, zasyp_id "
            f"FROM {table_plan} "
            "WHERE DATE(data_planu) = %s AND LOWER(sekcja) = LOWER(%s) AND status != 'nieoplacone' AND is_deleted = 0 "
            "ORDER BY CASE status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 ELSE 3 END, "
            "kolejnosc ASC, id ASC",
            (data_planu, sekcja)
        )
        
        rows = cursor.fetchall()
        result = [list(r) for r in rows]
        
        if conn:
            conn.close()
        return result

    @staticmethod
    def get_zasyp_started_produkty(data_planu, linia='PSD', cursor=None):
        """Get list of products started (w toku/zakonczone) in Zasyp section."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT DISTINCT produkt FROM {table_plan} "
            "WHERE sekcja='Zasyp' AND status IN ('w toku', 'zakonczone') "
            "AND DATE(data_planu) = %s",
            (data_planu,)
        )
        result = [r[0] for r in cursor.fetchall()]
        
        if conn:
            conn.close()
        return result

    @staticmethod
    def get_plan_typ_zlecenia(plan_id, linia='PSD'):
        """Get typ_zlecenia and sekcja for a specific plan."""
        conn = get_db_connection()
        cursor = conn.cursor()
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT COALESCE(typ_zlecenia, ''), sekcja FROM {table_plan} WHERE id=%s",
            (plan_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result if result else ('', '')

    @staticmethod
    def get_quality_orders_count(linia='PSD'):
        """Get count of unfinished quality orders for a given line."""
        conn = get_db_connection()
        cursor = conn.cursor()
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT COUNT(1) FROM {table_plan} "
            "WHERE (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') "
            "AND status != 'zakonczone'"
        )
        result = cursor.fetchone()
        conn.close()
        return int(result[0] or 0) if result else 0

    @staticmethod
    def get_pending_quality_count(linia='PSD', cursor=None):
        """Get count of pending quality orders (jakosc)."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT COUNT(1) FROM {table_plan} "
            "WHERE (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') AND status != 'zakonczone'"
        )
        result = cursor.fetchone()
        
        if conn:
            conn.close()
        return int(result[0] or 0) if result else 0
