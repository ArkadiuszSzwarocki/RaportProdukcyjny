from datetime import date, timedelta

from flask import current_app, flash, redirect, render_template, request, session, url_for

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required
from app.services.zasyp_etapy_service import ZasypEtapyService


def register_production_zasyp_etapy_routes(
    production_bp,
    bezpieczny_powrot,
    coerce_date,
    parse_float,
):
    def _read_zasyp_nr_from_form():
        raw = request.form.get('zasyp_nr') or request.form.get('szarza_nr')
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None

    def _read_zasyp_nr_from_args():
        raw = request.args.get('zasyp_nr') or request.args.get('szarza_nr')
        if raw is None:
            return ''
        return str(raw).strip()

    @production_bp.route('/zasyp_etap_manual_set', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'zarzad')
    def zasyp_etap_manual_set():
        """Ręczny zapis czasu START/STOP etapu (HH:MM) dla zlecenia Zasyp."""
        linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia_input).upper()

        plan_id_raw = request.form.get('plan_id')
        etap_raw = request.form.get('etap')
        szarza_nr_raw = _read_zasyp_nr_from_form()
        czas_start_hhmm = (request.form.get('czas_start_hhmm') or '').strip()
        czas_stop_hhmm = (request.form.get('czas_stop_hhmm') or '').strip()

        try:
            plan_id = int(plan_id_raw)
            etap = int(etap_raw)
        except Exception:
            flash('❌ Nieprawidłowe dane ręcznego zapisu etapu', 'danger')
            return redirect(bezpieczny_powrot())

        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT sekcja, status, data_planu, produkt FROM {table_plan} WHERE id=%s",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                flash('❌ Zlecenie nie znalezione', 'danger')
                return redirect(bezpieczny_powrot())
            sekcja, status, data_planu, produkt = row[0], row[1], row[2], row[3]
            if sekcja != 'Zasyp':
                flash('❌ To nie jest zlecenie Zasyp', 'danger')
                return redirect(bezpieczny_powrot())
            if status not in ('w toku', 'zakonczone'):
                flash('❌ Zlecenie musi być W TOKU lub ZAKOŃCZONE', 'danger')
                return redirect(bezpieczny_powrot())
            data_planu_date = coerce_date(data_planu)
        except Exception as e:
            current_app.logger.error('zasyp_etap_manual_set failed: %s', e, exc_info=True)
            flash('❌ Błąd ręcznego zapisu etapu', 'danger')
            return redirect(bezpieczny_powrot())
        finally:
            try:
                conn.close()
            except Exception:
                pass

        ok, msg = ZasypEtapyService.set_etap_manual_times(
            plan_id=plan_id,
            linia=linia,
            data_planu=data_planu_date,
            etap=etap,
            czas_start_hhmm=czas_start_hhmm,
            czas_stop_hhmm=czas_stop_hhmm,
            user_login=session.get('login') or '',
            szarza_nr=szarza_nr_raw,
        )
        flash(('✅ ' if ok else '❌ ') + msg, 'success' if ok else 'danger')
        if ok:
            audit_log(
                'RĘCZNY zapis etapu Zasyp',
                f'plan_id={plan_id}, etap={etap}, linia={linia}, start={czas_start_hhmm}, stop={czas_stop_hhmm}, produkt={produkt}',
            )
        return redirect(bezpieczny_powrot())

    @production_bp.route('/zasyp_etap_reset', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'zarzad', 'pracownik', 'magazynier')
    def zasyp_etap_reset():
        """Reset etapu (kasuje zapis czasu START/STOP i podpisy)."""
        linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia_input).upper()
        plan_id_raw = request.form.get('plan_id')
        etap_raw = request.form.get('etap')
        szarza_nr_raw = _read_zasyp_nr_from_form()

        try:
            plan_id = int(plan_id_raw)
            etap = int(etap_raw)
        except Exception:
            flash('❌ Nieprawidłowe dane resetu etapu', 'danger')
            return redirect(bezpieczny_powrot())

        produkt = ''
        db_conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = db_conn.cursor()
            cursor.execute(f"SELECT produkt FROM {table_plan} WHERE id=%s", (plan_id,))
            row = cursor.fetchone()
            produkt = row[0] if row else ''
        finally:
            db_conn.close()

        ok, msg = ZasypEtapyService.reset_etap(plan_id=plan_id, linia=linia, etap=etap, szarza_nr=szarza_nr_raw)
        flash(('✅ ' if ok else '❌ ') + msg, 'success' if ok else 'danger')
        if ok:
            audit_log('RESET etapu Zasyp', f'plan_id={plan_id}, etap={etap}, linia={linia}, produkt={produkt}')
            sekcja = request.form.get('sekcja') or 'Zasyp'
            data_value = request.form.get('data_planu') or request.args.get('data') or str(date.today())
            restart_szarza_val = str(szarza_nr_raw or '').strip()
            from flask import current_app
            current_app.logger.info(f'[ZASYP-RESET] redirect: plan_id={plan_id}, etap={etap}, restart_szarza={restart_szarza_val}')
            return redirect(
                url_for(
                    'main.index',
                    sekcja=sekcja,
                    linia=linia,
                    data=data_value,
                    restart_plan=plan_id,
                    restart_etap=etap,
                    restart_szarza=restart_szarza_val,
                )
            )
        return redirect(bezpieczny_powrot())

    @production_bp.route('/zasyp_etap_delete', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'zarzad', 'pracownik', 'magazynier')
    def zasyp_etap_delete():
        """Całkowite usunięcie rekordu etapu (dla sub-etapów AGRO)."""
        linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia_input).upper()
        plan_id_raw = request.form.get('plan_id')
        etap_raw = request.form.get('etap')
        szarza_nr_raw = _read_zasyp_nr_from_form()

        try:
            plan_id = int(plan_id_raw)
            etap = int(etap_raw)
        except Exception:
            flash('❌ Nieprawidłowe dane usuwania etapu', 'danger')
            return redirect(bezpieczny_powrot())

        produkt = ''
        db_conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = db_conn.cursor()
            cursor.execute(f"SELECT produkt FROM {table_plan} WHERE id=%s", (plan_id,))
            row = cursor.fetchone()
            produkt = row[0] if row else ''
        finally:
            db_conn.close()

        ok, msg = ZasypEtapyService.delete_etap(plan_id=plan_id, linia=linia, etap=etap, szarza_nr=szarza_nr_raw)
        flash(('✅ ' if ok else '❌ ') + msg, 'success' if ok else 'danger')
        if ok:
            audit_log('USUWANIE etapu Zasyp', f'plan_id={plan_id}, etap={etap}, linia={linia}, produkt={produkt}')
        return redirect(bezpieczny_powrot())

    @production_bp.route('/zasyp_etapy_set_szarza', methods=['POST'])
    @login_required
    def zasyp_etapy_set_szarza():
        """Zapisz wielkość szarży (kg) dla aktywnego zlecenia Zasyp."""
        linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia_input).upper()
        plan_id_raw = request.form.get('plan_id')
        kg_raw = request.form.get('wielkosc_szarzy_kg')

        try:
            plan_id = int(plan_id_raw)
        except Exception:
            flash('❌ Nieprawidłowe dane', 'danger')
            return redirect(bezpieczny_powrot())

        kg = parse_float(kg_raw)
        if kg is None:
            flash('❌ Podaj poprawną wartość (kg)', 'danger')
            return redirect(bezpieczny_powrot())

        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT sekcja, status, data_planu, produkt FROM {table_plan} WHERE id=%s",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                flash('❌ Zlecenie nie znalezione', 'danger')
                return redirect(bezpieczny_powrot())
            sekcja, status, data_planu, produkt = row[0], row[1], row[2], row[3]
            if sekcja != 'Zasyp':
                flash('❌ To nie jest zlecenie Zasyp', 'danger')
                return redirect(bezpieczny_powrot())
            if status != 'w toku':
                flash('❌ Zlecenie musi być W TOKU', 'danger')
                return redirect(bezpieczny_powrot())
            data_planu_date = coerce_date(data_planu)
        except Exception as e:
            current_app.logger.error('zasyp_etapy_set_szarza failed: %s', e, exc_info=True)
            flash('❌ Błąd zapisu wielkości zasypu', 'danger')
            return redirect(bezpieczny_powrot())
        finally:
            try:
                conn.close()
            except Exception:
                pass

        ok, msg = ZasypEtapyService.set_wielkosc_szarzy(
            plan_id=plan_id,
            linia=linia,
            data_planu=data_planu_date,
            kg=kg,
            user_login=session.get('login') or '',
        )
        flash(('✅ ' if ok else '❌ ') + msg, 'success' if ok else 'danger')
        if ok:
            audit_log('Ustawił wielkość zasypu', f'plan_id={plan_id}, kg={kg}, linia={linia}, produkt={produkt}')
        return redirect(bezpieczny_powrot())

    @production_bp.route('/zasyp_etapy_podsumowanie', methods=['GET'])
    @roles_required('lider', 'admin', 'zarzad', 'laborant', 'laboratorium')
    def zasyp_etapy_podsumowanie():
        """Podsumowanie etapów Zasyp (per data) + metryki szarże/dosypki."""
        linia_input = request.args.get('linia') or session.get('selected_hall_view') or 'AGRO'
        linia = str(linia_input).upper()

        today = date.today()
        od_raw = request.args.get('od')
        do_raw = request.args.get('do')

        d_do = coerce_date(do_raw) if do_raw else today
        d_od = coerce_date(od_raw) if od_raw else (d_do - timedelta(days=14))
        if d_od > d_do:
            d_od, d_do = d_do, d_od

        rows = ZasypEtapyService.get_summary(d_od=d_od, d_do=d_do, linia=linia)
        zlecenia_rows = ZasypEtapyService.get_zlecenia_summary(d_od=d_od, d_do=d_do, linia=linia)

        return render_template(
            'zasyp_etapy_podsumowanie.html',
            linia=linia,
            d_od=d_od,
            d_do=d_do,
            rows=rows,
            zlecenia_rows=zlecenia_rows,
        )

    @production_bp.route('/zasyp_kolejny_pomiar/<int:plan_id>', methods=['POST'])
    @roles_required('pracownik', 'produkcja', 'lider', 'admin')
    def zasyp_kolejny_pomiar(plan_id):
        """Zwiększa licznik szarż dla zasyp_etapy i resetuje punkty kontrolne przed dodaniem fizycznej szarży z wagi."""
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        user_login = session.get('login') or 'unknown'
        ok, msg = ZasypEtapyService.kolejny_pomiar(plan_id, linia, user_login)

        flash(msg, 'success' if ok else 'danger')
        return redirect(bezpieczny_powrot())

    @production_bp.route('/zasyp_dodaj_pare_dosypki/<int:plan_id>', methods=['POST'])
    @roles_required('pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'magazynier', 'laborant', 'laboratorium')
    def zasyp_dodaj_pare_dosypki(plan_id):
        """Dodaje do bieżącej szarży AGRO parę etapów: dosypka + mieszanie po dosypce."""
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        szarza_nr_raw = _read_zasyp_nr_from_form()
        user_login = session.get('login') or 'unknown'

        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT sekcja, status, data_planu, produkt FROM {table_plan} WHERE id=%s",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                flash('❌ Zlecenie nie znalezione', 'danger')
                return redirect(bezpieczny_powrot())
            sekcja, status, data_planu, produkt = row[0], row[1], row[2], row[3]
            if sekcja != 'Zasyp':
                flash('❌ To nie jest zlecenie Zasyp', 'danger')
                return redirect(bezpieczny_powrot())
            if status != 'w toku':
                flash('❌ Zlecenie musi być W TOKU', 'danger')
                return redirect(bezpieczny_powrot())
            data_planu_date = coerce_date(data_planu)
        except Exception as e:
            current_app.logger.error('zasyp_dodaj_pare_dosypki failed: %s', e, exc_info=True)
            flash('❌ Błąd dodawania pary dosypki', 'danger')
            return redirect(bezpieczny_powrot())
        finally:
            try:
                conn.close()
            except Exception:
                pass

        ok, msg = ZasypEtapyService.add_agro_dosypka_pair(
            plan_id=plan_id,
            linia=linia,
            data_planu=data_planu_date,
            user_login=user_login,
            szarza_nr=szarza_nr_raw,
        )
        flash(('✅ ' if ok else '❌ ') + msg, 'success' if ok else 'danger')
        if ok:
            audit_log('DODANIE pary dosypki Zasyp', f'plan_id={plan_id}, linia={linia}, szarza_nr={szarza_nr_raw}, produkt={produkt}')
        return redirect(bezpieczny_powrot())

    @production_bp.route('/zasyp_usun_ostatnia_pare_dosypki/<int:plan_id>', methods=['POST'])
    @roles_required('pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'magazynier', 'laborant', 'laboratorium')
    def zasyp_usun_ostatnia_pare_dosypki(plan_id):
        """Usuwa ostatnio dodaną parę AGRO (39/49..31/41, a na końcu 3/4) dla bieżącej szarży."""
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        szarza_nr_raw = _read_zasyp_nr_from_form()

        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT sekcja, status, produkt FROM {table_plan} WHERE id=%s",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                flash('❌ Zlecenie nie znalezione', 'danger')
                return redirect(bezpieczny_powrot())
            sekcja, status, produkt = row[0], row[1], row[2]
            if sekcja != 'Zasyp':
                flash('❌ To nie jest zlecenie Zasyp', 'danger')
                return redirect(bezpieczny_powrot())
            if status != 'w toku':
                flash('❌ Zlecenie musi być W TOKU', 'danger')
                return redirect(bezpieczny_powrot())
        except Exception as e:
            current_app.logger.error('zasyp_usun_ostatnia_pare_dosypki failed: %s', e, exc_info=True)
            flash('❌ Błąd usuwania pary dosypki', 'danger')
            return redirect(bezpieczny_powrot())
        finally:
            try:
                conn.close()
            except Exception:
                pass

        ok, msg = ZasypEtapyService.remove_last_agro_dosypka_pair(
            plan_id=plan_id,
            linia=linia,
            szarza_nr=szarza_nr_raw,
        )
        flash(('✅ ' if ok else '❌ ') + msg, 'success' if ok else 'danger')
        if ok:
            audit_log('USUNIĘCIE ostatniej pary dosypki Zasyp', f'plan_id={plan_id}, linia={linia}, szarza_nr={szarza_nr_raw}, produkt={produkt}')
        return redirect(bezpieczny_powrot())

    @production_bp.route('/zasyp_usun_punkt_kontrolny_page/<int:plan_id>', methods=['GET'])
    @login_required
    @roles_required('pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'magazynier')
    def zasyp_usun_punkt_kontrolny_page(plan_id):
        """Render 2-step confirmation before removing a control point (szarza session)."""
        linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
        sekcja = request.args.get('sekcja') or 'Zasyp'
        szarza_nr = _read_zasyp_nr_from_args()
        data_planu = request.args.get('data') or request.args.get('data_planu') or ''
        return render_template(
            'confirm_delete_punkt_kontrolny.html',
            plan_id=plan_id,
            szarza_nr=szarza_nr,
            linia=linia,
            sekcja=sekcja,
            data_planu=data_planu,
        )

    @production_bp.route('/zasyp_usun_punkt_kontrolny/<int:plan_id>', methods=['POST'])
    @roles_required('pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'magazynier')
    def zasyp_usun_punkt_kontrolny(plan_id):
        """Usuwa cały punkt kontrolny (całą sesję szarży) dla wskazanego planu."""
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        szarza_nr_raw = _read_zasyp_nr_from_form()

        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT sekcja, status, produkt FROM {table_plan} WHERE id=%s",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                flash('❌ Zlecenie nie znalezione', 'danger')
                return redirect(bezpieczny_powrot())
            sekcja, status, produkt = row[0], row[1], row[2]
            if sekcja != 'Zasyp':
                flash('❌ To nie jest zlecenie Zasyp', 'danger')
                return redirect(bezpieczny_powrot())
            if status != 'w toku':
                flash('❌ Zlecenie musi być W TOKU', 'danger')
                return redirect(bezpieczny_powrot())
        except Exception as e:
            current_app.logger.error('zasyp_usun_punkt_kontrolny failed: %s', e, exc_info=True)
            flash('❌ Błąd usuwania punktu kontrolnego', 'danger')
            return redirect(bezpieczny_powrot())
        finally:
            try:
                conn.close()
            except Exception:
                pass

        ok, msg = ZasypEtapyService.remove_kontrolny_session(
            plan_id=plan_id,
            linia=linia,
            szarza_nr=szarza_nr_raw,
        )
        flash(('✅ ' if ok else '❌ ') + msg, 'success' if ok else 'danger')
        if ok:
            audit_log('USUNIĘCIE punktu kontrolnego Zasyp', f'plan_id={plan_id}, linia={linia}, szarza_nr={szarza_nr_raw}, produkt={produkt}')
        return redirect(bezpieczny_powrot())
