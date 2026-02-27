"""
Database query helpers - centralized SQL queries to DRY the codebase.
All queries use parameterized statements with %s placeholders.
"""
from app.db import get_db_connection
from datetime import date, datetime, timedelta


class QueryHelper:
    """Centralized database queries for the application."""
    
    @staticmethod
    def get_pracownicy():
        """Fetch all employees ordered by name."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pracownicy ORDER BY imie_nazwisko")
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_obsada_zmiany(data_wpisu, sekcja=None):
        """Get assigned staff (obsada) for a given day.
        
        Args:
            data_wpisu: date object
            sekcja: Optional section filter
            
        Returns:
            List of (id, pracownik_id, imie_nazwisko) tuples
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if sekcja:
            cursor.execute(
                "SELECT o.id, p.imie_nazwisko FROM obsada_zmiany o "
                "JOIN pracownicy p ON o.pracownik_id = p.id "
                "WHERE o.data_wpisu = %s AND o.sekcja = %s",
                (data_wpisu, sekcja)
            )
        else:
            cursor.execute(
                "SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s",
                (data_wpisu,)
            )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_dziennik_zmiany(data_wpisu, sekcja):
        """Get shift log entries (non-finished status only) for a given day/section."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT d.id, p.imie_nazwisko, d.problem, d.czas_start, d.czas_stop, d.kategoria, "
            "TIMESTAMPDIFF(MINUTE, d.czas_start, d.czas_stop), d.pracownik_id, d.sekcja, d.data_zakonczenia "
            "FROM dziennik_zmiany d LEFT JOIN pracownicy p ON d.pracownik_id = p.id "
            "WHERE d.data_wpisu = %s AND d.sekcja = %s AND d.status != 'zakończone' "
            "ORDER BY d.id DESC",
            (data_wpisu, sekcja)
        )
        rows = cursor.fetchall()
        result = [list(r) for r in rows]

        # For Workowanie: override plan value (p[2]) with corresponding Zasyp.tonaz_rzeczywisty
        # and override realisation (p[7]) with current bufor.spakowano for the product/date.
        try:
            if sekcja.lower() == 'workowanie' and result:
                for p in result:
                    try:
                        prod = p[1]
                        # Get tonaz_rzeczywisty from the first matching Zasyp for that product/date
                        cursor.execute(
                            "SELECT COALESCE(tonaz_rzeczywisty, 0) FROM plan_produkcji "
                            "WHERE DATE(data_planu) = %s AND sekcja = 'Zasyp' AND produkt = %s "
                            "ORDER BY COALESCE(real_stop, real_start, id) ASC LIMIT 1",
                            (data_wpisu, prod)
                        )
                        zasyp_row = cursor.fetchone()
                        if zasyp_row and zasyp_row[0] is not None:
                            p[2] = zasyp_row[0]

                        # Get spakowano value from bufor (take MAX to avoid double-counting duplicates)
                        cursor.execute(
                            "SELECT COALESCE(MAX(spakowano), 0) FROM bufor WHERE data_planu = %s AND produkt = %s AND status = 'aktywny'",
                            (data_wpisu, prod)
                        )
                        buf_row = cursor.fetchone()
                        if buf_row and buf_row[0] is not None:
                            # Ensure list has p[7] position
                            while len(p) <= 7:
                                p.append(None)
                            p[7] = buf_row[0]
                    except Exception:
                        # ignore per-plan errors
                        continue
        except Exception:
            pass

        conn.close()
        return result
    
    @staticmethod
    def get_plan_produkcji(data_planu, sekcja):
        """Get production plans (excludes 'nieoplacone' and deleted) for a given day/section.
        
        Returns list of tuples: (id, produkt, tonaz, status, real_start, real_stop, 
                                 minutes_diff, tonaz_rzeczywisty, kolejnosc, typ_produkcji, 
                                 wyjasnienie_rozbieznosci, uszkodzone_worki, nazwa_zlecenia)
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # For all sections: show all plans (no special filtering)
        # Plan (p[2]) = tonaz (plan value)
        # Realizacja (p[7]) = tonaz_rzeczywisty (actual realized)
        # p[11] = uszkodzone_worki (damaged bags)
        # p[12] = nazwa_zlecenia (order name - to identify BUF orders)
        cursor.execute(
            "SELECT id, produkt, tonaz, status, real_start, real_stop, "
            "TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, kolejnosc, "
            "typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0), COALESCE(nazwa_zlecenia, '') "
            "FROM plan_produkcji "
            "WHERE DATE(data_planu) = %s AND LOWER(sekcja) = LOWER(%s) AND status != 'nieoplacone' AND is_deleted = 0 "
            "ORDER BY CASE status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 ELSE 3 END, "
            "kolejnosc ASC, id ASC",
            (data_planu, sekcja)
        )
        
        result = [list(r) for r in cursor.fetchall()]
        conn.close()
        return result
    
    @staticmethod
    def get_paletki_for_plan(plan_id):
        """Get all paletki (pallets) for a specific production plan."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, "
            "p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
            "FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id "
            "WHERE pw.plan_id = %s ORDER BY pw.data_dodania ASC",
            (plan_id,)
        )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_paletki_magazyn(data_planu):
        """Get all confirmed paletki in Magazyn (Warehouse) for a given day."""
        conn = get_db_connection()
        cursor = conn.cursor()
        # Prefer magazyn_palety records (separate table) for Magazyn UI. Fall back
        # to palety_workowanie rows with status='przyjeta' for backwards compatibility.
        cursor.execute(
            "SELECT m.id, m.plan_id, m.waga_netto AS waga, m.tara, m.waga_brutto, "
            "pw.data_dodania AS data_dodania, "
            "m.produkt, COALESCE(p.typ_produkcji, '') AS typ_produkcji, 'przyjeta' AS status, NULL AS czas_potwierdzenia_s, "
            "GREATEST(m.data_potwierdzenia, pw.data_dodania) "
            "FROM magazyn_palety m LEFT JOIN plan_produkcji p ON m.plan_id = p.id "
            "LEFT JOIN palety_workowanie pw ON m.paleta_workowanie_id = pw.id "
            "WHERE DATE(GREATEST(m.data_potwierdzenia, pw.data_dodania)) = %s AND m.waga_netto > 0 "
            "UNION ALL "
            "SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, COALESCE(pw.data_potwierdzenia, pw.data_dodania) AS data_dodania, "
            "p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s, "
            "CASE WHEN pw.data_potwierdzenia IS NOT NULL AND pw.data_potwierdzenia >= pw.data_dodania THEN pw.data_potwierdzenia "
            "WHEN pw.czas_rzeczywistego_potwierdzenia IS NOT NULL THEN CAST(CONCAT(DATE(pw.data_dodania), ' ', pw.czas_rzeczywistego_potwierdzenia) AS DATETIME) "
            "ELSE pw.data_dodania END "
            "FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id "
            "WHERE (pw.data_potwierdzenia IS NOT NULL OR COALESCE(pw.status,'') = 'przyjeta') AND pw.waga > 0 "
            "AND NOT EXISTS (SELECT 1 FROM magazyn_palety mp WHERE mp.paleta_workowanie_id = pw.id) "
            "AND DATE(COALESCE(pw.data_potwierdzenia, pw.data_dodania)) = %s "
            "ORDER BY 6 DESC, 1 DESC",
            (data_planu, data_planu)
        )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_unconfirmed_paletki(data_planu):
        """Get paletki that haven't been confirmed yet (status != 'przyjeta', 'zamknieta')."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pw.id, pw.plan_id, p.produkt, pw.data_dodania "
            "FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id "
            "WHERE DATE(pw.data_dodania) = %s AND p.sekcja = 'Workowanie' "
            "AND pw.waga > 0 AND COALESCE(pw.status,'') NOT IN ('przyjeta', 'zamknieta')",
            (data_planu,)
        )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_paletki_for_produkt_magazyn(data_planu, produkt):
        """Get paletki for a specific product in Magazyn (Warehouse) view."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, "
            "p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
            "FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id "
            "WHERE DATE(p.data_planu) = %s AND p.produkt = %s AND p.sekcja = 'Workowanie' "
            "ORDER BY pw.id DESC",
            (data_planu, produkt)
        )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_waga_workowania(data_planu, produkt, typ_produkcji):
        """Get total weight executed in Workowanie for a product."""
        conn = get_db_connection()
        cursor = conn.cursor()
        typ_param = typ_produkcji if typ_produkcji else ''
        cursor.execute(
            "SELECT SUM(tonaz_rzeczywisty) FROM plan_produkcji "
            "WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' "
            "AND COALESCE(typ_produkcji,'')=%s",
            (data_planu, produkt, typ_param)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 0
    
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
            # Fallback for legacy databases without wyjscie_od/wyjscie_do columns
            cursor.execute(
                "SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz "
                "FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id "
                "WHERE o.data_wpisu = %s",
                (data_wpisu,)
            )
            rows = cursor.fetchall()
            # Add None for wyjscie_od/wyjscie_do columns
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
    def get_quality_orders_count():
        """Get count of unfinished quality orders."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(1) FROM plan_produkcji "
            "WHERE (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') "
            "AND status != 'zakonczone'"
        )
        result = cursor.fetchone()
        conn.close()
        return int(result[0] or 0) if result else 0
    
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
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_planned_leaves(data_od=None, data_do=None, limit=500):
        """Get planned leave requests within a date range."""
        if data_od is None:
            data_od = date.today()
        if data_do is None:
            data_do = date.today() + timedelta(days=60)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, w.czas_od, "
            "w.czas_do, w.status FROM wnioski_wolne w "
            "JOIN pracownicy p ON w.pracownik_id = p.id "
            "WHERE w.data_od <= %s AND w.data_do >= %s "
            "ORDER BY w.data_od ASC LIMIT %s",
            (data_do, data_od, limit)
        )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_recent_absences(days=30, limit=500):
        """Get recent absence/non-attendance records (last N days)."""
        since = date.today() - timedelta(days=days)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT o.id, p.imie_nazwisko, o.typ, o.data_wpisu, o.ilosc_godzin, o.komentarz "
            "FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id "
            "WHERE o.data_wpisu BETWEEN %s AND %s "
            "AND LOWER(TRIM(COALESCE(o.typ,''))) NOT LIKE 'obec%' "
            "ORDER BY o.data_wpisu DESC LIMIT %s",
            (since, date.today(), limit)
        )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_plan_typ_zlecenia(plan_id):
        """Get typ_zlecenia and sekcja for a specific plan."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(typ_zlecenia, ''), sekcja FROM plan_produkcji WHERE id=%s",
            (plan_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result if result else ('', '')
    
    @staticmethod
    def get_zasyp_started_produkty(data_planu):
        """Get list of products started (w toku/zakonczone) in Zasyp section."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT produkt FROM plan_produkcji "
            "WHERE sekcja='Zasyp' AND status IN ('w toku', 'zakonczone') "
            "AND DATE(data_planu) = %s",
            (data_planu,)
        )
        result = [r[0] for r in cursor.fetchall()]
        conn.close()
        return result
    
    @staticmethod
    def get_paleta_seq_number(plan_id, paleta_id):
        """Get sequence number (1-based) of a paleta within its plan."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(1) FROM palety_workowanie WHERE plan_id = %s AND id <= %s",
            (plan_id, paleta_id)
        )
        result = cursor.fetchone()
        conn.close()
        return int(result[0]) if result and result[0] is not None else 1
    
    @staticmethod
    def get_paletki_for_product(data_planu, produkt, typ_produkcji=None):
        """Get paletki for a specific product (Magazyn view).
        
        Args:
            data_planu: date of plan
            produkt: product name
            typ_produkcji: optional type filter
            
        Returns:
            List of paleta rows
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
            "FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id "
            "WHERE DATE(p.data_planu) = %s AND p.produkt = %s AND p.sekcja = 'Workowanie' ORDER BY pw.id DESC",
            (data_planu, produkt)
        )
        result = cursor.fetchall()
        conn.close()
        return result
    
    @staticmethod
    def get_workowanie_sum_for_product(data_planu, produkt, typ_produkcji=None):
        """Get total weight from Workowanie for a product (used by Zasyp view).
        
        Args:
            data_planu: date of plan
            produkt: product name
            typ_produkcji: optional type filter
            
        Returns:
            Float: total tonaz_rzeczywisty
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        # typ_produkcji may be NULL in DB; use COALESCE to match empty/NULL values correctly
        typ_param = typ_produkcji if typ_produkcji is not None else ''
        cursor.execute(
            "SELECT SUM(tonaz_rzeczywisty) FROM plan_produkcji "
            "WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND COALESCE(typ_produkcji,'')=%s",
            (data_planu, produkt, typ_param)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 0
    
    @staticmethod
    def get_presence_records_for_day(data_wpisu):
        """Get all presence/absence records (obecnosc) for a day.
        
        Args:
            data_wpisu: date to query
            
        Returns:
            List of (id, imie_nazwisko, typ, ilosc_godzin, komentarz, None, None) tuples
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Try new schema with wyjscie_od/wyjscie_do
            cursor.execute(
                "SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz, o.wyjscie_od, o.wyjscie_do FROM obecnosc o "
                "JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s",
                (data_wpisu,)
            )
            result = cursor.fetchall()
        except Exception:
            # Fallback to legacy schema (no wyjscie_od/wyjscie_do columns)
            try:
                cursor.execute(
                    "SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz FROM obecnosc o "
                    "JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s",
                    (data_wpisu,)
                )
                rows = cursor.fetchall()
                # Append None, None for wyjscie_od/wyjscie_do to match new schema
                result = [tuple(list(r) + [None, None]) for r in rows]
            except Exception:
                result = []
        conn.close()
        return result
    
    @staticmethod
    def get_absence_ids_for_day(data_wpisu):
        """Get all workers with absence/presence records on a day.
        
        Args:
            data_wpisu: date to query
            
        Returns:
            List of (pracownik_id, typ) tuples
        """
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
    def get_pending_quality_count():
        """Get count of pending quality orders (jakosc).
        
        Returns:
            Int: count of non-completed quality orders
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(1) FROM plan_produkcji "
            "WHERE (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') AND status != 'zakonczone'"
        )
        result = cursor.fetchone()
        conn.close()
        return int(result[0] or 0) if result else 0
    
    @staticmethod
    def get_planned_leaves(days_ahead=60, limit=500):
        """Get planned/scheduled leaves for the next N days.
        
        Args:
            days_ahead: number of days into the future to check
            limit: maximum number of records to return
            
        Returns:
            List of dicts with leave details
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        end_date = date.today() + timedelta(days=days_ahead)
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
                'id': r[0], 
                'pracownik': r[1], 
                'typ': r[2], 
                'data_od': r[3], 
                'data_do': r[4], 
                'czas_od': r[5], 
                'czas_do': r[6], 
                'status': r[7]
            })
        conn.close()
        return result
    
    @staticmethod
    def get_recent_absences(days_back=30, limit=500):
        """Get recent absence records (excludes regular attendance).
        
        Args:
            days_back: number of days back to check
            limit: maximum number of records to return
            
        Returns:
            List of dicts with absence details
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        since = date.today() - timedelta(days=days_back)
        cursor.execute(
            "SELECT o.id, p.imie_nazwisko, o.typ, o.data_wpisu, o.ilosc_godzin, o.komentarz "
            "FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id "
            "WHERE o.data_wpisu BETWEEN %s AND %s AND LOWER(TRIM(COALESCE(o.typ,''))) NOT LIKE 'obec%' "
            "ORDER BY o.data_wpisu DESC LIMIT %s",
            (since, date.today(), limit)
        )
        raw = cursor.fetchall()
        result = []
        for r in raw:
            result.append({
                'id': r[0], 
                'pracownik': r[1], 
                'typ': r[2], 
                'data_wpisu': r[3], 
                'ilosc_godzin': r[4], 
                'komentarz': r[5]
            })
        conn.close()
        return result
    
    @staticmethod
    def get_obsada_for_date(data_wpisu):
        """Get staff assignment (obsada) for a specific date, grouped by sekcja.
        
        Args:
            data_wpisu: date to query
            
        Returns:
            Dict mapping sekcja -> list of (pracownik_id, imie_nazwisko) tuples
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT oz.sekcja, p.id, p.imie_nazwisko FROM obsada_zmiany oz "
            "JOIN pracownicy p ON oz.pracownik_id = p.id "
            "WHERE oz.data_wpisu = %s ORDER BY oz.sekcja, p.imie_nazwisko",
            (data_wpisu,)
        )
        rows = cursor.fetchall()
        obsady_map = {}
        for r in rows:
            sekc, pid, name = r[0], r[1], r[2]
            obsady_map.setdefault(sekc, []).append((pid, name))
        conn.close()
        return obsady_map
    
    @staticmethod
    def get_unassigned_pracownicy(data_wpisu):
        """Get workers not assigned to any sekcja on a specific date.
        
        Args:
            data_wpisu: date to query
            
        Returns:
            List of (id, imie_nazwisko) tuples
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, imie_nazwisko FROM pracownicy "
            "WHERE id NOT IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu=%s) "
            "ORDER BY imie_nazwisko",
            (data_wpisu,)
        )
        result = cursor.fetchall()
        conn.close()
        return result



