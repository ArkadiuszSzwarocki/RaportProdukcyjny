# routes_zarzad.py
from flask import Blueprint, render_template, request
from datetime import datetime, date, timedelta
from decorators import zarzad_required
from services.stats_service import get_date_range, get_kpi_data, get_chart_data, get_worker_stats
from db import get_db_connection # Do raportów okresowych jeśli nie przeniesione w całości

zarzad_bp = Blueprint('zarzad', __name__)

@zarzad_bp.route('/zarzad')
@zarzad_required
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

    # 1. Oblicz zakres dat (korzystając z serwisu)
    d_od, d_do = get_date_range(tryb, wybrany_rok, wybrany_miesiac, wybrana_data)
    
    # Tytuł (logika prezentacyjna może zostać w widoku lub tutaj)
    tytul = f"Raport: {tryb}" 

    # 2. Pobierz dane z serwisu
    kpi = get_kpi_data(d_od, d_do)
    charts = get_chart_data(d_od, d_do)
    pracownicy_stats = get_worker_stats(d_od, d_do, tryb)

    # Oblicz datę następną dla nawigacji
    try:
        next_date = (date.fromisoformat(str(wybrana_data)) + timedelta(days=1)).isoformat()
    except Exception:
        next_date = str((teraz + timedelta(days=1)).date())

    return render_template(
        'zarzad.html',
        tryb=tryb,
        tytul=tytul,
        wybrany_rok=wybrany_rok,
        wybrany_miesiac=wybrany_miesiac,
        wybrana_data=wybrana_data,
        suma_plan=kpi['plan'],
        suma_wykonanie=kpi['wykonanie'],
        ilosc_zlecen=kpi['ilosc_zlecen'],
        procent=kpi['procent'],
        time_aw=charts['total_downtime'],
        chart_labels=charts['labels'],
        chart_plan=charts['plan'],
        chart_wyk=charts['wyk'],
        pie_labels=charts['pie_labels'],
        pie_values=charts['pie_values'],
        pracownicy_stats=pracownicy_stats,
        next_date=next_date
    )

@zarzad_bp.route('/raporty_okresowe')
@zarzad_required
def raporty_okresowe():
    # Tu również można zastosować stats_service, aby odchudzić kod
    teraz = datetime.now()
    rok = request.args.get('rok', teraz.year, type=int)
    mc = request.args.get('miesiac', teraz.month, type=int)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # ... (oryginalne zapytania SQL lub przeniesione do serwisu) ...
    # Dla skrócenia przykładu zostawiam jak jest, ale rekomenduję przeniesienie do services/stats_service.py
    cursor.execute("SELECT MONTH(data_planu), COALESCE(SUM(COALESCE(tonaz_rzeczywisty, tonaz)), 0) FROM plan_produkcji WHERE YEAR(data_planu)=%s AND status='zakonczone' GROUP BY MONTH(data_planu) ORDER BY MONTH(data_planu)", (rok,))
    trend = cursor.fetchall()
    conn.close()
    
    labels = [['Sty','Lut','Mar','Kwi','Maj','Cze','Lip','Sie','Wrz','Paź','Lis','Gru'][r[0]-1] for r in trend]
    data = [float(r[1]) for r in trend]
    
    # Placeholder na pozostałe dane
    stats = [0, 0, 0] 
    awarie = []

    return render_template('raporty_okresowe.html', rok=rok, miesiac=mc, stats=stats, awarie=awarie, labels_rok=labels, data_rok=data)