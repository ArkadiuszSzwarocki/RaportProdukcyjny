from app.db import get_db_connection, get_table_name
from datetime import datetime
from app.utils.location_validator import validate_warehouse_location, is_production_tank_code

class WarehouseV2Service:
    @staticmethod
    def get_pallet_history(pallet_id, pallet_type, linia='PSD'):
        """Zwraca historię ruchów palety ściśle odseparowaną wg typu (Wyrób Gotowy / Surowiec / Opakowanie)."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            p_type_norm = str(pallet_type or '').strip().lower()
            if 'surow' in p_type_norm:
                allowed_types = ('surowiec', 'surowce')
                is_finished_good = False
                source_tbl = get_table_name('magazyn_surowce', linia)
            elif 'opakow' in p_type_norm:
                allowed_types = ('opakowanie', 'opakowania')
                is_finished_good = False
                source_tbl = get_table_name('magazyn_opakowania', linia)
            elif 'dodat' in p_type_norm:
                allowed_types = ('dodatek', 'dodatki')
                is_finished_good = False
                source_tbl = 'magazyn_dodatki'
            else:
                allowed_types = ('wyrob_gotowy', 'wyroby_gotowe', 'gotowy', 'wyrób gotowy')
                is_finished_good = True
                source_tbl = get_table_name('magazyn_palety', linia)

            real_id = None
            nr_pal_sscc = None
            try:
                cursor.execute(f"SELECT id, nr_palety FROM {source_tbl} WHERE id = %s OR nr_palety = %s LIMIT 1", (pallet_id, str(pallet_id)))
                row_found = cursor.fetchone()
                if row_found:
                    real_id = row_found.get('id')
                    nr_pal_sscc = row_found.get('nr_palety')
            except Exception:
                pass

            target_id = real_id if real_id is not None else pallet_id
            target_sscc = nr_pal_sscc if nr_pal_sscc else str(pallet_id)

            # 1. Pobieramy historię z palety_historia - priorytet dla unikalnego numeru SSCC (nr_palety)
            placeholders = ', '.join(['%s'] * len(allowed_types))
            if nr_pal_sscc:
                query_params = [nr_pal_sscc, target_id] + list(allowed_types)
                cursor.execute(f"""
                    SELECT id, akcja as typ_ruchu, komentarz, user_login as autor_login, data_ruchu as autor_data,
                           lokalizacja_zrodlowa, lokalizacja_docelowa
                    FROM palety_historia
                    WHERE (nr_palety = %s OR (nr_palety IS NULL AND paleta_id = %s AND LOWER(COALESCE(typ_palety, 'wyrob_gotowy')) IN ({placeholders})))
                    ORDER BY data_ruchu DESC
                """, tuple(query_params))
            else:
                query_params = [target_id, target_sscc] + list(allowed_types)
                cursor.execute(f"""
                    SELECT id, akcja as typ_ruchu, komentarz, user_login as autor_login, data_ruchu as autor_data,
                           lokalizacja_zrodlowa, lokalizacja_docelowa
                    FROM palety_historia
                    WHERE (paleta_id = %s OR nr_palety = %s)
                      AND LOWER(COALESCE(typ_palety, 'wyrob_gotowy')) IN ({placeholders})
                    ORDER BY data_ruchu DESC
                """, tuple(query_params))
            historia_nowa = cursor.fetchall() or []
            
            # 2. Pobieramy historię wsteczną ze starych tabel
            historia_stara = []
            if not is_finished_good:
                for t_ruch in ['magazyn_ruch', 'magazyn_agro_ruch']:
                    try:
                        cursor.execute(f"""
                            SELECT id, typ_ruchu, autor_login, COALESCE(autor_data, created_at) as autor_data, komentarz,
                                   NULL as lokalizacja_zrodlowa, NULL as lokalizacja_docelowa
                            FROM {t_ruch} 
                            WHERE surowiec_id = %s 
                            ORDER BY id DESC
                        """, (target_id,))
                        historia_stara.extend(cursor.fetchall() or [])
                    except Exception:
                        pass
            else:
                try:
                    cursor.execute(f"""
                        SELECT data_potwierdzenia as autor_data, user_login as autor_login, 'POTWIERDZENIE' as typ_ruchu, 'Rejestracja wyrobu' as komentarz,
                               NULL as lokalizacja_zrodlowa, NULL as lokalizacja_docelowa
                        FROM {source_tbl} WHERE id = %s OR nr_palety = %s
                    """, (target_id, target_sscc))
                    row = cursor.fetchone()
                    if row and row.get('autor_data'):
                        historia_stara.append(row)
                except Exception:
                    pass
                    
            # Combine
            combined = historia_nowa + historia_stara
            
            # Sort po dacie upewniając się, że autor_data jest datetime
            def get_dt(x):
                dt = x.get('autor_data')
                from datetime import datetime
                if isinstance(dt, datetime):
                    return dt
                if isinstance(dt, str):
                    try: return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                    except: pass
                return datetime.min
                
            combined.sort(key=get_dt, reverse=True)
            
            # Deduplikacja by nie wyświetlać tego samego ruchu dwa razy
            seen = set()
            deduped = []
            for h in combined:
                dt = get_dt(h)
                key = f"{dt.strftime('%Y-%m-%d %H:%M')}_{h.get('typ_ruchu')}_{h.get('autor_login')}"
                if key not in seen:
                    seen.add(key)
                    h['autor_data'] = dt.strftime('%Y-%m-%d %H:%M:%S') if dt != datetime.min else str(h.get('autor_data', ''))
                    deduped.append(h)
                    
            return deduped
        finally:
            conn.close()

    @staticmethod
    def move_pallet(pallet_id, pallet_type, new_location, worker_login, linia='PSD', amount_to_move=None):
        """Przenosi paletę na nową lokalizację. Jeśli amount_to_move < ilość systemowa, dzieli paletę."""
        
        if new_location:
            new_location = new_location.strip().upper()
            
            # --- ZASYP / PRZEKAZANIE NA PRODUKCJĘ ---
            from app.utils.location_validator import is_production_tank_code
            if is_production_tank_code(new_location):
                if pallet_type != 'Surowiec':
                    return False, f"BŁĄD: Do stacji zasypowej ({new_location}) można wydać tylko Surowce."
                    
                # Pobieramy ilość do wydania
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
                    
                # Wywołaj proces zasypu (dokładnie tak jak w skanerze głównym)
                from app.services.scanner_service import ScannerService
                try:
                    success, msg, extra_data = ScannerService.dispatch_to_production(
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
            from app.utils.location_validator import validate_warehouse_location
            is_valid, error_msg = validate_warehouse_location(new_location, allow_empty=False)
            if not is_valid:
                return False, error_msg

            # Sprawdzenie ze słownikiem dozwolonych lokalizacji (jak w głównym skanerze)
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
                    # Dokładne dopasowanie (np. MP01, K001)
                    if new_location == dozw_lok:
                        is_dict_valid = True
                        break
                    # Prefiksowe dopasowanie dla regałów i alejek (np. R01, A01, OS01, OSIP)
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

            # Pobierz stare dane do logu i podziału
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
                # Sprawdź czy to oczekujące przesunięcie / dostawa w magazyn_dostawy
                code_to_check = str(pallet_id or '').strip()
                if code_to_check:
                    try:
                        import json
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
                                            return True, f"Przyjęto przesunięcie i umieszczono paletę na lokalizacji: {new_location}"
                                        else:
                                            return False, f"Błąd przyjęcia przesunięcia: {msg_acc}"
                    except Exception as ex_acc:
                        print(f"Błąd auto-przyjęcia dostawy w move_pallet: {ex_acc}")

                # Sprawdź również transfer OSIP
                try:
                    from app.services.osip_transfer_service import OsipTransferService
                    ok_osip, msg_osip = OsipTransferService.auto_receive_pallet_by_code(code_to_check, new_location, worker_login)
                    if ok_osip:
                        return True, f"Przyjęto transfer OSIP na lokalizację: {new_location}"
                except Exception as ex_osip:
                    pass

                return False, "Paleta nie znaleziona."
                
            old_loc = row.get('lokalizacja')
            qty = float(row.get(col_qty) or 0)
            nr_palety = row.get('nr_palety')
            
            # --- PRZYJĘCIE W LOCIE DLA PALETY W ZLECENIU PRZESUNIĘCIA LUB BLOKADA JAKOŚCIOWA ---
            from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
            in_transfer, trf_ref = DeliveryQueries.is_pallet_in_pending_transfer(pallet_id=pallet_id, nr_palety=nr_palety)
            is_in_transfer_acceptance = bool(in_transfer)

            # Zwykła blokada jakościowa/ręczna (jeśli paleta NIE bierze udziału w otwartym zleceniu przesunięcia)
            if row.get('is_blocked') and not is_in_transfer_acceptance:
                return False, f"BŁĄD: Paleta {nr_palety or pallet_id} jest zablokowana ręcznie (blokada magazynowa) i nie może być przesuwana!"

            # SPRAWDZENIE CZY REGAŁ NIE JEST ZAJĘTY PRZEZ INNĄ PALETĘ
            if new_location and str(old_loc).strip().upper() != str(new_location).strip().upper():
                from app.utils.location_validator import check_rack_location_availability, validate_centrala_osip_move
                
                # Blokada bezpośrednich przesunięć Centrala <-> OSIP (wymagany transfer)
                is_trf_valid, trf_err_msg = validate_centrala_osip_move(
                    source_location=old_loc,
                    target_location=new_location,
                    pallet_id=pallet_id,
                    nr_palety=nr_palety
                )
                if not is_trf_valid:
                    return False, trf_err_msg

                is_loc_available, loc_error_msg = check_rack_location_availability(new_location, current_nr_palety=nr_palety)
                if not is_loc_available:
                    return False, loc_error_msg
            
            amount_to_move = float(amount_to_move) if amount_to_move is not None else qty
            
            if amount_to_move <= 0:
                return False, "Ilość do przeniesienia musi być większa od zera."
                
            if amount_to_move >= qty:
                # Przenosimy całą paletę
                cursor = conn.cursor()
                cursor.execute(f"UPDATE {table} SET lokalizacja = %s, is_blocked = 0 WHERE id = %s", (new_location, pallet_id))
                moved_qty = qty
            is_split = amount_to_move < qty
            if not is_split:
                # Cała paleta przenoszona
                cursor = conn.cursor()
                cursor.execute(f"UPDATE {table} SET lokalizacja = %s WHERE id = %s", (new_location, pallet_id))
                new_pallet_id = pallet_id
                target_pallet_sscc = nr_palety
            else:
                # Dzielenie palety (split)
                from app.utils.pallet_id import generate_pallet_id
                new_qty_old = qty - amount_to_move
                cursor = conn.cursor()
                cursor.execute(f"UPDATE {table} SET {col_qty} = %s WHERE id = %s", (new_qty_old, pallet_id))
                
                # Utwórz nową paletę z odciętą ilością i nowym numerem SSCC
                insert_data = dict(row)
                del insert_data['id'] # Usuń ID, żeby wygenerowało nowe
                insert_data['lokalizacja'] = new_location
                insert_data[col_qty] = amount_to_move
                insert_data['is_blocked'] = 0
                
                # Generujemy nowy unikalny numer SSCC
                new_sscc = generate_pallet_id(linia, pallet_type)
                insert_data['nr_palety'] = new_sscc
                target_pallet_sscc = new_sscc
                
                columns = ', '.join([f"`{k}`" for k in insert_data.keys()])
                placeholders = ', '.join(['%s'] * len(insert_data))
                values = list(insert_data.values())
                
                cursor.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)
                new_pallet_id = cursor.lastrowid
                moved_qty = amount_to_move
            
            # Zapisz ruch do historii
            table_ruch = get_table_name('magazyn_ruch', linia)
            try:
                cursor.execute(f"""
                    INSERT INTO {table_ruch} 
                    (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) 
                    VALUES (%s, 'PRZESUNIECIE', 0, %s, 'POTWIERDZONE', %s, %s, %s)
                """, (new_pallet_id, moved_qty, worker_login, datetime.now(), f"Z {old_loc or 'Brak'} do {new_location}" + (" (Podział)" if is_split else "")))

                mother_sscc = nr_palety or f"{pallet_type[:3].upper()}-{pallet_id}"
                now_dt = datetime.now()

                if is_split:
                    # Kopiowanie pełnej historii palety matki do nowo powstałej palety
                    cur_h = conn.cursor(dictionary=True)
                    cur_h.execute("""
                        SELECT linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu
                        FROM palety_historia
                        WHERE (paleta_id = %s OR (nr_palety IS NOT NULL AND nr_palety = %s))
                        ORDER BY data_ruchu ASC, id ASC
                    """, (pallet_id, mother_sscc))
                    for h in cur_h.fetchall() or []:
                        cursor.execute("""
                            INSERT INTO palety_historia
                            (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            new_pallet_id,
                            target_pallet_sscc,
                            h.get('linia') or linia,
                            h.get('typ_palety') or pallet_type.lower(),
                            h.get('akcja'),
                            h.get('lokalizacja_zrodlowa'),
                            h.get('lokalizacja_docelowa'),
                            h.get('komentarz'),
                            h.get('user_login'),
                            h.get('data_ruchu') or now_dt
                        ))

                    # Log podziału dla nowo utworzonej palety
                    cursor.execute("""
                        INSERT INTO palety_historia
                        (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu)
                        VALUES (%s, %s, %s, %s, 'PODZIAL_PALETY', %s, %s, %s, %s, %s)
                    """, (
                        new_pallet_id,
                        target_pallet_sscc,
                        linia,
                        pallet_type.lower(),
                        old_loc,
                        new_location,
                        f"Utworzono z podziału palety matki {mother_sscc} (odcięto {amount_to_move}). Przeniesiono na {new_location}",
                        worker_login,
                        now_dt
                    ))

                    # Log odjęcia ilości z palety matki
                    cursor.execute("""
                        INSERT INTO palety_historia
                        (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu)
                        VALUES (%s, %s, %s, %s, 'PODZIAL_ODJECIE', %s, %s, %s, %s, %s)
                    """, (
                        pallet_id,
                        mother_sscc,
                        linia,
                        pallet_type.lower(),
                        old_loc,
                        old_loc,
                        f"Odcięto {amount_to_move} podczas podziału palety do nowej palety {target_pallet_sscc}",
                        worker_login,
                        now_dt
                    ))
                else:
                    # Log to palety_historia dla palety przenoszonej w całości
                    cursor.execute("""
                        INSERT INTO palety_historia
                        (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login)
                        VALUES (%s, %s, %s, %s, 'PRZESUNIECIE', %s, %s, %s, %s)
                    """, (new_pallet_id, target_pallet_sscc, linia, pallet_type.lower(), old_loc, new_location, f"Przesunięcie z {old_loc or 'Brak'} do {new_location}", worker_login))
            except Exception as e:
                print("Błąd zapisu ruchu:", e)
                print("Błąd zapisu ruchu:", e)
            # --- AUTO-AKCEPTACJA DOSTAWY ZEWNĘTRZNEJ ---
            # Jeśli przenoszona paleta wisiała w "Oczekujące na Przyjęcie", zdejmujemy ją stamtąd.
            if nr_palety:
                try:
                    import json
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

            # --- AUTO-AKCEPTACJA PRZESUNIĘCIA OSIP ---
            try:
                from app.services.osip_transfer_service import OsipTransferService
                code_to_check = nr_palety or str(new_pallet_id)
                OsipTransferService.auto_receive_pallet_by_code(code_to_check, new_location, worker_login)
                if new_pallet_id and str(new_pallet_id) != str(code_to_check):
                    OsipTransferService.auto_receive_pallet_by_code(str(new_pallet_id), new_location, worker_login)
            except Exception as osip_e:
                print("Błąd podczas automatycznego przyjmowania transferu OSIP:", osip_e)
            
            conn.commit()
            if is_in_transfer_acceptance:
                return True, f"✅ Przyjęto w zleceniu {trf_ref} na regał: {new_location}"
            return True, "Pomyślnie przeniesiono."
        except Exception as e:
            if conn: conn.rollback()
            print(f"Error in move_pallet: {e}")
            return False, f"Błąd: {str(e)}"
        finally:
            if conn: conn.close()
            
    @staticmethod
    def toggle_block(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Przełącza status blokady palety."""
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

            cursor.execute(f"SELECT is_blocked, nr_palety FROM {table} WHERE id = %s", (pallet_id,))
            row = cursor.fetchone()
            if not row:
                return False, "Paleta nie znaleziona."
                
            new_status = 0 if row.get('is_blocked') else 1
            nr_p = row.get('nr_palety')
            cursor.execute(f"UPDATE {table} SET is_blocked = %s WHERE id = %s", (new_status, pallet_id))
            
            # Log to history
            action = 'BLOKADA' if new_status else 'ODBLOKOWANIE'
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (pallet_id, nr_p, linia, pallet_type.lower(), action, f"{action} palety przez użytkownika", worker_login)
            )
            
            conn.commit()
            return True, f"Paleta {'zablokowana' if new_status else 'odblokowana'}."
        finally:
            conn.close()

    @staticmethod
    def dispatch_pallet(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Wydaje paletę (przesuwa do archiwum z lokalizacją EXPEDITION)."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
                col_qty = 'stan_magazynowy'
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
                col_qty = 'stan_magazynowy'
            elif pallet_type == 'Dodatek':
                table = 'magazyn_dodatki'
                col_qty = 'stan_magazynowy'
            else:
                table = get_table_name('magazyn_palety', linia)
                col_qty = 'waga_netto'

            # 1. Pobierz dane
            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (pallet_id,))
            p = cursor.fetchone()
            if not p:
                return False, "Paleta nie znaleziona."
            
            if p.get('is_blocked'):
                return False, "NIE MOŻNA WYDAĆ ZABLOKOWANEJ PALETY!"
            
            # 2. Wstaw do archiwum z nową lokalizacją
            cursor.execute("""
                INSERT INTO magazyn_archiwum (original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, waga_ostatnia, lokalizacja_ostatnia, user_login, komentarz)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (p['id'], p.get('nr_palety'), p.get('nazwa') or p.get('produkt'), pallet_type, p.get('linia', linia), p.get('nr_partii'), p[col_qty], 'EXPEDITION', worker_login, f"Wydanie z {p.get('lokalizacja')}"))

            # 3. Usuń z aktywnego
            cursor.execute(f"DELETE FROM {table} WHERE id = %s", (pallet_id,))
            
            # Zapisz ruch do historii
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, %s, 'WYDANIE', %s, 'EXPEDITION', %s, %s)",
                    (pallet_id, p.get('nr_palety'), linia, pallet_type.lower(), p.get('lokalizacja'), f"Wydanie palety z {p.get('lokalizacja')}", worker_login)
                )
            except Exception as e:
                print("Błąd zapisu historii:", e)

            conn.commit()
            return True, "Paleta została wydana i zarchiwizowana."
        finally:
            conn.close()

    @staticmethod
    def archive_pallet(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Archiwizuje paletę (przenosi do magazyn_archiwum i usuwa z aktywnego)."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
                col_qty = 'stan_magazynowy'
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
                col_qty = 'stan_magazynowy'
            elif pallet_type == 'Dodatek':
                table = 'magazyn_dodatki'
                col_qty = 'stan_magazynowy'
            else:
                table = get_table_name('magazyn_palety', linia)
                col_qty = 'waga_netto'

            # 1. Pobierz dane do archiwum
            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (pallet_id,))
            p = cursor.fetchone()
            if not p:
                return False, "Paleta nie znaleziona."

            if p.get('is_blocked'):
                return False, "NIE MOŻNA ZARCHIWIZOWAĆ ZABLOKOWANEJ PALETY!"

            from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
            in_trf, trf_ref = DeliveryQueries.is_pallet_in_pending_transfer(pallet_id=pallet_id, nr_palety=p.get('nr_palety'))
            if in_trf:
                return False, f"BŁĄD: Paleta {p.get('nr_palety') or pallet_id} znajduje się na otwartej liście przesunięć #{trf_ref}. Archiwizacja niemożliwa!"

            # 2. Wstaw do archiwum
            cursor.execute("""
                INSERT INTO magazyn_archiwum (original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, waga_ostatnia, lokalizacja_ostatnia, user_login, komentarz)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (p['id'], p.get('nr_palety'), p.get('nazwa') or p.get('produkt'), pallet_type, p.get('linia', linia), p.get('nr_partii'), p[col_qty], p.get('lokalizacja'), worker_login, "Ręczna archiwizacja z dashboardu"))

            # 3. Usuń z aktywnego
            cursor.execute(f"DELETE FROM {table} WHERE id = %s", (pallet_id,))
            
            # Log to palety_historia
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, %s, 'ARCHIWIZACJA', %s, %s)",
                    (pallet_id, p.get('nr_palety'), linia, pallet_type.lower(), "Archiwizacja palety (przeniesienie do archiwum)", worker_login)
                )
            except Exception as e:
                print("Błąd zapisu historii:", e)

            conn.commit()
            return True, "Paleta została przeniesiona do archiwum."
        finally:
            conn.close()

    @staticmethod
    def rename_pallet(pallet_id, pallet_type, new_name, worker_login, linia='PSD'):
        """Zmienia nazwę produktu na palecie."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
            elif pallet_type == 'Dodatek':
                table = 'magazyn_dodatki'
            else:
                return False, "Nie można zmienić nazwy wyrobu gotowego."

            cursor.execute(f"UPDATE {table} SET nazwa = %s WHERE id = %s", (new_name, pallet_id))
            conn.commit()
            return True, "Nazwa zaktualizowana."
        finally:
            conn.close()

    @staticmethod
    def update_weight(pallet_id, pallet_type, new_weight, worker_login, linia='PSD'):
        """Aktualizuje wagę/ilość na palecie. Jeśli 0, archiwizuje."""
        new_weight = float(new_weight)
        if new_weight <= 0:
            return WarehouseV2Service.archive_pallet(pallet_id, pallet_type, worker_login, linia)
            
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
                col = 'stan_magazynowy'
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
                col = 'stan_magazynowy'
            elif pallet_type == 'Dodatek':
                table = 'magazyn_dodatki'
                col = 'stan_magazynowy'
            else:
                table = get_table_name('magazyn_palety', linia)
                col = 'waga_netto'

            # Pobierz starą wagę do logu
            cursor.execute(f"SELECT {col} FROM {table} WHERE id = %s", (int(pallet_id),))
            row = cursor.fetchone()
            if not row:
                return False, f"Błąd: Paleta o ID {pallet_id} nie istnieje."
                
            old_weight = float(row[0]) if row[0] is not None else 0.0

            cursor.execute(f"UPDATE {table} SET {col} = %s WHERE id = %s", (new_weight, int(pallet_id)))
            
            # Zapisz ruch do historii
            table_ruch = get_table_name('magazyn_ruch', linia)
            try:
                cursor.execute(f"""
                    INSERT INTO {table_ruch} 
                    (typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) 
                    VALUES ('KOREKTA_WAGI', %s, %s, 'POTWIERDZONE', %s, %s, %s)
                """, (new_weight - old_weight, new_weight, worker_login, datetime.now(), f"Ręczna zmiana wagi: {old_weight} -> {new_weight}"))
            except Exception as e:
                print(f"Błąd zapisu ruchu:", e)

            conn.commit()
            return True, f"Pomyślnie zaktualizowano wagę na {new_weight}."
        finally:
            conn.close()

    @staticmethod
    def return_pallet_to_raw(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Zwraca paletę wyrobów gotowych (np. z czyszczenia) jako Surowiec."""
        if pallet_type != 'Wyrób Gotowy':
            return False, "Tylko wyroby gotowe można zwrócić jako surowiec."
            
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_pal = get_table_name('magazyn_palety', linia)
            table_sur = get_table_name('magazyn_surowce', linia)
            
            # 1. Pobierz dane palety
            cursor.execute(f"SELECT nazwa_produktu, waga_netto, numer_palety FROM {table_pal} WHERE id = %s", (pallet_id,))
            pal = cursor.fetchone()
            if not pal:
                return False, "Paleta nie znaleziona."
                
            nazwa = pal['nazwa_produktu']
            waga = pal['waga_netto']
            nr_pal = pal['numer_palety']
            
            # 2. Wyzeruj wagę w wyrobach gotowych (archiwizacja)
            cursor.execute(f"UPDATE {table_pal} SET waga_netto = 0 WHERE id = %s", (pallet_id,))
            
            # 3. Dodaj jako surowiec (lokalizacja OSIP dla zwrotów)
            lokalizacja = 'OSIP' 
            
            cursor.execute(f"""
                INSERT INTO {table_sur} (nazwa, stan_magazynowy, lokalizacja) 
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE stan_magazynowy = stan_magazynowy + VALUES(stan_magazynowy)
            """, (nazwa, waga, lokalizacja))
            
            # 4. Log ruchu
            table_ruch = get_table_name('magazyn_ruch', linia)
            try:
                cursor.execute(f"""
                    INSERT INTO {table_ruch} 
                    (typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) 
                    VALUES ('ZWROT_Z_CZYSZCZENIA', %s, %s, 'POTWIERDZONE', %s, %s, %s)
                """, (waga, waga, worker_login, datetime.now(), f"Zwrot palety {nr_pal} ({nazwa}) jako surowiec do {lokalizacja}"))
            except Exception as e:
                print("Błąd zapisu ruchu:", e)

            conn.commit()
            return True, f"Paleta zwrócona jako surowiec do {lokalizacja}."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def update_packaging_type(pallet_id, pallet_type, new_packaging_type, worker_login, linia='PSD'):
        """Aktualizuje rodzaj opakowania na palecie (np. Big Bag (1000kg), Worek (25kg), Karton)."""
        if not new_packaging_type:
            return False, "Nie podano rodzaju opakowania."

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

            cursor.execute(f"SELECT id, nr_palety, typ_opakowania FROM {table} WHERE id = %s", (pallet_id,))
            row = cursor.fetchone()
            if not row:
                return False, f"Błąd: Paleta o ID {pallet_id} nie istnieje."

            old_pkg = row.get('typ_opakowania') or 'brak'
            cursor.execute(f"UPDATE {table} SET typ_opakowania = %s WHERE id = %s", (new_packaging_type, pallet_id))

            # Audit history log
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, %s, 'ZMIANA_OPAKOWANIA', %s, %s)",
                    (pallet_id, row.get('nr_palety'), linia, pallet_type.lower(), f"Zmiana opakowania: {old_pkg} -> {new_packaging_type}", worker_login)
                )
            except Exception as e:
                print(f"Błąd logowania historii zmiany opakowania: {e}")

            conn.commit()
            return True, "Rodzaj opakowania został pomyślnie zaktualizowany."
        except Exception as e:
            if conn: conn.rollback()
            return False, f"Błąd bazy danych: {str(e)}"
        finally:
            conn.close()

    @staticmethod
    def update_material_type(pallet_id, pallet_type, new_material_type, worker_login, linia='PSD'):
        """Aktualizuje typ materiału opakowania (Karton / Taśma) w typ_opakowania."""
        import sys
        print(f"[SERVICE] update_material_type: pallet_id={pallet_id}, type={pallet_type}, new_material={new_material_type}, linia={linia}", file=sys.stderr)
        
        if not new_material_type or new_material_type not in ('Karton', 'Taśma'):
            return False, "Błędny typ materiału. Wybierz 'Karton' lub 'Taśma'."

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
            else:
                return False, "Zmiana typu materiału dostępna tylko dla opakowań i surowców."

            print(f"[SERVICE] Table: {table}", file=sys.stderr)
            cursor.execute(f"SELECT id, nr_palety, typ_opakowania FROM {table} WHERE id = %s", (pallet_id,))
            row = cursor.fetchone()
            if not row:
                print(f"[SERVICE] Paleta nie znaleziona w tabeli {table}", file=sys.stderr)
                return False, f"Błąd: Paleta o ID {pallet_id} nie istnieje."

            old_material = row.get('typ_opakowania') or 'Karton'
            print(f"[SERVICE] Przed: {old_material}, Po: {new_material_type}", file=sys.stderr)
            cursor.execute(f"UPDATE {table} SET typ_opakowania = %s WHERE id = %s", (new_material_type, pallet_id))
            print(f"[SERVICE] UPDATE rowcount: {cursor.rowcount}", file=sys.stderr)

            # Audit history log
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, %s, 'ZMIANA_TYPU_MATERIALU', %s, %s)",
                    (pallet_id, row.get('nr_palety'), linia, pallet_type.lower(), f"Zmiana typu materiału: {old_material} -> {new_material_type}", worker_login)
                )
            except Exception as e:
                print(f"Błąd logowania historii zmiany typu materiału: {e}")

            conn.commit()
            print(f"[SERVICE] Commit OK", file=sys.stderr)
            return True, f"Typ materiału został zmieniony na '{new_material_type}'."
        except Exception as e:
            if conn: conn.rollback()
            print(f"[SERVICE] Exception: {str(e)}", file=sys.stderr)
            return False, f"Błąd bazy danych: {str(e)}"
        finally:
            conn.close()

    @staticmethod
    def bulk_update_material_type(pallet_ids: list, pallet_type: str, new_material_type: str, worker_login: str, linia: str = 'PSD') -> tuple[bool, str, int]:
        """Zbiorczo zmienia typ materiału dla wielu opakowań naraz."""
        if not pallet_ids or not new_material_type or new_material_type not in ('Karton', 'Taśma'):
            return False, "Błędne parametry", 0

        conn = get_db_connection()
        updated_count = 0
        try:
            cursor = conn.cursor(dictionary=True)
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
            else:
                return False, "Zmiana typu materiału dostępna tylko dla opakowań i surowców.", 0

            # Przygotuj listę ID dla zapytania
            id_placeholders = ','.join(['%s'] * len(pallet_ids))
            
            # Pobierz wszystkie rekordy do zalogowania
            cursor.execute(f"SELECT id, nr_palety, typ_opakowania FROM {table} WHERE id IN ({id_placeholders})", pallet_ids)
            rows = cursor.fetchall()
            
            if not rows:
                return False, "Nie znaleziono opakowań o podanych ID.", 0
            
            # Zaktualizuj wszystkie rekordy
            cursor.execute(
                f"UPDATE {table} SET typ_opakowania = %s WHERE id IN ({id_placeholders})",
                [new_material_type] + pallet_ids
            )
            updated_count = cursor.rowcount
            
            # Zaloguj każdą zmianę do historii
            try:
                for row in rows:
                    old_material = row.get('typ_opakowania') or 'Karton'
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, %s, 'ZMIANA_TYPU_MATERIALU_BULK', %s, %s)",
                        (row['id'], row.get('nr_palety'), linia, pallet_type.lower(), 
                         f"Zmiana typu materiału (bulk): {old_material} -> {new_material_type}", worker_login)
                    )
            except Exception as e:
                print(f"Błąd logowania historii zmiany zbiorczej: {e}")
            
            conn.commit()
            return True, f"Zmieniono typ materiału na '{new_material_type}' dla {updated_count} opakowań.", updated_count
        except Exception as e:
            if conn: conn.rollback()
            return False, f"Błąd bazy danych: {str(e)}", 0
        finally:
            conn.close()

    @staticmethod
    def restore_pallet_from_archive(archive_id: int = None, nr_palety: str = None, new_weight: float = None, new_location: str = None, user_login: str = 'admin') -> tuple[bool, str, dict]:
        """Przywraca paletę z tabeli magazyn_archiwum z powrotem do aktywnego magazynu."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # 1. Pobierz rekord z archiwum
            if archive_id:
                cursor.execute("SELECT * FROM magazyn_archiwum WHERE id = %s", (archive_id,))
            elif nr_palety:
                cursor.execute("SELECT * FROM magazyn_archiwum WHERE UPPER(TRIM(nr_palety)) = %s ORDER BY id DESC LIMIT 1", (nr_palety.strip().upper(),))
            else:
                return False, "Nie podano identyfikatora ani numeru palety do przywrócenia.", {}
                
            arc_row = cursor.fetchone()
            if not arc_row:
                return False, "Nie znaleziono palety w archiwum (być może została już przywrócona).", {}
                
            actual_archive_id = arc_row['id']
            pallet_nr = arc_row.get('nr_palety')
            pallet_name = arc_row.get('nazwa') or 'Surowiec'
            typ_palety = (arc_row.get('typ_palety') or 'surowiec').lower()
            linia = (arc_row.get('linia') or 'PSD').upper()
            nr_partii = arc_row.get('nr_partii') or ''
            
            loc = (new_location or arc_row.get('lokalizacja_ostatnia') or 'MP01').strip().upper()
            weight = float(new_weight if new_weight is not None else (arc_row.get('waga_ostatnia') or 0.0))
            if weight < 0:
                weight = 0.0
                
            # 2. Ustal docelową tabelę i kolumny
            if typ_palety == 'surowiec':
                table = get_table_name('magazyn_surowce', linia)
                col_amount = 'stan_magazynowy'
                col_name = 'nazwa'
            elif typ_palety == 'opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
                col_amount = 'stan_magazynowy'
                col_name = 'nazwa'
            elif typ_palety == 'dodatek':
                table = 'magazyn_dodatki'
                col_amount = 'stan_magazynowy'
                col_name = 'nazwa'
            else:
                table = get_table_name('magazyn_palety', linia)
                col_amount = 'waga_netto'
                col_name = 'produkt'
                
            # 3. Sprawdź czy taka paleta nie istnieje już w tabeli aktywnej
            if pallet_nr:
                cursor.execute(f"SELECT id FROM {table} WHERE nr_palety = %s", (pallet_nr,))
                existing = cursor.fetchone()
                if existing:
                    return False, f"Paleta o numerze {pallet_nr} już istnieje w magazynie aktywnym (ID: {existing['id']})!", {}
                    
            # 4. Pobierz ewentualne metadane (daty, opakowanie)
            dt_prod = None
            dt_przyd = None
            typ_opk = ''
            if pallet_nr:
                try:
                    cursor.execute("SELECT data_produkcji, data_przydatnosci, typ_opakowania FROM magazyn_inwentaryzacja_wpisy WHERE nr_palety = %s ORDER BY id DESC LIMIT 1", (pallet_nr,))
                    meta_row = cursor.fetchone()
                    if meta_row:
                        dt_prod = meta_row.get('data_produkcji')
                        dt_przyd = meta_row.get('data_przydatnosci')
                        typ_opk = meta_row.get('typ_opakowania') or ''
                except Exception:
                    pass

            # 5. Wstaw z powrotem do aktywnego magazynu
            if typ_palety == 'surowiec':
                cursor.execute(f"""
                    INSERT INTO {table} (nr_palety, {col_name}, {col_amount}, lokalizacja, nr_partii, linia, data_produkcji, data_przydatnosci, typ_opakowania)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (pallet_nr, pallet_name, weight, loc, nr_partii, linia, dt_prod, dt_przyd, typ_opk))
            elif typ_palety == 'opakowanie':
                cursor.execute(f"""
                    INSERT INTO {table} (nr_palety, {col_name}, {col_amount}, lokalizacja, nr_partii, linia)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (pallet_nr, pallet_name, weight, loc, nr_partii, linia))
            else:
                cursor.execute(f"""
                    INSERT INTO {table} (nr_palety, {col_name}, {col_amount}, lokalizacja, linia)
                    VALUES (%s, %s, %s, %s, %s)
                """, (pallet_nr, pallet_name, weight, loc, linia))
                
            new_id = cursor.lastrowid
            
            # 6. Rejestracja w palety_historia
            cursor.execute("""
                INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login)
                VALUES (%s, %s, %s, %s, 'PRZYWROCENIE_Z_ZUZYCIA', %s, %s, %s)
            """, (new_id, pallet_nr, linia, typ_palety, loc, f'Przywrócono z zużycia/archiwum przez {user_login}. Waga: {weight} kg, lokalizacja: {loc}. Partia: {nr_partii}', user_login))
            
            # 7. Usunięcie z magazyn_archiwum
            cursor.execute("DELETE FROM magazyn_archiwum WHERE id = %s", (actual_archive_id,))
            
            conn.commit()
            
            restored_info = {
                'id': new_id,
                'nr_palety': pallet_nr,
                'nazwa': pallet_name,
                'waga': weight,
                'lokalizacja': loc,
                'typ_palety': typ_palety,
                'linia': linia,
                'nr_partii': nr_partii
            }
            return True, f"Paleta {pallet_nr or pallet_name} została pomyślnie przywrócona na lokalizację {loc} z wagą {weight} kg.", restored_info
        except Exception as e:
            if conn: conn.rollback()
            return False, f"Błąd bazy danych podczas przywracania palety: {str(e)}", {}
        finally:
            conn.close()


