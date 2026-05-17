# routes_zarzad.py
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, date, timedelta
from app.decorators import zarzad_required, dynamic_role_required
from app.services.stats_service import get_date_range, get_kpi_data, get_chart_data, get_worker_stats, get_periodic_reports_data
from app.db import get_db_connection # Do raportów okresowych jeśli nie przeniesione w całości

zarzad_bp = Blueprint('zarzad', __name__)

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
            f"""SELECT p.id, p.produkt, p.tonaz, p.tonaz_rzeczywisty, p.status,
                      p.real_start, p.real_stop, p.typ_zlecenia,
                      COUNT(pal.id) as palety_ilosc,
                      COALESCE(SUM(pal.waga),0) as palety_waga
               FROM {table_plan} p
               LEFT JOIN {table_pal} pal ON p.id = pal.plan_id
               WHERE p.data_planu = %s AND p.sekcja = %s
               GROUP BY p.id
               ORDER BY p.real_start, p.id""",
            (data_obj, sekcja)
        )
        rows = cursor.fetchall()
        zlecenia = []
        for r in rows:
            plan_id, produkt, tonaz, tonaz_rz, status, real_start, real_stop, typ_zl, palety_ilosc, palety_waga = r
            zlecenia.append({
                'id': plan_id,
                'produkt': produkt or '',
                'tonaz_plan': float(tonaz or 0),
                'tonaz_rz': float(tonaz_rz or 0),
                'status': status or '',
                'start': real_start.strftime('%H:%M') if real_start else None,
                'stop': real_stop.strftime('%H:%M') if real_stop else None,
                'typ': typ_zl or '',
                'palety_ilosc': int(palety_ilosc or 0),
                'palety_waga': float(palety_waga or 0),
            })
        return jsonify({'data': data_str, 'sekcja': sekcja, 'linia': linia, 'zlecenia': zlecenia})
    finally:
        conn.close()


@zarzad_bp.route('/raporty_okresowe')
@dynamic_role_required('wyniki')
def raporty_okresowe():
    # Tu również można zastosować stats_service, aby odchudzić kod
    teraz = datetime.now()
    rok = request.args.get('rok', teraz.year, type=int)
    mc = request.args.get('miesiac', teraz.month, type=int)
    linia = request.args.get('linia') or 'PSD'
    
    report_data = get_periodic_reports_data(rok, mc, linia)

    return render_template(
        'raporty_okresowe.html', 
        rok=rok, 
        miesiac=mc, 
        stats=report_data['stats'], 
        awarie=report_data['awarie'], 
        labels_rok=report_data['labels_rok'], 
        data_rok=report_data['data_rok']
    )
