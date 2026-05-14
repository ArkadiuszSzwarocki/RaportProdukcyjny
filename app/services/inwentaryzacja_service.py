
from app.db import get_db_connection, get_table_name
from datetime import datetime
import json

class InwentaryzacjaService:
    @staticmethod
    def get_active_session(linia=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_inwentaryzacja_sesje WHERE status = 'OPEN' LIMIT 1"
            )
            return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def start_session(linia, user_login, comment='', lokalizacja='Wszystko'):
        active = InwentaryzacjaService.get_active_session()
        if active:
            return False, "Istnieje już otwarta sesja inwentaryzacji."
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO magazyn_inwentaryzacja_sesje (linia, created_by, comment, lokalizacja) VALUES (%s, %s, %s, %s)",
                ('GLOBAL', user_login, comment, lokalizacja)
            )
            conn.commit()
            return True, cursor.lastrowid

        finally:
            conn.close()

    @staticmethod
    def get_rack_data(rack_prefix, sesja_id=None):
        """Fetch all items for all locations starting with rack_prefix (e.g. 'R01')."""
        conn = get_db_connection()
        all_items = {} # Map location -> [items]
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Get counted items in this session
            counted_ids = set()
            if sesja_id:
                cursor.execute("SELECT paleta_id, typ_palety, lokalizacja FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s", (sesja_id,))
                for row in cursor.fetchall():
                    # For new pallets (id=None), we might use nr_palety or location as key, but for existing ones:
                    if row['paleta_id']:
                        counted_ids.add(f"{row['typ_palety']}_{row['paleta_id']}")
                    else:
                        # Mark location as having at least one counted item
                        counted_ids.add(f"loc_{row['lokalizacja']}")

            hall_contexts = ['PSD', 'AGRO']
            
            # Helper to add items to map
            def add_to_map(rows):
                for r in rows:
                    loc = r['lokalizacja']
                    if loc not in all_items: all_items[loc] = []
                    r['displayId'] = r['nr_palety'] if r.get('nr_palety') else f"{r['typ_palety'][:3].upper()}-{r['id']}"
                    
                    # Mark if counted
                    r['counted'] = f"{r['typ_palety']}_{r['id']}" in counted_ids or f"loc_{loc}" in counted_ids
                    
                    all_items[loc].append(r)


            # 1. Surowce
            cursor.execute(
                "SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'surowiec' as typ_palety, linia FROM magazyn_surowce WHERE lokalizacja LIKE %s AND stan_magazynowy > 0", 
                (f"{rack_prefix}%",)
            )
            add_to_map(cursor.fetchall())
            
            # 2. Opakowania
            cursor.execute(
                "SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'opakowanie' as typ_palety, linia FROM magazyn_opakowania WHERE lokalizacja LIKE %s AND stan_magazynowy > 0", 
                (f"{rack_prefix}%",)
            )
            add_to_map(cursor.fetchall())

            # 3. Wyroby Gotowe
            for hall in hall_contexts:
                table = get_table_name('magazyn_palety', hall)
                cursor.execute(
                    f"SELECT id, nr_palety, produkt as nazwa, nr_partii, waga_netto as stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'wyrób gotowy' as typ_palety, linia FROM {table} WHERE lokalizacja LIKE %s AND waga_netto > 0", 
                    (f"{rack_prefix}%",)
                )
                add_to_map(cursor.fetchall())
            
            return all_items
        except Exception as e:
            print(f"Error in get_rack_data: {e}")
            return {}
        finally:
            conn.close()

    @staticmethod
    def get_pallets_at_location(lokalizacja, sesja_id=None):
        conn = get_db_connection()
        all_pallets = []
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Get counted items in this session
            counted_ids = set()
            if sesja_id:
                cursor.execute("SELECT paleta_id, typ_palety FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s AND lokalizacja = %s", (sesja_id, lokalizacja))
                for row in cursor.fetchall():
                    if row['paleta_id']:
                        counted_ids.add(f"{row['typ_palety']}_{row['paleta_id']}")

            hall_contexts = ['PSD', 'AGRO']

            
            # 1. Surowce (UNIFIED)
            # Since surowce are unified into one table, we only query once
            table_sur = 'magazyn_surowce'
            cursor.execute(
                f"SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, 'surowiec' as typ_palety, linia FROM {table_sur} WHERE lokalizacja = %s AND stan_magazynowy > 0", 
                (lokalizacja,)
            )
            for p in cursor.fetchall():
                p['displayId'] = p['nr_palety'] if p['nr_palety'] else f"SUR-{p['id']}"
                p['counted'] = f"surowiec_{p['id']}" in counted_ids
                all_pallets.append(p)

            
            # 2. Opakowania (UNIFIED)
            table_opk = 'magazyn_opakowania'
            cursor.execute(
                f"SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, 'opakowanie' as typ_palety, linia FROM {table_opk} WHERE lokalizacja = %s AND stan_magazynowy > 0", 
                (lokalizacja,)
            )
            for p in cursor.fetchall():
                p['displayId'] = p['nr_palety'] if p['nr_palety'] else f"OPK-{p['id']}"
                p['counted'] = f"opakowanie_{p['id']}" in counted_ids
                all_pallets.append(p)


            # 3. Wyroby Gotowe (STILL SEPARATE)
            for hall in hall_contexts:
                table = get_table_name('magazyn_palety', hall)
                cursor.execute(
                    f"SELECT id, nr_palety, produkt as nazwa, nr_partii, waga_netto as stan_magazynowy, data_produkcji, data_przydatnosci, 'wyrób gotowy' as typ_palety, linia FROM {table} WHERE lokalizacja = %s AND waga_netto > 0", 
                    (lokalizacja,)
                )
                for p in cursor.fetchall():
                    p['displayId'] = p['nr_palety'] if p['nr_palety'] else f"PAL-{p['id']}"
                    if not p.get('linia'): p['linia'] = hall
                    p['counted'] = f"wyrób gotowy_{p['id']}" in counted_ids
                    all_pallets.append(p)

            
            return all_pallets
        except Exception as e:
            print(f"Error in get_pallets_at_location: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def _clean_date(date_val):
        """Helper to clean various date formats (JS strings, etc) to YYYY-MM-DD."""
        if not date_val or str(date_val).strip() == '' or str(date_val).lower() in ['none', 'null', 'undefined']:
            return None
        s_val = str(date_val).strip()
        try:
            # Handle JS format like "Tue, 28 Apr 2026 00:00:00 GMT"
            if 'GMT' in s_val:
                # We need to remove the weekday and GMT to parse easily or use a more flexible parser
                # Simple approach: use parts
                parts = s_val.split(' ')
                # Tue, 28 Apr 2026 00:00:00 GMT -> ["Tue,", "28", "Apr", "2026", "00:00:00", "GMT"]
                if len(parts) >= 4:
                    day = parts[1]
                    month_name = parts[2]
                    year = parts[3]
                    # Map month names
                    months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
                    month = months.get(month_name, '01')
                    return f"{year}-{month}-{day.zfill(2)}"
            
            # Handle ISO format "2026-04-28T00:00:00.000Z"
            if 'T' in s_val:
                return s_val.split('T')[0]
                
            # If it's already YYYY-MM-DD or similar
            if '-' in s_val:
                parts = s_val.split('-')
                if len(parts) == 3:
                    # ensure it's YYYY-MM-DD
                    if len(parts[0]) == 4: return s_val[:10]
                    if len(parts[2]) == 4: return f"{parts[2]}-{parts[1]}-{parts[0]}" # DD-MM-YYYY
            
            return s_val[:10]
        except Exception:
            return None

    @staticmethod
    def add_entry(sesja_id, paleta_id, typ_palety, nazwa, lokalizacja, nr_partii, waga_systemowa, waga_faktyczna, user_login, linia='PSD', nr_palety=None, data_produkcji=None, data_przydatnosci=None, typ_opakowania='brak'):

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            d_prod = InwentaryzacjaService._clean_date(data_produkcji)
            d_przyd = InwentaryzacjaService._clean_date(data_przydatnosci)

            # Check if entry already exists for this pallet in this session
            cursor.execute(
                "SELECT id FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s AND paleta_id = %s AND typ_palety = %s AND linia = %s AND (nr_palety IS NULL OR nr_palety = %s)",
                (sesja_id, paleta_id, typ_palety, linia, nr_palety)
            )
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute(
                    "UPDATE magazyn_inwentaryzacja_wpisy SET waga_faktyczna = %s, data_produkcji = %s, data_przydatnosci = %s, typ_opakowania = %s, data_wpisu = NOW(), user_login = %s WHERE id = %s",
                    (waga_faktyczna, d_prod, d_przyd, typ_opakowania, user_login, existing[0])
                )
            else:
                cursor.execute(
                    "INSERT INTO magazyn_inwentaryzacja_wpisy (sesja_id, paleta_id, nr_palety, typ_palety, nazwa, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, waga_systemowa, waga_faktyczna, typ_opakowania, user_login, linia) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (sesja_id, paleta_id, nr_palety, typ_palety, nazwa, lokalizacja, nr_partii, d_prod, d_przyd, waga_systemowa, waga_faktyczna, typ_opakowania, user_login, linia)
                )

            conn.commit()
            return True, "Wpis zapisany"
        finally:
            conn.close()

    @staticmethod
    def get_report(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s", (sesja_id,))
            entries = cursor.fetchall()
            
            # Compare and calculate diff
            for e in entries:
                e['roznica'] = e['waga_faktyczna'] - e['waga_systemowa']
                e['alert'] = abs(e['roznica']) > 0.1 # Some threshold
            
            return entries
        finally:
            conn.close()

    @staticmethod
    def close_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE magazyn_inwentaryzacja_sesje SET status = 'CLOSED', closed_at = NOW() WHERE id = %s",
                (sesja_id,)
            )
            conn.commit()
            return True, "Sesja zamknięta"
        finally:
            conn.close()

    @staticmethod
    def resume_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE magazyn_inwentaryzacja_sesje SET status = 'OPEN', closed_at = NULL WHERE id = %s",
                (sesja_id,)
            )
            conn.commit()
            return True, "Sesja została wznowiona"
        finally:
            conn.close()

    @staticmethod
    def delete_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s", (sesja_id,))
            cursor.execute("DELETE FROM magazyn_inwentaryzacja_sesje WHERE id = %s", (sesja_id,))
            conn.commit()
            return True, "Sesja została usunięta"
        except Exception as e:
            if conn: conn.rollback()
            print(f"Error deleting session {sesja_id}: {e}")
            return False, f"Błąd bazy danych: {str(e)}"
        finally:
            conn.close()


    @staticmethod
    def update_session(sesja_id, lokalizacja, comment):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE magazyn_inwentaryzacja_sesje SET lokalizacja = %s, comment = %s WHERE id = %s",
                (lokalizacja, comment, sesja_id)
            )
            conn.commit()
            return True, "Dane sesji zostały zaktualizowane"
        finally:
            conn.close()

    @staticmethod
    def apply_inventory(sesja_id, user_login):


        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # 1. Get entries
            cursor.execute("SELECT * FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s", (sesja_id,))
            entries = cursor.fetchall()
            
            for e in entries:
                linia_e = e.get('linia', 'PSD')
                table_sur = get_table_name('magazyn_surowce', linia_e)
                table_opk = get_table_name('magazyn_opakowania', linia_e)
                table_pal = get_table_name('magazyn_palety', linia_e)
                
                if e['typ_palety'] == 'surowiec':
                    table = table_sur
                    col_amount = 'stan_magazynowy'
                    col_name = 'nazwa'
                elif e['typ_palety'] == 'opakowanie':
                    table = table_opk
                    col_amount = 'stan_magazynowy'
                    col_name = 'nazwa'
                else: # wyrób gotowy
                    table = table_pal
                    col_amount = 'waga_netto'
                    col_name = 'produkt'

                if e['paleta_id']:
                    # UPDATE EXISTING
                    if e['waga_faktyczna'] <= 0:
                        # ARCHIVING
                        cursor.execute("""
                            INSERT INTO magazyn_archiwum (original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, waga_ostatnia, lokalizacja_ostatnia, user_login, komentarz)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (e['paleta_id'], e['nr_palety'], e['nazwa'], e['typ_palety'], linia_e, e['nr_partii'], e['waga_systemowa'], e['lokalizacja'], user_login, "Zaktualizowano do 0 podczas inwentaryzacji"))
                        
                        cursor.execute(f"DELETE FROM {table} WHERE id = %s", (e['paleta_id'],))
                    else:
                        # Update stock and metadata
                        cursor.execute(f"""
                            UPDATE {table} 
                            SET {col_amount} = %s, lokalizacja = %s, nr_partii = %s, typ_opakowania = %s, 
                                data_produkcji = %s, data_przydatnosci = %s 
                            WHERE id = %s
                        """, (e['waga_faktyczna'], e['lokalizacja'], e['nr_partii'], e['typ_opakowania'], 
                              InwentaryzacjaService._clean_date(e['data_produkcji']), 
                              InwentaryzacjaService._clean_date(e['data_przydatnosci']), 
                              e['paleta_id']))
                else:
                    # INSERT NEW PALLET
                    if e['waga_faktyczna'] > 0:
                        d_prod = InwentaryzacjaService._clean_date(e['data_produkcji'])
                        d_przyd = InwentaryzacjaService._clean_date(e['data_przydatnosci'])
                        
                        if e['typ_palety'] in ['surowiec', 'opakowanie']:
                            cursor.execute(f"""
                                INSERT INTO {table} (nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, typ_opakowania) 
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, (e['nr_palety'], e['nazwa'], e['waga_faktyczna'], e['lokalizacja'], e['nr_partii'], d_prod, d_przyd, e['typ_opakowania']))
                        else: # Wyrób gotowy
                            cursor.execute(f"""
                                INSERT INTO {table} (produkt, waga_netto, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, user_login) 
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, (e['nazwa'], e['waga_faktyczna'], e['lokalizacja'], e['nr_partii'], d_prod, d_przyd, e['typ_opakowania'], user_login))
                
                # Log in history for both new and updated
                p_id = e['paleta_id'] or cursor.lastrowid
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'INWENTARYZACJA_KOREKTA', %s, %s, %s)",
                    (p_id, linia_e, e['typ_palety'], e['lokalizacja'], f"Korekta inwentaryzacyjna: {e['waga_systemowa']} -> {e['waga_faktyczna']}", user_login)
                )

            
            # 2. Mark session as APPLIED
            cursor.execute("UPDATE magazyn_inwentaryzacja_sesje SET status = 'APPLIED', closed_at = NOW() WHERE id = %s", (sesja_id,))
            conn.commit()
            return True, "Zmiany zostały wprowadzone do magazynu"
        except Exception as e:
            print(f"Error applying inventory: {e}")
            if conn: conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def get_all_product_names():
        """Get unique product names from all relevant tables for autocomplete."""
        conn = get_db_connection()
        names = set()
        try:
            cursor = conn.cursor()
            # Surowce
            cursor.execute("SELECT DISTINCT nazwa FROM magazyn_surowce WHERE nazwa IS NOT NULL AND nazwa != ''")
            for r in cursor.fetchall(): names.add(r[0])
            # Opakowania
            cursor.execute("SELECT DISTINCT nazwa FROM magazyn_opakowania WHERE nazwa IS NOT NULL AND nazwa != ''")
            for r in cursor.fetchall(): names.add(r[0])
            
            return sorted(list(names))
        except Exception as e:
            print(f"Error fetching product names: {e}")
            return []
        finally:
            conn.close()
