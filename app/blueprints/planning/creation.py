import logging
from datetime import date
from flask import current_app, flash, jsonify, redirect, request, session, url_for

from app.db import get_db_connection
from app.decorators import hall_restricted, roles_required
from app.services.notification_service import notify_workers_about_plan_change
from app.services.planning.mutation import PlanningMutationService
from app.services.planning.commands.dodaj_szarze_command import DodajSzarzeCommand
from app.services.planning.commands.dodaj_plan_command import DodajPlanCommand
from app.services.planning.commands.dodaj_plany_batch_command import DodajPlanyBatchCommand

def register_planning_creation_routes(planning_bp, *, return_url_builder):
    
    @planning_bp.route('/dodaj_plan_zaawansowany', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    def dodaj_plan_zaawansowany():
        """Add plan with advanced options."""
        data_planu = request.form.get('data_planu')
        produkt = request.form.get('produkt')
        sekcja = (request.form.get('sekcja') or '').strip()
        sekcja = (sekcja[0].upper() + sekcja[1:].lower()) if sekcja else ''
        typ = request.form.get('typ_produkcji', 'worki_zgrzewane_25')
        wymaga_oplaty = bool(request.form.get('wymaga_oplaty'))
        linia = request.form.get('linia', 'PSD')
        rodzaj_palety = request.form.get('rodzaj_palety', 'krajowa')

        try:
            tonaz = int(float(request.form.get('tonaz', 0)))
        except Exception as error:
            current_app.logger.debug(f'Failed to parse tonaz in dodaj_plan_zaawansowany: {error}')
            tonaz = 0

        success, message, plan_id = PlanningMutationService.create_plan(
            data_planu, produkt, tonaz, sekcja, typ, status='zaplanowane', wymaga_oplaty=wymaga_oplaty, linia=linia, rodzaj_palety=rodzaj_palety,
        )

        if success and plan_id:
            notify_workers_about_plan_change(
                plan_context={'id': plan_id, 'produkt': produkt, 'sekcja': sekcja, 'data_planu': data_planu},
                action_label='dodał',
                author_name=session.get('imie_nazwisko') or session.get('login'),
                created_by_user_id=session.get('user_id'),
                linia=linia,
            )

        if not success:
            flash(message, 'modal_error')
            current_app.logger.warning(f'Failed to create plan: {message}')

        return redirect(url_for('planista.panel_planisty', data=data_planu))

    @planning_bp.route('/dodaj_plan', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'operator', 'pracownik', 'lider', 'stepnpio')
    @hall_restricted
    def dodaj_plan():
        """Add a plan or production entry."""
        data_planu = request.form.get('data_planu') or request.form.get('data') or str(date.today())
        produkt = request.form.get('produkt', '').strip()
        sekcja = (request.form.get('sekcja') or request.args.get('sekcja') or 'Nieprzydzielony').strip()
        sekcja = sekcja[0].upper() + sekcja[1:].lower() if sekcja else 'Nieprzydzielony'
        typ = request.form.get('typ_produkcji', 'worki_zgrzewane_25')
        typ_opakowania = request.form.get('typ_opakowania', '').strip() or 'worki'
        linia = request.form.get('linia', 'PSD')
        rodzaj_palety = request.form.get('rodzaj_palety', 'krajowa')
        auto_szarza_mode = str(request.form.get('auto_szarza_mode') or 'manual').strip().lower()
        rodzaj_palety = request.form.get('rodzaj_palety', 'krajowa')

        try:
            tonaz = int(float(request.form.get('tonaz', 0)))
        except Exception:
            tonaz = 0

        try:
            plan_id_str = request.form.get('plan_id', '').strip()
            plan_id_provided = int(plan_id_str) if plan_id_str else 0
        except Exception:
            plan_id_provided = 0

        role = (session.get('rola') or '').lower().strip()
        is_admin_role = role in ['admin', 'planista', 'zarzad', 'masteradmin', 'master admin', 'master_admin']
        is_ops_role = role in ['operator', 'pracownik', 'lider', 'stepnpio']
        
        if not is_admin_role and not is_ops_role:
            flash('Brak uprawnień do dodawania planów lub zasypów.', 'warning')
            return redirect(return_url_builder())

        if is_ops_role and not (sekcja == 'Zasyp' and plan_id_provided > 0):
            flash('Brak uprawnień do dodawania zasypów w tym widoku.', 'warning')
            return redirect(return_url_builder())

        if not produkt:
            return redirect(return_url_builder())

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if tonaz > 0:
                if sekcja == 'Zasyp':
                    nr_szarzy_str = request.form.get('nr_szarzy') or request.form.get('nr_zasypu')
                    try:
                        nr_szarzy = int(nr_szarzy_str) if nr_szarzy_str else None
                    except ValueError:
                        nr_szarzy = None

                    ui_trigger = (request.form.get('ui_trigger') or '').strip() or 'button:dodaj_szarze_popup'
                    
                    success, message = DodajSzarzeCommand.execute(
                        conn=conn, cursor=cursor, linia=linia, data_planu=data_planu, produkt=produkt, 
                        tonaz=tonaz, typ=typ, plan_id_provided=plan_id_provided, nr_szarzy=nr_szarzy, 
                        auto_szarza_mode=auto_szarza_mode, is_admin=is_admin_role, session=session, 
                        request_path=request.path, ui_trigger=ui_trigger
                    )
                    
                    if not success:
                        flash(message, 'error' if 'Musisz podać' in message or 'Nie znaleziono' in message else 'modal_error')
                    else:
                        conn.commit()
                        from app.db import refresh_bufor_queue
                        refresh_bufor_queue(None, linia=linia)
                        
                    return redirect(return_url_builder())

                if sekcja in ('Workowanie', 'Czyszczenie'):
                    from app.db import get_table_name, refresh_bufor_queue
                    table_plan = get_table_name('plan_produkcji', linia)
                    table_pal = get_table_name('palety_workowanie', linia)

                    cursor.execute(
                        f"SELECT id, typ_produkcji FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja IN ('Workowanie', 'Czyszczenie') AND status IN ('zaplanowane', 'w toku') ORDER BY id ASC LIMIT 1",
                        (data_planu, produkt),
                    )
                    main_plan = cursor.fetchone()
                    if main_plan:
                        main_plan_id = main_plan[0]
                        cursor.execute(f'INSERT INTO {table_pal} (plan_id, waga, status) VALUES (%s, %s, %s)', (main_plan_id, tonaz, 'oczekuje'))
                        cursor.execute(f'UPDATE {table_plan} SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id=%s', (tonaz, main_plan_id))
                        conn.commit()
                        refresh_bufor_queue(conn, linia=linia)
                    return redirect(return_url_builder())

            # Jeżeli to nie był zasyp, to próbujemy dodać zwykły plan
            success, message, _ = DodajPlanCommand.execute(
                conn=conn, cursor=cursor, linia=linia, data_planu=data_planu, produkt=produkt, 
                tonaz=tonaz, sekcja=sekcja, typ=typ, typ_opakowania=typ_opakowania, session=session
            )
            if not success:
                flash(message, 'modal_error')
                return redirect(url_for('planista.panel_planisty', data=data_planu, linia=linia))

            conn.commit()
            
        except Exception as e:
            current_app.logger.error(f'Error adding plan: {e}', exc_info=True)
            conn.rollback()
        finally:
            conn.close()

        return redirect(return_url_builder())

    @planning_bp.route('/dodaj_plany_batch', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    def dodaj_plany_batch():
        """Add multiple plans in batch."""
        try:
            data = request.get_json(force=True)
        except Exception:
            data = {}
            
        data_planu = data.get('data_planu') or str(date.today())
        plans = data.get('plans') or []
        if not plans:
            return jsonify({'success': False, 'message': 'Brak planów w żądaniu'})

        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            success, message = DodajPlanyBatchCommand.execute(
                conn=conn, cursor=cursor, data_planu=data_planu, plans=plans, session=session
            )
            
            if success:
                conn.commit()
                return jsonify({'success': True})
            else:
                conn.rollback()
                return jsonify({'success': False, 'message': message})
                
        except Exception as error:
            current_app.logger.error(f'Failed to insert batch plans: {error}', exc_info=True)
            conn.rollback()
            return jsonify({'success': False, 'message': 'Błąd podczas zapisu planów'})
        finally:
            conn.close()