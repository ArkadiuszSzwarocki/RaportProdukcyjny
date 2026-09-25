import re
import json
from datetime import datetime
from app.db import get_db_connection, get_table_name
from app.utils.location_validator import (
    validate_warehouse_location,
    is_production_tank_code,
    check_rack_location_availability,
    validate_centrala_osip_move
)
from app.utils.pallet_id import generate_pallet_id
from app.services.warehouse_history.movement_recorder import MovementRecorder

class PalletRelocationService:
    @staticmethod
    def move_pallet(pallet_id, pallet_type, new_location, worker_login, linia='PSD', amount_to_move=None):
        """Relocate pallet, validate location constraints, and handle splitting / partial movements."""
        if new_location:
            new_location = new_location.strip().upper()
            
            # --- PRZEKAZANIE NA PRODUKCJĘ (ZASYP) ---
            if is_production_tank_code(new_location):
                if pallet_type != 'Surowiec':
                    return False, f"BŁĄD: Do stacji zasypowej ({new_location}) można wydać tylko Surowce."
                    
                conn_tmp = get_db_connection()
                try:
                    cur_tmp = conn_tmp.cursor()
                    table_surowce = get_table_name('magazyn_surowce', linia)
                    cur_tmp.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (pallet_id,))
                    row_tmp = cur_tmp.fetchone()
                    if not row_tmp:
                        return False, "Nie znaleziono palety surowca."
                    qty = amount_to_move if amount_to_move is not None else float(row_tmp[0])
                finally:
                    conn_tmp.close()
                    
                from app.services.scanner_service import ScannerService
                try:
                    success, msg, _ = ScannerService.dispatch_to_production(
                        surowiec_id=pallet_id,
                        ilosc=qty,
                        worker_login=worker_login,
                        linia=linia,
                        zbiornik=new_location,
                        komentarz="Zasyp (z panelu magazynu)"
                    )
                    if success:
                        return True, f"Przekazano na produkcję ({new_location})."
                    return False, f"Błąd przekazania: {msg}"
                except Exception as e:
                    return False, f"Błąd krytyczny zasypu: {str(e)}"
                    
            # --- ZWYKŁE PRZESUNIĘCIE MAGAZYNOWE ---
            is_valid, error_msg = validate_warehouse_location(new_location, allow_empty=False)
            if not is_valid:
                return False, error_msg

            conn_dict = get_db_connection()
            try:
                cur_dict = conn_dict.cursor()
                cur_dict.execute("SELECT nazwa FROM magazyn_dozwolone_lokalizacje")
                dozwolone = [row[0].upper() for row in cur_dict.fetchall()]
            except Exception as e:
                dozwolone = []
                print(f"Błąd ładowania słownika lokalizacji: {e}")
            finally:
                conn_dict.close()

            if dozwolone:
                is_dict_valid = False
                for dozw_lok in dozwolone:
                    if new_location == dozw_lok:
                        is_dict_valid = True
                        break
                    elif (dozw_lok.startswith('R') or dozw_lok.startswith('A') or dozw_lok.startswith('OS')) and new_location.startswith(dozw_lok):
                        is_dict_valid = True
                        break
                
                if not is_dict_valid:
                    return False, f"BŁĄD: Lokalizacja '{new_location}' nie występuje w dozwolonym słowniku (Baza: Ustawienia)."

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
            elif pallet_type == 'Dodatek':
                table = 'magazyn_dodatki'
            else:
                table = get_table_name('magazyn_palety', linia)

            col_qty = 'waga_netto' if pallet_type == 'Wyrób Gotowy' else 'stan_magazynowy'
            row = None
            if isinstance(pallet_id, int) or (isinstance(pallet_id, str) and pallet_id.isdigit()):
                cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (int(pallet_id),))
                row = cursor.fetchone()
            if not row:
                cursor.execute(f"SELECT * FROM {table} WHERE nr_palety = %s", (str(pallet_id),))
                row = cursor.fetchone()
            if not row and pallet_type != 'Dodatek':
                alt_linia = 'PSD' if str(linia).upper() == 'AGRO' else 'AGRO'
                if pallet_type == 'Surowiec':
                    alt_table = get_table_name('magazyn_surowce', alt_linia)
                elif pallet_type == 'Opakowanie':
                    alt_table = get_table_name('magazyn_opakowania', alt_linia)
                else:
                    alt_table = get_table_name('magazyn_palety', alt_linia)
                if isinstance(pallet_id, int) or (isinstance(pallet_id, str) and pallet_id.isdigit()):
                    cursor.execute(f"SELECT * FROM {alt_table} WHERE id = %s", (int(pallet_id),))
                    alt_row = cursor.fetchone()
                else:
                    alt_row = None
                if not alt_row:
                    cursor.execute(f"SELECT * FROM {alt_table} WHERE nr_palety = %s", (str(pallet_id),))
                    alt_row = cursor.fetchone()
                if alt_row:
                    table = alt_table
                    linia = alt_linia
                    row = alt_row

            if not row:
                code_to_check = str(pallet_id or '').strip()
                if code_to_check:
                    try:
                        from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
                        cursor.execute("SELECT id, items FROM magazyn_dostawy WHERE status IN ('OCZEKUJE', 'IN_PROGRESS')")
                        pending_orders = cursor.fetchall()
                        for o in pending_orders:
                            items_data = json.loads(o.get('items') or '[]')
                            for item in items_data:
                                if not item.get('accepted') and not item.get('rejected'):
                                    it_nr = str(item.get('nr_palety') or item.get('sourcePalletNo') or '').strip().upper()
                                    it_id = str(item.get('id') or item.get('sourcePalletId') or '')
                                    if (it_nr and it_nr == code_to_check.upper()) or (it_id and it_id == code_to_check):
                                        ok_acc, msg_acc, _ = AcceptanceService.accept_item(
                                            o['id'],
                                            item['id'],
                                            new_location,
                                            worker_login
                                        )
                                        if ok_acc:
                                            return True, f"Przyjęto przesunięcie i umieszczono paletę na lokalizacji: {new_location}", None
                                        else:
                                            return False, f"Błąd przyjęcia przesunięcia: {msg_acc}", None
                    except Exception as ex_acc:
                        print(f"Błąd auto-przyjęcia dostawy w move_pallet: {ex_acc}")

                try:
                    from app.services.osip_transfer_service import OsipTransferService
                    ok_osip, _ = OsipTransferService.auto_receive_pallet_by_code(code_to_check, new_location, worker_login)
                    if ok_osip:
                        return True, f"Przyjęto transfer OSIP na lokalizację: {new_location}", None
                except Exception:
                    pass

                return False, "Paleta nie znaleziona.", None
                
            old_loc = row.get('lokalizacja')
            qty = float(row.get(col_qty) or 0)
            nr_palety = row.get('nr_palety')

            if pallet_type == 'Surowiec':
                from app.utils.surowiec_validator import is_valid_surowiec
                s_name = row.get('nazwa')
                if not is_valid_surowiec(s_name):
                    return False, f"BŁĄD: Surowiec '{s_name}' nie istnieje w słowniku surowców. Przesunięcie zablokowane.", None
            
            from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
            in_transfer, trf_ref = DeliveryQueries.is_pallet_in_pending_transfer(pallet_id=pallet_id, nr_palety=nr_palety)
            is_in_transfer_acceptance = bool(in_transfer)

            if row.get('is_blocked') and not is_in_transfer_acceptance:
                return False, f"BŁĄD: Paleta {nr_palety or pallet_id} jest zablokowana ręcznie (blokada magazynowa) i nie może być przesuwana!", None

            if new_location and str(old_loc).strip().upper() != str(new_location).strip().upper():
                is_trf_valid, trf_err_msg = validate_centrala_osip_move(
                    source_location=old_loc,
                    target_location=new_location,
                    pallet_id=pallet_id,
                    nr_palety=nr_palety
                )
                if not is_trf_valid:
                    return False, trf_err_msg, None

                is_loc_available, loc_error_msg = check_rack_location_availability(new_location, current_nr_palety=nr_palety)
                if not is_loc_available:
                    return False, loc_error_msg, None
            
            amount_to_move = float(amount_to_move) if amount_to_move is not None else qty
            
            if amount_to_move <= 0:
                return False, "Ilość do przeniesienia musi być większa od zera.", None
                
            real_pallet_id = row.get('id')
            if amount_to_move >= qty:
                cursor = conn.cursor()
                cursor.execute(f"UPDATE {table} SET lokalizacja = %s, is_blocked = 0 WHERE id = %s", (new_location, real_pallet_id))
                moved_qty = qty
            
            is_split = amount_to_move < qty
            if not is_split:
                cursor = conn.cursor()
                target_pallet_sscc = nr_palety
                if not target_pallet_sscc or re.match(r'^(SUR|OPK|DOD|PAL)-?\d{1,8}$', str(target_pallet_sscc), re.IGNORECASE):
                    target_pallet_sscc = generate_pallet_id(linia, pallet_type)
                    cursor.execute(f"UPDATE {table} SET nr_palety = %s, lokalizacja = %s WHERE id = %s", (target_pallet_sscc, new_location, real_pallet_id))
                else:
                    cursor.execute(f"UPDATE {table} SET lokalizacja = %s WHERE id = %s", (new_location, real_pallet_id))
                new_pallet_id = real_pallet_id
                mother_sscc = nr_palety
            else:
                new_qty_old = qty - amount_to_move
                cursor = conn.cursor()
                cursor.execute(f"UPDATE {table} SET {col_qty} = %s WHERE id = %s", (new_qty_old, real_pallet_id))
                
                insert_data = dict(row)
                del insert_data['id']
                insert_data['lokalizacja'] = new_location
                insert_data[col_qty] = amount_to_move
                insert_data['is_blocked'] = 0
                
                new_sscc = generate_pallet_id(linia, pallet_type)
                insert_data['nr_palety'] = new_sscc
                target_pallet_sscc = new_sscc
                
                columns = ', '.join([f"`{k}`" for k in insert_data.keys()])
                placeholders = ', '.join(['%s'] * len(insert_data))
                values = list(insert_data.values())
                
                cursor.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)
                new_pallet_id = cursor.lastrowid
                moved_qty = amount_to_move
                mother_sscc = nr_palety
            
            table_ruch = get_table_name('magazyn_ruch', linia)
            mat_name = row.get('nazwa') or row.get('produkt') or ''
            is_lp01 = (str(new_location).strip().upper() == 'LP01')
            typ_ruchu_log = 'WYDANIE_NA_MASZYNE' if is_lp01 else 'PRZESUNIECIE'
            komentarz_lp01 = f"Wydanie materiału na maszynę LP01 z {old_loc or 'Brak'}" + (" (Podział)" if is_split else "")
            komentarz_ruch = komentarz_lp01 if is_lp01 else (f"Z {old_loc or 'Brak'} do {new_location}" + (" (Podział)" if is_split else ""))
            
            try:
                cursor.execute(f"""
                    INSERT INTO {table_ruch} 
                    (surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, autor_login, autor_data, komentarz) 
                    VALUES (%s, %s, %s, %s, %s, %s, 'POTWIERDZONE', %s, %s, %s)
                """, (new_pallet_id, mat_name, typ_ruchu_log, moved_qty, moved_qty, new_location, worker_login, datetime.now(), komentarz_ruch))
                movement_id = cursor.lastrowid
                operation_id = f"{table_ruch}:{movement_id}"

                if not mother_sscc or re.match(r'^(SUR|OPK|DOD|PAL)-?\d{1,8}$', str(mother_sscc), re.IGNORECASE):
                    mother_sscc = generate_pallet_id(linia, pallet_type)
                    cursor.execute(f"UPDATE {table} SET nr_palety = %s WHERE id = %s", (mother_sscc, real_pallet_id))
                now_dt = datetime.now()

                if is_split:
                    # Do not clone the mother's history. The child gets a single lineage
                    # event; older events remain attached exclusively to the mother SSCC.
                    child_saved = MovementRecorder.record_movement(
                        new_pallet_id, linia, pallet_type, 'UTWORZENIE_Z_PODZIALU',
                        old_loc, new_location,
                        f"Utworzono z podziału palety matki {mother_sscc} (odcięto {amount_to_move}). " + (f"Wydano na maszynę LP01" if is_lp01 else f"Przeniesiono na {new_location}"),
                        worker_login, target_pallet_sscc,
                        cursor=cursor, connection=conn, operation_id=operation_id,
                        quantity_before=0, quantity_after=amount_to_move, occurred_at=now_dt,
                    )
                    mother_saved = MovementRecorder.record_movement(
                        real_pallet_id, linia, pallet_type, 'PODZIAL_ODJECIE',
                        old_loc, old_loc,
                        f"Odcięto {amount_to_move} podczas podziału palety do nowej palety {target_pallet_sscc}" + (f" (Wydanie na maszynę LP01)" if is_lp01 else ""),
                        worker_login, mother_sscc,
                        cursor=cursor, connection=conn, operation_id=operation_id,
                        quantity_before=qty, quantity_after=qty - amount_to_move, occurred_at=now_dt,
                    )
                    if not child_saved or not mother_saved:
                        raise RuntimeError("Nie udało się zapisać historii podziału palety")
                else:
                    history_saved = MovementRecorder.record_movement(
                        new_pallet_id, linia, pallet_type, typ_ruchu_log,
                        old_loc, new_location,
                        komentarz_lp01 if is_lp01 else f"Przesunięcie z {old_loc or 'Brak'} do {new_location}",
                        worker_login, target_pallet_sscc,
                        cursor=cursor, connection=conn, operation_id=operation_id,
                        quantity_before=qty, quantity_after=qty, occurred_at=now_dt,
                    )
                    if not history_saved:
                        raise RuntimeError("Nie udało się zapisać historii przesunięcia palety")
            except Exception as e:
                raise RuntimeError(f"Błąd zapisu ruchu: {e}") from e

            # Auto-accept in pending deliveries
            if nr_palety:
                try:
                    cur_dict = conn.cursor(dictionary=True)
                    cur_dict.execute("SELECT id, items FROM magazyn_dostawy WHERE status = 'OCZEKUJE'")
                    pending_deliveries = cur_dict.fetchall()
                    for d in pending_deliveries:
                        if not d.get('items'): continue
                        try:
                            d_items = json.loads(d['items'])
                            changed = False
                            for item in d_items:
                                if not item.get('accepted') and not item.get('rejected'):
                                    if item.get('nr_palety') == nr_palety or item.get('sourcePalletNo') == nr_palety:
                                        item['accepted'] = True
                                        item['accepted_by'] = worker_login
                                        item['accepted_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                        item['lokalizacja_przyjecia'] = new_location
                                        changed = True
                            if changed:
                                all_processed = all(i.get('accepted') or i.get('rejected') for i in d_items)
                                new_status = 'COMPLETED' if all_processed else 'OCZEKUJE'
                                cur_dict.execute(
                                    """
                                    UPDATE magazyn_dostawy 
                                    SET items = %s, status = %s, 
                                        potwierdzone_przez = IF(%s, COALESCE(potwierdzone_przez, %s), potwierdzone_przez), 
                                        potwierdzone_at = IF(%s, COALESCE(potwierdzone_at, NOW()), potwierdzone_at) 
                                    WHERE id = %s
                                    """,
                                    (json.dumps(d_items), new_status, 1 if all_processed else 0, worker_login, 1 if all_processed else 0, d['id'])
                                )
                        except Exception as inner_e:
                            print("Błąd podczas przetwarzania pozycji w dostawie:", inner_e)
                except Exception as e:
                    print("Błąd podczas automatycznego przyjmowania dostawy ze skanera:", e)

            try:
                from app.services.osip_transfer_service import OsipTransferService
                code_to_check = nr_palety or str(new_pallet_id)
                OsipTransferService.auto_receive_pallet_by_code(code_to_check, new_location, worker_login)
                if new_pallet_id and str(new_pallet_id) != str(code_to_check):
                    OsipTransferService.auto_receive_pallet_by_code(str(new_pallet_id), new_location, worker_login)
            except Exception as osip_e:
                print("Błąd podczas automatycznego przyjmowania transferu OSIP:", osip_e)
            
            split_info = {
                'is_split': bool(is_split),
                'new_sscc': target_pallet_sscc if is_split else None,
                'new_pallet_id': new_pallet_id,
                'mother_sscc': mother_sscc,
                'mother_pallet_id': pallet_id,
                'moved_qty': moved_qty,
                'remaining_qty': (qty - amount_to_move) if is_split else qty,
                'new_location': new_location,
                'pallet_type': pallet_type,
            }

            conn.commit()
            if is_in_transfer_acceptance:
                return True, f"✅ Przyjęto w zleceniu {trf_ref} na regał: {new_location}", split_info
            if is_lp01:
                return True, f"✅ Pomyślnie wydano materiał na maszynę LP01 ({moved_qty} szt/kg).", split_info
            if is_split:
                return True, f"✅ Pomyślnie odcięto {moved_qty} kg na nową paletę {target_pallet_sscc} (lokalizacja: {new_location}). Pozostało na matce: {qty - amount_to_move} kg.", split_info
            return True, "Pomyślnie przeniesiono.", split_info
        except Exception as e:
            if conn: conn.rollback()
            print(f"Error in move_pallet: {e}")
            return False, f"Błąd: {str(e)}", None
        finally:
            if conn: conn.close()
