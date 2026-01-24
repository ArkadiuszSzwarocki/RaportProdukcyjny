# services/stats_service.py
from datetime import date, datetime, timedelta
from collections import defaultdict
import json
from db import get_db_connection

def get_date_range(tryb, rok, miesiac, wybrana_data):
    """Oblicza zakres dat na podstawie wybranego trybu."""
    teraz = datetime.now()
    d_od = d_do = None
    
    # Logika dat (wycięta z app.py)
    if tryb == 'dzien':
        d_od = d_do = wybrana_data
    elif tryb == 'tydzien':
        # (Uproszczona logika dla przykładu - w pełnej wersji przenieś tu całą logikę tygodni)
        d_od = teraz.date() - timedelta(days=teraz.weekday())
        d_do = d_od + timedelta(days=6)
    elif tryb == 'miesiac':
        d_od = date(rok, miesiac, 1)
        last_day = (date(rok, miesiac+1, 1) - timedelta(days=1)) if miesiac < 12 else date(rok, 12, 31)
        d_do = last_day
    elif tryb == 'rok':
        d_od = date(rok, 1, 1)
        d_do = date(rok, 12, 31)
        
    return d_od, d_do

def get_kpi_data(d_od, d_do):
    """Pobiera główne wskaźniki KPI."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(SUM(tonaz), 0), 
               COALESCE(SUM(tonaz_rzeczywisty), 0), 
               COUNT(id) 
        FROM plan_produkcji 
        WHERE data_planu BETWEEN %s AND %s AND status='zakonczone' AND COALESCE(typ_zlecenia, '') != 'jakosc'
    """, (d_od, d_do))
    kpi = cursor.fetchone()
    conn.close()
    return {
        'plan': kpi[0],
        'wykonanie': kpi[1],
        'ilosc_zlecen': kpi[2],
        'procent': (kpi[1]/kpi[0]*100) if kpi[0] else 0
    }

def get_chart_data(d_od, d_do):
    """Pobiera dane do wykresów (produkcja i awarie)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Wykres Produkcji
    cursor.execute("""
        SELECT data_planu, SUM(tonaz), SUM(COALESCE(tonaz_rzeczywisty, 0)) 
        FROM plan_produkcji 
        WHERE data_planu BETWEEN %s AND %s AND COALESCE(typ_zlecenia, '') != 'jakosc'
        GROUP BY data_planu ORDER BY data_planu
    """, (d_od, d_do))
    ch = cursor.fetchall()
    
    # Wykres Awarii
    cursor.execute("""
        SELECT kategoria, COALESCE(SUM(TIMESTAMPDIFF(MINUTE, czas_start, czas_stop)), 0) 
        FROM dziennik_zmiany 
        WHERE data_wpisu BETWEEN %s AND %s 
        GROUP BY kategoria
    """, (d_od, d_do))
    dt = cursor.fetchall()
    conn.close()

    return {
        'labels': json.dumps([str(r[0]) for r in ch]),
        'plan': json.dumps([float(r[1]) for r in ch]),
        'wyk': json.dumps([float(r[2]) for r in ch]),
        'pie_labels': json.dumps([r[0] for r in dt]),
        'pie_values': json.dumps([float(r[1]) for r in dt]),
        'total_downtime': sum([float(r[1]) for r in dt])
    }

def get_worker_stats(d_od, d_do, tryb):
    """Generuje statystyki pracownicze."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p_stats = []

    if tryb == 'dzien':
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko")
        all_p = cursor.fetchall()
        p_dict = {p[1]: {'zasyp':'-','workowanie':'-','magazyn':'-','hr':'-'} for p in all_p}
        
        cursor.execute("""
            SELECT p.imie_nazwisko, o.sekcja 
            FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id 
            WHERE o.data_wpisu=%s
        """, (d_od,))
        for r in cursor.fetchall(): 
            if r[1] in ['Zasyp','Workowanie','Magazyn']: 
                p_dict[r[0]][r[1].lower()] = '✅'
                
        cursor.execute("""
            SELECT p.imie_nazwisko, o.typ 
            FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id 
            WHERE o.data_wpisu=%s
        """, (d_od,))
        for r in cursor.fetchall(): 
            p_dict[r[0]]['hr'] = r[1]
            
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]
    else:
        # Logika dla statystyk okresowych (uproszczona)
        cursor.execute("""
            SELECT p.imie_nazwisko, COUNT(o.id) 
            FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id 
            WHERE o.data_wpisu BETWEEN %s AND %s GROUP BY p.imie_nazwisko
        """, (d_od, d_do))
        p_dict = defaultdict(lambda: {'total':0,'abs':0,'ot':0})
        for r in cursor.fetchall(): 
            p_dict[r[0]]['total'] = r[1]
            
        # ... (reszta logiki HR dla okresu) ...
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]
        p_stats.sort(key=lambda x: x['total'], reverse=True)

    conn.close()
    return p_stats