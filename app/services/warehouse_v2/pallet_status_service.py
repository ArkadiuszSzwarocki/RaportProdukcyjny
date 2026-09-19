from app.db import get_db_connection, get_table_name

class PalletStatusService:
    @staticmethod
    def toggle_block(pallet_id, pallet_type, worker_login, linia='PSD', sscc=None, reason=None):
        """Toggle lock/block status of a pallet, including buffer pallets."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            p_type_norm = str(pallet_type or '').strip().lower()
            if 'surow' in p_type_norm:
                table = get_table_name('magazyn_surowce', linia)
            elif 'opakow' in p_type_norm:
                table = get_table_name('magazyn_opakowania', linia)
            elif 'dodat' in p_type_norm:
                table = 'magazyn_dodatki'
            else:
                table = get_table_name('magazyn_palety', linia)

            target_sscc = str(sscc).strip() if sscc else None
            cursor.execute(f"SELECT is_blocked, nr_palety FROM {table} WHERE id = %s OR nr_palety = %s", (pallet_id, target_sscc or str(pallet_id)))
            row = cursor.fetchone()

            if not row and not any(k in p_type_norm for k in ('surow', 'opakow', 'dodat')):
                # Check buffer tables (palety_workowanie / palety_agro)
                buf_tbl = 'palety_workowanie' if str(linia).upper() == 'PSD' else 'palety_agro'
                cursor.execute(f"SELECT id, is_blocked, nr_palety FROM {buf_tbl} WHERE id = %s OR nr_palety = %s", (pallet_id, target_sscc or str(pallet_id)))
                b_row = cursor.fetchone()
                if not b_row:
                    alt_buf = 'palety_agro' if buf_tbl == 'palety_workowanie' else 'palety_workowanie'
                    cursor.execute(f"SELECT id, is_blocked, nr_palety FROM {alt_buf} WHERE id = %s OR nr_palety = %s", (pallet_id, target_sscc or str(pallet_id)))
                    b_row = cursor.fetchone()
                    if b_row:
                        buf_tbl = alt_buf
                        linia = 'AGRO' if alt_buf == 'palety_agro' else 'PSD'
                if b_row:
                    new_status = 0 if b_row.get('is_blocked') else 1
                    cursor.execute(f"UPDATE {buf_tbl} SET is_blocked = %s WHERE id = %s", (new_status, b_row['id']))
                    action = 'BLOKADA' if new_status else 'ODBLOKOWANIE'
                    comment = f"{action}: {reason}" if reason and new_status else f"{action} palety w buforze przez użytkownika"
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, 'wyrob_gotowy', %s, %s, %s)",
                        (b_row['id'], b_row.get('nr_palety'), linia, action, comment, worker_login)
                    )
                    conn.commit()
                    return True, f"Paleta {'zablokowana' if new_status else 'odblokowana'}."

            if not row:
                return False, "Paleta nie znaleziona."
                
            new_status = 0 if row.get('is_blocked') else 1
            nr_p = row.get('nr_palety')
            cursor.execute(f"UPDATE {table} SET is_blocked = %s WHERE id = %s OR nr_palety = %s", (new_status, pallet_id, target_sscc or str(pallet_id)))
            
            action = 'BLOKADA' if new_status else 'ODBLOKOWANIE'
            comment = f"{action}: {reason}" if reason and new_status else f"{action} palety przez użytkownika"
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (pallet_id, nr_p, linia, pallet_type.lower(), action, comment, worker_login)
            )
            
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
