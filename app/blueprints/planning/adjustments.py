import json
from datetime import date

from flask import current_app, flash, jsonify, redirect, request, session, url_for

from app.core.audit import audit_log
from app.db import get_db_connection, get_plan_notification_context, get_table_name, log_plan_history
from app.decorators import hall_restricted, roles_required, masteradmin_required
from app.services.plan_movement_service import PlanMovementService
from app.services.planning.mutation import PlanningMutationService
from app.services.notification_service import notify_workers_about_plan_change


def register_planning_adjustment_routes(planning_bp, *, return_url_builder):
    @planning_bp.route('/przenies_zlecenie/<int:id>', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    @hall_restricted
    def przenies_zlecenie(id):
        """Move a plan to a different date."""
        nowa_data = request.form.get('nowa_data')
        linia = request.args.get('linia') or request.form.get('linia', 'PSD')
        if not nowa_data:
            flash('Nowa data jest wymagana.', 'warning')
            return redirect(return_url_builder())



        success, message = PlanningMutationService.reschedule_plan(id, nowa_data, linia=linia)
        flash(message, 'success' if success else 'warning')
        return redirect(return_url_builder())

    @planning_bp.route('/przesun_zlecenie/<int:id>/<kierunek>', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    @hall_restricted
    def przesun_zlecenie(id, kierunek):
        """Move a plan up or down in the sequence."""
        data = request.args.get('data', str(date.today()))
        linia = request.args.get('linia') or request.form.get('linia', 'PSD')
        success, message = PlanMovementService.shift_plan_order(id, kierunek, linia=linia)
        if not success:
            flash(message, 'warning')
        return redirect(url_for('planista.panel_planisty', data=data, linia=linia))

    @planning_bp.route('/edytuj_plan/<int:id>', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    @hall_restricted
    def edytuj_plan(id):
        """Save plan edits: product, tonnage, section, date."""
        produkt = request.form.get('produkt')
        tonaz = request.form.get('tonaz')
        sekcja = request.form.get('sekcja')
        data_planu = request.form.get('data_planu')
        linia = request.form.get('linia', 'PSD')
        try:
            tonaz_val = int(float(tonaz)) if tonaz is not None and tonaz != '' else None
        except Exception as error:
            current_app.logger.debug(f'Failed to parse tonaz: {error}')
            tonaz_val = None

        conn = None
        try:
            conn = get_db_connection()
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()

            cursor.execute(f"SELECT id, status, sekcja, updated_at, zasyp_id FROM {table_plan} WHERE id=%s", (id,))
            row = cursor.fetchone()
            if not row:
                flash('Nie znaleziono zlecenia', 'warning')
                return redirect(return_url_builder())
            current_zasyp_id = row[4]

            last_seen = request.form.get('last_updated')
            db_updated_at = str(row[3]) if row[3] else ''
            if last_seen and db_updated_at and last_seen != db_updated_at:
                current_app.logger.warning(
                    'PUŁAPKA DUPLIKATÓW: Wykryto próbę równoległej edycji zlecenia ID=%s przez %s. (Oczekiwano: %s, Aktualnie: %s)',
                    id,
                    session.get('login'),
                    last_seen,
                    db_updated_at,
                )
                audit_log('KOLIZJA EDYCJI', f'Użytkownik {session.get("login")} próbuje nadpisać zmiany w zleceniu {id}')
                flash(
                    'UWAGA: Wykryto, że inna osoba zmieniła to zlecenie w międzyczasie! Twoje zmiany mogą nadpisać czyjąś pracę. Odśwież stronę, aby zobaczyć aktualne dane.',
                    'danger',
                )

            current_role = session.get('rola', '')
            produkt_provided = produkt if produkt and produkt.strip() else None
            sekcja_provided = sekcja if sekcja and sekcja.strip() else None
            data_provided = data_planu if data_planu and str(data_planu).strip() else None
            is_tonaz_only = (
                tonaz_val is not None
                and produkt_provided is None
                and sekcja_provided is None
                and data_provided is None
            )

            if row[1] == 'zakonczone':
                flash('Edytowanie zakończonego zlecenia jest zakazane', 'warning')
                return redirect(return_url_builder())
            elif row[1] == 'w toku':
                if current_role in ['planista', 'lider']:
                    if not is_tonaz_only:
                        flash('Gdy zlecenie w toku, planista może zmieniać tylko kg', 'warning')
                        return redirect(return_url_builder())
                elif current_role == 'admin':
                    if not is_tonaz_only:
                        flash('Gdy zlecenie w toku, można zmieniać tylko kg', 'warning')
                        return redirect(return_url_builder())
                else:
                    flash('Nie można edytować zleceń w toku', 'warning')
                    return redirect(return_url_builder())

            current_sekcja = row[2]
            updates = []
            params = []
            if produkt is not None:
                updates.append('produkt=%s')
                params.append(produkt)
            if tonaz_val is not None:
                updates.append('tonaz=%s')
                params.append(tonaz_val)
            if sekcja:
                updates.append('sekcja=%s')
                params.append(sekcja)
                current_sekcja = sekcja
            if data_planu:
                cursor.execute(f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja=%s", (data_planu, current_sekcja))
                result = cursor.fetchone()
                next_order = (result[0] if result and result[0] else 0) + 1
                updates.append('data_planu=%s')
                params.append(data_planu)
                updates.append('kolejnosc=%s')
                params.append(next_order)

            if updates:
                sql = f"UPDATE {table_plan} SET {', '.join(updates)} WHERE id=%s"
                params.append(id)
                cursor.execute(sql, tuple(params))

                if tonaz_val is not None and row[2] == 'Workowanie' and current_zasyp_id:
                    try:
                        table_bufor = get_table_name('bufor', linia)
                        cursor.execute(
                            f"UPDATE {table_bufor} SET tonaz_rzeczywisty = %s WHERE zasyp_id = %s AND status IN ('aktywny', 'zamkniete')",
                            (tonaz_val, current_zasyp_id),
                        )
                        if cursor.rowcount:
                            current_app.logger.info(
                                f'[BUFOR-SYNC] Zaktualizowano bufor.tonaz_rzeczywisty={tonaz_val} dla zasyp_id={current_zasyp_id} (plan.id={id})'
                            )
                    except Exception as buffer_error:
                        current_app.logger.warning(f'[BUFOR-SYNC] Nie udało się zsync bufor dla plan {id}: {buffer_error}')

                conn.commit()
                notify_workers_about_plan_change(
                    plan_context=get_plan_notification_context(id, conn=conn, linia=linia),
                    action_label='zmienił',
                    author_name=session.get('imie_nazwisko') or session.get('login'),
                    created_by_user_id=session.get('user_id'),
                    linia=linia,
                )
                flash('Zlecenie zaktualizowane', 'success')
                current_app.logger.info('Zlecenie ID=%s zaktualizowane przez %s', id, session.get('login'))
                audit_log('Edytował zlecenie', f'ID={id}')

        except Exception as error:
            current_app.logger.error(f'Failed to edit plan {id}: {error}', exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
            flash('Błąd podczas zapisu zmian', 'danger')

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return redirect(return_url_builder())

    @planning_bp.route('/edytuj_plan_ajax', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    @hall_restricted
    def edytuj_plan_ajax():
        """Edit plan via AJAX."""
        try:
            data = request.get_json(force=True)
        except Exception:
            data = request.form.to_dict()

        plan_id = data.get('id')
        if not plan_id:
            return jsonify({'success': False, 'message': 'Brak id'}), 400

        try:
            pid = int(plan_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowe id'}), 400

        produkt = data.get('produkt')
        tonaz = data.get('tonaz')
        sekcja = data.get('sekcja')
        data_planu = data.get('data_planu')
        typ_produkcji = data.get('typ_produkcji')
        nazwa_zlecenia = data.get('nazwa_zlecenia')
        data_produkcji = data.get('data_produkcji')
        opakowanie_id = data.get('opakowanie_id')
        etykieta_id = data.get('etykieta_id')
        linia = data.get('linia', 'PSD')

        try:
            tonaz_val = int(float(tonaz)) if tonaz is not None and str(tonaz).strip() != '' else None
        except Exception:
            tonaz_val = None

        conn = None
        try:
            conn = get_db_connection()
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            
            if linia.upper() == 'AGRO':
                cursor.execute(
                    f"SELECT id, produkt, tonaz, sekcja, data_planu, status, COALESCE(typ_produkcji, ''), COALESCE(nazwa_zlecenia, ''), zasyp_id, COALESCE(typ_zlecenia, ''), data_produkcji, opakowanie_id, etykieta_id FROM {table_plan} WHERE id=%s",
                    (pid,),
                )
            else:
                cursor.execute(
                    f"SELECT id, produkt, tonaz, sekcja, data_planu, status, COALESCE(typ_produkcji, ''), COALESCE(nazwa_zlecenia, ''), zasyp_id, COALESCE(typ_zlecenia, ''), data_produkcji, NULL as opakowanie_id, NULL as etykieta_id FROM {table_plan} WHERE id=%s",
                    (pid,),
                )
                
            before = cursor.fetchone()
            if not before:
                return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia'}), 404

            current_role = session.get('rola', '')
            produkt_provided = produkt if produkt and (produkt.strip() if isinstance(produkt, str) else str(produkt).strip()) else None
            sekcja_provided = sekcja if sekcja and (sekcja.strip() if isinstance(sekcja, str) else str(sekcja).strip()) else None
            data_provided = data_planu if data_planu and str(data_planu).strip() else None
            is_tonaz_only = (
                tonaz is not None
                and str(tonaz).strip() != ''
                and produkt_provided is None
                and sekcja_provided is None
                and data_provided is None
            )

            if before[5] == 'zakonczone':
                return jsonify({'success': False, 'message': 'Edytowanie zakończonego zlecenia jest zakazane'}), 403

            if before[5] == 'w toku' and current_role in ['planista', 'admin', 'zarzad', 'lider']:
                if not is_tonaz_only:
                    return jsonify({'success': False, 'message': 'Gdy zlecenie w toku, możesz zmieniać tylko kg'}), 403
            elif before[5] == 'w toku':
                return jsonify({'success': False, 'message': 'Nie można edytować zleceń w toku'}), 403

            updates = []
            params = []
            changes = {}
            current_sekcja = before[3]

            if produkt is not None and produkt != before[1]:
                updates.append('produkt=%s')
                params.append(produkt)
                changes['produkt'] = {'before': before[1], 'after': produkt}
            if tonaz_val is not None and tonaz_val != (before[2] or 0):
                updates.append('tonaz=%s')
                params.append(tonaz_val)
                changes['tonaz'] = {'before': before[2], 'after': tonaz_val}
            if sekcja and sekcja != before[3]:
                updates.append('sekcja=%s')
                params.append(sekcja)
                changes['sekcja'] = {'before': before[3], 'after': sekcja}
                current_sekcja = sekcja
            if typ_produkcji is not None and typ_produkcji != (before[6] or ''):
                updates.append('typ_produkcji=%s')
                params.append(typ_produkcji)
                changes['typ_produkcji'] = {'before': before[6], 'after': typ_produkcji}
            if nazwa_zlecenia is not None and nazwa_zlecenia != (before[7] or ''):
                updates.append('nazwa_zlecenia=%s')
                params.append(nazwa_zlecenia)
                changes['nazwa_zlecenia'] = {'before': before[7], 'after': nazwa_zlecenia}
            if data_planu and data_planu != str(before[4]):
                cursor.execute(f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja=%s", (data_planu, current_sekcja))
                result = cursor.fetchone()
                next_order = (result[0] if result and result[0] else 0) + 1
                updates.append('data_planu=%s')
                params.append(data_planu)
                updates.append('kolejnosc=%s')
                params.append(next_order)
                changes['data_planu'] = {'before': str(before[4]), 'after': data_planu}

            if before[9] == 'carry_over_ghost' and before[5] == 'zakonczone' and tonaz_val is not None and tonaz_val > 0:
                updates.append('status=%s')
                params.append('zaplanowane')
                changes['status'] = {'before': 'zakonczone', 'after': 'zaplanowane'}

            if linia.upper() == 'AGRO':
                # Enforce that opakowanie_id and etykieta_id are present (not NULL/None/empty) for AGRO orders.
                if opakowanie_id is not None:
                    try:
                        opakowanie_id_int = int(opakowanie_id) if opakowanie_id not in (None, '', 'None') else None
                    except Exception:
                        opakowanie_id_int = None
                else:
                    opakowanie_id_int = before[11]

                if etykieta_id is not None:
                    try:
                        etykieta_id_int = int(etykieta_id) if etykieta_id not in (None, '', 'None') else None
                    except Exception:
                        etykieta_id_int = None
                else:
                    etykieta_id_int = before[12]

                if not opakowanie_id_int or not etykieta_id_int:
                    return jsonify({'success': False, 'message': 'Dla linii AGRO wyznaczony worek (opakowanie) oraz etykieta są obowiązkowe!'}), 400

                if opakowanie_id is not None and opakowanie_id_int != before[11]:
                    updates.append('opakowanie_id=%s')
                    params.append(opakowanie_id_int)
                    changes['opakowanie_id'] = {'before': before[11], 'after': opakowanie_id_int}

                if etykieta_id is not None and etykieta_id_int != before[12]:
                    updates.append('etykieta_id=%s')
                    params.append(etykieta_id_int)
                    changes['etykieta_id'] = {'before': before[12], 'after': etykieta_id_int}

            if data_produkcji is not None:
                data_prod_val = data_produkcji.strip() if data_produkcji and str(data_produkcji).strip() else None
                before_prod_date = before[10]
                if before_prod_date is not None and hasattr(before_prod_date, 'strftime'):
                    before_prod_date_str = before_prod_date.strftime('%Y-%m-%d')
                else:
                    before_prod_date_str = str(before_prod_date) if before_prod_date else None

                if data_prod_val != before_prod_date_str:
                    updates.append('data_produkcji=%s')
                    params.append(data_prod_val)
                    changes['data_produkcji'] = {'before': before_prod_date_str, 'after': data_prod_val}

            if updates:
                sql = f"UPDATE {table_plan} SET {', '.join(updates)} WHERE id=%s"
                params.append(pid)
                cursor.execute(sql, tuple(params))
                conn.commit()
                notify_workers_about_plan_change(
                    plan_context=get_plan_notification_context(pid, conn=conn, linia=linia),
                    action_label='zmienił',
                    author_name=session.get('imie_nazwisko') or session.get('login'),
                    created_by_user_id=session.get('user_id'),
                    linia=linia,
                )
                current_app.logger.info('Zlecenie ID=%s zaktualizowane (AJAX) przez %s: %s', pid, session.get('login'), changes)
                audit_log('Edytował zlecenie (AJAX)', f'ID={pid}, zmiany: {list(changes.keys())}')

                try:
                    if 'tonaz' in changes and (before[3] or '').lower() == 'workowanie' and before[8]:
                        table_bufor = get_table_name('bufor', linia)
                        cursor.execute(
                            f"UPDATE {table_bufor} SET tonaz_rzeczywisty = %s WHERE zasyp_id = %s AND status IN ('aktywny', 'zamkniete')",
                            (changes['tonaz']['after'], before[8]),
                        )
                        conn.commit()
                except Exception as error:
                    current_app.logger.error(f'Error syncing bufor.tonaz_rzeczywisty (AJAX): {error}', exc_info=True)

                try:
                    if 'produkt' in changes and (before[3] or '').lower() == 'zasyp':
                        table_bufor = get_table_name('bufor', linia)
                        cursor.execute(
                            f"UPDATE {table_bufor} SET produkt = %s WHERE zasyp_id = %s",
                            (changes['produkt']['after'], pid),
                        )
                        conn.commit()
                except Exception as error:
                    current_app.logger.error(f'Error syncing bufor.produkt (AJAX): {error}', exc_info=True)

                try:
                    if (before[3] or '').lower() == 'zasyp':
                        linked_updates = []
                        linked_params = []
                        for field in ['produkt', 'typ_produkcji', 'nazwa_zlecenia', 'data_planu', 'tonaz', 'opakowanie_id', 'etykieta_id']:
                            if field in changes:
                                if field == 'tonaz' and (before[9] == 'carry_over_ghost' or 'carry-over' in (before[7] or '').lower()):
                                    continue
                                linked_updates.append(f'{field}=%s')
                                linked_params.append(changes[field]['after'])

                        if linked_updates:
                            linked_sql = f"UPDATE {table_plan} SET {', '.join(linked_updates)} WHERE zasyp_id=%s AND status='zaplanowane' AND LOWER(sekcja)='workowanie'"
                            linked_params.append(pid)
                            cursor.execute(linked_sql, tuple(linked_params))
                            conn.commit()
                except Exception as error:
                    current_app.logger.error(f'Error propagating Zasyp changes to Workowanie: {error}', exc_info=True)

                try:
                    user_login = session.get('login') or session.get('imie_nazwisko')
                except Exception:
                    user_login = None

                try:
                    log_plan_history(pid, 'edit', json.dumps(changes, default=str, ensure_ascii=False), user_login)
                except Exception as error:
                    current_app.logger.error(f'Error logging plan history: {error}', exc_info=True)

                return jsonify({'success': True, 'message': 'Zaktualizowano', 'changes': changes})

            return jsonify({'success': True, 'message': 'Brak zmian'})

        except Exception as error:
            current_app.logger.error(f'Error in edytuj_plan_ajax: {error}', exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'success': False, 'message': 'Błąd serwera'}), 500

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @planning_bp.route('/update_uszkodzone_worki', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    def update_uszkodzone_worki():
        """Update uszkodzone_worki field via AJAX."""
        try:
            data = request.get_json(force=True)
        except Exception:
            data = request.form.to_dict()

        plan_id = data.get('id')
        uszkodzone_worki = data.get('uszkodzone_worki', 0)
        if not plan_id:
            return jsonify({'success': False, 'message': 'Brak id planu'}), 400

        try:
            plan_id_int = int(plan_id)
            uszk_val = int(uszkodzone_worki) if uszkodzone_worki else 0
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Nieprawidłowe wartości'}), 400

        linia = data.get('linia') or request.args.get('linia') or 'PSD'
        conn = get_db_connection()
        table_plan = get_table_name('plan_produkcji', linia)
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT id, uszkodzone_worki FROM {table_plan} WHERE id=%s", (plan_id_int,))
            result = cursor.fetchone()
            if not result:
                conn.close()
                return jsonify({'success': False, 'message': 'Plan nie znaleziony'}), 404

            cursor.execute(f"UPDATE {table_plan} SET uszkodzone_worki=%s WHERE id=%s", (uszk_val, plan_id_int))
            conn.commit()
            current_app.logger.debug(f'[USZKODZONE-WORKI] Plan {plan_id_int}: uszkodzone_worki={uszk_val}')
            conn.close()
            return jsonify({'success': True, 'message': 'Zaktualizowano liczę uszkodzonych worków'})

        except Exception as error:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            current_app.logger.exception(f'[USZKODZONE-WORKI-ERROR] {str(error)}')
            return jsonify({'success': False, 'message': 'Błąd aktualizacji'}), 500

    @planning_bp.route('/przenies_zlecenie_ajax', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    def przenies_zlecenie_ajax():
        """Move a plan to different date via AJAX."""
        try:
            data = request.get_json(force=True)
        except Exception:
            data = request.form.to_dict()

        plan_id = data.get('id')
        to_date = data.get('to_date') or data.get('data')
        current_app.logger.debug('przenies_zlecenie_ajax: id=%s, to_date=%s', plan_id, to_date)
        if not plan_id or not to_date:
            return jsonify({'success': False, 'message': 'Brak parametrów'}), 400

        linia = data.get('linia') or request.args.get('linia') or 'PSD'
        from_bufor = bool(data.get('from_bufor', False))

        try:
            pid = int(plan_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Błąd ID'}), 400

        success, message = PlanningMutationService.reschedule_plan(pid, to_date, linia=linia)
        if success:
            audit_log('Przesunął zlecenie', f'ID={pid}, nowa data={to_date}')
            current_app.logger.info('Przesunięto zlecenie ID=%s na %s przez %s', pid, to_date, session.get('login'))
            try:
                conn = get_db_connection()
                table_plan = get_table_name('plan_produkcji', linia)
                cursor = conn.cursor()
                cursor.execute(f"SELECT data_planu FROM {table_plan} WHERE id=%s", (pid,))
                old_row = cursor.fetchone()
                old_date = old_row[0] if old_row else '?'
                conn.close()
                user_login = session.get('login') or session.get('imie_nazwisko') or 'System'
                log_plan_history(pid, 'przeniesienie', f'Z {old_date} na {to_date}', user_login)
            except Exception as history_error:
                current_app.logger.warning('Błąd zapisu historii dla zlecenia %s: %s', pid, history_error)

        status_code = 200 if success else 400
        return jsonify({'success': success, 'message': message}), status_code

    @planning_bp.route('/przesun_zlecenie_ajax', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    def przesun_zlecenie_ajax():
        """Move a plan up/down in sequence via AJAX."""
        try:
            data = request.get_json(force=True)
        except Exception:
            data = request.form.to_dict()

        plan_id = data.get('id')
        kierunek = data.get('kierunek')
        if not plan_id or not kierunek:
            return jsonify({'success': False, 'message': 'Brak parametrów'}), 400

        try:
            pid = int(plan_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowe id'}), 400

        linia = data.get('linia') or request.args.get('linia') or 'PSD'
        success, message = PlanMovementService.shift_plan_order(pid, kierunek, linia=linia)
        if success:
            try:
                user_login = session.get('login') or session.get('imie_nazwisko')
                log_plan_history(pid, 'reorder', json.dumps({'direction': kierunek}, ensure_ascii=False), user_login)
            except Exception:
                pass

        status_code = 200 if success else 400
        return jsonify({'success': success, 'message': message}), status_code

    @planning_bp.route('/usun_plan_ajax/<int:id>', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    @hall_restricted
    def api_usun_plan(id):
        """Soft delete plan via AJAX."""
        linia = request.args.get('linia') or request.form.get('linia') or request.get_json(silent=True, force=False) and request.get_json(silent=True).get('linia') or 'PSD'
        current_app.logger.info('Usuwanie zlecenia ID=%s przez %s', id, session.get('login'))

        try:
            success, message = PlanningMutationService.delete_plan(id, linia=linia)
            current_app.logger.info('Wynik usunięcia zlecenia ID=%s: %s', id, message)

            if success:
                audit_log('Usunął zlecenie', f'ID={id}')
                try:
                    conn = get_db_connection()
                    table_plan = get_table_name('plan_produkcji', linia)
                    cursor = conn.cursor()
                    cursor.execute(f"SELECT produkt, data_planu, tonaz FROM {table_plan} WHERE id=%s", (id,))
                    result = cursor.fetchone()
                    conn.close()
                    if result:
                        details = {'produkt': result[0], 'data_planu': str(result[1]), 'tonaz': result[2]}
                        user_login = session.get('login') or session.get('imie_nazwisko')
                        log_plan_history(id, 'soft_delete', json.dumps(details, ensure_ascii=False), user_login)
                except Exception as history_error:
                    current_app.logger.warning('Błąd zapisu historii dla zlecenia %s: %s', id, history_error)

            return jsonify({'success': success, 'message': message}), 200 if success else 400

        except Exception:
            current_app.logger.exception('Błąd przy usuwaniu zlecenia %s', id)
            return jsonify({'success': False, 'message': 'Błąd przy usuwaniu zlecenia.'}), 500