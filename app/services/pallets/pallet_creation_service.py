from datetime import datetime
import threading
from flask import current_app

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.services.planning.status import PlanningStatusService
from app.utils.pallet_id import generate_pallet_id
from app.blueprints.warehouse.routes.printing_routes import _select_preferred_printer
from app.repositories.warehouse_pallet_repository import WarehousePalletRepository
from app.repositories.warehouse_movement_ledger_repository import WarehouseMovementLedgerRepository


class PalletCreationService:
    """Service handling pallet creation, weight registration, packaging deduction, and label printing."""

    @staticmethod
    def _async_print_label(paleta_id_local, nr_palety_local, linia, app, usr_ip=None, usr_name=None):
        """Asynchronously print 2 copies of finished product label."""
        with app.app_context():
            conn2 = None
            try:
                from app.utils.pallet_label import prepare_pallet_label_data
                conn2 = get_db_connection()
                cur2 = conn2.cursor()
                label_data_local = prepare_pallet_label_data(cur2, paleta_id_local, linia, source_table='workowanie')
            except Exception as prep_err:
                app.logger.error('Failed to prepare label data for paleta %s: %s', paleta_id_local, prep_err)
                if conn2:
                    try:
                        conn2.close()
                    except Exception:
                        pass
                return

            try:
                if not label_data_local:
                    app.logger.error('No label data prepared for paleta %s', paleta_id_local)
                    if conn2:
                        try:
                            conn2.close()
                        except Exception:
                            pass
                    return

                from app.services.print_server import get_printer
                printer_local = get_printer()

                override_ip = None
                override_name = usr_name or None

                if usr_ip:
                    clean_ip = usr_ip.strip()
                    if clean_ip.startswith('net:'):
                        clean_ip = clean_ip.replace('net:', '').strip()
                    elif clean_ip.startswith('db:'):
                        try:
                            db_id = int(clean_ip.replace('db:', ''))
                            cur2.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s AND aktywna = 1", (db_id,))
                            p_row = cur2.fetchone()
                            if p_row:
                                clean_ip = p_row.get('ip') if isinstance(p_row, dict) else p_row[0]
                                override_name = override_name or (p_row.get('nazwa') if isinstance(p_row, dict) else p_row[1])
                        except Exception:
                            clean_ip = None
                    elif clean_ip.isdigit():
                        try:
                            cur2.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s AND aktywna = 1", (int(clean_ip),))
                            p_row = cur2.fetchone()
                            if p_row:
                                clean_ip = p_row.get('ip') if isinstance(p_row, dict) else p_row[0]
                                override_name = override_name or (p_row.get('nazwa') if isinstance(p_row, dict) else p_row[1])
                        except Exception:
                            pass
                    override_ip = clean_ip or None

                if override_name:
                    try:
                        cur2.execute("SELECT ip, nazwa FROM drukarki WHERE (nazwa = %s OR LOWER(nazwa) LIKE LOWER(%s)) AND aktywna = 1 LIMIT 1", (override_name, f"%{override_name}%"))
                        p_row = cur2.fetchone()
                        if p_row:
                            db_p_ip = p_row.get('ip') if isinstance(p_row, dict) else p_row[0]
                            db_p_nazwa = p_row.get('nazwa') if isinstance(p_row, dict) else p_row[1]
                            if db_p_ip:
                                override_ip = db_p_ip
                            if db_p_nazwa:
                                override_name = db_p_nazwa
                    except Exception:
                        pass

                if not override_ip or not override_name:
                    pref_name, pref_ip = _select_preferred_printer(cur2, linia=linia)
                    if not override_ip:
                        override_ip = pref_ip
                    if not override_name:
                        override_name = pref_name

                try:
                    ok, print_msg = printer_local.print_finished_product_label(
                        label_data_local,
                        override_ip=override_ip,
                        override_name=override_name,
                        copies=2
                    )
                    app.logger.info(
                        'Async print (2 copies) for paleta %s: ok=%s printer=%s ip=%s msg=%s',
                        nr_palety_local, ok, override_name or getattr(printer_local, 'printer_name', None),
                        override_ip or getattr(printer_local, 'printer_ip', None), print_msg
                    )
                except Exception as single_err:
                    app.logger.error('Print attempt failed for paleta %s: %s', paleta_id_local, single_err)

                if conn2:
                    try:
                        conn2.close()
                    except Exception:
                        pass

            except Exception as err:
                app.logger.error('Unexpected error in async print thread for paleta %s: %s', paleta_id_local, err)
                if conn2:
                    try:
                        conn2.close()
                    except Exception:
                        pass

    @staticmethod
    def dodaj_palete(plan_id, linia, waga_palety, nr_plomby, data_produkcji, printer_ip, printer_name, user_login, app_obj, is_ajax, safe_return_url):
        """Add paleta (package) to Workowanie buffer using repository pattern and recording unified stock movement."""
        linia = linia
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            current_app.logger.debug('dodaj_palete: plan_id=%s', plan_id)
        except Exception:
            pass

        try:
            waga_input = int(float(waga_palety.replace(',', '.')))
        except Exception:
            waga_input = 0

        nr_plomby = str(nr_plomby or '').strip()
        if not nr_plomby:
            nr_plomby = None
        elif len(nr_plomby) > 100:
            nr_plomby = nr_plomby[:100]

        plan_row = WarehousePalletRepository.get_plan_info(plan_id, linia, conn=conn)

        if not plan_row:
            conn.close()
            return ('Błąd: Plan nie znaleziony', 404, None)

        now_ts = datetime.now()
        plan_sekcja = plan_row.get('sekcja')
        _plan_data = plan_row.get('data_planu')
        plan_produkt = plan_row.get('produkt')
        plan_data_produkcji = plan_row.get('data_produkcji')
        plan_zasyp_id = plan_row.get('zasyp_id')

        input_data_produkcji = str(data_produkcji or '').strip()
        if input_data_produkcji:
            try:
                datetime.strptime(input_data_produkcji, '%Y-%m-%d')
            except ValueError:
                conn.close()
                return ('Błąd: Nieprawidłowy format daty produkcji (oczekiwano RRRR-MM-DD)', 400, None)
            selected_data_produkcji = input_data_produkcji
        elif plan_data_produkcji:
            if hasattr(plan_data_produkcji, 'strftime'):
                selected_data_produkcji = plan_data_produkcji.strftime('%Y-%m-%d')
            else:
                selected_data_produkcji = str(plan_data_produkcji)
        elif _plan_data:
            if hasattr(_plan_data, 'strftime'):
                selected_data_produkcji = _plan_data.strftime('%Y-%m-%d')
            else:
                selected_data_produkcji = str(_plan_data)
        else:
            selected_data_produkcji = now_ts.strftime('%Y-%m-%d')

        if plan_sekcja not in ('Workowanie', 'Czyszczenie'):
            conn.close()
            try:
                current_app.logger.warning('REJECTED: Cannot add paleta to sekcja=%s', plan_sekcja)
            except Exception:
                pass
            return ('Błąd: Paletki można dodawać tylko do Workowania (bufora) lub Czyszczenia', 400, None)

        if waga_input <= 0:
            conn.close()
            return ('Błąd: Waga musi być większa od 0', 400, None)

        try:
            paleta_id = None
            nr_palety = None

            # Concurrency-safe reserved pallet check with row locking
            reserved_row = WarehousePalletRepository.find_reserved_pallet(plan_id, linia, lock_for_update=True, conn=conn)

            nr_palety_czyszczenie = None
            is_czyszczenie = (plan_sekcja == 'Czyszczenie' or (plan_produkt and ('czyszczenie' in plan_produkt.lower() or 'maka mix do lnu' in plan_produkt.lower() or 'mąka mix do lnu' in plan_produkt.lower())))
            if is_czyszczenie:
                nr_palety_czyszczenie = WarehousePalletRepository.find_cleaning_sscc(plan_id, plan_zasyp_id, linia, conn=conn)

            pallet_type = 'surowiec' if is_czyszczenie else 'wyrób gotowy'

            if reserved_row:
                paleta_id = reserved_row.get('id')
                nr_palety = reserved_row.get('nr_palety')
                if not nr_palety or (is_czyszczenie and (nr_palety == nr_palety_czyszczenie or not nr_palety.startswith('SUR'))):
                    nr_palety = generate_pallet_id(linia, pallet_type)

                WarehousePalletRepository.update_reserved_pallet(
                    pallet_id=paleta_id,
                    linia=linia,
                    waga=waga_input,
                    data_dodania=now_ts,
                    user_login=user_login,
                    nr_palety=nr_palety,
                    nr_plomby=nr_plomby,
                    conn=conn
                )
            else:
                nr_palety = generate_pallet_id(linia, pallet_type)

                paleta_id = WarehousePalletRepository.insert_new_pallet(
                    plan_id=plan_id,
                    linia=linia,
                    waga=waga_input,
                    data_dodania=now_ts,
                    user_login=user_login,
                    nr_palety=nr_palety,
                    nr_plomby=nr_plomby,
                    conn=conn
                )

            # Compute sequential pallet number (nr_palety_lp) for this plan and store it if column exists
            try:
                if paleta_id:
                    cursor.execute(f"SHOW COLUMNS FROM {table_pal} LIKE 'nr_palety_lp'")
                    col = cursor.fetchone()
                    if col:
                        cursor.execute(f"SELECT nr_palety_lp FROM {table_pal} WHERE id = %s", (paleta_id,))
                        cur_lp = cursor.fetchone()
                        cur_lp_val = None
                        if cur_lp and cur_lp[0] is not None:
                            try:
                                cur_lp_val = int(cur_lp[0])
                            except (ValueError, TypeError):
                                cur_lp_val = None

                        if cur_lp_val is not None and cur_lp_val > 0:
                            pass
                        else:
                            cursor.execute(
                                f"SELECT COALESCE(MAX(nr_palety_lp), 0) FROM {table_pal} WHERE plan_id = %s AND id != %s",
                                (plan_id, paleta_id),
                            )
                            max_res = cursor.fetchone()
                            max_lp = 0
                            if max_res and max_res[0] is not None:
                                try:
                                    max_lp = int(max_res[0])
                                except (ValueError, TypeError):
                                    max_lp = 0

                            if max_lp == 0:
                                cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, paleta_id))
                                res_lp = cursor.fetchone()
                                try:
                                    nr_palety_lp = int(res_lp[0]) if (res_lp and res_lp[0]) else 1
                                except (ValueError, TypeError):
                                    nr_palety_lp = 1
                            else:
                                nr_palety_lp = max_lp + 1
                            cursor.execute(f"UPDATE {table_pal} SET nr_palety_lp = %s WHERE id = %s", (nr_palety_lp, paleta_id))
            except Exception as lp_err:
                current_app.logger.warning("Failed to compute nr_palety_lp: %s", lp_err)

            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id = %s",
                (waga_input, plan_id),
            )

            cursor.execute(
                f"UPDATE {table_plan} SET data_produkcji = %s WHERE id = %s",
                (selected_data_produkcji, plan_id),
            )

            is_original_czyszczenie = False
            try:
                nazwa_do_historii = plan_produkt
                if plan_produkt and 'czyszczenie' in plan_produkt.lower():
                    is_original_czyszczenie = True
                    nazwa_do_historii = "Mąka mix do Lnu"
                    cursor.execute(f"UPDATE {table_plan} SET produkt = %s WHERE id = %s", (nazwa_do_historii, plan_id))
                    plan_produkt = nazwa_do_historii

                # Automatic acceptance of finished goods into warehouse inventory
                default_loc = 'MGW01' if str(linia).upper() == 'PSD' else 'MGW02'
                
                if not is_original_czyszczenie:
                    cursor.execute(
                        f"UPDATE {table_pal} SET status='przyjeta', waga_potwierdzona=%s, data_potwierdzenia=%s WHERE id=%s",
                        (waga_input, now_ts, paleta_id)
                    )
                    
                    cursor.execute("""
                        INSERT INTO magazyn_palety (
                            paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, 
                            waga_brutto, tara, user_login, nr_partii, data_produkcji, 
                            data_przydatnosci, lokalizacja, nr_palety, nr_plomby, linia, nr_palety_lp, data_potwierdzenia
                        ) VALUES (%s, %s, %s, %s, %s, %s, 25, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        paleta_id, plan_id, _plan_data, nazwa_do_historii, waga_input,
                        waga_input + 25, user_login, None, selected_data_produkcji,
                        None, default_loc, nr_palety, nr_plomby, linia, nr_palety_lp, now_ts
                    ))

                # Record in unified warehouse movement ledger (PW movement)
                WarehouseMovementLedgerRepository.record_movement(
                    movement_type='PW',
                    pallet_id=paleta_id,
                    pallet_code=nr_palety,
                    product_name=nazwa_do_historii,
                    source_location=f"PRODUKCJA_{linia}",
                    target_location=default_loc if not is_original_czyszczenie else "BUFOR_WORKOWANIE",
                    quantity=waga_input,
                    unit='kg',
                    user_login=user_login,
                    reference_id=str(plan_id),
                    notes=f"Utworzono i przyjęto paletę wyrobu gotowego ze zlecenia #{plan_id}",
                    external_conn=conn
                )

                hist_comment = f"Utworzono i przyjęto na {default_loc}: {nazwa_do_historii}, waga: {waga_input} kg"
                if is_original_czyszczenie and nr_palety_czyszczenie:
                    hist_comment += f" (Paleta matka: {nr_palety_czyszczenie})"
                order_loc = f"Zlecenie #{plan_id}: {nazwa_do_historii}"
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'wyrob_gotowy', 'PRZYJECIE', %s, %s, %s, %s)",
                    (paleta_id, nr_palety, linia, order_loc, default_loc if not is_original_czyszczenie else 'BUFOR', hist_comment, user_login)
                )

                if not is_original_czyszczenie:
                    try:
                        from app.services.pallets.pallet_confirmation_service import PalletConfirmationService
                        PalletConfirmationService._trigger_closing_report_print(cursor, plan_id, table_plan, table_pal)
                    except Exception as print_chk_err:
                        current_app.logger.warning('Failed to check closing report auto-print: %s', print_chk_err)
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for paleta %s: %s', paleta_id, hist_err)

            # Packaging deduction for cleaning
            if is_original_czyszczenie:
                try:
                    cursor.execute(f"SELECT opakowanie_id FROM {table_plan} WHERE id=%s", (plan_id,))
                    op_row = cursor.fetchone()
                    opak_id = op_row[0] if op_row else None
                    if opak_id:
                        bags_to_deduct = max(1, int(waga_input / 25))
                        cursor.execute(
                            "UPDATE magazyn_opakowania SET stan_magazynowy = GREATEST(0, stan_magazynowy - %s) WHERE id=%s",
                            (bags_to_deduct, opak_id)
                        )
                        current_app.logger.info("Deducted %s bags for Czyszczenie from folia %s", bags_to_deduct, opak_id)
                except Exception as op_err:
                    current_app.logger.error("Failed to deduct bags for Czyszczenie: %s", op_err)

            conn.commit()

            # Async print
            user_printer_ip = str(printer_ip or '').strip()
            user_printer_name = str(printer_name or '').strip()
            try:
                t = threading.Thread(
                    target=PalletCreationService._async_print_label,
                    args=(paleta_id, nr_palety, linia, app_obj, user_printer_ip, user_printer_name),
                    daemon=True
                )
                t.start()
            except Exception as thr_err:
                current_app.logger.error('Failed to start async print thread for paleta %s: %s', nr_palety, thr_err)

            try:
                PlanningStatusService.ensure_status_after_tonaz_update(plan_id, linia=linia)
            except Exception as error:
                try:
                    current_app.logger.warning('Warning during status validation: %s', error)
                except Exception:
                    pass

            try:
                current_app.logger.info(
                    'Dodano paletę: plan_id=%s, waga=%s kg, data_produkcji=%s, użytkownik=%s',
                    plan_id,
                    waga_input,
                    selected_data_produkcji,
                    user_login,
                )
                audit_log(
                    'Dodał paletę',
                    f'plan_id={plan_id}, produkt={plan_produkt}, waga={waga_input} kg, data_produkcji={selected_data_produkcji}'
                )
            except Exception:
                pass

            if is_original_czyszczenie:
                try:
                    from app.services.pallets.pallet_confirmation_service import PalletConfirmationService
                    PalletConfirmationService.potwierdz_palete(
                        paleta_id=paleta_id,
                        linia=linia,
                        user_login=user_login,
                        app_obj=app_obj,
                        update_paleta_workowanie=None,
                        update_paleta_magazyn=None,
                        is_ajax=is_ajax,
                        safe_return_url=safe_return_url
                    )
                except Exception as auto_zatw_err:
                    current_app.logger.warning("Failed auto confirmation of czyszczenie pallet %s: %s", paleta_id, auto_zatw_err)

        except Exception as error:
            try:
                current_app.logger.exception('Failed to add paleta: %s', error)
            except Exception:
                pass
            conn.rollback()
            conn.close()
            return ('Błąd: Nie udało się dodać paletki', 500, None)

        conn.close()

        if is_ajax:
            return ({'success': True, 'message': 'Paletka dodana', 'paleta_id': paleta_id}, 200, None)

        return ('OK', 302, safe_return_url)
