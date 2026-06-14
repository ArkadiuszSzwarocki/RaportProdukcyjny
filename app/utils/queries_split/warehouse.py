"""
Wersja: 1.1.0
Opis: Zapytania SQL dla magazynu i palet.
"""
from app.db import get_db_connection, get_table_name
from datetime import date

class WarehouseQueries:
    @staticmethod
    def get_paletki_for_plan(plan_id, linia='PSD', cursor=None):
        """Get all paletki (pallets) for a specific production plan."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            
        table_palety = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, "
            f"p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
            f"FROM {table_palety} pw JOIN {table_plan} p ON pw.plan_id = p.id "
            f"WHERE pw.plan_id = %s ORDER BY pw.data_dodania ASC",
            (plan_id,)
        )
        result = cursor.fetchall()
        
        if conn:
            conn.close()
        return result
    
    @staticmethod
    def get_paletki_magazyn(data_planu, linia='PSD', cursor=None):
        """Get all confirmed paletki in Magazyn (Warehouse) for a given day/line."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
        
        table_magazyn = get_table_name('magazyn_palety', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        table_palety = get_table_name('palety_workowanie', linia)
        
        cursor.execute(
            f"SELECT m.id, m.plan_id, m.waga_netto AS waga, m.tara, m.waga_brutto, "
            "COALESCE(pw.data_dodania, m.data_potwierdzenia) AS data_dodania, "
            "m.produkt, COALESCE(p.typ_produkcji, '') AS typ_produkcji, 'przyjeta' AS status, NULL AS czas_potwierdzenia_s, "
            "COALESCE(m.data_potwierdzenia, pw.data_dodania, m.created_at), m.user_login, m.nr_palety, m.nr_plomby "
            f"FROM {table_magazyn} m LEFT JOIN {table_plan} p ON m.plan_id = p.id "
            f"LEFT JOIN {table_palety} pw ON m.paleta_workowanie_id = pw.id "
            f"WHERE DATE(COALESCE(m.data_potwierdzenia, pw.data_dodania, m.created_at)) = %s AND m.waga_netto > 0 "
            "UNION ALL "
            "SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, COALESCE(pw.data_potwierdzenia, pw.data_dodania) AS data_dodania, "
            "p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s, "
            "CASE WHEN pw.data_potwierdzenia IS NOT NULL AND pw.data_potwierdzenia >= pw.data_dodania THEN pw.data_potwierdzenia "
            "WHEN pw.czas_rzeczywistego_potwierdzenia IS NOT NULL THEN CAST(CONCAT(DATE(pw.data_dodania), ' ', pw.czas_rzeczywistego_potwierdzenia) AS DATETIME) "
            "ELSE pw.data_dodania END, NULL AS user_login, pw.nr_palety, pw.nr_plomby "
            f"FROM {table_palety} pw JOIN {table_plan} p ON pw.plan_id = p.id "
            "WHERE (pw.data_potwierdzenia IS NOT NULL OR COALESCE(pw.status,'') IN ('przyjeta', 'w_magazynie')) AND pw.waga > 0 "
            f"AND NOT EXISTS (SELECT 1 FROM {table_magazyn} mp WHERE mp.paleta_workowanie_id = pw.id) "
            "AND DATE(COALESCE(pw.data_potwierdzenia, pw.data_dodania)) = %s "
            "ORDER BY 6 DESC, 1 DESC",
            (data_planu, data_planu)
        )
        result = cursor.fetchall()
        
        if conn:
            conn.close()
        return result
    
    @staticmethod
    def get_unconfirmed_paletki(data_planu, linia='PSD', cursor=None):
        """Get paletki that haven't been confirmed yet."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            
        table_palety = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT pw.id, pw.plan_id, p.produkt, pw.data_dodania, "
            f"(SELECT COUNT(1) FROM {table_palety} pw2 WHERE pw2.plan_id = pw.plan_id AND pw2.id <= pw.id) as seq "
            f", pw.nr_palety "
            f"FROM {table_palety} pw JOIN {table_plan} p ON pw.plan_id = p.id "
            "WHERE DATE(pw.data_dodania) = %s AND p.sekcja IN ('Workowanie', 'Czyszczenie') "
            "AND pw.waga > 0 AND COALESCE(pw.status,'') NOT IN ('przyjeta', 'zamknieta', 'w_magazynie')",
            (data_planu,)
        )
        result = cursor.fetchall()
        
        if conn:
            conn.close()
        return result
    
    @staticmethod
    def get_paletki_for_produkt_magazyn(data_planu, produkt, linia='PSD'):
        """Get paletki for a specific product in Magazyn (Warehouse) view."""
        conn = get_db_connection()
        cursor = conn.cursor()
        table_palety = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, "
            f"p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
            f"FROM {table_palety} pw JOIN {table_plan} p ON pw.plan_id = p.id "
            f"WHERE DATE(p.data_planu) = %s AND p.produkt = %s AND p.sekcja IN ('Workowanie', 'Czyszczenie') "
            "ORDER BY pw.id DESC",
            (data_planu, produkt)
        )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_waga_workowania(data_planu, produkt, typ_produkcji, linia='PSD'):
        """Get total weight executed in Workowanie for a product."""
        conn = get_db_connection()
        cursor = conn.cursor()
        table_plan = get_table_name('plan_produkcji', linia)
        typ_param = typ_produkcji if typ_produkcji else ''
        cursor.execute(
            f"SELECT SUM(tonaz_rzeczywisty) FROM {table_plan} "
            "WHERE data_planu=%s AND produkt=%s AND sekcja IN ('Workowanie', 'Czyszczenie') "
            "AND COALESCE(typ_produkcji,'')=%s",
            (data_planu, produkt, typ_param)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 0

    @staticmethod
    def get_paleta_seq_number(plan_id, paleta_id, linia='PSD'):
        """Get sequence number (1-based) of a paleta within its plan."""
        conn = get_db_connection()
        cursor = conn.cursor()
        table_palety = get_table_name('palety_workowanie', linia)
        cursor.execute(
            f"SELECT COUNT(1) FROM {table_palety} WHERE plan_id = %s AND id <= %s",
            (plan_id, paleta_id)
        )
        result = cursor.fetchone()
        conn.close()
        return int(result[0]) if result and result[0] is not None else 1
    
    @staticmethod
    def get_paletki_for_product(data_planu, produkt, typ_produkcji=None, linia='PSD'):
        """Get paletki for a specific product (Magazyn view)."""
        conn = get_db_connection()
        cursor = conn.cursor()
        table_palety = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
            f"FROM {table_palety} pw JOIN {table_plan} p ON pw.plan_id = p.id "
            f"WHERE DATE(p.data_planu) = %s AND p.produkt = %s AND p.sekcja IN ('Workowanie', 'Czyszczenie') ORDER BY pw.id DESC",
            (data_planu, produkt)
        )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_workowanie_sum_for_product(data_planu, produkt, typ_produkcji=None, linia='PSD'):
        """Get total weight from Workowanie for a product (used by Zasyp view)."""
        conn = get_db_connection()
        cursor = conn.cursor()
        table_plan = get_table_name('plan_produkcji', linia)
        typ_param = typ_produkcji if typ_produkcji is not None else ''
        cursor.execute(
            f"SELECT SUM(tonaz_rzeczywisty) FROM {table_plan} "
            "WHERE data_planu=%s AND produkt=%s AND sekcja IN ('Workowanie', 'Czyszczenie') AND COALESCE(typ_produkcji,'')=%s",
            (data_planu, produkt, typ_param)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 0
