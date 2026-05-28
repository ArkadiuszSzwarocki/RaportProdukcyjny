
from app.db import get_db_connection, get_table_name
from datetime import datetime
import json

class InwentaryzacjaService:
    ID_PREFIX_MAP = {
        'surowiec': 'SUR',
        'opakowanie': 'OPK',
        'dodatek': 'DOD',
        'wyrób gotowy': 'PAL',
        'wyrob gotowy': 'PAL',
    }

    @staticmethod
    def _build_display_id(typ_palety, item_id, nr_palety=None):
        if nr_palety:
            return nr_palety

        pallet_type = str(typ_palety or '').strip().lower()
        prefix = InwentaryzacjaService.ID_PREFIX_MAP.get(pallet_type)
        if not prefix:
            # Fallback keeps legacy behavior only for unknown types.
            prefix = (pallet_type[:3].upper() if pallet_type else 'ID')

        return f"{prefix}-{item_id}"

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
    def get_active_sessions():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_inwentaryzacja_sesje WHERE status = 'OPEN' ORDER BY created_at DESC"
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def start_session(linia, user_login, comment='', lokalizacja='Wszystko'):
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
            
            # Fetch all entries in this session for this rack
            counted_map = {} # Key: f"{typ_palety}_{paleta_id}" -> row
            new_items_list = [] # List of new items (paleta_id is None)
            
            # Prepare LIKE patterns for robust matching
            clean_prefix = rack_prefix.strip().upper()
            base_prefix = clean_prefix
            if base_prefix.startswith('R-'): base_prefix = base_prefix[2:]
            elif base_prefix.startswith('R'): base_prefix = base_prefix[1:]
            
            p1 = f"{base_prefix}%"
            p2 = f"R{base_prefix}%"
            p3 = f"R-{base_prefix}%"
            like_clause = "(UPPER(TRIM(lokalizacja)) LIKE %s OR UPPER(TRIM(lokalizacja)) LIKE %s OR UPPER(TRIM(lokalizacja)) LIKE %s)"
            params = (p1, p2, p3)

            if sesja_id:
                cursor.execute(
                    f"SELECT id, paleta_id, nr_palety, typ_palety, nazwa, nr_partii, waga_systemowa, waga_faktyczna, lokalizacja, data_produkcji, data_przydatnosci, typ_opakowania, linia, jednostka FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s AND {like_clause}",
                    (sesja_id, *params)
                )
                for row in cursor.fetchall():
                    if row['paleta_id']:
                        counted_map[f"{row['typ_palety']}_{row['paleta_id']}"] = row
                    else:
                        new_items_list.append(row)

            hall_contexts = ['PSD', 'AGRO']
            
            def normalize_loc_key(loc_str):
                l = str(loc_str).strip().upper()
                if l.startswith('R-'): return 'R' + l[2:]
                if not l.startswith('R') and l and l[0].isdigit(): return 'R' + l
                return l

            # Helper to add items to map
            def add_to_map(rows):
                for r in rows:
                    raw_loc = r['lokalizacja']
                    loc = normalize_loc_key(raw_loc)
                    r['lokalizacja'] = loc # update it so frontend gets consistent value
                    if loc not in all_items: all_items[loc] = []
                    r['displayId'] = InwentaryzacjaService._build_display_id(
                        r.get('typ_palety'),
                        r.get('id'),
                        r.get('nr_palety')
                    )
                    
                    # Check if counted
                    key = f"{r['typ_palety']}_{r['id']}"
                    if key in counted_map:
                        r['counted'] = True
                        r['waga_faktyczna'] = counted_map[key]['waga_faktyczna']
                        r['jednostka'] = counted_map[key]['jednostka'] or 'kg'
                    else:
                        r['counted'] = False
                        r['waga_faktyczna'] = None
                        r['jednostka'] = r.get('jednostka') or 'kg'
                    
                    all_items[loc].append(r)

            # LIKE patterns were already defined above in this function.

            # 1. Surowce
            cursor.execute(
                f"SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'surowiec' as typ_palety, linia, jednostka FROM magazyn_surowce WHERE {like_clause} AND stan_magazynowy > 0", 
                params
            )
            add_to_map(cursor.fetchall())
            
            # 2. Opakowania
            cursor.execute(
                f"SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'opakowanie' as typ_palety, linia, 'szt' as jednostka FROM magazyn_opakowania WHERE {like_clause} AND stan_magazynowy > 0", 
                params
            )
            add_to_map(cursor.fetchall())

            # 2.5 Dodatki
            cursor.execute(
                f"SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'dodatek' as typ_palety, linia, 'kg' as jednostka FROM magazyn_dodatki WHERE {like_clause} AND stan_magazynowy > 0", 
                params
            )
            add_to_map(cursor.fetchall())

            # 3. Wyroby Gotowe
            for hall in hall_contexts:
                table = get_table_name('magazyn_palety', hall)
                cursor.execute(
                    f"SELECT id, nr_palety, produkt as nazwa, nr_partii, waga_netto as stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'wyrób gotowy' as typ_palety, linia, 'kg' as jednostka FROM {table} WHERE {like_clause} AND waga_netto > 0", 
                    params
                )
                add_to_map(cursor.fetchall())
            
            # 4. Add newly created items (paleta_id is None)
            for new_p in new_items_list:
                if new_p['nazwa'] != 'PUSTE GNIAZDO' and (new_p['waga_faktyczna'] is not None and new_p['waga_faktyczna'] <= 0):
                    continue
                loc = new_p['lokalizacja']
                if loc not in all_items: all_items[loc] = []
                
                # Build synthetic pallet object
                synthetic = {
                    "id": None,
                    "nr_palety": new_p['nr_palety'],
                    "nazwa": new_p['nazwa'],
                    "nr_partii": new_p['nr_partii'],
                    "stan_magazynowy": 0,
                    "lokalizacja": loc,
                    "data_produkcji": new_p['data_produkcji'].strftime('%Y-%m-%d') if hasattr(new_p['data_produkcji'], 'strftime') else new_p['data_produkcji'],
                    "data_przydatnosci": new_p['data_przydatnosci'].strftime('%Y-%m-%d') if hasattr(new_p['data_przydatnosci'], 'strftime') else new_p['data_przydatnosci'],
                    "typ_palety": new_p['typ_palety'],
                    "linia": new_p['linia'],
                    "displayId": new_p['nr_palety'] if new_p['nr_palety'] else f"NEW-{new_p['id']}",
                    "counted": True,
                    "waga_faktyczna": new_p['waga_faktyczna'],
                    "jednostka": new_p['jednostka'] or 'kg'
                }
                all_items[loc].append(synthetic)
            
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
            
            # Fetch all counted entries for this location
            counted_map = {} # Key: f"{typ_palety}_{paleta_id}" -> row
            new_items_list = [] # List of new items
            
            # Prepare IN variants for robust matching
            clean_loc = lokalizacja.strip().upper()
            base_loc = clean_loc
            if base_loc.startswith('R-'): base_loc = base_loc[2:]
            elif base_loc.startswith('R'): base_loc = base_loc[1:]
            
            loc_variants = (base_loc, f"R{base_loc}", f"R-{base_loc}")
            in_clause = "UPPER(TRIM(lokalizacja)) IN (%s, %s, %s)"

            if sesja_id:
                cursor.execute(
                    f"SELECT id, paleta_id, nr_palety, typ_palety, nazwa, nr_partii, waga_systemowa, waga_faktyczna, data_produkcji, data_przydatnosci, typ_opakowania, linia, jednostka FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s AND {in_clause}", 
                    (sesja_id, *loc_variants)
                )
                for row in cursor.fetchall():
                    if row['paleta_id']:
                        counted_map[f"{row['typ_palety']}_{row['paleta_id']}"] = row
                    else:
                        new_items_list.append(row)

            hall_contexts = ['PSD', 'AGRO']
            
            # Helper to process pallets
            def process_pallet(p):
                p['displayId'] = InwentaryzacjaService._build_display_id(
                    p.get('typ_palety'),
                    p.get('id'),
                    p.get('nr_palety')
                )
                key = f"{p['typ_palety']}_{p['id']}"
                if key in counted_map:
                    p['counted'] = True
                    p['waga_faktyczna'] = counted_map[key]['waga_faktyczna']
                    p['jednostka'] = counted_map[key]['jednostka'] or 'kg'
                else:
                    p['counted'] = False
                    p['waga_faktyczna'] = None
                    p['jednostka'] = p.get('jednostka') or 'kg'
                return p

            # IN variants were already defined above in this function.

            # 1. Surowce
            table_sur = 'magazyn_surowce'
            cursor.execute(
                f"SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, 'surowiec' as typ_palety, linia, jednostka FROM {table_sur} WHERE {in_clause} AND stan_magazynowy > 0", 
                loc_variants
            )
            for p in cursor.fetchall():
                all_pallets.append(process_pallet(p))
            
            # 2. Opakowania
            table_opk = 'magazyn_opakowania'
            cursor.execute(
                f"SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, 'opakowanie' as typ_palety, linia, 'szt' as jednostka FROM {table_opk} WHERE {in_clause} AND stan_magazynowy > 0", 
                loc_variants
            )
            for p in cursor.fetchall():
                all_pallets.append(process_pallet(p))

            # 2.5 Dodatki
            cursor.execute(
                f"SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, 'dodatek' as typ_palety, linia, 'kg' as jednostka FROM magazyn_dodatki WHERE {in_clause} AND stan_magazynowy > 0", 
                loc_variants
            )
            for p in cursor.fetchall():
                all_pallets.append(process_pallet(p))

            # 3. Wyroby Gotowe
            for hall in hall_contexts:
                table = get_table_name('magazyn_palety', hall)
                cursor.execute(
                    f"SELECT id, nr_palety, produkt as nazwa, nr_partii, waga_netto as stan_magazynowy, data_produkcji, data_przydatnosci, 'wyrób gotowy' as typ_palety, linia, 'kg' as jednostka FROM {table} WHERE {in_clause} AND waga_netto > 0", 
                    loc_variants
                )
                for p in cursor.fetchall():
                    if not p.get('linia'): p['linia'] = hall
                    all_pallets.append(process_pallet(p))
            
            # 4. Append new pallets
            for new_p in new_items_list:
                if new_p['nazwa'] != 'PUSTE GNIAZDO' and (new_p['waga_faktyczna'] is not None and new_p['waga_faktyczna'] <= 0):
                    continue
                synthetic = {
                    "id": None,
                    "nr_palety": new_p['nr_palety'],
                    "nazwa": new_p['nazwa'],
                    "nr_partii": new_p['nr_partii'],
                    "stan_magazynowy": 0,
                    "data_produkcji": new_p['data_produkcji'].strftime('%Y-%m-%d') if hasattr(new_p['data_produkcji'], 'strftime') else new_p['data_produkcji'],
                    "data_przydatnosci": new_p['data_przydatnosci'].strftime('%Y-%m-%d') if hasattr(new_p['data_przydatnosci'], 'strftime') else new_p['data_przydatnosci'],
                    "typ_palety": new_p['typ_palety'],
                    "linia": new_p['linia'],
                    "displayId": new_p['nr_palety'] if new_p['nr_palety'] else f"NEW-{new_p['id']}",
                    "counted": True,
                    "waga_faktyczna": new_p['waga_faktyczna'],
                    "jednostka": new_p['jednostka'] or 'kg'
                }
                all_pallets.append(synthetic)
                
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
    def add_entry(sesja_id, paleta_id, typ_palety, nazwa, lokalizacja, nr_partii, waga_systemowa, waga_faktyczna, user_login, linia='PSD', nr_palety=None, data_produkcji=None, data_przydatnosci=None, typ_opakowania='brak', jednostka='kg'):

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            d_prod = InwentaryzacjaService._clean_date(data_produkcji)
            d_przyd = InwentaryzacjaService._clean_date(data_przydatnosci)

            # Check if entry already exists for this item in this session
            existing = None
            if paleta_id is not None:
                # 1. Systemic pallet: match strictly by paleta_id and typ_palety and linia
                cursor.execute(
                    "SELECT id FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s AND paleta_id = %s AND typ_palety = %s AND linia = %s",
                    (sesja_id, paleta_id, typ_palety, linia)
                )
                existing = cursor.fetchone()
            else:
                # 2. Manual/synthetic pallet (paleta_id is NULL)
                # If nr_palety is provided, we match by nr_palety and lokalizacja
                if nr_palety:
                    cursor.execute(
                        "SELECT id FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s AND paleta_id IS NULL AND nr_palety = %s AND lokalizacja = %s AND typ_palety = %s AND linia = %s",
                        (sesja_id, nr_palety, lokalizacja, typ_palety, linia)
                    )
                    existing = cursor.fetchone()
                
                # If still not found or nr_palety is empty, check by nazwa and lokalizacja
                if not existing:
                    cursor.execute(
                        "SELECT id FROM magazyn_inwentaryzacja_wpisy WHERE sesja_id = %s AND paleta_id IS NULL AND (nr_palety IS NULL OR nr_palety = '') AND nazwa = %s AND lokalizacja = %s AND typ_palety = %s AND linia = %s",
                        (sesja_id, nazwa, lokalizacja, typ_palety, linia)
                    )
                    existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    "UPDATE magazyn_inwentaryzacja_wpisy SET waga_faktyczna = %s, lokalizacja = %s, data_produkcji = %s, data_przydatnosci = %s, typ_opakowania = %s, data_wpisu = NOW(), user_login = %s, jednostka = %s WHERE id = %s",
                    (waga_faktyczna, lokalizacja, d_prod, d_przyd, typ_opakowania, user_login, jednostka, existing[0])
                )
            else:
                cursor.execute(
                    "INSERT INTO magazyn_inwentaryzacja_wpisy (sesja_id, paleta_id, nr_palety, typ_palety, nazwa, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, waga_systemowa, waga_faktyczna, typ_opakowania, user_login, linia, jednostka) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (sesja_id, paleta_id, nr_palety, typ_palety, nazwa, lokalizacja, nr_partii, d_prod, d_przyd, waga_systemowa, waga_faktyczna, typ_opakowania, user_login, linia, jednostka)
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
    def revert_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE magazyn_inwentaryzacja_sesje SET status = 'OPEN', closed_at = NULL WHERE id = %s",
                (sesja_id,)
            )
            conn.commit()
            return True, "Zatwierdzenie zostało wycofane. Sesja jest ponownie otwarta."
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
                                INSERT INTO {table} (nr_palety, produkt, waga_netto, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, user_login) 
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (e['nr_palety'], e['nazwa'], e['waga_faktyczna'], e['lokalizacja'], e['nr_partii'], d_prod, d_przyd, e['typ_opakowania'], user_login))
                            
                        # Update the inventory entry with the newly created pallet ID
                        new_pallet_id = cursor.lastrowid
                        cursor.execute("UPDATE magazyn_inwentaryzacja_wpisy SET paleta_id = %s WHERE id = %s", (new_pallet_id, e['id']))
                        e['paleta_id'] = new_pallet_id
                
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
    def get_all_product_names(typ=None):
        """Get unique product names from relevant tables for autocomplete."""
        conn = get_db_connection()
        names = set()
        try:
            cursor = conn.cursor()
            if typ == 'surowiec' or not typ:
                cursor.execute("SELECT DISTINCT nazwa FROM magazyn_surowce WHERE nazwa IS NOT NULL AND nazwa != ''")
                for r in cursor.fetchall(): names.add(r[0])
            if typ == 'opakowanie' or not typ:
                cursor.execute("SELECT DISTINCT nazwa FROM magazyn_opakowania WHERE nazwa IS NOT NULL AND nazwa != ''")
                for r in cursor.fetchall(): names.add(r[0])
            if typ == 'wyrób gotowy' or not typ:
                # Fetch from PSD and AGRO
                for hall in ['PSD', 'AGRO']:
                    table = get_table_name('magazyn_palety', hall)
                    cursor.execute(f"SELECT DISTINCT produkt FROM {table} WHERE produkt IS NOT NULL AND produkt != ''")
                    for r in cursor.fetchall(): names.add(r[0])
            if typ == 'dodatek' or not typ:
                cursor.execute("SELECT DISTINCT nazwa FROM magazyn_dodatki WHERE nazwa IS NOT NULL AND nazwa != ''")
                for r in cursor.fetchall(): names.add(r[0])
                
            return sorted(list(names))
        except Exception as e:
            print(f"Error fetching product names: {e}")
            return []
        finally:
            conn.close()
