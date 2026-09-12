import sys
from app.db import get_db_connection, get_table_name

class PalletMaterialService:
    @staticmethod
    def update_packaging_type(pallet_id, pallet_type, new_packaging_type, worker_login, linia='PSD'):
        """Update packaging type descriptor on a pallet (e.g. Big Bag, Worek 25kg, Karton)."""
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

            cursor.execute(f"SELECT id, nr_palety, typ_opakowania, COALESCE(NULLIF(TRIM(lokalizacja), ''), 'OCZEKUJĄCE') as lokalizacja FROM {table} WHERE id = %s", (pallet_id,))
            row = cursor.fetchone()
            if not row:
                return False, f"Błąd: Paleta o ID {pallet_id} nie istnieje."

            old_pkg = row.get('typ_opakowania') or 'brak'
            current_loc = row.get('lokalizacja') or 'OCZEKUJĄCE'
            cursor.execute(f"UPDATE {table} SET typ_opakowania = %s WHERE id = %s", (new_packaging_type, pallet_id))

            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, %s, 'ZMIANA_OPAKOWANIA', %s, %s, %s, %s)",
                    (pallet_id, row.get('nr_palety'), linia, pallet_type.lower(), current_loc, current_loc, f"Zmiana opakowania: {old_pkg} -> {new_packaging_type}", worker_login)
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
        """Update material type category for packaging/raw materials (Karton / Taśma)."""
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

            cursor.execute(f"SELECT id, nr_palety, typ_opakowania, COALESCE(NULLIF(TRIM(lokalizacja), ''), 'OCZEKUJĄCE') as lokalizacja FROM {table} WHERE id = %s", (pallet_id,))
            row = cursor.fetchone()
            if not row:
                return False, f"Błąd: Paleta o ID {pallet_id} nie istnieje."

            old_material = row.get('typ_opakowania') or 'Karton'
            current_loc = row.get('lokalizacja') or 'OCZEKUJĄCE'
            cursor.execute(f"UPDATE {table} SET typ_opakowania = %s WHERE id = %s", (new_material_type, pallet_id))

            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, %s, 'ZMIANA_TYPU_MATERIALU', %s, %s, %s, %s)",
                    (pallet_id, row.get('nr_palety'), linia, pallet_type.lower(), current_loc, current_loc, f"Zmiana typu materiału: {old_material} -> {new_material_type}", worker_login)
                )
            except Exception as e:
                print(f"Błąd logowania historii zmiany typu materiału: {e}")

            conn.commit()
            return True, f"Typ materiału został zmieniony na '{new_material_type}'."
        except Exception as e:
            if conn: conn.rollback()
            print(f"[SERVICE] Exception: {str(e)}", file=sys.stderr)
            return False, f"Błąd bazy danych: {str(e)}"
        finally:
            conn.close()

    @staticmethod
    def bulk_update_material_type(pallet_ids: list, pallet_type: str, new_material_type: str, worker_login: str, linia: str = 'PSD') -> tuple[bool, str, int]:
        """Bulk update material type for a collection of packaging or raw pallets."""
        if not pallet_ids or not new_material_type or new_material_type not in ('Karton', 'Taśma'):
            return False, "Błędne parametry", 0

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
            else:
                return False, "Zmiana typu materiału dostępna tylko dla opakowań i surowców.", 0

            id_placeholders = ','.join(['%s'] * len(pallet_ids))
            
            cursor.execute(f"SELECT id, nr_palety, typ_opakowania, COALESCE(NULLIF(TRIM(lokalizacja), ''), 'OCZEKUJĄCE') as lokalizacja FROM {table} WHERE id IN ({id_placeholders})", pallet_ids)
            rows = cursor.fetchall()
            
            if not rows:
                return False, "Nie znaleziono opakowań o podanych ID.", 0
            
            cursor.execute(
                f"UPDATE {table} SET typ_opakowania = %s WHERE id IN ({id_placeholders})",
                [new_material_type] + pallet_ids
            )
            updated_count = cursor.rowcount
            
            try:
                for row in rows:
                    old_material = row.get('typ_opakowania') or 'Karton'
                    cur_loc = row.get('lokalizacja') or 'OCZEKUJĄCE'
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, %s, 'ZMIANA_TYPU_MATERIALU_BULK', %s, %s, %s, %s)",
                        (row['id'], row.get('nr_palety'), linia, pallet_type.lower(), cur_loc, cur_loc,
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
