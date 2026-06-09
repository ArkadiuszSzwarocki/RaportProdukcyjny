import logging
from datetime import date

from flask import current_app, flash, jsonify, redirect, request, session, url_for

from app.core.audit import audit_log
from app.db import get_db_connection, get_plan_notification_context, get_table_name, refresh_bufor_queue
from app.decorators import hall_restricted, roles_required
from app.services.notification_service import notify_laboratory_about_zasyp, notify_workers_about_plan_batch, notify_workers_about_plan_change
from app.services.planning_service import PlanningService


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

        try:
            tonaz = int(float(request.form.get('tonaz', 0)))
        except Exception as error:
            current_app.logger.debug(f'Failed to parse tonaz in dodaj_plan_zaawansowany: {error}')
            tonaz = 0

        linia = request.form.get('linia', 'PSD')
        success, message, plan_id = PlanningService.create_plan(
            data_planu,
            produkt,
            tonaz,
            sekcja,
            typ,
            status='zaplanowane',
            wymaga_oplaty=wymaga_oplaty,
            linia=linia,
        )

        if success and plan_id:
            notify_workers_about_plan_change(
                plan_context={
                    'id': plan_id,
                    'produkt': produkt,
                    'sekcja': sekcja,
                    'data_planu': data_planu,
                },
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
        try:
            tonaz = int(float(request.form.get('tonaz', 0)))
        except Exception:
            tonaz = 0
        sekcja = (request.form.get('sekcja') or request.args.get('sekcja') or 'Nieprzydzielony').strip()
        sekcja = sekcja[0].upper() + sekcja[1:].lower() if sekcja else 'Nieprzydzielony'
        typ = request.form.get('typ_produkcji', 'worki_zgrzewane_25')
        typ_opakowania = request.form.get('typ_opakowania', '').strip() or 'worki'
        linia = request.form.get('linia', 'PSD')

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

        if is_ops_role:
            if not (sekcja == 'Zasyp' and plan_id_provided > 0):
                flash('Brak uprawnień do dodawania zasypów w tym widoku.', 'warning')
                return redirect(return_url_builder())

        log_msg = f'[DODAJ_PLAN] POST received: sekcja={sekcja}, produkt={produkt}, tonaz={tonaz}, typ={typ}, plan_id={plan_id_provided}'
        try:
            current_app.logger.warning(log_msg)
        except Exception:
            pass
        try:
            print(log_msg)
        except Exception:
            pass

        if not produkt:
            try:
                current_app.logger.debug('[DODAJ_PLAN] MISSING produkt - redirecting')
            except Exception:
                pass
            return redirect(return_url_builder())

        conn = get_db_connection()
        cursor = conn.cursor()

        zasyp_plan_id = None
        if tonaz > 0:
            if sekcja == 'Zasyp':
                try:
                    current_app.logger.debug('[DODAJ_PLAN] Processing ZASYP')
                except Exception:
                    pass

                table_plan = get_table_name('plan_produkcji', linia)
                table_szarze = get_table_name('szarze', linia)
                table_dosypki = get_table_name('dosypki', linia)

                if plan_id_provided > 0:
                    zasyp_plan_id = plan_id_provided
                    try:
                        current_app.logger.debug(f'[DODAJ_PLAN] Using PROVIDED plan_id={zasyp_plan_id} ({linia})')
                    except Exception:
                        pass
                else:
                    try:
                        current_app.logger.debug(f'[DODAJ_PLAN] plan_id_provided=0, searching for Zasyp plan for produkt={produkt} ({linia})')
                    except Exception:
                        pass

                    cursor.execute(
                        f"SELECT id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Zasyp' AND COALESCE(typ_produkcji,'')=%s ORDER BY id DESC LIMIT 1",
                        (data_planu, produkt, typ),
                    )
                    szarza_plan = cursor.fetchone()
                    if szarza_plan:
                        zasyp_plan_id = szarza_plan[0]
                        try:
                            current_app.logger.debug(f'[DODAJ_PLAN] FOUND Zasyp plan: plan_id={zasyp_plan_id}')
                        except Exception:
                            pass

                if zasyp_plan_id:
                    try:
                        current_app.logger.debug(f'[DODAJ_PLAN] ADDING szarża: plan_id={zasyp_plan_id}, tonaz={tonaz}')
                    except Exception:
                        pass

                    auto_szarza_mode = str(request.form.get('auto_szarza_mode') or 'manual').strip().lower()
                    auto_szarza_mode = 'auto' if auto_szarza_mode == 'auto' else 'manual'

                    nr_szarzy_str = request.form.get('nr_szarzy') or request.form.get('nr_zasypu')
                    try:
                        nr_szarzy = int(nr_szarzy_str) if nr_szarzy_str else None
                    except ValueError:
                        nr_szarzy = None

                    if not nr_szarzy:
                        flash('Musisz podać numer zasypu!', 'error')
                        conn.close()
                        return redirect(return_url_builder())

                    cursor.execute(f'SELECT MAX(nr_szarzy) FROM {table_szarze} WHERE plan_id=%s', (zasyp_plan_id,))
                    max_nr = cursor.fetchone()[0]
                    expected_nr = (max_nr or 0) + 1

                    is_admin = session.get('rola', '').lower() == 'admin'

                    if str(linia).upper() == 'AGRO' and auto_szarza_mode == 'auto' and not is_admin:
                        flash(
                            'BŁĄD: Tryb AUTO SZARŻA jest włączony. Ręczne + ZASYP jest zablokowane - użyj START Naważania.',
                            'modal_error',
                        )
                        conn.close()
                        return redirect(return_url_builder())

                    if nr_szarzy != expected_nr and not is_admin:
                        flash(
                            f'BŁĄD: Podałeś błędny numer zasypu ({nr_szarzy}). Wykryto naruszenie kolejności! (Oczekiwano: {expected_nr}). Zweryfikuj prawidłowy numer zasypu z recepturą.',
                            'modal_error',
                        )
                        conn.close()
                        return redirect(return_url_builder())

                    if str(linia).upper() == 'AGRO' and not is_admin:
                        try:
                            cursor.execute(
                                "SELECT COUNT(DISTINCT szarza_nr) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s",
                                (str(linia).upper(), int(zasyp_plan_id)),
                            )
                            kontrolne_row = cursor.fetchone()
                            kontrolne_count = int(kontrolne_row[0] if kontrolne_row else 0)
                        except Exception:
                            kontrolne_count = 0

                        target_szarza_nr = int(nr_szarzy)
                        if target_szarza_nr > kontrolne_count:
                            try:
                                linia_u = str(linia).upper()
                                start_login = (session.get('login') or '')[:100]
                                for missing_szarza_nr in range(kontrolne_count + 1, target_szarza_nr + 1):
                                    cursor.execute(
                                        """
                                        INSERT INTO zasyp_etapy (linia, plan_id, data_planu, szarza_nr, etap, czas_start, czas_stop, start_login, stop_login)
                                        VALUES (%s, %s, %s, %s, %s, NULL, NULL, %s, NULL)
                                        ON DUPLICATE KEY UPDATE plan_id = plan_id
                                        """,
                                        (linia_u, int(zasyp_plan_id), data_planu, int(missing_szarza_nr), 0, start_login),
                                    )
                            except Exception:
                                flash(
                                    f'BŁĄD: Nie udało się zsynchronizować punktów kontrolnych dla zasypu #{nr_szarzy}.',
                                    'modal_error',
                                )
                                conn.close()
                                return redirect(return_url_builder())

                    from datetime import datetime as _dt

                    now = _dt.now()
                    godzina = now.strftime('%H:%M:%S')
                    pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None

                    cursor.execute(
                        f'INSERT INTO {table_szarze} (plan_id, waga, data_dodania, godzina, pracownik_id, status, nr_szarzy) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                        (zasyp_plan_id, tonaz, now, godzina, pracownik_id, 'zarejestowana', nr_szarzy),
                    )

                    cursor.execute(
                        f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                        f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                        f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                        f"WHERE id = %s",
                        (zasyp_plan_id, zasyp_plan_id, zasyp_plan_id),
                    )
                    try:
                        ui_trigger = (request.form.get('ui_trigger') or '').strip() or 'button:dodaj_szarze_popup'
                        current_app.logger.info(
                            'Dodano zasyp do zlecenia ID=%s, produkt=%s, tonaz=%s kg, użytkownik=%s',
                            zasyp_plan_id,
                            produkt,
                            tonaz,
                            session.get('login'),
                        )
                        audit_log(
                            'Dodał zasyp',
                            f'zlecenie_id={zasyp_plan_id}, produkt={produkt}, tonaz={tonaz} kg, nr={nr_szarzy}, linia={linia}, trigger={ui_trigger}',
                        )
                    except Exception:
                        pass

                    plan_context = get_plan_notification_context(zasyp_plan_id, conn=conn, linia=linia)
                    notify_laboratory_about_zasyp(
                        plan_context=plan_context,
                        weight_kg=tonaz,
                        author_name=session.get('imie_nazwisko') or session.get('login'),
                        conn=conn,
                        cursor=cursor,
                        created_by_user_id=session.get('user_id'),
                        linia=linia,
                    )
                    
                    try:
                        # _mark_dosypki_updated function removed - no longer needed
                        # _mark_dosypki_updated(linia)
                        pass
                    except Exception as e:
                        current_app.logger.warning(f"Failed to mark dosypki updated on zasyp creation: {e}")

                    cursor.execute(
                        f"SELECT id, tonaz, zasyp_id FROM {table_plan} WHERE zasyp_id=%s AND sekcja='Workowanie' ORDER BY id ASC LIMIT 1",
                        (zasyp_plan_id,),
                    )
                    workowanie_plan = cursor.fetchone()
                    if not workowanie_plan:
                        cursor.execute(
                            f"SELECT id, tonaz, zasyp_id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' ORDER BY id ASC LIMIT 1",
                            (data_planu, produkt),
                        )
                        workowanie_plan = cursor.fetchone()

                    if not workowanie_plan:
                        cursor.execute(f'SELECT typ_produkcji FROM {table_plan} WHERE id=%s', (zasyp_plan_id,))
                        source_row = cursor.fetchone()
                        source_typ = source_row[0] if source_row else 'worki_zgrzewane_25'

                        cursor.execute(f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja='Workowanie'", (data_planu,))
                        res = cursor.fetchone()
                        nk_work = (res[0] if res and res[0] else 0) + 1

                        cursor.execute(
                            f'INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, zasyp_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                            (data_planu, produkt, tonaz, 'zaplanowane', 'Workowanie', nk_work, source_typ, 0, zasyp_plan_id),
                        )
                        try:
                            current_app.logger.debug(f'[DODAJ_PLAN] Created new Workowanie plan for produkt={produkt} when first szarża added')
                        except Exception:
                            pass
                    else:
                        workowanie_id = workowanie_plan[0]
                        w_existing_tonaz = workowanie_plan[1] or 0
                        w_zasyp_id = workowanie_plan[2]
                        debug_msg = f'[DODAJ_PLAN][DEBUG] produkt={produkt} data_planu={data_planu} zasyp_plan_id={zasyp_plan_id} w_zasyp_id={w_zasyp_id} w_existing_tonaz={w_existing_tonaz} szarza={tonaz}'
                        try:
                            current_app.logger.warning(debug_msg)
                        except Exception:
                            print(debug_msg)

                        cursor.execute(f"SELECT id, tonaz FROM {table_plan} WHERE zasyp_id=%s AND sekcja='Workowanie' ORDER BY id ASC LIMIT 1", (zasyp_plan_id,))
                        linked = cursor.fetchone()
                        if linked:
                            target_id, target_existing_tonaz = linked[0], linked[1] or 0
                            new_workowanie_tonaz = target_existing_tonaz + tonaz
                            cursor.execute(
                                f"UPDATE {table_plan} SET status='zaplanowane', real_start=NULL, real_stop=NULL, tonaz=%s WHERE id=%s AND status!='w toku'",
                                (new_workowanie_tonaz, target_id),
                            )
                            try:
                                status_logger = logging.getLogger('status_changes')
                                status_logger.info(
                                    'action=update_workowanie plan_id=%s old_tonaz=%s new_tonaz=%s user=%s endpoint=%s caller=routes_planning.dodaj_plan',
                                    target_id,
                                    target_existing_tonaz,
                                    new_workowanie_tonaz,
                                    session.get('login'),
                                    request.path,
                                )
                            except Exception:
                                pass
                            try:
                                current_app.logger.debug(
                                    f'[DODAJ_PLAN] Summed into linked Workowanie id={target_id}: tonaz={new_workowanie_tonaz} (was {target_existing_tonaz} + szarza {tonaz})'
                                )
                            except Exception:
                                pass
                        else:
                            if not w_zasyp_id:
                                try:
                                    cursor.execute(f'UPDATE {table_plan} SET zasyp_id=%s WHERE id=%s', (zasyp_plan_id, workowanie_id))
                                    w_zasyp_id = zasyp_plan_id
                                except Exception:
                                    pass
                            new_workowanie_tonaz = w_existing_tonaz + tonaz
                            cursor.execute(
                                f"UPDATE {table_plan} SET status='zaplanowane', real_start=NULL, real_stop=NULL, tonaz=%s WHERE id=%s AND status!='w toku'",
                                (new_workowanie_tonaz, workowanie_id),
                            )
                            try:
                                status_logger = logging.getLogger('status_changes')
                                status_logger.info(
                                    'action=update_workowanie plan_id=%s old_tonaz=%s new_tonaz=%s user=%s endpoint=%s caller=routes_planning.dodaj_plan',
                                    workowanie_id,
                                    w_existing_tonaz,
                                    new_workowanie_tonaz,
                                    session.get('login'),
                                    request.path,
                                )
                            except Exception:
                                pass
                            try:
                                current_app.logger.debug(
                                    f'[DODAJ_PLAN] Reset/sum Workowanie plan for produkt={produkt}: tonaz={new_workowanie_tonaz} (carry_over={w_existing_tonaz}, szarza={tonaz})'
                                )
                            except Exception:
                                pass

                    conn.commit()
                    conn.close()
                    try:
                        refresh_bufor_queue(None, linia=linia)
                    except Exception:
                        pass
                    try:
                        current_app.logger.debug('[DODAJ_PLAN] SUCCESS: committed and returning')
                    except Exception:
                        pass
                    return redirect(return_url_builder())

                conn.close()
                try:
                    current_app.logger.debug(
                        f'[DODAJ_PLAN] ERROR: No plan found for szarża. plan_id_provided={plan_id_provided}, produkt={produkt}'
                    )
                except Exception:
                    pass
                flash('Nie znaleziono planu do dodania zasypu', 'error')
                return redirect(return_url_builder())

            if sekcja == 'Workowanie':
                table_plan = get_table_name('plan_produkcji', linia)
                table_pal = get_table_name('palety_workowanie', linia)

                cursor.execute(
                    f"SELECT id, typ_produkcji FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND status IN ('zaplanowane', 'w toku') ORDER BY id ASC LIMIT 1",
                    (data_planu, produkt),
                )
                main_plan = cursor.fetchone()
                if main_plan:
                    main_plan_id, _actual_typ = main_plan[0], main_plan[1]
                    try:
                        current_app.logger.debug(f'[DODAJ_PLAN] Adding paleta to Workowanie main plan {main_plan_id}, tonaz={tonaz}')
                    except Exception:
                        pass

                    cursor.execute(
                        f'INSERT INTO {table_pal} (plan_id, waga, status) VALUES (%s, %s, %s)',
                        (main_plan_id, tonaz, 'oczekuje'),
                    )
                    cursor.execute(
                        f'UPDATE {table_plan} SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id=%s',
                        (tonaz, main_plan_id),
                    )
                    try:
                        current_app.logger.debug(f'[DODAJ_PLAN] Updated Workowanie plan {main_plan_id}, tonaz_rzeczywisty += {tonaz}')
                    except Exception:
                        pass

                    conn.commit()
                    try:
                        refresh_bufor_queue(conn, linia=linia)
                    except Exception:
                        pass
                    conn.close()
                return redirect(return_url_builder())

        table_plan = get_table_name('plan_produkcji', linia)
        try:
            cursor.execute(
                f'SELECT id, sekcja FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND (is_deleted=0 OR is_deleted IS NULL) LIMIT 1',
                (data_planu, produkt),
            )
            existing = cursor.fetchone()
            if existing:
                flash(
                    f'Zlecenie dla {produkt} już istnieje na dzień {data_planu}. Zmień ilość istniejącego zlecenia zamiast tworzyć nowe.',
                    'modal_error',
                )
                conn.close()
                return redirect(url_for('planista.panel_planisty', data=data_planu, linia=linia))
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

        status = 'zaplanowane'
        cursor.execute(f'SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja=%s', (data_planu, sekcja))
        res = cursor.fetchone()
        nk = (res[0] if res and res[0] else 0) + 1
        
        # Dla Czyszczenia nie ustawiamy typ_opakowania (operator wybiera na workowaniu)
        typ_opak_db = None if sekcja == 'Czyszczenie' else typ_opakowania
        
        cursor.execute(
            f'INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, typ_opakowania, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (data_planu, produkt, tonaz, status, sekcja, nk, typ, typ_opak_db, 0),
        )
        zasyp_plan_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None

        notify_workers_about_plan_change(
            plan_context={
                'id': zasyp_plan_id,
                'produkt': produkt,
                'sekcja': sekcja,
                'data_planu': data_planu,
            },
            action_label='dodał',
            author_name=session.get('imie_nazwisko') or session.get('login'),
            conn=conn,
            cursor=cursor,
            created_by_user_id=session.get('user_id'),
            linia=linia,
        )

        conn.commit()
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
            table_psd = get_table_name('plan_produkcji', 'PSD')
            cursor.execute(
                f"""
                SELECT sekcja, MAX(kolejnosc) as max_seq
                FROM {table_psd}
                WHERE data_planu=%s
                GROUP BY sekcja
            """,
                (data_planu,),
            )
            max_seq_map = {row[0]: (row[1] if row[1] else 0) for row in cursor.fetchall()}

            table_agro = get_table_name('plan_produkcji', 'Agro')
            cursor.execute(
                f"""
                SELECT sekcja, MAX(kolejnosc) as max_seq
                FROM {table_agro}
                WHERE data_planu=%s
                GROUP BY sekcja
            """,
                (data_planu,),
            )
            max_seq_map_agro = {row[0]: (row[1] if row[1] else 0) for row in cursor.fetchall()}

            for idx, plan in enumerate(plans, start=1):
                produkt = (plan.get('produkt') or '').strip()
                try:
                    tonaz = int(float(plan.get('tonaz') or 0))
                except Exception as parse_err:
                    current_app.logger.debug(f'Row {idx} tonaz parse error: {parse_err}')
                    tonaz = 0
                typ = (plan.get('typ_produkcji') or '').strip() or 'worki_zgrzewane_25'
                typ_opakowania = (plan.get('typ_opakowania') or '').strip() or 'worki'
                sekcja = (plan.get('sekcja') or 'Zasyp').strip()
                sekcja = sekcja[0].upper() + sekcja[1:].lower() if sekcja else 'Zasyp'
                nr = plan.get('nr_receptury') or ''
                if not produkt:
                    return jsonify({'success': False, 'message': f'Wiersz {idx}: brak nazwy produktu'})
                if not (isinstance(tonaz, int) and tonaz > 0):
                    return jsonify({'success': False, 'message': f'Wiersz {idx}: nieprawidłowy tonaż'})
                if not typ:
                    return jsonify({'success': False, 'message': f'Wiersz {idx}: brak typu produkcji'})

                target_linia = 'Agro' if sekcja == 'Agro' else 'PSD'
                table_target = get_table_name('plan_produkcji', target_linia)

                cursor.execute(
                    f'SELECT id FROM {table_target} WHERE data_planu=%s AND produkt=%s AND (is_deleted=0 OR is_deleted IS NULL) LIMIT 1',
                    (data_planu, produkt),
                )
                if cursor.fetchone():
                    return jsonify({'success': False, 'message': f'Wiersz {idx}: zlecenie dla {produkt} już istnieje na {data_planu} — edytuj istniejący plan.'})

                if sekcja == 'Agro':
                    opakowanie_id_val = plan.get('opakowanie_id')
                    etykieta_id_val = plan.get('etykieta_id')
                    
                    try:
                        opakowanie_id = int(opakowanie_id_val) if opakowanie_id_val not in (None, '', 'None') else None
                    except Exception:
                        opakowanie_id = None
                        
                    try:
                        etykieta_id = int(etykieta_id_val) if etykieta_id_val not in (None, '', 'None') else None
                    except Exception:
                        etykieta_id = None

                    # Dla worków wymagane są opakowanie i etykieta
                    if typ_opakowania == 'worki' and (not opakowanie_id or not etykieta_id):
                        return jsonify({'success': False, 'message': f'Wiersz {idx}: Dla linii AGRO z workami wyznaczony worek (opakowanie) oraz etykieta są obowiązkowe!'})

                    nk_agro = max_seq_map_agro.get('Agro', 0) + 1
                    max_seq_map_agro['Agro'] = nk_agro
                    cursor.execute(
                        f'INSERT INTO {table_agro} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, nr_receptury, tonaz_rzeczywisty, opakowanie_id, etykieta_id, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                        (data_planu, produkt, tonaz, 'zaplanowane', 'Zasyp', nk_agro, typ, nr, 0, opakowanie_id, etykieta_id, typ_opakowania),
                    )

                    nk_work_agro = max_seq_map_agro.get('Workowanie', 0) + 1
                    max_seq_map_agro['Workowanie'] = nk_work_agro
                    zasyp_id_agro = cursor.lastrowid
                    cursor.execute(
                        f'INSERT INTO {table_agro} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, zasyp_id, opakowanie_id, etykieta_id, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                        (data_planu, produkt, 0, 'zaplanowane', 'Workowanie', nk_work_agro, typ, 0, zasyp_id_agro, opakowanie_id, etykieta_id, typ_opakowania),
                    )
                    continue

                nk_zasyp = max_seq_map.get('Zasyp', 0) + 1
                max_seq_map['Zasyp'] = nk_zasyp
                cursor.execute(
                    f'INSERT INTO {table_psd} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, nr_receptury, tonaz_rzeczywisty, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                    (data_planu, produkt, tonaz, 'zaplanowane', sekcja, nk_zasyp, typ, nr, 0, typ_opakowania),
                )

                if sekcja == 'Zasyp':
                    nk_work = max_seq_map.get('Workowanie', 0) + 1
                    max_seq_map['Workowanie'] = nk_work
                    zasyp_id_created = cursor.lastrowid
                    cursor.execute(
                        f'INSERT INTO {table_psd} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, zasyp_id, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                        (data_planu, produkt, 0, 'zaplanowane', 'Workowanie', nk_work, typ, 0, zasyp_id_created, typ_opakowania),
                    )

            notify_workers_about_plan_batch(
                data_planu=data_planu,
                plans_count=len(plans),
                author_name=session.get('imie_nazwisko') or session.get('login'),
                conn=conn,
                cursor=cursor,
                created_by_user_id=session.get('user_id'),
                linia='PSD',
            )
            conn.commit()
            current_app.logger.info('Dodano %s zleceń na dzień %s przez %s', len(plans), data_planu, session.get('login'))
            audit_log('Dodał zlecenia (bulk)', f'{len(plans)} zleceń na {data_planu}')
            return jsonify({'success': True})

        except Exception as error:
            current_app.logger.error(f'Failed to insert batch plans: {error}', exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'success': False, 'message': 'Błąd podczas zapisu planów'})

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass