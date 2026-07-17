from datetime import date, datetime
import os
import threading

import mysql.connector
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required, masteradmin_required
from app.services.planning.status import PlanningStatusService
from app.utils.validation import require_field
from app.utils.pallet_id import generate_pallet_id

from .printing_routes import _select_preferred_printer
from .misc_routes import _parse_data_produkcji_input
from .palety_helpers import _resolve_plan_id_for_paleta

def _resolve_plan_id_for_paleta(cursor, paleta_id, linia, requested_plan_id=None):
    """Resolve Workowanie plan_id for a pallet id from magazyn/buffer tables safely."""
    table_pal = get_table_name('palety_workowanie', linia)
    table_mag = get_table_name('magazyn_palety', linia)

    requested_id = None
    try:
        if requested_plan_id not in (None, '', 'None'):
            requested_id = int(requested_plan_id)
    except Exception:
        requested_id = None

    if requested_id:
        # Validate that requested plan_id really belongs to this pallet.
        cursor.execute(
            f"SELECT 1 FROM {table_mag} WHERE (id=%s OR paleta_workowanie_id=%s) AND plan_id=%s LIMIT 1",
            (paleta_id, paleta_id, requested_id),
        )
        if cursor.fetchone():
            return requested_id

        cursor.execute(
            f"SELECT 1 FROM {table_pal} WHERE id=%s AND plan_id=%s LIMIT 1",
            (paleta_id, requested_id),
        )
        if cursor.fetchone():
            return requested_id

    # First check magazyn table by confirmed pallet id/pointer.
    # This avoids id-collision with palety_workowanie IDs.
    cursor.execute(
        f'''
        SELECT COALESCE(mp.plan_id, pw.plan_id)
        FROM {table_mag} mp
        LEFT JOIN {table_pal} pw ON pw.id = mp.paleta_workowanie_id
        WHERE mp.id = %s OR mp.paleta_workowanie_id = %s
        ORDER BY CASE WHEN mp.id = %s THEN 0 ELSE 1 END, mp.id DESC
        LIMIT 1
        ''',
        (paleta_id, paleta_id, paleta_id),
    )
    row = cursor.fetchone()
    if row and row[0]:
        return int(row[0])

    cursor.execute(f"SELECT plan_id FROM {table_pal} WHERE id=%s", (paleta_id,))
    row = cursor.fetchone()
    if row and row[0]:
        return int(row[0])

    return None

def register_palety_routes(warehouse_bp, *, resolve_request_linia, resolve_payload_linia, update_paleta_workowanie, update_paleta_magazyn, safe_return):
    def dodaj_palete(plan_id):
        """Add paleta (package) to Workowanie buffer."""
        linia = resolve_request_linia()
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        table_zasypy = get_table_name('szarze', linia)
    
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            current_app.logger.debug('dodaj_palete: plan_id=%s', plan_id)
        except Exception:
            pass
    
        try:
            waga_input = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
        except Exception:
            waga_input = 0
    
        nr_plomby = str(request.form.get('nr_plomby') or '').strip()
        if not nr_plomby:
            nr_plomby = None
        elif len(nr_plomby) > 100:
            nr_plomby = nr_plomby[:100]
    
        cursor.execute(f"SELECT sekcja, data_planu, produkt, data_produkcji, zasyp_id FROM {table_plan} WHERE id=%s", (plan_id,))
        plan_row = cursor.fetchone()
    
        if not plan_row:
            conn.close()
            return ('Błąd: Plan nie znaleziony', 404)
    
        now_ts = datetime.now()
        plan_sekcja, _plan_data, plan_produkt, plan_data_produkcji, plan_zasyp_id = plan_row
    
        input_data_produkcji = str(request.form.get('data_produkcji') or '').strip()
        if input_data_produkcji:
            try:
                datetime.strptime(input_data_produkcji, '%Y-%m-%d')
            except ValueError:
                conn.close()
                return ('Błąd: Nieprawidłowy format daty produkcji (oczekiwano RRRR-MM-DD)', 400)
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
            return ('Błąd: Paletki można dodawać tylko do Workowania (bufora) lub Czyszczenia', 400)
    
        if waga_input <= 0:
            conn.close()
            return ('Błąd: Waga musi być większa od 0', 400)
    
        try:
            user_login = session.get('login', 'System')
            paleta_id = None
            nr_palety = None
    
            # If there are reserved labels for this plan, consume the oldest one first.
            cursor.execute(
                f"SELECT id, nr_palety FROM {table_pal} WHERE plan_id = %s AND COALESCE(status, '') = 'rezerwacja' ORDER BY id ASC LIMIT 1",
                (plan_id,),
            )
            reserved_row = cursor.fetchone()
    
            nr_palety_czyszczenie = None
            if plan_produkt == 'Czyszczenie':
                cursor.execute(f"SELECT skan_sscc FROM {table_plan} WHERE id IN (%s, %s) AND skan_sscc IS NOT NULL LIMIT 1", (plan_id, plan_zasyp_id or -1))
                sscc_row = cursor.fetchone()
                if sscc_row and sscc_row[0]:
                    nr_palety_czyszczenie = sscc_row[0]
    
            if reserved_row:
                paleta_id = reserved_row[0]
                if plan_produkt == 'Czyszczenie' and nr_palety_czyszczenie:
                    nr_palety = nr_palety_czyszczenie
                else:
                    nr_palety = reserved_row[1] or generate_pallet_id(linia)
                cursor.execute(
                    f"UPDATE {table_pal} SET waga = %s, tara = 25, waga_brutto = 0, data_dodania = %s, status = 'do_przyjecia', dodal_login = %s, nr_palety = %s, nr_plomby = COALESCE(%s, nr_plomby) WHERE id = %s",
                    (waga_input, now_ts, user_login, nr_palety, nr_plomby, paleta_id),
                )
            else:
                if plan_produkt == 'Czyszczenie' and nr_palety_czyszczenie:
                    nr_palety = nr_palety_czyszczenie
                else:
                    nr_palety = generate_pallet_id(linia)
                cursor.execute(
                    f"INSERT INTO {table_pal} (plan_id, waga, tara, waga_brutto, data_dodania, status, dodal_login, nr_palety, nr_plomby) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia', %s, %s, %s)",
                    (plan_id, waga_input, now_ts, user_login, nr_palety, nr_plomby),
                )
                paleta_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
    
            # Compute sequential pallet number (nr_palety_lp) for this plan and store it if column exists
            try:
                if paleta_id:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, paleta_id))
                    res_lp = cursor.fetchone()
                    nr_palety_lp = int(res_lp[0]) if res_lp else 1
                    # check if column exists
                    try:
                        cursor.execute(f"SHOW COLUMNS FROM {table_pal} LIKE 'nr_palety_lp'")
                        col = cursor.fetchone()
                        if col:
                            cursor.execute(f"UPDATE {table_pal} SET nr_palety_lp = %s WHERE id = %s", (nr_palety_lp, paleta_id))
                    except Exception:
                        # ignore if SHOW COLUMNS or UPDATE fails on older schemas
                        pass
            except Exception:
                pass
    
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
                if plan_produkt == 'Czyszczenie':
                    is_original_czyszczenie = True
                    nazwa_do_historii = "Maka Mix do Lnu"
                    # Zaktualizuj nazwe produktu w zleceniu
                    cursor.execute(f"UPDATE {table_plan} SET produkt = %s WHERE id = %s", (nazwa_do_historii, plan_id))
                    plan_produkt = nazwa_do_historii
    
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'UTWORZENIE', %s, %s)",
                    (paleta_id, linia, f"Utworzono paletę: {nazwa_do_historii}, waga: {waga_input} kg", user_login)
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for paleta %s: %s', paleta_id, hist_err)
    
            # --- AUTOMATYCZNY WYDRUK 2 ETYKIET ASYNCHRONICZNIE ---
            app_obj = current_app._get_current_object()
            
            user_printer_ip = str(request.form.get('printer_ip') or '').strip()
            user_printer_name = str(request.form.get('printer_name') or '').strip()
    
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
                            
                            if usr_ip or usr_name:
                                override_ip = usr_ip or None
                                override_name = usr_name or None
                            else:
                                override_name, override_ip = _select_preferred_printer(cur2)
                                
                            for copy_num in range(1, 3):
                                try:
                                    ok, print_msg = printer_local.print_finished_product_label(
                                        label_data_local,
                                        override_ip=override_ip,
                                        override_name=override_name,
                                    )
                                    app.logger.info(
                                        'Async print copy %s/2 for paleta %s: ok=%s printer=%s ip=%s msg=%s',
                                        copy_num, nr_palety_local, ok, override_name or getattr(printer_local, 'printer_name', None), override_ip or getattr(printer_local, 'printer_ip', None), print_msg
                                    )
                                except Exception as single_err:
                                    app.logger.error('Print attempt failed for paleta %s copy %s: %s', paleta_id_local, copy_num, single_err)
                                
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
                    session.get('login'),
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
    
        except Exception as error:
            try:
                current_app.logger.exception('Failed to add paleta: %s', error)
            except Exception:
                pass
            conn.rollback()
            conn.close()
            return ('Błąd: Nie udało się dodać paletki', 500)
    
        conn.close()
    
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Paletka dodana', 'paleta_id': paleta_id}), 200
    
        return redirect(safe_return())

    def dodaj_palete_page(plan_id):
        """Render form for adding paleta."""
        # This endpoint is intended to be loaded into a modal via AJAX (data-slide).
        # If accessed directly (full-page navigation), redirect back to a safe page
        # to avoid exposing the popup as a standalone page.
        if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
            return redirect(safe_return())
        linia = str(resolve_request_linia()).upper()
        table_plan = get_table_name('plan_produkcji', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        produkt = None
        sekcja = None
        typ = None
        data_produkcji = date.today().isoformat()
        try:
            cursor.execute(f"SELECT produkt, sekcja, typ_produkcji, data_produkcji FROM {table_plan} WHERE id=%s", (plan_id,))
            row = cursor.fetchone()
            if row:
                produkt, sekcja, typ = row[0], row[1], row[2]
                plan_data_produkcji = row[3] if len(row) > 3 else None
                if plan_data_produkcji:
                    if hasattr(plan_data_produkcji, 'strftime'):
                        data_produkcji = plan_data_produkcji.strftime('%Y-%m-%d')
                    else:
                        data_produkcji = str(plan_data_produkcji)
        except Exception as error:
            current_app.logger.error('Failed to fetch plan %s for dodaj_palete_page: %s', plan_id, error, exc_info=True)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        return render_template(
            'warehouse/popups/add_pallet.html',
            plan_id=plan_id,
            produkt=produkt,
            sekcja=sekcja,
            typ=typ,
            linia=linia,
            data_produkcji=data_produkcji,
        )

    def edytuj_palete_page(paleta_id):
        """Render form for editing paleta weight."""
        linia = str(resolve_request_linia()).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        waga = None
        sekcja = None
        try:
            cursor.execute(f"SELECT waga, plan_id FROM {table_pal} WHERE id=%s", (paleta_id,))
            row = cursor.fetchone()
            if row:
                waga = row[0]
                plan_id = row[1]
                cursor.execute(f"SELECT sekcja FROM {table_plan} WHERE id=%s", (plan_id,))
                r2 = cursor.fetchone()
                if r2:
                    sekcja = r2[0]
        except Exception as error:
            current_app.logger.error('Failed to load paleta %s for edit page: %s', paleta_id, error, exc_info=True)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        return render_template('warehouse/popups/edit_pallet.html', paleta_id=paleta_id, waga=waga, sekcja=sekcja, linia=linia)

    def confirm_delete_palete_page(paleta_id):
        """Render delete confirmation for paleta."""
        linia = resolve_request_linia()
        source = request.args.get('source', '')
        return render_template('warehouse/popups/delete_pallet_confirm.html', paleta_id=paleta_id, linia=linia, source=source)

    def potwierdz_palete_page(paleta_id):
        """Render form for confirming paleta acceptance."""
        linia = str(resolve_request_linia()).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        waga = None
        try:
            cursor.execute(f"SELECT waga, waga_brutto, tara FROM {table_pal} WHERE id=%s", (paleta_id,))
            row = cursor.fetchone()
            if row:
                waga = row[0]
        except Exception as error:
            current_app.logger.error('Failed to load paleta %s for potwierdz_palete_page: %s', paleta_id, error, exc_info=True)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        dzisiaj_iso = date.today().isoformat()
        return render_template('warehouse/popups/confirm_pallet.html', paleta_id=paleta_id, waga=waga, linia=linia, dzisiaj_iso=dzisiaj_iso)

    def potwierdz_palete(paleta_id):
        """Confirm paleta acceptance with warehouse manager/lider."""
        linia = resolve_request_linia()
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        table_mag = get_table_name('magazyn_palety', linia)
    
        role = str(session.get('rola', '')).strip()
        if role not in ['magazynier', 'lider', 'admin', 'masteradmin']:
            current_app.logger.warning(
                '[WAREHOUSE-AUTH] User %s with role=%s tried to confirm paleta %s - insufficient permissions',
                session.get('login'),
                role,
                paleta_id,
            )
            return jsonify({'success': False, 'message': 'Brak uprawnień do zatwierdzania palet'}), 403
    
        provided_netto = None
        provided_brutto = None
        deklarowana_waga = None
        weight_difference = None
        has_weight_difference = False
        check_only_request = False
        force_accept_request = False
        status_updated = False
        error_message = None
    
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
    
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and check_only_request:
                return jsonify(
                    {
                        'success': True,
                        'check_only': True,
                        'has_difference': has_weight_difference,
                        'difference': weight_difference,
                        'requires_confirmation': has_weight_difference,
                    }
                ), 200
    
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
                    f"SELECT plan_id, COALESCE(status,''), COALESCE(waga_potwierdzona, 0), nr_palety, nr_plomby FROM {table_pal} WHERE id=%s",
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
    
            user_login = session.get('login', 'System')
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
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': f'Nie udało się zatwierdzić palety: {error_message or "błąd zapisu statusu"}'}), 500
                return redirect(safe_return())
    
            if plan_id:
                netto_val = provided_netto if provided_netto is not None else stored_netto
    
                try:
                    cursor.execute(f"SELECT data_planu, produkt, data_produkcji FROM {table_plan} WHERE id=%s", (plan_id,))
                    row = cursor.fetchone()
                    if row and prev_status not in ('przyjeta', 'w_magazynie'):
                        cursor.execute(f"SELECT id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' LIMIT 1", (row[0], row[1]))
                        mp = cursor.fetchone()
                        mp_id = mp[0] if mp else None
    
                        nr_partii = request.form.get('nr_partii')
                        
                        # Check request.form, then fallback to plan's data_produkcji, then fallback to plan's date, then fallback to current date
                        data_produkcji = request.form.get('data_produkcji')
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
    
                        if row[1] == 'Czyszczenie':
                            import uuid, json
                            from datetime import datetime
                            dostawa_id = str(uuid.uuid4())
                            items = [{
                                "id": str(uuid.uuid4()),
                                "type": "surowiec",
                                "name": row[1],
                                "amount": netto_val,
                                "unit": "kg",
                                "confirmed": False
                            }]
                            try:
                                cursor.execute("""
                                    INSERT INTO magazyn_dostawy
                                        (id, order_ref, supplier, delivery_date, status, items,
                                         created_by, created_at, requires_lab, linia)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                """, (dostawa_id, f"Czyszczenie Zlecenie #{plan_id}", "PRODUKCJA", data_produkcji, "OCZEKUJE",
                                      json.dumps(items), session.get('login'), datetime.now(), 0, linia))
                                mag_id = None
                                
                                # Update status to przeklasyfikowana
                                cursor.execute(f"UPDATE {table_pal} SET status='przeklasyfikowana' WHERE id=%s", (paleta_id,))
                                
                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, 'surowiec', 'PRZEKLASYFIKOWANIE', %s, %s, %s)",
                                    (paleta_id, linia, lokalizacja, f"Przeklasyfikowano na surowiec: {row[1]}, Oczekuje w dostawach", session.get('login'))
                                )
                            except Exception as e:
                                current_app.logger.error('Database error for Czyszczenie dostawa: %s', e)
                        else:
                            try:
                                cursor.execute(
                                    f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                    (paleta_id, mp_id, row[0], row[1], netto_val, provided_brutto if provided_brutto is not None else 0, tara, session.get('login'), nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby),
                                )
                                mag_id = cursor.lastrowid
                                
                                # Log to palety_historia
                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'PRZYJECIE', %s, %s, %s)",
                                    (paleta_id, linia, lokalizacja, f"Przyjęcie palety: {row[1]}, partia: {nr_partii}", session.get('login'))
                                )
                            except mysql.connector.Error as e:
                                current_app.logger.debug('Database error for paleta %s in %s: %s', paleta_id, table_mag, e)
    
                        if cursor.rowcount > 0:
                            current_app.logger.info(
                                'Potwierdzono paletę ID=%s: waga_netto=%s kg, produkt=%s, użytkownik=%s, lokalizacja=%s',
                                paleta_id,
                                netto_val,
                                row[1] if len(row) > 1 else '—',
                                session.get('login'),
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
                        
                        # --- Automatyczny wydruk raportu na drukarce biurowej, jeśli to ostatnia paleta w zakończonym zleceniu ---
                        printed_msg = None
                        try:
                            cursor.execute(f"SELECT status FROM {table_plan} WHERE id=%s", (plan_id,))
                            plan_status_row = cursor.fetchone()
                            if plan_status_row and str(plan_status_row[0]).strip().lower() in ('zakończone', 'zakończony', 'zakonczone'):
                                cursor.execute(f"SELECT COUNT(id) FROM {table_pal} WHERE plan_id=%s", (plan_id,))
                                total_pallets = cursor.fetchone()[0] or 0
                                
                                cursor.execute(f"SELECT COUNT(id) FROM {table_pal} WHERE plan_id=%s AND status IN ('przyjeta', 'w_magazynie')", (plan_id,))
                                accepted_pallets = cursor.fetchone()[0] or 0
                                
                                if total_pallets > 0 and total_pallets == accepted_pallets:
                                    current_app.logger.info("Magazynier przyjął ostatnią paletę zlecenia %s. Wyzwalanie wydruku biurowego.", plan_id)
                                    from app.services.office_print_service import trigger_office_print
                                    trigger_office_print(plan_id)
                                    printed_msg = "Zlecenie zamknięte - przyjęto ostatnią paletę. Raport został wysłany na drukarkę."
                                    flash(printed_msg, 'success')
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
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                response_data = {'success': True, 'paleta_id': paleta_id}
                if 'printed_msg' in locals() and printed_msg:
                    response_data['message'] = printed_msg
                if has_weight_difference and not force_accept_request:
                    response_data['has_difference'] = True
                    response_data['difference'] = weight_difference
                return jsonify(response_data), 200
        except Exception:
            pass
        return redirect(safe_return())

    def usun_palete(id):
        """Delete paleta from buffer."""
        linia = str(resolve_request_linia()).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
    
            cursor.execute(f"SELECT plan_id FROM {table_pal} WHERE id=%s", (id,))
            res = cursor.fetchone()
    
            if not res:
                msg = f'Paleta ID={id} nie istnieje'
                current_app.logger.warning('[WAREHOUSE-DELETE] %s', msg)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': msg}), 404
                flash(msg, 'warning')
                return redirect(safe_return())
    
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
                    (id, linia, f"Usunięto paletę z workowania: {nr_palety_val or 'ID='+str(id)}, waga: {waga_val} kg, status: {status_val}", session.get('login'))
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for deleted paleta %s: %s', id, hist_err)
            
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s AND status NOT IN ('przyjeta', 'w_magazynie')) WHERE id = %s",
                (plan_id, plan_id),
            )
            conn.commit()
    
            current_app.logger.info('Usunięto paletę ID=%s, plan_id=%s, użytkownik=%s', id, plan_id, session.get('login'))
            audit_log('Usunął paletę', f'ID={id}, plan_id={plan_id}')
            msg = 'Paleta usunięta'
    
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': msg}), 200
    
            flash(msg, 'success')
        except Exception as error:
            current_app.logger.error('[WAREHOUSE-DELETE] Error deleting paleta %s: %s', id, error, exc_info=True)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 500
            flash(f'Błąd przy usuwaniu palety: {str(error)}', 'danger')
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    
        return redirect(safe_return())

    def edytuj_palete(paleta_id):
        """Edit paleta weight (netto)."""
        linia = str(resolve_request_linia()).upper()
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
    
            try:
                waga = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
            except Exception:
                waga = 0
    
            result = update_paleta_workowanie(cursor, paleta_id, waga, linia=linia)
            if not result.get('found'):
                msg = f'Paleta ID={paleta_id} nie istnieje'
                current_app.logger.warning('[WAREHOUSE-EDIT] %s', msg)
                flash(msg, 'warning')
                return redirect(safe_return())
            
            # Log to palety_historia - edycja wagi
            try:
                old_waga = result.get('old_waga', 0)
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'EDYCJA_WAGI', %s, %s)",
                    (paleta_id, linia, f"Zmieniono wagę: {old_waga} kg → {waga} kg", session.get('login'))
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for edited paleta %s: %s', paleta_id, hist_err)
    
            conn.commit()
            current_app.logger.info('Edytowano paletę ID=%s, waga=%s kg, użytkownik=%s', paleta_id, waga, session.get('login'))
            audit_log('Edytował paletę', f'ID={paleta_id}, waga={waga} kg')
            flash(f'Paleta zaktualizowana (waga={waga}kg)', 'success')
        except Exception as error:
            current_app.logger.error('[WAREHOUSE-EDIT] Failed to edit paleta %s: %s', paleta_id, error, exc_info=True)
            flash(f'Błąd przy edytowaniu palety: {str(error)}', 'danger')
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    
        return redirect(safe_return())

    def edytuj_palete_ajax():
        """AJAX: Edytuj wagę palety w magazyn_palety (tylko potwierdzone w magazynie)."""
        data = request.get_json(force=True) or {}
        linia = str(resolve_payload_linia(data)).upper()
        paleta_id = data.get('id')
        nowa_waga = data.get('waga')
        try:
            paleta_id = int(paleta_id)
            nowa_waga = int(float(str(nowa_waga).replace(',', '.')))
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowe dane'}), 400
    
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
    
            result = update_paleta_magazyn(cursor, paleta_id, nowa_waga, linia=linia)
            if not result.get('found'):
                msg = f'Paleta ID={paleta_id} nie istnieje w magazynie lub nie została potwierdzona'
                current_app.logger.warning('[WAREHOUSE-AJAX-EDIT] %s', msg)
                return jsonify({'success': False, 'message': msg}), 404
    
            conn.commit()
            plan_id = result.get('plan_id')
            current_app.logger.info('Edytowano paletę (AJAX) ID=%s, waga=%s kg, użytkownik=%s', paleta_id, nowa_waga, session.get('login'))
            audit_log('Edytował paletę (magazyn)', f'ID={paleta_id}, waga={nowa_waga} kg, plan_id={plan_id}')
            return jsonify({'success': True, 'message': f'Waga zaktualizowana ({nowa_waga}kg)'})
        except Exception as error:
            current_app.logger.exception('[WAREHOUSE-AJAX-EDIT] Failed to edit paleta %s: %s', paleta_id, error)
            return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def usun_palete_ajax():
        """AJAX: Usuń paletę tylko z magazyn_palety (potwierdzone w magazynie)."""
        data = request.get_json(force=True) or {}
        linia = str(resolve_payload_linia(data)).upper()
        paleta_id = data.get('id')
        try:
            paleta_id = int(paleta_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowe id'}), 400
    
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
    
            table_mag = get_table_name('magazyn_palety', linia)
            table_plan = get_table_name('plan_produkcji', linia)
            table_pal = get_table_name('palety_workowanie', linia)
    
            cursor.execute(f"SELECT plan_id, paleta_workowanie_id FROM {table_mag} WHERE id=%s", (paleta_id,))
            row = cursor.fetchone()
    
            if not row:
                msg = f'Paleta ID={paleta_id} nie istnieje w magazynie lub nie została potwierdzona'
                current_app.logger.warning('[WAREHOUSE-AJAX-DELETE] %s', msg)
                return jsonify({'success': False, 'message': msg}), 404
    
            plan_id = row[0]
            paleta_workowanie_id = row[1] if len(row) > 1 else None
            
            # Get paleta details for history before deletion
            cursor.execute(f"SELECT nr_palety, produkt, waga_netto, lokalizacja FROM {table_mag} WHERE id=%s", (paleta_id,))
            mag_data = cursor.fetchone()
            nr_pal = mag_data[0] if mag_data else None
            produkt = mag_data[1] if mag_data and len(mag_data) > 1 else ''
            waga = mag_data[2] if mag_data and len(mag_data) > 2 else 0
            lokalizacja = mag_data[3] if mag_data and len(mag_data) > 3 else ''
            
            cursor.execute(f"DELETE FROM {table_mag} WHERE id=%s", (paleta_id,))
            
            # Log to palety_historia - usunięcie z magazynu
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'USUNIECIE_Z_MAGAZYNU', %s, %s, %s)",
                    (paleta_id, linia, lokalizacja, f"Usunięto z magazynu: {nr_pal or 'ID='+str(paleta_id)}, {produkt}, {waga} kg", session.get('login'))
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for deleted paleta from magazyn %s: %s', paleta_id, hist_err)
            try:
                if paleta_workowanie_id:
                    cursor.execute(
                        f"UPDATE {table_pal} SET status=%s, data_potwierdzenia=NULL, czas_potwierdzenia_s=NULL, czas_rzeczywistego_potwierdzenia=NULL, waga_potwierdzona=NULL WHERE id=%s",
                        ('zamknieta', paleta_workowanie_id),
                    )
            except Exception:
                try:
                    current_app.logger.exception('Failed to update palety_workowanie after magazyn delete for paleta_workowanie_id=%s', paleta_workowanie_id)
                except Exception:
                    pass
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto), 0) FROM {table_mag} WHERE plan_id = %s) WHERE id = %s",
                (plan_id, plan_id),
            )
    
            conn.commit()
            current_app.logger.info('Usunięto paletę z magazynu (AJAX) ID=%s, plan_id=%s, użytkownik=%s', paleta_id, plan_id, session.get('login'))
            audit_log('Usunął paletę z magazynu', f'ID={paleta_id}, plan_id={plan_id}')
            return jsonify({'success': True, 'message': 'Paleta usunięta z magazynu'})
        except Exception as error:
            current_app.logger.exception('[WAREHOUSE-AJAX-DELETE] Failed to delete paleta %s: %s', paleta_id, error)
            return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

