import csv
import io
from datetime import date, datetime, timedelta

from flask import current_app, render_template, request

from app.db import get_db_connection
from app.decorators import roles_required


def _parse_summary_date(value):
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            continue
    return None


def _resolve_summary_range(args):
    period = args.get('period', 'day')
    qdate = _parse_summary_date(args.get('date')) or date.today()
    start = _parse_summary_date(args.get('start'))
    end = _parse_summary_date(args.get('end'))

    if start and end:
        return period, qdate if qdate else start, start, end + timedelta(days=1)

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
        quarter = (qdate.month - 1) // 3
        start_month = quarter * 3 + 1
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

    return period, qdate, start, end


def _to_datetime(value):
    if not value:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None
    return value


def _minutes_between(a, b):
    start = _to_datetime(a)
    stop = _to_datetime(b)
    if not start or not stop:
        return None
    try:
        return round((stop - start).total_seconds() / 60.0, 1)
    except Exception:
        return None


def _seconds_between(a, b):
    start = _to_datetime(a)
    stop = _to_datetime(b)
    if not start or not stop:
        return None
    try:
        return int(round((stop - start).total_seconds()))
    except Exception:
        return None


def _format_display_dt(value):
    dt = _to_datetime(value)
    if not dt:
        return None
    try:
        return dt.strftime('%d.%m.%Y %H:%M')
    except Exception:
        try:
            return str(value)
        except Exception:
            return None


def _minutes_to_mmss(minutes_value):
    if minutes_value is None or minutes_value == '':
        return ''
    try:
        total_seconds = int(round(float(minutes_value) * 60))
        negative = total_seconds < 0
        total_seconds = abs(total_seconds)
        mins = total_seconds // 60
        secs = total_seconds % 60
        formatted = f"{mins}:{secs:02d}"
        return f"-{formatted}" if negative else formatted
    except Exception:
        return ''


def register_warehouse_summary_routes(warehouse_bp):
    @warehouse_bp.route('/podsumowanie_szarz', methods=['GET'], endpoint='podsumowanie_szarz')
    @warehouse_bp.route('/podsumowanie_zasypow', methods=['GET'], endpoint='podsumowanie_zasypow')
    @roles_required('planista', 'lider', 'admin')
    def podsumowanie_zasypow():
        """Page: summary of zasypy (legacy: szarze) and dosypki durations per zlecenie with period filters."""
        period, qdate, start, end = _resolve_summary_range(request.args)
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

                szarza_minutes = _minutes_between(real_start, first_szarza_time)
                szarza_seconds = _seconds_between(real_start, first_szarza_time)
                szarza_to_dosypka_minutes = _minutes_between(first_szarza_time, first_dosypka_order_time)
                szarza_to_dosypka_seconds = _seconds_between(first_szarza_time, first_dosypka_order_time)
                dosypka_add_to_confirm_minutes = _minutes_between(first_dosypka_order_time, first_dosypka_confirmed_time)
                dosypka_add_to_confirm_seconds = _seconds_between(first_dosypka_order_time, first_dosypka_confirmed_time)
                lab_minutes = _minutes_between(first_szarza_time, first_dosypka_confirmed_time)
                lab_seconds = _seconds_between(first_szarza_time, first_dosypka_confirmed_time)
                mixing_minutes = 5.0

                end_of_mixing = None
                if first_dosypka_confirmed_time:
                    try:
                        end_of_mixing = _to_datetime(first_dosypka_confirmed_time) + timedelta(minutes=mixing_minutes)
                    except Exception:
                        end_of_mixing = None

                wait_to_next_szarza = _minutes_between(end_of_mixing, next_szarza_time) if end_of_mixing else None

                real_start_hms = None
                real_start_dt = _to_datetime(real_start)
                if real_start_dt:
                    try:
                        real_start_hms = real_start_dt.strftime('%H:%M:%S')
                    except Exception:
                        real_start_hms = None

                results.append({
                    'plan_id': plan_id,
                    'produkt': produkt,
                    'data_planu': data_planu,
                    'real_start': real_start,
                    'real_start_fmt': _format_display_dt(real_start),
                    'real_start_hms': real_start_hms,
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

            def avg(field):
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

            szarze_details = []
            for r in rows:
                plan_id = r[0]
                produkt = r[1]
                try:
                    cursor.execute("SELECT id, data_dodania, uwagi FROM szarze WHERE plan_id=%s ORDER BY data_dodania ASC", (plan_id,))
                    szarze_rows = cursor.fetchall()
                except Exception:
                    szarze_rows = []

                try:
                    for item in results:
                        if item.get('plan_id') == plan_id:
                            times = []
                            for idx, srow in enumerate(szarze_rows):
                                sid = srow[0]
                                dt = srow[1]
                                formatted = _format_display_dt(dt)
                                formatted_hms = None
                                dt_value = _to_datetime(dt)
                                if dt_value:
                                    try:
                                        formatted_hms = dt_value.strftime('%H:%M:%S')
                                    except Exception:
                                        formatted_hms = None
                                dosypki_list = []
                                drows = []
                                try:
                                    cursor.execute("SELECT id, data_zlecenia, data_potwierdzenia, nazwa FROM dosypki WHERE plan_id=%s AND szarza_id=%s AND COALESCE(anulowana,0)=0 ORDER BY data_zlecenia ASC", (plan_id, sid))
                                    drows = cursor.fetchall()
                                    for d in drows:
                                        did = d[0]
                                        dz_hms = None
                                        dconf_hms = None
                                        dz_dt = _to_datetime(d[1])
                                        dc_dt = _to_datetime(d[2] if len(d) > 2 else None)
                                        dnazwa = d[3] if len(d) > 3 else None
                                        if dz_dt:
                                            try:
                                                dz_hms = dz_dt.strftime('%H:%M:%S')
                                            except Exception:
                                                dz_hms = None
                                        if dc_dt:
                                            try:
                                                dconf_hms = dc_dt.strftime('%H:%M:%S')
                                            except Exception:
                                                dconf_hms = None
                                        dosypki_list.append({'id': did, 'order_time_hms': dz_hms, 'confirm_time_hms': dconf_hms, 'nazwa': dnazwa})
                                except Exception:
                                    dosypki_list = []

                                szarza_start_hms = None
                                szarza_start_dt = None
                                try:
                                    plan_real_start = None
                                    for it in results:
                                        if it.get('plan_id') == plan_id:
                                            plan_real_start = it.get('real_start')
                                            break
                                    if idx == 0:
                                        prs = _to_datetime(plan_real_start)
                                        if prs:
                                            szarza_start_dt = prs
                                            szarza_start_hms = prs.strftime('%H:%M:%S')
                                    else:
                                        try:
                                            prev_id = szarze_rows[idx - 1][0]
                                            cursor.execute("SELECT MAX(data_potwierdzenia) FROM dosypki WHERE plan_id=%s AND szarza_id=%s AND potwierdzone=1 AND COALESCE(anulowana,0)=0", (plan_id, prev_id))
                                            pv = cursor.fetchone()
                                            prev_conf = pv[0] if pv else None
                                        except Exception:
                                            prev_conf = None
                                        pc = _to_datetime(prev_conf)
                                        if pc:
                                            start_next = pc + timedelta(minutes=4)
                                            szarza_start_dt = start_next
                                            szarza_start_hms = start_next.strftime('%H:%M:%S')
                                except Exception:
                                    szarza_start_hms = None
                                    szarza_start_dt = None

                                whole_szarza_hms = None
                                whole_szarza_seconds = None
                                try:
                                    first_conf = None
                                    if drows:
                                        for d in drows:
                                            if d and len(d) > 2 and d[2]:
                                                first_conf = d[2]
                                                break
                                    fc = _to_datetime(first_conf)
                                    if szarza_start_dt and fc:
                                        end_mix = fc + timedelta(minutes=4)
                                        whole_szarza_seconds = int(round((end_mix - szarza_start_dt).total_seconds()))
                                        sec = abs(whole_szarza_seconds)
                                        h = sec // 3600
                                        m = (sec % 3600) // 60
                                        s = sec % 60
                                        fmt = f"{h:02d}:{m:02d}:{s:02d}"
                                        whole_szarza_hms = f"-{fmt}" if whole_szarza_seconds < 0 else fmt
                                except Exception:
                                    whole_szarza_hms = None
                                    whole_szarza_seconds = None

                                start_to_add_seconds = None
                                start_to_add_hms = None
                                try:
                                    added_dt = _to_datetime(srow[1] if srow and len(srow) > 1 else None)
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
                    szarza_time_fmt = _format_display_dt(szarza_time)
                    try:
                        cursor.execute("SELECT MIN(data_dodania) FROM szarze WHERE plan_id=%s AND data_dodania > %s", (plan_id, szarza_time))
                        ns = cursor.fetchone()
                        next_s = ns[0] if ns else None
                    except Exception:
                        next_s = None

                    try:
                        cursor.execute("SELECT id, data_zlecenia, data_potwierdzenia, nazwa FROM dosypki WHERE plan_id=%s AND szarza_id=%s AND COALESCE(anulowana,0)=0 ORDER BY data_zlecenia ASC", (plan_id, szarza_id))
                        dos_rows = cursor.fetchall()
                    except Exception:
                        dos_rows = []
                    dosypki_order_times = [dr[1] for dr in dos_rows if dr and dr[1]]
                    dosypki_nazwy = [dr[3] for dr in dos_rows if dr and len(dr) > 3 and dr[3]]
                    dosypki_order_times_fmt = [_format_display_dt(dt) for dt in dosypki_order_times]

                    dosypka_order_time = dosypki_order_times[0] if dosypki_order_times else None
                    dosypka_confirm_time = dos_rows[0][2] if dos_rows and dos_rows[0] and len(dos_rows[0]) > 2 else None
                    start_to_first_s = None
                    dosypki_intervals_s = []
                    plan_real_start = None
                    for it in results:
                        if it.get('plan_id') == plan_id:
                            plan_real_start = it.get('real_start')
                            break
                    if dosypki_order_times:
                        start_to_first_s = _seconds_between(plan_real_start, dosypki_order_times[0])
                        for pos in range(1, len(dosypki_order_times)):
                            dosypki_intervals_s.append(_seconds_between(dosypki_order_times[pos - 1], dosypki_order_times[pos]))

                    dosypka_confirm_time_fmt = _format_display_dt(dosypka_confirm_time)
                    szarza_duration_s = _seconds_between(szarza_time, next_s)
                    try:
                        if not next_s and plan_tonaz is not None and abs((plan_tonaz or 0) - 1000) < 0.01 and plan_real_start:
                            szarza_duration_s = _seconds_between(plan_real_start, szarza_time)
                    except Exception:
                        pass
                    szarza_to_dosypka_s = _seconds_between(szarza_time, dosypka_order_time)
                    dosypka_add_to_confirm_s = _seconds_between(dosypka_order_time, dosypka_confirm_time)
                    total_to_end_of_mixing_s = None
                    if dosypka_confirm_time:
                        try:
                            end_of_mixing = _to_datetime(dosypka_confirm_time) + timedelta(minutes=5.0)
                            total_to_end_of_mixing_s = _seconds_between(szarza_time, end_of_mixing)
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
                    try:
                        szarze_details[-1].update({
                            'dosypki_order_times': dosypki_order_times_fmt,
                            'dosypki_intervals_s': dosypki_intervals_s,
                            'start_to_first_dosypka_s': start_to_first_s,
                            'dosypki_nazwy': dosypki_nazwy
                        })
                    except Exception:
                        pass

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
            if filter_has_dosypki == '1':
                filtered_details = [s for s in filtered_details if s.get('dosypki_order_times') and len(s.get('dosypki_order_times')) > 0]
            if filter_no_dosypki == '1':
                filtered_details = [s for s in filtered_details if not s.get('dosypki_order_times') or len(s.get('dosypki_order_times')) == 0]
            if filter_has_uwagi == '1':
                filtered_details = [s for s in filtered_details if s.get('uwagi') and str(s.get('uwagi')).strip()]
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
            if page < 1:
                page = 1
            if page > total_pages:
                page = total_pages
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paged_szarze = filtered_details[start_idx:end_idx]

        finally:
            try:
                conn.close()
            except Exception:
                pass

        return render_template('podsumowanie_szarz.html', results=results, averages=averages, period=period, qdate=qdate, grouped_summary=grouped_summary, szarze_details=paged_szarze, szarze_total=total_items, szarze_page=page, szarze_per_page=per_page, szarze_total_pages=total_pages, szarze_filter_plan=filter_plan, szarze_filter_product=filter_product)

    @warehouse_bp.route('/podsumowanie_szarz.csv', methods=['GET'], endpoint='podsumowanie_szarz_csv')
    @warehouse_bp.route('/podsumowanie_zasypow.csv', methods=['GET'], endpoint='podsumowanie_zasypow_csv')
    @roles_required('planista', 'lider', 'admin')
    def podsumowanie_zasypow_csv():
        """Return CSV export for the same query as podsumowanie_szarz/podsumowanie_zasypow."""
        period, qdate, start, end = _resolve_summary_range(request.args)

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

        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(['plan_id', 'produkt', 'data_planu', 'real_start', 'first_szarza_time', 'first_dosypka_order_time', 'szarza_to_dosypka', 'dosypka_add_to_confirm', 'first_dosypka_confirmed_time', 'lab_total_from_szarza', 'mixing_minutes', 'wait_to_next_szarza'])
        for r in rows:
            real_start = r[3]
            first_szarza_time = r[4]
            first_dosypka_confirmed_time = r[5]
            first_dosypka_order_time = r[6]
            next_szarza_time = r[7]
            mixing_minutes = 5.0

            szarza_minutes = _minutes_between(real_start, first_szarza_time)
            szarza_to_dosypka = _minutes_between(first_szarza_time, first_dosypka_order_time)
            dosypka_add_to_confirm = _minutes_between(first_dosypka_order_time, first_dosypka_confirmed_time)
            lab_minutes = _minutes_between(first_szarza_time, first_dosypka_confirmed_time)
            wait_to_next_szarza = ''
            if first_dosypka_confirmed_time and next_szarza_time:
                try:
                    end_of_mixing = _to_datetime(first_dosypka_confirmed_time) + timedelta(minutes=mixing_minutes)
                    wait_to_next_szarza = round((_to_datetime(next_szarza_time) - end_of_mixing).total_seconds() / 60.0, 1)
                except Exception:
                    wait_to_next_szarza = ''

            writer.writerow([
                r[0],
                r[1],
                r[2],
                real_start or '',
                first_szarza_time or '',
                first_dosypka_order_time or '',
                _minutes_to_mmss(szarza_to_dosypka),
                _minutes_to_mmss(dosypka_add_to_confirm),
                first_dosypka_confirmed_time or '',
                _minutes_to_mmss(lab_minutes),
                _minutes_to_mmss(mixing_minutes),
                _minutes_to_mmss(wait_to_next_szarza),
            ])

        csv_data = out.getvalue()
        return current_app.response_class(csv_data, mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename=podsumowanie_szarz_{period}_{qdate}.csv'
        })