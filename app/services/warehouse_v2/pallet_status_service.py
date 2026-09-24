from app.db import get_db_connection, get_table_name

class PalletStatusService:
    @staticmethod
    def toggle_block(pallet_id, pallet_type, worker_login, linia='PSD', sscc=None, reason=None):
        """Toggle lock/block status of a pallet, keeping warehouse and buffer tables in sync."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            p_type_norm = str(pallet_type or '').strip().lower()
            target_sscc = str(sscc).strip() if sscc else None
            
            # Find the pallet across tables to determine current status and nr_palety
            if 'surow' in p_type_norm:
                tables_to_check = [get_table_name('magazyn_surowce', linia)]
            elif 'opakow' in p_type_norm:
                tables_to_check = [get_table_name('magazyn_opakowania', linia)]
            elif 'dodat' in p_type_norm:
                tables_to_check = ['magazyn_dodatki']
            else:
                tables_to_check = ['magazyn_palety', 'magazyn_palety_agro', 'palety_workowanie', 'palety_agro']

            found_row = None
            for tbl in tables_to_check:
                try:
                    cursor.execute(
                        f"SELECT id, is_blocked, nr_palety FROM {tbl} WHERE id = %s OR (nr_palety IS NOT NULL AND nr_palety = %s)",
                        (pallet_id if str(pallet_id).isdigit() else -1, target_sscc or str(pallet_id))
                    )
                    row = cursor.fetchone()
                    if row:
                        found_row = row
                        break
                except Exception:
                    pass

            if not found_row:
                all_tables = ['magazyn_palety', 'magazyn_palety_agro', 'palety_workowanie', 'palety_agro', 'magazyn_surowce', 'magazyn_opakowania', 'magazyn_dodatki']
                for tbl in all_tables:
                    try:
                        cursor.execute(
                            f"SELECT id, is_blocked, nr_palety FROM {tbl} WHERE id = %s OR (nr_palety IS NOT NULL AND nr_palety = %s)",
                            (pallet_id if str(pallet_id).isdigit() else -1, target_sscc or str(pallet_id))
                        )
                        row = cursor.fetchone()
                        if row:
                            found_row = row
                            break
                    except Exception:
                        pass

            if not found_row:
                return False, "Paleta nie znaleziona."

            new_status = 0 if found_row.get('is_blocked') else 1
            nr_p = found_row.get('nr_palety') or target_sscc or str(pallet_id)

            # Update ALL tables where this pallet (by nr_palety or id) exists to keep them in sync
            synced_tables = ['magazyn_palety', 'magazyn_palety_agro', 'palety_workowanie', 'palety_agro', 'magazyn_surowce', 'magazyn_opakowania', 'magazyn_dodatki']
            for tbl in synced_tables:
                try:
                    if nr_p and nr_p != str(pallet_id):
                        cursor.execute(
                            f"UPDATE {tbl} SET is_blocked = %s WHERE nr_palety = %s OR id = %s",
                            (new_status, nr_p, pallet_id if str(pallet_id).isdigit() else -1)
                        )
                    else:
                        cursor.execute(
                            f"UPDATE {tbl} SET is_blocked = %s WHERE id = %s OR nr_palety = %s",
                            (new_status, pallet_id if str(pallet_id).isdigit() else -1, str(pallet_id))
                        )
                except Exception:
                    pass

            action = 'BLOKADA' if new_status else 'ODBLOKOWANIE'
            comment = f"{action}: {reason}" if reason and new_status else f"{action} palety przez użytkownika"
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (pallet_id if str(pallet_id).isdigit() else found_row.get('id'), nr_p, linia, pallet_type.lower() if pallet_type else 'wyrob_gotowy', action, comment, worker_login)
                )
            except Exception:
                pass

            conn.commit()
            return True, f"Paleta {'zablokowana' if new_status else 'odblokowana'}."
        finally:
            conn.close()

    @staticmethod
    def dispatch_pallet(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Dispatch a pallet to EXPEDITION and move it to archive."""
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

            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (pallet_id,))
            p = cursor.fetchone()
            if not p:
                return False, "Paleta nie znaleziona."
            
            if p.get('is_blocked'):
                return False, "NIE MOŻNA WYDAĆ ZABLOKOWANEJ PALETY!"
            
            cursor.execute("""
                INSERT INTO magazyn_archiwum (original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, waga_ostatnia, lokalizacja_ostatnia, user_login, komentarz)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (p['id'], p.get('nr_palety'), p.get('nazwa') or p.get('produkt'), pallet_type, p.get('linia', linia), p.get('nr_partii'), p[col_qty], 'EXPEDITION', worker_login, f"Wydanie z {p.get('lokalizacja')}"))

            cursor.execute(f"DELETE FROM {table} WHERE id = %s", (pallet_id,))
            
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
        """Archive a pallet manually from the dashboard."""
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

            cursor.execute("""
                INSERT INTO magazyn_archiwum (original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, waga_ostatnia, lokalizacja_ostatnia, user_login, komentarz)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (p['id'], p.get('nr_palety'), p.get('nazwa') or p.get('produkt'), pallet_type, p.get('linia', linia), p.get('nr_partii'), p[col_qty], p.get('lokalizacja'), worker_login, "Ręczna archiwizacja z dashboardu"))

            cursor.execute(f"DELETE FROM {table} WHERE id = %s", (pallet_id,))
            
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
