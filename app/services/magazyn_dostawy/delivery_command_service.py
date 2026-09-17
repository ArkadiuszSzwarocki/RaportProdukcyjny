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
                'OSIP', 'BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'BFOS', 'PSD', 'PSD01',
                'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP',
            }
            known_source_locations.update({f'KO{i:02d}' for i in range(1, 23)})
            known_target_locations = {'BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'BFOS', 'MS01', 'MP01', 'PSD01'}

            def _is_known_source_location(value):
                loc = _norm_loc(value)
                if not loc:
                    return False

                clean_loc = loc.replace('_', '').replace('-', '').replace(' ', '')
                if clean_loc in {'BFMS01', 'BFMP01', 'BFOS', 'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02', 'OSIP', 'PSD', 'PSD01', 'RAMPA', 'MIX01', 'WTRANZYCIEOSIP'}:
                    return True

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
                    return (1 <= nr <= 24) and (nr not in (7, 8, 9, 10, 23, 24))

                mz_simple = re.match(r'^MZ(\d{2})$', loc)
                if mz_simple:
                    nr = int(mz_simple.group(1))
                    return nr in (7, 8, 9, 10, 23, 24)

                ko_match = re.match(r'^KO(\d{2})$', loc)
                if ko_match:
                    nr = int(ko_match.group(1))
                    return 1 <= nr <= 22

                if loc.startswith('MD') or loc.startswith('MDO') or loc.startswith('BF'):
                    return True

                return False

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
                if _norm_loc(it.get('sourceSpot')) and _norm_loc(it.get('sourceSpot')) != 'DOSTAWA'
            })

            # Dostawa zewnętrzna jest wyłącznie wtedy, gdy podano dostawcę zewnętrznego (supplier)
            is_external = bool(supplier)
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
            if not lokalizacja_z:
                if source_locations:
                    lokalizacja_z = source_locations[0] if len(source_locations) == 1 else 'WIELE'
                elif not is_external:
                    # Dla przesunięć wewnętrznych bez wskazanej konkretnej półki domyślnym magazynem źródłowym jest hala wydania
                    lokalizacja_z = 'MS01' if linia == 'PSD' else ('MGW01' if linia == 'AGRO' else linia)

            if lokalizacja_do and lokalizacja_do not in known_target_locations and lokalizacja_do != 'OCZEKUJĄCE':
                return False, f"Nieznana lokalizacja docelowa: {lokalizacja_do}."

            unaccepted_sources = sorted({
                _norm_loc(it.get('sourceSpot'))
                for it in items
                if _norm_loc(it.get('sourceSpot')) and not it.get('accepted')
            })

            if lokalizacja_do and any(_is_route_conflict(loc, lokalizacja_do) for loc in unaccepted_sources):
                return False, f"Operacja niemożliwa: Skąd i Dokąd nie mogą być takie same ({lokalizacja_do})."

            # Walidacja blokady przesunięć Centrala <-> OSIP (wymagany transfer)
            if not is_external and lokalizacja_do and lokalizacja_do != 'OCZEKUJĄCE':
                from app.utils.location_validator import validate_centrala_osip_move
                for it in items:
                    src_spot = _norm_loc(it.get('sourceSpot'))
                    pal_no = it.get('palletNo') or it.get('nr_palety')
                    if src_spot and src_spot != lokalizacja_do:
                        is_trf_valid, trf_err = validate_centrala_osip_move(
                            source_location=src_spot,
                            target_location=lokalizacja_do,
                            nr_palety=pal_no
                        )
                        if not is_trf_valid:
                            return False, trf_err

            # Date validation for items
            today_date = datetime.now().strftime('%Y-%m-%d')
            for idx, it in enumerate(items):
                prod_date = str(it.get('data_produkcji') or '').strip()
                expiry_date = str(it.get('data_przydatnosci') or '').strip()

                if prod_date and prod_date > today_date:
                    return False, f"Pozycja {idx + 1}: Data produkcji ({prod_date}) jest późniejsza niż dzisiejsza data ({today_date})."

                if prod_date and expiry_date and expiry_date < prod_date:
                    return False, f"Pozycja {idx + 1}: Data przydatności ({expiry_date}) jest wcześniejsza niż data produkcji ({prod_date})."

            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)

                # Walidacja produktów z listy słownikowej
                table_sur = get_table_name('magazyn_surowce', linia)
                table_opk = get_table_name('magazyn_opakowania', linia)
                table_wg = get_table_name('magazyn_palety', linia)

                valid_dict_map = {}
                dict_queries = [
                    ("SELECT DISTINCT nazwa FROM slownik_surowcow WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''", ()),
                    (f"SELECT DISTINCT nazwa FROM {table_sur} WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''", ()),
                    (f"SELECT DISTINCT nazwa FROM {table_opk} WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''", ()),
                    ("SELECT DISTINCT nazwa FROM magazyn_dodatki WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''", ()),
                    (f"SELECT DISTINCT produkt as nazwa FROM {table_wg} WHERE produkt IS NOT NULL AND TRIM(produkt) != ''", ()),
                ]
                for dq, dparams in dict_queries:
                    try:
                        cursor.execute(dq, dparams)
                        for dr in cursor.fetchall():
                            dn = (dr.get('nazwa') or '').strip()
                            if dn:
                                valid_dict_map[dn.lower()] = dn
                    except Exception:
                        pass

                if items and valid_dict_map:
                    for idx, it in enumerate(items):
                        p_name = str(it.get('productName') or it.get('nazwa') or '').strip()
                        if not p_name:
                            return False, f"Pozycja {idx + 1}: Brak nazwy produktu. Wybierz produkt z listy."

                        canonical = valid_dict_map.get(p_name.lower())
                        if not canonical:
                            return False, f"Pozycja {idx + 1}: Produkt '{p_name}' nie istnieje w słowniku. Wybierz poprawną nazwę z listy."
                        it['productName'] = canonical

                cursor.execute("SELECT status, items, lokalizacja_z FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
                old_data = cursor.fetchone()
                old_status = old_data['status'] if old_data else None
                old_items = json.loads(old_data['items']) if old_data and old_data.get('items') else []

                # 1. Detect removed items from pending transfer to RESTORE them
                if old_status == 'OCZEKUJE' and items is not None:
                    table_sur = get_table_name('magazyn_surowce', linia)
                    table_opk = get_table_name('magazyn_opakowania', linia)
                    new_ids = [str(it.get('id')) for it in items]
                    for old_it in old_items:
                        if str(old_it.get('id')) not in new_ids and not old_it.get('accepted'):
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
                                if not restored:
                                    cursor.execute(f"UPDATE magazyn_dodatki SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0", (orig_loc, curr_loc, p_name))
                                    restored = cursor.rowcount > 0
                                
                                if restored:
                                    cursor.execute(
                                        "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'TRANSFER_CANCEL', %s, %s, %s, %s)",
                                        (None, linia, 'mix', curr_loc, orig_loc, f"Przywrócenie (usunięto z przesunięcia {order_ref})", login)
                                    )

                # Process external delivery receptions
                is_external_reception = is_external
                if is_external_reception:
                    table_sur = get_table_name('magazyn_surowce', linia)
                    table_opk = get_table_name('magazyn_opakowania', linia)

                    # Jeśli to edycja istniejącej dostawy — usuń usunięte pozycje z bazy surowców/opakowań
                    if old_data and old_items:
                        new_pallet_ids = {it.get('sourcePalletId') for it in items if it.get('sourcePalletId')}
                        for old_it in old_items:
                            old_pid = old_it.get('sourcePalletId')
                            if old_pid and old_pid not in new_pallet_ids and not old_it.get('accepted'):
                                old_src = str(old_it.get('source') or old_it.get('scannedType') or old_it.get('type') or '').lower()
                                del_table = table_opk if old_src == 'opakowanie' or old_it.get('packageForm') == 'packaging' else table_sur
                                try:
                                    cursor.execute(f"DELETE FROM {del_table} WHERE id = %s", (old_pid,))
                                except Exception:
                                    pass
                    
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
                        item['productName'] = product_name
                        item['nr_partii'] = nr_partii
                        item['data_produkcji'] = str(data_produkcji) if data_produkcji else ''
                        item['data_przydatnosci'] = str(data_przydatnosci) if data_przydatnosci else ''
                        item['quantity'] = qty
                        item['netWeight'] = qty
                        item['unitsPerPallet'] = qty if pkg_form == 'packaging' else 0

                        source_pallet_id = item.get('sourcePalletId')
                        if source_pallet_id:
                            # AKTUALIZACJA ISTNIEJĄCEJ PALETY PRZY EDYCJI
                            cursor.execute(
                                f"UPDATE {target_table} SET nazwa=%s, stan_magazynowy=%s, lokalizacja=%s, nr_partii=%s, data_produkcji=%s, data_przydatnosci=%s, nr_palety=%s, typ_opakowania=%s WHERE id = %s",
                                (product_name, qty, physical_insert_loc, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form, source_pallet_id)
                            )
                            pallet_id = source_pallet_id
                        else:
                            # DB INSERT DLA NOWEJ PALETY
                            cursor.execute(
                                f"INSERT INTO {target_table} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                                (product_name, qty, physical_insert_loc, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form)
                            )
                            pallet_id = cursor.lastrowid
                            item['sourcePalletId'] = pallet_id
                            
                            cursor.execute(
                                "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'DOSTAWA_PRZYJECIE', %s, %s, %s, %s)",
                                (pallet_id, linia, pallet_type, 'DOSTAWA', physical_insert_loc, f"Przyjęcie zewnętrzne z {supplier} - WZ: {order_ref}", login)
                            )
                        
                        # Trigger physical printing for this pallet in the background!
                        if printer_ip and printer_name and not source_pallet_id:
                            try:
                                import threading
                                import requests
                                import urllib3
                                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                                payload = {
                                    "drukarka": printer_name,
                                    "ip": printer_ip,
                                    "typ": pallet_type,
                                    "copies": 2,
                                    "dane": {
                                        "palletData": {
                                            "nrPalety": nr_palety,
                                            "productName": product_name,
                                            "batchNumber": nr_partii or '---',
                                            "productionDate": str(data_produkcji) if data_produkcji else '---',
                                            "expiryDate": str(data_przydatnosci) if data_przydatnosci else '---',
                                            "currentWeight": qty,
                                            "labNotes": "Przyjęta",
                                            "copies": 2
                                        }
                                    }
                                }
                                print_payloads.append(payload)
                            except Exception as pe:
                                print(f"Błąd przygotowania danych do druku: {pe}")
                    
                    # Start ONE thread to print all collected payloads sequentially
                    if print_payloads:
                        def run_print_queue(payloads):
                            import time
                            import requests
                            import urllib3
                            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                            url = "http://127.0.0.1:3001/drukuj-zpl"
                            for p in payloads:
                                try:
                                    requests.post(url, json=p, verify=False, timeout=5)
                                except Exception:
                                    pass
                                time.sleep(0.08)
                        import threading
                        threading.Thread(target=run_print_queue, args=(print_payloads,), daemon=True).start()

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
                            deduped_items.append(item)
                    items = deduped_items

                # BLOKADA PALET W DOKUMENCIE
                if not is_external_reception:
                    table_sur = get_table_name('magazyn_surowce', linia)
                    table_opk = get_table_name('magazyn_opakowania', linia)
                    table_got = get_table_name('magazyn_palety', linia)
                    
                    def toggle_block(item_list, blocked_val):
                        if not item_list: return
                        for it in item_list:
                            # Paleta matka przy wydaniu częściowym NIE powinna być blokowana
                            if it.get('is_partial') and blocked_val == 1:
                                continue
                            pid = it.get('sourcePalletId')
                            pnr = it.get('sourcePalletNo') or it.get('nr_palety')
                            if not pid and not pnr: continue
                            for l_code in ['PSD', 'AGRO']:
                                for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                                    if pid:
                                        try: cursor.execute(f"UPDATE {tbl} SET is_blocked = %s WHERE id = %s", (blocked_val, pid))
                                        except Exception: pass
                                    if pnr:
                                        try: cursor.execute(f"UPDATE {tbl} SET is_blocked = %s WHERE nr_palety = %s", (blocked_val, pnr))
                                        except Exception: pass
                                if pid:
                                    try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = %s WHERE id = %s", (blocked_val, pid))
                                    except Exception: pass
                                if pnr:
                                    try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = %s WHERE nr_palety = %s", (blocked_val, pnr))
                                    except Exception: pass

                    # 1. Zdejmujemy blokadę ze wszystkich starych palet
                    if old_items:
                        toggle_block(old_items, 0)
                    
                    # 2. Nakładamy blokadę na aktualne palety w dokumencie (ponieważ status to nie zakończone/anulowane)
                    if str(status).upper() not in ['ZAKONCZONE', 'ZAKOŃCZONE', 'ANULOWANE', 'COMPLETED']:
                        toggle_block(items, 1)

                partial_print_items = []
                # 2. Handle item resolution and keep transfer in OCZEKUJE for internal transfers
                if not is_external_reception:
                    table_sur = get_table_name('magazyn_surowce', linia)
                    table_opk = get_table_name('magazyn_opakowania', linia)
                    table_got = get_table_name('magazyn_palety', linia)
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
                    
                    for idx, item in enumerate(items):
                        if item.get('id') in (None, ''):
                            item['id'] = f"item_{idx}_{int(datetime.now().timestamp())}"

                        if item.get('accepted'):
                            updated_items.append(item)
                            continue

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
                                        else:
                                            cursor.execute(f"SELECT id, nr_palety, waga_netto AS stan_magazynowy FROM {table_got} WHERE id = %s AND (lokalizacja = %s OR (lokalizacja IS NULL AND %s = 'MGW01')) AND waga_netto > 0", (p_id, source_spot, source_spot))
                                            p_res = cursor.fetchone()
                                            if p_res: p_type = 'wyrob_gotowy'

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
                                        else:
                                            cursor.execute(f"SELECT id, nr_palety, waga_netto AS stan_magazynowy FROM {table_got} WHERE nr_palety = %s AND (lokalizacja = %s OR (lokalizacja IS NULL AND %s = 'MGW01')) AND waga_netto > 0", (p_nr, source_spot, source_spot))
                                            p_res = cursor.fetchone()
                                            if p_res: p_type = 'wyrob_gotowy'

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
                                        else:
                                            cursor.execute(f"SELECT id, nr_palety, waga_netto AS stan_magazynowy FROM {table_got} WHERE produkt = %s AND (lokalizacja = %s OR (lokalizacja IS NULL AND %s = 'MGW01')) AND waga_netto > 0", (p_name, source_spot, source_spot))
                                            p_res = cursor.fetchone()
                                            if p_res: p_type = 'wyrob_gotowy'

                            if not p_res:
                                if item_skip_lookup or item.get('sourcePalletId'):
                                    item['originalSpot'] = item.get('originalSpot') or source_spot
                                    item['warehouseLookupSkipped'] = True
                                    item['accepted'] = False
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

                            item['originalSpot'] = item.get('originalSpot') or source_spot
                            item['sourceSpot'] = source_spot
                            item['sourcePalletId'] = p_id
                            item['scannedType'] = p_type
                            if p_nr:
                                item['sourcePalletNo'] = p_nr
                            item['accepted'] = False

                            # Sprawdzamy czy to wydanie częściowe (część wagi z palety matki)
                            source_stock = float(p_res.get('stan_magazynowy') or 0.0)
                            transfer_qty = 0.0
                            if item.get('packageForm') == 'packaging' or p_type == 'opakowanie':
                                transfer_qty = float(item.get('unitsPerPallet') or item.get('quantity') or 0.0)
                            else:
                                transfer_qty = float(item.get('netWeight') or item.get('quantity') or 0.0)

                            is_already_split = bool(item.get('is_partial') and item.get('nr_palety') and item.get('nr_palety') != p_nr)
                            is_partial_transfer = (not is_already_split) and (0 < transfer_qty < source_stock)

                            if is_partial_transfer:
                                # --- WYDANIE CZĘŚCIOWE Z PALETY MATKI ---
                                remaining_stock = round(source_stock - transfer_qty, 3)
                                child_sscc = generate_pallet_id(linia, type=p_type)

                                # 1. Pomniejszamy paletę matkę i NIE blokujemy jej
                                tbl_sur = get_table_name('magazyn_surowce', linia)
                                tbl_opk = get_table_name('magazyn_opakowania', linia)
                                tbl_got = get_table_name('magazyn_palety', linia)

                                if p_type == 'surowiec':
                                    cursor.execute(f"UPDATE {tbl_sur} SET stan_magazynowy = %s, is_blocked = 0, updated_at = NOW() WHERE id = %s", (remaining_stock, p_id))
                                elif p_type == 'opakowanie':
                                    cursor.execute(f"UPDATE {tbl_opk} SET stan_magazynowy = %s, is_blocked = 0 WHERE id = %s", (remaining_stock, p_id))
                                elif p_type == 'dodatek':
                                    cursor.execute("UPDATE magazyn_dodatki SET stan_magazynowy = %s, is_blocked = 0 WHERE id = %s", (remaining_stock, p_id))
                                elif p_type == 'wyrob_gotowy':
                                    cursor.execute(f"UPDATE {tbl_got} SET waga_netto = %s, is_blocked = 0 WHERE id = %s", (remaining_stock, p_id))

                                # 2. Historia i ruch magazynowy dla palety matki
                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) "
                                    "VALUES (%s, %s, %s, %s, 'WYDANIE_PRZESUNIECIE_CZESCIOWE', %s, %s, %s, %s)",
                                    (p_id, p_nr, linia, p_type, source_spot, source_spot,
                                     f"Wydanie częściowe {transfer_qty} kg na zlecenie przesunięcia {order_ref}. Na palecie matce pozostaje {remaining_stock} kg.", login)
                                )
                                table_ruch = get_table_name('magazyn_ruch', linia)
                                cursor.execute(
                                    f"INSERT INTO {table_ruch} (surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, autor_login, autor_data, komentarz) "
                                    f"VALUES (%s, %s, 'PRZESUNIECIE', %s, %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                                    (p_id, p_name, -transfer_qty, remaining_stock, source_spot, login, f"Wydanie częściowe ze zlecenia przesunięcia {order_ref}")
                                )

                                # 3. Konfiguracja pozycji przesunięcia z NOWYM SSCC
                                item['nr_palety'] = child_sscc
                                item['sourcePalletNo'] = p_nr
                                item['sourcePalletId'] = p_id
                                item['is_partial'] = True
                                item['motherWeightBefore'] = source_stock
                                item['motherWeightAfter'] = remaining_stock
                                item['netWeight'] = transfer_qty

                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) "
                                    "VALUES (%s, %s, %s, %s, 'UTWORZENIE_Z_PODZIALU', %s, %s, %s, %s)",
                                    (None, child_sscc, linia, p_type, source_spot, lokalizacja_do,
                                     f"Utworzono z wydania częściowego palety matki {p_nr} ({transfer_qty} kg) dla zlecenia przesunięcia {order_ref}", login)
                                )

                                # 4. Kolejkowanie wydruku DWÓCH etykiet: paleta matka (pomniejszona) + nowe przesunięcie (nowy SSCC)
                                partial_print_items.append({
                                    'mother_sscc': p_nr,
                                    'child_sscc': child_sscc,
                                    'product_name': p_name,
                                    'mother_weight': remaining_stock,
                                    'child_weight': transfer_qty,
                                    'nr_partii': item.get('nr_partii'),
                                    'data_produkcji': item.get('data_produkcji'),
                                    'data_przydatnosci': item.get('data_przydatnosci'),
                                    'linia': linia,
                                    'p_type': p_type
                                })
                            elif is_already_split:
                                # Paleta już wcześniej podzielona w tym dokumencie, zachowujemy nr_palety (child_sscc) i is_partial
                                item['is_partial'] = True
                                if p_id:
                                    for l_code in ['PSD', 'AGRO']:
                                        for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                                            try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE id = %s", (p_id,))
                                            except Exception: pass
                                        try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 0 WHERE id = %s", (p_id,))
                                        except Exception: pass
                            else:
                                # --- PEŁNE PRZESUNIĘCIE CAŁEJ PALETY ---
                                if p_nr:
                                    item['nr_palety'] = p_nr
                                item['is_partial'] = False

                                # Ustawiamy status OCZEKUJĄCE oraz blokadę całej palety do czasu przyjęcia
                                for l_code in ['PSD', 'AGRO']:
                                    for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                                        if p_id:
                                            try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 1, lokalizacja = 'OCZEKUJĄCE', is_loaded = 0 WHERE id = %s", (p_id,))
                                            except Exception: pass
                                        if p_nr:
                                            try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 1, lokalizacja = 'OCZEKUJĄCE', is_loaded = 0 WHERE nr_palety = %s", (p_nr,))
                                            except Exception: pass
                                    if p_id:
                                        try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 1, lokalizacja = 'OCZEKUJĄCE' WHERE id = %s", (p_id,))
                                        except Exception: pass
                                    if p_nr:
                                        try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 1, lokalizacja = 'OCZEKUJĄCE' WHERE nr_palety = %s", (p_nr,))
                                        except Exception: pass

                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'WYDANIE_PRZESUNIECIE', %s, %s, %s, %s)",
                                    (p_id, linia, p_type, source_spot, lokalizacja_do, f"Zlecenie przesunięcia {order_ref}: {source_spot} -> {lokalizacja_do}", login)
                                )
                        updated_items.append(item)
                    
                    items = updated_items

                has_pending = any(not it.get('accepted') for it in items)
                final_status = 'OCZEKUJE' if has_pending else 'COMPLETED'

                if old_data:
                    cursor.execute("""
                        UPDATE magazyn_dostawy
                        SET order_ref=%s, supplier=%s, delivery_date=%s, status=%s, items=%s,
                            lokalizacja_z=%s, lokalizacja_do=%s
                        WHERE id=%s
                    """, (order_ref, supplier, delivery_date, final_status, json.dumps(items),
                          lokalizacja_z, lokalizacja_do, dostawa_id))
                else:
                    cursor.execute("""
                        INSERT INTO magazyn_dostawy
                            (id, order_ref, supplier, delivery_date, status, items,
                             created_by, created_at, requires_lab, linia,
                             lokalizacja_z, lokalizacja_do)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (dostawa_id, order_ref, supplier, delivery_date, final_status,
                          json.dumps(items), login, datetime.now(), 0, linia,
                          lokalizacja_z, lokalizacja_do))

                conn.commit()

                # Automatyczny wydruk etykiet dla wydań częściowych (matka + dziecko)
                if partial_print_items:
                    try:
                        from app.services.print_server import PrintServer
                        ps = PrintServer()

                        # Wybór drukarki
                        target_ip = data.get('printer_ip')
                        target_name = data.get('printer_name')
                        if not target_ip and data.get('printer_id'):
                            cursor.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s", (data['printer_id'],))
                            p_row = cursor.fetchone()
                            if p_row:
                                target_ip = p_row.get('ip')
                                target_name = p_row.get('nazwa')

                        if not target_ip:
                            cursor.execute("SELECT ip, nazwa FROM drukarki WHERE aktywna = 1 ORDER BY id ASC LIMIT 1")
                            p_row = cursor.fetchone()
                            if p_row:
                                target_ip = p_row.get('ip')
                                target_name = p_row.get('nazwa')

                        print_bridge_payloads = []
                        for p_info in partial_print_items:
                            zpl_m = ps.build_finished_product_label_zpl({
                                'nr_palety': p_info['mother_sscc'],
                                'nazwa': p_info['product_name'],
                                'ilosc': p_info['mother_weight'],
                                'partia': p_info['nr_partii'] or '---',
                                'data': str(p_info['data_produkcji'] or ''),
                                'termin': str(p_info['data_przydatnosci'] or ''),
                                'linia': p_info['linia'],
                                'is_surowiec': (p_info['p_type'] == 'surowiec'),
                                'typ': p_info['p_type']
                            }, copies=2)

                            zpl_c = ps.build_finished_product_label_zpl({
                                'nr_palety': p_info['child_sscc'],
                                'nazwa': p_info['product_name'],
                                'ilosc': p_info['child_weight'],
                                'partia': p_info['nr_partii'] or '---',
                                'data': str(p_info['data_produkcji'] or ''),
                                'termin': str(p_info['data_przydatnosci'] or ''),
                                'linia': p_info['linia'],
                                'is_surowiec': (p_info['p_type'] == 'surowiec'),
                                'typ': p_info['p_type']
                            }, copies=2)

                            cursor.execute("""
                                INSERT INTO print_jobs (printer_ip, printer_name, zpl_content, status)
                                VALUES (%s, %s, %s, 'PENDING')
                            """, (target_ip, target_name, zpl_m))
                            cursor.execute("""
                                INSERT INTO print_jobs (printer_ip, printer_name, zpl_content, status)
                                VALUES (%s, %s, %s, 'PENDING')
                            """, (target_ip, target_name, zpl_c))

                            print_bridge_payloads.append({'drukarka': target_name, 'ip': target_ip, 'dane': zpl_m, 'copies': 2})
                            print_bridge_payloads.append({'drukarka': target_name, 'ip': target_ip, 'dane': zpl_c, 'copies': 2})

                        conn.commit()

                        if print_bridge_payloads:
                            import threading
                            def _send_bridge(payloads):
                                import requests, time
                                for p in payloads:
                                    try:
                                        requests.post("http://127.0.0.1:3001/drukuj-zpl", json=p, timeout=4)
                                    except Exception:
                                        pass
                                    time.sleep(0.1)
                            threading.Thread(target=_send_bridge, args=(print_bridge_payloads,), daemon=True).start()
                    except Exception as pe:
                        print(f"Błąd wydruku etykiet przy podziale: {pe}")

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

                # Zwalnianie blokad na paletach przy anulowaniu i przywracanie wagi dla wydań częściowych
                for it in items:
                    pid = it.get('sourcePalletId')
                    pnr = it.get('sourcePalletNo') or it.get('nr_palety')

                    # Przywracanie wagi palecie matce jeśli było to wydanie częściowe
                    if it.get('is_partial'):
                        p_type = it.get('scannedType') or 'surowiec'
                        qty_to_restore = float(it.get('netWeight') or it.get('quantity') or 0.0)
                        if qty_to_restore > 0 and (pid or pnr):
                            if p_type == 'surowiec':
                                cursor.execute(f"UPDATE {table_sur} SET stan_magazynowy = stan_magazynowy + %s, is_blocked = 0, updated_at = NOW() WHERE (id = %s OR nr_palety = %s)", (qty_to_restore, pid, pnr))
                            elif p_type == 'opakowanie':
                                cursor.execute(f"UPDATE {table_opk} SET stan_magazynowy = stan_magazynowy + %s, is_blocked = 0 WHERE (id = %s OR nr_palety = %s)", (qty_to_restore, pid, pnr))
                            elif p_type == 'dodatek':
                                cursor.execute("UPDATE magazyn_dodatki SET stan_magazynowy = stan_magazynowy + %s, is_blocked = 0 WHERE (id = %s OR nr_palety = %s)", (qty_to_restore, pid, pnr))
                            elif p_type == 'wyrob_gotowy':
                                table_got = get_table_name('magazyn_palety', linia)
                                cursor.execute(f"UPDATE {table_got} SET waga_netto = waga_netto + %s, is_blocked = 0 WHERE (id = %s OR nr_palety = %s)", (qty_to_restore, pid, pnr))

                            cursor.execute(
                                "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) "
                                "VALUES (%s, %s, %s, %s, 'ANULOWANIE_PODZIALU', %s, %s, %s, %s)",
                                (pid, pnr, linia, p_type, it.get('sourceSpot'), it.get('sourceSpot'), f"Zwrot wagi {qty_to_restore} kg z anulowanego przesunięcia częściowego {order_ref}", login)
                            )

                    if not pid and not pnr: continue
                    for l_code in ['PSD', 'AGRO']:
                        for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                            if pid:
                                try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE id = %s", (pid,))
                                except Exception: pass
                            if pnr:
                                try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE nr_palety = %s", (pnr,))
                                except Exception: pass
                        if pid:
                            try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 0 WHERE id = %s", (pid,))
                            except Exception: pass
                        if pnr:
                            try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 0 WHERE nr_palety = %s", (pnr,))
                            except Exception: pass

                # Mark as CANCELLED instead of deleting
                cursor.execute("UPDATE magazyn_dostawy SET status = 'CANCELLED' WHERE id = %s", (dostawa_id,))
                conn.commit()
                return True, "Przesunięcie zostało anulowane (status: ANULOWANE)"
            except Exception as e:
                return False, str(e)
            finally:
                conn.close()

    @staticmethod
    def lock_draft_pallets(items, linia='AGRO', user_login='system'):
        """
        Locks pallets added to a draft transfer list so they cannot be moved or modified elsewhere.
        Sets is_blocked = 1 across warehouse tables for both lines.
        """
        if not items:
            return True, "No items to lock"
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            for it in items:
                pid = it.get('sourcePalletId') or it.get('id')
                pnr = it.get('sourcePalletNo') or it.get('nr_palety')
                if not pid and not pnr:
                    continue
                for l_code in ['PSD', 'AGRO']:
                    for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                        if pid:
                            try:
                                cursor.execute(f"UPDATE {tbl} SET is_blocked = 1 WHERE id = %s", (pid,))
                            except Exception:
                                pass
                        if pnr:
                            try:
                                cursor.execute(f"UPDATE {tbl} SET is_blocked = 1 WHERE nr_palety = %s", (pnr,))
                            except Exception:
                                pass
                    if pid:
                        try:
                            cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 1 WHERE id = %s", (pid,))
                        except Exception:
                            pass
                    if pnr:
                        try:
                            cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 1 WHERE nr_palety = %s", (pnr,))
                        except Exception:
                            pass
            conn.commit()
            return True, "Draft pallets locked successfully"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def unlock_draft_pallets(items, linia='AGRO', user_login='system'):
        """
        Unlocks pallets removed from a draft transfer list (provided they are not in an active transfer).
        Sets is_blocked = 0 across warehouse tables.
        """
        if not items:
            return True, "No items to unlock"
        from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            for it in items:
                pid = it.get('sourcePalletId') or it.get('id')
                pnr = it.get('sourcePalletNo') or it.get('nr_palety')
                if not pid and not pnr:
                    continue
                # Do NOT unlock if pallet is in an active saved transfer
                in_trf, _ = DeliveryQueries.is_pallet_in_pending_transfer(pallet_id=pid, nr_palety=pnr)
                if in_trf:
                    continue
                for l_code in ['PSD', 'AGRO']:
                    for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                        if pid:
                            try:
                                cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE id = %s", (pid,))
                            except Exception:
                                pass
                        if pnr:
                            try:
                                cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE nr_palety = %s", (pnr,))
                            except Exception:
                                pass
                    if pid:
                        try:
                            cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 0 WHERE id = %s", (pid,))
                        except Exception:
                            pass
                    if pnr:
                        try:
                            cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 0 WHERE nr_palety = %s", (pnr,))
                        except Exception:
                            pass
            conn.commit()
            return True, "Draft pallets unlocked successfully"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def sync_draft_pallets(items, linia='AGRO', user_login='system'):
        """
        Synchronizes draft items with current DB state:
        - Refreshes current location (lokalizacja) and current weight/stock.
        - Ensures is_blocked = 1 for all items in the draft.
        - Returns updated items and a list of changes (if any location was updated).
        """
        if not items:
            return True, {"items": [], "changes": []}
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            updated_items = []
            changes = []
            for it in items:
                item_copy = dict(it)
                pid = it.get('sourcePalletId') or it.get('id')
                pnr = it.get('sourcePalletNo') or it.get('nr_palety')
                curr_row = None
                found_tbl = None

                # Search across warehouse tables
                for l_code in [linia, 'AGRO' if str(linia).upper() == 'PSD' else 'PSD']:
                    for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                        if pnr:
                            cursor.execute(f"SELECT * FROM {tbl} WHERE nr_palety = %s LIMIT 1", (pnr,))
                            curr_row = cursor.fetchone()
                        if not curr_row and pid:
                            try:
                                cursor.execute(f"SELECT * FROM {tbl} WHERE id = %s LIMIT 1", (int(pid),))
                                curr_row = cursor.fetchone()
                            except (ValueError, TypeError):
                                pass
                        if curr_row:
                            found_tbl = tbl
                            break
                    if curr_row:
                        break

                if curr_row:
                    old_loc = (item_copy.get('sourceSpot') or item_copy.get('lokalizacja_z') or '').strip().upper()
                    new_loc = (curr_row.get('lokalizacja') or '').strip().upper()
                    if new_loc and old_loc != new_loc:
                        changes.append({
                            'nr_palety': pnr or str(pid),
                            'old_location': old_loc,
                            'new_location': new_loc
                        })
                        item_copy['sourceSpot'] = new_loc
                        item_copy['originalSpot'] = new_loc
                        item_copy['lokalizacja_z'] = new_loc

                    qty_col = 'waga_netto' if 'magazyn_palety' in (found_tbl or '') else 'stan_magazynowy'
                    if qty_col in curr_row and curr_row[qty_col] is not None:
                        item_copy['quantity'] = float(curr_row[qty_col])
                        item_copy['ilosc'] = float(curr_row[qty_col])

                    # Ensure is_blocked = 1 in database
                    if found_tbl and curr_row.get('id'):
                        try:
                            cursor.execute(f"UPDATE {found_tbl} SET is_blocked = 1 WHERE id = %s", (curr_row['id'],))
                        except Exception:
                            pass
                    if found_tbl and curr_row.get('nr_palety'):
                        try:
                            cursor.execute(f"UPDATE {found_tbl} SET is_blocked = 1 WHERE nr_palety = %s", (curr_row['nr_palety'],))
                        except Exception:
                            pass

                updated_items.append(item_copy)
            conn.commit()
            return True, {"items": updated_items, "changes": changes}
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def init_live_transfer(linia='AGRO', order_ref=None, login='system'):
        """Initializes a new open live transfer order directly in the database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            dostawa_id = str(uuid.uuid4())
            if not order_ref:
                from app.blueprints.magazyn_dostawy.config import generate_pallet_id
                now_s = datetime.now().strftime('%Y%m%d%H%M')
                order_ref = f"WZ-{linia.upper()}-{now_s}"
            
            cursor.execute("""
                INSERT INTO magazyn_dostawy
                    (id, order_ref, supplier, delivery_date, status, items,
                     created_by, created_at, requires_lab, linia,
                     lokalizacja_z, lokalizacja_do)
                VALUES (%s, %s, %s, %s, 'OCZEKUJE', '[]', %s, NOW(), 0, %s, 'WIELE', '')
            """, (dostawa_id, order_ref, None, datetime.now(), login, linia.upper()))
            conn.commit()
            return True, {"dostawa_id": dostawa_id, "order_ref": order_ref}
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def add_live_transfer_item(dostawa_id, item, linia='AGRO', login='system'):
        """Adds a single pallet to an active live transfer order and sets is_blocked=1."""
        if not dostawa_id or not item:
            return False, "Missing dostawa_id or item payload"
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, status, items, order_ref FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, f"Transfer order #{dostawa_id} not found"

            raw_items = dostawa.get('items')
            items = json.loads(raw_items) if isinstance(raw_items, str) else (raw_items or [])
            if not isinstance(items, list):
                items = []

            p_nr = item.get('nr_palety') or item.get('sourcePalletNo')
            p_id = item.get('sourcePalletId') or item.get('id')

            # Check if item is already added to this transfer
            for it in items:
                it_nr = it.get('nr_palety') or it.get('sourcePalletNo')
                it_id = it.get('sourcePalletId') or it.get('id')
                if (p_nr and it_nr and str(p_nr).strip().upper() == str(it_nr).strip().upper()) or \
                   (p_id and it_id and str(p_id).strip() == str(it_id).strip()):
                    # Already added
                    accepted_count = sum(1 for i in items if i.get('accepted'))
                    return True, {"total_items": len(items), "accepted_count": accepted_count, "items": items}

            item_to_add = dict(item)
            item_to_add['id'] = str(len(items))
            item_to_add['accepted'] = False
            if p_nr:
                item_to_add['nr_palety'] = p_nr
                item_to_add['sourcePalletNo'] = p_nr
            if p_id:
                item_to_add['sourcePalletId'] = p_id

            items.append(item_to_add)

            # Block pallet in database so scanner knows it is part of this active transfer
            for l_code in ['PSD', 'AGRO']:
                for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                    if p_id:
                        try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 1 WHERE id = %s", (p_id,))
                        except Exception: pass
                    if p_nr:
                        try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 1 WHERE nr_palety = %s", (p_nr,))
                        except Exception: pass
                if p_id:
                    try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 1 WHERE id = %s", (p_id,))
                    except Exception: pass
                if p_nr:
                    try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 1 WHERE nr_palety = %s", (p_nr,))
                    except Exception: pass

            cursor.execute("UPDATE magazyn_dostawy SET items = %s, status = 'OCZEKUJE' WHERE id = %s", (json.dumps(items), dostawa_id))
            conn.commit()

            accepted_count = sum(1 for i in items if i.get('accepted'))
            return True, {"total_items": len(items), "accepted_count": accepted_count, "items": items}
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def remove_live_transfer_item(dostawa_id, item_id=None, nr_palety=None, linia='AGRO', login='system'):
        """Removes a pallet from an active live transfer order and unblocks it."""
        if not dostawa_id:
            return False, "Missing dostawa_id"
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, items FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, f"Transfer order #{dostawa_id} not found"

            raw_items = dostawa.get('items')
            items = json.loads(raw_items) if isinstance(raw_items, str) else (raw_items or [])
            if not isinstance(items, list):
                items = []

            norm_nr = str(nr_palety).strip().upper() if nr_palety else None
            norm_id = str(item_id).strip() if item_id else None

            remaining_items = []
            removed_item = None
            for it in items:
                it_nr = str(it.get('nr_palety') or it.get('sourcePalletNo') or '').strip().upper()
                it_id = str(it.get('sourcePalletId') or it.get('id') or '').strip()
                if (norm_nr and it_nr and norm_nr == it_nr) or (norm_id and it_id and norm_id == it_id):
                    removed_item = it
                else:
                    remaining_items.append(it)

            if removed_item:
                p_id = removed_item.get('sourcePalletId') or removed_item.get('id')
                p_nr = removed_item.get('sourcePalletNo') or removed_item.get('nr_palety')
                for l_code in ['PSD', 'AGRO']:
                    for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                        if p_id:
                            try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE id = %s", (p_id,))
                            except Exception: pass
                        if p_nr:
                            try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE nr_palety = %s", (p_nr,))
                            except Exception: pass
                    if p_id:
                        try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 0 WHERE id = %s", (p_id,))
                        except Exception: pass
                    if p_nr:
                        try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 0 WHERE nr_palety = %s", (p_nr,))
                        except Exception: pass

                cursor.execute("UPDATE magazyn_dostawy SET items = %s WHERE id = %s", (json.dumps(remaining_items), dostawa_id))
                conn.commit()

            accepted_count = sum(1 for i in remaining_items if i.get('accepted'))
            return True, {"total_items": len(remaining_items), "accepted_count": accepted_count, "items": remaining_items}
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def close_live_transfer(dostawa_id, login='system'):
        """Closes an active live transfer order and marks status as COMPLETED."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, items, status FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, f"Transfer order #{dostawa_id} not found"

            raw_items = dostawa.get('items')
            items = json.loads(raw_items) if isinstance(raw_items, str) else (raw_items or [])

            # Unblock any items
            for it in items:
                p_id = it.get('sourcePalletId') or it.get('id')
                p_nr = it.get('sourcePalletNo') or it.get('nr_palety')
                for l_code in ['PSD', 'AGRO']:
                    for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                        if p_id:
                            try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE id = %s", (p_id,))
                            except Exception: pass
                        if p_nr:
                            try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE nr_palety = %s", (p_nr,))
                            except Exception: pass

            cursor.execute("""
                UPDATE magazyn_dostawy
                SET status = 'COMPLETED', potwierdzone_przez = %s, potwierdzone_at = NOW()
                WHERE id = %s
            """, (login, dostawa_id))
            conn.commit()
            return True, "Zlecenie zostało pomyślnie zamknięte (status: COMPLETED)"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()


