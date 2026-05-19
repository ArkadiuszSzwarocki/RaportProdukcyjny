from datetime import date, datetime

import mysql.connector
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required, masteradmin_required
from app.services.planning_service import PlanningService
from app.utils.validation import require_field
from app.utils.pallet_id import generate_pallet_id


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

        cursor.execute(f"SELECT sekcja, data_planu, produkt FROM {table_plan} WHERE id=%s", (plan_id,))
        plan_row = cursor.fetchone()

        if not plan_row:
            conn.close()
            return ('Błąd: Plan nie znaleziony', 404)

        plan_sekcja, _plan_data, plan_produkt = plan_row

        if plan_sekcja != 'Workowanie':
            conn.close()
            try:
                current_app.logger.warning('REJECTED: Cannot add paleta to sekcja=%s', plan_sekcja)
            except Exception:
                pass
            return ('Błąd: Paletki można dodawać tylko do Workowania (bufora)', 400)

        if waga_input <= 0:
            conn.close()
            return ('Błąd: Waga musi być większa od 0', 400)

        now_ts = datetime.now()

        try:
            user_login = session.get('login', 'System')
            nr_palety = generate_pallet_id(linia)
            cursor.execute(
                f"INSERT INTO {table_pal} (plan_id, waga, tara, waga_brutto, data_dodania, status, dodal_login, nr_palety) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia', %s, %s)",
                (plan_id, waga_input, now_ts, user_login, nr_palety),
            )
            paleta_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None

            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id = %s",
                (waga_input, plan_id),
            )

            conn.commit()

            # --- AUTOMATYCZNY WYDRUK 2 ETYKIET W TLE ---
            try:
                from app.utils.pallet_label import prepare_pallet_label_data
                label_data = prepare_pallet_label_data(cursor, paleta_id, linia)
                if label_data:
                    # 4. Wysłanie 2 kopii do serwera druku
                    from app.services.print_server import get_printer
                    printer = get_printer()
                    override_name, override_ip = _select_preferred_printer(cursor)
                    for copy_num in range(1, 3):
                        ok, print_msg = printer.print_finished_product_label(
                            label_data,
                            override_ip=override_ip,
                            override_name=override_name,
                        )
                        current_app.logger.info(
                            'Automatyczny wydruk kopii %s/2 dla palety %s: sukces=%s, drukarka=%s, ip=%s, msg=%s',
                            copy_num,
                            nr_palety,
                            ok,
                            override_name or printer.printer_name,
                            override_ip or printer.printer_ip,
                            print_msg
                        )
                else:
                    current_app.logger.error('Nie udało się przygotować danych etykiety do automatycznego wydruku dla paleta_id=%s', paleta_id)
            except Exception as print_err:
                current_app.logger.error('Failed to trigger automatic print for paleta %s: %s', nr_palety, print_err)
            # ---------------------------------------------

            try:
                PlanningService.ensure_status_after_tonaz_update(plan_id, linia=linia)
            except Exception as error:
                try:
                    current_app.logger.warning('Warning during status validation: %s', error)
                except Exception:
                    pass

            try:
                current_app.logger.info(
                    'Dodano paletę: plan_id=%s, waga=%s kg, użytkownik=%s',
                    plan_id,
                    waga_input,
                    session.get('login'),
                )
                audit_log('Dodał paletę', f'plan_id={plan_id}, produkt={plan_produkt}, waga={waga_input} kg')
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
        linia = str(resolve_request_linia()).upper()
        table_plan = get_table_name('plan_produkcji', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        produkt = None
        sekcja = None
        typ = None
        try:
            cursor.execute(f"SELECT produkt, sekcja, typ_produkcji FROM {table_plan} WHERE id=%s", (plan_id,))
            row = cursor.fetchone()
            if row:
                produkt, sekcja, typ = row[0], row[1], row[2]
        except Exception as error:
            current_app.logger.error('Failed to fetch plan %s for dodaj_palete_page: %s', plan_id, error, exc_info=True)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        return render_template('warehouse/popups/add_pallet.html', plan_id=plan_id, produkt=produkt, sekcja=sekcja, typ=typ, linia=linia)

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
    @masteradmin_required
    def confirm_delete_palete_page(paleta_id):
        """Render delete confirmation for paleta."""
        linia = resolve_request_linia()
        return render_template('warehouse/popups/delete_pallet_confirm.html', paleta_id=paleta_id, linia=linia)

    @warehouse_bp.route('/confirm_delete_szarze_page/<int:szarza_id>', methods=['GET'], endpoint='confirm_delete_szarze_page')
    @warehouse_bp.route('/confirm_delete_zasyp_page/<int:szarza_id>', methods=['GET'], endpoint='confirm_delete_zasyp_page')
    @masteradmin_required
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
                cursor.execute(f"SELECT plan_id, COALESCE(status,''), COALESCE(waga_potwierdzona, 0), nr_palety FROM {table_pal} WHERE id=%s", (paleta_id,))
                prev_row = cursor.fetchone()
                if prev_row:
                    plan_id = prev_row[0]
                    prev_status = prev_row[1]
                    stored_netto = int(prev_row[2] or 0)
                    nr_palety = prev_row[3]
            except Exception as error:
                current_app.logger.warning('Failed to fetch plan_id/status/weights for paleta %s: %s', paleta_id, error)

            user_login = session.get('login', 'System')
            try:
                cursor.execute(
                    f"UPDATE {table_pal} SET status='przyjeta', "
                    "data_potwierdzenia = DATE_ADD(data_dodania, INTERVAL TIMESTAMPDIFF(SECOND, data_dodania, NOW()) SECOND), "
                    "czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW()), "
                    "czas_rzeczywistego_potwierdzenia = SEC_TO_TIME(TIMESTAMPDIFF(SECOND, data_dodania, NOW())), "
                    "potwierdzil_login = %s "
                    "WHERE id=%s",
                    (user_login, paleta_id),
                )
                conn.commit()
                status_updated = True
            except Exception as error:
                current_app.logger.warning('Complex update failed for paleta %s: %s, retrying simple update', paleta_id, error)
                try:
                    cursor.execute(f"UPDATE {table_pal} SET status='przyjeta', potwierdzil_login=%s WHERE id=%s", (user_login, paleta_id))
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
                    if row and prev_status != 'przyjeta':
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

                        try:
                            cursor.execute(
                                f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                (paleta_id, mp_id, row[0], row[1], netto_val, provided_brutto if provided_brutto is not None else 0, tara, session.get('login'), nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety),
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
                except Exception as error:
                    current_app.logger.error('Failed to update Magazyn aggregates for paleta %s: %s', paleta_id, error, exc_info=True)
                    try:
                        conn.rollback()
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

        cursor.execute(f"SELECT tara, plan_id, nr_palety FROM {table_pal} WHERE id=%s", (paleta_id,))
        res = cursor.fetchone()
        if res:
            tara, plan_id, nr_palety = res
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
                            f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_palety) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (paleta_id, mp_id, row[0], row[1], netto, brutto, tara, session.get('login'), nr_palety),
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
    @masteradmin_required
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
    @masteradmin_required
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
            cursor.execute(f"DELETE FROM {table_pal} WHERE id=%s", (id,))
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s",
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
    @masteradmin_required
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
            cursor.execute(f"DELETE FROM {table_mag} WHERE id=%s", (paleta_id,))
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
            from app.utils.pallet_label import prepare_pallet_label_data
            label_data = prepare_pallet_label_data(cursor, paleta_id, linia)
            
            if not label_data:
                return jsonify({'success': False, 'message': 'Nie znaleziono palety (ani w buforze, ani w magazynie)'}), 404
            
            printer = get_printer()
            override_name, override_ip = _select_preferred_printer(cursor)
            ok = True
            msg = "Wysłano do drukarki"
            # Drukujemy 2 kopie etykiety wyrobu gotowego
            for copy_num in range(1, 3):
                print_ok, print_msg = printer.print_finished_product_label(
                    label_data,
                    override_ip=override_ip,
                    override_name=override_name,
                )
                if not print_ok:
                    ok = False
                    msg = print_msg
            
            if ok:
                audit_log('Wydruk etykiety ZPL (ręczny)', f'paleta_id={paleta_id}, produkt={label_data["nazwa"]}, nr_palety={label_data["nrPalety"]}, kopie=2')
            
            return jsonify({'success': ok, 'message': msg})
        except Exception as e:
            current_app.logger.exception('ZPL Print failed: %s', e)
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            cursor.close()
            conn.close()