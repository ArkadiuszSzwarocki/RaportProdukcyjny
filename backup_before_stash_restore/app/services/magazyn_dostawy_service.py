from app.db import get_db_connection, get_table_name
import json
from datetime import datetime
import uuid
import re

class MagazynDostawyService:
    RACK_PATTERN = re.compile(r'^R\d{2}\d{2}\d{2}$')
    RACK_PREFIX_PATTERN = re.compile(r'^R\d{0,6}$')
    BASE_LOCATIONS = [
        'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02',
        'OSIP', 'BF_MS01', 'BF_MP01', 'KO01', 'PSD',
        'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP', 'PSD01', 'MD01'
    ]

    @staticmethod
    def get_dostawy(linia='PSD'):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_dostawy WHERE linia = %s ORDER BY created_at DESC",
                (linia,)
            )
            dostawy = cursor.fetchall()
            for d in dostawy:
                if d.get('items'):
                    try:
                        d['items_parsed'] = json.loads(d['items'])
                    except Exception:
                        d['items_parsed'] = []
            return dostawy
        finally:
            conn.close()

    @staticmethod
    def get_oczekujace(linia='PSD'):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_dostawy WHERE status = 'OCZEKUJE' ORDER BY created_at DESC"
            )
            dostawy = cursor.fetchall()
            for d in dostawy:
                if d.get('items'):
                    try:
                        d['items_parsed'] = json.loads(d['items'])
                    except Exception:
                        d['items_parsed'] = []
            return dostawy
        finally:
            conn.close()

    @staticmethod
    def get_raport(date_from=None, date_to=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM magazyn_dostawy WHERE status = 'COMPLETED'"
            params = []
            if date_from:
                query += " AND DATE(created_at) >= %s"
                params.append(date_from)
            if date_to:
                query += " AND DATE(created_at) <= %s"
                params.append(date_to)
            query += " ORDER BY created_at DESC"
            cursor.execute(query, params)
            dostawy = cursor.fetchall()
            for d in dostawy:
                if d.get('created_at'):
                    d['created_at'] = d['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                if d.get('potwierdzone_at'):
                    d['potwierdzone_at'] = d['potwierdzone_at'].strftime('%Y-%m-%d %H:%M:%S')
                if d.get('items'):
                    try:
                        d['items_parsed'] = json.loads(d['items'])
                    except Exception:
                        d['items_parsed'] = []
            return dostawy
        finally:
            conn.close()

    @staticmethod
    def save_dostawa(data, login='system'):
        linia = data.get('linia', 'PSD').upper()
        dostawa_id = data.get('id') or str(uuid.uuid4())[:18]
        order_ref = data.get('order_ref') or data.get('orderRef', '')
        supplier = data.get('supplier', '')
        delivery_date = data.get('delivery_date') or data.get('deliveryDate', datetime.now().strftime('%Y-%m-%d'))
        items = data.get('items', [])
        status = data.get('status', 'OCZEKUJE')
        lokalizacja_z = str(data.get('lokalizacja_z', '') or '').strip().upper()
        lokalizacja_do = str(data.get('lokalizacja_do', '') or '').strip().upper()

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            exists = cursor.fetchone()

            if exists:
                cursor.execute("""
                    UPDATE magazyn_dostawy
                    SET order_ref=%s, delivery_date=%s, status=%s, items=%s,
                        lokalizacja_z=%s, lokalizacja_do=%s
                    WHERE id=%s
                """, (order_ref, delivery_date, status, json.dumps(items),
                      lokalizacja_z, lokalizacja_do, dostawa_id))
            else:
                cursor.execute("""
                    INSERT INTO magazyn_dostawy
                        (id, order_ref, supplier, delivery_date, status, items,
                         created_by, created_at, requires_lab, linia,
                         lokalizacja_z, lokalizacja_do)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (dostawa_id, order_ref, supplier, delivery_date, status,
                      json.dumps(items), login, datetime.now(), 0, linia,
                      lokalizacja_z, lokalizacja_do))

            conn.commit()
            return True, dostawa_id
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def accept_item(dostawa_id, item_id, lokalizacja, login='system'):
        conn = get_db_connection()
        try:
            lokalizacja = str(lokalizacja or '').strip().upper()
            if not lokalizacja:
                return False, "Podaj lokalizację.", None

            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa: return False, "Nie znaleziono przesunięcia", None

            items = json.loads(dostawa['items'] or '[]')
            linia = dostawa['linia']
            target = next((i for i in items if i.get('id') == item_id), None)
            if not target: return False, "Nie znaleziono pozycji", None
            if target.get('accepted'): return False, "Pozycja już przyjęta", None

            table_sur = get_table_name('magazyn_surowce', linia)
            table_opk = get_table_name('magazyn_opakowania', linia)

            cursor.execute(f"SELECT 1 FROM {table_sur} WHERE UPPER(lokalizacja) = %s AND stan_magazynowy > 0", (lokalizacja,))
            if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w surowcach!", None
            cursor.execute(f"SELECT 1 FROM {table_opk} WHERE UPPER(lokalizacja) = %s AND stan_magazynowy > 0", (lokalizacja,))
            if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w opakowaniach!", None

            product_name = target.get('productName') or 'Brak nazwy'
            if target.get('packageForm') == 'packaging':
                qty = float(target.get('unitsPerPallet') or 0)
                cursor.execute(f"INSERT INTO {table_opk} (nazwa, stan_magazynowy, lokalizacja) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa)", (product_name, qty, lokalizacja))
            else:
                qty = float(target.get('netWeight') or 0)
                cursor.execute(f"INSERT INTO {table_sur} (nazwa, stan_magazynowy, lokalizacja) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa)", (product_name, qty, lokalizacja))

            target['accepted'] = True
            target['accepted_by'] = login
            target['accepted_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            target['lokalizacja_przyjecia'] = lokalizacja

            all_accepted = all(i.get('accepted') for i in items)
            new_status = 'COMPLETED' if all_accepted else 'OCZEKUJE'

            cursor.execute("UPDATE magazyn_dostawy SET items=%s, status=%s, potwierdzone_przez=%s, potwierdzone_at=%s WHERE id=%s", (json.dumps(items), new_status, login if all_accepted else dostawa.get('potwierdzone_przez'), datetime.now() if all_accepted else dostawa.get('potwierdzone_at'), dostawa_id))
            conn.commit()
            
            return True, "", {
                "all_accepted": all_accepted,
                "accepted_count": sum(1 for i in items if i.get('accepted')),
                "total": len(items)
            }
        except Exception as e:
            return False, str(e), None
        finally:
            conn.close()

    @staticmethod
    def check_location(lokalizacja, linia='PSD'):
        lokalizacja = str(lokalizacja or '').strip().upper()
        if not lokalizacja:
            return False, "", []

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_sur = get_table_name('magazyn_surowce', linia)
            table_opk = get_table_name('magazyn_opakowania', linia)
            cursor.execute(f"SELECT nazwa, stan_magazynowy, 'Surowiec' as typ FROM {table_sur} WHERE UPPER(lokalizacja) = %s AND stan_magazynowy > 0", (lokalizacja,))
            items_sur = cursor.fetchall()
            cursor.execute(f"SELECT nazwa, stan_magazynowy, 'Opakowanie' as typ FROM {table_opk} WHERE UPPER(lokalizacja) = %s AND stan_magazynowy > 0", (lokalizacja,))
            items_opk = cursor.fetchall()
            all_items = items_sur + items_opk
            if all_items:
                content_desc = ", ".join([f"{i['nazwa']} ({i['stan_magazynowy']})" for i in all_items])
                return True, content_desc, all_items
            return False, "", []
        finally:
            conn.close()

    @staticmethod
    def _generate_rack_locations():
        # Format regału: R + regał(2) + rząd(2) + miejsce(2), np. R030109
        locations = []
        for rack in range(1, 8):
            for row in range(1, 4):
                for place in range(1, 11):
                    locations.append(f"R{rack:02d}{row:02d}{place:02d}")
        return locations

    @staticmethod
    def _get_occupied_locations(cursor, linia='PSD'):
        occupied = set()
        table_sur = get_table_name('magazyn_surowce', linia)
        table_opk = get_table_name('magazyn_opakowania', linia)

        cursor.execute(
            f"SELECT DISTINCT UPPER(TRIM(lokalizacja)) AS lokalizacja FROM {table_sur} "
            "WHERE COALESCE(TRIM(lokalizacja), '') <> '' AND COALESCE(stan_magazynowy, 0) > 0"
        )
        for row in cursor.fetchall():
            loc = row.get('lokalizacja')
            if loc:
                occupied.add(loc)

        cursor.execute(
            f"SELECT DISTINCT UPPER(TRIM(lokalizacja)) AS lokalizacja FROM {table_opk} "
            "WHERE COALESCE(TRIM(lokalizacja), '') <> '' AND COALESCE(stan_magazynowy, 0) > 0"
        )
        for row in cursor.fetchall():
            loc = row.get('lokalizacja')
            if loc:
                occupied.add(loc)

        # Dodatki i wyroby gotowe mogą współdzielić przestrzeń lokalizacji.
        optional_sources = [
            ('magazyn_dodatki', 'stan_magazynowy'),
            ('magazyn_palety', 'waga_netto'),
        ]
        for base_table, qty_col in optional_sources:
            try:
                table_name = get_table_name(base_table, linia)
                cursor.execute(
                    f"SELECT DISTINCT UPPER(TRIM(lokalizacja)) AS lokalizacja FROM {table_name} "
                    f"WHERE COALESCE(TRIM(lokalizacja), '') <> '' AND COALESCE({qty_col}, 0) > 0"
                )
                for row in cursor.fetchall():
                    loc = row.get('lokalizacja')
                    if loc:
                        occupied.add(loc)
            except Exception:
                continue

        return occupied

    @staticmethod
    def suggest_locations(prefix='', linia='PSD', limit=40):
        normalized_prefix = str(prefix or '').strip().upper()
        rack_locations = MagazynDostawyService._generate_rack_locations()

        static_locations = set(MagazynDostawyService.BASE_LOCATIONS)
        static_locations.update([f"OS{idx:02d}" for idx in range(1, 78)])
        static_locations.update([f"BB{idx:02d}" for idx in range(1, 25)])
        static_locations.update([f"MZ{idx:02d}" for idx in range(1, 7)])
        static_locations.update(['MZ05-01', 'MZ06-01'])

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            # Uzupełniamy pulę o realnie istniejące lokalizacje z DB.
            for base_table, qty_col in [
                ('magazyn_surowce', 'stan_magazynowy'),
                ('magazyn_opakowania', 'stan_magazynowy'),
                ('magazyn_dodatki', 'stan_magazynowy'),
                ('magazyn_palety', 'waga_netto'),
            ]:
                try:
                    table_name = get_table_name(base_table, linia)
                    cursor.execute(
                        f"SELECT DISTINCT UPPER(TRIM(lokalizacja)) AS lokalizacja FROM {table_name} "
                        f"WHERE COALESCE(TRIM(lokalizacja), '') <> '' AND COALESCE({qty_col}, 0) >= 0"
                    )
                    for row in cursor.fetchall():
                        loc = row.get('lokalizacja')
                        if loc:
                            static_locations.add(loc)
                except Exception:
                    continue

            is_rack_query = bool(
                normalized_prefix.startswith('R') and
                MagazynDostawyService.RACK_PREFIX_PATTERN.match(normalized_prefix)
            )

            if is_rack_query:
                occupied = MagazynDostawyService._get_occupied_locations(cursor, linia)
                candidates = [
                    loc for loc in rack_locations
                    if loc.startswith(normalized_prefix)
                    and loc not in occupied
                ]
            else:
                candidates = [
                    loc for loc in static_locations
                    if loc.startswith(normalized_prefix)
                ]

            candidates = sorted(candidates, key=lambda x: (len(x), x))
            return candidates[:max(1, int(limit or 40))]
        finally:
            conn.close()
