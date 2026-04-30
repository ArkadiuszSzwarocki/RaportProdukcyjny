from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
import logging
import os
import glob
import uuid
from datetime import date, datetime, timedelta
from typing import Optional
from app.db import get_db_connection, get_table_name, rollover_unfinished, sync_dosypka_notifications
from app.decorators import login_required, roles_required
from app.core.audit import audit_log
from app.services.zasyp_etapy_service import ZasypEtapyService
from app.services.zasyp_start_notification_service import (
    add_start_event,
    build_sound_url_if_exists,
    build_start_tts_text,
    get_latest_start_event,
)
from app.services.zasyp_mieszanie_notification_service import (
    add_mieszanie_event,
    build_mieszanie_tts_text,
    get_latest_mieszanie_event,
    is_mieszanie_after_dosypka,
)

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


def _get_allowed_dosypka_materials(cursor, linia: str) -> list[str]:
    """Load allowed raw material names for dosypka from available warehouse tables."""
    linia_upper = str(linia or '').upper()
    # Dosypki on PSD should use the same material dictionary as AGRO.
    if linia_upper in {'AGRO', 'PSD'}:
        candidate_tables = [
            'magazyn_agro_slownik_surowce',
            'magazyn_agro_surowce',
            'magazyn_agro_ruch',
            'mom_pozycje',
        ]
    else:
        candidate_tables = [
            'magazyn_slownik_surowce',
            'magazyn_surowce',
            'magazyn_ruch',
            'mom_pozycje',
        ]
    candidate_columns = ['nazwa', 'surowiec_nazwa', 'nazwa_surowca', 'surowiec']

    values_map = {}
    for table_name in candidate_tables:
        cursor.execute(
            "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1",
            (table_name,)
        )
        if not cursor.fetchone():
            continue

        picked_col = None
        for col_name in candidate_columns:
            cursor.execute(
                "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s LIMIT 1",
                (table_name, col_name)
            )
            if cursor.fetchone():
                picked_col = col_name
                break

        if not picked_col:
            continue

        try:
            cursor.execute(
                f"SELECT DISTINCT {picked_col} FROM {table_name} WHERE {picked_col} IS NOT NULL AND TRIM({picked_col}) <> '' ORDER BY {picked_col} ASC"
            )
            for row in cursor.fetchall():
                raw_val = row[0] if isinstance(row, (list, tuple)) else None
                name = str(raw_val or '').strip()
                if name:
                    values_map.setdefault(name.lower(), name)
        except Exception:
            current_app.logger.debug('dosypka source read failed: %s.%s', table_name, picked_col, exc_info=True)

    return sorted(values_map.values(), key=lambda s: s.lower())


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


def _insert_szarza_compatible(cursor, table_szarze: str, *, plan_id: int, nr_szarzy: int, waga: float,
                              godzina: str, data_dodania: datetime, pracownik_id: Optional[int],
                              produkt: Optional[str] = None, typ_produkcji: Optional[str] = None,
                              data_planu: Optional[date] = None) -> None:
    """Insert szarza row using only columns that exist in the target table schema."""
    cursor.execute(f"SHOW COLUMNS FROM {table_szarze}")
    existing_cols = {row[0] for row in cursor.fetchall() or []}

    values_map = {
        'plan_id': plan_id,
        'produkt': produkt,
        'nr_szarzy': nr_szarzy,
        'waga': waga,
        'godzina': godzina,
        'data_dodania': data_dodania,
        'pracownik_id': pracownik_id,
        'status': 'zarejestowana',
        'typ_produkcji': typ_produkcji or 'N/A',
        'data_planu': data_planu,
        'potwierdzone_workowanie': 0,
    }

    ordered_cols = [
        'plan_id', 'produkt', 'nr_szarzy', 'waga', 'godzina', 'data_dodania',
        'pracownik_id', 'status', 'typ_produkcji', 'data_planu', 'potwierdzone_workowanie'
    ]
    insert_cols = [col for col in ordered_cols if col in existing_cols]
    insert_vals = [values_map[col] for col in insert_cols]
    placeholders = ', '.join(['%s'] * len(insert_cols))
    cols_sql = ', '.join(insert_cols)
    cursor.execute(
        f"INSERT INTO {table_szarze} ({cols_sql}) VALUES ({placeholders})",
        tuple(insert_vals),
    )


def _notify_laboratory_stage_start(linia: str, plan_id: int, etap: int, produkt: str) -> None:
    """Emit laboratorium notification for start of selected Zasyp stages (1=Naważanie, 2=Mieszanie)."""
    try:
        etap_i = int(etap)
    except Exception:
        return
    if etap_i not in (1, 2, 4) and not (40 < etap_i < 50):
        return

    # Try to resolve current szarza number (if any)
    szarza_nr = None
    conn2 = None
    try:
        conn2 = get_db_connection()
        cur2 = conn2.cursor()
        table_szarze = get_table_name('szarze', linia)
        cur2.execute(f"SELECT MAX(nr_szarzy) FROM {table_szarze} WHERE plan_id=%s", (plan_id,))
        r = cur2.fetchone()
        if r and r[0] is not None:
            try:
                szarza_nr = int(r[0])
            except Exception:
                szarza_nr = None
    except Exception:
        szarza_nr = None
    finally:
        try:
            if conn2:
                conn2.close()
        except Exception:
            pass

    try:
        ts_ms = int(time.time() * 1000)
        uniq = uuid.uuid4().hex[:8]
        is_nawazanie = etap_i == 1
        filename_prefix = 'zasyp_start' if is_nawazanie else 'zasyp_mieszanie_start'
        filename = f"{filename_prefix}_{plan_id}_{ts_ms}_{uniq}.mp3"
        text = build_start_tts_text(produkt, szarza_nr) if is_nawazanie else build_mieszanie_tts_text(produkt, szarza_nr, etap_i)

        try:
            generate_tts_async(text, filename)
        except Exception:
            current_app.logger.exception('Failed to kick off TTS for zasyp stage notification')
            filename = None

        try:
            if is_nawazanie:
                add_start_event(linia, plan_id, produkt, szarza_nr, filename)
            else:
                add_mieszanie_event(linia, plan_id, etap_i, produkt, szarza_nr, filename)
        except Exception:
            current_app.logger.exception('Failed to register zasyp stage notification event')
    except Exception:
        current_app.logger.exception('Unexpected error while preparing zasyp stage notification event')


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
    role = str(session.get('rola') or '').lower()
    default_auto_mode = 'auto' if role in ['operator', 'pracownik', 'produkcja', 'lider'] else 'manual'
    auto_szarza_mode = str(request.form.get('auto_szarza_mode') or default_auto_mode).strip().lower()

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
            f"SELECT sekcja, status, data_planu, produkt, typ_produkcji FROM {table_plan} WHERE id=%s",
            (plan_id,),
        )
        row = cursor.fetchone()
        if not row:
            flash('❌ Zlecenie nie znalezione', 'danger')
            return redirect(bezpieczny_powrot())
        sekcja, status, data_planu, produkt = row[0], row[1], row[2], row[3]
        typ_produkcji = row[4] if len(row) > 4 else None
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

                _insert_szarza_compatible(
                    auto_cursor,
                    table_szarze,
                    plan_id=plan_id,
                    nr_szarzy=next_nr,
                    waga=auto_kg,
                    godzina=godzina,
                    data_dodania=now,
                    pracownik_id=pracownik_id,
                    produkt=produkt,
                    typ_produkcji=typ_produkcji,
                    data_planu=data_planu_date,
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
        # If stage start requires laboratorium notification, register event + optional TTS file.
        try:
            _notify_laboratory_stage_start(linia, plan_id, etap, produkt)
        except Exception:
            current_app.logger.exception('Failed post-start zasyp notification')
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
    role = str(session.get('rola') or '').lower()
    default_auto_mode = 'auto' if role in ['operator', 'pracownik', 'produkcja', 'lider'] else 'manual'
    auto_szarza_mode = str(request.form.get('auto_szarza_mode') or default_auto_mode).strip().lower()
    auto_szarza_enabled = auto_szarza_mode == 'auto'

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
            f"SELECT sekcja, status, data_planu, produkt, typ_produkcji FROM {table_plan} WHERE id=%s",
            (plan_id,),
        )
        row = cursor.fetchone()
        if not row:
            flash('❌ Zlecenie nie znalezione', 'danger')
            return redirect(bezpieczny_powrot())
        sekcja, status, data_planu, produkt = row[0], row[1], row[2], row[3]
        typ_produkcji = row[4] if len(row) > 4 else None
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
                if next_action not in ('add_pair', 'oprozniamy', 'oprozniamy_end_today', 'oprozniamy_new_point'):
                    msg = f"{msg}; brak wyboru w oknie decyzji - nie uruchomiono kolejnego etapu"
                elif next_action in ('oprozniamy', 'oprozniamy_end_today', 'oprozniamy_new_point'):
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
                try:
                    _notify_laboratory_stage_start(linia, plan_id, next_etap, produkt)
                except Exception:
                    current_app.logger.exception('Failed post-auto-start zasyp notification')

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
                                try:
                                    _notify_laboratory_stage_start(linia, plan_id, 1, produkt)
                                except Exception:
                                    current_app.logger.exception('Failed post-auto-start (new point) zasyp notification')

                                if auto_szarza_enabled or wants_new_point_after_empty:
                                    # New-point flow must keep etap 1 start and szarza row in sync.
                                    param = ZasypEtapyService.get_parametry(plan_id, linia)
                                    kg_auto_new = param.get('wielkosc_szarzy_kg')
                                    try:
                                        kg_auto_new = float(kg_auto_new) if kg_auto_new is not None else None
                                    except Exception:
                                        kg_auto_new = None

                                    auto_conn = None
                                    try:
                                        auto_conn = get_db_connection()
                                        auto_cursor = auto_conn.cursor()
                                        table_szarze = get_table_name('szarze', linia)
                                        table_plan = get_table_name('plan_produkcji', linia)
                                        table_dosypki = get_table_name('dosypki', linia)

                                        # Fallback: when configured batch size is missing, reuse the latest batch weight for this plan.
                                        if not (kg_auto_new and kg_auto_new > 0):
                                            auto_cursor.execute(
                                                f"SELECT waga FROM {table_szarze} WHERE plan_id=%s ORDER BY COALESCE(nr_szarzy, 0) DESC, data_dodania DESC, id DESC LIMIT 1",
                                                (plan_id,),
                                            )
                                            row_last = auto_cursor.fetchone()
                                            try:
                                                last_waga = row_last[0] if row_last else None
                                            except Exception:
                                                last_waga = None
                                            try:
                                                kg_auto_new = float(last_waga) if last_waga is not None else None
                                            except Exception:
                                                kg_auto_new = None

                                        if kg_auto_new and kg_auto_new > 0:
                                            now = datetime.now()
                                            godzina = now.strftime('%H:%M:%S')
                                            pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None

                                            auto_cursor.execute(
                                                f"SELECT id FROM {table_szarze} WHERE plan_id=%s AND nr_szarzy=%s AND status='zarejestowana' LIMIT 1",
                                                (plan_id, new_szarza_nr),
                                            )
                                            exists_row = auto_cursor.fetchone()

                                            if not exists_row:
                                                _insert_szarza_compatible(
                                                    auto_cursor,
                                                    table_szarze,
                                                    plan_id=plan_id,
                                                    nr_szarzy=new_szarza_nr,
                                                    waga=kg_auto_new,
                                                    godzina=godzina,
                                                    data_dodania=now,
                                                    pracownik_id=pracownik_id,
                                                    produkt=produkt,
                                                    typ_produkcji=typ_produkcji,
                                                    data_planu=data_planu_date,
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
                                            else:
                                                msg = f"{msg}; szarża #{new_szarza_nr} już istniała"
                                        else:
                                            msg = f"{msg}; tryb AUTO SZARŻA aktywny, ale brak wielkości szarży - nie dodano rekordu"
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
                                msg = f"{msg}; {km_msg}; nie udało się uruchomić Naważania: {st_msg}"
                        else:
                            msg = f"{msg}; {km_msg}; nie rozpoznano numeru nowej szarży"
                    else:
                        msg = f"{msg}; nie udało się utworzyć nowego punktu: {km_msg}"
            else:
                next_msg_s = str(next_msg or '')
                if linia == 'AGRO' and next_etap == 5 and 'nie może się rozpocząć przed zakończeniem' in next_msg_s.lower():
                    msg = f"{msg}; etap 5 nie został uruchomiony automatycznie (najpierw zakończ Mieszanie po dosypce)"
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
        role = str(session.get('rola') or '').lower()
        if role in ['laborant', 'laboratorium']:
            flash('❌ Brak uprawnień: laborant nie może uruchamiać zleceń.', 'warning')
            return redirect(bezpieczny_powrot())

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
    role = str(session.get('rola') or '').lower()
    default_auto_mode = 'auto' if role in ['pracownik', 'produkcja', 'lider'] else 'manual'
    auto_szarza_mode = str(request.form.get('auto_szarza_mode') or default_auto_mode).strip().lower()
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
                            _insert_szarza_compatible(
                                cursor,
                                table_szarze,
                                plan_id=plan_id,
                                nr_szarzy=next_szarza_nr,
                                waga=kg_auto,
                                godzina=now_dt.strftime('%H:%M:%S'),
                                data_dodania=now_dt,
                                pracownik_id=None,
                                produkt=produkt,
                                typ_produkcji='N/A',
                                data_planu=data_planu_date,
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
@roles_required('pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'magazynier', 'laborant', 'laboratorium')
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
@roles_required('pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'magazynier', 'laborant', 'laboratorium')
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
_dosypki_updates = {'AGRO': 0, 'PSD': 0}
ZWOLNIENIE_BANNER_TTL_SECONDS = 180
import threading
ZASYP_START_BANNER_TTL_SECONDS = 180


def _mark_dosypki_updated(linia: str) -> None:
    try:
        linia_u = str(linia or 'PSD').upper()
        _dosypki_updates[linia_u] = time.time()
    except Exception:
        pass


def _ensure_zwolnienie_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS zasyp_zwolnienia_mieszalnika (
            linia VARCHAR(16) PRIMARY KEY,
            timestamp_unix DOUBLE NOT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _set_zwolnienie_timestamp(linia: str) -> float:
    linia_u = str(linia or 'AGRO').upper()
    ts = time.time()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _ensure_zwolnienie_table(cursor)
        cursor.execute(
            """
            INSERT INTO zasyp_zwolnienia_mieszalnika (linia, timestamp_unix)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE timestamp_unix = VALUES(timestamp_unix)
            """,
            (linia_u, ts),
        )
        conn.commit()
    except Exception:
        # Safe fallback for environments where table creation/query fails.
        _mieszalnik_zwolnienia[linia_u] = ts
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
    return ts


def _get_zwolnienie_timestamp(linia: str) -> float:
    linia_u = str(linia or 'AGRO').upper()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _ensure_zwolnienie_table(cursor)
        cursor.execute(
            "SELECT timestamp_unix FROM zasyp_zwolnienia_mieszalnika WHERE linia = %s LIMIT 1",
            (linia_u,),
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            try:
                return float(row[0])
            except Exception:
                return 0.0
    except Exception:
        pass
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
    return float(_mieszalnik_zwolnienia.get(linia_u, 0.0) or 0.0)


def _tts_filename_for_linia(linia: str) -> str:
    return f"zwolnienie_{str(linia or 'AGRO').lower()}.mp3"


def generate_tts_async(text: str, filename: str) -> None:
    """Generate TTS in a background thread and save to static/sounds/filename."""
    try:
        app_root = current_app.root_path
        logger = current_app.logger
    except Exception:
        # Fallbacks if no app context - try to proceed anyway
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logger = logging.getLogger('raportprodukcyjny')

    def _job():
        try:
            try:
                from gtts import gTTS
            except Exception:
                logger.warning('gTTS not installed or import failed; skipping TTS generation')
                return
            out_dir = os.path.join(app_root, 'static', 'sounds')
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, filename)
            # Generate TTS (may require network)
            tts = gTTS(text=text, lang='pl')
            tts.save(out_path)
            logger.info('TTS saved: %s', out_path)
        except Exception:
            logger.exception('TTS generation failed')

    try:
        t = threading.Thread(target=_job, daemon=True)
        t.start()
    except Exception:
        logger.exception('Failed to start TTS thread')

@production_bp.route('/api/zasyp/zwolnij_mieszalnik', methods=['POST'])
@roles_required('laborant', 'laboratorium', 'admin', 'zarzad')
def api_zwolnij_mieszalnik():
    """Signalyze operatorom ze zasyp jest zwolniony"""
    linia = request.form.get('linia') or request.json.get('linia') or 'AGRO'
    linia = linia.upper()
    ts = _set_zwolnienie_timestamp(linia)
    # Kick off TTS generation for this zwolnienie (async)
    try:
        text = f"Laboratorium zwolniło mieszalnik do wysypu na linii {linia}"
        filename = _tts_filename_for_linia(linia)
        generate_tts_async(text, filename)
        audio_url = build_sound_url_if_exists(filename)
    except Exception:
        audio_url = None
    return jsonify({"success": True, "timestamp": ts, "audio_url": audio_url})

@production_bp.route('/api/zasyp/poll_zwolnienie', methods=['GET'])
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
    current = _get_zwolnienie_timestamp(linia)
    is_fresh = (time.time() - current) <= ZWOLNIENIE_BANNER_TTL_SECONDS if current > 0 else False
    if current > last_seen and is_fresh:
        try:
            filename = _tts_filename_for_linia(linia)
            audio_url = build_sound_url_if_exists(filename)
        except Exception:
            audio_url = None
        return jsonify({"new_zwolnienie": True, "timestamp": current, "audio_url": audio_url})
    return jsonify({"new_zwolnienie": False})


@production_bp.route('/api/zasyp/poll_etap_start', methods=['GET'])
def api_poll_etap_start():
    """Poll for recent zasyp ETAP START events (Naważanie). Only returns events to `laborant`/`laboratorium` roles."""
    role = str(session.get('rola') or '').strip().lower()
    if role not in ['laborant', 'laboratorium']:
        return jsonify({"new_start": False})

    linia = request.args.get('linia', 'AGRO').upper()
    try:
        last_seen = float(request.args.get('last_seen', 0))
    except Exception:
        last_seen = 0.0

    latest = get_latest_start_event(linia, last_seen)
    if not latest:
        return jsonify({"new_start": False})

    ts = float(latest.get('event_timestamp') if 'event_timestamp' in latest else (latest.get('timestamp') or 0.0) or 0.0)
    is_fresh = (time.time() - ts) <= ZASYP_START_BANNER_TTL_SECONDS if ts > 0 else False
    if ts > last_seen and is_fresh:
        audio_filename = latest.get('audio_filename') or None
        if audio_filename and not str(audio_filename).startswith('zasyp_start_'):
            audio_filename = None
        if not audio_filename and latest.get('audio_url'):
            try:
                audio_filename = str(latest.get('audio_url')).split('/')[-1]
            except Exception:
                audio_filename = None
        voice_text = build_start_tts_text(latest.get('produkt'), latest.get('szarza_nr'))
        return jsonify({
            "new_start": True,
            "timestamp": ts,
            "plan_id": latest.get('plan_id'),
            "produkt": latest.get('produkt'),
            "szarza_nr": latest.get('szarza_nr'),
            "tts_text": voice_text,
            "audio_url": build_sound_url_if_exists(audio_filename),
        })
    return jsonify({"new_start": False})


@production_bp.route('/api/zasyp/poll_mieszanie_start', methods=['GET'])
def api_poll_mieszanie_start():
    """Poll for recent zasyp Mieszanie START events. Only returns events to `laborant`/`laboratorium` roles."""
    role = str(session.get('rola') or '').strip().lower()
    if role not in ['laborant', 'laboratorium']:
        return jsonify({"new_start": False})

    linia = request.args.get('linia', 'AGRO').upper()
    try:
        last_seen = float(request.args.get('last_seen', 0))
    except Exception:
        last_seen = 0.0

    latest = get_latest_mieszanie_event(linia, last_seen)
    if not latest:
        return jsonify({"new_start": False})

    ts = float(latest.get('event_timestamp') if 'event_timestamp' in latest else (latest.get('timestamp') or 0.0) or 0.0)
    is_fresh = (time.time() - ts) <= ZASYP_START_BANNER_TTL_SECONDS if ts > 0 else False
    if ts > last_seen and is_fresh:
        audio_filename = latest.get('audio_filename') or None
        if audio_filename and not str(audio_filename).startswith('zasyp_mieszanie_start_'):
            audio_filename = None
        etap_nr = latest.get('etap_nr')
        voice_text = build_mieszanie_tts_text(latest.get('produkt'), latest.get('szarza_nr'), etap_nr)
        banner_title = 'OPERATOR DODAŁ DOSYPKĘ - TRWA MIESZANIE' if is_mieszanie_after_dosypka(etap_nr) else 'OPERATOR ROZPOCZĄŁ MIESZANIE'
        return jsonify({
            "new_start": True,
            "timestamp": ts,
            "plan_id": latest.get('plan_id'),
            "etap_nr": etap_nr,
            "produkt": latest.get('produkt'),
            "szarza_nr": latest.get('szarza_nr'),
            "banner_title": banner_title,
            "tts_text": voice_text,
            "audio_url": build_sound_url_if_exists(audio_filename),
        })
    return jsonify({"new_start": False})


@production_bp.route('/api/zasyp/poll_dosypki_update', methods=['GET'])
def api_poll_dosypki_update():
    """Return update timestamp for dosypki so dashboards can refresh after confirm/cancel/add."""
    linia = request.args.get('linia', 'AGRO').upper()
    try:
        last_seen = float(request.args.get('last_seen', 0))
    except Exception:
        last_seen = 0.0
    current = _dosypki_updates.get(linia, 0.0)
    if current > last_seen:
        return jsonify({"new_update": True, "timestamp": current})
    return jsonify({"new_update": False})


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
@roles_required('laborant', 'laboratorium', 'planista', 'admin')
def dosypka_page(plan_id):
    """Render form to add up to 4 dosypki for an active Zasyp plan."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    conn = get_db_connection()
    try:
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        table_plan = get_table_name('plan_produkcji', linia)
        table_dosypki = get_table_name('dosypki', linia)
        cursor = conn.cursor()
        cursor.execute(f"SELECT produkt, typ_produkcji, status FROM {table_plan} WHERE id=%s AND sekcja='Zasyp'", (plan_id,))
        plan = cursor.fetchone()
        if not plan:
            msg = 'Plan nie znaleziony'
            if is_ajax:
                return f'<div class="p-15 text-danger">{msg}</div>', 404
            flash(msg, 'error')
            return redirect(bezpieczny_powrot())
        
        produkt, typ_produkcji, status = plan[0], plan[1], plan[2]
        # Only allow adding dosypki to active orders
        if status != 'w toku':
            msg = 'Dosypki można dodawać tylko do aktywnego zlecenia (status "w toku")'
            if is_ajax:
                return f'<div class="p-15 text-warning">{msg}</div>', 400
            flash(msg, 'warning')
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
                SELECT id, nazwa, kg, data_zlecenia, potwierdzone, COALESCE(anulowana, 0), anulowal_login, data_anulowania
                FROM {table_dosypki}
                WHERE plan_id=%s AND szarza_id=%s
                ORDER BY COALESCE(anulowana, 0) ASC, data_zlecenia DESC
                """,
                (plan_id, szarza_id_int)
            )
        else:
            cursor.execute(
                f"""
                SELECT id, nazwa, kg, data_zlecenia, potwierdzone, COALESCE(anulowana, 0), anulowal_login, data_anulowania
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
                'potwierdzone': bool(row[4]),
                'anulowana': bool(row[5]),
                'anulowal_login': row[6],
                'data_anulowania': str(row[7]) if row[7] is not None else '',
            }
            for row in cursor.fetchall()
        ]

        # Pull suggestions strictly from warehouse sources.
        try:
            dostepne_surowce = _get_allowed_dosypka_materials(cursor, linia)
        except Exception:
            current_app.logger.warning('dosypka_page: failed to load raw material suggestions', exc_info=True)
            dostepne_surowce = []

        return render_template(
            'dodaj_dosypke_popup.html',
            plan_id=plan_id,
            produkt=produkt,
            typ=typ_produkcji,
            szarza_id=szarza_id,
            existing_dosypki=existing_dosypki,
            linia=linia,
            dostepne_surowce=dostepne_surowce
        )
    except Exception as e:
        current_app.logger.error(f'Error in dosypka_page: {e}', exc_info=True)
        msg = 'Błąd pobierania danych planu'
        if is_ajax:
            return f'<div class="p-15 text-danger">{msg}</div>', 500
        flash(msg, 'error')
        return redirect(bezpieczny_powrot())
    finally:
        try:
            conn.close()
        except Exception:
            pass


@production_bp.route('/dodaj_dosypke', methods=['POST'])
@roles_required('laborant', 'laboratorium', 'admin')
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

    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'

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
        table_plan = get_table_name('plan_produkcji', linia)
        table_dosypki = get_table_name('dosypki', linia)
        table_szarze = get_table_name('szarze', linia)
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

        # Popup may send szarza sequence number (1,2,3...) instead of real szarze.id.
        # Resolve it to actual ID for this plan to keep dosypki visible in szarza list.
        if szarza_id and not brak_dosypki:
            cursor.execute(
                f"SELECT id FROM {table_szarze} WHERE id=%s AND plan_id=%s LIMIT 1",
                (szarza_id, plan_id)
            )
            id_match = cursor.fetchone()
            if not id_match:
                cursor.execute(
                    f"SELECT id FROM {table_szarze} WHERE plan_id=%s ORDER BY data_dodania ASC, id ASC",
                    (plan_id,)
                )
                szarza_ids_for_plan = [int(row[0]) for row in cursor.fetchall() if row and row[0] is not None]
                if szarza_ids_for_plan and 1 <= int(szarza_id) <= len(szarza_ids_for_plan):
                    szarza_id = int(szarza_ids_for_plan[int(szarza_id) - 1])

        # If the popup didn't send szarza_id, bind dosypka to the latest szarza for this plan.
        if not szarza_id and not brak_dosypki:
            cursor.execute(
                f"SELECT id FROM {table_szarze} WHERE plan_id=%s ORDER BY data_dodania DESC, id DESC LIMIT 1",
                (plan_id,)
            )
            latest_szarza = cursor.fetchone()
            if latest_szarza and latest_szarza[0]:
                szarza_id = int(latest_szarza[0])

        if not brak_dosypki:
            allowed_surowce = _get_allowed_dosypka_materials(cursor, linia)
            if not allowed_surowce:
                flash('Brak dostępnego słownika surowców magazynu. Nie można zapisać własnych nazw.', 'warning')
                return redirect(bezpieczny_powrot())

            allowed_map = {str(name).strip().lower(): name for name in allowed_surowce if str(name).strip()}
            invalid_entries = [name for name, _ in entries if str(name).strip().lower() not in allowed_map]
            if invalid_entries:
                invalid_label = ', '.join(sorted(set(invalid_entries))[:3])
                flash(f'Niedozwolona nazwa surowca: {invalid_label}. Wybierz pozycję z listy magazynu.', 'warning')
                return redirect(bezpieczny_powrot())

            # Normalize names to warehouse dictionary form before insert.
            entries = [(allowed_map[str(name).strip().lower()], kg) for name, kg in entries]

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
        _mark_dosypki_updated(linia)

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
@roles_required('operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
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
        _mark_dosypki_updated(linia)
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
@roles_required('laborant', 'laboratorium', 'admin')
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
        _mark_dosypki_updated(linia)
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
@roles_required('laborant', 'laboratorium', 'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
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
        visible_roles = ('laborant', 'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
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


@production_bp.route('/zasyp/szarza_notatka/<int:szarza_id>', methods=['GET'])
@roles_required('laborant', 'laboratorium', 'lider', 'admin', 'zarzad')
def szarza_notatka_page(szarza_id):
    """Render popup for editing szarza note (uwagi) from Zasyp dashboard."""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia).upper()
    table_szarze = get_table_name('szarze', linia)
    conn = get_db_connection()
    cursor = conn.cursor()
    uwagi = ''
    try:
        cursor.execute(f"SELECT uwagi FROM {table_szarze} WHERE id=%s", (szarza_id,))
        row = cursor.fetchone()
        if row:
            uwagi = row[0] or ''
    except Exception as e:
        current_app.logger.error('Failed to load szarza note (id=%s): %s', szarza_id, e, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    data = request.args.get('data') or str(date.today())
    sekcja = request.args.get('sekcja', 'Zasyp')
    return render_template('edytuj_szarze_popup.html', szarza_id=szarza_id, uwagi=uwagi, linia=linia, data=data, sekcja=sekcja)


@production_bp.route('/zasyp/szarza_notatka/<int:szarza_id>', methods=['POST'])
@roles_required('laborant', 'laboratorium', 'lider', 'admin', 'zarzad')
def szarza_notatka_save(szarza_id):
    """Save szarza note (uwagi) from Zasyp dashboard popup."""
    new_uwagi = request.form.get('uwagi', '')
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia).upper()
    table_szarze = get_table_name('szarze', linia)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"UPDATE {table_szarze} SET uwagi=%s WHERE id=%s", (new_uwagi, szarza_id))
        conn.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Zapisano notatkę', 'szarza_id': szarza_id}), 200
        flash('Zapisano notatkę do szarży', 'success')
    except Exception as e:
        current_app.logger.error('Failed to save szarza note (id=%s): %s', szarza_id, e, exc_info=True)
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


@production_bp.route('/dosypki_list', methods=['GET'])
@roles_required('laborant', 'laboratorium', 'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
def dosypki_list():
    """Render slide-over page with list of active unconfirmed dosypki for operators."""
    # Accept optional plan_id to filter dosypki for a specific zlecenie
    plan_id = request.args.get('plan_id', None)
    linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
    # Fetch unconfirmed dosypki server-side so fragment shows data even if client JS doesn't run
    from app.db import list_unconfirmed_dosypki
    rows = list_unconfirmed_dosypki(linia=linia)
    role = session.get('rola', '')
    visible_roles = ('laborant', 'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
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
