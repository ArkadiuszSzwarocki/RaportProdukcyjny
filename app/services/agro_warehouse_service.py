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
            cursor.execute(f"SELECT * FROM {table_surowce} WHERE stan_magazynowy > 0 ORDER BY nazwa, lokalizacja")
            res = cursor.fetchall()
            return res
        finally:
            conn.close()

    @staticmethod
    def get_grouped_inventory(linia='Agro'):
        """Return inventory grouped by surowiec name with total qty and pallet count."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT nazwa, "
                f"SUM(stan_magazynowy) AS total_kg, "
                f"COUNT(*) AS liczba_palet "
                f"FROM {table_surowce} "
                f"WHERE stan_magazynowy > 0 "
                f"GROUP BY nazwa "
                f"ORDER BY nazwa ASC"
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_palety_dla_surowca(nazwa, linia='Agro'):
        """Return all active pallets for a surowiec, sorted by id ASC (FIFO order, oldest first)."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT id, nazwa, stan_magazynowy, lokalizacja "
                f"FROM {table_surowce} "
                f"WHERE nazwa = %s AND stan_magazynowy > 0 "
                f"ORDER BY id ASC",
                (nazwa,)
            )
            rows = cursor.fetchall()
            # Convert Decimal to float for JSON serialization
            for r in rows:
                r['stan_magazynowy'] = float(r['stan_magazynowy'])
            return rows
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
    def use_for_production(surowiec_id, ilosc, worker_login, plan_id=None, linia='Agro', komentarz=None):
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
            cursor.execute(
                f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz) "
                "VALUES (%s, 'PRODUKCJA', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s, %s)",
                (surowiec_id, -ilosc, stan_po, worker_login, datetime.now(), worker_login, datetime.now(), plan_id, komentarz)
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
            cursor.execute(f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy - %s WHERE id = %s", (qty, s_id))
            cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (s_id,))
            stan_po = cursor.fetchone()[0]
            
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
    def get_history(limit=100, status=None, linia='Agro'):
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            q = f"SELECT r.*, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa FROM {table_ruch} r LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id "
            params = []
            if status:
                q += " WHERE r.status = %s "
                params.append(status)
            q += " ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
            params.append(limit)
            cursor.execute(q, tuple(params))
            return cursor.fetchall()
        finally:
            conn.close()
