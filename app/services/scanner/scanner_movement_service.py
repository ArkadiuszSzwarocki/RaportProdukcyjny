from datetime import datetime
from app.db import get_db_connection, get_table_name
from app.services.tank_validation_service import TankValidationService
from app.utils.location_validator import is_deleted_station_code, check_rack_location_availability
from app.utils.pallet_id import is_valid_pallet_id, generate_pallet_id

class ScannerMovementService:
    """Obsługuje fizyczne ruchy magazynowe skanera: przekazywanie na produkcję i przesunięcia regałowe."""

    @staticmethod
    def dispatch_to_production(
        surowiec_id: int,
        ilosc: float,
        worker_login: str,
        linia: str = 'Agro',
        plan_id: int | None = None,
        zbiornik: str | None = None,
        komentarz: str | None = None,
        pallet_type: str = 'Surowiec',
    ) -> tuple[bool, str, dict | None]:
        """Pobiera `ilosc` kg z palety na stację produkcyjną / do zbiornika."""
        if ilosc <= 0:
            return False, "Ilość musi być > 0", None

        if pallet_type == 'Opakowanie':
            table_surowce = get_table_name('magazyn_opakowania', linia)
        elif pallet_type == 'Dodatek':
            table_surowce = 'magazyn_dodatki'
        else:
            table_surowce = get_table_name('magazyn_surowce', linia)
            
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, is_blocked, nr_partii, data_produkcji, data_przydatnosci FROM {table_surowce} WHERE id = %s",
                (surowiec_id,)
            )
            pallet = cur.fetchone()
            if not pallet:
                return False, f"Paleta #{surowiec_id} nie istnieje", None

            if pallet.get('is_blocked') or str(pallet.get('lokalizacja') or '').upper().startswith('OCZEK'):
                return False, f"BŁĄD: Paleta #{surowiec_id} ma status OCZEKUJĄCE na przyjęcie / jest ZABLOKOWANA. Nie można jej wydać na produkcję dopóki nie zostanie przyjęta na magazyn docelowy!", None

            pallet_sscc = str(pallet.get('nr_palety') or '').strip()
            if not pallet_sscc or not is_valid_pallet_id(pallet_sscc):
                pallet_sscc = generate_pallet_id(linia, pallet_type)
                cur.execute(f"UPDATE {table_surowce} SET nr_palety = %s WHERE id = %s", (pallet_sscc, surowiec_id))
                pallet['nr_palety'] = pallet_sscc

            stan = float(pallet['stan_magazynowy'] or 0)
            if ilosc > stan:
                return False, f"Za duża ilość — dostępne: {stan:.1f} kg", None

            now = datetime.now()
            plan_id_val = int(plan_id) if plan_id not in (None, '', 0, '0') else None
            
            zbiornik_normalized = str(zbiornik or '').strip().upper() if zbiornik else None
            if not zbiornik_normalized:
                return False, "⚠️ Brak kodu zbiornika! Podaj zbiornik (np. BB02, MZ07) aby przenieść surowiec na produkcję.", None

            if is_deleted_station_code(zbiornik_normalized):
                return False, f"❌ Stacja/zbiornik {zbiornik_normalized} została wycofana/usunięta z systemu! Dozwolone: BB01-BB06, BB11-BB22, MZ07-MZ10, MZ23-MZ24, KO01-KO40.", None
            
            zbiornik_val = zbiornik_normalized
            lokalizacja_val = zbiornik_val

            is_valid_mat, err_mat = TankValidationService.validate_tank_material(
                kod_zbiornika=zbiornik_val,
                surowiec_nazwa=pallet.get('nazwa', ''),
                surowiec_id=surowiec_id
            )
            if not is_valid_mat:
                return False, err_mat, None

            is_partial = ilosc < stan
            lokalizacja_zrodlowa = (pallet.get('lokalizacja') or '').strip()

            if is_partial:
                cur.execute(
                    f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy - %s WHERE id = %s",
                    (ilosc, surowiec_id)
                )
            else:
                cur.execute(
                    f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy - %s, lokalizacja = %s WHERE id = %s",
                    (ilosc, lokalizacja_val, surowiec_id)
                )

            cur.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            stan_po = float(cur.fetchone()['stan_magazynowy'] or 0)

            cur.execute(
                f"INSERT INTO {table_ruch} "
                "(surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, "
                "autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz, zbiornik) "
                "VALUES (%s,%s,'PRODUKCJA',%s,%s,%s,'POTWIERDZONE',%s,%s,%s,%s,%s,%s,%s)",
                (
                    surowiec_id, pallet['nazwa'], -ilosc, stan_po,
                    lokalizacja_zrodlowa,
                    worker_login, now, worker_login, now,
                    plan_id_val, komentarz, zbiornik_val
                )
            )

            try:
                cur.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) "
                    "VALUES (%s, %s, %s, %s, 'WYDANIE_PRODUKCJA', %s, %s, %s, %s)",
                    (
                        surowiec_id, pallet_sscc, linia, pallet_type.lower(),
                        lokalizacja_zrodlowa or 'Magazyn', zbiornik_val,
                        f"Wydanie do stacji {zbiornik_val} (ilość: {ilosc:.1f} kg)",
                        worker_login
                    )
                )
            except Exception as hist_err:
                print("Błąd zapisu palety_historia w dispatch_to_production:", hist_err)

            conn.commit()

            extra_data = {
                'is_partial': is_partial,
                'stan_po': stan_po,
                'ilosc_pobrana': ilosc,
                'zbiornik': zbiornik_val,
                'pallet_name': pallet['nazwa'],
                'nr_palety': pallet_sscc,
                'lokalizacja_zrodlowa': lokalizacja_zrodlowa,
                'id': surowiec_id
            }

            return True, f"Przekazano {ilosc:.1f} kg [{pallet['nazwa']}] na produkcję. Pozostało: {stan_po:.1f} kg", extra_data
        except Exception as e:
            conn.rollback()
            return False, f"Błąd: {e}", None
        finally:
            conn.close()

    @staticmethod
    def move_pallet(
        surowiec_id: int,
        nowa_lokalizacja: str,
        worker_login: str,
        linia: str = 'Agro',
    ) -> tuple[bool, str]:
        """Przenosi paletę na nową lokalizację i zapisuje historię w magazyn_ruch."""
        nowa_lokalizacja = str(nowa_lokalizacja or '').strip().upper()
        if not nowa_lokalizacja:
            return False, "Nie podano lokalizacji docelowej"

        conn_dict = get_db_connection()
        try:
            cur_dict = conn_dict.cursor()
            cur_dict.execute("SELECT nazwa FROM magazyn_dozwolone_lokalizacje")
            dozwolone = [row[0].upper() for row in cur_dict.fetchall()]
        finally:
            conn_dict.close()

        is_valid = any(nowa_lokalizacja.startswith(dozw_lok) for dozw_lok in dozwolone)
        if not is_valid:
            return False, f"Lokalizacja '{nowa_lokalizacja}' nie występuje w dozwolonym słowniku ustawień."

        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch = get_table_name('magazyn_ruch', linia)
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, is_blocked FROM {table_surowce} WHERE id = %s",
                (surowiec_id,)
            )
            pallet = cur.fetchone()
            if not pallet:
                return False, f"Paleta #{surowiec_id} nie istnieje"

            nr_p = pallet.get('nr_palety')
            from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
            in_trf, trf_ref = DeliveryQueries.is_pallet_in_pending_transfer(pallet_id=surowiec_id, nr_palety=nr_p)
            is_in_transfer_acceptance = bool(in_trf)
            trf_order_ref = trf_ref or ''

            if pallet.get('is_blocked') and not is_in_transfer_acceptance:
                return False, f"BŁĄD: Paleta {nr_p or surowiec_id} jest zablokowana ręcznie (blokada magazynowa) i nie może być przesunięta."

            stara_lokalizacja = (pallet.get('lokalizacja') or '').strip().upper()
            if stara_lokalizacja == nowa_lokalizacja:
                return False, f"Paleta jest już na lokalizacji {nowa_lokalizacja}"

            is_loc_available, error_msg = check_rack_location_availability(nowa_lokalizacja, current_nr_palety=pallet.get('nr_palety'))
            if not is_loc_available:
                return False, error_msg

            now = datetime.now()
            stan = float(pallet['stan_magazynowy'] or 0)

            cur.execute(
                f"UPDATE {table_surowce} SET lokalizacja = %s, is_blocked = 0 WHERE id = %s",
                (nowa_lokalizacja, surowiec_id)
            )

            cur.execute(
                f"INSERT INTO {table_ruch} "
                "(surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, "
                "autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz) "
                "VALUES (%s,%s,'PRZESUNIECIE',%s,%s,%s,'POTWIERDZONE',%s,%s,%s,%s,%s)",
                (
                    surowiec_id, pallet['nazwa'], stan, stan,
                    nowa_lokalizacja,
                    worker_login, now, worker_login, now,
                    f"Przesunięcie skanerem: {stara_lokalizacja or 'Brak'} -> {nowa_lokalizacja}"
                )
            )
            conn.commit()

            try:
                from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
                AcceptanceService.auto_accept_by_pallet_no(pallet.get('nr_palety'), nowa_lokalizacja, worker_login)
                
                from app.services.osip_transfer_service import OsipTransferService
                OsipTransferService.auto_receive_pallet_by_code(pallet.get('nr_palety') or str(surowiec_id), nowa_lokalizacja, worker_login)
            except Exception as ex:
                import logging
                logging.error(f"Błąd powiadamiania dostaw/transferów o przeniesieniu: {ex}")

            if is_in_transfer_acceptance:
                return True, f"✅ Przyjęto w zleceniu {trf_order_ref} na regał: {nowa_lokalizacja}"
            return True, f"Przeniesiono paletę [{pallet['nazwa']}] na lokalizację: {nowa_lokalizacja}"
        except Exception as e:
            conn.rollback()
            return False, f"Błąd: {e}"
        finally:
            conn.close()
