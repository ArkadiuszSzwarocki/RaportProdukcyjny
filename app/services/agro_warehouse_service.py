import logging
import os
import re
from datetime import datetime

from app.db import get_db_connection, get_table_name
from app.utils.location_validator import validate_warehouse_location, is_production_tank_code


logger = logging.getLogger(__name__)


BB_TANK_CODES = [f"BB{i:02d}" for i in range(1, 25)]
MZ_TANK_CODES = [f"MZ{i:02d}" for i in range(1, 25)] + ["MZ05-01", "MZ06-01"]
KO_TANK_CODES = [f"KO{i:02d}" for i in range(1, 25)]
PRODUCTION_TANK_CODES = BB_TANK_CODES + MZ_TANK_CODES + KO_TANK_CODES

_DODATEK_NAME_REGEX = re.compile(r"\b(DOD|DODAT|DODATEK|DODATKI)\b", re.IGNORECASE)


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
    def get_production_tanks():
        return {
            'BB': list(BB_TANK_CODES),
            'MZ': list(MZ_TANK_CODES),
            'KO': list(KO_TANK_CODES),
            'ALL': list(PRODUCTION_TANK_CODES),
        }

    @staticmethod
    def normalize_production_tank(tank_code):
        normalized = _normalize_tank_code(tank_code)
        if not normalized:
            return None
        return normalized if normalized in PRODUCTION_TANK_CODES else None

    @staticmethod
    def get_packaging_inventory(linia='Agro'):
        """Return packaging inventory rows from magazyn_opakowania."""
        table_opak = get_table_name('magazyn_opakowania', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT * FROM {table_opak} "
                f"WHERE (lokalizacja != 'ZUŻYTE' OR lokalizacja IS NULL) AND stan_magazynowy > 0 "
                f"ORDER BY nazwa, id"
            )
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
            raw_zbiornik = _normalize_tank_code(zbiornik)
            zbiornik_val = AgroWarehouseService.normalize_production_tank(raw_zbiornik) or raw_zbiornik
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
        
        Każdy wiersz: ruch_id, surowiec_id, nazwa, lokalizacja, ilosc_pobrana, ilosc_zwrocona,
        ilosc_korekta, do_zwrotu, plan_id, plan_name, data, zbiornik.
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
                f"COALESCE((SELECT SUM(k.ilosc) FROM {table_ruch} k WHERE k.ruch_zrodlowy_id = r.id AND k.typ_ruchu = 'INWENTARYZACJA_PROD'), 0) as ilosc_korekta, "
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
                korekta = float(r.get('ilosc_korekta') or 0)
                do_zwrotu = round(pobrana - zwrocona + korekta, 2)
                if do_zwrotu <= 0:
                    continue  # w pełni zwrócone
                result.append({
                    'ruch_id': r['ruch_id'],
                    'surowiec_id': r.get('surowiec_id'),
                    'nazwa': r.get('nazwa') or '',
                    'lokalizacja': r.get('lokalizacja') or '',
                    'ilosc_pobrana': pobrana,
                    'ilosc_zwrocona': zwrocona,
                    'ilosc_korekta': korekta,
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
    def get_production_inventory(limit=500, linia='Agro'):
        """Zwraca bieżące stany surowców pozostających w produkcji (BB/MZ/KO)."""
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
                f"COALESCE((SELECT SUM(k.ilosc) FROM {table_ruch} k WHERE k.ruch_zrodlowy_id = r.id AND k.typ_ruchu = 'INWENTARYZACJA_PROD'), 0) as ilosc_korekta, "
                f"r.plan_id, r.autor_login, r.autor_data, r.zbiornik{plan_select} "
                f"FROM {table_ruch} r LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id {plan_join} "
                "WHERE r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE' "
                "AND COALESCE(NULLIF(TRIM(r.zbiornik), ''), '') <> '' "
                "ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
            )
            cursor.execute(q, (limit,))
            rows = cursor.fetchall()

            result = []
            for r in rows:
                pobrana = float(r.get('ilosc_pobrana') or 0)
                zwrocona = float(r.get('ilosc_zwrocona') or 0)
                korekta = float(r.get('ilosc_korekta') or 0)
                stan_systemowy = round(pobrana - zwrocona + korekta, 2)
                if stan_systemowy <= 0:
                    continue

                zbiornik = _normalize_tank_code(r.get('zbiornik'))
                strefa = _classify_tank_zone(zbiornik)
                rodzaj = 'DODATKI' if _is_additive_material(r.get('nazwa'), r.get('lokalizacja')) else 'SUROWCE'

                result.append({
                    'ruch_id': r['ruch_id'],
                    'surowiec_id': r.get('surowiec_id'),
                    'nazwa': r.get('nazwa') or '',
                    'lokalizacja': r.get('lokalizacja') or '',
                    'zbiornik': zbiornik or '',
                    'strefa': strefa,
                    'rodzaj': rodzaj,
                    'ilosc_pobrana': pobrana,
                    'ilosc_zwrocona': zwrocona,
                    'ilosc_korekta': korekta,
                    'stan_systemowy': stan_systemowy,
                    'plan_id': r.get('plan_id'),
                    'plan_name': r.get('plan_name') or '',
                    'autor_login': r.get('autor_login') or '',
                    'data': r['autor_data'].strftime('%d.%m.%Y %H:%M') if r.get('autor_data') else '',
                })

            return result
        finally:
            conn.close()

    @staticmethod
    def get_production_inventory_snapshot(limit=4000, linia='Agro', show_empty=False):
        """Zwraca aktualny snapshot produkcji: maksymalnie 1 surowiec na zbiornik.

        Snapshot wybiera najnowszy aktywny wpis (stan_systemowy > 0) dla każdego zbiornika.
        Gdy show_empty=True, zwraca również puste zdefiniowane zbiorniki.
        """
        rows = AgroWarehouseService.get_production_inventory(limit=limit, linia=linia)
        by_tank = {}

        for row in rows:
            tank_code = _normalize_tank_code(row.get('zbiornik'))
            if not tank_code:
                continue
            if tank_code in by_tank:
                continue

            item = dict(row)
            item['zbiornik'] = tank_code
            item['surowiec_nazwa'] = item.get('nazwa') or ''
            item['plan_nazwa'] = item.get('plan_name') or ''
            item['is_empty'] = False
            by_tank[tank_code] = item

        if show_empty:
            for tank_code in AgroWarehouseService.get_production_tanks().get('ALL', []):
                if tank_code in by_tank:
                    continue
                by_tank[tank_code] = {
                    'ruch_id': None,
                    'surowiec_id': None,
                    'nazwa': '',
                    'surowiec_nazwa': '',
                    'lokalizacja': '',
                    'zbiornik': tank_code,
                    'strefa': _classify_tank_zone(tank_code),
                    'rodzaj': '',
                    'ilosc_pobrana': 0.0,
                    'ilosc_zwrocona': 0.0,
                    'ilosc_korekta': 0.0,
                    'stan_systemowy': 0.0,
                    'plan_id': None,
                    'plan_name': '',
                    'plan_nazwa': '',
                    'autor_login': '',
                    'data': '',
                    'is_empty': True,
                }

        def _tank_sort_key(item):
            tank = item.get('zbiornik') or ''
            zone = _classify_tank_zone(tank)
            zone_rank = {'BB': 0, 'MZ': 1, 'KO': 2, 'INNE': 3, 'BRAK': 4}.get(zone, 9)
            return (zone_rank, tank)

        return sorted(by_tank.values(), key=_tank_sort_key)

    @staticmethod
    def get_production_tank_history(tank_code, limit=300, linia='Agro'):
        """Zwraca historię ruchów dla wskazanego zbiornika produkcyjnego."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        normalized_tank = _normalize_tank_code(tank_code)
        if not normalized_tank:
            return []

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
                f"SELECT r.id, r.typ_ruchu, r.ilosc, r.ilosc_po, r.status, r.autor_login, r.autor_data, r.komentarz, "
                f"COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, r.plan_id, r.zbiornik{plan_select} "
                f"FROM {table_ruch} r "
                f"LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id "
                f"{plan_join} "
                "WHERE UPPER(TRIM(COALESCE(r.zbiornik, ''))) = %s "
                "AND r.typ_ruchu IN ('PRODUKCJA', 'ZWROT', 'INWENTARYZACJA_PROD') "
                "ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
            )
            cursor.execute(q, (normalized_tank, limit))
            rows = cursor.fetchall()

            result = []
            for r in rows:
                result.append({
                    'id': r.get('id'),
                    'typ_ruchu': r.get('typ_ruchu') or '',
                    'ilosc': float(r.get('ilosc') or 0),
                    'ilosc_po': float(r.get('ilosc_po') or 0),
                    'status': r.get('status') or '',
                    'autor_login': r.get('autor_login') or '',
                    'autor_data': r['autor_data'].strftime('%d.%m.%Y %H:%M') if r.get('autor_data') else '',
                    'komentarz': r.get('komentarz') or '',
                    'surowiec_nazwa': r.get('surowiec_nazwa') or '',
                    'plan_id': r.get('plan_id'),
                    'plan_name': r.get('plan_name') or '',
                    'zbiornik': _normalize_tank_code(r.get('zbiornik')) or normalized_tank,
                })

            return result
        finally:
            conn.close()

    @staticmethod
    def adjust_production_inventory(ruch_id, actual_qty, worker_login, linia='Agro', komentarz=None):
        """Korekta stanu surowca będącego w produkcji (BB/MZ/KO) dla wskazanego ruchu PRODUKCJA."""
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT id, surowiec_id, COALESCE(surowiec_nazwa, '') as surowiec_nazwa, plan_id, zbiornik "
                f"FROM {table_ruch} WHERE id = %s AND typ_ruchu = 'PRODUKCJA' AND status = 'POTWIERDZONE'",
                (ruch_id,)
            )
            base_move = cursor.fetchone()
            if not base_move:
                return False, 'Nie znaleziono ruchu PRODUKCJA do korekty.'

            cursor.execute(
                f"SELECT ABS(COALESCE(ilosc, 0)) as ilosc_pobrana FROM {table_ruch} WHERE id = %s",
                (ruch_id,)
            )
            pobrana_row = cursor.fetchone() or {}
            pobrana = float(pobrana_row.get('ilosc_pobrana') or 0)

            cursor.execute(
                f"SELECT COALESCE(SUM(ilosc), 0) as ilosc_zwrocona FROM {table_ruch} "
                "WHERE ruch_zrodlowy_id = %s AND typ_ruchu = 'ZWROT'",
                (ruch_id,)
            )
            zwrot_row = cursor.fetchone() or {}
            zwrocona = float(zwrot_row.get('ilosc_zwrocona') or 0)

            cursor.execute(
                f"SELECT COALESCE(SUM(ilosc), 0) as ilosc_korekta FROM {table_ruch} "
                "WHERE ruch_zrodlowy_id = %s AND typ_ruchu = 'INWENTARYZACJA_PROD'",
                (ruch_id,)
            )
            korekta_row = cursor.fetchone() or {}
            korekta = float(korekta_row.get('ilosc_korekta') or 0)

            current_qty = round(pobrana - zwrocona + korekta, 3)
            delta = round(float(actual_qty) - current_qty, 3)
            if abs(delta) < 0.001:
                return True, None

            zbiornik_val = _normalize_tank_code(base_move.get('zbiornik'))
            opis = (komentarz or 'Inwentaryzacja produkcji').strip()
            if zbiornik_val:
                opis = f"{opis} ({zbiornik_val})"

            cursor.execute(
                f"INSERT INTO {table_ruch} "
                "(surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz, ruch_zrodlowy_id, zbiornik) "
                "VALUES (%s, %s, 'INWENTARYZACJA_PROD', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    base_move.get('surowiec_id'),
                    base_move.get('surowiec_nazwa') or None,
                    delta,
                    float(actual_qty),
                    worker_login,
                    datetime.now(),
                    worker_login,
                    datetime.now(),
                    base_move.get('plan_id'),
                    opis,
                    ruch_id,
                    zbiornik_val,
                )
            )
            conn.commit()
            return True, None
        except Exception as e:
            conn.rollback()
            return False, str(e)
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

            base_query = (
                f"SELECT id, produkt, data_planu, typ_produkcji, start_machine_counter, "
                f"start_pallet_counter, opakowanie_id "
                f"FROM {table_plan} WHERE status='w toku' AND sekcja='Workowanie'"
            )

            if target_date:
                query = f"{base_query} AND DATE(data_planu) = %s ORDER BY real_start DESC LIMIT 1"
                cursor.execute(query, (target_date,))
                return cursor.fetchone()

            # Prefer today's active plan, but allow rollover plans that started earlier
            # and are still running (e.g. long shifts crossing midnight).
            todays_query = f"{base_query} AND DATE(data_planu) = CURDATE() ORDER BY real_start DESC LIMIT 1"
            cursor.execute(todays_query)
            plan = cursor.fetchone()
            if plan:
                return plan

            fallback_query = f"{base_query} ORDER BY real_start DESC LIMIT 1"
            cursor.execute(fallback_query)
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
            
            query = f"SELECT id, produkt, data_planu, typ_produkcji, opakowanie_id FROM {table_plan} WHERE status='zakonczone' AND sekcja='Workowanie'"
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
            cursor.execute("SELECT start_machine_counter, stop_machine_counter FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
            counters_row = cursor.fetchone()
            if counters_row and counters_row['start_machine_counter'] > 0 and counters_row['stop_machine_counter'] > 0:
                total_pulled = max(counters_row['stop_machine_counter'] - counters_row['start_machine_counter'], 0)
                uszkodzone = max(total_pulled - expected_bags, 0)
            else:
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
    def link_packaging_to_plan(opakowanie_id, plan_id, ilosc_pobrana=None, user_login=None):
        """Manually link a packaging item to a production plan (confirmed by operator).
        Jeśli podano ilosc_pobrana mniejszą niż aktualny stan_magazynowy, rekord zostanie podzielony.
        Sumuje pozostałe na maszynie opakowania tego samego typu.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # 1. Get current state of new packaging
            cursor.execute("SELECT nazwa, stan_magazynowy, lokalizacja FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
            new_row = cursor.fetchone()
            if not new_row: return False, "Opakowanie nie istnieje"
            stan_poczatkowy_nowego = float(new_row['stan_magazynowy'])
            nazwa = new_row['nazwa']
            lokalizacja = new_row['lokalizacja']
            
            # 2. Find any active links for this plan (to close them or carry over)
            cursor.execute("""
                SELECT ap.id as link_id, ap.opakowanie_id, ap.stan_poczatkowy, o.nazwa 
                FROM agro_plan_opakowania ap
                JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                WHERE ap.plan_id = %s AND ap.is_active = TRUE
            """, (plan_id,))
            active_links = cursor.fetchall()
            
            carryover_qty = 0.0
            
            for al in active_links:
                if al['nazwa'] == nazwa:
                    # Same material name: calculate remaining qty on the fly and carry it over!
                    # Fetch plan metadata
                    cursor.execute("SELECT start_machine_counter, typ_produkcji, produkt FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
                    plan_row = cursor.fetchone()
                    live_total_pulled = 0
                    if plan_row:
                        table_palety = get_table_name('palety_workowanie', 'AGRO')
                        cursor.execute(f"SELECT COUNT(*) AS cnt, COALESCE(SUM(waga), 0) AS total_kg FROM {table_palety} WHERE plan_id = %s", (plan_id,))
                        totals_row = cursor.fetchone() or {'cnt': 0, 'total_kg': 0}
                        palety_count = int(totals_row.get('cnt') or 0)
                        palety_kg_wykonane = float(totals_row.get('total_kg') or 0.0)
                        
                        bag_kg = 25.0
                        typ_prod = plan_row['typ_produkcji'] or ''
                        kg_match = re.search(r'(\d+)', typ_prod)
                        if kg_match:
                            bag_kg = float(kg_match.group(1))
                        else:
                            produkt_nazwa = str(plan_row['produkt'] or '').lower()
                            if 'mleko' in produkt_nazwa or '20' in produkt_nazwa:
                                bag_kg = 20.0
                                
                        estimated_bags = int(round(palety_kg_wykonane / bag_kg)) if bag_kg > 0 else 0
                        live_total_pulled = estimated_bags
                        
                        start_machine_counter = int(plan_row['start_machine_counter'] or 0)
                        try:
                            from app.services.mqtt_service import get_latest_data
                            latest_d = get_latest_data()
                            current_counter = latest_d.get('counter', 0)
                            if current_counter > start_machine_counter and start_machine_counter > 0:
                                live_total_pulled = current_counter - start_machine_counter
                        except:
                            pass
                            
                    cursor.execute("SELECT COALESCE(SUM(zuzyte_worki), 0) AS total_zuzyte FROM agro_workowanie_rozliczenie WHERE plan_id = %s", (plan_id,))
                    already_logged_row = cursor.fetchone()
                    already_logged = float(already_logged_row.get('total_zuzyte') or 0) if already_logged_row else 0.0
                    
                    stan_poczatkowy_al = float(al['stan_poczatkowy'] or 0)
                    live_usage_for_roll = max(live_total_pulled - already_logged, 0)
                    remaining = max(stan_poczatkowy_al - live_usage_for_roll, 0)
                    
                    carryover_qty += remaining
                    
                    # Close the old active link with stan_koncowy = remaining
                    cursor.execute(
                        "UPDATE agro_plan_opakowania SET stan_koncowy = %s, is_active = FALSE WHERE id = %s",
                        (remaining, al['link_id'])
                    )
                    
                    # Log to settlement history (agro_workowanie_rozliczenie)
                    zuzycie_al = max(stan_poczatkowy_al - remaining, 0)
                    cursor.execute("SELECT data_planu, produkt FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
                    p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}
                    cursor.execute("""
                        INSERT INTO agro_workowanie_rozliczenie (
                            plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                            stan_przed, zuzyte_worki, stan_po, autor_login
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        plan_id, p_meta['data_planu'], p_meta['produkt'], al['opakowanie_id'], al['nazwa'],
                        stan_poczatkowy_al, zuzycie_al, remaining, user_login or 'System'
                    ))
                    
                    # Move to history table and delete from current
                    cursor.execute(
                        "INSERT INTO magazyn_opakowania_historia (oryginalny_id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia) "
                        "SELECT id, nr_palety, nazwa, 0, 'ZUŻYTE', nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia "
                        "FROM magazyn_opakowania WHERE id = %s",
                        (al['opakowanie_id'],)
                    )
                    cursor.execute("DELETE FROM magazyn_opakowania WHERE id = %s", (al['opakowanie_id'],))
                else:
                    # Different material: close it with 0 left and ZUŻYTE
                    stan_poczatkowy_al = float(al['stan_poczatkowy'] or 0)
                    cursor.execute(
                        "UPDATE agro_plan_opakowania SET stan_koncowy = 0, is_active = FALSE WHERE id = %s",
                        (al['link_id'],)
                    )
                    
                    cursor.execute("SELECT data_planu, produkt FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
                    p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}
                    cursor.execute("""
                        INSERT INTO agro_workowanie_rozliczenie (
                            plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                            stan_przed, zuzyte_worki, stan_po, autor_login
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        plan_id, p_meta['data_planu'], p_meta['produkt'], al['opakowanie_id'], al['nazwa'],
                        stan_poczatkowy_al, stan_poczatkowy_al, 0.0, user_login or 'System'
                    ))
                    
                    cursor.execute(
                        "INSERT INTO magazyn_opakowania_historia (oryginalny_id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia) "
                        "SELECT id, nr_palety, nazwa, 0, 'ZUŻYTE', nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia "
                        "FROM magazyn_opakowania WHERE id = %s",
                        (al['opakowanie_id'],)
                    )
                    cursor.execute("DELETE FROM magazyn_opakowania WHERE id = %s", (al['opakowanie_id'],))
            
            # Oblicz pobraną ilość (jeśli podano ułamek, to traktujemy jako część)
            ilosc_docelowa = stan_poczatkowy_nowego
            if ilosc_pobrana is not None:
                try:
                    ilosc_docelowa = float(ilosc_pobrana)
                except:
                    pass
                    
            target_opakowanie_id = opakowanie_id
            
            # Odczytaj aktualny licznik MQTT przy wsadzeniu rolki
            mqtt_licznik_start = 0
            try:
                from app.services.mqtt_service import get_latest_data
                mqtt_licznik_start = int(get_latest_data().get('counter', 0) or 0)
            except Exception:
                pass

            if 0 < ilosc_docelowa < stan_poczatkowy_nowego:
                # Rozdzielenie partii (utworzenie nowego rekordu dla maszyny, zostawienie reszty na starym)
                stan_pozostaly = stan_poczatkowy_nowego - ilosc_docelowa
                # Aktualizacja starego rekordu — odejmij pobraną ilość ze stanu magazynowego
                cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s WHERE id = %s", (stan_pozostaly, opakowanie_id))

                # Utworzenie nowego rekordu (ilość pobrana + carryover) — nowy wpis reprezentuje rolkę na maszynie
                ilosc_na_maszyne = ilosc_docelowa + carryover_qty
                cursor.execute(
                    "INSERT INTO magazyn_opakowania (nazwa, stan_magazynowy, lokalizacja) VALUES (%s, %s, %s)",
                    (nazwa, ilosc_na_maszyne, 'Maszyna')
                )
                target_opakowanie_id = cursor.lastrowid

                # FIX: Zapis ruchu POBRANIE_DO_PRODUKCJI (odejmuje ze stanu magazynowego)
                table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                try:
                    cursor.execute(
                        f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                        "VALUES (%s, 'POBRANIE_DO_PRODUKCJI', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                        (opakowanie_id, -ilosc_docelowa, stan_pozostaly, user_login or 'System',
                         f"Pobranie folii na produkcję AGRO (podział z lok: {lokalizacja}) plan #{plan_id}")
                    )
                    komentarz_pobrania = f"Wsadzenie rolki z lok: {lokalizacja}"
                    if carryover_qty > 0:
                        komentarz_pobrania += f" (w tym carryover {int(carryover_qty)} szt. z poprzedniej rolki)"
                    cursor.execute(
                        f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                        "VALUES (%s, 'POBRANIE_NA_MASZYNE', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                        (target_opakowanie_id, ilosc_na_maszyne, ilosc_na_maszyne, user_login or 'System', komentarz_pobrania)
                    )
                except Exception as ex:
                    print(f"Error logging partial move: {ex}")

                stan_poczatkowy_plan = ilosc_na_maszyne
            else:
                # Brak podziału — sprawdzamy czy już podpięte
                cursor.execute("SELECT id FROM agro_plan_opakowania WHERE plan_id = %s AND opakowanie_id = %s AND is_active = TRUE", (plan_id, target_opakowanie_id))
                if cursor.fetchone(): return True, "Już podpięte"

                stan_w_magazynie_przed = stan_poczatkowy_nowego
                ilosc_na_maszyne = stan_poczatkowy_nowego + carryover_qty

                # FIX: Odejmij całą rolkę ze stanu magazynowego (stan = 0, lokal = Maszyna)
                cursor.execute(
                    "UPDATE magazyn_opakowania SET stan_magazynowy = 0, lokalizacja = 'Maszyna' WHERE id = %s",
                    (target_opakowanie_id,)
                )

                table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                try:
                    # FIX: Ruch POBRANIE_DO_PRODUKCJI — poprawnie zmniejsza stan magazynowy
                    cursor.execute(
                        f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                        "VALUES (%s, 'POBRANIE_DO_PRODUKCJI', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                        (target_opakowanie_id, -stan_w_magazynie_przed, 0, user_login or 'System',
                         f"Pobranie folii na produkcję AGRO (lok: {lokalizacja}) plan #{plan_id}")
                    )
                    komentarz_pobrania = f"Wsadzenie rolki z lok: {lokalizacja}"
                    if carryover_qty > 0:
                        komentarz_pobrania += f" (w tym carryover {int(carryover_qty)} szt. z poprzedniej rolki)"
                    cursor.execute(
                        f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                        "VALUES (%s, 'POBRANIE_NA_MASZYNE', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                        (target_opakowanie_id, ilosc_na_maszyne, ilosc_na_maszyne, user_login or 'System', komentarz_pobrania)
                    )
                except Exception as ex:
                    print(f"Error logging full pull move: {ex}")

                stan_poczatkowy_plan = ilosc_na_maszyne
                
            # 3. Link — zapisz licznik MQTT przy wsadzeniu
            cursor.execute(
                "INSERT INTO agro_plan_opakowania (plan_id, opakowanie_id, stan_poczatkowy, is_active, licznik_start) VALUES (%s, %s, %s, TRUE, %s)",
                (plan_id, target_opakowanie_id, stan_poczatkowy_plan, mqtt_licznik_start)
            )
            new_link_id = cursor.lastrowid

            # Log wsadzenia rolki w agro_workowanie_rozliczenie
            cursor.execute("SELECT data_planu, produkt FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
            p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}
            cursor.execute("""
                INSERT INTO agro_workowanie_rozliczenie (
                    plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                    stan_przed, zuzyte_worki, stan_po, autor_login,
                    typ_zdarzenia, licznik_start, link_id
                ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, 'WSADZENIE', %s, %s)
            """, (
                plan_id, p_meta['data_planu'], p_meta['produkt'], target_opakowanie_id, nazwa,
                stan_poczatkowy_plan, stan_poczatkowy_plan, user_login or 'System',
                mqtt_licznik_start, new_link_id
            ))
            
            conn.commit()
            return True, None
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def return_packaging_from_machine(opakowanie_id, stan_po, lokalizacja, user_login, is_partial=False, print_label=False):
        """Return a roll from machine back to warehouse.

        If `is_partial` is True, `stan_po` means quantity returned to warehouse.
        Otherwise `stan_po` means quantity left on the returned roll.
        """
        print_result = {'requested': bool(print_label), 'success': False, 'message': None}
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            try:
                numeric_val = float(stan_po) if (stan_po is not None and str(stan_po).strip() != '') else 0.0
            except (ValueError, TypeError):
                numeric_val = 0.0

            final_loc = lokalizacja if (lokalizacja and lokalizacja.strip()) else ('ZUŻYTE' if (not is_partial and numeric_val <= 0) else 'Maszyna')

            cursor.execute("SELECT nazwa, stan_magazynowy FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
            opak_row = cursor.fetchone()
            if not opak_row:
                return False, "Opakowanie nie istnieje", {'print_result': print_result}
            opak_nazwa = opak_row['nazwa']
            aktualny_stan_maszyna = float(opak_row['stan_magazynowy'])

            cursor.execute(
                """
                SELECT id, plan_id, stan_poczatkowy
                FROM agro_plan_opakowania
                WHERE opakowanie_id = %s AND is_active = TRUE
                ORDER BY created_at DESC LIMIT 1
                """,
                (opakowanie_id,),
            )
            link = cursor.fetchone()

            if is_partial:
                ilosc_zwracana = numeric_val
                if ilosc_zwracana <= 0:
                    return False, "Ilość zwracana musi być większa od 0", {'print_result': print_result}

                nowy_stan_maszyna = aktualny_stan_maszyna - ilosc_zwracana
                if nowy_stan_maszyna < 0:
                    nowy_stan_maszyna = 0
                cursor.execute(
                    "UPDATE magazyn_opakowania SET stan_magazynowy = %s, updated_at = NOW() WHERE id = %s",
                    (nowy_stan_maszyna, opakowanie_id),
                )

                if link:
                    nowy_stan_poczatkowy = float(link['stan_poczatkowy']) - ilosc_zwracana
                    cursor.execute(
                        "UPDATE agro_plan_opakowania SET stan_poczatkowy = %s WHERE id = %s",
                        (nowy_stan_poczatkowy, link['id']),
                    )

                cursor.execute(
                    "SELECT id, stan_magazynowy FROM magazyn_opakowania WHERE nazwa = %s AND lokalizacja = %s LIMIT 1",
                    (opak_nazwa, final_loc),
                )
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        "UPDATE magazyn_opakowania SET stan_magazynowy = stan_magazynowy + %s, updated_at = NOW() WHERE id = %s",
                        (ilosc_zwracana, existing['id']),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO magazyn_opakowania (nazwa, stan_magazynowy, lokalizacja, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
                        (opak_nazwa, ilosc_zwracana, final_loc),
                    )

                table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                cursor.execute(
                    f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                    "VALUES (%s, 'CZESCIOWY_ZWROT', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                    (opakowanie_id, ilosc_zwracana, nowy_stan_maszyna, user_login, f"Częściowy zwrot na lok: {final_loc}"),
                )

                ilosc_przy_zwrocie = ilosc_zwracana
                pozostalo_na_rolce = nowy_stan_maszyna
            else:
                final_stan = numeric_val
                cursor.execute(
                    "UPDATE magazyn_opakowania SET stan_magazynowy = %s, lokalizacja = %s, updated_at = NOW() WHERE id = %s",
                    (final_stan, final_loc, opakowanie_id),
                )

                if link:
                    plan_id = link['plan_id']
                    stan_przed = float(link['stan_poczatkowy'])
                    zuzycie = max(stan_przed - final_stan, 0)

                    cursor.execute(
                        "UPDATE agro_plan_opakowania SET stan_koncowy = %s, is_active = FALSE WHERE id = %s",
                        (final_stan, link['id']),
                    )

                    cursor.execute(f"SELECT data_planu, produkt FROM {get_table_name('plan_produkcji', 'AGRO')} WHERE id = %s", (plan_id,))
                    p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}

                    cursor.execute(
                        """
                        INSERT INTO agro_workowanie_rozliczenie (
                            plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                            stan_przed, zuzyte_worki, stan_po, autor_login
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            plan_id,
                            p_meta['data_planu'],
                            p_meta['produkt'],
                            opakowanie_id,
                            opak_nazwa,
                            stan_przed,
                            zuzycie,
                            final_stan,
                            user_login,
                        ),
                    )

                table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                cursor.execute(
                    f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                    "VALUES (%s, 'ZWROT_Z_MASZYNY', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                    (opakowanie_id, 0, final_stan, user_login, f"Pełny zwrot na lok: {final_loc}"),
                )

                ilosc_przy_zwrocie = final_stan
                pozostalo_na_rolce = final_stan

            conn.commit()
        except Exception as e:
            conn.rollback()
            return False, str(e), {'print_result': print_result}
        finally:
            conn.close()

        return_label = {
            'opakowanie_id': opakowanie_id,
            'opakowanie_nazwa': opak_nazwa,
            'ilosc_przy_zwrocie': ilosc_przy_zwrocie,
            'pozostalo_na_rolce': pozostalo_na_rolce,
            'lokalizacja': final_loc,
            'data_odlozenia': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'odlozyl': user_login or 'System',
            'tryb_zwrotu': 'CZESCIOWY' if is_partial else 'CALKOWITY',
        }

        if print_result['requested']:
            try:
                ok, msg = AgroWarehouseService.print_packaging_return_label(return_label)
                print_result['success'] = bool(ok)
                print_result['message'] = msg
            except Exception as print_err:
                print_result['success'] = False
                print_result['message'] = str(print_err)
                logger.exception('Packaging return label print failed for opakowanie_id=%s: %s', opakowanie_id, print_err)

        return True, None, {'return_label': return_label, 'print_result': print_result}

    @staticmethod
    def build_packaging_return_label_zpl(label_data):
        """Build informational ZPL label for packaging returns."""
        opakowanie_nazwa = _sanitize_zpl_text(label_data.get('opakowanie_nazwa'), 58) or 'BRAK NAZWY'
        ilosc_przy_zwrocie = _format_quantity_label(label_data.get('ilosc_przy_zwrocie'))
        pozostalo_na_rolce = _format_quantity_label(label_data.get('pozostalo_na_rolce'))
        lokalizacja = _sanitize_zpl_text(label_data.get('lokalizacja'), 48) or 'BRAK'
        data_odlozenia = _sanitize_zpl_text(label_data.get('data_odlozenia'), 32) or datetime.now().strftime('%Y-%m-%d %H:%M')
        operator = _sanitize_zpl_text(label_data.get('odlozyl'), 36) or 'SYSTEM'
        tryb_zwrotu = _sanitize_zpl_text(label_data.get('tryb_zwrotu'), 16) or 'ZWROT'

        qr_payload = _sanitize_zpl_text(
            f"{opakowanie_nazwa}|{ilosc_przy_zwrocie}|{pozostalo_na_rolce}|{lokalizacja}|{data_odlozenia}|{operator}",
            160,
        )

        return f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,55^A0N,52,52^FDZWROT OPAKOWANIA^FS
^FO40,130^A0N,32,32^FDTRYB: {tryb_zwrotu}^FS
^FO40,185^A0N,44,44^FB720,2,0,L^FD{opakowanie_nazwa}^FS
^FO40,330^A0N,34,34^FDILOSC PRZY ZWROCIE: {ilosc_przy_zwrocie} szt^FS
^FO40,390^A0N,34,34^FDPOZOSTALO NA ROLCE: {pozostalo_na_rolce} szt^FS
^FO40,450^A0N,34,34^FDLOKALIZACJA: {lokalizacja}^FS
^FO40,510^A0N,34,34^FDDATA ODLOZENIA: {data_odlozenia}^FS
^FO40,570^A0N,34,34^FDODLOZYL: {operator}^FS
^FO470,690^BY3^BQN,2,7^FDLA,{qr_payload}^FS
^XZ"""

    @staticmethod
    def print_packaging_return_label(label_data):
        """Print informational packaging-return label via print bridge."""
        from app.services.print_server import get_printer

        candidate_printers = []
        seen_targets = set()

        def _append_candidate(name, ip):
            key = ((name or '').strip().lower(), (ip or '').strip().lower())
            if key in seen_targets:
                return
            seen_targets.add(key)
            candidate_printers.append((name, ip))

        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """
                    SELECT id, nazwa, ip
                    FROM drukarki
                    WHERE aktywna = 1
                    ORDER BY
                        CASE
                            WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                            WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                            ELSE 2
                        END,
                        id ASC
                    """
                )
                for row in cursor.fetchall() or []:
                    _append_candidate(row.get('nazwa'), row.get('ip'))
            finally:
                conn.close()
        except Exception as printer_cfg_err:
            logger.warning('Could not resolve preferred printer for packaging return label: %s', printer_cfg_err)

        printer = get_printer()
        zpl = AgroWarehouseService.build_packaging_return_label_zpl(label_data)

        # Last resort: use configured default printer from PrintServer.
        _append_candidate(None, None)

        last_message = 'Brak dostępnej drukarki'
        for idx, (override_name, override_ip) in enumerate(candidate_printers, start=1):
            ok, msg = printer.print_zpl_label(zpl, override_ip=override_ip, override_name=override_name)
            if ok:
                if idx > 1:
                    logger.info(
                        'Packaging return label printed via fallback printer (attempt=%s, printer=%s, ip=%s)',
                        idx,
                        override_name or printer.printer_name,
                        override_ip or printer.printer_ip,
                    )
                return True, msg

            last_message = msg
            logger.warning(
                'Packaging return label print attempt %s failed (printer=%s, ip=%s): %s',
                idx,
                override_name or printer.printer_name,
                override_ip or printer.printer_ip,
                msg,
            )

        return False, last_message

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
            cooldown_seconds = _get_auto_pallet_cooldown_seconds()
            
            # Optional cooldown can be used as an emergency guard against hardware bit flickering.
            if cooldown_seconds > 0:
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
                    if time_diff < cooldown_seconds:
                        logger.warning(
                            "[COOLDOWN] Skipped auto-registering pallet for plan_id=%s. "
                            "Last pallet added %.1fs ago (cooldown %.1fs).",
                            plan_id,
                            time_diff,
                            cooldown_seconds,
                        )
                        return False
            
            nr_palety = None
            paleta_id = None

            # Consume the oldest reserved label first, if available.
            cursor.execute(
                f"SELECT id, nr_palety FROM {table_pal} WHERE plan_id = %s AND COALESCE(status, '') = 'rezerwacja' ORDER BY id ASC LIMIT 1",
                (plan_id,),
            )
            reserved_row = cursor.fetchone()

            if reserved_row:
                paleta_id = reserved_row[0]
                nr_palety = reserved_row[1] or generate_pallet_id(linia)
                cursor.execute(
                    f"UPDATE {table_pal} SET waga = %s, tara = 25, waga_brutto = 0, data_dodania = %s, status = 'do_przyjecia', dodal_login = %s, nr_palety = %s WHERE id = %s",
                    (waga_input, now_ts, user_login, nr_palety, paleta_id),
                )
            else:
                nr_palety = generate_pallet_id(linia)
                cursor.execute(
                    f"INSERT INTO {table_pal} (plan_id, waga, tara, waga_brutto, data_dodania, status, dodal_login, nr_palety) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia', %s, %s)",
                    (plan_id, waga_input, now_ts, user_login, nr_palety),
                )
                paleta_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
            
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

            if paleta_id:
                try:
                    from app.utils.pallet_label import prepare_pallet_label_data
                    from app.services.print_server import get_printer

                    label_data = prepare_pallet_label_data(cursor, paleta_id, linia)
                    if not label_data:
                        logger.warning(
                            'System auto-print skipped: missing label data for paleta_id=%s (plan_id=%s, source=%s)',
                            paleta_id,
                            plan_id,
                            source_instance,
                        )
                    else:
                        printer = get_printer()
                        printer_row = _select_preferred_printer(cursor)
                        override_name = None
                        override_ip = None
                        if printer_row:
                            override_name = printer_row[1] if len(printer_row) > 1 else None
                            override_ip = printer_row[2] if len(printer_row) > 2 else None

                        for copy_num in range(1, 3):
                            ok, print_msg = printer.print_finished_product_label(
                                label_data,
                                override_ip=override_ip,
                                override_name=override_name,
                            )
                            logger.info(
                                'System auto-print copy %s/2 for paleta=%s (plan_id=%s, source=%s): success=%s, printer=%s, ip=%s, msg=%s',
                                copy_num,
                                nr_palety,
                                plan_id,
                                source_instance,
                                ok,
                                override_name or printer.printer_name,
                                override_ip or printer.printer_ip,
                                print_msg,
                            )
                            if not ok:
                                break
                except Exception as print_err:
                    logger.error(
                        'System auto-print failed for paleta=%s (plan_id=%s, source=%s): %s',
                        nr_palety,
                        plan_id,
                        source_instance,
                        print_err,
                    )
                
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
            
            # Delete corresponding "wsadzenie" (where zuzyte_worki = 0)
            cursor.execute("""
                DELETE FROM agro_workowanie_rozliczenie 
                WHERE plan_id = %s AND opakowanie_id = %s AND zuzyte_worki = 0
            """, (row['plan_id'], row['opakowanie_id']))
            
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
            
            # Delete corresponding history records from agro_workowanie_rozliczenie (except the "wsadzenie" row where zuzyte_worki = 0)
            cursor.execute("DELETE FROM agro_workowanie_rozliczenie WHERE plan_id = %s AND opakowanie_id = %s AND zuzyte_worki > 0", (plan_id, opakowanie_id))
            
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

