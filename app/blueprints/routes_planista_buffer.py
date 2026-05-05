from datetime import date

from flask import current_app, jsonify, redirect, render_template, request, url_for

from app.db import get_db_connection, get_table_name, refresh_bufor_queue
from app.decorators import dynamic_role_required, roles_required


def register_planista_buffer_routes(planista_bp):
    @planista_bp.route('/bufor', methods=['GET'])
    @dynamic_role_required('bufor')
    def bufor_page():
        app_logger = current_app.logger
        app_logger.info('[BUFOR] bufor_page() called')

        wybrana_data = request.args.get('data', str(date.today()))
        wybrana_linia = request.args.get('linia', 'PSD')
        app_logger.info(f'[BUFOR] Starting bufor_page for date {wybrana_data}, line {wybrana_linia}')

        bufor_list = []

        try:
            refresh_bufor_queue(linia=wybrana_linia)

            conn = get_db_connection()
            cursor = conn.cursor()

            table_bufor = get_table_name('bufor', wybrana_linia)
            table_plan = get_table_name('plan_produkcji', wybrana_linia)

            cursor.execute(
                f"""
                 SELECT b.id, b.zasyp_id, b.data_planu, b.produkt, b.nazwa_zlecenia,
                     b.typ_produkcji, b.kolejka,
                     z.tonaz, z.tonaz_rzeczywisty, z.real_start, z.status,
                     w.tonaz, w.tonaz_rzeczywisty
                FROM {table_bufor} b
                LEFT JOIN {table_plan} z ON z.id = b.zasyp_id
                 LEFT JOIN {table_plan} w ON w.zasyp_id = b.zasyp_id AND w.sekcja = 'Workowanie'
                WHERE b.data_planu = %s AND b.status = 'aktywny'
                ORDER BY b.kolejka ASC
            """,
                (wybrana_data,),
            )

            rows = cursor.fetchall()
            app_logger.info(f'[BUFOR] Loaded {len(rows)} active bufor entries for date {wybrana_data}')

            for row in rows:
                (
                    buf_id,
                    zasyp_id,
                    zasyp_data,
                    produkt,
                    nazwa_zlecenia,
                    typ_produkcji,
                    kolejka,
                    zasyp_plan_tonaz,
                    zasyp_rzeczywisty_tonaz,
                    real_start,
                    status,
                    workowanie_plan_tonaz,
                    workowanie_rzeczywisty_tonaz,
                ) = row

                pozostalo_do_spakowania = (zasyp_rzeczywisty_tonaz or 0) - (workowanie_rzeczywisty_tonaz or 0)
                needs_reconciliation = round(pozostalo_do_spakowania, 1) != 0
                start_time = real_start.strftime('%H:%M') if real_start else 'N/A'

                przeniesiony_z = None
                if str(zasyp_data) != wybrana_data:
                    try:
                        from datetime import datetime as _dt2

                        przeniesiony_z = _dt2.strptime(str(zasyp_data), '%Y-%m-%d').strftime('%d.%m.%Y')
                    except Exception:
                        przeniesiony_z = str(zasyp_data)

                bufor_list.append(
                    {
                        'id': zasyp_id,
                        'buf_id': buf_id,
                        'zasyp_id': zasyp_id,
                        'data': str(zasyp_data),
                        'produkt': produkt,
                        'nazwa': nazwa_zlecenia or '',
                        'typ_produkcji': typ_produkcji or '',
                        'plan_zasypu': zasyp_plan_tonaz or 0,
                        'do_spakowania': zasyp_rzeczywisty_tonaz or 0,
                        'spakowane': workowanie_rzeczywisty_tonaz or 0,
                        'pozostalo_do_spakowania': round(pozostalo_do_spakowania, 1),
                        'kolejka': kolejka,
                        'needs_reconciliation': needs_reconciliation,
                        'status': status or 'zaplanowane',
                        'real_start': real_start,
                        'start_time': start_time,
                        'przeniesiony_z': przeniesiony_z,
                    }
                )

            conn.close()

        except Exception as error:
            app_logger.error(
                f'ERROR in bufor_page for date {wybrana_data}: {type(error).__name__}: {str(error)}',
                exc_info=True,
            )
            bufor_list = []

        return render_template('bufor.html', bufor_list=bufor_list, wybrana_data=wybrana_data, wybrana_linia=wybrana_linia)

    @planista_bp.route('/bufor/rozlicz', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad')
    def bufor_rozlicz():
        """Endpoint obsługujący rozliczenie zasypu."""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            try:
                plan_id = int(request.form.get('plan_id'))
            except Exception:
                try:
                    plan_id = int(request.form.get('plan_id'))
                except Exception:
                    try:
                        plan_id = int(request.json.get('plan_id'))
                    except Exception:
                        plan_id = None
                if not plan_id:
                    conn.close()
                    return ('Brak plan_id', 400)

            final = request.form.get('final_tonaz') or (request.json.get('final_tonaz') if request.json else None)
            note = request.form.get('note') or (request.json.get('note') if request.json else None)
            close = request.form.get('close') == '1' or (request.json.get('close') if request.json else False)

            try:
                if final is not None and final != '':
                    try:
                        value = int(float(str(final).replace(',', '.')))
                    except Exception:
                        value = None
                else:
                    value = None

                sql = 'UPDATE plan_produkcji SET '
                parts = []
                params = []
                if value is not None:
                    parts.append('tonaz_rzeczywisty=%s')
                    params.append(value)
                if note:
                    parts.append('wyjasnienie_rozbieznosci=%s')
                    params.append(note)
                if close:
                    parts.append("status='zakonczone'")
                    parts.append('real_stop=NOW()')

                linia = request.form.get('linia') or (request.json.get('linia') if request.json else 'PSD')
                table_plan = get_table_name('plan_produkcji', linia)

                if parts:
                    sql += ', '.join(parts) + ' WHERE id=%s'
                    params.append(plan_id)
                    cursor.execute(sql.replace('plan_produkcji', table_plan), tuple(params))
                    conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            return jsonify({'ok': True})
        except Exception:
            sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
            data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
            return redirect(url_for('planista.panel_planisty', sekcja=sekcja, data=data))

    @planista_bp.route('/bufor/archiwizuj', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad')
    def bufor_archiwizuj():
        """Endpoint obsługujący archiwizację zlecenia."""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            data = request.get_json(silent=True) or {}
            plan_id = data.get('plan_id') or request.form.get('plan_id') or request.args.get('plan_id')
            linia = data.get('linia') or request.form.get('linia') or request.args.get('linia', 'PSD')

            if not plan_id:
                return jsonify({'ok': False, 'message': 'Brak plan_id'}), 400

            plan_id = int(plan_id)
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f'UPDATE {table_plan} SET status=%s WHERE id=%s', ('archiwizowany', plan_id))

            table_bufor = get_table_name('bufor', linia)
            cursor.execute(f'UPDATE {table_bufor} SET status=%s WHERE zasyp_id=%s', ('zamkniete', plan_id))

            conn.commit()
            return jsonify({'ok': True})
        except Exception as error:
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'ok': False, 'message': str(error)}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @planista_bp.route('/bufor/reorder', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad')
    def bufor_reorder():
        """Swap kolejka of two adjacent bufor entries."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            data = request.get_json(silent=True) or {}
            buf_id = data.get('buf_id')
            direction = data.get('direction')
            linia = data.get('linia', 'PSD')

            if not buf_id or direction not in ('up', 'down'):
                return jsonify({'success': False, 'message': 'Brak wymaganych parametrów'}), 400

            buf_id = int(buf_id)
            table_bufor = get_table_name('bufor', linia)

            cursor.execute(f"SELECT id, kolejka, data_planu FROM {table_bufor} WHERE id = %s AND status = 'aktywny'", (buf_id,))
            current = cursor.fetchone()
            if not current:
                return jsonify({'success': False, 'message': 'Nie znaleziono wpisu w buforze'}), 404

            current_kolejka = current['kolejka']
            data_planu = current['data_planu']

            if direction == 'up':
                cursor.execute(
                    f"SELECT id, kolejka FROM {table_bufor} WHERE data_planu = %s AND status = 'aktywny' AND kolejka < %s ORDER BY kolejka DESC LIMIT 1",
                    (data_planu, current_kolejka),
                )
            else:
                cursor.execute(
                    f"SELECT id, kolejka FROM {table_bufor} WHERE data_planu = %s AND status = 'aktywny' AND kolejka > %s ORDER BY kolejka ASC LIMIT 1",
                    (data_planu, current_kolejka),
                )

            neighbor = cursor.fetchone()
            if not neighbor:
                return jsonify({'success': False, 'message': 'Brak sąsiedniej pozycji do zamiany'}), 400

            neighbor_id = neighbor['id']
            neighbor_kolejka = neighbor['kolejka']

            cursor.execute(f'UPDATE {table_bufor} SET kolejka = %s WHERE id = %s', (-1, buf_id))
            cursor.execute(f'UPDATE {table_bufor} SET kolejka = %s WHERE id = %s', (current_kolejka, neighbor_id))
            cursor.execute(f'UPDATE {table_bufor} SET kolejka = %s WHERE id = %s', (neighbor_kolejka, buf_id))
            conn.commit()

            return jsonify({'success': True, 'message': 'Kolejność zmieniona'}), 200
        except Exception as error:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error in bufor_reorder: {str(error)}')
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @planista_bp.route('/bufor/create_zlecenie', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad')
    def bufor_create_zlecenie():
        """Create new Workowanie zlecenie based on buffer remainder."""
        try:
            data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        except Exception:
            data = request.form.to_dict()

        zasyp_id = data.get('zasyp_id')
        use_buffer = data.get('use_buffer_data') == 'true' or data.get('use_buffer_data') is True
        override_work_date = data.get('workowanie_date')

        if not zasyp_id:
            return jsonify({'success': False, 'message': 'Brak zasyp_id'}), 400

        try:
            zasyp_id = int(zasyp_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowy zasyp_id'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        linia = data.get('linia') or 'PSD'
        table_bufor = get_table_name('bufor', linia)
        table_plan = get_table_name('plan_produkcji', linia)

        try:
            if use_buffer:
                if str(linia).upper() == 'AGRO':
                    cursor.execute(
                        f"""
                        SELECT
                            zasyp_id,
                            data_planu,
                            produkt,
                            COALESCE(tonaz_rzeczywisty, 0) as tonaz_rzeczywisty,
                            typ_produkcji,
                            COALESCE(nazwa_zlecenia, '') as nazwa_zlecenia,
                            COALESCE(SUM(spakowano), 0) as spakowano
                        FROM {table_bufor}
                        WHERE zasyp_id = %s
                        GROUP BY zasyp_id, data_planu, produkt, typ_produkcji, nazwa_zlecenia
                        LIMIT 1
                    """,
                        (zasyp_id,),
                    )
                    zasyp_data = cursor.fetchone()
                    if not zasyp_data:
                        conn.close()
                        return jsonify({'success': False, 'message': 'Nie znaleziono wpisu w buforze dla tego Zasypu'}), 404
                    z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa, spakowano = zasyp_data
                    z_linia = 'AGRO'
                else:
                    cursor.execute(
                        f"""
                        SELECT
                            zasyp_id,
                            data_planu,
                            produkt,
                            COALESCE(tonaz_rzeczywisty, 0) as tonaz_rzeczywisty,
                            typ_produkcji,
                            COALESCE(nazwa_zlecenia, '') as nazwa_zlecenia,
                            COALESCE(SUM(spakowano), 0) as spakowano,
                            MAX(linia) as linia
                        FROM {table_bufor}
                        WHERE zasyp_id = %s
                        GROUP BY zasyp_id, data_planu, produkt, typ_produkcji, nazwa_zlecenia
                        LIMIT 1
                    """,
                        (zasyp_id,),
                    )
                    zasyp_data = cursor.fetchone()
                    if not zasyp_data:
                        conn.close()
                        return jsonify({'success': False, 'message': 'Nie znaleziono wpisu w buforze dla tego Zasypu'}), 404
                    z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa, spakowano, z_linia = zasyp_data
                roznicza = (z_tonaz_rz or 0) - spakowano
            else:
                if str(linia).upper() == 'AGRO':
                    cursor.execute(
                        f"""
                        SELECT id, data_planu, produkt, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia
                        FROM {table_plan}
                        WHERE id = %s AND sekcja = 'Zasyp'
                    """,
                        (zasyp_id,),
                    )
                    zasyp = cursor.fetchone()
                    if not zasyp:
                        conn.close()
                        return jsonify({'success': False, 'message': 'Nie znaleziono Zasypu'}), 404
                    z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa = zasyp
                    z_linia = 'AGRO'
                else:
                    cursor.execute(
                        f"""
                        SELECT id, data_planu, produkt, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia, linia
                        FROM {table_plan}
                        WHERE id = %s AND sekcja = 'Zasyp'
                    """,
                        (zasyp_id,),
                    )
                    zasyp = cursor.fetchone()
                    if not zasyp:
                        conn.close()
                        return jsonify({'success': False, 'message': 'Nie znaleziono Zasypu'}), 404
                    z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa, z_linia = zasyp

                cursor.execute(
                    f"""
                    SELECT SUM(spakowano) FROM {table_bufor}
                    WHERE zasyp_id = %s AND data_planu = %s
                """,
                    (zasyp_id, z_data),
                )
                result = cursor.fetchone()
                spakowano = result[0] or 0 if result else 0
                roznicza = (z_tonaz_rz or 0) - spakowano

            work_date = str(override_work_date) if override_work_date else str(z_data)
            source_date_str = str(z_data)
            is_new_day = work_date != source_date_str

            if roznicza <= 0:
                conn.close()
                return jsonify({'success': False, 'message': 'Nie ma pozostałego towaru do spakowania (różnica <= 0)'}), 400

            cursor.execute(
                f"""
                SELECT id FROM {table_plan}
                WHERE data_planu = %s AND produkt = %s AND sekcja = 'Workowanie'
                LIMIT 1
            """,
                (work_date, z_produkt),
            )
            existing_work = cursor.fetchone()
            if existing_work:
                conn.close()
                return jsonify(
                    {
                        'success': False,
                        'message': f'Zlecenie Workowanie na produkt "{z_produkt}" już istnieje dla tej daty',
                    }
                ), 400

            final_zasyp_id = z_id
            if is_new_day:
                cursor.execute(
                    f"""
                    SELECT id FROM {table_plan}
                    WHERE data_planu = %s AND produkt = %s AND sekcja = 'Zasyp' AND typ_zlecenia = 'carry_over_ghost'
                    LIMIT 1
                """,
                    (work_date, z_produkt),
                )
                existing_ghost = cursor.fetchone()

                if existing_ghost:
                    final_zasyp_id = existing_ghost[0]
                else:
                    cursor.execute(f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu = %s AND sekcja = 'Zasyp'", (work_date,))
                    result_max = cursor.fetchone()
                    nk_zasyp = (result_max[0] or 0) + 1

                    if str(linia).upper() == 'AGRO':
                        cursor.execute(
                            f"""
                            INSERT INTO {table_plan}
                            (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, typ_zlecenia, tonaz_rzeczywisty)
                            VALUES (%s, %s, %s, 0, 'zakonczone', %s, %s, %s, 'carry_over_ghost', 0)
                        """,
                            (work_date, 'Zasyp', z_produkt, nk_zasyp, z_typ or 'worki_zgrzewane_25', f'Carry-over {source_date_str}'),
                        )
                    else:
                        cursor.execute(
                            f"""
                            INSERT INTO {table_plan}
                            (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, typ_zlecenia, linia, tonaz_rzeczywisty)
                            VALUES (%s, %s, %s, 0, 'zakonczone', %s, %s, %s, 'carry_over_ghost', %s, 0)
                        """,
                            (
                                work_date,
                                'Zasyp',
                                z_produkt,
                                nk_zasyp,
                                z_typ or 'worki_zgrzewane_25',
                                f'Carry-over {source_date_str}',
                                z_linia,
                            ),
                        )
                    final_zasyp_id = cursor.lastrowid

                    cursor.execute(f'SELECT COALESCE(MAX(kolejka),0) FROM {table_bufor} WHERE data_planu=%s', (work_date,))
                    max_kolejka = cursor.fetchone()[0] or 0
                    if str(linia).upper() == 'AGRO':
                        cursor.execute(
                            f"""
                            INSERT INTO {table_bufor} (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, tonaz_rzeczywisty, spakowano, kolejka, status)
                            VALUES (%s, %s, %s, %s, %s, %s, 0, %s, 'aktywny')
                        """,
                            (
                                final_zasyp_id,
                                work_date,
                                z_produkt,
                                f'Carry-over {source_date_str}',
                                z_typ or 'worki_zgrzewane_25',
                                round(roznicza, 1),
                                max_kolejka + 1,
                            ),
                        )
                    else:
                        cursor.execute(
                            f"""
                            INSERT INTO {table_bufor} (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, tonaz_rzeczywisty, spakowano, kolejka, status, linia)
                            VALUES (%s, %s, %s, %s, %s, %s, 0, %s, 'aktywny', %s)
                        """,
                            (
                                final_zasyp_id,
                                work_date,
                                z_produkt,
                                f'Carry-over {source_date_str}',
                                z_typ or 'worki_zgrzewane_25',
                                round(roznicza, 1),
                                max_kolejka + 1,
                                z_linia,
                            ),
                        )

            cursor.execute(
                f"""
                SELECT MAX(kolejnosc) FROM {table_plan}
                WHERE data_planu = %s AND sekcja = 'Workowanie'
            """,
                (work_date,),
            )
            result = cursor.fetchone()
            next_kolejnosc = (result[0] or 0) + 1 if result else 1

            if str(linia).upper() == 'AGRO':
                cursor.execute(
                    f"""
                    INSERT INTO {table_plan}
                    (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, zasyp_id, tonaz_rzeczywisty)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                """,
                    (
                        work_date,
                        'Workowanie',
                        z_produkt,
                        round(roznicza, 1),
                        'zaplanowane',
                        next_kolejnosc,
                        z_typ or 'worki_zgrzewane_25',
                        z_nazwa or '',
                        final_zasyp_id,
                    ),
                )
            else:
                cursor.execute(
                    f"""
                    INSERT INTO {table_plan}
                    (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, zasyp_id, linia, tonaz_rzeczywisty)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                """,
                    (
                        work_date,
                        'Workowanie',
                        z_produkt,
                        round(roznicza, 1),
                        'zaplanowane',
                        next_kolejnosc,
                        z_typ or 'worki_zgrzewane_25',
                        z_nazwa or '',
                        final_zasyp_id,
                        z_linia,
                    ),
                )

            conn.commit()
            new_id = cursor.lastrowid

            conn.close()
            return jsonify(
                {
                    'success': True,
                    'message': f'Utworzono zlecenie Workowanie z planem {round(roznicza, 1)} kg',
                    'new_id': new_id,
                    'plan_kg': round(roznicza, 1),
                }
            ), 201

        except Exception as error:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception('Error in bufor_create_zlecenie')
            return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass