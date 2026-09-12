from app.db import get_db_connection, get_table_name

class PalletRestoreService:
    @staticmethod
    def restore_pallet_from_archive(archive_id: int = None, nr_palety: str = None, new_weight: float = None, new_location: str = None, user_login: str = 'admin') -> tuple[bool, str, dict]:
        """Restore a pallet from archive table back into active inventory."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
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
                
            if pallet_nr:
                cursor.execute(f"SELECT id FROM {table} WHERE nr_palety = %s", (pallet_nr,))
                existing = cursor.fetchone()
                if existing:
                    return False, f"Paleta o numerze {pallet_nr} już istnieje w magazynie aktywnym (ID: {existing['id']})!", {}
                    
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
            
            cursor.execute("""
                INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login)
                VALUES (%s, %s, %s, %s, 'PRZYWROCENIE_Z_ZUZYCIA', %s, %s, %s)
            """, (new_id, pallet_nr, linia, typ_palety, loc, f'Przywrócono z zużycia/archiwum przez {user_login}. Waga: {weight} kg, lokalizacja: {loc}. Partia: {nr_partii}', user_login))
            
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
