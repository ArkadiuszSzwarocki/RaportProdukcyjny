from datetime import datetime
from app.db import get_db_connection, get_table_name
from app.services.warehouse_v2.pallet_status_service import PalletStatusService

class PalletModificationService:
    @staticmethod
    def rename_pallet(pallet_id, pallet_type, new_name, worker_login, linia='PSD'):
        """Rename product on a raw material or packaging pallet."""
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
    def update_weight(pallet_id, pallet_type, new_weight, worker_login, linia='PSD', sscc=None):
        """Update pallet weight or amount. If 0 or less, pallet is archived."""
        new_weight = float(new_weight)
        if new_weight <= 0:
            return PalletStatusService.archive_pallet(pallet_id, pallet_type, worker_login, linia)
            
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            p_type_norm = str(pallet_type or '').strip().lower()
            if 'surow' in p_type_norm:
                table = get_table_name('magazyn_surowce', linia)
                col = 'stan_magazynowy'
            elif 'opakow' in p_type_norm:
                table = get_table_name('magazyn_opakowania', linia)
                col = 'stan_magazynowy'
            elif 'dodat' in p_type_norm:
                table = 'magazyn_dodatki'
                col = 'stan_magazynowy'
            else:
                table = get_table_name('magazyn_palety', linia)
                col = 'waga_netto'

            target_sscc = str(sscc).strip() if sscc else None
            cursor.execute(f"SELECT {col}, nr_palety FROM {table} WHERE id = %s OR nr_palety = %s", (pallet_id, target_sscc or str(pallet_id)))
            row = cursor.fetchone()

            if not row and not any(k in p_type_norm for k in ('surow', 'opakow', 'dodat')):
                # Check buffer tables
                buf_tbl = 'palety_workowanie' if str(linia).upper() == 'PSD' else 'palety_agro'
                cursor.execute(f"SELECT id, waga, nr_palety FROM {buf_tbl} WHERE id = %s OR nr_palety = %s", (pallet_id, target_sscc or str(pallet_id)))
                b_row = cursor.fetchone()
                if not b_row:
                    alt_buf = 'palety_agro' if buf_tbl == 'palety_workowanie' else 'palety_workowanie'
                    cursor.execute(f"SELECT id, waga, nr_palety FROM {alt_buf} WHERE id = %s OR nr_palety = %s", (pallet_id, target_sscc or str(pallet_id)))
                    b_row = cursor.fetchone()
                    if b_row:
                        buf_tbl = alt_buf
                        linia = 'AGRO' if alt_buf == 'palety_agro' else 'PSD'
                if b_row:
                    old_weight = float(b_row[1] or 0.0)
                    p_real_id = b_row[0]
                    p_nr = b_row[2]
                    cursor.execute(f"UPDATE {buf_tbl} SET waga = %s, waga_brutto = %s + COALESCE(tara, 0) WHERE id = %s", (new_weight, new_weight, p_real_id))
                    cursor.execute("""
                        INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login)
                        VALUES (%s, %s, %s, 'wyrob_gotowy', 'KOREKTA_WAGI', %s, %s)
                    """, (p_real_id, p_nr, linia, f"Ręczna zmiana wagi w buforze: {old_weight} -> {new_weight} kg", worker_login))
                    conn.commit()
                    return True, f"Waga została zaktualizowana ({old_weight} -> {new_weight} kg)."

            if not row:
                return False, f"Błąd: Paleta o ID {pallet_id} nie istnieje."
                
            old_weight = float(row[0]) if row[0] is not None else 0.0
            nr_p = row[1] if len(row) > 1 else target_sscc

            cursor.execute(f"UPDATE {table} SET {col} = %s WHERE id = %s OR nr_palety = %s", (new_weight, pallet_id, target_sscc or str(pallet_id)))
            
            # Zapisz ruch do historii
            try:
                cursor.execute("""
                    INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login)
                    VALUES (%s, %s, %s, %s, 'KOREKTA_WAGI', %s, %s)
                """, (pallet_id, nr_p, linia, pallet_type.lower(), f"Ręczna zmiana wagi: {old_weight} -> {new_weight}", worker_login))
            except Exception as e:
                print(f"Błąd zapisu ruchu:", e)

            conn.commit()
            return True, f"Waga zaktualizowana pomyślnie na {new_weight}."
        finally:
            conn.close()

    @staticmethod
    def return_pallet_to_raw(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Return a finished good pallet back to raw materials (OSIP)."""
        if pallet_type != 'Wyrób Gotowy':
            return False, "Tylko wyroby gotowe można zwrócić jako surowiec."
            
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_pal = get_table_name('magazyn_palety', linia)
            table_sur = get_table_name('magazyn_surowce', linia)
            
            cursor.execute(f"SELECT nazwa_produktu, waga_netto, numer_palety FROM {table_pal} WHERE id = %s", (pallet_id,))
            pal = cursor.fetchone()
            if not pal:
                return False, "Paleta nie znaleziona."
                
            nazwa = pal['nazwa_produktu']
            waga = pal['waga_netto']
            nr_pal = pal['numer_palety']
            
            cursor.execute(f"UPDATE {table_pal} SET waga_netto = 0 WHERE id = %s", (pallet_id,))
            lokalizacja = 'OSIP' 
            
            cursor.execute(f"""
                INSERT INTO {table_sur} (nazwa, stan_magazynowy, lokalizacja) 
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE stan_magazynowy = stan_magazynowy + VALUES(stan_magazynowy)
            """, (nazwa, waga, lokalizacja))
            
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
