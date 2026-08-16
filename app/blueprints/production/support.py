from datetime import date, datetime

from flask import current_app, flash, jsonify, redirect, render_template, request, session

from app.db import get_db_connection, get_table_name, rollover_unfinished
from app.decorators import login_required, roles_required


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
        linia = request.args.get('linia', request.form.get('linia')) or session.get('selected_hall_view') or 'PSD'
        date_str = request.args.get('date') or request.form.get('date')
        try:
            qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
        except Exception:
            qdate = date.today()

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT oz.sekcja, oz.id, p.imie_nazwisko, p.id FROM obsada_zmiany oz JOIN pracownicy p ON oz.pracownik_id = p.id WHERE oz.data_wpisu = %s ORDER BY oz.sekcja, p.imie_nazwisko",
                (qdate,),
            )
            rows = cursor.fetchall()
            obsady_map = {}
            for r in rows:
                sekc, oz_id, name, pracownik_id = r[0], r[1], r[2], r[3]
                obsady_map.setdefault(sekc, []).append((oz_id, name, pracownik_id))

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

        try:
            is_ajax = request.headers.get('X-Requested-With', '') == 'XMLHttpRequest' or request.path.startswith('/api/') or request.args.get('fragment') == 'true'
        except Exception:
            is_ajax = False

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
