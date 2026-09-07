# routes_zarzad.py
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, date, timedelta
from app.decorators import zarzad_required, dynamic_role_required
from app.services.stats_service import get_date_range, get_kpi_data, get_chart_data, get_worker_stats
from app.db import get_db_connection # Do raportów okresowych jeśli nie przeniesione w całości
from app.services.machine_telemetry_service import MachineTelemetryService

zarzad_bp = Blueprint('zarzad', __name__)


def _normalize_line(raw_line: str) -> str:
    line = str(raw_line or 'AGRO').strip().upper()
    return line if line in ('AGRO', 'PSD', 'ALL') else 'AGRO'

@zarzad_bp.route('/zarzad')
@dynamic_role_required('wyniki')
def zarzad_panel():
    teraz = datetime.now()
    tryb = request.args.get('tryb', 'miesiac')
    
    # Pomocnicza funkcja wewnętrzna
    def get_arg_int(key, default):
        val = request.args.get(key)
        try:
            return int(val)
        except Exception:
            return default

    wybrany_rok = get_arg_int('rok', teraz.year)
    wybrany_miesiac = get_arg_int('miesiac', teraz.month)
    wybrana_data = request.args.get('data') or str(teraz.date())
    linia = request.args.get('linia') or 'PSD'

    # 1. Oblicz zakres dat (korzystając z serwisu)
    d_od, d_do = get_date_range(tryb, wybrany_rok, wybrany_miesiac, wybrana_data)
    
    # 2. Pobierz dane z serwisu (przekazując linia)
    kpi = get_kpi_data(d_od, d_do, linia=linia)
    charts = get_chart_data(d_od, d_do, linia=linia)
    pracownicy_stats = get_worker_stats(d_od, d_do, tryb, linia=linia)

    # Oblicz datę następną dla nawigacji
    try:
        next_date = (date.fromisoformat(str(wybrana_data)) + timedelta(days=1)).isoformat()
    except Exception:
        next_date = str((teraz + timedelta(days=1)).date())

    return render_template(
        'zarzad.html',
        tryb=tryb,
        tytul=f"Raport {linia}: {tryb}",
        wybrany_rok=wybrany_rok,
        wybrany_miesiac=wybrany_miesiac,
        wybrana_data=wybrana_data,
        linia=linia,
        suma_plan=kpi['plan'],
        suma_wykonanie=kpi['wykonanie'],
        ilosc_zlecen=kpi['ilosc_zlecen'],
        procent=kpi['procent'],
        time_aw=charts['total_downtime'],
        chartLabels=charts['labels'],
        chartPlan=charts['plan'],
        chartZasyp=charts['wyk'],
        chartWork=charts.get('work', []),
        pieLabels=charts['pie_labels'],
        pieValues=charts['pie_values'],
        pracownicy_stats=pracownicy_stats,
        next_date=next_date
    )


@zarzad_bp.route('/zarzad/live-line')
@dynamic_role_required('wyniki')
def zarzad_live_line():
    """Dedicated live management dashboard for production line monitoring."""
    linia = _normalize_line(request.args.get('linia'))
    return render_template('zarzad_live_line.html', linia=linia)


@zarzad_bp.route('/zarzad/live-line/api')
@dynamic_role_required('wyniki')
def zarzad_live_line_api():
    """JSON feed for the dedicated live management dashboard."""
    linia = _normalize_line(request.args.get('linia'))
    data = MachineTelemetryService.get_live_dashboard_data()

    machines = data.get('machines') or {}
    bagger = machines.get('bagger') or {}
    palletizer = machines.get('palletizer') or {}
    wrapper = machines.get('wrapper') or {}
    broker = data.get('broker') or {}
    order = data.get('active_order') or {}

    response = {
        'success': True,
        'linia': linia,
        'timestamp_iso': data.get('timestamp_iso'),
        'broker': {
            'is_connected': bool(broker.get('is_connected', False)),
            'time_since_update_sec': broker.get('time_since_update_sec', 0),
            'messages_total': broker.get('messages_total', 0),
            'topics_seen': broker.get('topics_seen') or [],
        },
        'order': {
            'plan_id': order.get('plan_id', 0),
            'product_name': order.get('product_name', ''),
            'batch_number': order.get('batch_number', ''),
            'status': order.get('status', ''),
        },
        'kpi': {
            'wydajnosc_bpm': bagger.get('bpm', 0),
            'ton_per_hour': bagger.get('tons_per_hour', 0),
            'worki_licznik_global': bagger.get('counter_global', 0),
            'palety_licznik_global': palletizer.get('pallets_completed_global', 0),
            'ulozone_worki': palletizer.get('accumulated_bags', 0),
            'target_worki_na_palete': palletizer.get('total_target_bags', 0),
            'postep_palety_percent': palletizer.get('pallet_progress_percent', 0),
        },
        'line_state': {
            'pakowaczka_status': bagger.get('status', 'OFFLINE'),
            'paletyzator_status': palletizer.get('status', 'OFFLINE'),
            'owijarka_status': wrapper.get('status', 'OFFLINE'),
            'warstwa': palletizer.get('current_layer', 0),
            'worek_na_warstwie': palletizer.get('current_bag', 0),
            'obracak_aktywny': bool(palletizer.get('turner_active', False)),
            'popychacz_aktywny': bool(palletizer.get('pusher_active', False)),
            'oproznianie': bool(palletizer.get('is_emptying', False)),
            'sygnal_start_owijarki': bool(palletizer.get('wrapper_start_signal', False)),
            'owijanie_postep_percent': wrapper.get('progress_percent', 0),
            'owijanie_faza': wrapper.get('phase_code', 'IDLE'),
            'paleta_owinieta': bool(wrapper.get('is_wrapped', False)),
            'rolki1zajete': bool(palletizer.get('roller_1_occupied', False)),
            'rolki2zajete': bool(palletizer.get('roller_2_occupied', False)),
            'buforPelny': bool(palletizer.get('buffer_full', False)),
        },
        'stations': data.get('pallet_stations') or [],
        'recent_errors': data.get('recent_errors') or [],
    }
    return jsonify(response)

@zarzad_bp.route('/zarzad/dzien_szczegoly')
@dynamic_role_required('wyniki')
def dzien_szczegoly():
    """Zwraca JSON ze zleceniami produkcyjnymi dla podanej daty i sekcji."""
    data_str = request.args.get('data', str(date.today()))
    sekcja = request.args.get('sekcja', 'Zasyp')
    linia = request.args.get('linia') or 'PSD'
    try:
        data_obj = date.fromisoformat(data_str)
    except ValueError:
        return jsonify({'error': 'Nieprawidłowy format daty'}), 400

    conn = get_db_connection()
    from app.db import get_table_name
    table_plan = get_table_name('plan_produkcji', linia)
    table_pal = get_table_name('palety_workowanie', linia)
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""SELECT id, produkt, tonaz, tonaz_rzeczywisty, status,
                      real_start, real_stop, typ_zlecenia
               FROM {table_plan}
               WHERE data_planu = %s AND sekcja = %s
               ORDER BY real_start, id""",
            (data_obj, sekcja)
        )
        rows = cursor.fetchall()
        zlecenia = []
        for r in rows:
            plan_id, produkt, tonaz, tonaz_rz, status, real_start, real_stop, typ_zl = r
            cursor.execute(
                f"SELECT COUNT(1), COALESCE(SUM(waga),0) FROM {table_pal} WHERE plan_id=%s",
                (plan_id,)
            )
            pal = cursor.fetchone()
            zlecenia.append({
                'id': plan_id,
                'produkt': produkt or '',
                'tonaz_plan': float(tonaz or 0),
                'tonaz_rz': float(tonaz_rz or 0),
                'status': status or '',
                'start': real_start.strftime('%H:%M') if real_start else None,
                'stop': real_stop.strftime('%H:%M') if real_stop else None,
                'typ': typ_zl or '',
                'palety_ilosc': int(pal[0] or 0),
                'palety_waga': float(pal[1] or 0),
            })
        return jsonify({'data': data_str, 'sekcja': sekcja, 'linia': linia, 'zlecenia': zlecenia})
    finally:
        conn.close()


@zarzad_bp.route('/raporty_okresowe')
@dynamic_role_required('wyniki')
def raporty_okresowe():
    import os
    from flask import send_from_directory
    from app.repositories.downtime_repository import DowntimeRepository
    from app.db import get_table_name

    teraz = datetime.now()
    rok = request.args.get('rok', teraz.year, type=int)
    mc = request.args.get('miesiac', teraz.month, type=int)
    linia = (request.args.get('linia') or 'AGRO').strip().upper()
    if linia not in ['AGRO', 'PSD', 'ALL']:
        linia = 'AGRO'

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Trend roczny
    if linia == 'ALL':
        t_agro = get_table_name('plan_produkcji', 'AGRO')
        t_psd = get_table_name('plan_produkcji', 'PSD')
        cursor.execute(f"""
            SELECT m, SUM(tonaz) as suma FROM (
                SELECT MONTH(data_planu) as m, COALESCE(SUM(COALESCE(tonaz_rzeczywisty, tonaz)), 0) as tonaz
                FROM {t_agro} WHERE YEAR(data_planu)=%s AND status='zakonczone' GROUP BY MONTH(data_planu)
                UNION ALL
                SELECT MONTH(data_planu) as m, COALESCE(SUM(COALESCE(tonaz_rzeczywisty, tonaz)), 0) as tonaz
                FROM {t_psd} WHERE YEAR(data_planu)=%s AND status='zakonczone' GROUP BY MONTH(data_planu)
            ) as t GROUP BY m ORDER BY m
        """, (rok, rok))
    else:
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(f"""
            SELECT MONTH(data_planu) as m, COALESCE(SUM(COALESCE(tonaz_rzeczywisty, tonaz)), 0) as suma
            FROM {table_plan} WHERE YEAR(data_planu)=%s AND status='zakonczone' GROUP BY MONTH(data_planu) ORDER BY MONTH(data_planu)
        """, (rok,))
    
    trend_rows = cursor.fetchall() or []
    trend_dict = {int(r['m']): float(r['suma'] or 0) for r in trend_rows}

    months_pl = ['Sty', 'Lut', 'Mar', 'Kwi', 'Maj', 'Cze', 'Lip', 'Sie', 'Wrz', 'Paź', 'Lis', 'Gru']
    labels = months_pl
    data = [trend_dict.get(i, 0.0) for i in range(1, 13)]

    # 2. Statystyki wybranego miesiąca
    if linia == 'ALL':
        t_agro = get_table_name('plan_produkcji', 'AGRO')
        t_psd = get_table_name('plan_produkcji', 'PSD')
        cursor.execute(f"""
            SELECT COUNT(1) as zlecenia_cnt, COALESCE(SUM(COALESCE(tonaz_rzeczywisty, tonaz)), 0) as tonaz_sum
            FROM (
                SELECT tonaz_rzeczywisty, tonaz FROM {t_agro} WHERE YEAR(data_planu)=%s AND MONTH(data_planu)=%s AND status='zakonczone'
                UNION ALL
                SELECT tonaz_rzeczywisty, tonaz FROM {t_psd} WHERE YEAR(data_planu)=%s AND MONTH(data_planu)=%s AND status='zakonczone'
            ) as m
        """, (rok, mc, rok, mc))
    else:
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(f"""
            SELECT COUNT(1) as zlecenia_cnt, COALESCE(SUM(COALESCE(tonaz_rzeczywisty, tonaz)), 0) as tonaz_sum
            FROM {table_plan} WHERE YEAR(data_planu)=%s AND MONTH(data_planu)=%s AND status='zakonczone'
        """, (rok, mc))
    
    month_stat = cursor.fetchone() or {'zlecenia_cnt': 0, 'tonaz_sum': 0}
    stats = [
        int(month_stat.get('zlecenia_cnt') or 0),
        int(month_stat.get('tonaz_sum') or 0),
        0 # Czas awarii obliczany poniżej
    ]

    # 3. Awarie w danym miesiącu
    awarie = []
    total_downtime_min = 0
    try:
        dt_repo = DowntimeRepository()
        date_start = f"{rok}-{mc:02d}-01"
        import calendar
        last_day = calendar.monthrange(rok, mc)[1]
        date_end = f"{rok}-{mc:02d}-{last_day:02d}"

        raw_dts = []
        if linia in ['AGRO', 'ALL']:
            raw_dts.extend(dt_repo.get_downtimes('AGRO', date_start, date_end))
        if linia in ['PSD', 'ALL']:
            raw_dts.extend(dt_repo.get_downtimes('PSD', date_start, date_end))

        # Agregacja awarii
        aggr = {}
        for d in raw_dts:
            kat = d.get('kategoria') or d.get('sekcja') or 'Inne'
            dur = int(d.get('czas_trwania_min') or 0)
            total_downtime_min += dur
            if kat not in aggr:
                aggr[kat] = {'count': 0, 'duration': 0}
            aggr[kat]['count'] += 1
            aggr[kat]['duration'] += dur

        for kat, vals in aggr.items():
            awarie.append([kat, vals['count'], vals['duration']])
    except Exception:
        pass

    stats[2] = total_downtime_min

    # 4. Historia wysłanych raportów e-mail z tabeli auto_report_history
    email_reports_history = []
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auto_report_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data_raportu DATE NOT NULL,
                linia VARCHAR(20) NOT NULL,
                typ_raportu VARCHAR(50) NOT NULL,
                odbiorcy TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_rep (data_raportu, linia, typ_raportu)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        conn.commit()

        q_hist = "SELECT * FROM auto_report_history"
        params_hist = []
        if linia != 'ALL':
            q_hist += " WHERE linia = %s"
            params_hist.append(linia)
        q_hist += " ORDER BY created_at DESC LIMIT 50"

        cursor.execute(q_hist, tuple(params_hist))
        raw_hist = cursor.fetchall() or []

        raporty_dir = 'raporty'
        for h in raw_hist:
            d_str = str(h.get('data_raportu') or '')
            lin = h.get('linia') or 'AGRO'
            pdf_name = f"Raport_{lin}_{d_str}.pdf"
            xls_name = f"Raport_{lin}_{d_str}.xlsx"
            
            created_dt = h.get('created_at')
            created_str = created_dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(created_dt, 'strftime') else str(created_dt)

            email_reports_history.append({
                'id': h.get('id'),
                'data_raportu': d_str,
                'linia': lin,
                'typ_raportu': h.get('typ_raportu') or 'Zmianowy',
                'odbiorcy': h.get('odbiorcy') or '-',
                'created_at': created_str,
                'pdf_filename': pdf_name,
                'xls_filename': xls_name
            })
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()

    return render_template(
        'raporty_okresowe.html',
        rok=rok,
        miesiac=mc,
        linia=linia,
        stats=stats,
        awarie=awarie,
        labels_rok=labels,
        data_rok=data,
        email_reports_history=email_reports_history
    )


@zarzad_bp.route('/raporty/plik/<filename>')
@dynamic_role_required('wyniki')
def pobierz_plik_raportu(filename):
    """Pobiera wygenerowany plik raportu PDF lub Excel z folderu raporty/. Jeśli plik nie istnieje na dysku, generuje go w locie (nawet zerowy)."""
    import os
    import re
    from flask import send_from_directory, abort, current_app
    from scripts.generator_raportow import generuj_paczke_raportow

    safe_name = os.path.basename(filename)
    raporty_dir = os.path.abspath('raporty')
    os.makedirs(raporty_dir, exist_ok=True)
    file_path = os.path.join(raporty_dir, safe_name)

    if not os.path.exists(file_path):
        m = re.match(r'^Raport_([A-Za-z0-9]+)_(\d{4}-\d{2}-\d{2})\.(pdf|xlsx)$', safe_name, re.IGNORECASE)
        if m:
            linia_req = m.group(1).upper()
            data_req = m.group(2)
            try:
                generuj_paczke_raportow(data_req, '', '', linia=linia_req)
            except Exception as e:
                current_app.logger.error(f"[POBIERZ_RAPORT] Błąd generowania w locie dla {safe_name}: {e}")

    if not os.path.exists(file_path):
        abort(404, description="Nie znaleziono pliku raportu i nie udało się go wygenerować.")

    return send_from_directory(raporty_dir, safe_name, as_attachment=True)

