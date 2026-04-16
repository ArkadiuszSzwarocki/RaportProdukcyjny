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
    def get_inventory_grouped(linia='Agro'):
        """Return inventory grouped by material name. Each group contains total quantity and list of pallets ordered by FIFO (id asc)."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # get distinct materials with total quantity
            cursor.execute(f"SELECT nazwa, SUM(stan_magazynowy) as total FROM {table_surowce} WHERE stan_magazynowy > 0 GROUP BY nazwa ORDER BY nazwa")
            groups = cursor.fetchall()
            result = []
            for g in groups:
                name = g['nazwa']
                total = float(g['total']) if g.get('total') is not None else 0.0
                # fetch individual pallets for this material ordered by id (FIFO)
                cursor.execute(f"SELECT id, nazwa, stan_magazynowy, lokalizacja FROM {table_surowce} WHERE nazwa = %s AND stan_magazynowy > 0 ORDER BY id ASC", (name,))
                pallets = cursor.fetchall()
                # normalize pallet rows
                pallets_norm = []
                for p in pallets:
                    pallets_norm.append({
                        'id': p['id'],
                        'nazwa': p.get('nazwa'),
                        'stan_magazynowy': float(p.get('stan_magazynowy') or 0),
                        'lokalizacja': p.get('lokalizacja')
                    })
                result.append({ 'nazwa': name, 'total': total, 'pallets': pallets_norm })
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
    def add_delivery(nazwa, ilosc, author_login, linia='Agro', komentarz=None):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Check if surowiec exists in dictionary
            cursor.execute("INSERT IGNORE INTO magazyn_agro_slownik_surowce (nazwa) VALUES (%s)", (nazwa,))
            
            # 2. Add pending movement with NAZWA
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_nazwa, typ_ruchu, ilosc, status, autor_login, autor_data, komentarz) "
                "VALUES (%s, 'PRZYJECIE', %s, 'OCZEKUJACE', %s, %s, %s)",
                (nazwa, ilosc, author_login, datetime.now(), komentarz)
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
    def confirm_delivery(ruch_id, worker_login, linia='Agro', lokalizacja=None):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT surowiec_nazwa, ilosc, status FROM {table_ruch} WHERE id = %s", (ruch_id,))
            row = cursor.fetchone()
            if not row or row[2] != 'OCZEKUJACE':
                return False
            
            name, qty = row[0], row[1]
            
            # PALLET TRACKING: We ALWAYS create a NEW row for each confirmed pallet
            # Each row is a unique (material, location) pair.
            
            # Check if spot is occupied
            if lokalizacja:
                cursor.execute(f"SELECT id FROM {table_surowce} WHERE lokalizacja = %s AND stan_magazynowy > 0", (lokalizacja,))
                if cursor.fetchone():
                    return False # Spot occupied
            
            # Create the stock record (the "pallet")
            cursor.execute(f"INSERT INTO {table_surowce} (nazwa, stan_magazynowy, lokalizacja) VALUES (%s, %s, %s)", (name, qty, lokalizacja))
            surowiec_id = cursor.lastrowid
            
            # Update history
            cursor.execute(
                f"UPDATE {table_ruch} SET surowiec_id = %s, lokalizacja = %s, status = 'POTWIERDZONE', potwierdzil_login = %s, potwierdzil_data = %s WHERE id = %s",
                (surowiec_id, lokalizacja, worker_login, datetime.now(), ruch_id)
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
            
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def perform_inventory(surowiec_id, actual_qty, worker_login, linia='Agro', komentarz=None):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            old_qty = cursor.fetchone()[0]
            delta = actual_qty - old_qty
            
            cursor.execute(f"UPDATE {table_surowce} SET stan_magazynowy = %s WHERE id = %s", (actual_qty, surowiec_id))
            
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz) "
                "VALUES (%s, 'INWENTARYZACJA', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s)",
                (surowiec_id, delta, actual_qty, worker_login, datetime.now(), worker_login, datetime.now(), komentarz)
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
    def issue_warehouse(surowiec_id, ilosc, worker_login, linia='Agro', komentarz=None):
        """Wydanie surowca z magazynu (nie na produkcję). Tworzy ruch OCZEKUJACE typu WYDANIE_MAG."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT nazwa, lokalizacja FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            row = cursor.fetchone()
            if not row:
                return False
            nazwa = f"{row[0]} ({row[1]})" if row[1] else row[0]

            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, status, autor_login, autor_data, komentarz) "
                "VALUES (%s, %s, 'WYDANIE_MAG', %s, 'OCZEKUJACE', %s, %s, %s)",
                (surowiec_id, nazwa, ilosc, worker_login, datetime.now(), komentarz)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def confirm_warehouse_issue(ruch_id, worker_login, linia='Agro'):
        """Potwierdź wydanie z magazynu — zmniejsz stan palety."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT surowiec_id, ilosc, status, typ_ruchu FROM {table_ruch} WHERE id = %s", (ruch_id,))
            row = cursor.fetchone()
            if not row or row[2] != 'OCZEKUJACE' or row[3] != 'WYDANIE_MAG':
                return False

            s_id, qty = row[0], row[1]
            if not s_id:
                return False
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
    def get_locations_inventory(linia='Agro'):
        """Zwraca wszystkie palety z lokalizacjami i stanami — do inwentaryzacji regałów."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT id, nazwa, stan_magazynowy, lokalizacja FROM {table_surowce} "
                "WHERE stan_magazynowy > 0 OR lokalizacja IS NOT NULL "
                "ORDER BY lokalizacja ASC, nazwa ASC"
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def perform_bulk_inventory(items, worker_login, linia='Agro'):
        """Inwentaryzacja zbiorcza — lista {surowiec_id, actual_qty, komentarz}."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            count = 0
            now = datetime.now()
            for item in items:
                sid = item.get('surowiec_id')
                actual = float(item.get('actual_qty', 0))
                note = item.get('komentarz') or 'Inwentaryzacja zbiorcza'

                cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (sid,))
                row = cursor.fetchone()
                if not row:
                    continue
                old_qty = float(row[0])
                if old_qty == actual:
                    continue  # brak zmiany

                delta = actual - old_qty
                cursor.execute(f"UPDATE {table_surowce} SET stan_magazynowy = %s WHERE id = %s", (actual, sid))
                cursor.execute(
                    f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz) "
                    "VALUES (%s, 'INWENTARYZACJA', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s)",
                    (sid, delta, actual, worker_login, now, worker_login, now, note)
                )
                count += 1
            conn.commit()
            return count
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
