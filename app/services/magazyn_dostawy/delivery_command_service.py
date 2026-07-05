from app.db import get_db_connection, get_table_name
import json
from datetime import datetime
import uuid
import re
from app.utils.pallet_id import generate_pallet_id
from app.utils.location_validator import validate_warehouse_location, is_production_tank_code

from app.services.magazyn_dostawy.location_service import LocationService

class DeliveryCommandService:

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

            is_external = not bool(source_locations)
            physical_insert_loc = 'OCZEKUJĄCE' if is_external else lokalizacja_do

            # Walidacja: lokalizacja_do NIE może być kodem zbiornika produkcyjnego
            if lokalizacja_do and not is_external:
                is_valid, error_msg = validate_warehouse_location(lokalizacja_do, allow_empty=False)
                if not is_valid:
                    return False, error_msg

            # Walidacja: żadna z lokalizacji źródłowych NIE może być kodem zbiornika
            for source_loc in source_locations:
                is_valid, error_msg = validate_warehouse_location(source_loc, allow_empty=False)
                if not is_valid:
                    return False, f"Błąd w lokalizacji źródłowej: {error_msg}"

            unknown_sources = sorted([loc for loc in source_locations if not _is_known_source_location(loc)])
            if unknown_sources and not global_skip_warehouse_lookup:
                preview = ', '.join(unknown_sources[:5])
                suffix = ', ...' if len(unknown_sources) > 5 else ''
                return False, f"Nieznane lokalizacje źródłowe: {preview}{suffix}."

            lokalizacja_z = _norm_loc(data.get('lokalizacja_z', ''))
            if not lokalizacja_z and source_locations:
                lokalizacja_z = source_locations[0] if len(source_locations) == 1 else 'WIELE'

            if lokalizacja_do and lokalizacja_do not in known_target_locations and lokalizacja_do != 'OCZEKUJĄCE':
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
                    
                    print_payloads = []
                    
                    for idx, item in enumerate(items):
                        if item.get('id') in (None, ''):
                            item['id'] = f"item_{idx}_{int(datetime.now().timestamp())}"
                        
                        if not item.get('nr_palety'):
                            p_type = 'opakowanie' if item.get('packageForm') == 'packaging' else 'surowiec'
                            item['nr_palety'] = generate_pallet_id(linia, type=p_type)
                        
                        product_name = item.get('productName') or 'Brak nazwy'
                        nr_palety = item.get('nr_palety')
                        nr_partii = item.get('nr_partii')
                        data_produkcji = item.get('data_produkcji') or None
                        data_przydatnosci = item.get('data_przydatnosci') or None
                        
                        if item.get('packageForm') == 'packaging':
                            qty = float(item.get('quantity') or item.get('unitsPerPallet') or 0)
                            pallet_type = 'opakowanie'
                            target_table = table_opk
                            pkg_form = 'packaging'
                        else:
                            qty = float(item.get('quantity') or item.get('netWeight') or 0)
                            pallet_type = 'surowiec'
                            target_table = table_sur
                            pkg_form = item.get('packageForm', 'bags')

                        # We do NOT accept it immediately - it stays pending

                        item['sourceSpot'] = 'DOSTAWA'

                        # DB INSERT
                        cursor.execute(f"INSERT INTO {target_table} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa), nr_partii = VALUES(nr_partii), data_produkcji = VALUES(data_produkcji), data_przydatnosci = VALUES(data_przydatnosci), nr_palety = VALUES(nr_palety), typ_opakowania = VALUES(typ_opakowania), lokalizacja = VALUES(lokalizacja)", (product_name, qty, physical_insert_loc, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form))
                        pallet_id = cursor.lastrowid
                        if not pallet_id or pallet_id == 0:
                            cursor.execute(f"SELECT id FROM {target_table} WHERE lokalizacja = %s AND stan_magazynowy > 0 LIMIT 1", (physical_insert_loc,))
                            p_row = cursor.fetchone()
                            pallet_id = p_row['id'] if p_row else None

                        item['sourcePalletId'] = pallet_id
                        cursor.execute(
                            "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'DOSTAWA_PRZYJECIE', %s, %s, %s, %s)",
                            (pallet_id, linia, pallet_type, 'DOSTAWA', physical_insert_loc, f"Przyjęcie zewnętrzne z {supplier} - WZ: {order_ref}", login)
                        )
                        
                        # Trigger physical printing for this pallet in the background!
                        if printer_ip and printer_name:
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
                                            "labNotes": "Przyjęta"
                                        }
                                    }
                                }
                                print_payloads.append(payload)
                            except Exception as pe:
                                print(f"Błąd przygotowania danych do druku: {pe}")
                    
                    # Start ONE thread to print all collected payloads sequentially
                    if print_payloads:
                        def run_print_queue(payloads):
                            import requests
                            import urllib3
                            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                            url = "http://127.0.0.1:3001/drukuj-zpl"
                            for p in payloads:
                                for _ in range(2):
                                    try:
                                        requests.post(url, json=p, verify=False, timeout=3)
                                    except Exception:
                                        pass
                        import threading
                        threading.Thread(target=run_print_queue, args=(print_payloads,), daemon=True).start()
                    
                    # Status pozostaje jako OCZEKUJE, aby zlecenie widniało na liście 'Oczekujące'

                # DEDUPLICATE items before saving (by item ID)
                if items:
                    seen_ids = set()
                    deduped_items = []
                    for item in items:
                        item_id = str(item.get('id', ''))
                        if item_id and item_id not in seen_ids:
                            seen_ids.add(item_id)
                            deduped_items.append(item)
                        elif not item_id:
                            # Item without ID - keep it but it's unusual
                            deduped_items.append(item)
                    items = deduped_items

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
