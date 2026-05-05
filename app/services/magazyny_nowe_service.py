from app.db import get_db_connection, get_table_name
from datetime import datetime

class MagazynyNoweService:
    @staticmethod
    def get_pallet_history(pallet_id, pallet_type, linia='PSD'):
        """Zwraca historię ruchów palety."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # W zależności od typu, uderzamy do odpowiedniej tabeli magazyn_ruch
            # Surowce, Opakowania używają zazwyczaj magazyn_ruch
            # Wyroby gotowe używają magazyn_palety (dane dodania itp)
            
            table_ruch = get_table_name('magazyn_ruch', linia)
            
            if pallet_type in ['Surowiec', 'Opakowanie']:
                # W RaportProdukcyjny magazyn_ruch łączy się po surowiec_id
                cursor.execute(f"""
                    SELECT id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz 
                    FROM {table_ruch} 
                    WHERE surowiec_id = %s 
                    ORDER BY autor_data DESC
                """, (pallet_id,))
                return cursor.fetchall()
            else:
                # Wyroby gotowe: prosta historia z magazyn_palety (lub brak w zależności od implementacji)
                cursor.execute(f"SELECT data_potwierdzenia as autor_data, user_login as autor_login, 'POTWIERDZENIE' as typ_ruchu FROM {get_table_name('magazyn_palety', linia)} WHERE id = %s", (pallet_id,))
                row = cursor.fetchone()
                if row:
                    return [row]
                return []
        finally:
            conn.close()

    @staticmethod
    def move_pallet(pallet_id, pallet_type, new_location, worker_login, linia='PSD'):
        """Przenosi paletę na nową lokalizację (np. regał, stanowisko Big Bag)."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
            else:
                # Wyroby gotowe nie mają standardowo pola lokalizacja, dodajmy to bezpiecznie
                return False, "Wyroby gotowe aktualnie nie obsługują dynamicznych lokalizacji."

            # Pobierz stare dane do logu
            cursor.execute(f"SELECT lokalizacja, stan_magazynowy FROM {table} WHERE id = %s", (pallet_id,))
            row = cursor.fetchone()
            if not row:
                return False, "Paleta nie znaleziona."
                
            old_loc = row[0]
            qty = row[1]
            
            # Zaktualizuj lokalizację
            cursor.execute(f"UPDATE {table} SET lokalizacja = %s WHERE id = %s", (new_location, pallet_id))
            
            # Zapisz ruch do historii
            table_ruch = get_table_name('magazyn_ruch', linia)
            try:
                cursor.execute(f"""
                    INSERT INTO {table_ruch} 
                    (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) 
                    VALUES (%s, 'PRZESUNIECIE', 0, %s, 'POTWIERDZONE', %s, %s, %s)
                """, (pallet_id, qty, worker_login, datetime.now(), f"Z {old_loc or 'Brak'} do {new_location}"))
            except Exception as e:
                print("Błąd zapisu ruchu:", e)

            conn.commit()
            return True, "Pomyślnie przeniesiono."
        finally:
            conn.close()
            
    @staticmethod
    def archive_pallet(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Archiwizuje (zeruje stan) paletę."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
            else:
                table = get_table_name('magazyn_palety', linia)
                cursor.execute(f"UPDATE {table} SET waga_netto = 0 WHERE id = %s", (pallet_id,))
                conn.commit()
                return True, "Paleta zarchiwizowana."

            cursor.execute(f"UPDATE {table} SET stan_magazynowy = 0 WHERE id = %s", (pallet_id,))
            
            # Zapisz ruch do historii
            table_ruch = get_table_name('magazyn_ruch', linia)
            try:
                cursor.execute(f"""
                    INSERT INTO {table_ruch} 
                    (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) 
                    VALUES (%s, 'ARCHIWIZACJA', 0, 0, 'POTWIERDZONE', %s, %s, %s)
                """, (pallet_id, worker_login, datetime.now(), "Ręczna archiwizacja palety z systemu."))
            except Exception as e:
                print("Błąd zapisu ruchu:", e)

            conn.commit()
            return True, "Paleta zarchiwizowana."
        finally:
            conn.close()
