from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
from datetime import date, datetime
import mysql.connector
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required, dynamic_role_required
from app.utils.validation import require_field
from app.services.planning_service import PlanningService
from app.core.audit import audit_log

warehouse_bp = Blueprint('warehouse', __name__)


def _update_paleta_workowanie(cursor, paleta_id, waga, linia='PSD'):
    """Helper: update palety_workowanie weight or confirmed weight.

    Returns dict: {'found': bool, 'action': str, 'plan_id': int, 'status': str}
    """
    from app.db import get_table_name as _gtn
    table_pal = _gtn('palety_workowanie', linia)
    table_plan = _gtn('plan_produkcji', linia)
    cursor.execute(f"SELECT COALESCE(status,''), plan_id FROM {table_pal} WHERE id=%s", (paleta_id,))
    row = cursor.fetchone()
    if not row:
        return {'found': False}
    status = row[0] if row[0] else ''
    plan_id = row[1]

    if status == 'przyjeta':
        cursor.execute(f"UPDATE {table_pal} SET waga_potwierdzona=%s WHERE id=%s", (waga, paleta_id))
        action = 'waga_potwierdzona'
    else:
        cursor.execute(f"UPDATE {table_pal} SET waga=%s WHERE id=%s", (waga, paleta_id))
        cursor.execute(
            f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s",
            (plan_id, plan_id)
        )
        action = 'waga'

    return {'found': True, 'action': action, 'plan_id': plan_id, 'status': status}


def _update_paleta_magazyn(cursor, paleta_id, nowa_waga):
    """Helper: update magazyn_palety weight and refresh plan aggregate."""
    cursor.execute("SELECT plan_id FROM magazyn_palety WHERE id=%s", (paleta_id,))
    row = cursor.fetchone()
    if not row:
        return {'found': False}
    plan_id = row[0]
    cursor.execute("UPDATE magazyn_palety SET waga_netto=%s WHERE id=%s", (nowa_waga, paleta_id))
    cursor.execute("""
            UPDATE plan_produkcji pp
            SET tonaz_rzeczywisty = (
                SELECT COALESCE(SUM(mp.waga_netto), 0)
                FROM magazyn_palety mp
                WHERE mp.plan_id = pp.id
            )
            WHERE pp.id = %s
        """, (plan_id,))
    return {'found': True, 'plan_id': plan_id}

def bezpieczny_powrot():
    """Default return path: planner view or dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    return url_for('main.index', sekcja=sekcja, data=data, linia=linia)


@warehouse_bp.route('/dodaj_palete/<int:plan_id>', methods=['POST'])
@login_required
def dodaj_palete(plan_id):
    """Add paleta (package) to Workowanie buffer"""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    table_plan = get_table_name('plan_produkcji', linia)
    table_pal = get_table_name('palety_workowanie', linia)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_app.logger.debug('dodaj_palete: plan_id=%s', plan_id)
    except Exception:
        pass
    
    try:
        waga_input = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
    except Exception:
        waga_input = 0
    
    cursor.execute(f"SELECT sekcja, data_planu, produkt FROM {table_plan} WHERE id=%s", (plan_id,))
    plan_row = cursor.fetchone()
    
    if not plan_row:
        conn.close()
        return ("Błąd: Plan nie znaleziony", 404)
    
    plan_sekcja, plan_data, plan_produkt = plan_row
    
    if plan_sekcja != 'Workowanie':
        conn.close()
        try:
            current_app.logger.warning(f'REJECTED: Cannot add paleta to sekcja={plan_sekcja}')
        except Exception:
            pass
        return ("Błąd: Paletki można dodawać tylko do Workowania (bufora)", 400)
    
    if waga_input <= 0:
        conn.close()
        return ("Błąd: Waga musi być większa od 0", 400)
    
    from datetime import datetime as _dt
    now_ts = _dt.now()
    
    try:
        cursor.execute(
            f"INSERT INTO {table_pal} (plan_id, waga, tara, waga_brutto, data_dodania, status) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia')",
            (plan_id, waga_input, now_ts)
        )
        paleta_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
        
        cursor.execute(
            f"UPDATE {table_plan} SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id = %s",
            (waga_input, plan_id)
        )
        
        conn.commit()
        
        # Validate and fix status anomalies after tonaz update
        try:
            PlanningService.ensure_status_after_tonaz_update(plan_id)
        except Exception as e:
            try:
                current_app.logger.warning(f'Warning during status validation: {str(e)}')
            except Exception:
                pass
        
        try:
            current_app.logger.info('Dodano paletę: plan_id=%s, waga=%s kg, użytkownik=%s', plan_id, waga_input, session.get('login'))
            audit_log('Dodał paletę', f'plan_id={plan_id}, produkt={plan_produkt}, waga={waga_input} kg')
        except Exception:
            pass
        
    except Exception as e:
        try:
            current_app.logger.exception(f'Failed to add paleta: {str(e)}')
        except Exception:
            pass
        conn.rollback()
        conn.close()
        return ("Błąd: Nie udało się dodać paletki", 500)
    
    conn.close()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Paletka dodana', 'paleta_id': paleta_id}), 200
    
    return redirect(bezpieczny_powrot())


@warehouse_bp.route('/dodaj_palete_page/<int:plan_id>', methods=['GET'])
@login_required
def dodaj_palete_page(plan_id):
    """Render form for adding paleta"""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia).upper()
    table_plan = get_table_name('plan_produkcji', linia)
    conn = get_db_connection()
    cursor = conn.cursor()
    produkt = None
    sekcja = None
    typ = None
    try:
        cursor.execute(f"SELECT produkt, sekcja, typ_produkcji FROM {table_plan} WHERE id=%s", (plan_id,))
        row = cursor.fetchone()
        if row:
            produkt, sekcja, typ = row[0], row[1], row[2]
    except Exception as e:
        current_app.logger.error(f'Failed to fetch plan {plan_id} for dodaj_palete_page: {e}', exc_info=True)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return render_template('dodaj_palete_popup.html', plan_id=plan_id, produkt=produkt, sekcja=sekcja, typ=typ, linia=linia)


@warehouse_bp.route('/edytuj_palete_page/<int:paleta_id>', methods=['GET'])
@login_required
def edytuj_palete_page(paleta_id):
    """Render form for editing paleta weight"""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia).upper()
    table_pal = get_table_name('palety_workowanie', linia)
    table_plan = get_table_name('plan_produkcji', linia)
    conn = get_db_connection()
    cursor = conn.cursor()
    waga = None
    sekcja = None
    try:
        cursor.execute(f"SELECT waga, plan_id FROM {table_pal} WHERE id=%s", (paleta_id,))
        row = cursor.fetchone()
        if row:
            waga = row[0]
            plan_id = row[1]
            cursor.execute(f"SELECT sekcja FROM {table_plan} WHERE id=%s", (plan_id,))
            r2 = cursor.fetchone()
            if r2:
                sekcja = r2[0]
    except Exception as e:
        current_app.logger.error(f'Failed to load paleta {paleta_id} for edit page: {e}', exc_info=True)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return render_template('edytuj_palete_popup.html', paleta_id=paleta_id, waga=waga, sekcja=sekcja, linia=linia)


@warehouse_bp.route('/confirm_delete_palete_page/<int:paleta_id>', methods=['GET'])
@login_required
def confirm_delete_palete_page(paleta_id):
    """Render delete confirmation for paleta"""
    linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
    return render_template('confirm_delete_palete.html', paleta_id=paleta_id, linia=linia)


@warehouse_bp.route('/confirm_delete_szarze_page/<int:szarza_id>', methods=['GET'])
@login_required
def confirm_delete_szarze_page(szarza_id):
    """Render delete confirmation for szarża"""
    linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
    return render_template('confirm_delete_szarze.html', szarza_id=szarza_id, linia=linia)


@warehouse_bp.route('/edytuj_szarze_page/<int:szarza_id>', methods=['GET'])
@login_required
def edytuj_szarze_page(szarza_id):
    """Render form for editing szarża notes (uwagi)"""
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
        current_app.logger.error(f'Failed to load szarza {szarza_id} for edit page: {e}', exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    data = request.args.get('data') or str(date.today())
    sekcja = request.args.get('sekcja', 'Zasyp')
    return render_template('edytuj_szarze_popup.html', szarza_id=szarza_id, uwagi=uwagi, linia=linia, data=data, sekcja=sekcja)


@warehouse_bp.route('/edytuj_szarze/<int:szarza_id>', methods=['POST'])
@login_required
def edytuj_szarze(szarza_id):
    """Save szarża notes (uwagi) to DB"""
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
        current_app.logger.error(f'Failed to save uwagi for szarza {szarza_id}: {e}', exc_info=True)
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


@warehouse_bp.route('/podsumowanie_szarz', methods=['GET'])
@roles_required('planista', 'lider', 'admin')
def podsumowanie_szarz():
    """Page: summary of szarze and dosypki durations per zlecenie with period filters."""
    # Parse filters
    period = request.args.get('period', 'day')
    qdate_str = request.args.get('date')
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    qdate = None
    # prefer explicit start/end if provided (start/end are inclusive dates in ISO YYYY-MM-DD)
    start = None
    end = None
    if start_str and end_str:
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                start = datetime.strptime(start_str, fmt).date()
                break
            except Exception:
                continue
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                end = datetime.strptime(end_str, fmt).date()
                break
            except Exception:
                continue
        if start and end:
            qdate = start
    if not qdate:
        if qdate_str:
            for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
                try:
                    qdate = datetime.strptime(qdate_str, fmt).date()
                    break
                except Exception:
                    continue
        if not qdate:
            qdate = date.today()

    # Compute date range (end is exclusive)
    from datetime import timedelta
    if start and end:
        # user provided inclusive end -> convert to exclusive by adding one day
        end = end + timedelta(days=1)
    else:
        if period == 'day':
            start = qdate
            end = qdate + timedelta(days=1)
        elif period == 'week':
            start = qdate - timedelta(days=qdate.weekday())
            end = start + timedelta(days=7)
        elif period == 'month':
            start = qdate.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
        elif period == 'quarter':
            q = (qdate.month - 1) // 3
            start_month = q * 3 + 1
            start = qdate.replace(month=start_month, day=1)
            if start_month + 3 > 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start_month + 3)
        elif period == 'year':
            start = qdate.replace(month=1, day=1)
            end = start.replace(year=start.year + 1)
        else:
            start = qdate
            end = qdate + timedelta(days=1)

    group_by = request.args.get('group_by', 'plan')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT p.id, p.produkt, p.data_planu, p.real_start, p.tonaz,
                (SELECT s.id FROM szarze s WHERE s.plan_id=p.id ORDER BY s.data_dodania ASC LIMIT 1) AS first_szarza_id,
                (SELECT s.data_dodania FROM szarze s WHERE s.plan_id=p.id ORDER BY s.data_dodania ASC LIMIT 1) AS first_szarza_time,
                (SELECT d.data_potwierdzenia FROM dosypki d WHERE d.plan_id=p.id AND d.szarza_id = (SELECT s2.id FROM szarze s2 WHERE s2.plan_id=p.id ORDER BY s2.data_dodania ASC LIMIT 1) AND d.potwierdzone=1 AND COALESCE(d.anulowana,0)=0 ORDER BY d.data_potwierdzenia ASC LIMIT 1) AS first_dosypka_confirmed_time,
                    (SELECT d.data_zlecenia FROM dosypki d WHERE d.plan_id=p.id AND d.szarza_id = (SELECT s2.id FROM szarze s2 WHERE s2.plan_id=p.id ORDER BY s2.data_dodania ASC LIMIT 1) AND COALESCE(d.anulowana,0)=0 ORDER BY d.data_zlecenia ASC LIMIT 1) AS first_dosypka_order_time,
                (SELECT MIN(s3.data_dodania) FROM szarze s3 WHERE s3.plan_id=p.id AND s3.data_dodania > (SELECT s4.data_dodania FROM szarze s4 WHERE s4.plan_id=p.id ORDER BY s4.data_dodania ASC LIMIT 1)) AS next_szarza_time
            FROM plan_produkcji p
            WHERE p.sekcja='Zasyp' AND p.data_planu >= %s AND p.data_planu < %s
            ORDER BY p.data_planu, p.kolejnosc
            """,
            (start, end)
        )

        rows = cursor.fetchall()
        try:
            current_app.logger.debug('[podsumowanie_szarz] fetched rows=%s', len(rows))
        except Exception:
            pass
        results = []
        for r in rows:
            plan_id = r[0]
            produkt = r[1]
            data_planu = r[2]
            real_start = r[3]
            plan_tonaz = r[4]
            first_szarza_time = r[6]
            first_dosypka_confirmed_time = r[7]
            first_dosypka_order_time = r[8]
            next_szarza_time = r[9]

            def minutes_between(a, b):
                if not a or not b:
                    return None
                try:
                    if isinstance(a, str):
                        a = datetime.fromisoformat(a)
                    if isinstance(b, str):
                        b = datetime.fromisoformat(b)
                    delta = b - a
                    return round(delta.total_seconds() / 60.0, 1)
                except Exception:
                    return None

            def seconds_between(a, b):
                if not a or not b:
                    return None
                try:
                    if isinstance(a, str):
                        a = datetime.fromisoformat(a)
                    if isinstance(b, str):
                        b = datetime.fromisoformat(b)
                    delta = b - a
                    return int(round(delta.total_seconds()))
                except Exception:
                    return None

            # Rule 1: time from real_start to first szarza
            szarza_minutes = minutes_between(real_start, first_szarza_time)
            szarza_seconds = seconds_between(real_start, first_szarza_time)

            # Rule 2a: time from first szarza to dosypka order (when lab requested dosypka)
            szarza_to_dosypka_minutes = minutes_between(first_szarza_time, first_dosypka_order_time)
            szarza_to_dosypka_seconds = seconds_between(first_szarza_time, first_dosypka_order_time)

            # Rule 2b: time from dosypka order to dosypka confirmation (lab processing)
            dosypka_add_to_confirm_minutes = minutes_between(first_dosypka_order_time, first_dosypka_confirmed_time)
            dosypka_add_to_confirm_seconds = seconds_between(first_dosypka_order_time, first_dosypka_confirmed_time)

            # Traditional lab_minutes: total from szarza to confirmation (kept for compatibility)
            lab_minutes = minutes_between(first_szarza_time, first_dosypka_confirmed_time)
            lab_seconds = seconds_between(first_szarza_time, first_dosypka_confirmed_time)

            # Rule 4: mixing time fixed
            mixing_minutes = 5.0

            # Rule 5: time from end of mixing (dosypka confirmed + mixing) to next szarza
            end_of_mixing = None
            if first_dosypka_confirmed_time:
                try:
                    dt = first_dosypka_confirmed_time
                    if isinstance(dt, str):
                        dt = datetime.fromisoformat(dt)
                    end_of_mixing = dt + timedelta(minutes=mixing_minutes)
                except Exception:
                    end_of_mixing = None

            wait_to_next_szarza = minutes_between(end_of_mixing, next_szarza_time) if end_of_mixing else None

            # format real_start for display
            def format_dt(dt):
                if not dt:
                    return None
                try:
                    if isinstance(dt, str):
                        dt = datetime.fromisoformat(dt)
                    return dt.strftime('%d.%m.%Y %H:%M')
                except Exception:
                    try:
                        return str(dt)
                    except Exception:
                        return None

            results.append({
                'plan_id': plan_id,
                'produkt': produkt,
                'data_planu': data_planu,
                'real_start': real_start,
                'real_start_fmt': format_dt(real_start),
                'real_start_hms': (datetime.fromisoformat(real_start).strftime('%H:%M:%S') if isinstance(real_start, str) else (real_start.strftime('%H:%M:%S') if real_start else None)),
                'szarza_seconds': szarza_seconds,
                'first_szarza_time': first_szarza_time,
                'szarze_times': None,
                'szarza_minutes': szarza_minutes,
                'szarza_to_dosypka_minutes': szarza_to_dosypka_minutes,
                'szarza_to_dosypka_seconds': szarza_to_dosypka_seconds,
                'first_dosypka_confirmed_time': first_dosypka_confirmed_time,
                'lab_minutes': lab_minutes,
                'lab_seconds': lab_seconds,
                'dosypka_add_to_confirm_minutes': dosypka_add_to_confirm_minutes,
                'dosypka_add_to_confirm_seconds': dosypka_add_to_confirm_seconds,
                'mixing_minutes': mixing_minutes,
                'next_szarza_time': next_szarza_time,
                'wait_to_next_szarza': wait_to_next_szarza,
            })

        # Compute averages (only over non-null values)
        def avg(field):
            # exclude None and negative durations from averages
            vals = [x[field] for x in results if x[field] is not None and isinstance(x[field], (int, float)) and x[field] >= 0]
            return round(sum(vals) / len(vals), 1) if vals else None

        averages = {
            'szarza_minutes': avg('szarza_minutes'),
            'lab_minutes': avg('lab_minutes'),
            'szarza_to_dosypka_minutes': avg('szarza_to_dosypka_minutes'),
            'dosypka_add_to_confirm_minutes': avg('dosypka_add_to_confirm_minutes'),
            'mixing_minutes': avg('mixing_minutes'),
            'wait_to_next_szarza': avg('wait_to_next_szarza'),
        }

        # Grouping
        grouped = {}
        if group_by == 'produkt':
            for item in results:
                key = item['produkt'] or 'UNKNOWN'
                grouped.setdefault(key, []).append(item)
        else:
            for item in results:
                key = f"Z{item['plan_id']}"
                grouped.setdefault(key, []).append(item)

        grouped_summary = []
        for key, items in grouped.items():
            def avg_items(field):
                vals = [x[field] for x in items if x[field] is not None and isinstance(x[field], (int, float)) and x[field] >= 0]
                return round(sum(vals) / len(vals), 1) if vals else None
            grouped_summary.append({
                'group': key,
                'count': len(items),
                'szarza_minutes': avg_items('szarza_minutes'),
                'lab_minutes': avg_items('lab_minutes'),
                'szarza_to_dosypka_minutes': avg_items('szarza_to_dosypka_minutes'),
                'dosypka_add_to_confirm_minutes': avg_items('dosypka_add_to_confirm_minutes'),
                'wait_to_next_szarza': avg_items('wait_to_next_szarza')
            })

        # Details per szarza (each batch) and its dosypki
        szarze_details = []
        for r in rows:
            plan_id = r[0]
            produkt = r[1]
            # fetch szarze for this plan
            try:
                cursor.execute("SELECT id, data_dodania, uwagi FROM szarze WHERE plan_id=%s ORDER BY data_dodania ASC", (plan_id,))
                szarze_rows = cursor.fetchall()
            except Exception:
                szarze_rows = []

            # attach full list of szarze times to corresponding result entry
            try:
                # find the result dict for this plan and set szarze_times
                for item in results:
                    if item.get('plan_id') == plan_id:
                        times = []
                        for idx, srow in enumerate(szarze_rows):
                            sid = srow[0]
                            dt = srow[1]
                            formatted = None
                            formatted_hms = None
                            try:
                                if isinstance(dt, str):
                                    dt = datetime.fromisoformat(dt)
                                formatted = dt.strftime('%d.%m.%Y %H:%M')
                                formatted_hms = dt.strftime('%H:%M:%S')
                            except Exception:
                                try:
                                    formatted = str(dt)
                                except Exception:
                                    formatted = None
                                formatted_hms = None
                            # fetch dosypki for this szarza to attach as list
                            dosypki_list = []
                            try:
                                cursor.execute("SELECT id, data_zlecenia, data_potwierdzenia, nazwa FROM dosypki WHERE plan_id=%s AND szarza_id=%s AND COALESCE(anulowana,0)=0 ORDER BY data_zlecenia ASC", (plan_id, sid))
                                drows = cursor.fetchall()
                                for d in drows:
                                    did = d[0]
                                    dz = d[1]
                                    dconf = d[2] if len(d) > 2 else None
                                    dnazwa = d[3] if len(d) > 3 else None
                                    try:
                                        if isinstance(dz, str):
                                            dz_dt = datetime.fromisoformat(dz)
                                        else:
                                            dz_dt = dz
                                        dz_hms = dz_dt.strftime('%H:%M:%S') if dz_dt else None
                                    except Exception:
                                        dz_hms = (str(dz) if dz is not None else None)
                                    try:
                                        if isinstance(dconf, str):
                                            dc_dt = datetime.fromisoformat(dconf)
                                        else:
                                            dc_dt = dconf
                                        dconf_hms = dc_dt.strftime('%H:%M:%S') if dc_dt else None
                                    except Exception:
                                        dconf_hms = (str(dconf) if dconf is not None else None)
                                    dosypki_list.append({'id': did, 'order_time_hms': dz_hms, 'confirm_time_hms': dconf_hms, 'nazwa': dnazwa})
                            except Exception:
                                dosypki_list = []
                            # compute szarza start: for first szarza -> plan_real_start, otherwise -> previous szarza last confirmation + 4min
                            szarza_start_hms = None
                            szarza_start_dt = None
                            try:
                                # plan real start
                                plan_real_start = None
                                for it in results:
                                    if it.get('plan_id') == plan_id:
                                        plan_real_start = it.get('real_start')
                                        break
                                if idx == 0:
                                    if plan_real_start:
                                        if isinstance(plan_real_start, str):
                                            prs = datetime.fromisoformat(plan_real_start)
                                        else:
                                            prs = plan_real_start
                                        szarza_start_dt = prs
                                        szarza_start_hms = prs.strftime('%H:%M:%S')
                                else:
                                    try:
                                        prev_id = szarze_rows[idx-1][0]
                                        cursor.execute("SELECT MAX(data_potwierdzenia) FROM dosypki WHERE plan_id=%s AND szarza_id=%s AND potwierdzone=1 AND COALESCE(anulowana,0)=0", (plan_id, prev_id))
                                        pv = cursor.fetchone()
                                        prev_conf = pv[0] if pv else None
                                    except Exception:
                                        prev_conf = None
                                    if prev_conf:
                                        if isinstance(prev_conf, str):
                                            pc = datetime.fromisoformat(prev_conf)
                                        else:
                                            pc = prev_conf
                                        start_next = pc + timedelta(minutes=4)
                                        szarza_start_dt = start_next
                                        try:
                                            szarza_start_hms = start_next.strftime('%H:%M:%S')
                                        except Exception:
                                            szarza_start_hms = None

                            except Exception:
                                szarza_start_hms = None
                                szarza_start_dt = None

                            # compute whole szarza duration: from szarza_start -> first confirmation + 4 minutes
                            whole_szarza_hms = None
                            whole_szarza_seconds = None
                            try:
                                # find first confirmation datetime from drows
                                first_conf = None
                                if drows:
                                    for d in drows:
                                        if d and len(d) > 2 and d[2]:
                                            first_conf = d[2]
                                            break
                                if szarza_start_dt and first_conf:
                                    if isinstance(first_conf, str):
                                        fc = datetime.fromisoformat(first_conf)
                                    else:
                                        fc = first_conf
                                    end_mix = fc + timedelta(minutes=4)
                                    whole_szarza_seconds = int(round((end_mix - szarza_start_dt).total_seconds()))
                                    # format as HH:MM:SS
                                    if whole_szarza_seconds is not None:
                                        sec = abs(whole_szarza_seconds)
                                        h = sec // 3600
                                        m = (sec % 3600) // 60
                                        s = sec % 60
                                        fmt = f"{h:02d}:{m:02d}:{s:02d}"
                                        whole_szarza_hms = f"-{fmt}" if whole_szarza_seconds < 0 else fmt
                            except Exception:
                                whole_szarza_hms = None
                                whole_szarza_seconds = None
                            # (szarza_start already computed above)

                            # compute time from szarza start -> szarza added (seconds and formatted HH:MM:SS)
                            start_to_add_seconds = None
                            start_to_add_hms = None
                            try:
                                added_dt = None
                                if srow and len(srow) > 1:
                                    added_raw = srow[1]
                                    if added_raw:
                                        added_dt = datetime.fromisoformat(added_raw) if isinstance(added_raw, str) else added_raw
                                if szarza_start_dt and added_dt:
                                    delta = int(round((added_dt - szarza_start_dt).total_seconds()))
                                    start_to_add_seconds = delta
                                    sec = abs(delta)
                                    h = sec // 3600
                                    m = (sec % 3600) // 60
                                    s = sec % 60
                                    fmt = f"{h:02d}:{m:02d}:{s:02d}"
                                    start_to_add_hms = f"-{fmt}" if delta < 0 else fmt
                            except Exception:
                                start_to_add_seconds = None
                                start_to_add_hms = None

                            times.append({'id': sid, 'time': formatted, 'time_hms': formatted_hms, 'dosypki': dosypki_list, 'whole_szarza_hms': whole_szarza_hms, 'whole_szarza_seconds': whole_szarza_seconds, 'szarza_start_hms': szarza_start_hms, 'start_to_add_seconds': start_to_add_seconds, 'start_to_add_hms': start_to_add_hms})
                        item['szarze_times'] = times
                        break
            except Exception:
                pass

                for idx, srow in enumerate(szarze_rows):
                    szarza_id = srow[0]
                    szarza_time = srow[1]
                    szarza_uwagi = srow[2] if len(srow) > 2 else None
                # formatted time for display
                try:
                    if isinstance(szarza_time, str):
                        sz_dt = datetime.fromisoformat(szarza_time)
                    else:
                        sz_dt = szarza_time
                    szarza_time_fmt = sz_dt.strftime('%d.%m.%Y %H:%M') if sz_dt else None
                except Exception:
                    try:
                        szarza_time_fmt = str(szarza_time)
                    except Exception:
                        szarza_time_fmt = None
                # next szarza time
                try:
                    cursor.execute("SELECT MIN(data_dodania) FROM szarze WHERE plan_id=%s AND data_dodania > %s", (plan_id, szarza_time))
                    ns = cursor.fetchone()
                    next_s = ns[0] if ns else None
                except Exception:
                    next_s = None


                # fetch all dosypki for this szarza (order times) to compute intervals
                try:
                    cursor.execute("SELECT id, data_zlecenia, data_potwierdzenia, nazwa FROM dosypki WHERE plan_id=%s AND szarza_id=%s AND COALESCE(anulowana,0)=0 ORDER BY data_zlecenia ASC", (plan_id, szarza_id))
                    dos_rows = cursor.fetchall()
                except Exception:
                    dos_rows = []
                dosypki_order_times = [dr[1] for dr in dos_rows if dr and dr[1]]
                dosypki_nazwy = [dr[3] for dr in dos_rows if dr and len(dr) > 3 and dr[3]]
                dosypki_order_times_fmt = []
                for dt in dosypki_order_times:
                    try:
                        if isinstance(dt, str):
                            dtt = datetime.fromisoformat(dt)
                        else:
                            dtt = dt
                        dosypki_order_times_fmt.append(dtt.strftime('%d.%m.%Y %H:%M'))
                    except Exception:
                        try:
                            dosypki_order_times_fmt.append(str(dt))
                        except Exception:
                            dosypki_order_times_fmt.append(None)

                # first dosypka times (for compatibility)
                dosypka_order_time = dosypki_order_times[0] if dosypki_order_times else None
                dosypka_confirm_time = None
                if dos_rows and dos_rows[0] and len(dos_rows[0]) > 2:
                    dosypka_confirm_time = dos_rows[0][2]

                # helper to compute seconds between two datetimes
                def secs_between(a, b):
                    if not a or not b:
                        return None
                    try:
                        if isinstance(a, str):
                            a = datetime.fromisoformat(a)
                        if isinstance(b, str):
                            b = datetime.fromisoformat(b)
                        return int(round((b - a).total_seconds()))
                    except Exception:
                        return None

                # compute intervals: start->first, then between successive dosypki
                start_to_first_s = None
                dosypki_intervals_s = []
                # find plan real_start from results
                plan_real_start = None
                for it in results:
                    if it.get('plan_id') == plan_id:
                        plan_real_start = it.get('real_start')
                        break
                if dosypki_order_times:
                    # start -> first
                    start_to_first_s = secs_between(plan_real_start, dosypki_order_times[0])
                    # between dosypki
                    for i in range(1, len(dosypki_order_times)):
                        s = secs_between(dosypki_order_times[i-1], dosypki_order_times[i])
                        dosypki_intervals_s.append(s)
                try:
                    if dosypka_confirm_time:
                        if isinstance(dosypka_confirm_time, str):
                            dc_dt = datetime.fromisoformat(dosypka_confirm_time)
                        else:
                            dc_dt = dosypka_confirm_time
                        dosypka_confirm_time_fmt = dc_dt.strftime('%d.%m.%Y %H:%M')
                    else:
                        dosypka_confirm_time_fmt = None
                except Exception:
                    try:
                        dosypka_confirm_time_fmt = str(dosypka_confirm_time)
                    except Exception:
                        dosypka_confirm_time_fmt = None

                szarza_duration_s = secs_between(szarza_time, next_s)
                # If there is no next szarza and plan tonaz == 1000, measure duration from plan start
                try:
                    if not next_s and plan_tonaz is not None and abs((plan_tonaz or 0) - 1000) < 0.01:
                        # find plan real_start
                        plan_real_start = None
                        for it in results:
                            if it.get('plan_id') == plan_id:
                                plan_real_start = it.get('real_start')
                                break
                        if plan_real_start:
                            szarza_duration_s = secs_between(plan_real_start, szarza_time)
                except Exception:
                    pass
                szarza_to_dosypka_s = secs_between(szarza_time, dosypka_order_time)
                dosypka_add_to_confirm_s = secs_between(dosypka_order_time, dosypka_confirm_time)
                total_to_end_of_mixing_s = None
                if dosypka_confirm_time:
                    try:
                        dt = dosypka_confirm_time
                        if isinstance(dt, str):
                            dt = datetime.fromisoformat(dt)
                        end_of_mixing = dt + timedelta(minutes=5.0)
                        total_to_end_of_mixing_s = secs_between(szarza_time, end_of_mixing)
                    except Exception:
                        total_to_end_of_mixing_s = None

                szarze_details.append({
                    'plan_id': plan_id,
                    'produkt': produkt,
                    'szarza_id': szarza_id,
                    'szarza_time': szarza_time,
                    'uwagi': szarza_uwagi,
                    'szarza_time_fmt': szarza_time_fmt,
                    'szarza_duration_s': szarza_duration_s,
                    'szarza_to_dosypka_s': szarza_to_dosypka_s,
                    'dosypka_add_to_confirm_s': dosypka_add_to_confirm_s,
                    'dosypka_confirm_time': dosypka_confirm_time,
                    'dosypka_confirm_time_fmt': dosypka_confirm_time_fmt,
                    'total_to_end_of_mixing_s': total_to_end_of_mixing_s
                })

                # extend last appended dict with dosypki sequence info
                try:
                    szarze_details[-1].update({
                        'dosypki_order_times': dosypki_order_times_fmt,
                        'dosypki_intervals_s': dosypki_intervals_s,
                        'start_to_first_dosypka_s': start_to_first_s,
                        'dosypki_nazwy': dosypki_nazwy
                    })
                except Exception:
                    pass

        # Filtering and pagination for szarze_details
        page = 1
        per_page = 20
        try:
            page = int(request.args.get('sz_page', 1))
        except Exception:
            page = 1
        try:
            per_page = int(request.args.get('sz_per_page', 20))
        except Exception:
            per_page = 20

        filter_plan = request.args.get('sz_filter_plan')
        filter_product = request.args.get('sz_filter_product')
        filter_has_dosypki = request.args.get('sz_filter_has_dosypki')
        filter_no_dosypki = request.args.get('sz_filter_no_dosypki')
        filter_has_uwagi = request.args.get('sz_filter_has_uwagi')
        filter_surowiec = request.args.get('sz_filter_surowiec')

        filtered_details = szarze_details
        if filter_plan:
            try:
                pid = int(filter_plan)
                filtered_details = [s for s in filtered_details if s.get('plan_id') == pid]
            except Exception:
                pass
        if filter_product:
            fp = filter_product.strip().lower()
            filtered_details = [s for s in filtered_details if s.get('produkt') and fp in s.get('produkt').lower()]
        # Filter: has dosypki / no dosypki
        if filter_has_dosypki == '1':
            filtered_details = [s for s in filtered_details if s.get('dosypki_order_times') and len(s.get('dosypki_order_times')) > 0]
        if filter_no_dosypki == '1':
            filtered_details = [s for s in filtered_details if not s.get('dosypki_order_times') or len(s.get('dosypki_order_times')) == 0]
        # Filter: has uwagi (notes)
        if filter_has_uwagi == '1':
            filtered_details = [s for s in filtered_details if s.get('uwagi') and str(s.get('uwagi')).strip()]
        # Filter: surowiec name (partial, case-insensitive)
        if filter_surowiec:
            fs = filter_surowiec.strip().lower()
            if fs:
                def has_surowiec(s):
                    names = s.get('dosypki_nazwy') or []
                    for n in names:
                        try:
                            if n and fs in n.lower():
                                return True
                        except Exception:
                            continue
                    return False
                filtered_details = [s for s in filtered_details if has_surowiec(s)]

        total_items = len(filtered_details)
        total_pages = max(1, (total_items + per_page - 1) // per_page)
        if page < 1: page = 1
        if page > total_pages: page = total_pages
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paged_szarze = filtered_details[start_idx:end_idx]

    finally:
        try:
            conn.close()
        except Exception:
            pass

    return render_template('podsumowanie_szarz.html', results=results, averages=averages, period=period, qdate=qdate, grouped_summary=grouped_summary, szarze_details=paged_szarze, szarze_total=total_items, szarze_page=page, szarze_per_page=per_page, szarze_total_pages=total_pages, szarze_filter_plan=filter_plan, szarze_filter_product=filter_product)


@warehouse_bp.route('/podsumowanie_szarz.csv', methods=['GET'])
@roles_required('planista', 'lider', 'admin')
def podsumowanie_szarz_csv():
    """Return CSV export for the same query as podsumowanie_szarz."""
    period = request.args.get('period', 'day')
    qdate_str = request.args.get('date')
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    qdate = None
    start = None
    end = None
    if start_str and end_str:
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                start = datetime.strptime(start_str, fmt).date()
                break
            except Exception:
                continue
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                end = datetime.strptime(end_str, fmt).date()
                break
            except Exception:
                continue
        if start:
            qdate = start
    if not qdate:
        if qdate_str:
            for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
                try:
                    qdate = datetime.strptime(qdate_str, fmt).date()
                    break
                except Exception:
                    continue
        if not qdate:
            qdate = date.today()

    from datetime import timedelta
    if start and end:
        end = end + timedelta(days=1)
    else:
        if period == 'day':
            start = qdate
            end = qdate + timedelta(days=1)
        elif period == 'week':
            start = qdate - timedelta(days=qdate.weekday())
            end = start + timedelta(days=7)
        elif period == 'month':
            start = qdate.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
        elif period == 'quarter':
            q = (qdate.month - 1) // 3
            start_month = q * 3 + 1
            start = qdate.replace(month=start_month, day=1)
            if start_month + 3 > 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start_month + 3)
        elif period == 'year':
            start = qdate.replace(month=1, day=1)
            end = start.replace(year=start.year + 1)
        else:
            start = qdate
            end = qdate + timedelta(days=1)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT p.id, p.produkt, p.data_planu, p.real_start,
                (SELECT s.data_dodania FROM szarze s WHERE s.plan_id=p.id ORDER BY s.data_dodania ASC LIMIT 1) AS first_szarza_time,
                (SELECT d.data_potwierdzenia FROM dosypki d WHERE d.plan_id=p.id AND d.szarza_id = (SELECT s2.id FROM szarze s2 WHERE s2.plan_id=p.id ORDER BY s2.data_dodania ASC LIMIT 1) AND d.potwierdzone=1 AND COALESCE(d.anulowana,0)=0 ORDER BY d.data_potwierdzenia ASC LIMIT 1) AS first_dosypka_confirmed_time,
                (SELECT d.data_zlecenia FROM dosypki d WHERE d.plan_id=p.id AND d.szarza_id = (SELECT s2.id FROM szarze s2 WHERE s2.plan_id=p.id ORDER BY s2.data_dodania ASC LIMIT 1) AND COALESCE(d.anulowana,0)=0 ORDER BY d.data_zlecenia ASC LIMIT 1) AS first_dosypka_order_time,
                (SELECT MIN(s3.data_dodania) FROM szarze s3 WHERE s3.plan_id=p.id AND s3.data_dodania > (SELECT s4.data_dodania FROM szarze s4 WHERE s4.plan_id=p.id ORDER BY s4.data_dodania ASC LIMIT 1)) AS next_szarza_time
            FROM plan_produkcji p
            WHERE p.sekcja='Zasyp' AND p.data_planu >= %s AND p.data_planu < %s
            ORDER BY p.data_planu, p.kolejnosc
            """,
            (start, end)
        )
        rows = cursor.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Build CSV
    import io, csv
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['plan_id', 'produkt', 'data_planu', 'real_start', 'first_szarza_time', 'first_dosypka_order_time', 'szarza_to_dosypka', 'dosypka_add_to_confirm', 'first_dosypka_confirmed_time', 'lab_total_from_szarza', 'mixing_minutes', 'wait_to_next_szarza'])
    for r in rows:
        plan_id = r[0]
        produkt = r[1]
        data_planu = r[2]
        real_start = r[3]
        first_szarza_time = r[4]
        first_dosypka_confirmed_time = r[5]
        first_dosypka_order_time = r[6]
        next_szarza_time = r[7]

        def to_minutes(a, b):
            try:
                if not a or not b:
                    return ''
                if isinstance(a, str):
                    a = datetime.fromisoformat(a)
                if isinstance(b, str):
                    b = datetime.fromisoformat(b)
                return round((b - a).total_seconds() / 60.0, 1)
            except Exception:
                return ''

        def minutes_to_mmss(m):
            if m is None or m == '':
                return ''
            try:
                secs = int(round(float(m) * 60))
                neg = secs < 0
                secs = abs(secs)
                mins = secs // 60
                s = secs % 60
                fmt = f"{mins}:{s:02d}"
                return f"-{fmt}" if neg else fmt
            except Exception:
                return ''

        szarza_minutes = to_minutes(real_start, first_szarza_time)
        szarza_to_dosypka = to_minutes(first_szarza_time, first_dosypka_order_time)
        dosypka_add_to_confirm = to_minutes(first_dosypka_order_time, first_dosypka_confirmed_time)
        lab_minutes = to_minutes(first_szarza_time, first_dosypka_confirmed_time)
        mixing_minutes = 5.0
        wait_to_next_szarza = ''
        if first_dosypka_confirmed_time and next_szarza_time:
            try:
                dt = first_dosypka_confirmed_time
                if isinstance(dt, str):
                    dt = datetime.fromisoformat(dt)
                end_of_mixing = dt + timedelta(minutes=mixing_minutes)
                if isinstance(next_szarza_time, str):
                    ns = datetime.fromisoformat(next_szarza_time)
                else:
                    ns = next_szarza_time
                wait_to_next_szarza = round((ns - end_of_mixing).total_seconds() / 60.0, 1)
            except Exception:
                wait_to_next_szarza = ''

        # Format minute values to mm:ss for CSV export
        szarza_mmss = minutes_to_mmss(szarza_minutes)
        szarza_to_dosypka_mmss = minutes_to_mmss(szarza_to_dosypka)
        dosypka_add_to_confirm_mmss = minutes_to_mmss(dosypka_add_to_confirm)
        lab_mmss = minutes_to_mmss(lab_minutes)
        mixing_mmss = minutes_to_mmss(mixing_minutes)
        wait_mmss = minutes_to_mmss(wait_to_next_szarza)

        w.writerow([plan_id, produkt, data_planu, real_start or '', first_szarza_time or '', first_dosypka_order_time or '', szarza_to_dosypka_mmss, dosypka_add_to_confirm_mmss, first_dosypka_confirmed_time or '', lab_mmss, mixing_mmss, wait_mmss])

    csv_data = out.getvalue()
    return current_app.response_class(csv_data, mimetype='text/csv', headers={
        'Content-Disposition': f'attachment; filename=podsumowanie_szarz_{period}_{qdate}.csv'
    })


@warehouse_bp.route('/potwierdz_palete_page/<int:paleta_id>', methods=['GET'])
@login_required
def potwierdz_palete_page(paleta_id):
    """Render form for confirming paleta acceptance"""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia).upper()
    table_pal = get_table_name('palety_workowanie', linia)
    conn = get_db_connection()
    cursor = conn.cursor()
    waga = None
    try:
        cursor.execute(f"SELECT waga, waga_brutto, tara FROM {table_pal} WHERE id=%s", (paleta_id,))
        row = cursor.fetchone()
        if row:
            waga = row[0]
    except Exception as e:
        current_app.logger.error(f'Failed to load paleta {paleta_id} for potwierdz_palete_page: {e}', exc_info=True)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return render_template('potwierdz_palete.html', paleta_id=paleta_id, waga=waga, linia=linia)


@warehouse_bp.route('/potwierdz_palete/<int:paleta_id>', methods=['POST'])
@login_required
def potwierdz_palete(paleta_id):
    """Confirm paleta acceptance with warehouse manager/lider"""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    table_plan = get_table_name('plan_produkcji', linia)
    table_pal = get_table_name('palety_workowanie', linia)
    table_mag = get_table_name('magazyn_palety', linia)
    
    role = session.get('rola', '')
    if role not in ['magazynier', 'lider', 'admin']:
        current_app.logger.warning(f'[WAREHOUSE-AUTH] User {session.get("login")} with role={role} tried to confirm paleta {paleta_id} - insufficient permissions')
        return jsonify({'success': False, 'message': 'Brak uprawnień do zatwierdzania palet'}), 403
    
    # Initialize variables that will be used in response (scope fix)
    provided_netto = None
    provided_brutto = None
    deklarowana_waga = None
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Step 1: Ensure column exists (idempotent)
        try:
            cursor.execute(f"ALTER TABLE {table_pal} ADD COLUMN status VARCHAR(32) DEFAULT 'do_przyjecia'")
            conn.commit()
        except Exception as e:
            current_app.logger.debug(f'ALTER TABLE potwierdz_palete: {e}')
            try: conn.rollback()
            except: pass
        
        # Step 2: Fetch tara (weight of package)
        tara = 25  # default
        try:
            cursor.execute(f"SELECT COALESCE(tara,25) FROM {table_pal} WHERE id=%s", (paleta_id,))
            trow = cursor.fetchone()
            tara = int(trow[0]) if trow and trow[0] is not None else 25
        except Exception as e:
            current_app.logger.warning(f'Failed to fetch tara for paleta {paleta_id}: {e}')
        
        # Step 3: Parse provided weights from form (netto/brutto)
        try:
            if request.form.get('waga_palety'):
                try:
                    provided_netto = int(float(require_field(request.form, 'waga_palety').replace(',', '.')))
                except (ValueError, Exception):
                    provided_netto = None
            elif request.form.get('waga_brutto'):
                try:
                    provided_brutto = int(float(require_field(request.form, 'waga_brutto').replace(',', '.')))
                except (ValueError, Exception):
                    provided_brutto = None
                if provided_brutto is not None:
                    n = provided_brutto - int(tara)
                    provided_netto = n if n >= 0 else 0
        except Exception as e:
            current_app.logger.error(f'Failed to parse provided weight for paleta {paleta_id}: {e}', exc_info=True)
        
        # Step 3b: FETCH DECLARED WEIGHT BEFORE ANY UPDATES (for validation)
        try:
            cursor.execute(f"SELECT waga FROM {table_pal} WHERE id=%s", (paleta_id,))
            drow = cursor.fetchone()
            if drow and drow[0] is not None:
                deklarowana_waga = int(drow[0])
        except Exception as e:
            current_app.logger.debug(f'Failed to fetch declared weight for paleta {paleta_id}: {e}')
        
        # Step 4: Persist provided weights separately
        try:
            if provided_netto is not None:
                cursor.execute(f"UPDATE {table_pal} SET waga_potwierdzona=%s WHERE id=%s", (provided_netto, paleta_id))
            if provided_brutto is not None:
                cursor.execute(f"UPDATE {table_pal} SET waga_brutto=%s WHERE id=%s", (provided_brutto, paleta_id))
            if provided_netto is not None or provided_brutto is not None:
                conn.commit()
        except Exception as e:
            current_app.logger.error(f'Failed to persist weights for paleta {paleta_id}: {e}', exc_info=True)
            try: conn.rollback()
            except: pass
        
        # Step 5: Get plan_id, previous status, and stored weights before update
        prev_status = ''
        plan_id = None
        stored_netto = None
        try:
            cursor.execute(f"SELECT plan_id, COALESCE(status,''), COALESCE(waga_potwierdzona, 0) FROM {table_pal} WHERE id=%s", (paleta_id,))
            prev_row = cursor.fetchone()
            if prev_row:
                plan_id = prev_row[0]
                prev_status = prev_row[1]
                stored_netto = int(prev_row[2] or 0)
        except Exception as e:
            current_app.logger.warning(f'Failed to fetch plan_id/status/weights for paleta {paleta_id}: {e}')
        
        # Step 6: Update paleta status to 'przyjeta' (accepted)
        try:
            cursor.execute(
                f"UPDATE {table_pal} SET status='przyjeta', "
                "data_potwierdzenia = DATE_ADD(data_dodania, INTERVAL TIMESTAMPDIFF(SECOND, data_dodania, NOW()) SECOND), "
                "czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW()), "
                "czas_rzeczywistego_potwierdzenia = SEC_TO_TIME(TIMESTAMPDIFF(SECOND, data_dodania, NOW())) "
                "WHERE id=%s",
                (paleta_id,)
            )
            conn.commit()
        except Exception as e:
            current_app.logger.warning(f'Complex update failed for paleta {paleta_id}: {e}, retrying simple update')
            try:
                cursor.execute(f"UPDATE {table_pal} SET status='przyjeta' WHERE id=%s", (paleta_id,))
                conn.commit()
            except Exception as e2:
                current_app.logger.error(f'Simple status update also failed for paleta {paleta_id}: {e2}', exc_info=True)
                try: conn.rollback()
                except: pass
        
        # Step 6b: Update Magazyn table if plan_id exists
        if plan_id:
            netto_val = provided_netto if provided_netto is not None else stored_netto
            
            try:
                cursor.execute(f"SELECT data_planu, produkt FROM {table_plan} WHERE id=%s", (plan_id,))
                z = cursor.fetchone()
                if z and prev_status != 'przyjeta':
                    # Find existing Magazyn plan id for this date+product
                    cursor.execute(f"SELECT id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' LIMIT 1", (z[0], z[1]))
                    mp = cursor.fetchone()
                    mp_id = mp[0] if mp else None
                    
                    # Prevent duplicate magazyn entries atomically (INSERT IGNORE is race-condition-safe)
                    try:
                        cursor.execute(
                            f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (paleta_id, mp_id, z[0], z[1], netto_val, provided_brutto if provided_brutto is not None else 0, tara, session.get('login'))
                        )
                    except mysql.connector.Error:
                        current_app.logger.debug(f'Database error for paleta {paleta_id} in {table_mag}: ignored if duplicate.')
                        pass
                    
                    if cursor.rowcount > 0:
                        current_app.logger.info('Potwierdzono paletę ID=%s: waga_netto=%s kg, produkt=%s, użytkownik=%s', paleta_id, netto_val, z[1] if len(z) > 1 else '—', session.get('login'))
                        audit_log('Potwierdził paletę', f'ID={paleta_id}, produkt={z[1] if len(z) > 1 else "—"}, waga_netto={netto_val} kg')
                    else:
                        current_app.logger.debug('Paleta ID=%s już jest w magazynie (INSERT IGNORE pominął duplikat), waga=%s kg', paleta_id, netto_val)
                    
                    # Recalculate Magazyn aggregates
                    cursor.execute(
                        f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto),0) FROM {table_mag} WHERE plan_id = {table_plan}.id) WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'",
                        (z[0], z[1])
                    )
                    conn.commit()
            except Exception as e:
                current_app.logger.error(f'Failed to update Magazyn aggregates for paleta {paleta_id}: {e}', exc_info=True)
                try: conn.rollback()
                except: pass
    
    except Exception as e:
        current_app.logger.error(f'Failed to potwierdz palete {paleta_id}: {e}', exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    # Return response (AJAX or redirect)
    try:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Calculate difference for AJAX response
            response_data = {'success': True, 'paleta_id': paleta_id}
            current_app.logger.debug(f'AJAX Response: deklarowana_waga={deklarowana_waga}, provided_netto={provided_netto}')
            if deklarowana_waga is not None and provided_netto is not None:
                difference = abs(provided_netto - deklarowana_waga)
                current_app.logger.debug(f'Difference calculated: {difference}')
                if difference > 1:
                    response_data['has_difference'] = True
                    response_data['difference'] = round(difference, 1)
                    current_app.logger.debug(f'Returning modal response: {response_data}')
            return jsonify(response_data), 200
    except Exception:
        pass
    return redirect(bezpieczny_powrot())




@warehouse_bp.route('/api/bufor', methods=['GET'])
@login_required
def api_bufor():
    """Public API returning bufor entries as JSON (czyta z tabeli bufor z systemem kolejkowania)"""
    from datetime import date as _date
    from app.db import refresh_bufor_queue
    
    out = []
    qdate = request.args.get('data') or str(_date.today())
    # Normalize incoming date formats: accept 'YYYY-MM-DD' or 'DD.MM.YYYY'
    try:
        from datetime import datetime
        try:
            dt = datetime.strptime(qdate, '%Y-%m-%d')
            qdate = dt.date().isoformat()
        except Exception:
            try:
                dt = datetime.strptime(qdate, '%d.%m.%Y')
                qdate = dt.date().isoformat()
            except Exception:
                qdate = str(_date.today())
    except Exception:
        qdate = str(_date.today())
    
    try:
        # Odśwież bufor przed zwróceniem danych
        refresh_bufor_queue()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Pobierz wszystkie wpisy z bufora dla danego dnia, posortowane po kolejce
        cur.execute("""
            SELECT id, zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, 
                   tonaz_rzeczywisty, spakowano, kolejka
            FROM bufor
            WHERE data_planu = %s AND status = 'aktywny'
            ORDER BY kolejka ASC
        """, (qdate,))
        
        rows = cur.fetchall()
        
        for row in rows:
            buf_id, z_id, z_data, z_produkt, z_nazwa, z_typ, z_tonaz, z_spakowano, z_kolejka = row
            
            pozostalo_w_silosie = max(z_tonaz - z_spakowano, 0)
            needs_reconciliation = round((z_spakowano or 0) - (z_tonaz or 0), 1) != 0
            show_in_bufor = (pozostalo_w_silosie > 0) or (z_spakowano and z_spakowano > 0)
            
            if show_in_bufor:
                out.append({
                    'id': z_id,
                    'data': str(z_data),
                    'produkt': z_produkt,
                    'nazwa': z_nazwa,
                    'w_silosie': round(max(pozostalo_w_silosie, 0), 1),
                    'typ_produkcji': z_typ,
                    'zasyp_total': z_tonaz,
                    'spakowano_total': z_spakowano,
                    'kolejka': z_kolejka,
                    'needs_reconciliation': needs_reconciliation,
                    'raw_pozostalo': round(pozostalo_w_silosie, 1)
                })
        
        conn.close()
        
    except Exception as e:
        try: 
            import traceback
            print(f"[ERROR] api_bufor: {e}")
            traceback.print_exc()
            conn.close()
        except Exception: 
            pass
        return jsonify({'bufor': [], 'error': True, 'message': str(e)}), 500

    return jsonify({'bufor': out})


@warehouse_bp.route('/bufor/create_zlecenie', methods=['POST'])
@login_required
@roles_required('planista', 'admin', 'zarzad', 'lider')
def warehouse_bufor_create_zlecenie():
    """Create new Workowanie zlecenie based on buffer remainder (Zasyp.tonaz_rzeczywisty - spakowano).
    
    OPCJA 1 (standardowa): zasyp_id - czyta z Zasypu
    OPCJA 2 (nowa): use_buffer_data=true + zasyp_id - czyta bezpośrednio z bufora 
                    (działa nawet gdy Zasyp jest zamknięty)
    OPCJA 3: workowanie_date (optionalne) - data dla nowego Workowania (domyślnie data z Zasypu/bufora)
    """
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
    except Exception:
        data = request.form.to_dict()
    
    zasyp_id = data.get('zasyp_id')
    use_buffer = data.get('use_buffer_data') == 'true' or data.get('use_buffer_data') == True
    override_work_date = data.get('workowanie_date')  # Np. zmiana daty dla nowego dnia
    
    if not zasyp_id:
        return jsonify({'success': False, 'message': 'Brak zasyp_id'}), 400
    
    try:
        zasyp_id = int(zasyp_id)
    except Exception:
        return jsonify({'success': False, 'message': 'Nieprawidłowy zasyp_id'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if use_buffer:
            # OPCJA 2: Czytaj bezpośrednio z bufora (niezależnie od statusu Zasypu)
            # Aggreguj wszystkie wpisy bufora dla tego Zasypu i data_planu
            cursor.execute("""
                SELECT 
                    zasyp_id,
                    data_planu,
                    produkt,
                    COALESCE(tonaz_rzeczywisty, 0) as tonaz_rzeczywisty,
                    typ_produkcji,
                    COALESCE(nazwa_zlecenia, '') as nazwa_zlecenia,
                    COALESCE(SUM(spakowano), 0) as spakowano
                FROM bufor
                WHERE zasyp_id = %s
                GROUP BY zasyp_id, data_planu, produkt, typ_produkcji, nazwa_zlecenia
                LIMIT 1
            """, (zasyp_id,))
            zasyp_data = cursor.fetchone()
            
            if not zasyp_data:
                conn.close()
                return jsonify({'success': False, 'message': 'Nie znaleziono wpisu w buforze dla tego Zasypu'}), 404
            
            z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa, spakowano = zasyp_data
            # Calculate remainder from buffer directly
            roznicza = (z_tonaz_rz or 0) - spakowano
        else:
            # OPCJA 1 (standardowa): Czytaj z Zasypu
            cursor.execute("""
                SELECT id, data_planu, produkt, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia
                FROM plan_produkcji
                WHERE id = %s AND sekcja = 'Zasyp'
            """, (zasyp_id,))
            zasyp = cursor.fetchone()
            
            if not zasyp:
                conn.close()
                return jsonify({'success': False, 'message': 'Nie znaleziono Zasypu'}), 404
            
            z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa = zasyp
            
            # Get how much was already packed (sum from bufor.spakowano)
            cursor.execute("""
                SELECT SUM(spakowano) FROM bufor
                WHERE zasyp_id = %s AND data_planu = %s
            """, (zasyp_id, z_data))
            
            result = cursor.fetchone()
            spakowano = result[0] or 0 if result else 0
            
            # Calculate remainder: Zasyp.tonaz_rzeczywisty - spakowano
            roznicza = (z_tonaz_rz or 0) - spakowano
        
        # OPCJA 3: Override workowanie date if provided (dla rana następnego dnia)
        work_date = override_work_date if override_work_date else z_data
        
        if roznicza <= 0:
            conn.close()
            return jsonify({'success': False, 'message': 'Nie ma pozostałego towaru do spakowania (różnica <= 0)'}), 400
        
        # Get next sequence number for Workowanie section (dla dnia Workowania)
        cursor.execute("""
            SELECT MAX(kolejnosc) FROM plan_produkcji 
            WHERE data_planu = %s AND sekcja = 'Workowanie'
        """, (work_date,))
        
        result = cursor.fetchone()
        next_kolejnosc = (result[0] or 0) + 1 if result else 1
        
        # Atomically create new Workowanie zlecenie only if one doesn't already exist
        insert_sql = """
            INSERT INTO plan_produkcji
            (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, zasyp_id)
            SELECT %s, 'Workowanie', %s, %s, 'zaplanowane', %s, %s, %s, %s
            FROM DUAL
            WHERE NOT EXISTS (SELECT 1 FROM plan_produkcji WHERE zasyp_id = %s AND sekcja = 'Workowanie')
        """
        params = (
            work_date,
            z_produkt,
            round(roznicza, 1),  # plan = różnica
            next_kolejnosc,
            z_typ or 'worki_zgrzewane_25',
            (z_nazwa or '') + '_BUF',  # Add _BUF suffix to mark buffer origin
            z_id,  # value for zasyp_id column
            z_id   # value for WHERE NOT EXISTS check
        )

        import mysql.connector
        try:
            cursor.execute(insert_sql, params)
        except mysql.connector.IntegrityError as ie:
            # Likely a duplicate-key created by concurrent insert — return existing record gracefully
            try:
                conn.rollback()
            except Exception:
                pass
            cursor.execute("SELECT id FROM plan_produkcji WHERE zasyp_id=%s AND sekcja='Workowanie' LIMIT 1", (z_id,))
            existing = cursor.fetchone()
            existing_id = existing[0] if existing else None
            conn.close()
            return jsonify({
                'success': True,
                'message': 'Zlecenie Workowanie już istnieje',
                'existing_id': existing_id
            }), 200

        # If rowcount==1 then INSERT happened; otherwise another process already created it
        if cursor.rowcount:
            conn.commit()
            new_id = cursor.lastrowid
            conn.close()
            return jsonify({
                'success': True,
                'message': f'Utworzono zlecenie Workowanie z planem {round(roznicza, 1)} kg',
                'new_id': new_id,
                'plan_kg': round(roznicza, 1)
            }), 201
        else:
            # Someone else created the Workowanie for this zasyp_id concurrently — return existing id
            cursor.execute("SELECT id FROM plan_produkcji WHERE zasyp_id=%s AND sekcja='Workowanie' LIMIT 1", (z_id,))
            existing = cursor.fetchone()
            existing_id = existing[0] if existing else None
            conn.close()
            return jsonify({
                'success': True,
                'message': 'Zlecenie Workowanie już istnieje',
                'existing_id': existing_id
            }), 200
        
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.exception('Error in warehouse_bufor_create_zlecenie')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@warehouse_bp.route('/api/start_from_queue/<int:kolejka>', methods=['POST'])
@login_required
def start_from_queue(kolejka):
    """Startu zlecenie z bufora po numerze kolejki"""
    from datetime import datetime as _datetime
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Pobierz wpis z bufora po kolejce - Workowanie połącz na podstawie zasyp_id FK
        cur.execute("""
            SELECT b.zasyp_id, b.data_planu, b.produkt, b.kolejka,
                   w.id as workowanie_id
            FROM bufor b
            LEFT JOIN plan_produkcji w ON w.zasyp_id = b.zasyp_id
                AND w.sekcja = 'Workowanie'
            WHERE b.kolejka = %s AND b.status = 'aktywny'
            LIMIT 1
        """, (kolejka,))
        
        row = cur.fetchone()
        
        if not row:
            return jsonify({'success': False, 'message': f'Nie znaleziono wpisu w bufore z kolejką {kolejka}'}), 404
        
        zasyp_id, data_planu, produkt, buf_kolejka, workowanie_id = row
        
        if not workowanie_id:
            return jsonify({'success': False, 'message': f'Brak odpowiadającego Workowania dla {produkt} na dzień {data_planu}'}), 400
        
        # Zaktualizuj status Workowania na 'w toku' i ustaw real_start
        cur.execute("""
            UPDATE plan_produkcji 
            SET status = 'w toku', real_start = %s
            WHERE id = %s AND sekcja = 'Workowanie'
        """, (_datetime.now(), workowanie_id))
        
        # Oznacz ten wpis bufora jako 'startowany'
        cur.execute("""
            UPDATE bufor 
            SET status = 'startowany'
            WHERE kolejka = %s AND status = 'aktywny'
        """, (kolejka,))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Uruchomiono zlecenie {produkt} (kolejka {buf_kolejka})',
            'workowanie_id': workowanie_id,
            'produkt': produkt,
            'kolejka': buf_kolejka
        }), 200
    
    except Exception as e:
        conn.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
    
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@warehouse_bp.route('/wazenie_magazyn/<int:paleta_id>', methods=['POST'])
@login_required
def wazenie_magazyn(paleta_id):
    """Weigh paleta in warehouse and update weight"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        brutto = int(float(request.form.get('waga_brutto', '0').replace(',', '.')))
    except Exception:
        brutto = 0
    
    cursor.execute("SELECT tara, plan_id FROM palety_workowanie WHERE id=%s", (paleta_id,))
    res = cursor.fetchone()
    if res:
        tara, plan_id = res
        netto = brutto - int(tara)
        if netto < 0: netto = 0
        # Do not overwrite original Workowanie paleta weight here; store brutto
        # for warehouse audit and add netto to Magazyn aggregates only.
        try:
            cursor.execute("UPDATE palety_workowanie SET waga_brutto=%s WHERE id=%s", (brutto, paleta_id))
        except Exception as e:
            current_app.logger.error(f'Failed to store brutto for paleta {paleta_id}: {e}', exc_info=True)
        cursor.execute("SELECT data_planu, produkt FROM plan_produkcji WHERE id=%s", (plan_id,))
        z = cursor.fetchone()
        if z:
            # For magazyn, insert a separate magazyn_palety record (or update existing)
            cursor.execute("SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' LIMIT 1", (z[0], z[1]))
            mp = cursor.fetchone()
            mp_id = mp[0] if mp else None
            cursor.execute("SELECT id FROM magazyn_palety WHERE paleta_workowanie_id=%s", (paleta_id,))
            exists = cursor.fetchone()
            if not exists:
                try:
                    cursor.execute(
                        "INSERT IGNORE INTO magazyn_palety (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (paleta_id, mp_id, z[0], z[1], netto, brutto, tara, session.get('login'))
                    )
                except mysql.connector.IntegrityError:
                    # If duplicate was somehow created concurrently between check and insert
                    pass
            else:
                cursor.execute("UPDATE magazyn_palety SET waga_netto=%s, waga_brutto=%s, tara=%s, data_potwierdzenia=NOW() WHERE paleta_workowanie_id=%s", (netto, brutto, tara, paleta_id))
            cursor.execute(
                "UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto),0) FROM magazyn_palety WHERE plan_id = plan_produkcji.id) WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'",
                (z[0], z[1])
            )
    
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@warehouse_bp.route('/usun_szarze/<int:id>', methods=['POST'])
@roles_required('lider', 'admin')
def usun_szarze(id):
    """Delete szarża from Zasyp section"""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia).upper()
    table_szarze = get_table_name('szarze', linia)
    table_plan = get_table_name('plan_produkcji', linia)
    table_dosypki = get_table_name('dosypki', linia)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT plan_id FROM {table_szarze} WHERE id=%s", (id,))
        res = cursor.fetchone()
        if res:
            plan_id = res[0]
            cursor.execute(f"DELETE FROM {table_szarze} WHERE id=%s", (id,))
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                "WHERE id = %s",
                (plan_id, plan_id, plan_id)
            )
            conn.commit()
    finally:
        conn.close()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Szarża usunięta'}), 200
    
    return redirect(bezpieczny_powrot())


@warehouse_bp.route('/usun_palete/<int:id>', methods=['POST'])
@roles_required('lider', 'admin')
def usun_palete(id):
    """Delete paleta from buffer"""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia).upper()
    table_pal = get_table_name('palety_workowanie', linia)
    table_plan = get_table_name('plan_produkcji', linia)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if paleta exists
        cursor.execute(f"SELECT plan_id FROM {table_pal} WHERE id=%s", (id,))
        res = cursor.fetchone()
        
        if not res:
            msg = f'Paleta ID={id} nie istnieje'
            current_app.logger.warning(f'[WAREHOUSE-DELETE] {msg}')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': msg}), 404
            flash(msg, 'warning')
            return redirect(bezpieczny_powrot())
        
        plan_id = res[0]
        cursor.execute(f"DELETE FROM {table_pal} WHERE id=%s", (id,))
        cursor.execute(f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s", (plan_id, plan_id))
        conn.commit()
        
        current_app.logger.info('Usunięto paletę ID=%s, plan_id=%s, użytkownik=%s', id, plan_id, session.get('login'))
        audit_log('Usunął paletę', f'ID={id}, plan_id={plan_id}')
        msg = 'Paleta usunięta'
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': msg}), 200
        
        flash(msg, 'success')
    except Exception as e:
        current_app.logger.error(f'[WAREHOUSE-DELETE] Error deleting paleta {id}: {e}', exc_info=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
        flash(f'Błąd przy usuwaniu palety: {str(e)}', 'danger')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    return redirect(bezpieczny_powrot())


@warehouse_bp.route('/edytuj_palete/\u003cint:paleta_id\u003e', methods=['POST'])
@roles_required('magazynier', 'lider', 'admin')
def edytuj_palete(paleta_id):
    """Edit paleta weight (netto)"""
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia).upper()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            waga = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
        except Exception:
            waga = 0

        result = _update_paleta_workowanie(cursor, paleta_id, waga, linia=linia)
        if not result.get('found'):
            msg = f'Paleta ID={paleta_id} nie istnieje'
            current_app.logger.warning(f'[WAREHOUSE-EDIT] {msg}')
            flash(msg, 'warning')
            return redirect(bezpieczny_powrot())

        conn.commit()
        current_app.logger.info('Edytowano paletę ID=%s, waga=%s kg, użytkownik=%s', paleta_id, waga, session.get('login'))
        audit_log('Edytował paletę', f'ID={paleta_id}, waga={waga} kg')
        flash(f'Paleta zaktualizowana (waga={waga}kg)', 'success')
    except Exception as e:
        current_app.logger.error(f'[WAREHOUSE-EDIT] Failed to edit paleta {paleta_id}: {e}', exc_info=True)
        flash(f'Błąd przy edytowaniu palety: {str(e)}', 'danger')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return redirect(bezpieczny_powrot())


@warehouse_bp.route('/api/edytuj_palete_ajax', methods=['POST'])
@roles_required('magazynier', 'produkcja', 'lider', 'admin')
def edytuj_palete_ajax():
    """AJAX: Edytuj wagę palety w magazyn_palety (tylko potwierdzone w magazynie)."""
    data = request.get_json(force=True) or {}
    paleta_id = data.get('id')
    nowa_waga = data.get('waga')
    try:
        paleta_id = int(paleta_id)
        nowa_waga = int(float(str(nowa_waga).replace(',', '.')))
    except Exception:
        return jsonify({'success': False, 'message': 'Nieprawidłowe dane'}), 400

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        result = _update_paleta_magazyn(cursor, paleta_id, nowa_waga)
        if not result.get('found'):
            msg = f'Paleta ID={paleta_id} nie istnieje w magazynie lub nie została potwierdzona'
            current_app.logger.warning(f'[WAREHOUSE-AJAX-EDIT] {msg}')
            return jsonify({'success': False, 'message': msg}), 404

        conn.commit()
        plan_id = result.get('plan_id')
        current_app.logger.info('Edytowano paletę (AJAX) ID=%s, waga=%s kg, użytkownik=%s', paleta_id, nowa_waga, session.get('login'))
        audit_log('Edytował paletę (magazyn)', f'ID={paleta_id}, waga={nowa_waga} kg, plan_id={plan_id}')
        return jsonify({'success': True, 'message': f'Waga zaktualizowana ({nowa_waga}kg)'})
    except Exception as e:
        current_app.logger.exception(f'[WAREHOUSE-AJAX-EDIT] Failed to edit paleta {paleta_id}: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@warehouse_bp.route('/api/usun_palete_ajax', methods=['POST'])
@roles_required('produkcja', 'lider', 'admin')
def usun_palete_ajax():
    """AJAX: Usuń paletę tylko z magazyn_palety (potwierdzone w magazynie)."""
    data = request.get_json(force=True) or {}
    paleta_id = data.get('id')
    try:
        paleta_id = int(paleta_id)
    except Exception:
        return jsonify({'success': False, 'message': 'Nieprawidłowe id'}), 400

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Tylko usuń palety z magazyn_palety (potwierdzone)
        cursor.execute("SELECT plan_id, paleta_workowanie_id FROM magazyn_palety WHERE id=%s", (paleta_id,))
        row = cursor.fetchone()
        
        if not row:
            msg = f'Paleta ID={paleta_id} nie istnieje w magazynie lub nie została potwierdzona'
            current_app.logger.warning(f'[WAREHOUSE-AJAX-DELETE] {msg}')
            return jsonify({'success': False, 'message': msg}), 404
        
        plan_id = row[0]
        paleta_workowanie_id = row[1] if len(row) > 1 else None
        cursor.execute("DELETE FROM magazyn_palety WHERE id=%s", (paleta_id,))
        # If this magazyn entry pointed to a palety_workowanie row, mark it as no longer confirmed
        try:
            if paleta_workowanie_id:
                cursor.execute(
                    "UPDATE palety_workowanie SET status=%s, data_potwierdzenia=NULL, czas_potwierdzenia_s=NULL, czas_rzeczywistego_potwierdzenia=NULL, waga_potwierdzona=NULL WHERE id=%s",
                    ('zamknieta', paleta_workowanie_id)
                )
        except Exception:
            # Don't block deletion if updating the workowanie row fails
            try:
                current_app.logger.exception('Failed to update palety_workowanie after magazyn delete for paleta_workowanie_id=%s', paleta_workowanie_id)
            except Exception:
                pass
        # Zaktualizuj agregat Magazyn
        cursor.execute(
            "UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto), 0) FROM magazyn_palety WHERE plan_id = %s) WHERE id = %s",
            (plan_id, plan_id)
        )
        
        conn.commit()
        current_app.logger.info('Usunięto paletę z magazynu (AJAX) ID=%s, plan_id=%s, użytkownik=%s', paleta_id, plan_id, session.get('login'))
        audit_log('Usunął paletę z magazynu', f'ID={paleta_id}, plan_id={plan_id}')
        return jsonify({'success': True, 'message': 'Paleta usunięta z magazynu'})
    except Exception as e:
        current_app.logger.exception(f'[WAREHOUSE-AJAX-DELETE] Failed to delete paleta {paleta_id}: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@warehouse_bp.route('/drukuj_etykiete/<int:paleta_id>', methods=['GET'])
@login_required
def drukuj_etykiete(paleta_id):
    """Generates a 100x150 mm printable label for a palette in Magazyn.
    Calculates which 'szarża' the palette belongs to based on cumulative weights.
    """
    from app.db import get_db_connection
    from flask import request, abort, render_template, current_app
    from werkzeug.exceptions import HTTPException
    import datetime

    linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
    linia = str(linia).upper()
    table_plan = get_table_name('plan_produkcji', linia)
    table_pal = get_table_name('palety_workowanie', linia)
    table_szarze = get_table_name('szarze', linia)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Checking if paleta_id belongs to magazyn_palety
        cursor.execute(f'''
            SELECT 
                COALESCE(mp.plan_id, pw.plan_id) AS plan_id,
                mp.waga_netto, 
                COALESCE(p.produkt, pw_p.produkt, mp.produkt) AS produkt,
                mp.paleta_workowanie_id,
                pw.data_dodania
            FROM magazyn_palety mp
            LEFT JOIN {table_plan} p ON mp.plan_id = p.id
            LEFT JOIN {table_pal} pw ON mp.paleta_workowanie_id = pw.id
            LEFT JOIN {table_plan} pw_p ON pw.plan_id = pw_p.id
            WHERE mp.id = %s
        ''', (paleta_id,))
        row = cursor.fetchone()
        
        data_workowanie = None
        
        if row:
            plan_id, paleta_waga, produkt, workowanie_id, pw_data = row
            if pw_data:
                data_workowanie = pw_data.strftime('%Y-%m-%d %H:%M:%S') if hasattr(pw_data, 'strftime') else str(pw_data)
            if plan_id:
                if workowanie_id:
                    cursor.execute(f'''
                        SELECT COALESCE(SUM(waga), 0) 
                        FROM {table_pal}
                        WHERE plan_id = %s AND id <= %s
                    ''', (plan_id, workowanie_id))
                    cumulative_paleta_waga = cursor.fetchone()[0]
                else:
                    cursor.execute('''
                        SELECT COALESCE(SUM(waga_netto), 0) 
                        FROM magazyn_palety 
                        WHERE plan_id = %s AND id <= %s
                    ''', (plan_id, paleta_id))
                    cumulative_paleta_waga = cursor.fetchone()[0]
            else:
                cumulative_paleta_waga = paleta_waga
        else:
            # Fallback for palety_workowanie API calls
            cursor.execute(f'''
                SELECT pw.plan_id, pw.waga, p.produkt, pw.data_dodania, pw.id
                FROM {table_pal} pw
                JOIN {table_plan} p ON pw.plan_id = p.id
                WHERE pw.id = %s
            ''', (paleta_id,))
            row = cursor.fetchone()
            if not row:
                abort(404, description="Paleta nie znaleziona")
                
            work_plan_id, paleta_waga, produkt, pw_data, wk_id = row
            if pw_data:
                data_workowanie = pw_data.strftime('%Y-%m-%d %H:%M:%S') if hasattr(pw_data, 'strftime') else str(pw_data)
                
            plan_id = work_plan_id
            workowanie_id = wk_id
            
            cursor.execute(f'''
                SELECT COALESCE(SUM(waga), 0) 
                FROM {table_pal}
                WHERE plan_id = %s AND id <= %s
            ''', (plan_id, paleta_id))
            cumulative_paleta_waga = cursor.fetchone()[0]

        szarza_nr = "?"
        zasyp_plan_id = None
        
        if plan_id:
            cursor.execute(f'SELECT zasyp_id FROM {table_plan} WHERE id = %s', (plan_id,))
            zasyp_check = cursor.fetchone()
            if zasyp_check and zasyp_check[0]:
                zasyp_plan_id = zasyp_check[0]
            else:
                zasyp_plan_id = plan_id

            cursor.execute(f'''
                SELECT id, waga, nr_szarzy
                FROM {table_szarze}
                WHERE plan_id = %s 
                ORDER BY data_dodania ASC, id ASC
            ''', (zasyp_plan_id,))
            szarze_rows = cursor.fetchall()
            
            cumulative_szarza = 0
            for i, s_row in enumerate(szarze_rows):
                cumulative_szarza += s_row[1]
                szarza_nr = s_row[2] if s_row[2] is not None else (i + 1)
                if cumulative_szarza >= cumulative_paleta_waga:
                    break

        data_wydruku = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

        # Optional expiry date passed as query parameter 'termin'
        termin_przydatnosci = request.args.get('termin') or None

        return render_template('magazyn_etykieta.html',
                       plan_id=zasyp_plan_id or 'Brak',
                       produkt=produkt or 'Nieznany',
                       nr_szarzy=szarza_nr,
                       waga=paleta_waga,
                       nr_palety=workowanie_id if workowanie_id else 'Brak',
                       data_workowanie=data_workowanie or 'Ręczna paleta',
                       data_wydruku=data_wydruku,
                       termin_przydatnosci=termin_przydatnosci)
    except HTTPException:
        # Re-raise standard HTTP escapes, eg abort(404)
        raise
    except Exception as e:
        current_app.logger.exception(f"Error generating label for paleta {paleta_id}: {e}")
        abort(500, description="Wystąpił błąd przy generowaniu etykiety.")
    finally:
        cursor.close()
        conn.close()
