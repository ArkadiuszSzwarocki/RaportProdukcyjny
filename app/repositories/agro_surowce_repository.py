from app.repositories.agro_tanks_repository import AgroTanksRepository
import logging
from app.db import get_db_connection, get_table_name
import datetime
import os
import re

_DODATEK_NAME_REGEX = re.compile(r'DODATEK')

def _normalize_tank_code(value):
    normalized = str(value or '').strip().upper()
    return normalized or None

def _classify_tank_zone(tank_code):
    normalized = _normalize_tank_code(tank_code)
    if not normalized:
        return 'BRAK'
    if normalized.startswith('BB'):
        return 'BB'
    if normalized.startswith('MZ'):
        return 'MZ'
    if normalized.startswith('KO'):
        return 'KO'
    return 'INNE'

def _is_additive_material(material_name, material_location=None):
    name = str(material_name or '').upper()
    location = str(material_location or '').upper()
    if location.startswith('DOD'):
        return True
    return bool(_DODATEK_NAME_REGEX.search(name))

def _get_auto_pallet_cooldown_seconds():
    """Return cooldown for auto pallet registration (seconds)."""
    raw_value = os.getenv('AGRO_AUTO_PALLET_COOLDOWN_SECONDS', '0')
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid AGRO_AUTO_PALLET_COOLDOWN_SECONDS=%r. Falling back to 0s.",
            raw_value,
        )
        return 0.0
    return max(0.0, parsed)

def _select_preferred_printer(cursor):
    """Pick production printer first, then fallback to any active printer."""
    cursor.execute(
        """
        SELECT id, nazwa, ip, lokalizacja
        FROM drukarki
        WHERE aktywna = 1
        ORDER BY
            CASE
                WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                ELSE 2
            END,
            id ASC
        LIMIT 1
        """
    )
    return cursor.fetchone()

def _sanitize_zpl_text(value, max_length=64):
    text = str(value or '')
    text = text.replace('^', ' ').replace('~', ' ')
    text = text.replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    if max_length and len(text) > max_length:
        return text[:max_length]
    return text

def _format_quantity_label(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return '0'

    if abs(numeric - round(numeric)) < 1e-6:
        return str(int(round(numeric)))
    return f"{numeric:.2f}".rstrip('0').rstrip('.')

class AgroSurowceRepository:
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
                    q_p = f"SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, typ_opakowania, nr_partii, created_at FROM {table_surowce} {where_clause} AND nazwa = %s ORDER BY id ASC"
                    cursor.execute(q_p, tuple(params + [name]))
                    pallets = cursor.fetchall()
                    # normalize pallet rows
                    pallets_norm = []
                    for p in pallets:
                        pallets_norm.append({
                            'id': p['id'],
                            'nr_palety': p.get('nr_palety'),
                            'nazwa': p.get('nazwa'),
                            'stan_magazynowy': float(p.get('stan_magazynowy') or 0),
                            'lokalizacja': p.get('lokalizacja'),
                            'typ_opakowania': p.get('typ_opakowania'),
                            'nr_partii': p.get('nr_partii'),
                            'created_at': p.get('created_at')
                        })
                    result.append({ 'nazwa': name, 'total': total, 'pallets': pallets_norm })
                return result
            finally:
                conn.close()

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

    def get_dictionary():
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT nazwa FROM magazyn_agro_slownik_surowce ORDER BY nazwa ASC")
                return cursor.fetchall()
            finally:
                conn.close()

    def get_occupied_locations(linia='Agro'):
            table_surowce = get_table_name('magazyn_surowce', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"SELECT lokalizacja FROM {table_surowce} WHERE lokalizacja IS NOT NULL AND stan_magazynowy > 0")
                return [r[0] for r in cursor.fetchall()]
            finally:
                conn.close()

    def get_suggested_location(nazwa, linia='Agro'):
            table_surowce = get_table_name('magazyn_surowce', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                occupied = AgroSurowceRepository.get_occupied_locations(linia)
                
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
                
                # Walidacja: lokalizacja NIE może być kodem zbiornika produkcyjnego
                if lokalizacja:
                    is_valid, error_msg = validate_warehouse_location(lokalizacja, allow_empty=False)
                    if not is_valid:
                        logger.warning(f"Attempted to use production tank code as warehouse location: {lokalizacja}")
                        return False  # Blocked: production tank code
                
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
                raw_zbiornik = _normalize_tank_code(zbiornik)
                zbiornik_val = AgroTanksRepository.normalize_production_tank(raw_zbiornik) or raw_zbiornik
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
                    "WHERE r.typ_ruchu IN ('PRZYJECIE','PRODUKCJA','WYDANIE_ZEW','WYDANIE_MAG','ZWROT','INWENTARYZACJA','INWENTARYZACJA_PROD','KOREKTA') "
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

