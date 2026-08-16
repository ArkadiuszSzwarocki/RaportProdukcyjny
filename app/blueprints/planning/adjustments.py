import json
from datetime import date
from flask import current_app, flash, jsonify, redirect, request, session, url_for

from app.core.audit import audit_log
from app.db import get_db_connection, get_plan_notification_context, get_table_name, log_plan_history
from app.decorators import hall_restricted, roles_required, masteradmin_required
from app.services.plan_movement_service import PlanMovementService
from app.services.planning.mutation import PlanningMutationService
from app.services.notification_service import notify_workers_about_plan_change
from app.services.planning.commands.edytuj_plan_command import EdytujPlanCommand

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
        linia = request.form.get('linia', 'PSD')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            success, message, changes, status_code = EdytujPlanCommand.execute(
                conn, cursor, linia, id, request.form.to_dict(), session
            )
            if success:
                conn.commit()
                notify_workers_about_plan_change(
                    plan_context=get_plan_notification_context(id, conn=conn, linia=linia),
                    action_label='zmienił',
                    author_name=session.get('imie_nazwisko') or session.get('login'),
                    created_by_user_id=session.get('user_id'),
                    linia=linia,
                )
                if 'KOLIZJA' in message or 'UWAGA' in message:
                    flash(message, 'danger')
                else:
                    flash('Zlecenie zaktualizowane', 'success')
                current_app.logger.info('Zlecenie ID=%s zaktualizowane przez %s', id, session.get('login'))
                audit_log('Edytował zlecenie', f'ID={id}')
            else:
                conn.rollback()
                flash(message, 'danger' if status_code == 500 else 'warning')
                
        except Exception as error:
            current_app.logger.error(f'Failed to edit plan {id}: {error}', exc_info=True)
            conn.rollback()
            flash('Błąd podczas zapisu zmian', 'danger')
        finally:
            conn.close()

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

        linia = data.get('linia', 'PSD')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            success, message, changes, status_code = EdytujPlanCommand.execute(
                conn, cursor, linia, pid, data, session
            )
            if success:
                conn.commit()
                if changes:
                    notify_workers_about_plan_change(
                        plan_context=get_plan_notification_context(pid, conn=conn, linia=linia),
                        action_label='zmienił',
                        author_name=session.get('imie_nazwisko') or session.get('login'),
                        created_by_user_id=session.get('user_id'),
                        linia=linia,
                    )
                    current_app.logger.info('Zlecenie ID=%s zaktualizowane (AJAX) przez %s: %s', pid, session.get('login'), changes)
                    audit_log('Edytował zlecenie (AJAX)', f'ID={pid}, zmiany: {list(changes.keys())}')
                
                return jsonify({'success': True, 'message': message, 'changes': changes})
            else:
                conn.rollback()
                return jsonify({'success': False, 'message': message}), status_code
                
        except Exception as error:
            current_app.logger.error(f'Error in edytuj_plan_ajax: {error}', exc_info=True)
            conn.rollback()
            return jsonify({'success': False, 'message': 'Błąd serwera'}), 500
        finally:
            conn.close()

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
            cursor.execute(f"SELECT id FROM {table_plan} WHERE id=%s", (plan_id_int,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': 'Plan nie znaleziony'}), 404

            cursor.execute(f"UPDATE {table_plan} SET uszkodzone_worki=%s WHERE id=%s", (uszk_val, plan_id_int))
            conn.commit()
            return jsonify({'success': True, 'message': 'Zaktualizowano liczę uszkodzonych worków'})

        except Exception as error:
            conn.rollback()
            current_app.logger.exception(f'[USZKODZONE-WORKI-ERROR] {str(error)}')
            return jsonify({'success': False, 'message': 'Błąd aktualizacji'}), 500
        finally:
            conn.close()

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
        if not plan_id or not to_date:
            return jsonify({'success': False, 'message': 'Brak parametrów'}), 400

        linia = data.get('linia') or request.args.get('linia') or 'PSD'

        try:
            pid = int(plan_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Błąd ID'}), 400

        success, message = PlanningMutationService.reschedule_plan(pid, to_date, linia=linia)
        if success:
            audit_log('Przesunął zlecenie', f'ID={pid}, nowa data={to_date}')
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

        return jsonify({'success': success, 'message': message}), 200 if success else 400

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

        return jsonify({'success': success, 'message': message}), 200 if success else 400

    @planning_bp.route('/usun_plan_ajax/<int:id>', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    @hall_restricted
    def api_usun_plan(id):
        """Soft delete plan via AJAX."""
        linia = request.args.get('linia') or request.form.get('linia') or request.get_json(silent=True, force=False) and request.get_json(silent=True).get('linia') or 'PSD'

        try:
            success, message = PlanningMutationService.delete_plan(id, linia=linia)

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
            return jsonify({'success': False, 'message': 'Błąd przy usuwaniu zlecenia.'}), 500