from datetime import date, datetime

from flask import current_app, flash, jsonify, redirect, render_template, request, session

from app.db import get_db_connection, get_table_name, rollover_unfinished
from app.decorators import login_required, roles_required
from app.services.attendance_service import AttendanceService


SECTION_ALIASES_AGRO = {
    'workowanie': 'Operator workowania',
    'operator workowania': 'Operator workowania',
    'zasyp': 'Operator zasypów 1',
    'zasyp 1': 'Operator zasypów 1',
    'operator zasypów 1': 'Operator zasypów 1',
    'operator zasypow 1': 'Operator zasypów 1',
    'zasyp 2': 'Operator zasypów 2',
    'operator zasypów 2': 'Operator zasypów 2',
    'operator zasypow 2': 'Operator zasypów 2',
    'zasyp 3': 'Operator zasypów 3',
    'operator zasypów 3': 'Operator zasypów 3',
    'operator zasypow 3': 'Operator zasypów 3',
    'zasyp 4': 'Operator zasypów 4',
    'operator zasypów 4': 'Operator zasypów 4',
    'operator zasypow 4': 'Operator zasypów 4',
    'sterownia': 'Operator sterowni',
    'operator sterowni': 'Operator sterowni',
    'hala agro': 'Operator sterowni',
    'technik': 'Technik utrzymania Ruchu',
    'technik ur': 'Technik utrzymania Ruchu',
    'technik utrzymania ruchu': 'Technik utrzymania Ruchu',
}


def normalize_agro_section(sec_name):
    if not sec_name:
        return sec_name
    return SECTION_ALIASES_AGRO.get(sec_name.strip().lower(), sec_name)


def register_production_support_routes(production_bp, bezpieczny_powrot):
    @production_bp.route('/manual_rollover', methods=['POST'])
    @roles_required('lider', 'admin')
    def manual_rollover():
        """Manually rollover unfinished jobs from one date to another."""
        from_date = request.form.get('from_date') or request.args.get('from_date')
        to_date = request.form.get('to_date') or request.args.get('to_date')
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        if not from_date or not to_date:
            flash('Brakuje daty źródłowej lub docelowej', 'error')
            return redirect(bezpieczny_powrot())

        try:
            added = rollover_unfinished(from_date, to_date, linia=linia)
            flash(f'Przeniesiono {added} zleceń ({linia}) z {from_date} na {to_date}', 'success')
        except Exception as e:
            current_app.logger.exception('manual_rollover failed: %s', e)
            flash('Błąd podczas przenoszenia zleceń', 'error')

        return redirect(bezpieczny_powrot())

    @production_bp.route('/obsada_page', methods=['GET'])
    @production_bp.route('/api/obsada_page', methods=['GET'])
    @login_required
    def obsada_page():
        """Render slide-over for managing obsada (workers on shift) for a sekcja."""
        sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Workowanie'))
        linia = request.args.get('linia') or request.form.get('linia')
        if not linia or linia == 'None':
            referrer = request.referrer or ''
            if '/agro' in referrer.lower() or 'linia=agro' in referrer.lower():
                linia = 'AGRO'
            else:
                linia = session.get('selected_hall_view') or 'PSD'

        date_str = request.args.get('date') or request.form.get('date')
        try:
            qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
        except Exception:
            qdate = date.today()

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            try:
                cursor.execute(
                    "SELECT oz.sekcja, oz.id, p.imie_nazwisko, p.id FROM obsada_zmiany oz JOIN pracownicy p ON oz.pracownik_id = p.id WHERE oz.data_wpisu = %s AND (UPPER(COALESCE(oz.linia, 'PSD')) = %s OR (%s = 'PSD' AND (oz.linia IS NULL OR oz.linia = ''))) ORDER BY oz.sekcja, p.imie_nazwisko",
                    (qdate, str(linia).strip().upper(), str(linia).strip().upper()),
                )
            except Exception:
                cursor.execute(
                    "SELECT oz.sekcja, oz.id, p.imie_nazwisko, p.id FROM obsada_zmiany oz JOIN pracownicy p ON oz.pracownik_id = p.id WHERE oz.data_wpisu = %s ORDER BY oz.sekcja, p.imie_nazwisko",
                    (qdate,),
                )
            rows = cursor.fetchall()
            obsady_map = {}
            for r in rows:
                raw_sec, oz_id, name, pracownik_id = r[0], r[1], r[2], r[3]
                sec_key = normalize_agro_section(raw_sec) if str(linia).strip().upper() == 'AGRO' else raw_sec
                obsady_map.setdefault(sec_key, []).append((oz_id, name, pracownik_id))

            if str(linia).strip().upper() == 'AGRO':
                try:
                    cursor.execute(
                        "SELECT id, imie_nazwisko FROM pracownicy "
                        "WHERE COALESCE(widoczny_agro, 1) = 1 "
                        "AND id NOT IN (SELECT pracownik_id FROM obecnosc WHERE data_wpisu=%s AND typ IN ('Nieobecnosc','Urlop','L4','Opieka')) "
                        "AND id NOT IN (SELECT pracownik_id FROM wnioski_wolne WHERE status='approved' AND data_od <= %s AND data_do >= %s) "
                        "AND id NOT IN (SELECT pracownik_id FROM uzytkownicy WHERE rola IN ('admin','zarzad','masteradmin') AND pracownik_id IS NOT NULL) "
                        "ORDER BY imie_nazwisko",
                        (qdate, qdate, qdate),
                    )
                except Exception:
                    cursor.execute(
                        "SELECT id, imie_nazwisko FROM pracownicy "
                        "WHERE id NOT IN (SELECT pracownik_id FROM obecnosc WHERE data_wpisu=%s AND typ IN ('Nieobecnosc','Urlop','L4','Opieka')) "
                        "AND id NOT IN (SELECT pracownik_id FROM wnioski_wolne WHERE status='approved' AND data_od <= %s AND data_do >= %s) "
                        "AND id NOT IN (SELECT pracownik_id FROM uzytkownicy WHERE rola IN ('admin','zarzad','masteradmin') AND pracownik_id IS NOT NULL) "
                        "ORDER BY imie_nazwisko",
                        (qdate, qdate, qdate),
                    )
            else:
                cursor.execute(
                    "SELECT id, imie_nazwisko FROM pracownicy "
                    "WHERE id NOT IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu=%s) "
                    "AND id NOT IN (SELECT pracownik_id FROM obecnosc WHERE data_wpisu=%s AND typ IN ('Nieobecnosc','Urlop','L4','Opieka')) "
                    "AND id NOT IN (SELECT pracownik_id FROM wnioski_wolne WHERE status='approved' AND data_od <= %s AND data_do >= %s) "
                    "AND id NOT IN (SELECT pracownik_id FROM uzytkownicy WHERE rola IN ('admin','zarzad','masteradmin') AND pracownik_id IS NOT NULL) "
                    "ORDER BY imie_nazwisko",
                    (qdate, qdate, qdate, qdate),
                )
            wszyscy = cursor.fetchall()

            cursor.execute(
                "SELECT p.id, p.imie_nazwisko FROM pracownicy p JOIN uzytkownicy u ON p.id = u.pracownik_id WHERE u.rola='lider' ORDER BY p.imie_nazwisko"
            )
            all_pracownicy = cursor.fetchall()

            cursor.execute("SELECT lider_psd_id, lider_agro_id FROM obsada_liderzy WHERE data_wpisu=%s", (qdate,))
            lider_row = cursor.fetchone()
            lider_psd_id = lider_row[0] if lider_row else None
            lider_agro_id = lider_row[1] if lider_row else None
        finally:
            try:
                conn.close()
            except Exception:
                pass

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == '1'
        if is_ajax:
            return render_template(
                'obsada_fragment.html',
                sekcja=sekcja,
                linia=linia,
                obsady_map=obsady_map,
                pracownicy=wszyscy,
                rola=session.get('rola'),
                qdate=qdate,
                lider_psd_id=lider_psd_id,
                lider_agro_id=lider_agro_id,
                all_pracownicy=all_pracownicy,
            )

        return render_template(
            'obsada.html',
            sekcja=sekcja,
            linia=linia,
            obsady_map=obsady_map,
            pracownicy=wszyscy,
            rola=session.get('rola'),
            qdate=qdate,
            lider_psd_id=lider_psd_id,
            lider_agro_id=lider_agro_id,
            all_pracownicy=all_pracownicy,
        )

    @production_bp.route('/api/obsada/agro_staff_visibility', methods=['GET'])
    @login_required
    def get_agro_staff_visibility():
        """Get all employees with their widoczny_agro status and current shift staffing."""
        qdate = request.args.get('date') or date.today().strftime('%Y-%m-%d')
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            try:
                cursor.execute("SELECT id, imie_nazwisko, COALESCE(widoczny_agro, 1) FROM pracownicy ORDER BY imie_nazwisko")
                rows = cursor.fetchall()
            except Exception:
                cursor.execute("SELECT id, imie_nazwisko, 1 FROM pracownicy ORDER BY imie_nazwisko")
                rows = cursor.fetchall()
            staff = [{'id': r[0], 'imie_nazwisko': r[1], 'widoczny_agro': bool(r[2])} for r in rows]

            # Fetch current obsada for AGRO on qdate
            try:
                cursor.execute(
                    "SELECT oz.sekcja, oz.id, p.imie_nazwisko, p.id FROM obsada_zmiany oz JOIN pracownicy p ON oz.pracownik_id = p.id WHERE oz.data_wpisu = %s AND UPPER(COALESCE(oz.linia, '')) = 'AGRO' ORDER BY oz.sekcja, p.imie_nazwisko",
                    (qdate,),
                )
                obs_rows = cursor.fetchall()
            except Exception:
                obs_rows = []

            obsada_map = {}
            for r in obs_rows:
                sec_key = normalize_agro_section(r[0])
                obsada_map.setdefault(sec_key, []).append({'id': r[1], 'imie_nazwisko': r[2], 'pracownik_id': r[3]})

            return jsonify({'success': True, 'staff': staff, 'obsada': obsada_map, 'date': qdate})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conn.close()

    @production_bp.route('/api/obsada/agro_staff_visibility', methods=['POST'])
    @login_required
    @roles_required(['lider', 'admin', 'masteradmin'])
    def update_agro_staff_visibility():
        """Update widoczny_agro status and shift assignments for AGRO employees."""
        data = request.get_json() or {}
        visible_ids = data.get('visible_ids', [])
        assignments = data.get('assignments', None)
        qdate = data.get('date') or date.today().strftime('%Y-%m-%d')

        if not isinstance(visible_ids, list):
            return jsonify({'success': False, 'message': 'Nieprawidłowy format danych'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE pracownicy SET widoczny_agro = 0")
            if visible_ids:
                format_strings = ','.join(['%s'] * len(visible_ids))
                cursor.execute(f"UPDATE pracownicy SET widoczny_agro = 1 WHERE id IN ({format_strings})", tuple(visible_ids))

            # Save position assignments ONLY if explicitly passed as a dictionary
            if isinstance(assignments, dict):
                agro_sections = [
                    'Operator sterowni', 'Operator workowania',
                    'Operator zasypów 1', 'Operator zasypów 2', 'Operator zasypów 3', 'Operator zasypów 4',
                    'Technik utrzymania Ruchu'
                ]
                for sekc in agro_sections:
                    if sekc in assignments:
                        p_ids = assignments[sekc]
                        if isinstance(p_ids, list):
                            # Delete old records for standard section name and aliases
                            cursor.execute(
                                "DELETE FROM obsada_zmiany WHERE data_wpisu = %s AND UPPER(COALESCE(linia, '')) = 'AGRO' AND (sekcja = %s OR sekcja = %s)",
                                (qdate, sekc, sekc.replace('Operator ', '').replace('zasypów', 'zasyp'))
                            )
                            for pid in p_ids:
                                cursor.execute(
                                    "INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id, linia) VALUES (%s, %s, %s, 'AGRO')",
                                    (qdate, sekc, pid)
                                )

            conn.commit()
            return jsonify({'success': True, 'message': 'Zapisano obsadę stanowisk oraz ustawienia pracowników AGRO.'})
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conn.close()

    @production_bp.route('/dodaj_do_obsady', methods=['POST'])
    @login_required
    def dodaj_do_obsady_alias():
        """Add worker to schedule (root alias)."""
        sekcja = request.form.get('sekcja') or request.args.get('sekcja', 'Zasyp')
        pracownik_id = request.form.get('pracownik_id')
        date_str = request.form.get('date') or request.args.get('date')
        linia = request.form.get('linia') or request.args.get('linia', 'PSD')
        
        if not pracownik_id:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'success': False, 'message': 'Nie wybrano pracownika'}), 400
            flash('Nie wybrano pracownika.', 'warning')
            return redirect(request.referrer or url_for('production.obsada_page'))
            
        success, inserted_id, employee_name = AttendanceService.add_to_schedule(sekcja, int(pracownik_id), date_str, linia=linia)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': success, 'id': inserted_id, 'pracownik_id': pracownik_id, 'name': employee_name})
        
        if success:
            flash(f'Pracownik {employee_name} dodany do obsady.', 'success')
        else:
            flash('Błąd przy dodawaniu do obsady.', 'warning')
        
        return redirect(request.referrer or url_for('production.obsada_page'))

    @production_bp.route('/zapisz_liderow_obsady', methods=['POST'])
    @login_required
    def zapisz_liderow_obsady_alias():
        """Save shift leaders (root alias)."""
        date_str = request.form.get('date') or request.args.get('date')
        
        raw_psd = request.form.get('lider_psd') if 'lider_psd' in request.form else 'NO_CHANGE'
        raw_agro = request.form.get('lider_agro') if 'lider_agro' in request.form else 'NO_CHANGE'
        
        lider_psd = 'NO_CHANGE' if raw_psd == 'NO_CHANGE' else (None if raw_psd in (None, '', '-1') else int(raw_psd))
        lider_agro = 'NO_CHANGE' if raw_agro == 'NO_CHANGE' else (None if raw_agro in (None, '', '-1') else int(raw_agro))
        
        success = AttendanceService.save_shift_leaders(date_str, lider_psd, lider_agro)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': success})
        
        if success:
            flash('Liderzy zmiany zapisani.', 'success')
        else:
            flash('Błąd przy zapisywaniu liderów.', 'warning')
        
        return redirect(request.referrer or url_for('production.obsada_page'))

    @production_bp.route('/usun_z_obsady/<int:id>', methods=['POST'])
    @login_required
    def usun_z_obsady_alias(id):
        """Remove from schedule (root alias)."""
        linia = request.form.get('linia') or request.args.get('linia', 'PSD')
        success = AttendanceService.remove_from_schedule(id, linia=linia)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': success})
        
        if success:
            flash('Pracownik usunięty z obsady.', 'success')
        return redirect(request.referrer or url_for('production.obsada_page'))

    @production_bp.route('/zasyp/szarza_notatka/<int:szarza_id>', methods=['GET'], endpoint='szarza_notatka_page')
    @production_bp.route('/zasyp/zasyp_notatka/<int:szarza_id>', methods=['GET'], endpoint='zasyp_notatka_page')
    @roles_required('laborant', 'laboratorium', 'lider', 'admin', 'zarzad')
    def szarza_notatka_page(szarza_id):
        """Render popup for editing zasyp note (uwagi) from Zasyp dashboard."""
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia).upper()
        table_zasypy = get_table_name('szarze', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        uwagi = ''
        try:
            cursor.execute(f"SELECT uwagi FROM {table_zasypy} WHERE id=%s", (szarza_id,))
            row = cursor.fetchone()
            if row:
                uwagi = row[0] or ''
        except Exception as e:
            current_app.logger.error('Failed to load zasyp note (id=%s): %s', szarza_id, e, exc_info=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        data = request.args.get('data') or str(date.today())
        sekcja = request.args.get('sekcja', 'Zasyp')
        return render_template(
            'warehouse/popups/edit_zasyp.html',
            szarza_id=szarza_id,
            zasyp_id=szarza_id,
            uwagi=uwagi,
            linia=linia,
            data=data,
            sekcja=sekcja,
        )

    @production_bp.route('/zasyp/szarza_notatka/<int:szarza_id>', methods=['POST'], endpoint='szarza_notatka_save')
    @production_bp.route('/zasyp/zasyp_notatka/<int:szarza_id>', methods=['POST'], endpoint='zasyp_notatka_save')
    @roles_required('laborant', 'laboratorium', 'lider', 'admin', 'zarzad')
    def szarza_notatka_save(szarza_id):
        """Save zasyp note (uwagi) from Zasyp dashboard popup."""
        new_uwagi = request.form.get('uwagi', '')
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia).upper()
        table_zasypy = get_table_name('szarze', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"UPDATE {table_zasypy} SET uwagi=%s WHERE id=%s", (new_uwagi, szarza_id))
            conn.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': 'Zapisano notatkę', 'szarza_id': szarza_id, 'zasyp_id': szarza_id}), 200
            flash('Zapisano notatkę do zasypu', 'success')
        except Exception as e:
            current_app.logger.error('Failed to save zasyp note (id=%s): %s', szarza_id, e, exc_info=True)
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

        return redirect(bezpieczny_powrot())
