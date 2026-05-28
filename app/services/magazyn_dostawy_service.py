from app.db import get_db_connection, get_table_name
import json
from datetime import datetime
import uuid
import re
from app.utils.pallet_id import generate_pallet_id

class MagazynDostawyService:
    OPEN_LOCATIONS_PREFIXES = ['MS01', 'MP01', 'MD01', 'MOP01', 'BF_MS01', 'BF_MP01', 'MDM01', 'PSD01']

    @staticmethod
    def _derive_target_zone(location):
        normalized = MagazynDostawyService._normalize_location_code(location)
        if not normalized:
            return ''

        for prefix in sorted(MagazynDostawyService.OPEN_LOCATIONS_PREFIXES, key=len, reverse=True):
            if normalized.startswith(prefix):
                return prefix

        if '_' in normalized:
            return normalized.split('_', 1)[0]
        if '-' in normalized:
            return normalized.split('-', 1)[0]

        match = re.match(r'^([A-Z]+\d{2})', normalized)
        if match:
            return match.group(1)

        return normalized[:4]

    @staticmethod
    def get_dostawy(linia='PSD'):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if str(linia).upper() == 'ALL':
                cursor.execute("SELECT * FROM magazyn_dostawy ORDER BY created_at DESC")
            else:
                cursor.execute(
                    "SELECT * FROM magazyn_dostawy WHERE UPPER(linia) = %s ORDER BY created_at DESC",
                    (str(linia).upper(),)
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
            # 1. Pending Raw Materials / Transfers
            if str(linia).upper() == 'ALL':
                cursor.execute(
                    "SELECT * FROM magazyn_dostawy WHERE status = 'OCZEKUJE' ORDER BY created_at DESC"
                )
            else:
                cursor.execute(
                    "SELECT * FROM magazyn_dostawy WHERE status = 'OCZEKUJE' AND UPPER(linia) = %s ORDER BY created_at DESC",
                    (str(linia).upper(),)
                )
            dostawy = cursor.fetchall()
            for d in dostawy:
                if d.get('items'):
                    try: d['items_parsed'] = json.loads(d['items'])
                    except Exception: d['items_parsed'] = []
            
            # 2. Pending Production Pallets (WG)
            wg = MagazynDostawyService.get_pending_production_pallets(linia)
            
            return {
                "dostawy": dostawy,
                "wg": wg
            }
        finally:
            conn.close()

    @staticmethod
    def get_pending_production_pallets(linia='PSD'):
        """Fetches pallets with status 'do_przyjecia' from production tables."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            normalized_line = str(linia or 'PSD').upper()
            is_psd = normalized_line == 'PSD'
            table_prod = 'palety_workowanie' if is_psd else 'palety_agro'
            table_plan = 'plan_produkcji' if is_psd else 'plan_produkcji_agro'
            table_wh = 'magazyn_palety' if is_psd else 'magazyn_palety_agro'
            plan_product_col = 'plan.produkt'
            
            # Check if table exists (safety)
            cursor.execute("SHOW TABLES LIKE %s", (table_prod,))
            if not cursor.fetchone():
                return []

            cursor.execute("SHOW TABLES LIKE %s", (table_wh,))
            has_wh_table = bool(cursor.fetchone())

            suggested_location_sql = "''"
            if has_wh_table:
                suggested_location_sql = (
                    f"COALESCE((SELECT w.lokalizacja FROM {table_wh} w "
                    f"WHERE w.produkt = {plan_product_col} "
                    "AND w.lokalizacja IS NOT NULL AND w.lokalizacja <> '' "
                    "ORDER BY COALESCE(w.data_potwierdzenia, w.created_at, w.id) DESC LIMIT 1), '')"
                )

            query = f"""
                SELECT p.*, plan.produkt as nazwa_produktu, 
                       plan.nazwa_zlecenia as numer_zlecenia,
                       {suggested_location_sql} AS suggested_location
                FROM {table_prod} p
                LEFT JOIN {table_plan} plan ON p.plan_id = plan.id
                WHERE p.status = 'do_przyjecia'
                ORDER BY p.data_dodania DESC
            """
            if is_psd:
                query = f"""
                    SELECT p.*, plan.produkt as nazwa_produktu,
                           plan.nazwa_zlecenia as numer_zlecenia,
                           {suggested_location_sql} AS suggested_location
                    FROM {table_prod} p
                    LEFT JOIN {table_plan} plan ON p.plan_id = plan.id
                    WHERE p.status = 'do_przyjecia'
                    ORDER BY p.data_dodania DESC
                """

            cursor.execute(query)
            rows = cursor.fetchall()
            for row in rows:
                suggested_location = MagazynDostawyService._normalize_location_code(row.get('suggested_location'))
                row['suggested_location'] = suggested_location
                row['target_zone'] = MagazynDostawyService._derive_target_zone(suggested_location)
            return rows
        except Exception as e:
            print(f"Error fetching pending production pallets: {e}")
            return []
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
            
            # For backfilling missing nr_palety in old reports
            table_sur_psd = get_table_name('magazyn_surowce', 'PSD')
            table_opk_psd = get_table_name('magazyn_opakowania', 'PSD')
            table_sur_agro = get_table_name('magazyn_surowce', 'AGRO')
            table_opk_agro = get_table_name('magazyn_opakowania', 'AGRO')

            for d in dostawy:
                if d.get('created_at'):
                    d['created_at'] = d['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                if d.get('potwierdzone_at'):
                    d['potwierdzone_at'] = d['potwierdzone_at'].strftime('%Y-%m-%d %H:%M:%S')
                if d.get('items'):
                    try:
                        its = json.loads(d['items'])
                        linia = d.get('linia', 'PSD').upper()
                        t_sur = table_sur_agro if linia == 'AGRO' else table_sur_psd
                        t_opk = table_opk_agro if linia == 'AGRO' else table_opk_psd

                        for item in its:
                            if not item.get('nr_palety'):
                                # Try to find it in DB by last known location/product
                                loc = item.get('lokalizacja_przyjecia')
                                name = item.get('productName')
                                if loc and name:
                                    cursor.execute(f"SELECT nr_palety FROM {t_sur} WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0 LIMIT 1", (loc, name))
                                    res = cursor.fetchone()
                                    if not res:
                                        cursor.execute(f"SELECT nr_palety FROM {t_opk} WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0 LIMIT 1", (loc, name))
                                        res = cursor.fetchone()
                                    if res:
                                        item['nr_palety'] = res['nr_palety']
                        d['items_parsed'] = its
                    except Exception as e:
                        print(f"Error parsing items in raport: {e}")
                        d['items_parsed'] = []
            return dostawy
        finally:
            conn.close()

    @staticmethod
    def save_dostawa(data, login='system'):
        def _norm_loc(value):
            return str(value or '').strip().upper()

        def _as_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on', 'tak')

        def _is_route_conflict(source_loc, target_loc):
            source = _norm_loc(source_loc)
            target = _norm_loc(target_loc)
            if not source or not target:
                return False
            if source == target:
                return True
            return source.startswith(target) or target.startswith(source)

        known_source_locations = {
            'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02',
            'OSIP', 'BF_MS01', 'BF_MP01', 'PSD', 'PSD01',
            'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP',
        }
        known_source_locations.update({f'KO{i:02d}' for i in range(1, 23)})
        known_target_locations = {'BF_MS01', 'BF_MP01', 'MS01', 'MP01', 'PSD01'}

        def _is_known_source_location(value):
            loc = _norm_loc(value)
            if not loc:
                return False

            if loc in known_source_locations:
                return True

            rack_match = re.match(r'^R0([1-7])(\d{2})(\d{2})$', loc)
            if rack_match:
                return True

            osip_match = re.match(r'^OS(\d{2})$', loc)
            if osip_match:
                nr = int(osip_match.group(1))
                return 1 <= nr <= 77

            bb_match = re.match(r'^BB(\d{2})$', loc)
            if bb_match:
                nr = int(bb_match.group(1))
                return 1 <= nr <= 24

            mz_simple = re.match(r'^MZ(\d{2})$', loc)
            if mz_simple:
                nr = int(mz_simple.group(1))
                return 1 <= nr <= 6

            ko_match = re.match(r'^KO(\d{2})$', loc)
            if ko_match:
                nr = int(ko_match.group(1))
                return 1 <= nr <= 22

            if loc.startswith('MD') or loc.startswith('MDO'):
                return True

            return loc in {'MZ05-01', 'MZ06-01'}

        linia = data.get('linia', 'PSD').upper()
        dostawa_id = data.get('id') or str(uuid.uuid4())[:18]
        order_ref = data.get('order_ref') or data.get('orderRef', '')
        supplier = data.get('supplier', '')
        delivery_date = data.get('delivery_date') or data.get('deliveryDate', datetime.now().strftime('%Y-%m-%d'))
        items = data.get('items', []) or []
        status = data.get('status', 'OCZEKUJE')
        lokalizacja_do = _norm_loc(data.get('lokalizacja_do', ''))
        global_skip_warehouse_lookup = _as_bool(data.get('skip_warehouse_lookup', data.get('skipWarehouseLookup', False)))

        source_locations = sorted({
            _norm_loc(it.get('sourceSpot'))
            for it in items
            if _norm_loc(it.get('sourceSpot'))
        })

        unknown_sources = sorted([loc for loc in source_locations if not _is_known_source_location(loc)])
        if unknown_sources:
            preview = ', '.join(unknown_sources[:5])
            suffix = ', ...' if len(unknown_sources) > 5 else ''
            return False, f"Nieznane lokalizacje źródłowe: {preview}{suffix}."

        lokalizacja_z = _norm_loc(data.get('lokalizacja_z', ''))
        if not lokalizacja_z and source_locations:
            lokalizacja_z = source_locations[0] if len(source_locations) == 1 else 'WIELE'

        if lokalizacja_do and lokalizacja_do not in known_target_locations:
            return False, f"Nieznana lokalizacja docelowa: {lokalizacja_do}."

        if lokalizacja_do and any(_is_route_conflict(loc, lokalizacja_do) for loc in source_locations):
            return False, f"Operacja niemożliwa: Skąd i Dokąd nie mogą być takie same ({lokalizacja_do})."

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT status, items, lokalizacja_z FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            old_data = cursor.fetchone()
            old_status = old_data['status'] if old_data else None
            old_items = json.loads(old_data['items']) if old_data and old_data.get('items') else []

            if old_data and old_status == 'OCZEKUJE' and old_data.get('lokalizacja_z'):
                return False, "Status OCZEKUJE: formularz wydania jest tylko do podglądu."

            # 1. Detect removed items from pending transfer to RESTORE them
            if old_status == 'OCZEKUJE' and items is not None:
                table_sur = get_table_name('magazyn_surowce', linia)
                table_opk = get_table_name('magazyn_opakowania', linia)
                new_ids = [str(it.get('id')) for it in items]
                for old_it in old_items:
                    if str(old_it.get('id')) not in new_ids:
                        # Item was removed! Restore it from buffer if it was buffered
                        curr_loc = _norm_loc(old_it.get('sourceSpot'))
                        orig_loc = _norm_loc(old_it.get('originalSpot'))
                        p_name = old_it.get('productName')
                        if curr_loc and orig_loc and curr_loc != orig_loc:
                            # Try restoring in surowce
                            cursor.execute(f"UPDATE {table_sur} SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (orig_loc, curr_loc, p_name))
                            restored = cursor.rowcount > 0
                            if not restored:
                                cursor.execute(f"UPDATE {table_opk} SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (orig_loc, curr_loc, p_name))
                                restored = cursor.rowcount > 0
                            
                            if restored:
                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'TRANSFER_CANCEL', %s, %s, %s, %s)",
                                    (None, linia, 'mix', curr_loc, orig_loc, f"Przywrócenie (usunięto z przesunięcia {order_ref})", login)
                                )

            # Process external delivery receptions
            is_external_reception = not lokalizacja_z
            if is_external_reception:
                table_sur = get_table_name('magazyn_surowce', linia)
                table_opk = get_table_name('magazyn_opakowania', linia)
                
                # Fetch printer info if printer_id is passed
                printer_id = data.get('printer_id')
                printer_ip = None
                printer_name = None
                if printer_id:
                    cursor.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s", (printer_id,))
                    printer_info = cursor.fetchone()
                    if printer_info:
                        printer_ip = printer_info['ip']
                        printer_name = printer_info['nazwa']
                
                for idx, item in enumerate(items):
                    if item.get('id') in (None, ''):
                        item['id'] = f"item_{idx}_{int(datetime.now().timestamp())}"
                    
                    if not item.get('nr_palety'):
                        p_type = 'opakowanie' if item.get('packageForm') == 'packaging' else 'surowiec'
                        item['nr_palety'] = generate_pallet_id(linia, type=p_type)
                    
                    # Ensure they are NOT accepted yet (they are pending Stage 2 confirmation!)
                    item['accepted'] = False
                    item.pop('accepted_by', None)
                    item.pop('accepted_at', None)
                    item.pop('lokalizacja_przyjecia', None)
                    
                    # Trigger printing for this pallet in the background!
                    if printer_ip and printer_name:
                        product_name = item.get('productName') or 'Brak nazwy'
                        nr_palety = item.get('nr_palety')
                        nr_partii = item.get('nr_partii')
                        data_produkcji = item.get('data_produkcji') or None
                        data_przydatnosci = item.get('data_przydatnosci') or None
                        
                        if item.get('packageForm') == 'packaging':
                            qty = float(item.get('quantity') or item.get('unitsPerPallet') or 0)
                            pallet_type = 'opakowanie'
                        else:
                            qty = float(item.get('quantity') or item.get('netWeight') or 0)
                            pallet_type = 'surowiec'
                        
                        try:
                            import threading
                            import requests
                            import urllib3
                            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                            payload = {
                                "drukarka": printer_name,
                                "ip": printer_ip,
                                "typ": pallet_type,
                                "dane": {
                                    "palletData": {
                                        "nrPalety": nr_palety,
                                        "productName": product_name,
                                        "batchNumber": nr_partii or '---',
                                        "productionDate": str(data_produkcji) if data_produkcji else '---',
                                        "expiryDate": str(data_przydatnosci) if data_przydatnosci else '---',
                                        "currentWeight": qty,
                                        "labNotes": "Dostawa Oczekująca"
                                    }
                                }
                            }
                            def run_print(p=payload):
                                url = "https://127.0.0.1:3001/drukuj-zpl"
                                for _ in range(2):
                                    try:
                                        requests.post(url, json=p, verify=False, timeout=3)
                                    except Exception:
                                        pass
                            threading.Thread(target=run_print, daemon=True).start()
                        except Exception as pe:
                            print(f"Błąd uruchomienia wątku drukowania: {pe}")
                
                # Status is always OCZEKUJE during creation/saving
                status = 'OCZEKUJE'

            if old_data:
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

            # 2. Handle automatic buffer move for Transfers
            if status == 'OCZEKUJE' and lokalizacja_do and source_locations:
                table_sur = get_table_name('magazyn_surowce', linia)
                table_opk = get_table_name('magazyn_opakowania', linia)
                updated_items = []
                used_request_nrs = set()
                used_request_ids = set()

                cursor.execute(
                    "SELECT id, items FROM magazyn_dostawy WHERE status = 'OCZEKUJE' AND linia = %s AND id <> %s",
                    (linia, dostawa_id)
                )
                other_pending = cursor.fetchall()
                reserved_other_nrs = set()
                reserved_other_ids = set()
                for pending in other_pending:
                    raw_items = pending.get('items')
                    if not raw_items:
                        continue
                    try:
                        pending_items = json.loads(raw_items)
                    except Exception:
                        continue
                    if not isinstance(pending_items, list):
                        continue

                    for pit in pending_items:
                        if not isinstance(pit, dict):
                            continue
                        if pit.get('accepted'):
                            continue

                        pit_nr = _norm_loc(pit.get('sourcePalletNo') or pit.get('nr_palety'))
                        if pit_nr:
                            reserved_other_nrs.add(pit_nr)

                        pit_id = pit.get('sourcePalletId')
                        pit_type = str(pit.get('scannedType') or pit.get('type') or '').strip().lower()
                        if pit_id not in (None, '') and pit_type:
                            reserved_other_ids.add(f"{pit_type}:{pit_id}")
                
                for item in items:
                    source_spot = _norm_loc(item.get('sourceSpot'))
                    item_skip_lookup = bool(global_skip_warehouse_lookup)
                    if source_spot:
                        if _is_route_conflict(source_spot, lokalizacja_do):
                            return False, f"Operacja niemożliwa: paleta ma tę samą lokalizację źródłową i docelową ({lokalizacja_do})."

                        p_name = item.get('productName')
                        p_id = item.get('sourcePalletId')
                        p_nr = item.get('sourcePalletNo') or item.get('nr_palety')
                        p_nr_norm = _norm_loc(p_nr)
                        if p_nr_norm:
                            if p_nr_norm in used_request_nrs:
                                return False, f"Paleta {p_nr_norm} została dodana wielokrotnie w tym samym zleceniu."
                            if p_nr_norm in reserved_other_nrs:
                                return False, f"Paleta {p_nr_norm} jest już zarezerwowana w innym oczekującym przesunięciu."
                            used_request_nrs.add(p_nr_norm)
                        p_type = None
                        p_res = None

                        if p_id:
                            cursor.execute(f"SELECT id, nr_palety, stan_magazynowy FROM {table_sur} WHERE id = %s AND lokalizacja = %s AND stan_magazynowy > 0", (p_id, source_spot))
                            p_res = cursor.fetchone()
                            if p_res: p_type = 'surowiec'
                            else:
                                cursor.execute(f"SELECT id, nr_palety, stan_magazynowy FROM {table_opk} WHERE id = %s AND lokalizacja = %s AND stan_magazynowy > 0", (p_id, source_spot))
                                p_res = cursor.fetchone()
                                if p_res: p_type = 'opakowanie'
                                else:
                                    cursor.execute(f"SELECT id, nr_palety, stan_magazynowy FROM magazyn_dodatki WHERE id = %s AND lokalizacja = %s AND stan_magazynowy > 0", (p_id, source_spot))
                                    p_res = cursor.fetchone()
                                    if p_res: p_type = 'dodatek'

                        if not p_res and p_nr:
                            cursor.execute(f"SELECT id, nr_palety, stan_magazynowy FROM {table_sur} WHERE lokalizacja = %s AND nr_palety = %s AND stan_magazynowy > 0", (source_spot, p_nr))
                            p_res = cursor.fetchone()
                            if p_res: p_type = 'surowiec'
                            else:
                                cursor.execute(f"SELECT id, nr_palety, stan_magazynowy FROM {table_opk} WHERE lokalizacja = %s AND nr_palety = %s AND stan_magazynowy > 0", (source_spot, p_nr))
                                p_res = cursor.fetchone()
                                if p_res: p_type = 'opakowanie'
                                else:
                                    cursor.execute(f"SELECT id, nr_palety, stan_magazynowy FROM magazyn_dodatki WHERE lokalizacja = %s AND nr_palety = %s AND stan_magazynowy > 0", (source_spot, p_nr))
                                    p_res = cursor.fetchone()
                                    if p_res: p_type = 'dodatek'

                        if not p_res:
                            cursor.execute(f"SELECT id, nr_palety, stan_magazynowy FROM {table_sur} WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (source_spot, p_name))
                            p_res = cursor.fetchone()
                            if p_res: p_type = 'surowiec'
                            else:
                                cursor.execute(f"SELECT id, nr_palety, stan_magazynowy FROM {table_opk} WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (source_spot, p_name))
                                p_res = cursor.fetchone()
                                if p_res: p_type = 'opakowanie'
                                else:
                                    cursor.execute(f"SELECT id, nr_palety, stan_magazynowy FROM magazyn_dodatki WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (source_spot, p_name))
                                    p_res = cursor.fetchone()
                                    if p_res: p_type = 'dodatek'

                        if not p_res:
                            if item_skip_lookup:
                                item['originalSpot'] = item.get('originalSpot') or source_spot
                                item['warehouseLookupSkipped'] = True
                                updated_items.append(item)
                                continue
                            return False, f"Nie znaleziono palety do przesunięcia ({p_name}) ze źródła {source_spot}."

                        p_id = p_res['id']
                        p_nr = p_res.get('nr_palety') or p_nr
                        p_nr_norm = _norm_loc(p_nr)
                        if p_nr_norm in reserved_other_nrs:
                            return False, f"Paleta {p_nr_norm} jest już zarezerwowana w innym oczekującym przesunięciu."

                        resolved_id_key = f"{p_type}:{p_id}"
                        if resolved_id_key in used_request_ids:
                            return False, f"Paleta {p_nr_norm or p_id} została dodana wielokrotnie w tym samym zleceniu."
                        if resolved_id_key in reserved_other_ids:
                            return False, f"Paleta {p_nr_norm or p_id} jest już zarezerwowana w innym oczekującym przesunięciu."
                        used_request_ids.add(resolved_id_key)

                        if p_type == 'surowiec': target_table = table_sur
                        elif p_type == 'opakowanie': target_table = table_opk
                        else: target_table = 'magazyn_dodatki'
                        
                        pallet_weight = float(p_res.get('stan_magazynowy') or 0)
                        form_weight = float(item.get('netWeight') or item.get('unitsPerPallet') or 0)
                        
                        is_partial = form_weight < (pallet_weight - 0.001) # Tolerance for floating point
                        
                        if is_partial:
                            # Subtract from source, don't move location
                            cursor.execute(f"UPDATE {target_table} SET stan_magazynowy = stan_magazynowy - %s WHERE id = %s", (form_weight, p_id))
                            item['is_partial'] = True
                            # Location in 'item' will be buffer, but in DB source stays at source
                        else:
                            # Move whole pallet
                            cursor.execute(f"UPDATE {target_table} SET lokalizacja = %s WHERE id = %s", (lokalizacja_do, p_id))
                            item['is_partial'] = False

                        item['originalSpot'] = item.get('originalSpot') or source_spot
                        item['sourceSpot'] = lokalizacja_do
                        item.pop('warehouseLookupSkipped', None)
                        item['sourcePalletId'] = p_id
                        if p_nr:
                            item['sourcePalletNo'] = p_nr
                            item['nr_palety'] = p_nr
                        cursor.execute(
                            "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'TRANSFER_START', %s, %s, %s, %s)",
                            (p_id, linia, p_type, source_spot, lokalizacja_do, f"Przesunięcie {order_ref}: {source_spot} -> {lokalizacja_do}", login)
                        )
                    updated_items.append(item)
                
                # Update items with the transfer staging location
                cursor.execute("UPDATE magazyn_dostawy SET items=%s WHERE id=%s", (json.dumps(updated_items), dostawa_id))

            conn.commit()
            return True, dostawa_id
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def accept_item(dostawa_id, item_id, lokalizacja, login='system', nr_partii=None, data_produkcji=None, data_przydatnosci=None, printer_ip=None, printer_name=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa: return False, "Nie znaleziono przesunięcia", None

            lokalizacja = str(lokalizacja or '').strip().upper()
            if not lokalizacja:
                return False, "Podaj lokalizację odstawienia.", None

            items = json.loads(dostawa['items'] or '[]')
            linia = dostawa['linia']
            # Compare IDs as strings to avoid type mismatch (int/float from JSON vs string from request)
            target = next((i for i in items if str(i.get('id')) == str(item_id)), None)
            if not target: return False, "Nie znaleziono pozycji", None
            if target.get('accepted'): return False, "Pozycja już przyjęta", None
            if target.get('rejected'): return False, "Pozycja została odrzucona", None

            source_spot = str(target.get('sourceSpot') or '').strip().upper()
            if not source_spot:
                fallback_source = str(dostawa.get('lokalizacja_z') or '').strip().upper()
                if fallback_source and fallback_source != 'WIELE':
                    source_spot = fallback_source
            if source_spot and source_spot == lokalizacja:
                return False, f"Nie można przyjąć na tę samą lokalizację ({lokalizacja}), z której przyjmujesz.", None

            table_sur = get_table_name('magazyn_surowce', linia)
            table_opk = get_table_name('magazyn_opakowania', linia)

            open_locations = ['MS01', 'MP01', 'MD01', 'MOP01', 'BF_MS01', 'BF_MP01', 'MDM01', 'MD01', 'PSD01']
            is_open = any(lokalizacja.upper().startswith(ol) for ol in open_locations)

            if not is_open:
                cursor.execute(f"SELECT 1 FROM {table_sur} WHERE lokalizacja = %s AND stan_magazynowy > 0", (lokalizacja,))
                if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w surowcach!", None
                cursor.execute(f"SELECT 1 FROM {table_opk} WHERE lokalizacja = %s AND stan_magazynowy > 0", (lokalizacja,))
                if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w opakowaniach!", None

            product_name = target.get('productName') or 'Brak nazwy'
            # Reuse existing nr_palety if this was a transfer, otherwise generate new
            nr_palety = target.get('nr_palety') or generate_pallet_id(linia, type=('opakowanie' if target.get('packageForm') == 'packaging' else 'surowiec'))
            pkg_form = target.get('packageForm', 'bags') # bags or big_bag

            if target.get('packageForm') == 'packaging':
                qty = float(target.get('unitsPerPallet') or 0)
                cursor.execute(f"INSERT INTO {table_opk} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa), nr_partii = VALUES(nr_partii), data_produkcji = VALUES(data_produkcji), data_przydatnosci = VALUES(data_przydatnosci), nr_palety = VALUES(nr_palety), typ_opakowania = VALUES(typ_opakowania)", (product_name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form))
                p_type = 'opakowanie'
            else:
                qty = float(target.get('netWeight') or 0)
                cursor.execute(f"INSERT INTO {table_sur} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa), nr_partii = VALUES(nr_partii), data_produkcji = VALUES(data_produkcji), data_przydatnosci = VALUES(data_przydatnosci), nr_palety = VALUES(nr_palety), typ_opakowania = VALUES(typ_opakowania)", (product_name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form))
                p_type = 'surowiec'

            # Get the ID of the pallet (new or existing)
            pallet_id = cursor.lastrowid
            if not pallet_id or pallet_id == 0:
                table_name = table_opk if target.get('packageForm') == 'packaging' else table_sur
                cursor.execute(f"SELECT id FROM {table_name} WHERE lokalizacja = %s AND stan_magazynowy > 0 LIMIT 1", (lokalizacja,))
                p_row = cursor.fetchone()
                pallet_id = p_row['id'] if p_row else None

            target['accepted'] = True
            target['accepted_by'] = login
            target['accepted_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            target['lokalizacja_przyjecia'] = lokalizacja
            target['nr_partii'] = nr_partii
            target['nr_palety'] = nr_palety
            target['data_produkcji'] = data_produkcji
            target['data_przydatnosci'] = data_przydatnosci

            # 3. IF TRANSFER: Empty the source spot
            source_spot = target.get('sourceSpot')
            is_partial = target.get('is_partial', False)

            if source_spot and not is_partial:
                # Find the pallet at source and zero it (in all 3 tables just in case)
                cursor.execute(f"UPDATE {table_sur} SET stan_magazynowy = 0 WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (source_spot, product_name))
                cursor.execute(f"UPDATE {table_opk} SET stan_magazynowy = 0 WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (source_spot, product_name))
                cursor.execute(f"UPDATE magazyn_dodatki SET stan_magazynowy = 0 WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (source_spot, product_name))
            
            # If it's partial, we already subtracted at Stage 1, so we just create the new one at destination (handled by next lines)
                
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, komentarz, user_login) VALUES (%s, %s, %s, 'WYDANIE_PRZESUNIECIE', %s, %s, %s)",
                    (None, linia, p_type, source_spot, f"Wydanie do przesunięcia: {product_name} -> {lokalizacja}", login)
                )

            # Log to palety_historia
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'PRZYJECIE', %s, %s, %s)",
                (pallet_id, linia, p_type, lokalizacja, f"Przyjęcie z dostawy: {product_name}, partia: {nr_partii}", login)
            )

            all_processed = all(i.get('accepted') or i.get('rejected') for i in items)
            new_status = 'COMPLETED' if all_processed else 'OCZEKUJE'

            cursor.execute("UPDATE magazyn_dostawy SET items=%s, status=%s, potwierdzone_przez=%s, potwierdzone_at=%s WHERE id=%s", (json.dumps(items), new_status, login if all_processed else dostawa.get('potwierdzone_przez'), datetime.now() if all_processed else dostawa.get('potwierdzone_at'), dostawa_id))
            conn.commit()
            
            # --- AUTO DRUKOWANIE ETYKIET (2 SZT) W TLE ---
            if printer_ip and printer_name:
                try:
                    import threading
                    import requests
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    payload = {
                        "drukarka": printer_name,
                        "ip": printer_ip,
                        "typ": p_type,
                        "dane": {
                            "palletData": {
                                "nrPalety": nr_palety,
                                "productName": product_name,
                                "batchNumber": nr_partii or '---',
                                "productionDate": str(data_produkcji) if data_produkcji else '---',
                                "expiryDate": str(data_przydatnosci) if data_przydatnosci else '---',
                                "currentWeight": qty,
                                "labNotes": "Dostawa Przyjęta"
                            }
                        }
                    }
                    def run_print():
                        url = "https://127.0.0.1:3001/drukuj-zpl"
                        for _ in range(2):
                            try:
                                requests.post(url, json=payload, verify=False, timeout=3)
                            except Exception:
                                pass
                    threading.Thread(target=run_print, daemon=True).start()
                except Exception as e:
                    print(f"Błąd uruchomienia wątku drukowania: {e}")
            # --- KONIEC AUTO DRUKU ---

            return True, "", {
                "all_accepted": all_processed,
                "all_processed": all_processed,
                "accepted_count": sum(1 for i in items if i.get('accepted')),
                "rejected_count": sum(1 for i in items if i.get('rejected')),
                "total": len(items),
                "linia": linia,
                "dostawa_id": dostawa_id,
                "nr_palety": nr_palety,
            }
        except Exception as e:
            return False, str(e), None
        finally:
            conn.close()

    @staticmethod
    def reject_item(dostawa_id, item_id, reason='', login='system'):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, "Nie znaleziono przesunięcia", None
            if str(dostawa.get('status') or '').upper() == 'CANCELLED':
                return False, "Przesunięcie jest już anulowane", None

            items = json.loads(dostawa.get('items') or '[]')
            target = next((i for i in items if str(i.get('id')) == str(item_id)), None)
            if not target:
                return False, "Nie znaleziono pozycji", None
            if target.get('accepted'):
                return False, "Pozycja już przyjęta", None
            if target.get('rejected'):
                return False, "Pozycja już odrzucona", None

            linia = dostawa['linia']
            table_sur = get_table_name('magazyn_surowce', linia)
            table_opk = get_table_name('magazyn_opakowania', linia)

            source_spot = str(target.get('sourceSpot') or '').strip().upper()
            if not source_spot:
                fallback_source = str(dostawa.get('lokalizacja_z') or '').strip().upper()
                if fallback_source and fallback_source != 'WIELE':
                    source_spot = fallback_source
            original_spot = str(target.get('originalSpot') or '').strip().upper()
            product_name = target.get('productName') or ''
            pallet_id = target.get('sourcePalletId')
            pallet_no = str(target.get('sourcePalletNo') or target.get('nr_palety') or '').strip()
            scanned_type = str(target.get('scannedType') or '').strip().lower()
            package_form = str(target.get('packageForm') or '').strip().lower()

            default_is_packaging = scanned_type == 'opakowanie' or package_form == 'packaging'
            default_table = table_opk if default_is_packaging else table_sur
            fallback_table = table_sur if default_is_packaging else table_opk
            restored = False
            restored_type = 'opakowanie' if default_is_packaging else 'surowiec'

            def _try_restore_on_table(table_name):
                if pallet_id not in (None, ''):
                    cursor.execute(
                        f"UPDATE {table_name} SET lokalizacja = %s WHERE id = %s AND lokalizacja = %s",
                        (original_spot, pallet_id, source_spot)
                    )
                    if cursor.rowcount > 0:
                        return True

                if pallet_no:
                    cursor.execute(
                        f"UPDATE {table_name} SET lokalizacja = %s WHERE lokalizacja = %s AND nr_palety = %s AND stan_magazynowy > 0",
                        (original_spot, source_spot, pallet_no)
                    )
                    if cursor.rowcount > 0:
                        return True

                if product_name:
                    cursor.execute(
                        f"UPDATE {table_name} SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0",
                        (original_spot, source_spot, product_name)
                    )
                    if cursor.rowcount > 0:
                        return True

                return False

            if source_spot and original_spot and source_spot != original_spot:
                restored = _try_restore_on_table(default_table)
                if not restored:
                    restored = _try_restore_on_table(fallback_table)
                    if restored:
                        restored_type = 'surowiec' if default_is_packaging else 'opakowanie'

            normalized_reason = str(reason or '').strip() or 'Brak palety do przyjęcia'
            target['rejected'] = True
            target['rejected_by'] = login
            target['rejected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            target['rejected_reason'] = normalized_reason
            target['reject_restored'] = restored

            if restored:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'TRANSFER_REJECT_ITEM', %s, %s, %s, %s)",
                    (pallet_id if pallet_id not in (None, '') else None, linia, restored_type, source_spot, original_spot, f"Odrzucenie pozycji: {normalized_reason}", login)
                )

            all_processed = all(i.get('accepted') or i.get('rejected') for i in items)
            new_status = 'COMPLETED' if all_processed else 'OCZEKUJE'

            cursor.execute(
                "UPDATE magazyn_dostawy SET items=%s, status=%s, potwierdzone_przez=%s, potwierdzone_at=%s WHERE id=%s",
                (
                    json.dumps(items),
                    new_status,
                    login if all_processed else dostawa.get('potwierdzone_przez'),
                    datetime.now() if all_processed else dostawa.get('potwierdzone_at'),
                    dostawa_id,
                )
            )
            conn.commit()

            return True, "", {
                "all_accepted": all_processed,
                "all_processed": all_processed,
                "accepted_count": sum(1 for i in items if i.get('accepted')),
                "rejected_count": sum(1 for i in items if i.get('rejected')),
                "total": len(items),
                "linia": linia,
                "dostawa_id": dostawa_id,
                "restored": restored,
            }
        except Exception as e:
            return False, str(e), None
        finally:
            conn.close()

    @staticmethod
    def check_location(lokalizacja, linia='PSD'):
        if any(str(lokalizacja or '').upper().startswith(ol) for ol in MagazynDostawyService.OPEN_LOCATIONS_PREFIXES):
            return False, "", [] # Always free for open locations

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_sur = get_table_name('magazyn_surowce', linia)
            table_opk = get_table_name('magazyn_opakowania', linia)
            cursor.execute(f"SELECT nazwa, stan_magazynowy, 'Surowiec' as typ FROM {table_sur} WHERE lokalizacja = %s AND stan_magazynowy > 0", (lokalizacja,))
            items_sur = cursor.fetchall()
            cursor.execute(f"SELECT nazwa, stan_magazynowy, 'Opakowanie' as typ FROM {table_opk} WHERE lokalizacja = %s AND stan_magazynowy > 0", (lokalizacja,))
            items_opk = cursor.fetchall()
            all_items = items_sur + items_opk
            if all_items:
                content_desc = ", ".join([f"{i['nazwa']} ({i['stan_magazynowy']})" for i in all_items])
                return True, content_desc, all_items
            return False, "", []
        finally:
            conn.close()

    @staticmethod
    def _normalize_location_code(value):
        return str(value or '').strip().upper()

    @staticmethod
    def _is_rack_location_code(value):
        return bool(re.match(r'^R0[1-7]\d{4}$', MagazynDostawyService._normalize_location_code(value)))

    @staticmethod
    def _rack_sort_key(location_code):
        normalized = MagazynDostawyService._normalize_location_code(location_code)
        match = re.match(r'^R(\d{2})(\d{2})(\d{2})$', normalized)
        if not match:
            return (999, 999, 999)
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))

    @staticmethod
    def _build_static_location_candidates():
        candidates = {
            'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02',
            'OSIP', 'BF_MS01', 'BF_MP01', 'PSD', 'PSD01',
            'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP',
            'R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07',
            'MDO01', 'MD01',
        }

        # Rack map used in inventory scanner: 3 rows x 10 places per rack.
        for rack_no in range(1, 8):
            rack_prefix = f"R{rack_no:02d}"
            for place in range(1, 11):
                for row in range(1, 4):
                    candidates.add(f"{rack_prefix}{place:02d}{row:02d}")

        for idx in range(1, 78):
            candidates.add(f"OS{idx:02d}")

        for idx in range(1, 25):
            candidates.add(f"BB{idx:02d}")

        for idx in range(1, 7):
            candidates.add(f"MZ{idx:02d}")

        for idx in range(1, 23):
            candidates.add(f"KO{idx:02d}")

        candidates.add('MZ05-01')
        candidates.add('MZ06-01')
        return candidates

    @staticmethod
    def _append_locations_from_query(cursor, query, params, target_set):
        try:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        except Exception:
            return

        for row in rows:
            location = MagazynDostawyService._normalize_location_code((row or {}).get('lokalizacja'))
            if location:
                target_set.add(location)

    @staticmethod
    def _load_db_location_sets(linia='PSD'):
        normalized_line = str(linia or 'PSD').upper()
        all_locations = set()
        occupied_locations = set()

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_sur = get_table_name('magazyn_surowce', normalized_line)
            table_opk = get_table_name('magazyn_opakowania', normalized_line)
            table_wg = get_table_name('magazyn_palety', normalized_line)

            all_queries = [
                (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_sur} WHERE lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_opk} WHERE lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                ("SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM magazyn_dodatki WHERE linia = %s AND lokalizacja IS NOT NULL AND lokalizacja <> ''", (normalized_line,)),
                (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_wg} WHERE lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
            ]

            occupied_queries = [
                (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_sur} WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_opk} WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                ("SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM magazyn_dodatki WHERE linia = %s AND stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''", (normalized_line,)),
                (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_wg} WHERE waga_netto > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
            ]

            for query, params in all_queries:
                MagazynDostawyService._append_locations_from_query(cursor, query, params, all_locations)

            for query, params in occupied_queries:
                MagazynDostawyService._append_locations_from_query(cursor, query, params, occupied_locations)
        finally:
            conn.close()

        return all_locations, occupied_locations

    @staticmethod
    def get_location_suggestions(prefix, linia='PSD', only_free_for_racks=True, limit=40):
        prefix_normalized = MagazynDostawyService._normalize_location_code(prefix)
        if not prefix_normalized:
            return []

        safe_limit = max(1, min(int(limit or 40), 100))

        candidates = MagazynDostawyService._build_static_location_candidates()
        occupied_locations = set()

        try:
            db_locations, occupied_locations = MagazynDostawyService._load_db_location_sets(linia)
            candidates.update(db_locations)
        except Exception:
            # Fallback to static dictionary if DB lookup is temporarily unavailable.
            pass

        matched = []
        for location in candidates:
            if not location.startswith(prefix_normalized):
                continue

            if only_free_for_racks and MagazynDostawyService._is_rack_location_code(location):
                if location in occupied_locations:
                    continue

            matched.append(location)

        matched.sort(key=lambda value: (0, *MagazynDostawyService._rack_sort_key(value)) if MagazynDostawyService._is_rack_location_code(value) else (1, value))
        return matched[:safe_limit]

    @staticmethod
    def cancel_dostawa(dostawa_id, login='system'):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT linia, status, items, order_ref FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa: return False, "Nie znaleziono przesunięcia"
            if dostawa['status'] == 'COMPLETED': return False, "Nie można anulować zakończonego przesunięcia"

            linia = dostawa['linia']
            order_ref = dostawa['order_ref']
            items = json.loads(dostawa['items'] or '[]')
            
            table_sur = get_table_name('magazyn_surowce', linia)
            table_opk = get_table_name('magazyn_opakowania', linia)

            # Restore each item from buffer
            for it in items:
                curr_loc = it.get('sourceSpot')
                orig_loc = it.get('originalSpot')
                p_name = it.get('productName')
                if curr_loc and orig_loc and curr_loc != orig_loc:
                    # Restore in surowce
                    cursor.execute(f"UPDATE {table_sur} SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (orig_loc, curr_loc, p_name))
                    restored = cursor.rowcount > 0
                    if not restored:
                        cursor.execute(f"UPDATE {table_opk} SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (orig_loc, curr_loc, p_name))
                        restored = cursor.rowcount > 0
                    
                    if restored:
                        cursor.execute(
                            "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'TRANSFER_CANCEL', %s, %s, %s, %s)",
                            (None, linia, 'mix', curr_loc, orig_loc, f"Anulowanie przesunięcia {order_ref}", login)
                        )

            # Mark as CANCELLED instead of deleting
            cursor.execute("UPDATE magazyn_dostawy SET status = 'CANCELLED' WHERE id = %s", (dostawa_id,))
            conn.commit()
            return True, "Przesunięcie zostało anulowane (status: ANULOWANE)"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def accept_production_pallet(pallet_id, lokalizacja, linia='PSD', login='system', confirmed_weight=None):
        """Moves a production pallet (WG) from 'do_przyjecia' to warehouse inventory."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_prod = 'palety_workowanie' if linia == 'PSD' else 'palety_agro'
            table_wh = 'magazyn_palety' if linia == 'PSD' else 'magazyn_palety_agro'
            
            # 1. Fetch pallet data
            query = f"""
                SELECT p.*, plan.produkt_nazwa, plan.data_planu
                FROM {table_prod} p
                LEFT JOIN plan_produkcji plan ON p.plan_id = plan.id
                WHERE p.id = %s AND p.status = 'do_przyjecia'
            """
            if linia == 'AGRO':
                query = f"""
                    SELECT p.*, plan.produkt as produkt_nazwa, plan.data_planu
                    FROM {table_prod} p
                    LEFT JOIN plan_produkcji_agro plan ON p.plan_id = plan.id
                    WHERE p.id = %s AND p.status = 'do_przyjecia'
                """
            
            cursor.execute(query, (pallet_id,))
            pallet = cursor.fetchone()
            if not pallet:
                return False, "Nie znaleziono palety lub jest już przyjęta."

            try:
                confirmed_netto = float(confirmed_weight) if confirmed_weight is not None else float(pallet.get('waga') or 0)
            except (TypeError, ValueError):
                confirmed_netto = float(pallet.get('waga') or 0)

            if confirmed_netto <= 0:
                return False, "Brak poprawnej wagi netto palety do przyjęcia."

            # 2. Update production table status
            cursor.execute(
                f"UPDATE {table_prod} SET status = 'w_magazynie', data_potwierdzenia = %s, waga_potwierdzona = %s WHERE id = %s",
                (datetime.now(), confirmed_netto, pallet_id),
            )
            
            # 3. Insert into warehouse table
            # Check if record already exists (some logic might have inserted it earlier)
            fk_col = 'paleta_workowanie_id'
            cursor.execute(f"SELECT id FROM {table_wh} WHERE {fk_col} = %s", (pallet_id,))
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute(
                    f"UPDATE {table_wh} SET lokalizacja = %s, data_potwierdzenia = %s, user_login = %s, waga_netto = %s WHERE id = %s",
                    (lokalizacja, datetime.now(), login, confirmed_netto, existing['id']),
                )
            else:
                cursor.execute(f"""
                    INSERT INTO {table_wh} 
                    ({fk_col}, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, lokalizacja, user_login, nr_palety)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (pallet_id, 
                      pallet.get('plan_id'), 
                      pallet.get('data_planu'), 
                      pallet.get('produkt_nazwa') or pallet.get('produkt') or 'Wyrób Gotowy', 
                      confirmed_netto, 
                      float(pallet.get('waga_brutto') or 0), 
                      float(pallet.get('tara') or 0), 
                      lokalizacja, login, 
                      pallet.get('nr_palety')))

            # 4. Log history
            cursor.execute("""
                INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login)
                VALUES (%s, %s, 'wyrob_gotowy', 'PRZYJECIE_WG', 'LINIA', %s, %s, %s)
            """, (pallet_id, linia, lokalizacja, f"Przyjęcie WG: {pallet['produkt_nazwa']}", login))

            conn.commit()
            return True, "Paleta została przyjęta do magazynu."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
