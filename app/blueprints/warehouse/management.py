from datetime import date, datetime
import os

import mysql.connector
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required, masteradmin_required
from app.services.planning.status import PlanningStatusService
from app.utils.validation import require_field
from app.utils.pallet_id import generate_pallet_id
import threading


def register_warehouse_management_routes(
    warehouse_bp,
    *,
    resolve_request_linia,
    resolve_payload_linia,
    update_paleta_workowanie,
    update_paleta_magazyn,
    safe_return,
):
    def _select_preferred_printer(cursor):
        """Pick production printer first, then fallback to any active printer."""
        try:
            cursor.execute(
                """
                SELECT nazwa, ip
                FROM drukarki
                WHERE aktywna = 1
                ORDER BY
                    CASE
                        WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                        WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                        ELSE 2
                    END,
                    id ASC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return None, None
            return row[0], row[1]
        except Exception as printer_err:
            current_app.logger.warning('Nie udało się pobrać preferowanej drukarki: %s', printer_err)
            return None, None

    def _list_active_printers(cursor):
        """Return active printers in preferred order for automatic fallback attempts."""
        try:
            cursor.execute(
                """
                SELECT id, nazwa, ip
                FROM drukarki
                WHERE aktywna = 1
                ORDER BY
                    CASE
                        WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                        WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                        ELSE 2
                    END,
                    id ASC
                """
            )
            return cursor.fetchall() or []
        except Exception as printer_err:
            current_app.logger.warning('Nie udało się pobrać listy drukarek aktywnych: %s', printer_err)
            return []

    def _parse_data_produkcji_input(raw_value):
        """Validate optional production date input (YYYY-MM-DD)."""
        value = str(raw_value or '').strip()
        if not value:
            return None
        try:
            datetime.strptime(value, '%Y-%m-%d')
        except ValueError as error:
            raise ValueError('Nieprawidlowy format daty produkcji (oczekiwano RRRR-MM-DD)') from error
        return value

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

    @warehouse_bp.route('/dodaj_palete/<int:plan_id>', methods=['POST'])
    @login_required
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
            
            def _async_print_label(paleta_id_local, nr_palety_local, app):
                with app.app_context():
                        try:
                            from app.utils.pallet_label import prepare_pallet_label_data
                            conn2 = get_db_connection()
                            cur2 = conn2.cursor()
                            label_data_local = prepare_pallet_label_data(cur2, paleta_id_local, linia)
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
                t = threading.Thread(target=_async_print_label, args=(paleta_id, nr_palety, app_obj), daemon=True)
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

    @warehouse_bp.route('/dodaj_palete_page/<int:plan_id>', methods=['GET'])
    @login_required
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

    @warehouse_bp.route('/api/workowanie/update_data_produkcji', methods=['POST'])
    @login_required
    def update_workowanie_data_produkcji():
        """Update production date for a Workowanie order (also allowed while in progress)."""
        data = request.get_json(silent=True) or {}
        plan_id_raw = data.get('plan_id')
        linia = str(resolve_payload_linia(data)).upper()

        try:
            plan_id = int(plan_id_raw)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidlowe id zlecenia'}), 400

        try:
            data_produkcji = _parse_data_produkcji_input(data.get('data_produkcji'))
        except ValueError as error:
            return jsonify({'success': False, 'message': str(error)}), 400

        if not data_produkcji:
            return jsonify({'success': False, 'message': 'Brak daty produkcji'}), 400

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            table_plan = get_table_name('plan_produkcji', linia)

            cursor.execute(f"SELECT sekcja, status FROM {table_plan} WHERE id=%s", (plan_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia'}), 404

            sekcja = str(row[0] or '')
            if sekcja.lower() != 'workowanie':
                return jsonify({'success': False, 'message': 'Zmiana daty jest dostepna tylko dla zlecen Workowanie'}), 400

            cursor.execute(f"UPDATE {table_plan} SET data_produkcji=%s WHERE id=%s", (data_produkcji, plan_id))
            conn.commit()

            current_app.logger.info(
                'Zmieniono data_produkcji=%s dla zlecenia Workowanie id=%s (linia=%s, user=%s)',
                data_produkcji,
                plan_id,
                linia,
                session.get('login'),
            )
            audit_log('Zmiana daty produkcji (Workowanie)', f'plan_id={plan_id}, data_produkcji={data_produkcji}, linia={linia}')

            return jsonify({
                'success': True,
                'message': f'Ustawiono date produkcji: {data_produkcji}',
                'data_produkcji': data_produkcji,
            })
        except Exception as error:
            current_app.logger.exception('Failed to update data_produkcji for Workowanie plan %s: %s', plan_id, error)
            return jsonify({'success': False, 'message': f'Blad: {error}'}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @warehouse_bp.route('/edytuj_palete_page/<int:paleta_id>', methods=['GET'])
    @login_required
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

    @warehouse_bp.route('/confirm_delete_palete_page/<int:paleta_id>', methods=['GET'])
    @roles_required('lider', 'admin')
    def confirm_delete_palete_page(paleta_id):
        """Render delete confirmation for paleta."""
        linia = resolve_request_linia()
        source = request.args.get('source', '')
        return render_template('warehouse/popups/delete_pallet_confirm.html', paleta_id=paleta_id, linia=linia, source=source)

    @warehouse_bp.route('/confirm_delete_szarze_page/<int:szarza_id>', methods=['GET'], endpoint='confirm_delete_szarze_page')
    @warehouse_bp.route('/confirm_delete_zasyp_page/<int:szarza_id>', methods=['GET'], endpoint='confirm_delete_zasyp_page')
    @roles_required('masteradmin', 'admin', 'lider')
    def confirm_delete_szarze_page(szarza_id):
        """Render delete confirmation for zasyp (legacy route name)."""
        linia = resolve_request_linia()
        sekcja = request.args.get('sekcja') or 'Zasyp'
        data_value = request.args.get('data') or request.args.get('data_planu') or str(date.today())
        return render_template(
            'warehouse/popups/delete_zasyp_confirm.html',
            szarza_id=szarza_id,
            zasyp_id=szarza_id,
            linia=linia,
            sekcja=sekcja,
            data_planu=data_value,
        )

    @warehouse_bp.route('/edytuj_szarze_page/<int:szarza_id>', methods=['GET'], endpoint='edytuj_szarze_page')
    @warehouse_bp.route('/edytuj_zasyp_page/<int:szarza_id>', methods=['GET'], endpoint='edytuj_zasyp_page')
    @login_required
    def edytuj_szarze_page(szarza_id):
        """Render form for editing zasyp notes (uwagi)."""
        linia = str(resolve_request_linia()).upper()
        table_zasypy = get_table_name('szarze', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        uwagi = ''
        try:
            cursor.execute(f"SELECT uwagi FROM {table_zasypy} WHERE id=%s", (szarza_id,))
            row = cursor.fetchone()
            if row:
                uwagi = row[0] or ''
        except Exception as error:
            current_app.logger.error('Failed to load zasyp %s for edit page: %s', szarza_id, error, exc_info=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        data_value = request.args.get('data') or str(date.today())
        sekcja = request.args.get('sekcja', 'Zasyp')
        return render_template('warehouse/popups/edit_zasyp.html', szarza_id=szarza_id, zasyp_id=szarza_id, uwagi=uwagi, linia=linia, data=data_value, sekcja=sekcja)

    @warehouse_bp.route('/edytuj_szarze/<int:szarza_id>', methods=['POST'], endpoint='edytuj_szarze')
    @warehouse_bp.route('/edytuj_zasyp/<int:szarza_id>', methods=['POST'], endpoint='edytuj_zasyp')
    @login_required
    def edytuj_szarze(szarza_id):
        """Save zasyp notes (uwagi) to DB (legacy route name)."""
        new_uwagi = request.form.get('uwagi', '')
        linia = str(resolve_request_linia()).upper()
        table_zasypy = get_table_name('szarze', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"UPDATE {table_zasypy} SET uwagi=%s WHERE id=%s", (new_uwagi, szarza_id))
            conn.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': 'Zapisano notatkę', 'szarza_id': szarza_id, 'zasyp_id': szarza_id}), 200
            flash('Zapisano notatkę do zasypu', 'success')
        except Exception as error:
            current_app.logger.error('Failed to save uwagi for zasyp %s: %s', szarza_id, error, exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Błąd zapisu notatki'}), 500
            flash('Błąd zapisu notatki', 'danger')
        finally:
            try:
                conn.close()
            except Exception:
                pass

        return redirect(safe_return())

    @warehouse_bp.route('/potwierdz_palete_page/<int:paleta_id>', methods=['GET'])
    @login_required
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

    @warehouse_bp.route('/potwierdz_palete/<int:paleta_id>', methods=['POST'])
    @login_required
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

    @warehouse_bp.route('/wazenie_magazyn/<int:paleta_id>', methods=['POST'])
    @login_required
    def wazenie_magazyn(paleta_id):
        """Weigh paleta in warehouse and update weight."""
        linia = str(resolve_request_linia()).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        table_mag = get_table_name('magazyn_palety', linia)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            brutto = int(float(request.form.get('waga_brutto', '0').replace(',', '.')))
        except Exception:
            brutto = 0

        cursor.execute(f"SELECT tara, plan_id, nr_palety, nr_plomby FROM {table_pal} WHERE id=%s", (paleta_id,))
        res = cursor.fetchone()
        if res:
            tara, plan_id, nr_palety, nr_plomby = res
            netto = brutto - int(tara)
            if netto < 0:
                netto = 0
            try:
                cursor.execute(f"UPDATE {table_pal} SET waga_brutto=%s WHERE id=%s", (brutto, paleta_id))
            except Exception as error:
                current_app.logger.error('Failed to store brutto for paleta %s: %s', paleta_id, error, exc_info=True)
            cursor.execute(f"SELECT data_planu, produkt FROM {table_plan} WHERE id=%s", (plan_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute(f"SELECT id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' LIMIT 1", (row[0], row[1]))
                mp = cursor.fetchone()
                mp_id = mp[0] if mp else None
                cursor.execute(f"SELECT id FROM {table_mag} WHERE paleta_workowanie_id=%s", (paleta_id,))
                exists = cursor.fetchone()
                if not exists:
                    try:
                        cursor.execute(
                            f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_palety, nr_plomby) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (paleta_id, mp_id, row[0], row[1], netto, brutto, tara, session.get('login'), nr_palety, nr_plomby),
                        )
                    except mysql.connector.IntegrityError:
                        pass
                else:
                    cursor.execute(
                        f"UPDATE {table_mag} SET waga_netto=%s, waga_brutto=%s, tara=%s, data_potwierdzenia=NOW() WHERE paleta_workowanie_id=%s",
                        (netto, brutto, tara, paleta_id),
                    )
                cursor.execute(
                    f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto),0) FROM {table_mag} WHERE plan_id = {table_plan}.id) WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'",
                    (row[0], row[1]),
                )

        conn.commit()
        conn.close()
        return redirect(safe_return())

    @warehouse_bp.route('/usun_szarze/<int:id>', methods=['POST'], endpoint='usun_szarze')
    @warehouse_bp.route('/usun_zasyp/<int:id>', methods=['POST'], endpoint='usun_zasyp')
    @roles_required('masteradmin', 'admin', 'lider')
    def usun_szarze(id):
        """Delete zasyp from Zasyp section (legacy route name)."""
        linia = str(resolve_request_linia()).upper()
        table_zasypy = get_table_name('szarze', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        table_dosypki = get_table_name('dosypki', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT plan_id FROM {table_zasypy} WHERE id=%s", (id,))
            res = cursor.fetchone()
            if res:
                plan_id = res[0]
                cursor.execute(f"DELETE FROM {table_zasypy} WHERE id=%s", (id,))
                cursor.execute(
                    f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                    f"COALESCE((SELECT SUM(waga) FROM {table_zasypy} WHERE plan_id = %s), 0) + "
                    f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                    "WHERE id = %s",
                    (plan_id, plan_id, plan_id),
                )
                conn.commit()
        finally:
            conn.close()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Zasyp usunięty'}), 200

        return redirect(safe_return())

    @warehouse_bp.route('/usun_palete/<int:id>', methods=['POST'])
    @roles_required('lider', 'admin')
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

    @warehouse_bp.route('/edytuj_palete/<int:paleta_id>', methods=['POST'])
    @roles_required('magazynier', 'lider', 'admin')
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

    @warehouse_bp.route('/api/edytuj_palete_ajax', methods=['POST'])
    @roles_required('magazynier', 'produkcja', 'lider', 'admin')
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

    @warehouse_bp.route('/api/usun_palete_ajax', methods=['POST'])
    @roles_required('produkcja', 'lider', 'admin')
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

    @warehouse_bp.route('/drukuj_etykiete/<int:paleta_id>', methods=['GET'])
    @login_required
    def drukuj_etykiete(paleta_id):
        """Generates a 100x150 mm printable label for a palette in Magazyn."""
        linia = str(resolve_request_linia()).upper()
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        table_zasypy = get_table_name('szarze', linia)
        table_mag = get_table_name('magazyn_palety', linia)

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                f'''
                SELECT 
                    COALESCE(mp.plan_id, pw.plan_id) AS plan_id,
                    mp.waga_netto, 
                    COALESCE(p.produkt, pw_p.produkt, mp.produkt) AS produkt,
                    mp.paleta_workowanie_id,
                    pw.data_dodania
                FROM {table_mag} mp
                LEFT JOIN {table_plan} p ON mp.plan_id = p.id
                LEFT JOIN {table_pal} pw ON mp.paleta_workowanie_id = pw.id
                LEFT JOIN {table_plan} pw_p ON pw.plan_id = pw_p.id
                WHERE mp.id = %s
                ''',
                (paleta_id,),
            )
            row = cursor.fetchone()

            data_workowanie = None

            if row:
                plan_id, paleta_waga, produkt, workowanie_id, pw_data = row
                if pw_data:
                    data_workowanie = pw_data.strftime('%Y-%m-%d %H:%M:%S') if hasattr(pw_data, 'strftime') else str(pw_data)
                if plan_id:
                    if workowanie_id:
                        cursor.execute(
                            f'''
                            SELECT COALESCE(SUM(waga), 0) 
                            FROM {table_pal}
                            WHERE plan_id = %s AND id <= %s
                            ''',
                            (plan_id, workowanie_id),
                        )
                        cumulative_paleta_waga = cursor.fetchone()[0]
                    else:
                        cursor.execute(
                            f'''
                            SELECT COALESCE(SUM(waga_netto), 0) 
                            FROM {table_mag} 
                            WHERE plan_id = %s AND id <= %s
                            ''',
                            (plan_id, paleta_id),
                        )
                        cumulative_paleta_waga = cursor.fetchone()[0]
                else:
                    cumulative_paleta_waga = paleta_waga
            else:
                cursor.execute(
                    f'''
                    SELECT pw.plan_id, pw.waga, p.produkt, pw.data_dodania, pw.id
                    FROM {table_pal} pw
                    JOIN {table_plan} p ON pw.plan_id = p.id
                    WHERE pw.id = %s
                    ''',
                    (paleta_id,),
                )
                row = cursor.fetchone()
                if not row:
                    abort(404, description='Paleta nie znaleziona')

                work_plan_id, paleta_waga, produkt, pw_data, wk_id = row
                if pw_data:
                    data_workowanie = pw_data.strftime('%Y-%m-%d %H:%M:%S') if hasattr(pw_data, 'strftime') else str(pw_data)

                plan_id = work_plan_id
                workowanie_id = wk_id

                cursor.execute(
                    f'''
                    SELECT COALESCE(SUM(waga), 0) 
                    FROM {table_pal}
                    WHERE plan_id = %s AND id <= %s
                    ''',
                    (plan_id, paleta_id),
                )
                cumulative_paleta_waga = cursor.fetchone()[0]

            zasyp_nr = '?'
            zasyp_plan_id = None

            if plan_id:
                cursor.execute(f'SELECT zasyp_id FROM {table_plan} WHERE id = %s', (plan_id,))
                zasyp_check = cursor.fetchone()
                if zasyp_check and zasyp_check[0]:
                    zasyp_plan_id = zasyp_check[0]
                else:
                    zasyp_plan_id = plan_id

                cursor.execute(
                    f'''
                    SELECT id, waga, nr_szarzy
                    FROM {table_zasypy}
                    WHERE plan_id = %s 
                    ORDER BY data_dodania ASC, id ASC
                    ''',
                    (zasyp_plan_id,),
                )
                zasypy_rows = cursor.fetchall()

                cumulative_zasyp = 0
                for index, s_row in enumerate(zasypy_rows):
                    cumulative_zasyp += s_row[1]
                    zasyp_nr = s_row[2] if s_row[2] is not None else (index + 1)
                    if cumulative_zasyp >= cumulative_paleta_waga:
                        break

            # Obliczanie numeru Lp. palety w zleceniu
            nr_palety_lp = 'Brak'
            if plan_id:
                if workowanie_id:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, workowanie_id))
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_mag} WHERE plan_id = %s AND id <= %s", (plan_id, paleta_id))
                res_lp = cursor.fetchone()
                nr_palety_lp = res_lp[0] if res_lp else 1

            data_wydruku = datetime.now().strftime('%Y-%m-%d %H:%M')
            termin_przydatnosci = request.args.get('termin') or None

            return render_template(
                'warehouse/label.html',
                plan_id=zasyp_plan_id or 'Brak',
                produkt=produkt or 'Nieznany',
                nr_szarzy=zasyp_nr,
                waga=paleta_waga,
                nr_palety=nr_palety_lp,
                data_workowanie=data_workowanie or 'Ręczna paleta',
                data_wydruku=data_wydruku,
                termin_przydatnosci=termin_przydatnosci,
            )
        except HTTPException:
            raise
        except Exception as error:
            current_app.logger.exception('Error generating label for paleta %s: %s', paleta_id, error)
            abort(500, description='Wystąpił błąd przy generowaniu etykiety.')
        finally:
            cursor.close()
            conn.close()

    @warehouse_bp.route('/drukuj_etykiete_zpl/<int:paleta_id>', methods=['POST'])
    @login_required
    def drukuj_etykiete_zpl(paleta_id):
        """Send ZPL label via print bridge (2 copies)."""
        from app.services.print_server import get_printer
        linia = str(resolve_request_linia()).upper()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            payload = request.get_json(silent=True) or {}
            requested_printer_id = None
            requested_printer_ip = None
            requested_printer_name = None
            selected_printer_raw = None
            if isinstance(payload, dict):
                selected_printer_raw = payload.get('printer_id') or payload.get('printerId')
                requested_printer_ip = payload.get('printer_ip') or payload.get('printerIp')
                requested_printer_name = payload.get('printer_name') or payload.get('printerName')
            if selected_printer_raw in (None, ''):
                selected_printer_raw = request.form.get('printer_id') or request.args.get('printer_id')
            if requested_printer_ip in (None, ''):
                requested_printer_ip = request.form.get('printer_ip') or request.args.get('printer_ip')
            if requested_printer_name in (None, ''):
                requested_printer_name = request.form.get('printer_name') or request.args.get('printer_name')

            requested_printer_ip = str(requested_printer_ip or '').strip() or None
            requested_printer_name = str(requested_printer_name or '').strip() or None

            if selected_printer_raw not in (None, '', 'auto', 'AUTO', 'default', 'DEFAULT', '0', 0):
                try:
                    requested_printer_id = int(selected_printer_raw)
                except (TypeError, ValueError):
                    return jsonify({'success': False, 'message': 'Nieprawidlowy printer_id'}), 400

            raw_requested_date = None
            if isinstance(payload, dict):
                raw_requested_date = (
                    payload.get('data_produkcji')
                    or payload.get('dataProdukcji')
                    or payload.get('productionDate')
                )
            if not raw_requested_date:
                raw_requested_date = request.form.get('data_produkcji') or request.args.get('data_produkcji')

            current_app.logger.info(
                'Manual ZPL request: paleta_id=%s, linia=%s, content_type=%s, requested_data_produkcji=%s, payload_keys=%s',
                paleta_id,
                linia,
                request.content_type,
                raw_requested_date,
                sorted(list(payload.keys())) if isinstance(payload, dict) else [],
            )

            requested_data_produkcji = None
            try:
                requested_data_produkcji = _parse_data_produkcji_input(raw_requested_date)
            except ValueError as error:
                return jsonify({'success': False, 'message': str(error)}), 400

            if requested_data_produkcji:
                table_plan = get_table_name('plan_produkcji', linia)
                plan_id = _resolve_plan_id_for_paleta(
                    cursor,
                    paleta_id,
                    linia,
                    requested_plan_id=payload.get('plan_id') if isinstance(payload, dict) else None,
                )
                if not plan_id:
                    return jsonify({'success': False, 'message': 'Nie znaleziono powiazanego zlecenia dla palety'}), 404

                cursor.execute(f"SELECT sekcja FROM {table_plan} WHERE id=%s", (plan_id,))
                row_plan = cursor.fetchone()
                if not row_plan:
                    return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia dla palety'}), 404

                sekcja = str(row_plan[0] or '')
                if sekcja.lower() != 'workowanie':
                    return jsonify({'success': False, 'message': 'Zmiana daty jest dostepna tylko dla Workowania'}), 400

                cursor.execute(
                    f"UPDATE {table_plan} SET data_produkcji=%s WHERE id=%s",
                    (requested_data_produkcji, plan_id),
                )
                conn.commit()
                current_app.logger.info(
                    'Ręczny wydruk: ustawiono data_produkcji=%s dla plan_id=%s (paleta_id=%s, linia=%s, user=%s)',
                    requested_data_produkcji,
                    plan_id,
                    paleta_id,
                    linia,
                    session.get('login'),
                )

            from app.utils.pallet_label import prepare_pallet_label_data
            
            # Pobierz plan_id z requestu
            req_plan_id_raw = None
            if isinstance(payload, dict):
                req_plan_id_raw = payload.get('plan_id') or payload.get('planId')
            if req_plan_id_raw in (None, ''):
                req_plan_id_raw = request.form.get('plan_id') or request.args.get('plan_id')

            label_data = prepare_pallet_label_data(cursor, paleta_id, linia, requested_plan_id=req_plan_id_raw)
            
            if not label_data:
                return jsonify({'success': False, 'message': 'Nie znaleziono palety (ani w buforze, ani w magazynie)'}), 404

            # Always prefer the date explicitly chosen by the operator for this print job.
            # DB update still persists this value on the linked Workowanie order.
            if requested_data_produkcji:
                label_data['data'] = requested_data_produkcji
            
            printer = get_printer()
            override_name = None
            override_ip = None
            if requested_printer_id:
                cursor.execute(
                    "SELECT nazwa, ip FROM drukarki WHERE id = %s AND aktywna = 1 LIMIT 1",
                    (requested_printer_id,),
                )
                selected_printer = cursor.fetchone()
                if not selected_printer:
                    return jsonify({'success': False, 'message': 'Wybrana drukarka nie istnieje lub jest nieaktywna'}), 404
                override_name, override_ip = selected_printer[0], selected_printer[1]
            elif requested_printer_ip:
                if len(requested_printer_ip) > 120:
                    return jsonify({'success': False, 'message': 'Nieprawidlowy adres drukarki'}), 400
                override_ip = requested_printer_ip
                override_name = requested_printer_name or requested_printer_ip
            else:
                override_name, override_ip = _select_preferred_printer(cursor)

            candidate_printers = []
            seen_targets = set()

            def _append_candidate(name, ip):
                key = ((name or '').strip().lower(), (ip or '').strip().lower())
                if key in seen_targets:
                    return
                seen_targets.add(key)
                candidate_printers.append((name, ip))

            _append_candidate(override_name, override_ip)

            # Niezależnie od wyboru ręcznego warto próbować kolejne aktywne drukarki,
            # bo timeout pojedynczej drukarki jest częsty i chwilowy.
            for printer_row in _list_active_printers(cursor):
                cand_name = printer_row[1] if len(printer_row) > 1 else None
                cand_ip = printer_row[2] if len(printer_row) > 2 else None
                _append_candidate(cand_name, cand_ip)

            # Last resort: fallback to configured default in PrintServer.
            _append_candidate(None, None)

            local_bridge_fallback = None
            try:
                fallback_printers = []
                fallback_seen = set()
                for cand_name, cand_ip in candidate_printers:
                    final_name = cand_name or printer.printer_name
                    final_ip = cand_ip or printer.printer_ip
                    if not final_ip:
                        continue
                    fallback_key = (str(final_name).strip().lower(), str(final_ip).strip().lower())
                    if fallback_key in fallback_seen:
                        continue
                    fallback_seen.add(fallback_key)
                    fallback_printers.append({'name': final_name, 'ip': final_ip})

                if fallback_printers:
                    endpoint_entries = []
                    endpoint_seen = set()

                    def _append_bridge_endpoints(base_name, raw_base):
                        base_value = str(raw_base or '').strip().rstrip('/')
                        if not base_value:
                            return

                        lowered = base_value.lower()
                        if lowered.endswith('/drukuj-zpl'):
                            base_value = base_value[:-11]
                        elif lowered.endswith('/status'):
                            base_value = base_value[:-7]

                        if '://' not in base_value:
                            base_value = f'https://{base_value}'

                        variants = [base_value]
                        if base_value.lower().startswith('https://'):
                            variants.append('http://' + base_value[8:])
                        elif base_value.lower().startswith('http://'):
                            variants.append('https://' + base_value[7:])

                        for variant_index, variant_base in enumerate(variants, start=1):
                            normalized_variant = variant_base.strip().rstrip('/')
                            if not normalized_variant:
                                continue
                            dedupe_key = normalized_variant.lower()
                            if dedupe_key in endpoint_seen:
                                continue
                            endpoint_seen.add(dedupe_key)
                            suffix = '' if variant_index == 1 else '_alt'
                            endpoint_entries.append(
                                {
                                    'name': f'{base_name}{suffix}',
                                    'endpoint': normalized_variant + '/drukuj-zpl',
                                    'status_endpoint': normalized_variant + '/status',
                                }
                            )

                    shared_bridge_base = str(os.getenv('PRINTER_CLIENT_BRIDGE_URL', '') or '').strip().rstrip('/')
                    if not shared_bridge_base:
                        shared_bridge_base = str(os.getenv('PRINTER_BRIDGE_URL', '') or '').strip().rstrip('/')

                    _append_bridge_endpoints('shared_bridge', shared_bridge_base)
                    _append_bridge_endpoints('localhost_bridge', 'http://127.0.0.1:3001')

                    primary_endpoint = endpoint_entries[0] if endpoint_entries else None
                    local_bridge_fallback = {
                        'endpoint': (primary_endpoint or {}).get('endpoint'),
                        'status_endpoint': (primary_endpoint or {}).get('status_endpoint'),
                        'endpoints': endpoint_entries,
                        'copies': 2,
                        'zpl': printer.build_finished_product_label_zpl(label_data),
                        'printers': fallback_printers,
                        'reason': 'server_printer_timeout',
                    }
            except Exception as fallback_err:
                current_app.logger.warning('Nie udało się przygotować fallbacku lokalnego wydruku: %s', fallback_err)

            ok = False
            msg = 'Błąd druku'
            target_name = override_name or printer.printer_name
            target_ip = override_ip or printer.printer_ip

            for candidate_index, (cand_name, cand_ip) in enumerate(candidate_printers, start=1):
                candidate_target_name = cand_name or printer.printer_name
                candidate_target_ip = cand_ip or printer.printer_ip
                candidate_ok = True

                for copy_num in range(1, 3):
                    print_ok, print_msg = printer.print_finished_product_label(
                        label_data,
                        override_ip=cand_ip,
                        override_name=cand_name,
                    )
                    if not print_ok:
                        candidate_ok = False
                        msg = f"{print_msg} (kopia {copy_num}/2)"
                        current_app.logger.warning(
                            'Ręczny wydruk paleta_id=%s nieudany na kopii %s/2 (drukarka=%s, ip=%s, próba=%s): %s',
                            paleta_id,
                            copy_num,
                            candidate_target_name,
                            candidate_target_ip,
                            candidate_index,
                            print_msg,
                        )
                        break

                if candidate_ok:
                    ok = True
                    target_name = candidate_target_name
                    target_ip = candidate_target_ip
                    if candidate_index > 1:
                        msg = f"Wysłano do drukarki {target_name} ({target_ip}) po fallbacku"
                    else:
                        msg = f"Wysłano do drukarki {target_name} ({target_ip})"
                    break
            
            if ok:
                audit_log('Wydruk etykiety ZPL (ręczny)', f'paleta_id={paleta_id}, produkt={label_data["nazwa"]}, nr_palety={label_data["nrPalety"]}, kopie=2')

            response_payload = {
                'success': ok,
                'message': msg,
                'printer_name': target_name,
                'printer_ip': target_ip,
            }

            if not ok and local_bridge_fallback:
                response_payload['local_bridge_fallback'] = local_bridge_fallback

            if requested_printer_id:
                response_payload['printer_id'] = requested_printer_id
            if requested_data_produkcji:
                response_payload['data_produkcji'] = requested_data_produkcji
            elif label_data.get('data'):
                response_payload['data_produkcji'] = str(label_data.get('data'))

            return jsonify(response_payload)
        except Exception as e:
            current_app.logger.exception('ZPL Print failed: %s', e)
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            cursor.close()
            conn.close()