from app.db import get_db_connection, get_table_name
from datetime import datetime
from app.utils.location_validator import validate_warehouse_location, is_production_tank_code

class WarehouseV2Service:
    @staticmethod
    def get_pallet_history(pallet_id, pallet_type, linia='PSD'):
        """Zwraca historię ruchów palety."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Pobieramy pełną historię z nowej tabeli palety_historia
            cursor.execute("""
                SELECT id, akcja as typ_ruchu, komentarz, user_login as autor_login, data_ruchu as autor_data
                FROM palety_historia
                WHERE paleta_id = %s
                ORDER BY data_ruchu DESC
            """, (pallet_id,))
            historia_nowa = cursor.fetchall()
            
            # Pobieramy historię wsteczną z tabel legacy
            table_ruch = get_table_name('magazyn_ruch', linia)
            historia_stara = []
            
            if pallet_type in ['Surowiec', 'Opakowanie']:
                cursor.execute(f"""
                    SELECT id, typ_ruchu, autor_login, autor_data, komentarz 
                    FROM {table_ruch} 
                    WHERE surowiec_id = %s 
                    ORDER BY autor_data DESC
                """, (pallet_id,))
                historia_stara = cursor.fetchall()
            else:
                cursor.execute(f"SELECT data_potwierdzenia as autor_data, user_login as autor_login, 'POTWIERDZENIE' as typ_ruchu, 'Rejestracja wyrobu' as komentarz FROM {get_table_name('magazyn_palety', linia)} WHERE id = %s", (pallet_id,))
                row = cursor.fetchone()
                if row:
                    historia_stara.append(row)
                    
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
            
            # Deduplikacja by nie wyświetlać tego samego ruchu dwa razy jeśli został zapisany w obu tabelach
            seen = set()
            deduped = []
            for h in combined:
                # prosty klucz deduplikacyjny na podstawie daty (co do minuty) i typu ruchu
                dt = get_dt(h)
                key = f"{dt.strftime('%Y-%m-%d %H:%M')}_{h.get('typ_ruchu')}_{h.get('autor_login')}"
                if key not in seen:
                    seen.add(key)
                    # Format date to string for JSON serialization
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
                    if new_location.startswith(dozw_lok):
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
            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (pallet_id,))
            row = cursor.fetchone()
            if not row:
                return False, "Paleta nie znaleziona."
                
            if row.get('is_blocked'):
                return False, f"BŁĄD: Paleta #{pallet_id} jest ZABLOKOWANA i nie może być przenoszona!"
                
            old_loc = row.get('lokalizacja')
            qty = float(row.get(col_qty) or 0)
            nr_palety = row.get('nr_palety')
            
            # SPRAWDZENIE CZY REGAŁ NIE JEST ZAJĘTY PRZEZ INNĄ PALETĘ
            if new_location and str(old_loc).strip().upper() != str(new_location).strip().upper():
                from app.utils.location_validator import check_rack_location_availability
                is_loc_available, loc_error_msg = check_rack_location_availability(new_location, current_nr_palety=nr_palety)
                if not is_loc_available:
                    return False, loc_error_msg
            
            amount_to_move = float(amount_to_move) if amount_to_move is not None else qty
            
            if amount_to_move <= 0:
                return False, "Ilość do przeniesienia musi być większa od zera."
                
            if amount_to_move >= qty:
                # Przenosimy całą paletę
                cursor = conn.cursor()
                cursor.execute(f"UPDATE {table} SET lokalizacja = %s WHERE id = %s", (new_location, pallet_id))
                moved_qty = qty
                new_pallet_id = pallet_id
            else:
                # Dzielenie palety (split)
                new_qty_old = qty - amount_to_move
                cursor = conn.cursor()
                cursor.execute(f"UPDATE {table} SET {col_qty} = %s WHERE id = %s", (new_qty_old, pallet_id))
                
                # Utwórz nową paletę z odciętą ilością
                insert_data = dict(row)
                del insert_data['id'] # Usuń ID, żeby wygenerowało nowe
                insert_data['lokalizacja'] = new_location
                insert_data[col_qty] = amount_to_move
                # Zerujemy nr_palety by wymusić ewentualne wydrukowanie nowej etykiety
                insert_data['nr_palety'] = None
                
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
                """, (new_pallet_id, moved_qty, worker_login, datetime.now(), f"Z {old_loc or 'Brak'} do {new_location}" + (" (Podział)" if amount_to_move < qty else "")))

                # Log to palety_historia dla palety przenoszonej/nowej
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (new_pallet_id, linia, pallet_type.lower(), 'PRZESUNIECIE_PODZIAL' if amount_to_move < qty else 'PRZESUNIECIE', old_loc, new_location, f"Przesunięcie z {old_loc or 'Brak'} do {new_location}" + (f" (Podział: przeniesiono {amount_to_move})" if amount_to_move < qty else ""), worker_login)
                )
                
                # Dodatkowy log dla starej palety jeśli był podział
                if amount_to_move < qty:
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'PODZIAL_ODJECIE', %s, %s, %s, %s)",
                        (pallet_id, linia, pallet_type.lower(), old_loc, old_loc, f"Odjęto {amount_to_move} podczas podziału palety", worker_login)
                    )
            except Exception as e:
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
                                cur_dict.execute("UPDATE magazyn_dostawy SET items = %s, status = %s WHERE id = %s", (json.dumps(d_items), new_status, d['id']))
                                
                                if new_status == 'COMPLETED':
                                    try:
                                        from flask import url_for
                                        from app.services.office_print_service import trigger_office_print_url
                                        report_url = url_for(
                                            'magazyn_dostawy.raport_przesuniecia',
                                            dostawa_id=d['id'],
                                            linia=linia,
                                            internal_print=1,
                                            _external=True
                                        )
                                        trigger_office_print_url(report_url, 'raport_dostawy_zewnetrznej', prefix="dostawa_zewn_")
                                    except Exception as print_e:
                                        print("Błąd uruchomienia wydruku raportu po przyjęciu:", print_e)
                                        
                        except Exception as inner_e:
                            print("Błąd podczas przetwarzania pozycji w dostawie:", inner_e)
                except Exception as e:
                    print("Błąd podczas automatycznego przyjmowania dostawy ze skanera:", e)
            
            conn.commit()
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
            cursor = conn.cursor()
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
            elif pallet_type == 'Dodatek':
                table = 'magazyn_dodatki'
            else:
                table = get_table_name('magazyn_palety', linia)

            cursor.execute(f"SELECT is_blocked FROM {table} WHERE id = %s", (pallet_id,))
            row = cursor.fetchone()
            if not row:
                return False, "Paleta nie znaleziona."
                
            new_status = 0 if row[0] else 1
            cursor.execute(f"UPDATE {table} SET is_blocked = %s WHERE id = %s", (new_status, pallet_id))
            
            # Log to history
            action = 'BLOKADA' if new_status else 'ODBLOKOWANIE'
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, %s, %s, %s)",
                (pallet_id, linia, pallet_type.lower(), action, f"{action} palety przez użytkownika", worker_login)
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
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'WYDANIE', %s, 'EXPEDITION', %s, %s)",
                    (pallet_id, linia, pallet_type.lower(), p.get('lokalizacja'), f"Wydanie palety z {p.get('lokalizacja')}", worker_login)
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
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, 'ARCHIWIZACJA', %s, %s)",
                    (pallet_id, linia, pallet_type.lower(), "Archiwizacja palety (przeniesienie do archiwum)", worker_login)
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
