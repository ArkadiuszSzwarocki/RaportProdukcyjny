import math
from hashlib import sha256
from app.db import get_db_connection, get_table_name
from app.services.scanner.scanner_code_normalizer import ScannerCodeNormalizer
from app.services.agro.agro_surowce_service import AgroSurowceService
from app.services.agro.agro_tanks_service import AgroTanksService, _normalize_tank_code, _classify_tank_zone
from datetime import datetime

class ProductionInventoryService:
    @staticmethod
    def available_start_locations(linia, cursor=None):
        conn = None
        try:
            if cursor is None:
                conn = get_db_connection()
                cursor = conn.cursor()
            cursor.execute(
                "SELECT UPPER(TRIM(lokalizacja)) FROM magazyn_inwentaryzacja_produkcji_sesje "
                "WHERE linia = %s AND status IN ('OPEN', 'CLOSED')",
                (linia,),
            )
            blocked = {row[0] for row in cursor.fetchall()}
            if 'WSZYSTKO' in blocked:
                return []
            return [area for area, conflicts in (
                ('BB+MZ', {'BB', 'MZ', 'BB+MZ'}),
                ('KO', {'KO'}),
                ('WZ04', {'WZ04'}),
            ) if not blocked.intersection(conflicts)]
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def get_active_sessions(linia='AGRO'):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_inwentaryzacja_produkcji_sesje WHERE status = 'OPEN' AND linia = %s ORDER BY created_at DESC",
                (linia,)
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_all_sessions(linia='AGRO', limit=100):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_inwentaryzacja_produkcji_sesje WHERE linia = %s ORDER BY id DESC LIMIT %s",
                (linia, limit)
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def start_session(linia, user_login, lokalizacja, comment=''):
        linia = linia.strip().upper()
        lokalizacja = lokalizacja.strip().upper()
        conn = get_db_connection()
        lock_scope = f'{conn.database}:{linia}:{lokalizacja}'
        lock_name = 'prod-inventory:' + sha256(lock_scope.encode()).hexdigest()[:40]
        locked = False
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT GET_LOCK(%s, 10)", (lock_name,))
            locked = cursor.fetchone()[0] == 1
            if not locked:
                return False, 'Trwa otwieranie inwentaryzacji. Spróbuj ponownie.'

            cursor.execute(
                """
                SELECT s.id
                FROM magazyn_inwentaryzacja_produkcji_sesje s
                LEFT JOIN magazyn_inwentaryzacja_produkcji_wpisy w ON w.sesja_id = s.id
                WHERE s.linia = %s AND UPPER(TRIM(s.lokalizacja)) = %s AND s.status = 'OPEN'
                GROUP BY s.id
                ORDER BY MAX(w.data_wpisu) DESC, s.id DESC
                LIMIT 1
                """,
                (linia, lokalizacja),
            )
            existing = cursor.fetchone()
            if existing:
                conn.rollback()
                return True, existing[0]
            if lokalizacja not in ProductionInventoryService.available_start_locations(linia, cursor):
                conn.rollback()
                return False, 'Ten obszar jest niedostępny lub czeka na zatwierdzenie.'
            cursor.execute(
                "INSERT INTO magazyn_inwentaryzacja_produkcji_sesje (linia, status, created_by, lokalizacja, comment) VALUES (%s, 'OPEN', %s, %s, %s)",
                (linia, user_login, lokalizacja, comment)
            )
            sesja_id = cursor.lastrowid
            
            # Immediately generate entries based on the snapshot for this location
            # We fetch all tanks, filter by the requested lokalizacja, and insert them.
            snapshot = AgroTanksService.get_production_inventory_snapshot(limit=4000, linia=linia, show_empty=True)
            
            lokalizacja_upper = lokalizacja.upper()
            
            for item in snapshot:
                tank = item.get('zbiornik', '').upper()
                zone = item.get('strefa', '').upper()
                
                # Check if it matches the location. Location could be "BB", "MZ", "KO", or a specific tank "BB 1"
                if (
                    lokalizacja_upper == 'WSZYSTKO' or lokalizacja_upper in tank or lokalizacja_upper == zone
                    or (lokalizacja_upper == 'BB+MZ' and tank.startswith(('BB', 'MZ')))
                ):
                    cursor.execute(
                        """
                        INSERT INTO magazyn_inwentaryzacja_produkcji_wpisy 
                        (sesja_id, ruch_id, zbiornik, surowiec_nazwa, waga_systemowa, waga_faktyczna, user_login)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (sesja_id, item.get('ruch_id'), tank, item.get('surowiec_nazwa'), item.get('stan_systemowy', 0.0), item.get('stan_systemowy', 0.0), user_login)
                    )
            
            conn.commit()
            return True, sesja_id
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            try:
                if locked:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
                    cursor.fetchone()
            finally:
                conn.close()

    @staticmethod
    def update_entries(sesja_id, updates, user_login):
        # updates = [{'id': wpis_id, 'waga_faktyczna': float}]
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute(
                "SELECT status, lokalizacja, linia FROM magazyn_inwentaryzacja_produkcji_sesje WHERE id = %s FOR UPDATE",
                (sesja_id,),
            )
            inventory_session = cursor.fetchone()
            if not inventory_session or inventory_session['status'] != 'OPEN':
                return False, 'Sesja inwentaryzacji nie jest otwarta.'

            for update in updates:
                weight = float(update['waga_faktyczna'])
                if not math.isfinite(weight) or weight < 0:
                    raise ValueError('Podaj poprawny stan faktyczny.')
                if inventory_session['lokalizacja'] == 'BB+MZ':
                    cursor.execute(
                        "SELECT surowiec_nazwa FROM magazyn_inwentaryzacja_produkcji_wpisy "
                        "WHERE id = %s AND sesja_id = %s",
                        (update['id'], sesja_id),
                    )
                    station = cursor.fetchone()
                    if not station:
                        raise ValueError('Stacja nie należy do tej sesji.')
                    expected = station['surowiec_nazwa'] or ''
                    code = ScannerCodeNormalizer.normalize_scanned_code(update.get('kod_palety') or '')
                    if not (weight == 0 and not code and expected in ('', 'PUSTY ZBIORNIK')):
                        if not code:
                            raise ValueError('Najpierw zeskanuj paletę.')
                        table = get_table_name('magazyn_surowce', inventory_session['linia'])
                        prefix, pallet_id = ScannerCodeNormalizer.extract_prefixed_id(code)
                        if prefix == 'SUR':
                            cursor.execute(f"SELECT nazwa FROM {table} WHERE id = %s", (pallet_id,))
                        else:
                            cursor.execute(f"SELECT nazwa FROM {table} WHERE UPPER(nr_palety) = %s", (code,))
                        pallet = cursor.fetchone()
                        if not pallet:
                            raise ValueError('Nie znaleziono surowca z zeskanowanej palety.')
                        actual = pallet['nazwa'] or ''
                        if not expected or ' '.join(expected.casefold().split()) != ' '.join(actual.casefold().split()):
                            raise ValueError(f'Surowiec niezgodny. Stacja: {expected or "pusta"}. Paleta: {actual}.')
                cursor.execute(
                    "UPDATE magazyn_inwentaryzacja_produkcji_wpisy SET waga_faktyczna = %s, user_login = %s, data_wpisu = GREATEST(CURRENT_TIMESTAMP, created_at + INTERVAL 1 SECOND) WHERE id = %s AND sesja_id = %s",
                    (weight, user_login, update['id'], sesja_id)
                )
            
            conn.commit()
            return True, "Zapisano zmiany."
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def update_material(sesja_id, entry_id, new_material, user_login, paleta_id=None, nr_palety=None, nr_partii=None, data_produkcji=None, data_przydatnosci=None, waga_faktyczna=None):

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status FROM magazyn_inwentaryzacja_produkcji_sesje WHERE id = %s FOR UPDATE",
                (sesja_id,),
            )
            inventory_session = cursor.fetchone()
            if not inventory_session or inventory_session[0] != 'OPEN':
                return False, 'Sesja inwentaryzacji nie jest otwarta.'
            is_empty = (new_material == 'PUSTY ZBIORNIK' or not new_material)
            mat_name = 'PUSTY ZBIORNIK' if is_empty else new_material
            actual_w = 0.0 if is_empty else (waga_faktyczna if waga_faktyczna is not None else 0.0)
            
            cursor.execute(
                """UPDATE magazyn_inwentaryzacja_produkcji_wpisy 
                   SET old_ruch_id = IFNULL(old_ruch_id, ruch_id),
                       ruch_id = CASE WHEN %s = 1 THEN ruch_id ELSE NULL END,
                       surowiec_nazwa = %s,
                       waga_faktyczna = %s,
                       user_login = %s,
                       data_wpisu = GREATEST(CURRENT_TIMESTAMP, created_at + INTERVAL 1 SECOND),
                       paleta_id = %s,
                       nr_palety = %s,
                       nr_partii = %s,
                       data_produkcji = %s,
                       data_przydatnosci = %s
                   WHERE id = %s AND sesja_id = %s""",
                (1 if is_empty else 0, mat_name, actual_w, user_login, paleta_id, nr_palety or '', nr_partii or '', data_produkcji, data_przydatnosci, entry_id, sesja_id)
            )
            conn.commit()
            return True, "Zaktualizowano surowiec."
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()


    @staticmethod
    def get_session_entries(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_inwentaryzacja_produkcji_wpisy WHERE sesja_id = %s ORDER BY zbiornik ASC",
                (sesja_id,)
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def close_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT lokalizacja FROM magazyn_inwentaryzacja_produkcji_sesje WHERE id = %s AND status = 'OPEN' FOR UPDATE",
                (sesja_id,),
            )
            inventory_session = cursor.fetchone()
            if inventory_session and inventory_session[0] == 'BB+MZ':
                cursor.execute(
                    "SELECT COUNT(*), SUM(data_wpisu > created_at) "
                    "FROM magazyn_inwentaryzacja_produkcji_wpisy WHERE sesja_id = %s",
                    (sesja_id,),
                )
                total, checked = cursor.fetchone()
                if not total or checked != total:
                    return False, 'Najpierw potwierdź wszystkie stacje BB i MZ.'
            cursor.execute("UPDATE magazyn_inwentaryzacja_produkcji_sesje SET status = 'CLOSED', closed_at = CURRENT_TIMESTAMP WHERE id = %s AND status = 'OPEN'", (sesja_id,))
            conn.commit()
            return True, "Sesja zamknięta"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def delete_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM magazyn_inwentaryzacja_produkcji_sesje WHERE id = %s", (sesja_id,))
            conn.commit()
            return True, "Usunięto sesję"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def apply_inventory(sesja_id, user_login):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM magazyn_inwentaryzacja_produkcji_sesje WHERE id = %s AND status = 'CLOSED'", (sesja_id,))
            sesja = cursor.fetchone()
            if not sesja:
                return False, "Sesja nie istnieje lub nie jest zamknięta."
                
            linia = sesja['linia']
            
            cursor.execute("SELECT * FROM magazyn_inwentaryzacja_produkcji_wpisy WHERE sesja_id = %s", (sesja_id,))
            wpisy = cursor.fetchall()
            
            for wpis in wpisy:
                waga_sys = float(wpis['waga_systemowa'] or 0)
                waga_fakt = float(wpis['waga_faktyczna'] or 0)
                
                # First, if the material was changed, zero out the old material
                if wpis.get('old_ruch_id'):
                    AgroTanksService.adjust_production_inventory(
                        ruch_id=wpis['old_ruch_id'],
                        actual_qty=0,
                        worker_login=user_login,
                        linia=linia,
                        komentarz=f"Inw. Prod. Sesja #{sesja_id} (Zastąpiono)"
                    )

                if wpis['ruch_id']:
                    # Existing material, update weight if changed
                    diff = waga_fakt - waga_sys
                    if abs(diff) > 0.001:
                        AgroTanksService.adjust_production_inventory(
                            ruch_id=wpis['ruch_id'],
                            actual_qty=waga_fakt,
                            worker_login=user_login,
                            linia=linia,
                            komentarz=f"Inw. Prod. Sesja #{sesja_id}"
                        )
                else:
                    # New material! The user replaced the old one, or the tank was empty
                    # We must create a new PRODUKCJA movement so it shows up in "Surowce w produkcji" and "Magazyn"
                    if waga_fakt > 0 and wpis['surowiec_nazwa'] and wpis['surowiec_nazwa'] != 'PUSTY ZBIORNIK':
                        if wpis.get('paleta_id'):
                            # Create via use_for_production
                            AgroSurowceService.use_for_production(
                                surowiec_id=wpis['paleta_id'],
                                ilosc=waga_fakt,
                                worker_login=user_login,
                                linia=linia,
                                komentarz=f"Inw. Prod. Sesja #{sesja_id}",
                                zbiornik=wpis['zbiornik']
                            )
                        else:
                            # Manually insert into magazyn_ruch because there is no warehouse pallet ID
                            from datetime import datetime
                            table_ruch = get_table_name('magazyn_ruch', linia)
                            zbiornik_val = AgroTanksService.normalize_production_tank(wpis['zbiornik']) or wpis['zbiornik']
                            cursor.execute(
                                f"INSERT INTO {table_ruch} (surowiec_nazwa, typ_ruchu, ilosc, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz, zbiornik) "
                                "VALUES (%s, 'PRODUKCJA', %s, 'POTWIERDZONE', %s, %s, %s, %s, %s, %s)",
                                (wpis['surowiec_nazwa'], -waga_fakt, user_login, datetime.now(), user_login, datetime.now(), f"Inw. Prod. Sesja #{sesja_id}", zbiornik_val)
                            )

            cursor.execute("UPDATE magazyn_inwentaryzacja_produkcji_sesje SET status = 'APPLIED' WHERE id = %s", (sesja_id,))
            conn.commit()
            return True, "Inwentaryzacja zatwierdzona."
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def edit_session(sesja_id, lokalizacja, comment):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE magazyn_inwentaryzacja_produkcji_sesje SET lokalizacja = %s, comment = %s WHERE id = %s", (lokalizacja, comment, sesja_id))
            conn.commit()
            return True, "Zaktualizowano sesję"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def revert_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE magazyn_inwentaryzacja_produkcji_sesje SET status = 'OPEN' WHERE id = %s", (sesja_id,))
            conn.commit()
            return True, "Cofnięto zatwierdzenie sesji"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def resume_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE magazyn_inwentaryzacja_produkcji_sesje SET status = 'OPEN' WHERE id = %s", (sesja_id,))
            conn.commit()
            return True, "Wznowiono sesję"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()
