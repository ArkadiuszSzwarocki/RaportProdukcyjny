# cspell:words ufeff wydozowan
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
    from flask import abort, Response
    from app.services.periodic_report_service import PeriodicReportService
    import csv
    import io
    now = datetime.now()
    year = request.args.get('rok', now.year, type=int)
    month = request.args.get('miesiac', now.month, type=int)
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        abort(400, description='Wybierz poprawny miesiąc i rok 2000–2100.')
    line = _normalize_line(request.args.get('linia'))
    section = request.args.get('sekcja', 'Zasyp')
    if section not in ('Zasyp','Workowanie'):
        section = 'Zasyp'
    from app.services.warehouse_live_updates import revision, report_channel
    from app.core.database import get_active_database_name
    initial_revision = revision(report_channel(get_active_database_name()))
    report = PeriodicReportService.load(year,month,line,request.args.get('produkt','').strip(),include_live=request.args.get('zakres','live') != 'closed')
    report['revision'] = initial_revision
    if request.args.get('format') == 'json':
        response = jsonify(success=True, report=report)
        response.headers['Cache-Control'] = 'no-store'
        return response
    if request.args.get('format') == 'csv':
        output = io.StringIO()
        writer = csv.writer(output,delimiter=';')
        writer.writerow(['Etap','Hala','Zlecenie','Data planu','Status','Produkt','Plan kg','Wykonanie miesiąca kg','Wykonanie całego zlecenia kg','Zasypy Excel kg','Czas brutto h','Tempo brutto kg/h'])
        for row in report['sections'][section]['details']:
            product = row['product']
            if product.startswith(('=','+','-','@','\t','\r')):
                product = "'" + product
            writer.writerow([section,row['line'],row['id'],row['date'],row['status'],product,row['plan'],row['actual'],row['total_actual'],row['excel'],row['hours'],row['rate']])
        return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={
            'Content-Disposition':f'attachment; filename="Raport_{line}_{section}_{year}-{month:02d}.csv"'})
    return render_template('raporty_okresowe.html',report=report,section=section)


@zarzad_bp.route('/raporty_okresowe/events')
@dynamic_role_required('wyniki')
def periodic_report_events():
    from flask import Response
    from app.core.database import get_active_database_name
    from app.services.warehouse_live_updates import reserve_stream, reserved_stream, report_channel
    release=reserve_stream()
    if release is None:
        return jsonify(success=False),503
    response=Response(reserved_stream(report_channel(get_active_database_name()),release),mimetype='text/event-stream',
        headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
    response.call_on_close(release)
    return response


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



@zarzad_bp.route('/raporty/czasy-wydozowan')
@dynamic_role_required('wyniki')
def dosing_times_report():
    from flask import abort,Response,current_app
    from app.services.dosing_time_report_service import DosingTimeReportService
    from pathlib import Path
    import csv,io,hashlib
    today=date.today()
    try:
        start=date.fromisoformat(request.args.get('od') or today.replace(day=1).isoformat())
        end=date.fromisoformat(request.args.get('do') or today.isoformat())
    except ValueError:
        abort(400,description='Podaj poprawny zakres dat.')
    if start.year<2000 or end.year>2100 or end<start or (end-start).days>366:abort(400,description='Zakres może obejmować maksymalnie 366 dni, w latach 2000–2100.')
    line=_normalize_line(request.args.get('linia'))
    report=DosingTimeReportService.load(start,end,line,request.args.get('zlecenie','').strip())
    if request.args.get('format')=='csv':
        output=io.StringIO();writer=csv.writer(output,delimiter=';')
        writer.writerow(['Hala','Zlecenie','Produkt','Data planu','Szarża','Kolejność procesu','Kolejność START','Etap','Nazwa etapu','START','STOP','Brutto s','Pauzy s','Praca s','Status','Start przez','Stop przez','Powód opóźnienia','Uwagi'])
        for order in report['orders']:
            for batch in order['batches']:
                for stage in batch['stages']:
                    values=[order['line'],order['id'],order['name'],order['date'],batch['number'],stage['sequence'],stage['actual_sequence'],stage['code'],stage['name'],stage['start'],stage['stop'],stage['gross_s'],stage['pause_s'],stage['work_s'],stage['state'],stage['start_login'],stage['stop_login'],stage['reason'],stage['issue']]
                    writer.writerow(["'"+value if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')) else value for value in values])
        return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="Czasy_etapow_{line}_{start}_{end}.csv"'})
    root=Path(current_app.static_folder).parent
    assets=('static/css/periodic_reports.css','static/css/dosing_times.css','static/js/dosing_times.js','templates/production/dosing_times_report.html')
    version=hashlib.sha256(b''.join((root/name).read_bytes() for name in assets)).hexdigest()[:20]
    return render_template('production/dosing_times_report.html',report=report,asset_version=version)
