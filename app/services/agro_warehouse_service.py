from app.db import get_db_connection, get_table_name
from datetime import datetime

class AgroWarehouseService:
    @staticmethod
    def get_inventory(linia='Agro'):
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # Show individual pallets/spots for warehouse precision
            cursor.execute(f"SELECT * FROM {table_surowce} WHERE stan_magazynowy > 0 ORDER BY nazwa, id")
            res = cursor.fetchall()
            return res
        finally:
            conn.close()

    @staticmethod
    def get_packaging_inventory(linia='Agro'):
        """Return packaging inventory rows from magazyn_opakowania."""
        table_opak = get_table_name('magazyn_opakowania', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM {table_opak} ORDER BY nazwa, id")
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def create_packaging(nazwa, ilosc, lokalizacja=None, linia='Agro'):
        table_opak = get_table_name('magazyn_opakowania', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"INSERT INTO {table_opak} (nazwa, stan_magazynowy, lokalizacja) VALUES (%s, %s, %s)", (nazwa, ilosc, lokalizacja))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def edit_packaging(record_id, nazwa=None, ilosc=None, lokalizacja=None, linia='Agro'):
        table_opak = get_table_name('magazyn_opakowania', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            updates = []
            params = []
            if nazwa is not None:
                updates.append('nazwa = %s')
                params.append(nazwa)
            if ilosc is not None:
                updates.append('stan_magazynowy = %s')
                params.append(ilosc)
            if lokalizacja is not None:
                updates.append('lokalizacja = %s')
                params.append(lokalizacja)
            if not updates:
                return True
            params.append(record_id)
            q = f"UPDATE {table_opak} SET " + ', '.join(updates) + " WHERE id = %s"
            cursor.execute(q, tuple(params))
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def delete_packaging(record_id, linia='Agro'):
        table_opak = get_table_name('magazyn_opakowania', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {table_opak} WHERE id = %s", (record_id,))
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def adjust_packaging_inventory(record_id, actual_qty, worker_login=None, linia='Agro'):
        table_opak = get_table_name('magazyn_opakowania', linia)
        # We will reuse magazyn_ruch for audit if available
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT stan_magazynowy FROM {table_opak} WHERE id = %s", (record_id,))
            row = cursor.fetchone()
            if not row:
                return False
            old_qty = row[0]
            delta = actual_qty - old_qty
            cursor.execute(f"UPDATE {table_opak} SET stan_magazynowy = %s WHERE id = %s", (actual_qty, record_id))
            try:
                cursor.execute(
                    f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) VALUES (%s, 'INWENTARYZACJA', %s, %s, 'POTWIERDZONE', %s, %s, %s)",
                    (record_id, delta, actual_qty, worker_login, datetime.now(), 'Inwentaryzacja opakowania')
                )
            except Exception:
                # If ruch table missing or insert fails, ignore audit
                pass
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def get_inventory_grouped(linia='Agro', pkg_form=None):
        """Return inventory grouped by material name.
        pkg_form: 'bags' or 'big_bag'
        """
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            where_clause = " WHERE stan_magazynowy > 0 "
            params = []
            if pkg_form:
                where_clause += " AND typ_opakowania = %s "
                params.append(pkg_form)
            
            # get distinct materials with total quantity
            cursor.execute(f"SELECT nazwa, SUM(stan_magazynowy) as total FROM {table_surowce} {where_clause} GROUP BY nazwa ORDER BY nazwa", tuple(params))
            groups = cursor.fetchall()
            result = []
            for g in groups:
                name = g['nazwa']
                total = float(g['total']) if g.get('total') is not None else 0.0
                # fetch individual pallets for this material
                q_p = f"SELECT id, nazwa, stan_magazynowy, lokalizacja, typ_opakowania FROM {table_surowce} {where_clause} AND nazwa = %s ORDER BY id ASC"
                cursor.execute(q_p, tuple(params + [name]))
                pallets = cursor.fetchall()
                # normalize pallet rows
                pallets_norm = []
                for p in pallets:
                    pallets_norm.append({
                        'id': p['id'],
                        'nazwa': p.get('nazwa'),
                        'stan_magazynowy': float(p.get('stan_magazynowy') or 0),
                        'lokalizacja': p.get('lokalizacja'),
                        'typ_opakowania': p.get('typ_opakowania')
                    })
                result.append({ 'nazwa': name, 'total': total, 'pallets': pallets_norm })
            return result
        finally:
            conn.close()

    @staticmethod
    def get_inventory_by_location(linia='Agro'):
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT id, nazwa, stan_magazynowy, lokalizacja FROM {table_surowce} WHERE stan_magazynowy > 0 ORDER BY lokalizacja ASC, id ASC")
            pallets = cursor.fetchall()
            
            grouped = {}
            for p in pallets:
                loc = p.get('lokalizacja') or 'Brak lokalizacji'
                if loc not in grouped:
                    grouped[loc] = []
                grouped[loc].append({
                    'id': p['id'],
                    'nazwa': p.get('nazwa'),
                    'stan_magazynowy': float(p.get('stan_magazynowy') or 0),
                    'lokalizacja': loc
                })
                
            result = []
            for loc in sorted(grouped.keys()):
                result.append({
                    'lokalizacja': loc,
                    'pallets': grouped[loc],
                    'total_kg': sum(p['stan_magazynowy'] for p in grouped[loc])
                })
            return result
        finally:
            conn.close()

    @staticmethod
    def get_dictionary():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT nazwa FROM magazyn_agro_slownik_surowce ORDER BY nazwa ASC")
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def add_delivery(nazwa, ilosc, author_login, linia='Agro', komentarz=None, nr_partii=None, data_produkcji=None, data_przydatnosci=None, pkg_form='bags'):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Check if surowiec exists in dictionary
            cursor.execute("INSERT IGNORE INTO magazyn_agro_slownik_surowce (nazwa) VALUES (%s)", (nazwa,))
            
            # 2. Add pending movement
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_nazwa, typ_ruchu, ilosc, status, autor_login, autor_data, komentarz, nr_partii, data_produkcji, data_przydatnosci, typ_opakowania) "
                "VALUES (%s, 'PRZYJECIE', %s, 'OCZEKUJACE', %s, %s, %s, %s, %s, %s, %s)",
                (nazwa, ilosc, author_login, datetime.now(), komentarz, nr_partii, data_produkcji, data_przydatnosci, pkg_form)
            )
            
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def edit_delivery(ruch_id, nazwa=None, ilosc=None, komentarz=None):
        table_ruch = get_table_name('magazyn_ruch', 'Agro')
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # only allow editing pending deliveries
            cursor.execute(f"SELECT typ_ruchu, status FROM {table_ruch} WHERE id = %s", (ruch_id,))
            row = cursor.fetchone()
            if not row or row[0] != 'PRZYJECIE' or row[1] != 'OCZEKUJACE':
                return False

            updates = []
            params = []
            if nazwa is not None:
                updates.append('surowiec_nazwa = %s')
                params.append(nazwa)
            if ilosc is not None:
                updates.append('ilosc = %s')
                params.append(ilosc)
            if komentarz is not None:
                updates.append('komentarz = %s')
                params.append(komentarz)

            if not updates:
                return True

            q = f"UPDATE {table_ruch} SET " + ', '.join(updates) + " WHERE id = %s"
            params.append(ruch_id)
            cursor.execute(q, tuple(params))
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def delete_delivery(ruch_id):
        table_ruch = get_table_name('magazyn_ruch', 'Agro')
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT typ_ruchu, status FROM {table_ruch} WHERE id = %s", (ruch_id,))
            row = cursor.fetchone()
            if not row or row[0] != 'PRZYJECIE' or row[1] != 'OCZEKUJACE':
                return False
            cursor.execute(f"DELETE FROM {table_ruch} WHERE id = %s", (ruch_id,))
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def confirm_delivery(ruch_id, worker_login, linia='Agro', lokalizacja=None, nr_partii=None, data_produkcji=None, data_przydatnosci=None):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT surowiec_nazwa, ilosc, status, nr_partii, data_produkcji, data_przydatnosci FROM {table_ruch} WHERE id = %s", (ruch_id,))
            row = cursor.fetchone()
            if not row or row[2] != 'OCZEKUJACE':
                return False
            
            name, qty = row[0], row[1]
            # Use provided values OR pre-filled values from movement record
            nr_partii = nr_partii or row[3]
            data_produkcji = data_produkcji or row[4]
            data_przydatnosci = data_przydatnosci or row[5]
            
            # PALLET TRACKING: We ALWAYS create a NEW row for each confirmed pallet
            # Each row is a unique (material, location) pair.
            
            # Check if spot is occupied
            if lokalizacja:
                cursor.execute(f"SELECT id FROM {table_surowce} WHERE lokalizacja = %s AND stan_magazynowy > 0", (lokalizacja,))
                if cursor.fetchone():
                    return False # Spot occupied
            
            # Create the stock record (the "pallet")
            cursor.execute(
                f"INSERT INTO {table_surowce} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci) VALUES (%s, %s, %s, %s, %s, %s)",
                (name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci)
            )
            surowiec_id = cursor.lastrowid
            
            # Update history
            cursor.execute(
                f"UPDATE {table_ruch} SET surowiec_id = %s, lokalizacja = %s, status = 'POTWIERDZONE', potwierdzil_login = %s, potwierdzil_data = %s WHERE id = %s",
                (surowiec_id, lokalizacja, worker_login, datetime.now(), ruch_id)
            )
            
            # Log to palety_historia
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, 'surowiec', 'PRZYJECIE', %s, %s, %s)",
                (surowiec_id, linia, lokalizacja, f"Przyjęcie surowca: {name}, partia: {nr_partii}", worker_login)
            )
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error in confirm_delivery: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    @staticmethod
    def use_for_production(surowiec_id, ilosc, worker_login, plan_id=None, linia='Agro', komentarz=None, zbiornik=None):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Update stock for THIS SPECIFIC PALLET/SPOT
            cursor.execute(f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy - %s WHERE id = %s", (ilosc, surowiec_id))
            
            # Get new level for audit
            cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            stan_po = cursor.fetchone()[0]
            
            # Add movement record
            plan_id_val = int(plan_id) if plan_id not in (None, '', 0, '0') else None
            zbiornik_val = zbiornik.strip() if zbiornik and str(zbiornik).strip() else None
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz, zbiornik) "
                "VALUES (%s, 'PRODUKCJA', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s, %s, %s)",
                (surowiec_id, -ilosc, stan_po, worker_login, datetime.now(), worker_login, datetime.now(), plan_id_val, komentarz, zbiornik_val)
            )

            # Log to palety_historia
            cursor.execute(f"SELECT nazwa, lokalizacja FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            s_row = cursor.fetchone()
            s_name = s_row[0] if s_row else 'surowiec'
            s_loc = s_row[1] if s_row else None
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, komentarz, user_login) VALUES (%s, %s, 'surowiec', 'WYDANIE_PROD', %s, %s, %s)",
                (surowiec_id, linia, s_loc, f"Pobranie na produkcję ({ilosc} kg): {s_name}. Zbiornik: {zbiornik_val or '—'}", worker_login)
            )
            
            conn.commit()
            return True
        finally:
            conn.close()



    @staticmethod
    def issue_external(surowiec_id, ilosc, worker_login, linia='Agro', komentarz=None):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT nazwa, lokalizacja FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            row = cursor.fetchone()
            nazwa = f"{row[0]} ({row[1]})" if row else 'Nieznany'

            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, status, autor_login, autor_data, komentarz) "
                "VALUES (%s, %s, 'WYDANIE_ZEW', %s, 'OCZEKUJACE', %s, %s, %s)",
                (surowiec_id, nazwa, ilosc, worker_login, datetime.now(), komentarz)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def confirm_external_issue(ruch_id, worker_login, linia='Agro'):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT surowiec_id, ilosc, status FROM {table_ruch} WHERE id = %s", (ruch_id,))
            row = cursor.fetchone()
            if not row or row[2] != 'OCZEKUJACE': return False
            
            s_id, qty = row[0], row[1]
            if not s_id:
                return False  # PRZYJECIE rows have no surowiec_id — use confirm_delivery instead
            cursor.execute(f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy - %s WHERE id = %s", (qty, s_id))
            cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (s_id,))
            result = cursor.fetchone()
            stan_po = result[0] if result else 0
            
            cursor.execute(
                f"UPDATE {table_ruch} SET status = 'POTWIERDZONE', potwierdzil_login = %s, potwierdzil_data = %s, ilosc_po = %s WHERE id = %s",
                (worker_login, datetime.now(), stan_po, ruch_id)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def get_occupied_locations(linia='Agro'):
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT lokalizacja FROM {table_surowce} WHERE lokalizacja IS NOT NULL AND stan_magazynowy > 0")
            return [r[0] for r in cursor.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def get_suggested_location(nazwa, linia='Agro'):
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            occupied = AgroWarehouseService.get_occupied_locations(linia)
            
            # Find the MOST RECENT location for THIS material
            cursor.execute(f"SELECT lokalizacja FROM {table_surowce} WHERE nazwa = %s AND lokalizacja IS NOT NULL ORDER BY id DESC LIMIT 1", (nazwa,))
            row = cursor.fetchone()
            last_loc = row[0] if row else None
            
            search_order = []
            if last_loc and len(last_loc) >= 7:
                try:
                    r, s, m = int(last_loc[1:3]), int(last_loc[3:5]), int(last_loc[5:7])
                    # Current row, next spots
                    for i in range(m + 1, 25): search_order.append(f"R{r:02d}{s:02d}{i:02d}")
                    # Next rows in same rack
                    for j in range(s + 1, 4):
                        for i in range(1, 25): search_order.append(f"R{r:02d}{j:02d}{i:02d}")
                    # Next racks
                    for k in range(r + 1, 4):
                        for j in range(1, 4):
                            for i in range(1, 25): search_order.append(f"R{k:02d}{j:02d}{i:02d}")
                except: pass

            # General fallback if search exhausted or no last_loc
            if not search_order:
                for k in range(1, 4):
                    for j in range(1, 4):
                        for i in range(1, 25):
                            loc = f"R{k:02d}{j:02d}{i:02d}"
                            if loc not in search_order: search_order.append(loc)

            for loc in search_order:
                if loc not in occupied: return loc
            return ""
        finally:
            conn.close()

    @staticmethod
    def rename_pallet(surowiec_id, new_name, worker_login, linia='Agro'):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # get current qty
            cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            row = cursor.fetchone()
            if not row:
                return False
            stan = row[0]

            # update name
            cursor.execute(f"UPDATE {table_surowce} SET nazwa = %s WHERE id = %s", (new_name, surowiec_id))

            # insert history record for audit
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz) "
                "VALUES (%s, 'KOREKTA', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s)",
                (surowiec_id, 0, stan, worker_login, datetime.now(), worker_login, datetime.now(), f'Zmiana nazwy na: {new_name}')
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def get_history(limit=100, status=None, linia='Agro', data=None, plan_id=None):
        """Return movement history with optional filters.

        Args:
            data: date string 'YYYY-MM-DD' — filter to that calendar day
            plan_id: int/str — filter to specific production order
        """
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # Join plan table to include plan name when plan_id is present
            try:
                table_plan = get_table_name('plan_produkcji', linia)
                plan_join = f" LEFT JOIN {table_plan} p ON r.plan_id = p.id "
                plan_select = ", p.produkt as plan_name"
            except Exception:
                plan_join = ""
                plan_select = ", NULL as plan_name"

            q = (
                f"SELECT r.*, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa{plan_select} "
                f"FROM {table_ruch} r LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id {plan_join} "
                "WHERE 1=1 "
            )
            params = []
            if status:
                q += " AND r.status = %s "
                params.append(status)
            if data:
                q += " AND DATE(r.autor_data) = %s "
                params.append(data)
            if plan_id:
                try:
                    params.append(int(plan_id))
                    q += " AND r.plan_id = %s "
                except (ValueError, TypeError):
                    pass
            q += " ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
            params.append(limit)
            cursor.execute(q, tuple(params))
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_production_moves(limit=100, linia='Agro'):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # include plan name via join if available
            try:
                table_plan = get_table_name('plan_produkcji', linia)
                plan_join = f" LEFT JOIN {table_plan} p ON r.plan_id = p.id "
                plan_select = ", p.produkt as plan_name"
            except Exception:
                plan_join = ""
                plan_select = ", NULL as plan_name"

            q = (
                f"SELECT r.*, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, s.lokalizacja as lokalizacja{plan_select} "
                f"FROM {table_ruch} r LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id {plan_join} "
                "WHERE r.typ_ruchu = 'PRODUKCJA' "
                "ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
            )
            cursor.execute(q, (limit,))
            return cursor.fetchall()
        finally:
            conn.close()



    @staticmethod
    def return_from_production(surowiec_id, ilosc, worker_login, plan_id=None, linia='Agro', komentarz=None, ruch_produkcja_id=None, lokalizacja=None):
        """Zwrot surowca z produkcji na magazyn — zwiększa stan palety.
        
        ruch_produkcja_id: opcjonalne ID ruchu PRODUKCJA, którego dotyczy zwrot.
        lokalizacja: docelowa lokalizacja (regał) — jeśli podana, aktualizuje lokalizację palety.
        """
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy + %s WHERE id = %s", (ilosc, surowiec_id))

            # Aktualizuj lokalizację palety jeśli podano
            if lokalizacja:
                cursor.execute(f"UPDATE {table_surowce} SET lokalizacja = %s WHERE id = %s", (lokalizacja, surowiec_id))

            cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            stan_po = cursor.fetchone()[0]

            plan_id_val = int(plan_id) if plan_id not in (None, '', 0, '0') else None
            ruch_ref = int(ruch_produkcja_id) if ruch_produkcja_id not in (None, '', 0, '0') else None
            lok_val = lokalizacja.strip() if lokalizacja and str(lokalizacja).strip() else None
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz, ruch_zrodlowy_id, lokalizacja) "
                "VALUES (%s, 'ZWROT', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s, %s, %s, %s)",
                (surowiec_id, ilosc, stan_po, worker_login, datetime.now(), worker_login, datetime.now(), plan_id_val, komentarz, ruch_ref, lok_val)
            )

            # Log to palety_historia
            cursor.execute(f"SELECT nazwa FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            s_row = cursor.fetchone()
            s_name = s_row[0] if s_row else 'surowiec'
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, 'surowiec', 'ZWROT', %s, %s, %s)",
                (surowiec_id, linia, lok_val, f"Zwrot z produkcji ({ilosc} kg): {s_name}", worker_login)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def get_production_items_for_return(linia='Agro', limit=200):
        """Zwraca listę ruchów PRODUKCJA z informacją ile jeszcze nie zwrócono.
        
        Każdy wiersz: ruch_id, surowiec_id, nazwa, lokalizacja, ilosc_pobrana, ilosc_zwrocona, do_zwrotu, plan_id, plan_name, data, zbiornik.
        """
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            try:
                table_plan = get_table_name('plan_produkcji', linia)
                plan_join = f" LEFT JOIN {table_plan} p ON r.plan_id = p.id "
                plan_select = ", p.produkt as plan_name"
            except Exception:
                plan_join = ""
                plan_select = ", NULL as plan_name"

            q = (
                f"SELECT r.id as ruch_id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as nazwa, "
                f"s.lokalizacja, ABS(r.ilosc) as ilosc_pobrana, "
                f"COALESCE((SELECT SUM(z.ilosc) FROM {table_ruch} z WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT'), 0) as ilosc_zwrocona, "
                f"r.plan_id, r.autor_login, r.autor_data, r.zbiornik{plan_select} "
                f"FROM {table_ruch} r LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id {plan_join} "
                "WHERE r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE' "
                "ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
            )
            cursor.execute(q, (limit,))
            rows = cursor.fetchall()
            result = []
            for r in rows:
                pobrana = float(r.get('ilosc_pobrana') or 0)
                zwrocona = float(r.get('ilosc_zwrocona') or 0)
                do_zwrotu = round(pobrana - zwrocona, 2)
                if do_zwrotu <= 0:
                    continue  # w pełni zwrócone
                result.append({
                    'ruch_id': r['ruch_id'],
                    'surowiec_id': r.get('surowiec_id'),
                    'nazwa': r.get('nazwa') or '',
                    'lokalizacja': r.get('lokalizacja') or '',
                    'ilosc_pobrana': pobrana,
                    'ilosc_zwrocona': zwrocona,
                    'do_zwrotu': do_zwrotu,
                    'plan_id': r.get('plan_id'),
                    'plan_name': r.get('plan_name') or '',
                    'autor_login': r.get('autor_login') or '',
                    'data': r['autor_data'].strftime('%d.%m.%Y %H:%M') if r.get('autor_data') else '',
                    'zbiornik': r.get('zbiornik') or '',
                })
            return result
        finally:
            conn.close()



    @staticmethod
    def get_current_running_plan(linia='Agro'):
        """Return current running production plan info for given line or None.

        Returns dict: {'id': <int>, 'produkt': <str>} or None.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            try:
                table_plan = get_table_name('plan_produkcji', linia)
            except Exception:
                table_plan = get_table_name('plan_produkcji', None)
            cursor.execute(f"SELECT id, produkt FROM {table_plan} WHERE status='w toku' ORDER BY real_start DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            return { 'id': int(row[0]), 'produkt': row[1] }
        finally:
            conn.close()

    @staticmethod
    def get_active_workowanie_plan(linia='Agro', target_date=None):
        """Helper to find specifically an active Workowanie plan."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', linia)
            
            query = f"SELECT id, produkt, data_planu, typ_produkcji, start_machine_counter, start_pallet_counter FROM {table_plan} WHERE status='w toku' AND sekcja='Workowanie'"
            params = []
            
            if target_date:
                query += " AND DATE(data_planu) = %s"
                params.append(target_date)
            else:
                query += " AND DATE(data_planu) = CURDATE()"
                
            query += " ORDER BY real_start DESC LIMIT 1"
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_finished_plans_of_day(linia='Agro', target_date=None):
        """Helper to find finished Workowanie plans for a specific day."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', linia)
            
            query = f"SELECT id, produkt, data_planu, typ_produkcji FROM {table_plan} WHERE status='zakonczone' AND sekcja='Workowanie'"
            params = []
            
            if target_date:
                query += " AND DATE(data_planu) = %s"
                params.append(target_date)
            else:
                query += " AND DATE(data_planu) = CURDATE()"
                
            query += " ORDER BY real_stop DESC"
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_linked_packaging(plan_id):
        """Get all packaging items linked to a production plan."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT ap.id as link_id, ap.opakowanie_id, ap.stan_poczatkowy, ap.stan_koncowy, ap.is_active,
                       o.nazwa, o.stan_magazynowy as current_stan
                FROM agro_plan_opakowania ap
                JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                WHERE ap.plan_id = %s AND ap.is_active = TRUE
                ORDER BY ap.created_at ASC
            """, (plan_id,))
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_all_linked_packaging(plan_id):
        """Get ALL packaging items linked to a production plan, active and inactive."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT ap.id as link_id, ap.opakowanie_id, ap.stan_poczatkowy, ap.stan_koncowy, ap.is_active,
                       o.nazwa, o.stan_magazynowy as current_stan
                FROM agro_plan_opakowania ap
                JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                WHERE ap.plan_id = %s
                ORDER BY ap.created_at ASC
            """, (plan_id,))
            return cursor.fetchall()
        finally:
            conn.close()


    @staticmethod
    def _link_to_active_plan(cursor, opakowanie_id, lokalizacja, linia='Agro'):
        """Internal helper to link packaging to active plan if moved to machine."""
        if str(lokalizacja).lower() != 'maszyna' or str(linia).upper() != 'AGRO':
            return
            
        # 1. Find active Workowanie plan
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(f"SELECT id FROM {table_plan} WHERE status='w toku' AND sekcja='Workowanie' ORDER BY real_start DESC LIMIT 1")
        plan_row = cursor.fetchone()
        if not plan_row:
            return
            
        plan_id = plan_row[0]
        
        # 2. Get current state of packaging
        cursor.execute("SELECT stan_magazynowy FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
        opak_row = cursor.fetchone()
        if not opak_row:
            return
        stan_poczatkowy = opak_row[0]
        
        # 3. Check if already linked and active for THIS plan
        cursor.execute("SELECT id FROM agro_plan_opakowania WHERE plan_id = %s AND opakowanie_id = %s AND is_active = TRUE", (plan_id, opakowanie_id))
        if cursor.fetchone():
            return # Already linked
            
        # 4. Link it
        cursor.execute(
            "INSERT INTO agro_plan_opakowania (plan_id, opakowanie_id, stan_poczatkowy, is_active) VALUES (%s, %s, %s, TRUE)",
            (plan_id, opakowanie_id, stan_poczatkowy)
        )

    @staticmethod
    def finalize_packaging_usage(plan_id, szt_na_palecie, packaging_results, user_login):
        """Processes final states for all packaging items used in a plan."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # 1. Fetch Plan Info
            table_plan = get_table_name('plan_produkcji', 'AGRO')
            cursor.execute(f"SELECT produkt, data_planu FROM {table_plan} WHERE id = %s", (plan_id,))
            plan_row = cursor.fetchone()
            if not plan_row:
                return False
                
            produkt = plan_row['produkt']
            data_planu = plan_row['data_planu']
            
            # 2. Get total pallets produced
            cursor.execute("SELECT COUNT(*) as cnt, SUM(waga) as total_kg FROM palety_agro WHERE plan_id = %s", (plan_id,))
            prod_row = cursor.fetchone()
            palety_count = prod_row['cnt'] or 0
            total_kg = float(prod_row['total_kg'] or 0)
            
            expected_bags = palety_count * szt_na_palecie
            total_consumed = 0
            
            # 3. Process each packaging item
            for res in packaging_results:
                link_id = res['link_id']
                stan_po = float(res['stan_po'])
                
                # Fetch linking record
                cursor.execute("SELECT opakowanie_id, stan_poczatkowy FROM agro_plan_opakowania WHERE id = %s", (link_id,))
                link_row = cursor.fetchone()
                if not link_row: continue
                
                opak_id = link_row['opakowanie_id']
                stan_przed = float(link_row['stan_poczatkowy'])
                zuzycie = max(stan_przed - stan_po, 0)
                total_consumed += zuzycie
                
                # Update link record
                cursor.execute(
                    "UPDATE agro_plan_opakowania SET stan_koncowy = %s, is_active = FALSE WHERE id = %s",
                    (stan_po, link_id)
                )
                
                # Update main warehouse stock (synchronize)
                cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s WHERE id = %s", (stan_po, opak_id))
                
                # Fetch packaging name
                cursor.execute("SELECT nazwa FROM magazyn_opakowania WHERE id = %s", (opak_id,))
                opak_nazwa = (cursor.fetchone() or {}).get('nazwa', 'Opakowanie')
                
                # Insert into agro_workowanie_rozliczenie
                cursor.execute("""
                    INSERT INTO agro_workowanie_rozliczenie (
                        plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                        stan_przed, wyprodukowano_szt, szt_na_palecie, palety_kg_wykonane,
                        zuzyte_worki, stan_po, autor_login
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    plan_id, data_planu, produkt, opak_id, opak_nazwa,
                    stan_przed, palety_count, szt_na_palecie, total_kg,
                    zuzycie, stan_po, user_login
                ))
                
                # Log to movement history
                table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                try:
                    cursor.execute(
                        f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                        "VALUES (%s, 'ROZLICZENIE_WORKOWANIE', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                        (opak_id, -zuzycie, stan_po, user_login, f"Rozliczenie plan #{plan_id}")
                    )
                except: pass
            
            # 4. Calculate total waste (damaged bags)
            uszkodzone = max(total_consumed - expected_bags, 0)
            
            # 5. Update plan record
            cursor.execute(f"UPDATE {table_plan} SET uszkodzone_worki = %s WHERE id = %s", (int(uszkodzone), plan_id))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error in finalize_packaging_usage: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    @staticmethod
    def link_packaging_to_plan(opakowanie_id, plan_id):
        """Manually link a packaging item to a production plan (confirmed by operator)."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # 1. Get current state
            cursor.execute("SELECT stan_magazynowy FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
            row = cursor.fetchone()
            if not row: return False, "Opakowanie nie istnieje"
            stan_poczatkowy = row['stan_magazynowy']
            
            # 2. Check if already linked and active
            cursor.execute("SELECT id FROM agro_plan_opakowania WHERE plan_id = %s AND opakowanie_id = %s AND is_active = TRUE", (plan_id, opakowanie_id))
            if cursor.fetchone(): return True, "Już podpięte"
            
            # 3. Link
            cursor.execute(
                "INSERT INTO agro_plan_opakowania (plan_id, opakowanie_id, stan_poczatkowy, is_active) VALUES (%s, %s, %s, TRUE)",
                (plan_id, opakowanie_id, stan_poczatkowy)
            )
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def return_packaging_from_machine(opakowanie_id, stan_po, lokalizacja, user_login):
        """Return a roll from machine back to warehouse with manual state & location."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Ensure stan_po is a float
            try:
                final_stan = float(stan_po) if (stan_po is not None and str(stan_po).strip() != '') else 0.0
            except (ValueError, TypeError):
                final_stan = 0.0

            final_loc = lokalizacja if (lokalizacja and lokalizacja.strip()) else ('ZUŻYTE' if final_stan <= 0 else 'Maszyna')
            
            # 1. Update main warehouse record
            cursor.execute(
                "UPDATE magazyn_opakowania SET stan_magazynowy = %s, lokalizacja = %s, updated_at = NOW() WHERE id = %s",
                (final_stan, final_loc, opakowanie_id)
            )
            
            # 2. If it was linked to an active plan, finalize that link
            cursor.execute("""
                SELECT id, plan_id, stan_poczatkowy 
                FROM agro_plan_opakowania 
                WHERE opakowanie_id = %s AND is_active = TRUE 
                ORDER BY created_at DESC LIMIT 1
            """, (opakowanie_id,))
            link = cursor.fetchone()
            
            if link:
                plan_id = link['plan_id']
                stan_przed = float(link['stan_poczatkowy'])
                zuzycie = max(stan_przed - float(stan_po), 0)
                
                # Update link record
                cursor.execute(
                    "UPDATE agro_plan_opakowania SET stan_koncowy = %s, is_active = FALSE WHERE id = %s",
                    (stan_po, link['id'])
                )
                
                # Fetch basic info for history
                cursor.execute("SELECT nazwa FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
                opak_nazwa = (cursor.fetchone() or {}).get('nazwa', 'Opakowanie')
                
                cursor.execute(f"SELECT data_planu, produkt FROM {get_table_name('plan_produkcji', 'AGRO')} WHERE id = %s", (plan_id,))
                p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}

                # Record in settlement history
                cursor.execute("""
                    INSERT INTO agro_workowanie_rozliczenie (
                        plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                        stan_przed, zuzyte_worki, stan_po, autor_login
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    plan_id, p_meta['data_planu'], p_meta['produkt'], opakowanie_id, opak_nazwa,
                    stan_przed, zuzycie, stan_po, user_login
                ))
            
            # 3. Log movement
            table_ruch = get_table_name('magazyn_ruch', 'AGRO')
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                "VALUES (%s, 'ZWROT_Z_MASZYNY', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                (opakowanie_id, 0, stan_po, user_login, f"Zwrot na lok: {lokalizacja}")
            )
            
            conn.commit()
            return True, None
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def adjust_inventory(surowiec_id, actual_qty, worker_login, linia='Agro', komentarz=None):
        """Korekta inwentaryzacyjna stanu palety surowca."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            row = cursor.fetchone()
            if not row:
                return False
            
            old_qty = row[0]
            delta = actual_qty - old_qty
            
            # 1. Aktualizacja stanu
            cursor.execute(f"UPDATE {table_surowce} SET stan_magazynowy = %s WHERE id = %s", (actual_qty, surowiec_id))
            
            # 2. Log ruchu
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                "VALUES (%s, 'INWENTARYZACJA', %s, %s, 'POTWIERDZONE', %s, %s, %s)",
                (surowiec_id, delta, actual_qty, worker_login, datetime.now(), komentarz or 'Korekta inwentaryzacyjna')
            )
            
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def issue_warehouse(surowiec_id, ilosc, worker_login, linia='Agro', komentarz=None):
        """Wydanie zewnętrzne lub likwidacja surowca (zdjęcie ze stanu bez produkcji)."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Zdjęcie ze stanu
            cursor.execute(f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy - %s WHERE id = %s", (ilosc, surowiec_id))
            
            # 2. Pobranie nowego stanu
            cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            stan_po = cursor.fetchone()[0]
            
            # 3. Log ruchu
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                "VALUES (%s, 'WYDANIE_MAG', %s, %s, 'POTWIERDZONE', %s, %s, %s)",
                (surowiec_id, -ilosc, stan_po, worker_login, datetime.now(), komentarz or 'Wydanie z magazynu')
            )
            
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def get_warehouse_entries(limit=1000, linia='Agro', date_from=None, date_to=None):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            try:
                table_plan = get_table_name('plan_produkcji', linia)
                plan_join = f" LEFT JOIN {table_plan} p ON r.plan_id = p.id "
                plan_select = ", p.produkt as plan_name"
            except Exception:
                plan_join = ""
                plan_select = ", NULL as plan_name"

            q = (
                f"SELECT r.*, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, s.lokalizacja as obecna_lokalizacja{plan_select} "
                f"FROM {table_ruch} r LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id {plan_join} "
                "WHERE r.typ_ruchu = 'PRZYJECIE' AND r.status = 'POTWIERDZONE' "
            )
            params = []
            if date_from:
                q += " AND DATE(r.autor_data) >= %s "
                params.append(date_from)
            if date_to:
                q += " AND DATE(r.autor_data) <= %s "
                params.append(date_to)
            q += " ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
            params.append(limit)
            cursor.execute(q, tuple(params))
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_combined_report(limit=2000, linia='Agro', date_from=None, date_to=None):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            try:
                table_plan = get_table_name('plan_produkcji', linia)
                plan_join = f" LEFT JOIN {table_plan} p ON r.plan_id = p.id "
                plan_select = ", p.produkt as plan_name"
            except Exception:
                plan_join = ""
                plan_select = ", NULL as plan_name"

            q = (
                f"SELECT r.*, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, s.lokalizacja as obecna_lokalizacja{plan_select} "
                f"FROM {table_ruch} r LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id {plan_join} "
                "WHERE r.typ_ruchu IN ('PRZYJECIE','PRODUKCJA','WYDANIE_ZEW','WYDANIE_MAG','ZWROT','INWENTARYZACJA','KOREKTA') "
            )
            params = []
            if date_from:
                q += " AND DATE(r.autor_data) >= %s "
                params.append(date_from)
            if date_to:
                q += " AND DATE(r.autor_data) <= %s "
                params.append(date_to)
            q += " ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
            params.append(limit)
            cursor.execute(q, tuple(params))
            return cursor.fetchall()
        finally:
            conn.close()
    @staticmethod
    def auto_register_pallet(plan_id, linia='AGRO', source_instance=None):
        """Automatically registers a 1000kg pallet for a given plan."""
        from app.utils.pallet_id import generate_pallet_id
        from app.services.planning_service import PlanningService
        from app.core.audit import audit_log
        
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Acquire database-level lock to prevent concurrency race conditions on MyISAM storage engine
            cursor.execute("SELECT GET_LOCK('agro_pallet_register', 10)")
            lock_res = cursor.fetchone()
            if not lock_res or lock_res[0] != 1:
                return False
            
            # Reset transaction snapshot so we see the latest committed data in repeatable-read isolation
            conn.commit()
            
            # Fetch plan info
            cursor.execute(f"SELECT produkt, sekcja FROM {table_plan} WHERE id=%s", (plan_id,))
            plan_row = cursor.fetchone()
            if not plan_row:
                return False
            
            plan_produkt, plan_sekcja = plan_row
            if plan_sekcja != 'Workowanie':
                return False
            
            waga_input = 1000
            now_ts = datetime.now()
            user_login = 'System'
            source_instance = str(source_instance or 'unknown')[:120]
            
            # Cooldown check: prevent duplicate auto-registration (e.g. from multiple threads or bit flickering)
            # Find the most recently added pallet for this plan
            cursor.execute(
                f"SELECT MAX(data_dodania) FROM {table_pal} WHERE plan_id = %s",
                (plan_id,)
            )
            latest_row = cursor.fetchone()
            if latest_row and latest_row[0]:
                latest_date = latest_row[0]
                if isinstance(latest_date, str):
                    try:
                        latest_date = datetime.strptime(latest_date, '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        pass
                
                time_diff = (now_ts - latest_date).total_seconds()
                if time_diff < 45:
                    print(f"[COOLDOWN] Skipped auto-registering pallet. Last pallet added {time_diff:.1f}s ago (cooldown 45s).")
                    return False
            
            nr_palety = generate_pallet_id(linia)
            
            # Insert pallet
            cursor.execute(
                f"INSERT INTO {table_pal} (plan_id, waga, tara, waga_brutto, data_dodania, status, dodal_login, nr_palety) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia', %s, %s)",
                (plan_id, waga_input, now_ts, user_login, nr_palety),
            )
            
            # Update plan tonnage
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id = %s",
                (waga_input, plan_id),
            )
            
            conn.commit()
            
            # Ensure status is updated (e.g. from 'w toku' to 'zakonczone' if target reached, though usually stays 'w toku')
            try:
                PlanningService.ensure_status_after_tonaz_update(plan_id, linia=linia)
            except Exception:
                pass
                
            audit_log(
                'System: Automatycznie dodano paletę',
                f'plan_id={plan_id}, produkt={plan_produkt}, waga={waga_input} kg, source_instance={source_instance}',
            )
            return True
        finally:
            try:
                cursor.execute("SELECT RELEASE_LOCK('agro_pallet_register')")
            except Exception:
                pass
            conn.close()

    @staticmethod
    def undo_packaging_link(link_id):
        """Delete an active packaging link (Undo addition)."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, plan_id, opakowanie_id, stan_poczatkowy, is_active FROM agro_plan_opakowania WHERE id = %s", (link_id,))
            row = cursor.fetchone()
            if not row:
                return False, "Nie znaleziono takiego powiązania"
            
            cursor.execute("DELETE FROM agro_plan_opakowania WHERE id = %s", (link_id,))
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def undo_packaging_return(link_id, user_login):
        """Restore an inactive packaging link to active state and revert warehouse stock."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, plan_id, opakowanie_id, stan_poczatkowy, stan_koncowy, is_active FROM agro_plan_opakowania WHERE id = %s", (link_id,))
            row = cursor.fetchone()
            if not row:
                return False, "Nie znaleziono powiązania"
            
            plan_id = row['plan_id']
            opakowanie_id = row['opakowanie_id']
            stan_poczatkowy = float(row['stan_poczatkowy'])
            
            # Restore is_active state
            cursor.execute("UPDATE agro_plan_opakowania SET is_active = TRUE, stan_koncowy = NULL WHERE id = %s", (link_id,))
            
            # Restore main warehouse stock
            cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s, lokalizacja = 'Maszyna' WHERE id = %s", (stan_poczatkowy, opakowanie_id))
            
            # Delete corresponding history records from agro_workowanie_rozliczenie
            cursor.execute("DELETE FROM agro_workowanie_rozliczenie WHERE plan_id = %s AND opakowanie_id = %s", (plan_id, opakowanie_id))
            
            # Delete corresponding history records from magazyn_ruch
            table_ruch = get_table_name('magazyn_ruch', 'AGRO')
            cursor.execute(f"DELETE FROM {table_ruch} WHERE surowiec_id = %s AND typ_ruchu = 'ZWROT_Z_MASZYNY' ORDER BY id DESC LIMIT 1", (opakowanie_id,))
            
            conn.commit()
            return True, None
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

