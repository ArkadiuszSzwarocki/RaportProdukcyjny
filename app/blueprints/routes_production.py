from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
import logging
import os
import glob
from datetime import date, datetime, timedelta
from typing import Optional
from app.db import get_db_connection, get_table_name, rollover_unfinished, sync_dosypka_notifications
from app.decorators import login_required, roles_required
from app.core.audit import audit_log
from app.services.zasyp_etapy_service import ZasypEtapyService

production_bp = Blueprint('production', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    # Try to get sekcja from query string first (URL parameters), then from form
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('main.index', sekcja=sekcja, data=data, linia=linia)


def _coerce_date(d: object) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str) and d:
        try:
            return date.fromisoformat(d[:10])
        except Exception:
            return date.today()
    return date.today()


def _parse_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        s = str(value).strip().replace(',', '.')
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _is_modal_sequence_error(msg: str) -> bool:
    s = str(msg or '').lower()
    return ('nie może' in s and ('start' in s or 'rozpocząć' in s)) or ('najwcześniej' in s)


def _flash_zasyp_result(ok: bool, msg: str) -> None:
    prefixed = ('✅ ' if ok else '❌ ') + str(msg or '')
    if ok:
        flash(prefixed, 'success')
        return
    if _is_modal_sequence_error(msg):
        flash(prefixed, 'modal_error')
    else:
        flash(prefixed, 'danger')


@production_bp.route('/zasyp_etap_start', methods=['POST'])
@login_required
def zasyp_etap_start():
    """START etapu 1-6 dla zlecenia Zasyp (na aktywnym zleceniu)."""
    linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia_input).upper()
    plan_id_raw = request.form.get('plan_id')
    etap_raw = request.form.get('etap')
    kg_raw = request.form.get('wielkosc_szarzy_kg')
    szarza_nr_raw = request.form.get('szarza_nr')
    auto_szarza_mode = str(request.form.get('auto_szarza_mode') or 'manual').strip().lower()

    try:
        plan_id = int(plan_id_raw)
        etap = int(etap_raw)
    except Exception:
        flash('❌ Nieprawidłowe dane START etapu', 'danger')
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
        data_planu_date = _coerce_date(data_planu)
    except Exception as e:
        current_app.logger.error('zasyp_etap_start failed: %s', e, exc_info=True)
        flash('❌ Błąd START etapu', 'danger')
        return redirect(bezpieczny_powrot())
    finally:
        try:
            conn.close()
        except Exception:
            pass

    kg_for_auto = None
    if etap == 1:
        kg = _parse_float(kg_raw)
        if kg is None:
            param = ZasypEtapyService.get_parametry(plan_id, linia)
            if param.get('wielkosc_szarzy_kg') is None:
                flash('❌ Podaj wielkość szarży przed startem Naważania', 'danger')
                return redirect(bezpieczny_powrot())
            try:
                kg_for_auto = float(param.get('wielkosc_szarzy_kg'))
            except Exception:
                kg_for_auto = None
        else:
            ok_kg, msg_kg = ZasypEtapyService.set_wielkosc_szarzy(
                plan_id=plan_id,
                linia=linia,
                data_planu=data_planu_date,
                kg=kg,
                user_login=session.get('login') or '',
            )
            if not ok_kg:
                flash(f'❌ {msg_kg}', 'danger')
                return redirect(bezpieczny_powrot())
            kg_for_auto = kg

    ok, msg = ZasypEtapyService.start_etap(
        plan_id=plan_id,
        linia=linia,
        data_planu=data_planu_date,
        etap=etap,
        user_login=session.get('login') or '',
        szarza_nr=szarza_nr_raw,
    )

    # AUTO SZARZA mode: when Naważanie starts, add one szarża automatically
    if ok and etap == 1 and auto_szarza_mode == 'auto' and 'zapisany' in str(msg).lower():
        try:
            auto_kg = float(kg_for_auto) if kg_for_auto is not None else None
        except Exception:
            auto_kg = None

        if auto_kg and auto_kg > 0:
            auto_conn = None
            try:
                auto_conn = get_db_connection()
                auto_cursor = auto_conn.cursor()
                table_szarze = get_table_name('szarze', linia)
                table_plan = get_table_name('plan_produkcji', linia)
                table_dosypki = get_table_name('dosypki', linia)

                auto_cursor.execute(f"SELECT MAX(nr_szarzy) FROM {table_szarze} WHERE plan_id=%s", (plan_id,))
                row = auto_cursor.fetchone()
                next_nr = (row[0] if row and row[0] else 0) + 1

                now = datetime.now()
                godzina = now.strftime('%H:%M:%S')
                pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None

                auto_cursor.execute(
                    f"INSERT INTO {table_szarze} (plan_id, waga, data_dodania, godzina, pracownik_id, status, nr_szarzy) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (plan_id, auto_kg, now, godzina, pracownik_id, 'zarejestowana', next_nr),
                )

                auto_cursor.execute(
                    f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                    f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                    f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                    f"WHERE id = %s",
                    (plan_id, plan_id, plan_id),
                )

                auto_conn.commit()
                msg = f"{msg}; AUTO SZARŻA: dodano nr {next_nr} ({auto_kg:g} kg)"
                audit_log('AUTO dodał szarżę', f'zlecenie_id={plan_id}, produkt={produkt}, tonaz={auto_kg:g} kg, nr={next_nr}, linia={linia}')
            except Exception as auto_err:
                try:
                    if auto_conn:
                        auto_conn.rollback()
                except Exception:
                    pass
                msg = f"{msg}; AUTO SZARŻA: błąd dodania ({auto_err})"
            finally:
                try:
                    if auto_conn:
                        auto_conn.close()
                except Exception:
                    pass

    _flash_zasyp_result(ok, msg)
    if ok:
        audit_log('START etapu Zasyp', f'plan_id={plan_id}, etap={etap}, linia={linia}, produkt={produkt}')
    return redirect(bezpieczny_powrot())


@production_bp.route('/zasyp_etap_stop', methods=['POST'])
@login_required
def zasyp_etap_stop():
    """STOP etapu 1-6 dla zlecenia Zasyp."""
    linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia_input).upper()
    plan_id_raw = request.form.get('plan_id')
    etap_raw = request.form.get('etap')
    szarza_nr_raw = request.form.get('szarza_nr')
    next_action = str(request.form.get('next_action') or '').strip().lower()

    try:
        plan_id = int(plan_id_raw)
        etap = int(etap_raw)
    except Exception:
        flash('❌ Nieprawidłowe dane STOP etapu', 'danger')
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
        data_planu_date = _coerce_date(data_planu)
    except Exception as e:
        current_app.logger.error('zasyp_etap_stop failed: %s', e, exc_info=True)
        flash('❌ Błąd STOP etapu', 'danger')
        return redirect(bezpieczny_powrot())
    finally:
        try:
            conn.close()
        except Exception:
            pass

    ok, msg = ZasypEtapyService.stop_etap(
        plan_id=plan_id,
        linia=linia,
        etap=etap,
        user_login=session.get('login') or '',
        szarza_nr=szarza_nr_raw,
    )

    if ok:
        next_etap = None
        wants_new_point_after_empty = False
        if linia == 'AGRO':
            # AGRO flow: 1 -> 2, then PAUZA (no auto-start for 2). Dosypka starts after etap 3 stop.
            if etap == 1:
                next_etap = 2
            elif etap == 2 or etap == 4 or str(etap).startswith('4'):
                if next_action in ('oprozniamy', 'oprozniamy_end_today', 'oprozniamy_new_point'):
                    next_etap = 5
                    wants_new_point_after_empty = next_action == 'oprozniamy_new_point'
                elif next_action == 'add_pair':
                    pair_ok, pair_msg = ZasypEtapyService.add_agro_dosypka_pair(
                        plan_id=plan_id,
                        linia=linia,
                        data_planu=data_planu_date,
                        user_login=session.get('login') or '',
                        szarza_nr=szarza_nr_raw,
                    )
                    if pair_ok:
                        pair_start = None
                        cleaned = str(pair_msg).replace('/', ' ').replace(',', ' ')
                        for token in cleaned.split():
                            try:
                                pair_start = int(token)
                                break
                            except Exception:
                                continue
                        if pair_start is not None:
                            next_etap = pair_start
                            msg = f"{msg}; {pair_msg}"
                        else:
                            msg = f"{msg}; {pair_msg}; brak automatycznego START (nierozpoznana para)"
                    else:
                        msg = f"{msg}; {pair_msg}"
            elif etap == 3:
                next_etap = 4
            elif str(etap).startswith('3') and etap != 3:
                # 31 -> 41, 32 -> 42, 310 -> 410, etc.
                next_etap = int('4' + str(etap)[1:])
        elif etap < 6:
            next_etap = etap + 1

        if next_etap is not None:
            next_ok, next_msg = ZasypEtapyService.start_etap(
                plan_id=plan_id,
                linia=linia,
                data_planu=data_planu_date,
                etap=next_etap,
                user_login=session.get('login') or '',
                szarza_nr=szarza_nr_raw,
            )
            if next_ok:
                msg = f'{msg}; automatycznie uruchomiono etap {next_etap}'
                audit_log('START etapu Zasyp', f'plan_id={plan_id}, etap={next_etap}, linia={linia}, produkt={produkt}')

                if wants_new_point_after_empty:
                    km_ok, km_msg = ZasypEtapyService.kolejny_pomiar(plan_id, linia, session.get('login') or '')
                    if km_ok:
                        new_szarza_nr = None
                        for token in str(km_msg).replace('#', ' ').split():
                            try:
                                new_szarza_nr = int(token)
                                break
                            except Exception:
                                continue

                        if new_szarza_nr is not None:
                            st_ok, st_msg = ZasypEtapyService.start_etap(
                                plan_id=plan_id,
                                linia=linia,
                                data_planu=data_planu_date,
                                etap=1,
                                user_login=session.get('login') or '',
                                szarza_nr=new_szarza_nr,
                            )
                            if st_ok:
                                msg = f"{msg}; {km_msg}; automatycznie uruchomiono Naważanie dla nowego punktu"
                                audit_log('START etapu Zasyp', f'plan_id={plan_id}, etap=1, linia={linia}, produkt={produkt}, szarza_nr={new_szarza_nr}')

                                # New-point flow should also create production batch entry for the new szarza.
                                param = ZasypEtapyService.get_parametry(plan_id, linia)
                                kg_auto_new = param.get('wielkosc_szarzy_kg')
                                try:
                                    kg_auto_new = float(kg_auto_new) if kg_auto_new is not None else None
                                except Exception:
                                    kg_auto_new = None

                                if kg_auto_new and kg_auto_new > 0:
                                    auto_conn = None
                                    try:
                                        auto_conn = get_db_connection()
                                        auto_cursor = auto_conn.cursor()
                                        table_szarze = get_table_name('szarze', linia)
                                        table_plan = get_table_name('plan_produkcji', linia)
                                        table_dosypki = get_table_name('dosypki', linia)

                                        now = datetime.now()
                                        godzina = now.strftime('%H:%M:%S')
                                        pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None

                                        auto_cursor.execute(
                                            f"INSERT INTO {table_szarze} (plan_id, waga, data_dodania, godzina, pracownik_id, status, nr_szarzy) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                            (plan_id, kg_auto_new, now, godzina, pracownik_id, 'zarejestowana', new_szarza_nr),
                                        )

                                        auto_cursor.execute(
                                            f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                                            f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                                            f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                                            f"WHERE id = %s",
                                            (plan_id, plan_id, plan_id),
                                        )

                                        auto_conn.commit()
                                        msg = f"{msg}; dodano szarżę #{new_szarza_nr} ({kg_auto_new:g} kg)"
                                        audit_log('AUTO dodał szarżę', f'zlecenie_id={plan_id}, produkt={produkt}, tonaz={kg_auto_new:g} kg, nr={new_szarza_nr}, linia={linia}')
                                    except Exception as auto_new_err:
                                        try:
                                            if auto_conn:
                                                auto_conn.rollback()
                                        except Exception:
                                            pass
                                        msg = f"{msg}; nie udało się dodać szarży dla nowego punktu: {auto_new_err}"
                                    finally:
                                        try:
                                            if auto_conn:
                                                auto_conn.close()
                                        except Exception:
                                            pass
                                else:
                                    msg = f"{msg}; brak wielkości szarży - nie dodano rekordu szarży"
                            else:
                                msg = f"{msg}; {km_msg}; nie udało się uruchomić Naważania: {st_msg}"
                        else:
                            msg = f"{msg}; {km_msg}; nie rozpoznano numeru nowej szarży"
                    else:
                        msg = f"{msg}; nie udało się utworzyć nowego punktu: {km_msg}"
            else:
                msg = f'{msg}; etap {next_etap}: {next_msg}'

    _flash_zasyp_result(ok, msg)
    if ok:
        audit_log('STOP etapu Zasyp', f'plan_id={plan_id}, etap={etap}, linia={linia}, produkt={produkt}')
    return redirect(bezpieczny_powrot())


@production_bp.route('/zasyp_etap_manual_set', methods=['POST'])
@login_required
@roles_required('lider', 'admin', 'zarzad')
def zasyp_etap_manual_set():
    """Ręczny zapis czasu START/STOP etapu (HH:MM) dla zlecenia Zasyp."""
    linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia_input).upper()

    plan_id_raw = request.form.get('plan_id')
    etap_raw = request.form.get('etap')
    szarza_nr_raw = request.form.get('szarza_nr')
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
        data_planu_date = _coerce_date(data_planu)
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
    szarza_nr_raw = request.form.get('szarza_nr')

    try:
        plan_id = int(plan_id_raw)
        etap = int(etap_raw)
    except Exception:
        flash('❌ Nieprawidłowe dane resetu etapu', 'danger')
        return redirect(bezpieczny_powrot())

    # Validate that plan exists and is Zasyp (defensive)
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
    szarza_nr_raw = request.form.get('szarza_nr')

    try:
        plan_id = int(plan_id_raw)
        etap = int(etap_raw)
    except Exception:
        flash('❌ Nieprawidłowe dane usuwania etapu', 'danger')
        return redirect(bezpieczny_powrot())

    # Validate
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

    kg = _parse_float(kg_raw)
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
        data_planu_date = _coerce_date(data_planu)
    except Exception as e:
        current_app.logger.error('zasyp_etapy_set_szarza failed: %s', e, exc_info=True)
        flash('❌ Błąd zapisu wielkości szarży', 'danger')
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
        audit_log('Ustawił wielkość szarży', f'plan_id={plan_id}, kg={kg}, linia={linia}, produkt={produkt}')
    return redirect(bezpieczny_powrot())


@production_bp.route('/zasyp_etapy_podsumowanie', methods=['GET'])
@roles_required('lider', 'admin', 'zarzad')
def zasyp_etapy_podsumowanie():
    """Podsumowanie etapów Zasyp (per data) + metryki szarże/dosypki."""
    linia_input = request.args.get('linia') or session.get('selected_hall_view') or 'AGRO'
    linia = str(linia_input).upper()

    today = date.today()
    od_raw = request.args.get('od')
    do_raw = request.args.get('do')

    d_do = _coerce_date(do_raw) if do_raw else today
    d_od = _coerce_date(od_raw) if od_raw else (d_do - timedelta(days=14))
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


@production_bp.route('/start_zlecenie/<int:id>', methods=['POST'])
@login_required
def start_zlecenie(id):
    """Rozpocznij wykonywanie zlecenia (zmiana statusu na 'w toku')
    
    Workowanie może startować niezależnie - Zasyp to przygotowanie wsadu,
    Workowanie workuje z bufora. Jeśli na Zasyp jest inne zlecenie - pokaż info.
    """
    conn = get_db_connection()
    try:
        linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia_input).upper()
        table_plan = get_table_name('plan_produkcji', linia)
        cursor = conn.cursor()
        cursor.execute(f"SELECT produkt, tonaz, sekcja, data_planu, typ_produkcji, status, COALESCE(tonaz_rzeczywisty, 0) FROM {table_plan} WHERE id=%s", (id,))
        z = cursor.fetchone()
        
        warning_info = None  # Informacja o tym co dzieje się na Zasyp
        
        if z:
            produkt, tonaz, sekcja, data_planu, typ, status_obecny, tonaz_rzeczywisty_zasyp = z
            
            # INFO ONLY (nie blokuje): jeśli na Workowanie, sprawdzić co dzieje się na Zasyp
            if sekcja == 'Workowanie':
                cursor.execute(
                    f"SELECT id, produkt FROM {table_plan} "
                    "WHERE sekcja='Zasyp' AND status='w toku' AND DATE(data_planu)=%s LIMIT 1",
                    (data_planu,)
                )
                active_on_zasyp = cursor.fetchone()
                
                if active_on_zasyp and active_on_zasyp[0] != id:
                    # Inne zlecenie aktywne na Zasyp - informuj ale nie blokuj
                    warning_info = {
                        'message': f"Na Zasyp trwa zlecenie: {active_on_zasyp[1]}",
                        'zasyp_order_id': active_on_zasyp[0],
                        'zasyp_order_name': active_on_zasyp[1]
                    }
            
            if sekcja == 'Workowanie':
                    # Allow planners/admins to bypass queue restriction
                    role = session.get('rola', '')
                    if role in ('planista', 'admin'):
                        current_app.logger.debug(f'[KOLEJKA] bypass for role={role} plan_id={id} produkt={produkt}')
                    else:
                        try:
                            # Log context for debugging
                            table_bufor = get_table_name('bufor', linia)
                            current_app.logger.debug(f'[KOLEJKA] start_zlecenie check id={id} produkt="{produkt}" data_planu={data_planu}')
                            
                            # FIFO Logic: find the absolute minimum queue in the buffer among all products 
                            # that are currently planned on Workowanie today.
                            cursor.execute(f"""
                                SELECT MIN(b.kolejka) 
                                FROM {table_bufor} b
                                WHERE DATE(b.data_planu) = %s AND b.status = 'aktywny'
                                  AND EXISTS (
                                      SELECT 1 FROM {table_plan} w
                                      WHERE w.sekcja = 'Workowanie' AND w.status IN ('zaplanowane', 'w toku')
                                        AND w.produkt = b.produkt AND w.data_planu = b.data_planu
                                  )
                            """, (data_planu,))
                            min_q_row = cursor.fetchone()
                            global_min_queue = min_q_row[0] if min_q_row else None
                            
                            if global_min_queue is not None:
                                # Check if THIS product has that global_min_queue
                                cursor.execute(f"""
                                    SELECT kolejka FROM {table_bufor}
                                    WHERE produkt = %s AND DATE(data_planu) = %s AND status = 'aktywny'
                                """, (produkt, data_planu))
                                my_q_row = cursor.fetchone()
                                my_q = my_q_row[0] if my_q_row else None
                                
                                if my_q is not None and my_q > global_min_queue:
                                    # Pobierz nazwę produktu, który powinien wejść pierwszy
                                    cursor.execute(f"SELECT produkt FROM {table_bufor} WHERE kolejka = %s AND status = 'aktywny' AND DATE(data_planu) = %s LIMIT 1", (global_min_queue, data_planu))
                                    earliest_produkt = cursor.fetchone()[0]
                                    
                                    flash(f"❌ Kolejkowanie Workowanie: W buforze znajduje się produkt przewidziany wcześniej do startu: {earliest_produkt}. Zalecana kolejność FIFO.", 'error')
                                    return redirect(bezpieczny_powrot())
                        except Exception as e:
                            current_app.logger.exception('[KOLEJKA] FIFO check failed: %s', e)

            # Zawsze wykonaj START - Workowanie pracuje niezależnie z bufora
            if status_obecny != 'w toku':
                cursor.execute(f"UPDATE {table_plan} SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'", (sekcja,))
                cursor.execute(f"UPDATE {table_plan} SET status='w toku', real_start=NOW(), real_stop=NULL WHERE id=%s", (id,))
                current_app.logger.info('Uruchomiono zlecenie ID=%s, produkt=%s przez %s', id, produkt, session.get('login'))
                audit_log('Uruchomił zlecenie', f'ID={id}, produkt={produkt}, sekcja={sekcja}')
                flash(f"✅ Uruchomiono: {produkt}", 'success')
                try:
                    status_logger = logging.getLogger('status_changes')
                    status_logger.info(f"action=start_zlecenie plan_id={id} old={status_obecny} new=w_toku user={session.get('login')} endpoint={request.path} caller=production.start_zlecenie sekcja={sekcja}")
                except Exception:
                    pass

                # Jeśli jest warning info - dodaj do flash message
                if warning_info:
                    flash(f"ℹ️ {warning_info['message']}", 'info')

                # Gdy Zasyp startuje — natychmiast dodaj do bufora i przelicz kolejkę
                if sekcja == 'Zasyp':
                    try:
                        from app.db import refresh_bufor_queue
                        conn.commit()  # commit real_start przed refresh
                        refresh_bufor_queue(linia=linia)
                        current_app.logger.info('[BUFOR] refresh po starcie Zasypu id=%s produkt=%s', id, produkt)
                    except Exception as _rb_err:
                        current_app.logger.warning('[BUFOR] refresh_bufor_queue po starcie Zasypu failed: %s', _rb_err)
            
        conn.commit()
        # commit done — ensure status change logged if not already
        try:
            pass
        except Exception:
            pass
    except Exception as e:
        current_app.logger.error(f"Error starting order {id}: {e}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        flash(f"❌ Błąd uruchamiania zlecenia", 'danger')
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    return redirect(bezpieczny_powrot())


@production_bp.route('/koniec_zlecenie/<int:id>', methods=['POST'])
@login_required
def koniec_zlecenie(id):
    """Zakończ wykonywanie zlecenia"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        final_tonaz = request.form.get('final_tonaz')
        wyjasnienie = request.form.get('wyjasnienie')
        uszkodzone_worki = request.form.get('uszkodzone_worki')
        sekcja = request.form.get('sekcja')
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        table_plan = get_table_name('plan_produkcji', linia)
        
        rzeczywista_waga = 0
        if final_tonaz:
            try:
                rzeczywista_waga = int(float(final_tonaz.replace(',', '.')))
            except Exception:
                pass

        sql = f"UPDATE {table_plan} SET status='zakonczone', real_stop=NOW()"
        params = []
        if rzeczywista_waga > 0:
            sql += ", tonaz_rzeczywisty=%s"
            params.append(rzeczywista_waga)
        if wyjasnienie:
            sql += ", wyjasnienie_rozbieznosci=%s"
            params.append(wyjasnienie)
        if uszkodzone_worki and sekcja == 'Workowanie':
            try:
                uszkodzone_count = int(uszkodzone_worki)
                sql += ", uszkodzone_worki=%s"
                params.append(uszkodzone_count)
            except (ValueError, TypeError):
                pass
        sql += " WHERE id=%s"
        params.append(id)
        cursor.execute(sql, tuple(params))
        
        # Zasyp i Workowanie działają NIEZALEŻNIE, ale tonaz workowania powinien równać się tonaz_rzeczywisty zasypu
        if sekcja == 'Zasyp' and rzeczywista_waga > 0:
            try:
                # Szukaj powiązanego workowania (przez zasyp_id lub produkt+data w AGRO)
                if str(linia).upper() == 'AGRO':
                    cursor.execute(
                        f"UPDATE {table_plan} SET tonaz = %s WHERE produkt = %s AND data_planu = %s AND sekcja = 'Workowanie' AND status != 'zakonczone'",
                        (rzeczywista_waga, produkt, data_planu)
                    )
                else:
                    cursor.execute(
                        f"UPDATE {table_plan} SET tonaz = %s WHERE zasyp_id = %s AND sekcja = 'Workowanie' AND status != 'zakonczone'",
                        (rzeczywista_waga, id)
                    )
                current_app.logger.info('[SYNC] Zaktualizowano tonaz Workowania na %s kg po zakończeniu Zasypu id=%s', rzeczywista_waga, id)
            except Exception as _sync_err:
                current_app.logger.warning('[SYNC] Błąd synchronizacji tonaz Workowania: %s', _sync_err)

        conn.commit()
        current_app.logger.info('Zakończono zlecenie ID=%s przez %s', id, session.get('login'))
        audit_log('Zakończył zlecenie', f'ID={id}, tonaz_rz={rzeczywista_waga} kg')
        try:
            status_logger = logging.getLogger('status_changes')
            status_logger.info(f"action=koniec_zlecenie plan_id={id} new=zakonczone user={session.get('login')} endpoint={request.path} caller=production.koniec_zlecenie sekcja={sekcja}")
        except Exception:
            pass

        # Domknij aktywny etap Zasyp jeśli zlecenie Zasyp i jest otwarty etap
        if sekcja == 'Zasyp':
            try:
                ZasypEtapyService.stop_any_running_etap(
                    plan_id=id,
                    linia=linia,
                    user_login=session.get('login') or 'system',
                )
            except Exception as e:
                current_app.logger.warning('stop_any_running_etap failed for id=%s: %s', id, e)

        # WAŻNE: Odśwież bufor teraz, żeby kolejka się przesuniała
        try:
            from app.db import refresh_bufor_queue
            refresh_bufor_queue(conn, linia=linia)
        except Exception as e:
            current_app.logger.warning(f'Failed to refresh bufor after koniec_zlecenie: {e}')
    except Exception as e:
        current_app.logger.error(f"Error completing order {id}: {e}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        flash(f"❌ Błąd zakończenia zlecenia", 'danger')
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    return redirect(bezpieczny_powrot())


@production_bp.route('/zapisz_wyjasnienie/<int:id>', methods=['POST'])
@login_required
def zapisz_wyjasnienie(id):
    """Zapisz wyjaśnienie rozbieżności"""
    conn = get_db_connection()
    try:
        linia = request.args.get('linia') or request.form.get('linia', 'PSD')
        table_plan = get_table_name('plan_produkcji', linia)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {table_plan} SET wyjasnienie_rozbieznosci=%s WHERE id=%s", (request.form.get('wyjasnienie'), id))
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"Error saving explanation for {id}: {e}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        flash(f"❌ Błąd zapisania wyjaśnienia", 'danger')
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    return redirect(bezpieczny_powrot())


@production_bp.route('/koniec_zlecenie_page/<int:id>', methods=['GET'])
@login_required
def koniec_zlecenie_page(id):
    """Widok potwierdzenia zakończenia zlecenia (analogicznie do dawnego modalu)."""
    linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia_input).upper()
    sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Zasyp'))
    produkt = None
    tonaz_rzeczywisty = None
    conn = get_db_connection()
    try:
        table_plan = get_table_name('plan_produkcji', linia)
        cursor = conn.cursor()
        cursor.execute(f"SELECT produkt, tonaz_rzeczywisty FROM {table_plan} WHERE id=%s", (id,))
        row = cursor.fetchone()
        if row:
            produkt, tonaz_rzeczywisty = row[0], row[1]
    except Exception as e:
        current_app.logger.error(f'Failed to fetch plan {id} for koniec_zlecenie_page: {e}', exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return render_template('koniec_zlecenie.html', id=id, sekcja=sekcja, produkt=produkt, tonaz=tonaz_rzeczywisty)


@production_bp.route('/test-pobierz-raport', methods=['GET'])
@login_required
def api_test_pobierz_raport():
    """Test endpoint: return most recent file from raporty/ directory as attachment"""
    try:
        rap_dir = os.path.join(current_app.root_path, 'raporty')
        if not os.path.isdir(rap_dir):
            current_app.logger.warning(f'Reports directory not found: {rap_dir}')
            return jsonify({'error': 'raporty directory not found'}), 404
        files = glob.glob(os.path.join(rap_dir, '*'))
        if not files:
            current_app.logger.warning('No reports available in raporty directory')
            return jsonify({'error': 'no reports available'}), 404
        latest = max(files, key=os.path.getmtime)
        return send_file(latest, as_attachment=True, download_name=os.path.basename(latest))
    except Exception as e:
        current_app.logger.error(f'Failed to send report: {e}', exc_info=True)
        return jsonify({'error': 'failed to send file'}), 500


@production_bp.route('/szarza_page/<int:plan_id>', methods=['GET'])
@login_required
def szarza_page(plan_id):
    """Strona dodawania nowej szarży dla konkretnego planu."""
    linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia_input).upper()
    current_app.logger.debug(f'[SZARZA_PAGE] Called with plan_id={plan_id}')
    
    conn = get_db_connection()
    try:
        table_plan = get_table_name('plan_produkcji', linia)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT produkt, typ_produkcji FROM {table_plan} WHERE id=%s AND sekcja='Zasyp'",
            (plan_id,)
        )
        plan = cursor.fetchone()
        if not plan:
            current_app.logger.warning(f'[SZARZA_PAGE] Plan {plan_id} not found')
            flash('Plan nie znaleziony', 'error')
            return redirect('/')
        
        produkt, typ_produkcji = plan[0], plan[1]
        
        # Calculate next szarża number (MAX + 1)
        table_szarze = get_table_name('szarze', linia)
        cursor.execute(f"SELECT MAX(nr_szarzy) FROM {table_szarze} WHERE plan_id=%s", (plan_id,))
        max_nr = cursor.fetchone()[0]
        next_nr = (max_nr or 0) + 1
        
        current_app.logger.debug(f'[SZARZA_PAGE] Rendering form for plan_id={plan_id}, produkt={produkt}, typ={typ_produkcji}, linia={linia}, next_nr={next_nr}')
        return render_template('dodaj_palete_popup.html', 
                     plan_id=plan_id, 
                     sekcja='Zasyp',
                     produkt=produkt,
                     typ=typ_produkcji,
                     linia=linia,
                     next_nr_szarzy=next_nr)
    except Exception as e:
        current_app.logger.error(f'[SZARZA_PAGE] Error in szarza_page: {e}', exc_info=True)
        flash('Błąd pobierania danych planu', 'error')
        return redirect('/')
    finally:
        try:
            conn.close()
        except Exception:
            pass


@production_bp.route('/zasyp_kolejny_pomiar/<int:plan_id>', methods=['POST'])
@roles_required('pracownik', 'produkcja', 'lider', 'admin')
def zasyp_kolejny_pomiar(plan_id):
    """Zwiększa licznik szarż dla zasyp_etapy i resetuje punkty kontrolne przed dodaniem fizycznej szarży z wagi."""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    auto_szarza_mode = str(request.form.get('auto_szarza_mode') or 'manual').strip().lower()
    user_login = session.get('login') or 'unknown'
    ok, msg = ZasypEtapyService.kolejny_pomiar(plan_id, linia, user_login)

    # Optional auto-create batch for the freshly opened control point/session.
    if ok and auto_szarza_mode == 'auto':
        conn = None
        try:
            next_szarza_nr = None
            if '#' in msg:
                try:
                    next_szarza_nr = int(msg.split('#', 1)[1].split()[0])
                except Exception:
                    next_szarza_nr = None

            if next_szarza_nr is not None:
                table_plan = get_table_name('plan_produkcji', linia)
                table_szarze = get_table_name('szarze', linia)

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT sekcja, status, data_planu, produkt FROM {table_plan} WHERE id=%s",
                    (plan_id,),
                )
                row = cursor.fetchone()
                if row and row[0] == 'Zasyp' and row[1] == 'w toku':
                    data_planu_date = _coerce_date(row[2])
                    produkt = row[3]
                    param = ZasypEtapyService.get_parametry(plan_id, linia)
                    kg_auto = _parse_float(param.get('wielkosc_szarzy_kg'))
                    if kg_auto and kg_auto > 0:
                        cursor.execute(
                            f"SELECT id FROM {table_szarze} WHERE plan_id=%s AND nr_szarzy=%s AND status='zarejestowana' LIMIT 1",
                            (plan_id, next_szarza_nr),
                        )
                        exists_row = cursor.fetchone()
                        if not exists_row:
                            now_dt = datetime.now()
                            cursor.execute(
                                f"""
                                INSERT INTO {table_szarze}
                                (plan_id, produkt, nr_szarzy, waga, godzina, data_dodania, pracownik_id, status, typ_produkcji, data_planu, potwierdzone_workowanie)
                                VALUES (%s, %s, %s, %s, %s, %s, NULL, 'zarejestowana', 'N/A', %s, 0)
                                """,
                                (
                                    plan_id,
                                    produkt,
                                    next_szarza_nr,
                                    kg_auto,
                                    now_dt.strftime('%H:%M:%S'),
                                    now_dt,
                                    data_planu_date,
                                ),
                            )
                            cursor.execute(
                                f"UPDATE {table_plan} SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id=%s",
                                (kg_auto, plan_id),
                            )
                            conn.commit()
                            msg = f"{msg} + auto-szarża {kg_auto:.1f} kg"
        except Exception as e:
            current_app.logger.warning('Auto batch after kolejny_pomiar failed: %s', e, exc_info=True)
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    flash(msg, 'success' if ok else 'danger')
    return redirect(bezpieczny_powrot())


@production_bp.route('/zasyp_dodaj_pare_dosypki/<int:plan_id>', methods=['POST'])
@roles_required('pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'magazynier')
def zasyp_dodaj_pare_dosypki(plan_id):
    """Dodaje do bieżącej szarży AGRO parę etapów: dosypka + mieszanie po dosypce."""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    szarza_nr_raw = request.form.get('szarza_nr')
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
        data_planu_date = _coerce_date(data_planu)
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
@roles_required('pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'magazynier')
def zasyp_usun_ostatnia_pare_dosypki(plan_id):
    """Usuwa ostatnio dodaną parę AGRO (39/49..31/41, a na końcu 3/4) dla bieżącej szarży."""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    szarza_nr_raw = request.form.get('szarza_nr')

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


@production_bp.route('/zasyp_usun_punkt_kontrolny/<int:plan_id>', methods=['POST'])
@roles_required('pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'magazynier')
def zasyp_usun_punkt_kontrolny(plan_id):
    """Usuwa cały punkt kontrolny (całą sesję szarży) dla wskazanego planu."""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    szarza_nr_raw = request.form.get('szarza_nr')

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

# --- ZWOLNIENIE MIESZALNIKA ---
import time
_mieszalnik_zwolnienia = {'AGRO': 0, 'PSD': 0}

@production_bp.route('/api/zasyp/zwolnij_mieszalnik', methods=['POST'])
@roles_required('laborant', 'admin', 'zarzad', 'lider')
def api_zwolnij_mieszalnik():
    """Signalyze operatorom ze zasyp jest zwolniony"""
    linia = request.form.get('linia') or request.json.get('linia') or 'AGRO'
    linia = linia.upper()
    _mieszalnik_zwolnienia[linia] = time.time()
    return jsonify({"success": True, "timestamp": _mieszalnik_zwolnienia[linia]})

@production_bp.route('/api/zasyp/poll_zwolnienie', methods=['GET'])
@login_required
def api_poll_zwolnienie():
    """Skrypt w dashboard.html pyta co X sekund czy był sygnał."""
    role = str(session.get('rola') or '').lower()
    if role in ['laborant', 'laboratorium', 'magazyn', 'magazynier', 'planista']:
        return jsonify({"new_zwolnienie": False})

    linia = request.args.get('linia', 'AGRO').upper()
    try:
        last_seen = float(request.args.get('last_seen', 0))
    except Exception:
        last_seen = 0.0
    current = _mieszalnik_zwolnienia.get(linia, 0.0)
    if current > last_seen:
        return jsonify({"new_zwolnienie": True, "timestamp": current})
    return jsonify({"new_zwolnienie": False})


@production_bp.route('/wyjasnij_page/<int:id>', methods=['GET'])
@login_required
def wyjasnij_page(id):
    """Render form to submit explanation via zapisz_wyjasnienie"""
    # If this endpoint is requested directly (not via AJAX/data-slide),
    # rendering the raw fragment results in a bare page. Redirect back
    # to a safe location to avoid showing an unstyled fragment.
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return redirect(bezpieczny_powrot())
    return render_template('wyjasnij.html', id=id)


@production_bp.route('/manual_rollover', methods=['POST'])
@roles_required('lider', 'admin')
def manual_rollover():
    """Manually rollover unfinished jobs from one date to another"""
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
    """Render slide-over for managing obsada (workers on shift) for a sekcja"""
    sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Workowanie'))
    linia = request.args.get('linia', request.form.get('linia')) or session.get('selected_hall_view') or 'PSD'
    # allow optional date parameter (YYYY-MM-DD) to view/modify obsada for other dates
    date_str = request.args.get('date') or request.form.get('date')
    try:
        qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        qdate = date.today()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # all obsada entries for given date (grouped by sekcja)
        cursor.execute("SELECT oz.sekcja, oz.id, p.imie_nazwisko, p.id FROM obsada_zmiany oz JOIN pracownicy p ON oz.pracownik_id = p.id WHERE oz.data_wpisu = %s ORDER BY oz.sekcja, p.imie_nazwisko", (qdate,))
        rows = cursor.fetchall()
        obsady_map = {}
        for r in rows:
            sekc, oz_id, name, pracownik_id = r[0], r[1], r[2], r[3]
            obsady_map.setdefault(sekc, []).append((oz_id, name, pracownik_id))
        # available employees: exclude those already assigned for that date (any sekcja),
        # those marked absent in obecnosc, and those on approved leave (wnioski_wolne)
        cursor.execute(
            "SELECT id, imie_nazwisko FROM pracownicy "
            "WHERE id NOT IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu=%s) "
            "AND id NOT IN (SELECT pracownik_id FROM obecnosc WHERE data_wpisu=%s AND typ IN ('Nieobecnosc','Urlop','L4','Opieka')) "
            "AND id NOT IN (SELECT pracownik_id FROM wnioski_wolne WHERE status='approved' AND data_od <= %s AND data_do >= %s) "
            "AND id NOT IN (SELECT pracownik_id FROM uzytkownicy WHERE rola IN ('admin','zarzad') AND pracownik_id IS NOT NULL) "
            "ORDER BY imie_nazwisko",
            (qdate, qdate, qdate, qdate)
        )
        wszyscy = cursor.fetchall()
        # pełna lista pracowników (dla wyboru liderów) - tylko liderzy
        cursor.execute("SELECT p.id, p.imie_nazwisko FROM pracownicy p JOIN uzytkownicy u ON p.id = u.pracownik_id WHERE u.rola='lider' ORDER BY p.imie_nazwisko")
        all_pracownicy = cursor.fetchall()
        # pobierz liderów dla tej daty (jeśli istnieją)
        cursor.execute("SELECT lider_psd_id, lider_agro_id FROM obsada_liderzy WHERE data_wpisu=%s", (qdate,))
        lider_row = cursor.fetchone()
        lider_psd_id = lider_row[0] if lider_row else None
        lider_agro_id = lider_row[1] if lider_row else None
    finally:
        try: conn.close()
        except Exception: pass

    # If requested via AJAX or the explicit API route, return only the fragment
    try:
        is_ajax = request.headers.get('X-Requested-With', '') == 'XMLHttpRequest' or request.path.startswith('/api/') or request.args.get('fragment') == 'true'
    except Exception:
        is_ajax = False

    if is_ajax:
        return render_template('obsada_fragment.html', sekcja=sekcja, linia=linia, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'), qdate=qdate, lider_psd_id=lider_psd_id, lider_agro_id=lider_agro_id, all_pracownicy=all_pracownicy)

    return render_template('obsada.html', sekcja=sekcja, linia=linia, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'), qdate=qdate, lider_psd_id=lider_psd_id, lider_agro_id=lider_agro_id, all_pracownicy=all_pracownicy)


@production_bp.route('/dosypka_page/<int:plan_id>', methods=['GET'])
@roles_required('laborant', 'planista', 'admin')
def dosypka_page(plan_id):
    """Render form to add up to 4 dosypki for an active Zasyp plan."""
    conn = get_db_connection()
    try:
        linia = request.args.get('linia') or request.form.get('linia', 'PSD')
        table_plan = get_table_name('plan_produkcji', linia)
        table_dosypki = get_table_name('dosypki', linia)
        cursor = conn.cursor()
        cursor.execute(f"SELECT produkt, typ_produkcji, status FROM {table_plan} WHERE id=%s AND sekcja='Zasyp'", (plan_id,))
        plan = cursor.fetchone()
        if not plan:
            flash('Plan nie znaleziony', 'error')
            return redirect('/')
        
        produkt, typ_produkcji, status = plan[0], plan[1], plan[2]
        # Only allow adding dosypki to active orders
        if status != 'w toku':
            flash('Dosypki można dodawać tylko do aktywnego zlecenia (status "w toku")', 'warning')
            return redirect(bezpieczny_powrot())
        
        szarza_id = request.args.get('szarza_id')
        szarza_id_int = None
        if szarza_id:
            try:
                szarza_id_int = int(szarza_id)
            except ValueError:
                szarza_id_int = None

        if szarza_id_int:
            cursor.execute(
                f"""
                SELECT id, nazwa, kg, data_zlecenia, COALESCE(anulowana, 0), anulowal_login, data_anulowania
                FROM {table_dosypki}
                WHERE plan_id=%s AND szarza_id=%s
                ORDER BY COALESCE(anulowana, 0) ASC, data_zlecenia DESC
                """,
                (plan_id, szarza_id_int)
            )
        else:
            cursor.execute(
                f"""
                SELECT id, nazwa, kg, data_zlecenia, COALESCE(anulowana, 0), anulowal_login, data_anulowania
                FROM {table_dosypki}
                WHERE plan_id=%s
                ORDER BY COALESCE(anulowana, 0) ASC, data_zlecenia DESC
                """,
                (plan_id,)
            )

        existing_dosypki = [
            {
                'id': row[0],
                'nazwa': row[1],
                'kg': float(row[2]) if row[2] is not None else 0,
                'data_zlecenia': str(row[3]) if row[3] is not None else '',
                'anulowana': bool(row[4]),
                'anulowal_login': row[5],
                'data_anulowania': str(row[6]) if row[6] is not None else '',
            }
            for row in cursor.fetchall()
        ]

        return render_template(
            'dodaj_dosypke_popup.html',
            plan_id=plan_id,
            produkt=produkt,
            typ=typ_produkcji,
            szarza_id=szarza_id,
            existing_dosypki=existing_dosypki,
            linia=linia
        )
    except Exception as e:
        current_app.logger.error(f'Error in dosypka_page: {e}', exc_info=True)
        flash('Błąd pobierania danych planu', 'error')
        return redirect('/')
    finally:
        try:
            conn.close()
        except Exception:
            pass


@production_bp.route('/dodaj_dosypke', methods=['POST'])
@roles_required('laborant', 'admin')
def dodaj_dosypke():
    """Handle POST from dosypka form and insert rows into `dosypki` table."""
    plan_id = request.form.get('plan_id')
    if not plan_id:
        flash('Brak identyfikatora zlecenia', 'error')
        return redirect(bezpieczny_powrot())
    try:
        plan_id = int(plan_id)
    except Exception:
        flash('Nieprawidłowe ID zlecenia', 'error')
        return redirect(bezpieczny_powrot())

    szarza_id = request.form.get('szarza_id')
    if szarza_id:
        try:
            szarza_id = int(szarza_id)
        except ValueError:
            szarza_id = None

    # Check if "brak dosypki" (no supplement) was selected
    brak_dosypki = request.form.get('brak_dosypki') == '1'

    # Collect up to 10 pairs of name/kg from the form
    entries = []
    for i in range(1, 11):
        name = (request.form.get(f'nazwa_{i}') or '').strip()
        kg_raw = request.form.get(f'kg_{i}')
        if name and kg_raw:
            try:
                kg = float(str(kg_raw).replace(',', '.'))
            except Exception:
                kg = 0
            if kg > 0:
                entries.append((name, kg))

    # If "brak dosypki" is selected, create special entry
    if brak_dosypki:
        entries = [('Brak dosypki', 0)]
    elif not entries:
        flash('Brak poprawnych pozycji dosypki do zapisania', 'warning')
        return redirect(bezpieczny_powrot())

    conn = get_db_connection()
    try:
        linia = request.args.get('linia') or request.form.get('linia', 'PSD')
        table_plan = get_table_name('plan_produkcji', linia)
        table_dosypki = get_table_name('dosypki', linia)
        cursor = conn.cursor()
        # Validate plan exists and is active
        cursor.execute(
            f"SELECT id, produkt, data_planu, status FROM {table_plan} WHERE id=%s AND sekcja='Zasyp'",
            (plan_id,)
        )
        r = cursor.fetchone()
        if not r or r[3] != 'w toku':
            flash('Dosypki można dodawać tylko do aktywnego zlecenia (status "w toku")', 'warning')
            return redirect(bezpieczny_powrot())

        pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None
        created_by_user_id = session.get('user_id') if 'user_id' in session else None
        for name, kg in entries:
            cursor.execute(f"INSERT INTO {table_dosypki} (plan_id, szarza_id, nazwa, kg, pracownik_id, potwierdzone) VALUES (%s, %s, %s, %s, %s, 0)", (plan_id, szarza_id, name, kg, pracownik_id))
            try:
                # Log individual dosypka creation to audit log
                audit_log('Dodał dosypkę', f'nazwa={name}, kg={kg}, plan_id={plan_id}')
            except Exception:
                # don't break on audit logging failure
                current_app.logger.debug('audit_log failed for dosypka insert', exc_info=True)
        sync_dosypka_notifications(
            plan_id=plan_id,
            author_name=session.get('imie_nazwisko') or session.get('login'),
            created_by_user_id=created_by_user_id,
            conn=conn,
            cursor=cursor,
            linia=linia
        )

        conn.commit()

        # Sygnał dla dashboardu (dźwięk/odświeżenie) - dosypka dodana
        _mieszalnik_zwolnienia[linia.upper()] = time.time()

        if brak_dosypki:
            flash('Oznaczono, że brak dosypki dla tego zlecenia.', 'success')
        else:
            flash(f'Zapisano {len(entries)} pozycji dosypki.', 'success')
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.error(f'Failed to insert dosypki: {e}', exc_info=True)
        flash('Błąd zapisu dosypki', 'error')
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return redirect(bezpieczny_powrot())


@production_bp.route('/potwierdz_dosypke/<int:dosypka_id>', methods=['POST'])
@roles_required('pracownik', 'produkcja', 'lider', 'admin')
def potwierdz_dosypke(dosypka_id):
    """Operator potwierdza odczytanie dosypki - mark as confirmed."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    table_plan = get_table_name('plan_produkcji', linia)
    table_dosypki = get_table_name('dosypki', linia)
    table_szarze = get_table_name('szarze', linia)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT id FROM {table_dosypki} WHERE id=%s AND potwierdzone=0 AND COALESCE(anulowana, 0)=0", (dosypka_id,))
        r = cursor.fetchone()
        if not r:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Pozycja nieznaleziona lub już potwierdzona'}), 404
            flash('Pozycja nieznaleziona lub już potwierdzona', 'warning')
            return redirect(bezpieczny_powrot())

        pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None
        
        # First, get the plan_id from dosypka to update tonaz_rzeczywisty
        cursor.execute(f"SELECT plan_id FROM {table_dosypki} WHERE id=%s", (dosypka_id,))
        dosypka_row = cursor.fetchone()
        plan_id = dosypka_row[0] if dosypka_row else None
        
        cursor.execute(f"UPDATE {table_dosypki} SET potwierdzone=1, potwierdzil_pracownik_id=%s, data_potwierdzenia=NOW() WHERE id=%s", (pracownik_id, dosypka_id))
        
        # Synchronize plan's tonaz_rzeczywisty = SUM(szarże) + SUM(dosypki potwierdzone)
        if plan_id:
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                f"WHERE id = %s",
                (plan_id, plan_id, plan_id)
            )
            sync_dosypka_notifications(
                plan_id=plan_id,
                author_name=session.get('imie_nazwisko') or session.get('login'),
                created_by_user_id=session.get('user_id'),
                conn=conn,
                cursor=cursor,
                linia=linia
            )
        
        conn.commit()
        if is_ajax:
            return jsonify({'success': True, 'message': 'Potwierdzono dosypkę.', 'plan_id': plan_id})
        flash('Potwierdzono dosypkę.', 'success')
        try:
            audit_log('Potwierdził dosypkę', f'id={dosypka_id}, plan_id={plan_id}')
        except Exception:
            current_app.logger.debug('audit_log failed for dosypka confirm', exc_info=True)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.error(f'Failed to confirm dosypka: {e}', exc_info=True)
        if is_ajax:
            return jsonify({'success': False, 'message': 'Błąd podczas potwierdzania'}), 500
        flash('Błąd podczas potwierdzania', 'error')
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return redirect(bezpieczny_powrot())


@production_bp.route('/anuluj_dosypke/<int:dosypka_id>', methods=['POST'])
@roles_required('laborant', 'admin')
def anuluj_dosypke(dosypka_id):
    """Mark dosypka as anulowana instead of deleting it."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    table_dosypki = get_table_name('dosypki', linia)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, plan_id FROM {table_dosypki} WHERE id=%s AND potwierdzone=0 AND COALESCE(anulowana, 0)=0",
            (dosypka_id,)
        )
        row = cursor.fetchone()
        if not row:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Pozycja nie istnieje, została już potwierdzona albo anulowana'}), 404
            flash('Pozycja nie istnieje, została już potwierdzona albo anulowana', 'warning')
            return redirect(bezpieczny_powrot())

        anulowal_login = session.get('login') or session.get('imie_nazwisko') or 'unknown'
        cursor.execute(
            f"UPDATE {table_dosypki} SET anulowana=1, data_anulowania=NOW(), anulowal_login=%s WHERE id=%s",
            (anulowal_login, dosypka_id)
        )
        sync_dosypka_notifications(
            plan_id=row[1],
            author_name=session.get('imie_nazwisko') or session.get('login'),
            created_by_user_id=session.get('user_id'),
            conn=conn,
            cursor=cursor,
            linia=linia
        )
        conn.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Dosypka została anulowana.',
                'plan_id': row[1],
                'anulowal_login': anulowal_login,
            })
        flash('Dosypka została anulowana.', 'success')
        try:
            audit_log('Anulował dosypkę', f'id={dosypka_id}, plan_id={row[1]}, anulowal={anulowal_login}')
        except Exception:
            current_app.logger.debug('audit_log failed for dosypka cancel', exc_info=True)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.error(f'Failed to cancel dosypka: {e}', exc_info=True)
        if is_ajax:
            return jsonify({'success': False, 'message': 'Błąd podczas anulowania'}), 500
        flash('Błąd podczas anulowania', 'error')
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return redirect(bezpieczny_powrot())


@production_bp.route('/api/dosypki', methods=['GET'])
@roles_required('laborant', 'pracownik', 'produkcja', 'lider', 'admin')
def api_dosypki():
    """Return JSON of active unconfirmed dosypki for operators."""
    current_app.logger.debug(f"[api_dosypki] Endpoint reached by user role: {session.get('rola')}")
    plan_id = request.args.get('plan_id', None)
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    table_dosypki = get_table_name('dosypki', linia)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if plan_id:
            cursor.execute(
                f"""
                SELECT id, plan_id, nazwa, kg, data_zlecenia,
                       COALESCE(anulowana, 0), anulowal_login, data_anulowania
                FROM {table_dosypki}
                WHERE potwierdzone = 0 AND COALESCE(anulowana, 0) = 0 AND plan_id = %s
                ORDER BY data_zlecenia ASC
                """,
                (plan_id,)
            )
        else:
            cursor.execute(
                f"""
                SELECT id, plan_id, nazwa, kg, data_zlecenia,
                       COALESCE(anulowana, 0), anulowal_login, data_anulowania
                FROM {table_dosypki}
                  WHERE potwierdzone = 0 AND COALESCE(anulowana, 0) = 0
                  ORDER BY data_zlecenia ASC
                """
            )
        rows = cursor.fetchall()
        role = session.get('rola', '')
        result = []
        # Roles that should see the detailed `nazwa` because they need to execute the dosypka
        visible_roles = ('laborant', 'pracownik', 'produkcja', 'lider', 'admin')
        for r in rows:
            if role in visible_roles:
                nazwa = r[2]
            else:
                nazwa = None
            result.append({
                'id': r[0],
                'plan_id': r[1],
                'nazwa': nazwa,
                'kg': float(r[3]),
                'data_zlecenia': str(r[4]),
                'anulowana': bool(r[5]),
                'anulowal_login': r[6],
                'data_anulowania': str(r[7]) if r[7] is not None else '',
            })
        return jsonify({'success': True, 'dosypki': result})
    except Exception as e:
        current_app.logger.error(f'api/dosypki failed: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@production_bp.route('/dosypki_list', methods=['GET'])
@roles_required('laborant', 'pracownik', 'produkcja', 'lider', 'admin')
def dosypki_list():
    """Render slide-over page with list of active unconfirmed dosypki for operators."""
    # Accept optional plan_id to filter dosypki for a specific zlecenie
    plan_id = request.args.get('plan_id', None)
    linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
    # Fetch unconfirmed dosypki server-side so fragment shows data even if client JS doesn't run
    from app.db import list_unconfirmed_dosypki
    rows = list_unconfirmed_dosypki(linia=linia)
    role = session.get('rola', '')
    visible_roles = ('laborant', 'pracownik', 'produkcja', 'lider', 'admin')
    dosypki = []
    for r in rows:
        # Filter by plan_id if provided
        if plan_id and str(r[1]) != str(plan_id):
            continue
        if role in visible_roles:
            nazwa = r[2]
        else:
            nazwa = None
        dosypki.append({'id': r[0], 'plan_id': r[1], 'nazwa': nazwa, 'kg': float(r[3]) if r[3] is not None else None, 'data_zlecenia': str(r[4]) if r[4] is not None else ''})
    # Always return the fragment regardless of X-Requested-With
    # because the quick popup JS via fetch expects just the fragment HTML.
    return render_template('dosypki_list.html', dosypki=dosypki, plan_id=plan_id, rola=role, linia=linia)



@production_bp.route('/agro/mix_rozliczenie', methods=['GET'])
@login_required
@roles_required('lider', 'admin')
def agro_mix_rozliczenie_page():
    """Render modal content for MIX settlement (AGRO only)."""
    data_planu = request.args.get('data', str(date.today()))
    linia = 'AGRO'
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        table_plan = get_table_name('plan_produkcji', linia)
        
        # 1. Find the LAST finished Zasyp order
        cursor.execute(f"""
            SELECT id, produkt, data_planu 
            FROM {table_plan} 
            WHERE sekcja='Zasyp' AND status='zakonczone' AND data_planu <= %s
            ORDER BY real_stop DESC LIMIT 1
        """, (data_planu,))
        last_plan = cursor.fetchone()
        
        # 2. Find the NEXT planned or running Zasyp order (current session)
        cursor.execute(f"""
            SELECT id, produkt, data_planu, status
            FROM {table_plan} 
            WHERE sekcja='Zasyp' AND status IN ('zaplanowane','w toku') AND data_planu >= %s
            ORDER BY case when status='w toku' then 1 else 2 end, data_planu ASC, kolejnosc ASC LIMIT 1
        """, (data_planu,))
        next_plan = cursor.fetchone()
        
        # If no next plan is found, we cannot create a MIX settlement
        if not next_plan:
            return render_template('agro_mix_rozliczenie_error.html', message="Nie można stworzyć MIX - brak zaplanowanego lub uruchomionego zlecenia Zasyp.")
        
        # 3. Get history of MIX for today
        cursor.execute("""
            SELECT * FROM agro_mix_rozliczenie 
            WHERE data_planu = %s 
            ORDER BY created_at DESC
        """, (data_planu,))
        history = cursor.fetchall()
        
        return render_template('agro_mix_rozliczenie.html', 
                               last_plan=last_plan, 
                               next_plan=next_plan,
                               history=history,
                               data_planu=data_planu)
    except Exception as e:
        current_app.logger.error(f"Error in agro_mix_rozliczenie_page: {e}")
        return "Błąd ładowania danych MIX", 500
    finally:
        conn.close()

@production_bp.route('/agro/mix_rozliczenie/add', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def agro_mix_rozliczenie_add():
    """Add a MIX settlement record."""
    data_planu = request.form.get('data_planu', str(date.today()))
    poprz_id = request.form.get('poprz_id')
    nast_id = request.form.get('nast_id')
    kategoria = request.form.get('kategoria', 'DO_LNU')
    ilosc_workow = request.form.get('ilosc_workow')
    waga_kg = request.form.get('waga_kg')
    
    if not nast_id or not ilosc_workow or not waga_kg:
        flash("Błąd: Wszystkie wymagane pola muszą być wypełnione.", "danger")
        return redirect(bezpieczny_powrot())
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agro_mix_rozliczenie (data_planu, poprzednie_zlecenie_id, nastepne_zlecenie_id, kategoria, nazwa_mix, ilosc_workow, waga_kg, autor_login)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (data_planu, poprz_id, nast_id, kategoria, kategoria.replace('_', ' '), ilosc_workow, waga_kg, session.get('login')))
        conn.commit()
        conn.close()
        flash("Rozliczenie MIX dodane pomyślnie.", "success")
    except Exception as e:
        current_app.logger.error(f"Error adding MIX settlement: {e}")
        flash(f"Błąd zapisu: {str(e)}", "danger")
        
    return redirect(bezpieczny_powrot())

@production_bp.route('/agro/mix_rozliczenie/print/<int:mix_id>')
@login_required
def agro_mix_rozliczenie_print(mix_id):
    """Printable view for a single MIX record."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM agro_mix_rozliczenie WHERE id=%s", (mix_id,))
        mix = cursor.fetchone()
        if not mix:
            return "Nie znaleziono rekordu MIX", 404
            
        # Get plan info
        table_plan = get_table_name('plan_produkcji', 'AGRO')
        poprz_prod = "---"
        if mix['poprzednie_zlecenie_id']:
            cursor.execute(f"SELECT produkt FROM {table_plan} WHERE id=%s", (mix['poprzednie_zlecenie_id'],))
            row = cursor.fetchone()
            if row: poprz_prod = row['produkt']

        nast_prod = "---"
        if mix['nastepne_zlecenie_id']:
            cursor.execute(f"SELECT produkt FROM {table_plan} WHERE id=%s", (mix['nastepne_zlecenie_id'],))
            row = cursor.fetchone()
            if row: nast_prod = row['produkt']

        return render_template('agro_mix_print.html', mix=mix, poprz_prod=poprz_prod, nast_prod=nast_prod)
    finally:
        conn.close()

@production_bp.route('/agro/mix/inventory', methods=['GET'])
@login_required
@roles_required('lider', 'admin')
def agro_mix_inventory():
    """List available MIXes for consumption (Ajax popup)."""
    selected_plan_id = request.args.get('selected_plan_id', type=int)
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch available MIXes along with their origin product
        table_plan = get_table_name('plan_produkcji', 'AGRO')
        cursor.execute(f"""
            SELECT m.*, p.produkt as origin_product
            FROM agro_mix_rozliczenie m
            LEFT JOIN {table_plan} p ON m.poprzednie_zlecenie_id = p.id
                  WHERE m.status='DOSTEPNY' 
            ORDER BY m.created_at DESC
        """)
        available_mixes = cursor.fetchall()
        
        # Only fetch ACTIVE (running) orders for ZASYP stage
        cursor.execute(f"SELECT id, produkt, nazwa_zlecenia FROM {table_plan} WHERE status = 'w toku' AND sekcja = 'Zasyp' ORDER BY kolejnosc ASC")
        active_plans = cursor.fetchall()
        
        conn.close()
        return render_template('agro_mix_inventory.html', 
                               mixes=available_mixes, 
                               plans=active_plans, 
                               selected_id=selected_plan_id)
    except Exception as e:
        current_app.logger.error(f"Error loading MIX inventory: {e}")
        return "Błąd ładowania zasobnika", 500

@production_bp.route('/agro/mix_consume', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def agro_mix_consume():
    """Consume an available MIX into a Zasyp plan."""
    mix_id = request.form.get('mix_id')
    plan_id = request.form.get('plan_id')
    
    if not mix_id or not plan_id:
        flash("Błąd: Nieprawidłowe dane konsumpcji MIX", "danger")
        return redirect(bezpieczny_powrot())
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch MIX weight
        cursor.execute("SELECT waga_kg, kategoria FROM agro_mix_rozliczenie WHERE id=%s AND status='DOSTEPNY'", (mix_id,))
        mix = cursor.fetchone()
        if not mix:
            conn.close()
            flash("Błąd: Ten MIX nie jest już dostępny", "danger")
            return redirect(bezpieczny_powrot())
        
        # 2. Update MIX status and consumption timestamp
        cursor.execute("""
            UPDATE agro_mix_rozliczenie 
            SET status='ZUZYTY', zuzyte_w_id=%s, zuzyte_kiedy=NOW()
            WHERE id=%s
        """, (plan_id, mix_id))
        
        # 3. INCREASE Zasyp actual tonnage
        table_plan = get_table_name('plan_produkcji', 'AGRO')
        cursor.execute(f"""
            UPDATE {table_plan} 
            SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s 
            WHERE id=%s
        """, (mix['waga_kg'], plan_id))
        
        conn.commit()
        conn.close()
        flash(f"Dodano {mix['waga_kg']} kg MIXu ({mix['kategoria'].replace('_',' ')}) do zlecenia.", "success")
    except Exception as e:
        current_app.logger.error(f"Error consuming MIX: {e}")
        flash(f"Błąd: {str(e)}", "danger")
        
    return redirect(bezpieczny_powrot())
