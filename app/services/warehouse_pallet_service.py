from datetime import date, datetime
import os
import threading
import json
from flask import current_app, request, session, jsonify, flash

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.services.planning.status import PlanningStatusService
from app.utils.pallet_id import generate_pallet_id

from app.blueprints.warehouse.routes.printing_routes import _select_preferred_printer
from app.blueprints.warehouse.routes.palety_helpers import _resolve_plan_id_for_paleta

from app.repositories.warehouse_pallet_repository import WarehousePalletRepository
from app.repositories.warehouse_movement_ledger_repository import WarehouseMovementLedgerRepository

class WarehousePalletService:
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
            user_login = user_login
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
                            nr_palety_lp = cur_lp_val
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
    
            # Manual add should explicitly set production date on the order.
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
    
                # Record in unified warehouse movement ledger (PW movement)
                WarehouseMovementLedgerRepository.record_movement(
                    movement_type='PW',
                    pallet_id=paleta_id,
                    pallet_code=nr_palety,
                    product_name=nazwa_do_historii,
                    source_location=f"PRODUKCJA_{linia}",
                    target_location="BUFOR_WORKOWANIE",
                    quantity=waga_input,
                    unit='kg',
                    user_login=user_login,
                    reference_id=str(plan_id),
                    notes=f"Utworzono paletę wyrobu gotowego ze zlecenia #{plan_id}",
                    external_conn=conn
                )
    
                hist_comment = f"Utworzono paletę: {nazwa_do_historii}, waga: {waga_input} kg"
                if is_original_czyszczenie and nr_palety_czyszczenie:
                    hist_comment += f" (Paleta matka: {nr_palety_czyszczenie})"
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, 'wyrob_gotowy', 'UTWORZENIE', %s, %s)",
                    (paleta_id, nr_palety, linia, hist_comment, user_login)
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for paleta %s: %s', paleta_id, hist_err)
    
            # --- AUTOMATYCZNY WYDRUK 2 ETYKIET ASYNCHRONICZNIE ---
            user_printer_ip = str(printer_ip or '').strip()
            user_printer_name = str(printer_name or '').strip()
    
            def _async_print_label(paleta_id_local, nr_palety_local, app, usr_ip=None, usr_name=None):
                with app.app_context():
                        try:
                            from app.utils.pallet_label import prepare_pallet_label_data
                            conn2 = get_db_connection()
                            cur2 = conn2.cursor()
                            label_data_local = prepare_pallet_label_data(cur2, paleta_id_local, linia, source_table='workowanie')
                        except Exception as prep_err:
                            app.logger.error('Failed to prepare label data for paleta %s: %s', paleta_id_local, prep_err)
                            if 'conn2' in locals() and conn2:
                                try:
                                    conn2.close()
                                except Exception:
                                    pass
                            return
    
                        try:
                            if not label_data_local:
                                app.logger.error('No label data prepared for paleta %s', paleta_id_local)
                                if 'conn2' in locals() and conn2:
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
                                            clean_ip = p_row[0]
                                            override_name = override_name or p_row[1]
                                    except Exception:
                                        clean_ip = None
                                elif clean_ip.isdigit():
                                    try:
                                        cur2.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s AND aktywna = 1", (int(clean_ip),))
                                        p_row = cur2.fetchone()
                                        if p_row:
                                            clean_ip = p_row[0]
                                            override_name = override_name or p_row[1]
                                    except Exception:
                                        pass
                                override_ip = clean_ip or None

                            if not override_ip and override_name:
                                try:
                                    cur2.execute("SELECT ip FROM drukarki WHERE nazwa = %s AND aktywna = 1 LIMIT 1", (override_name,))
                                    p_row = cur2.fetchone()
                                    if p_row and p_row[0]:
                                        override_ip = p_row[0]
                                except Exception:
                                    pass

                            if not override_ip and not override_name:
                                override_name, override_ip = _select_preferred_printer(cur2, linia=linia)
                                
                            try:
                                ok, print_msg = printer_local.print_finished_product_label(
                                    label_data_local,
                                    override_ip=override_ip,
                                    override_name=override_name,
                                    copies=2
                                )
                                app.logger.info(
                                    'Async print (2 copies) for paleta %s: ok=%s printer=%s ip=%s msg=%s',
                                    nr_palety_local, ok, override_name or getattr(printer_local, 'printer_name', None), override_ip or getattr(printer_local, 'printer_ip', None), print_msg
                                )
                            except Exception as single_err:
                                app.logger.error('Print attempt failed for paleta %s: %s', paleta_id_local, single_err)
                                
                            if 'conn2' in locals() and conn2:
                                try:
                                    conn2.close()
                                except Exception:
                                    pass
        
                        except Exception as err:
                            app.logger.error('Unexpected error in async print thread for paleta %s: %s', paleta_id_local, err)
            # ---------------------------------------------
            if is_original_czyszczenie:
                # Rozliczenie straty worków dla czyszczenia
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
    
            try:
                t = threading.Thread(target=_async_print_label, args=(paleta_id, nr_palety, app_obj, user_printer_ip, user_printer_name), daemon=True)
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
    
            try:
                # _mark_dosypki_updated function removed - no longer needed
                # _mark_dosypki_updated(linia)
                pass
            except Exception:
                pass
                
            if is_original_czyszczenie:
                try:
                    WarehousePalletService.potwierdz_palete(
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

    @staticmethod
    def potwierdz_palete(paleta_id, linia, user_login, app_obj, update_paleta_workowanie, update_paleta_magazyn, is_ajax, safe_return_url):
        """Confirm paleta acceptance with warehouse manager/lider."""
        linia = linia
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        table_mag = get_table_name('magazyn_palety', linia)
    
        role = str(session.get('rola', '')).strip()
        if role not in ['magazynier', 'lider', 'admin', 'masteradmin']:
            current_app.logger.warning(
                '[WAREHOUSE-AUTH] User %s with role=%s tried to confirm paleta %s - insufficient permissions',
                user_login,
                role,
                paleta_id,
            )
            return ({'success': False, 'message': 'Brak uprawnień do zatwierdzania palet'}, 403, None)
    
        provided_netto = None
        provided_brutto = None
        deklarowana_waga = None
        weight_difference = None
        has_weight_difference = False
        check_only_request = False
        force_accept_request = False
        status_updated = False
        error_message = None
        open_report_url = None
        is_last_pallet = False
    
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
    
            tara = 25
            try:
                cursor.execute(f"SELECT COALESCE(tara,25) FROM {table_pal} WHERE id=%s", (paleta_id,))
                trow = cursor.fetchone()
                tara = int(trow[0]) if trow and trow[0] is not None else 25
            except Exception as error:
                current_app.logger.warning('Failed to fetch tara for paleta %s: %s', paleta_id, error)
    
            try:
                if request.form.get('waga_palety'):
                    try:
                        provided_netto = int(float(require_field(request.form, 'waga_palety').replace(',', '.')))
                    except (ValueError, Exception):
                        provided_netto = None
                elif request.form.get('waga_brutto'):
                    try:
                        provided_brutto = int(float(require_field(request.form, 'waga_brutto').replace(',', '.')))
                    except (ValueError, Exception):
                        provided_brutto = None
                    if provided_brutto is not None:
                        netto_val = provided_brutto - int(tara)
                        provided_netto = netto_val if netto_val >= 0 else 0
            except Exception as error:
                current_app.logger.error('Failed to parse provided weight for paleta %s: %s', paleta_id, error, exc_info=True)
    
            check_only_request = str(request.form.get('check_only', '')).strip().lower() in ('1', 'true', 'yes')
            force_accept_request = str(request.form.get('force_accept', '')).strip().lower() in ('1', 'true', 'yes')
    
            try:
                cursor.execute(f"SELECT waga FROM {table_pal} WHERE id=%s", (paleta_id,))
                drow = cursor.fetchone()
                if drow and drow[0] is not None:
                    deklarowana_waga = int(drow[0])
            except Exception as error:
                current_app.logger.debug('Failed to fetch declared weight for paleta %s: %s', paleta_id, error)
    
            if deklarowana_waga is not None and provided_netto is not None:
                try:
                    weight_difference = round(abs(provided_netto - deklarowana_waga), 1)
                    has_weight_difference = bool(weight_difference > 1)
                except Exception:
                    weight_difference = None
                    has_weight_difference = False
    
            if is_ajax and check_only_request:
                return (
                    {
                        'success': True,
                        'check_only': True,
                        'has_difference': has_weight_difference,
                        'difference': weight_difference,
                        'requires_confirmation': has_weight_difference,
                    }, 200, None
                )
    
            try:
                if provided_netto is not None:
                    cursor.execute(f"UPDATE {table_pal} SET waga_potwierdzona=%s WHERE id=%s", (provided_netto, paleta_id))
                if provided_brutto is not None:
                    cursor.execute(f"UPDATE {table_pal} SET waga_brutto=%s WHERE id=%s", (provided_brutto, paleta_id))
                if provided_netto is not None or provided_brutto is not None:
                    conn.commit()
            except Exception as error:
                current_app.logger.error('Failed to persist weights for paleta %s: %s', paleta_id, error, exc_info=True)
                try:
                    conn.rollback()
                except Exception:
                    pass
    
            prev_status = ''
            plan_id = None
            stored_netto = None
            try:
                cursor.execute(
                    f"SELECT plan_id, COALESCE(status,''), COALESCE(waga_potwierdzona, waga, 0), nr_palety, nr_plomby FROM {table_pal} WHERE id=%s",
                    (paleta_id,),
                )
                prev_row = cursor.fetchone()
                if prev_row:
                    plan_id = prev_row[0]
                    prev_status = prev_row[1]
                    stored_netto = int(prev_row[2] or 0)
                    nr_palety = prev_row[3]
                    nr_plomby = prev_row[4] if len(prev_row) > 4 else None
            except Exception as error:
                current_app.logger.warning('Failed to fetch plan_id/status/weights for paleta %s: %s', paleta_id, error)
    
            user_login = user_login
            try:
                if linia == 'AGRO':
                    cursor.execute(
                        f"UPDATE {table_pal} SET status='przyjeta', "
                        "data_potwierdzenia = DATE_ADD(data_dodania, INTERVAL TIMESTAMPDIFF(SECOND, data_dodania, NOW()) SECOND), "
                        "czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW()), "
                        "czas_rzeczywistego_potwierdzenia = SEC_TO_TIME(TIMESTAMPDIFF(SECOND, data_dodania, NOW())) "
                        f"WHERE id=%s",
                        (paleta_id,),
                    )
                else:
                    cursor.execute(f"UPDATE {table_pal} SET status='przyjeta' WHERE id=%s", (paleta_id,))
                conn.commit()
                status_updated = True
            except Exception as error:
                current_app.logger.warning('Complex update failed for paleta %s: %s, retrying simple update', paleta_id, error)
                try:
                    cursor.execute(f"UPDATE {table_pal} SET status='przyjeta' WHERE id=%s", (paleta_id,))
                    conn.commit()
                    status_updated = True
                except Exception as second_error:
                    current_app.logger.error('Simple status update also failed for paleta %s: %s', paleta_id, second_error, exc_info=True)
                    error_message = str(second_error)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    
            if not status_updated:
                if is_ajax:
                    return ({'success': False, 'message': f'Nie udało się zatwierdzić palety: {error_message or "błąd zapisu statusu"}'}, 500, None)
                return ('OK', 302, safe_return_url)
    
            if plan_id:
                netto_val = provided_netto if provided_netto is not None else stored_netto
    
                try:
                    cursor.execute(f"SELECT data_planu, produkt, data_produkcji FROM {table_plan} WHERE id=%s", (plan_id,))
                    row = cursor.fetchone()
                    if row and prev_status not in ('przyjeta', 'w_magazynie'):
                        if linia == 'AGRO':
                            mp_id = plan_id
                        else:
                            cursor.execute(f"SELECT id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' LIMIT 1", (row[0], row[1]))
                            mp = cursor.fetchone()
                            mp_id = mp[0] if mp else None
    
                        nr_partii = request.form.get('nr_partii')
                        
                        # Check request.form, then fallback to plan's data_produkcji, then fallback to plan's date, then fallback to current date
                        data_produkcji = request.form.get('data_produkcji') if request else None
                        if not data_produkcji or not data_produkcji.strip():
                            plan_prod_date = row[2]
                            if plan_prod_date:
                                if hasattr(plan_prod_date, 'strftime'):
                                    data_produkcji = plan_prod_date.strftime('%Y-%m-%d')
                                else:
                                    data_produkcji = str(plan_prod_date)
                            else:
                                plan_date = row[0]
                                if plan_date:
                                    if hasattr(plan_date, 'strftime'):
                                        data_produkcji = plan_date.strftime('%Y-%m-%d')
                                    else:
                                        data_produkcji = str(plan_date)
                                else:
                                    from datetime import datetime
                                    data_produkcji = datetime.now().strftime('%Y-%m-%d')
    
                        data_przydatnosci = request.form.get('data_przydatnosci')
                        lokalizacja = request.form.get('lokalizacja')
    
                        prod_name_str = str(row[1] or '').strip()
                        is_czyszczenie_product = (
                            prod_name_str in ('Czyszczenie', 'Maka Mix do Lnu', 'Mąka mix do Lnu')
                            or 'czyszczenie' in prod_name_str.lower()
                            or 'maka mix do lnu' in prod_name_str.lower()
                            or 'mąka mix do lnu' in prod_name_str.lower()
                        )

                        if is_czyszczenie_product:
                            import uuid, json
                            from datetime import datetime
                            from app.utils.pallet_label import lookup_raw_material_details_by_sscc, _format_date

                            # Get mother pallet SSCC from plan
                            mother_sscc = None
                            try:
                                cursor.execute(
                                    f"SELECT skan_sscc FROM {table_plan} WHERE (id = %s OR id = (SELECT COALESCE(zasyp_id, -1) FROM {table_plan} WHERE id = %s)) AND skan_sscc IS NOT NULL AND TRIM(skan_sscc) <> '' LIMIT 1",
                                    (plan_id, plan_id)
                                )
                                sscc_row = cursor.fetchone()
                                if sscc_row and sscc_row[0]:
                                    mother_sscc = str(sscc_row[0]).strip()
                            except Exception as sscc_err:
                                current_app.logger.warning('Failed to find mother skan_sscc for plan %s: %s', plan_id, sscc_err)

                            # Output raw material (Mąka mix do Lnu) MUST have its own unique SSCC, NEVER the mother pallet SSCC!
                            child_sscc = nr_palety
                            if not child_sscc or child_sscc == mother_sscc:
                                child_sscc = generate_pallet_id(linia, 'surowiec')
                                cursor.execute(f"UPDATE {table_pal} SET nr_palety=%s WHERE id=%s", (child_sscc, paleta_id))
                                nr_palety = child_sscc

                            orig_meta = lookup_raw_material_details_by_sscc(cursor, mother_sscc or nr_palety)
                            orig_partia = str(orig_meta.get('nr_partii') or request.form.get('nr_partii') or '').strip()
                            orig_data_prod = _format_date(orig_meta.get('data_produkcji')) or data_produkcji
                            orig_data_przyd = _format_date(orig_meta.get('data_przydatnosci')) or request.form.get('data_przydatnosci') or ''

                            dostawa_id = str(uuid.uuid4())
                            item_name = "Mąka mix do Lnu"
                            final_amount = float(netto_val if netto_val and netto_val > 0 else stored_netto or 0)
                            items = [{
                                "id": str(uuid.uuid4()),
                                "type": "surowiec",
                                "name": item_name,
                                "productName": item_name,
                                "amount": final_amount,
                                "netWeight": final_amount,
                                "quantity": final_amount,
                                "unit": "kg",
                                "confirmed": False,
                                "nr_palety": nr_palety,
                                "sourcePalletNo": mother_sscc or nr_palety,
                                "nr_partii": orig_partia,
                                "data_produkcji": orig_data_prod,
                                "data_przydatnosci": orig_data_przyd
                            }]
                            try:
                                cursor.execute("""
                                    INSERT INTO magazyn_dostawy
                                        (id, order_ref, supplier, delivery_date, status, items,
                                         created_by, created_at, requires_lab, linia)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                """, (dostawa_id, f"Czyszczenie Zlecenie #{plan_id}", "PRODUKCJA", data_produkcji, "OCZEKUJE",
                                      json.dumps(items), user_login, datetime.now(), 0, linia))
                                mag_id = None
                                
                                # Update status to przeklasyfikowana
                                cursor.execute(f"UPDATE {table_pal} SET status='przeklasyfikowana' WHERE id=%s", (paleta_id,))
                                
                                # Copy history from mother pallet into palety_historia for new pallet
                                if mother_sscc:
                                    try:
                                        cursor.execute("""
                                            SELECT linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu
                                            FROM palety_historia
                                            WHERE (nr_palety IS NOT NULL AND nr_palety = %s)
                                            ORDER BY data_ruchu ASC, id ASC
                                        """, (mother_sscc,))
                                        mother_history = cursor.fetchall() or []
                                        for h in mother_history:
                                            h_linia = (h.get('linia') if isinstance(h, dict) else h[0]) or linia
                                            h_typ = (h.get('typ_palety') if isinstance(h, dict) else h[1]) or 'surowiec'
                                            h_akcja = (h.get('akcja') if isinstance(h, dict) else h[2])
                                            h_zrodlo = (h.get('lokalizacja_zrodlowa') if isinstance(h, dict) else h[3])
                                            h_cel = (h.get('lokalizacja_docelowa') if isinstance(h, dict) else h[4])
                                            h_kom = (h.get('komentarz') if isinstance(h, dict) else h[5])
                                            h_user = (h.get('user_login') if isinstance(h, dict) else h[6])
                                            h_data = (h.get('data_ruchu') if isinstance(h, dict) else h[7]) or datetime.now()
                                            cursor.execute("""
                                                INSERT INTO palety_historia
                                                (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu)
                                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                            """, (
                                                paleta_id, nr_palety, h_linia, h_typ, h_akcja,
                                                h_zrodlo, h_cel, h_kom, h_user, h_data
                                            ))
                                    except Exception as hist_copy_err:
                                        current_app.logger.warning('Failed to copy mother pallet history for %s: %s', nr_palety, hist_copy_err)

                                reclass_comment = f"Przeklasyfikowano na surowiec: {item_name} z palety matki {mother_sscc}. Oczekuje w dostawach" if mother_sscc else f"Przeklasyfikowano na surowiec: {item_name}. Oczekuje w dostawach"
                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'surowiec', 'PRZEKLASYFIKOWANIE', %s, %s, %s)",
                                    (paleta_id, nr_palety, linia, lokalizacja, reclass_comment, user_login)
                                )

                                if mother_sscc:
                                    try:
                                        cursor.execute(
                                            "INSERT INTO palety_historia (nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, 'surowiec', 'PRZEKLASYFIKOWANIE_POTOMNA', %s, %s)",
                                            (mother_sscc, linia, f"Wykorzystano do czyszczenia w zleceniu #{plan_id}. Nowa paleta potomna: {nr_palety} ({item_name}, {final_amount} kg)", user_login)
                                        )
                                    except Exception as m_log_err:
                                        current_app.logger.warning('Failed to log child link on mother pallet %s: %s', mother_sscc, m_log_err)
                            except Exception as e:
                                current_app.logger.error('Database error for Czyszczenie dostawa: %s', e)
                        else:
                            try:
                                pw_lp_val = None
                                try:
                                    cursor.execute(f"SHOW COLUMNS FROM {table_pal} LIKE 'nr_palety_lp'")
                                    if cursor.fetchone():
                                        cursor.execute(f"SELECT nr_palety_lp FROM {table_pal} WHERE id = %s", (paleta_id,))
                                        pw_lp_row = cursor.fetchone()
                                        pw_lp_val = pw_lp_row[0] if pw_lp_row else None
                                except Exception:
                                    pw_lp_val = None

                                has_mag_lp = False
                                try:
                                    cursor.execute(f"SHOW COLUMNS FROM {table_mag} LIKE 'nr_palety_lp'")
                                    has_mag_lp = bool(cursor.fetchone())
                                except Exception:
                                    has_mag_lp = False

                                if has_mag_lp:
                                    cursor.execute(
                                        f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby, nr_palety_lp) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                        (paleta_id, mp_id, row[0], row[1], netto_val, provided_brutto if provided_brutto is not None else 0, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby, pw_lp_val),
                                    )
                                else:
                                    cursor.execute(
                                        f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                        (paleta_id, mp_id, row[0], row[1], netto_val, provided_brutto if provided_brutto is not None else 0, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby),
                                    )
                                mag_id = cursor.lastrowid
                                
                                # Log to palety_historia
                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'PRZYJECIE', %s, %s, %s)",
                                    (paleta_id, linia, lokalizacja, f"Przyjęcie palety: {row[1]}, partia: {nr_partii}", user_login)
                                )
                            except mysql.connector.Error as e:
                                current_app.logger.debug('Database error for paleta %s in %s: %s', paleta_id, table_mag, e)

    
                        if cursor.rowcount > 0:
                            current_app.logger.info(
                                'Potwierdzono paletę ID=%s: waga_netto=%s kg, produkt=%s, użytkownik=%s, lokalizacja=%s',
                                paleta_id,
                                netto_val,
                                row[1] if len(row) > 1 else '—',
                                user_login,
                                lokalizacja
                            )
                            audit_log('Potwierdził paletę', f'ID={paleta_id}, produkt={row[1] if len(row) > 1 else "—"}, waga_netto={netto_val} kg, lokalizacja={lokalizacja}')
                        else:
                            current_app.logger.debug('Paleta ID=%s już jest w magazynie (INSERT IGNORE pominął duplikat), waga=%s kg', paleta_id, netto_val)
    
                        cursor.execute(
                            f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto),0) FROM {table_mag} WHERE plan_id = {table_plan}.id) WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'",
                            (row[0], row[1]),
                        )
                        conn.commit()
                        
                        # --- Automatyczny wydruk raportu na drukarce biurowej i otwarcie raportu dla magazyniera, jeśli to ostatnia paleta w zakończonym zleceniu ---
                        printed_msg = None
                        try:
                            cursor.execute(f"SELECT status, sekcja FROM {table_plan} WHERE id=%s", (plan_id,))
                            plan_status_row = cursor.fetchone()
                            if plan_status_row and str(plan_status_row[0]).strip().lower() in ('zakończone', 'zakończony', 'zakonczone'):
                                cursor.execute(f"SELECT COUNT(id) FROM {table_pal} WHERE plan_id=%s", (plan_id,))
                                total_pallets = cursor.fetchone()[0] or 0
                                
                                cursor.execute(f"SELECT COUNT(id) FROM {table_pal} WHERE plan_id=%s AND status IN ('przyjeta', 'w_magazynie')", (plan_id,))
                                accepted_pallets = cursor.fetchone()[0] or 0
                                
                                if total_pallets > 0 and total_pallets == accepted_pallets:
                                    is_last_pallet = True
                                    current_app.logger.info("Magazynier przyjął ostatnią paletę zlecenia %s (%s). Wyzwalanie wydruku biurowego i raportu.", plan_id, linia)
                                    from app.services.office_print_service import trigger_office_print
                                    typ = 'raport_palet_agro' if linia == 'AGRO' else 'raport_palet_psd'
                                    trigger_office_print(plan_id, typ_raportu=typ)
                                    printed_msg = "Zlecenie zamknięte - przyjęto ostatnią paletę. Raport z produkcji został otwarty do wydruku."
                                    if linia == 'AGRO':
                                        try:
                                            from flask import url_for
                                            open_report_url = url_for('agro_warehouse.raport_palet', plan_id=plan_id, autoprint=1)
                                        except Exception:
                                            open_report_url = f"/agro/raport_palet?plan_id={plan_id}&autoprint=1"
                                    else:
                                        try:
                                            from flask import url_for
                                            open_report_url = url_for('warehouse_v2.raport_palet', linia='PSD', plan_id=plan_id, autoprint=1)
                                        except Exception:
                                            open_report_url = f"/warehouse-v2/psd/raport_palet?plan_id={plan_id}&autoprint=1"
                        except Exception as print_err:
                            current_app.logger.error('Failed to check/trigger auto-print for plan %s: %s', plan_id, print_err)
                        # ---------------------------------------------------------------------------------------------------------
                except Exception as error:
                    current_app.logger.error('Failed to update Magazyn aggregates for paleta %s: %s', paleta_id, error, exc_info=True)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                        
            try:
                # _mark_dosypki_updated function removed - no longer needed
                # _mark_dosypki_updated(linia)
                pass
            except Exception:
                pass
    
        except Exception as error:
            current_app.logger.error('Failed to potwierdz palete %s: %s', paleta_id, error, exc_info=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
        try:
            if is_ajax:
                response_data = {'success': True, 'paleta_id': paleta_id}
                if 'printed_msg' in locals() and printed_msg:
                    response_data['message'] = printed_msg
                if open_report_url:
                    response_data['open_report_url'] = open_report_url
                    response_data['is_last_pallet'] = is_last_pallet
                    response_data['plan_id'] = plan_id
                if has_weight_difference and not force_accept_request:
                    response_data['has_difference'] = True
                    response_data['difference'] = weight_difference
                return (response_data, 200, None)
        except Exception:
            pass
        if open_report_url:
            return ('OK', 302, open_report_url)
        return ('OK', 302, safe_return_url)

    @staticmethod
    def usun_palete(id, linia, user_login, is_ajax, safe_return_url, conn=None):
        """Delete paleta from buffer."""
        linia = str(linia).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        own_conn = False
        try:
            if conn is None:
                conn = get_db_connection()
                own_conn = True
            cursor = conn.cursor()
    
            cursor.execute(f"SELECT plan_id FROM {table_pal} WHERE id=%s", (id,))
            res = cursor.fetchone()
    
            if not res:
                msg = f'Paleta ID={id} nie istnieje'
                current_app.logger.warning('[WAREHOUSE-DELETE] %s', msg)
                if is_ajax:
                    return ({'success': False, 'message': msg}, 404, None)
                # flash(msg, 'warning')
                return ('OK', 302, safe_return_url)
    
            plan_id = res[0]
            
            # Get paleta details for history before deletion
            cursor.execute(f"SELECT waga, nr_palety, status FROM {table_pal} WHERE id=%s", (id,))
            paleta_data = cursor.fetchone()
            waga_val = paleta_data[0] if paleta_data else 0
            nr_palety_val = paleta_data[1] if paleta_data and len(paleta_data) > 1 else None
            status_val = paleta_data[2] if paleta_data and len(paleta_data) > 2 else 'unknown'
            
            cursor.execute(f"DELETE FROM {table_pal} WHERE id=%s", (id,))
            
            # Log to palety_historia - usunięcie palety
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'USUNIECIE', %s, %s)",
                    (id, linia, f"Usunięto paletę z workowania: {nr_palety_val or 'ID='+str(id)}, waga: {waga_val} kg, status: {status_val}", user_login)
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for deleted paleta %s: %s', id, hist_err)
            
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s) WHERE id = %s",
                (plan_id, plan_id),
            )
            conn.commit()
    
            current_app.logger.info('Usunięto paletę ID=%s, plan_id=%s, użytkownik=%s', id, plan_id, user_login)
            audit_log('Usunął paletę', f'ID={id}, plan_id={plan_id}')
            msg = 'Paleta usunięta'
    
            if is_ajax:
                return ({'success': True, 'message': msg}, 200, None)
    
            # flash(msg, 'success')
        except Exception as error:
            current_app.logger.error('[WAREHOUSE-DELETE] Error deleting paleta %s: %s', id, error, exc_info=True)
            if is_ajax:
                return ({'success': False, 'message': f'Błąd: {str(error)}'}), 500
            # flash(f'Błąd przy usuwaniu palety: {str(error)}', 'danger')
        finally:
            if own_conn and conn:
                try:
                    conn.close()
                except Exception:
                    pass
    
        return ('OK', 302, safe_return_url)

    @staticmethod
    def edytuj_palete(paleta_id, linia, waga_palety, user_login, update_paleta_workowanie, is_ajax, safe_return_url):
        """Edit paleta weight (netto) in buffer or warehouse."""
        linia_input = str(linia or 'PSD').upper()
        lines_to_try = [linia_input]
        other_line = 'AGRO' if linia_input == 'PSD' else 'PSD'
        lines_to_try.append(other_line)

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                waga = int(float(str(waga_palety).replace(',', '.')))
            except Exception:
                waga = 0

            target_found = False
            effective_line = linia_input
            updated_info = {}

            for line in lines_to_try:
                table_mag = get_table_name('magazyn_palety', line)
                table_pal = get_table_name('palety_workowanie', line)
                table_plan = get_table_name('plan_produkcji', line)

                # 1. Check if paleta_id matches magazyn_palety by primary key ID (e.g. from warehouse table)
                cursor.execute(
                    f"SELECT id, paleta_workowanie_id, plan_id, waga_netto, nr_palety, tara FROM {table_mag} WHERE id=%s LIMIT 1",
                    (paleta_id,)
                )
                mag_row = cursor.fetchone()
                if mag_row:
                    mag_id, work_id, plan_id, old_netto, nr_palety, tara = mag_row
                    tara_val = float(tara or 0.0)
                    new_brutto = float(waga) + tara_val

                    # Update magazyn_palety
                    cursor.execute(
                        f"UPDATE {table_mag} SET waga_netto=%s, waga_brutto=%s WHERE id=%s",
                        (waga, new_brutto, mag_id)
                    )

                    # Update palety_workowanie / palety_agro if linked
                    if work_id:
                        cursor.execute(
                            f"UPDATE {table_pal} SET waga_potwierdzona=%s, waga=%s WHERE id=%s",
                            (waga, waga, work_id)
                        )

                    # Update tonaz_rzeczywisty in plan
                    if plan_id:
                        cursor.execute(
                            f"""
                            UPDATE {table_plan} pp
                            SET tonaz_rzeczywisty = (
                                SELECT COALESCE(SUM(mp.waga_netto), 0)
                                FROM {table_mag} mp
                                WHERE mp.plan_id = pp.id
                            )
                            WHERE pp.id = %s
                            """,
                            (plan_id,)
                        )

                    target_found = True
                    effective_line = line
                    updated_info = {
                        'type': 'magazyn',
                        'mag_id': mag_id,
                        'work_id': work_id,
                        'nr_palety': nr_palety,
                        'old_waga': old_netto,
                        'new_waga': waga,
                        'plan_id': plan_id
                    }
                    break

                # 2. Check if paleta_id matches palety_workowanie / palety_agro by primary key ID
                cursor.execute(
                    f"SELECT id, plan_id, waga, waga_potwierdzona, status, nr_palety, tara FROM {table_pal} WHERE id=%s LIMIT 1",
                    (paleta_id,)
                )
                pal_row = cursor.fetchone()
                if pal_row:
                    p_id = pal_row[0]
                    plan_id = pal_row[1] if len(pal_row) > 1 else None
                    old_w = pal_row[2] if len(pal_row) > 2 else 0
                    old_conf = pal_row[3] if len(pal_row) > 3 else None
                    status = pal_row[4] if len(pal_row) > 4 else ''
                    nr_palety = pal_row[5] if len(pal_row) > 5 else None
                    p_tara = pal_row[6] if len(pal_row) > 6 else 0.0
                    status_str = status or ''

                    if status_str in ('przyjeta', 'w_magazynie'):
                        cursor.execute(
                            f"UPDATE {table_pal} SET waga_potwierdzona=%s, waga=%s WHERE id=%s",
                            (waga, waga, p_id)
                        )
                        old_val = old_conf or old_w

                        # Also sync linked magazyn_palety if exists
                        tara_val = float(p_tara or 0.0)
                        new_brutto = float(waga) + tara_val
                        cursor.execute(
                            f"UPDATE {table_mag} SET waga_netto=%s, waga_brutto=%s WHERE paleta_workowanie_id=%s",
                            (waga, new_brutto, p_id)
                        )
                    else:
                        cursor.execute(
                            f"UPDATE {table_pal} SET waga=%s WHERE id=%s",
                            (waga, p_id)
                        )
                        old_val = old_w

                    if plan_id:
                        if status_str in ('przyjeta', 'w_magazynie'):
                            cursor.execute(
                                f"""
                                UPDATE {table_plan} pp
                                SET tonaz_rzeczywisty = (
                                    SELECT COALESCE(SUM(mp.waga_netto), 0)
                                    FROM {table_mag} mp
                                    WHERE mp.plan_id = pp.id
                                )
                                WHERE pp.id = %s
                                """,
                                (plan_id,)
                            )
                        else:
                            cursor.execute(
                                f"""
                                UPDATE {table_plan}
                                SET tonaz_rzeczywisty = (
                                    SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s
                                )
                                WHERE id = %s
                                """,
                                (plan_id, plan_id)
                            )

                    target_found = True
                    effective_line = line
                    updated_info = {
                        'type': 'workowanie',
                        'work_id': p_id,
                        'nr_palety': nr_palety,
                        'old_waga': old_val,
                        'new_waga': waga,
                        'plan_id': plan_id
                    }
                    break

            if not target_found:
                msg = f'Paleta ID={paleta_id} nie istnieje'
                current_app.logger.warning('[WAREHOUSE-EDIT] %s', msg)
                if is_ajax:
                    return ({'success': False, 'message': msg}, 404, None)
                flash(msg, 'warning')
                return ('OK', 302, safe_return_url)

            # Log history in palety_historia
            old_waga = updated_info.get('old_waga', 0)
            hist_pal_id = updated_info.get('work_id') or updated_info.get('mag_id') or paleta_id
            nr_pal_str = updated_info.get('nr_palety') or f"ID={paleta_id}"
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'EDYCJA_WAGI', %s, %s)",
                    (hist_pal_id, effective_line, f"Zmieniono wagę palety {nr_pal_str}: {old_waga} kg → {waga} kg", user_login)
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for edited paleta %s: %s', paleta_id, hist_err)

            conn.commit()
            current_app.logger.info('Edytowano paletę %s (%s), waga=%s kg, użytkownik=%s', nr_pal_str, effective_line, waga, user_login)
            audit_log('Edytował paletę', f'Paleta={nr_pal_str}, linia={effective_line}, waga={waga} kg')

            msg = f'Paleta zaktualizowana (waga={waga} kg)'
            if is_ajax:
                return ({'success': True, 'message': msg}, 200, None)
            flash(msg, 'success')
            return ('OK', 302, safe_return_url)

        except Exception as error:
            current_app.logger.error('[WAREHOUSE-EDIT] Failed to edit paleta %s: %s', paleta_id, error, exc_info=True)
            if is_ajax:
                return ({'success': False, 'message': f'Błąd przy edytowaniu palety: {str(error)}'}), 500, None
            flash(f'Błąd przy edytowaniu palety: {str(error)}', 'danger')
            return ('OK', 302, safe_return_url)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

