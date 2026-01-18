# routes_planista.py
from flask import Blueprint, render_template, request, redirect, session, url_for
from datetime import date, timedelta, datetime
from db import get_db_connection
from decorators import login_required

planista_bp = Blueprint('planista', __name__)

@planista_bp.route('/planista')
@login_required
def panel_planisty():
    # Sprawdzenie uprawnień (Planista lub Admin)
    if session.get('rola') not in ['planista', 'admin']:
        return redirect('/')

    # Pobranie daty (domyślnie dzisiaj)
    data_str = request.args.get('data', str(date.today()))
    try:
        wybrana_data = datetime.strptime(data_str, '%Y-%m-%d').date()
    except:
        wybrana_data = date.today()

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Pobierz wszystkie zlecenia na dany dzień (w tym NieOpłacone)
    # Sortowanie: Najpierw te w toku, potem zaplanowane, potem nieopłacone, na końcu zakończone
    query = """
        SELECT id, sekcja, produkt, tonaz, status, tonaz_rzeczywisty, 
               TIME_FORMAT(real_start, '%H:%i') as start, 
               TIME_FORMAT(real_stop, '%H:%i') as stop
        FROM plan_produkcji 
        WHERE data_planu = %s 
        ORDER BY 
            CASE status 
                WHEN 'w toku' THEN 1 
                WHEN 'zaplanowane' THEN 2 
                WHEN 'nieoplacone' THEN 3 
                WHEN 'zakonczone' THEN 4 
                ELSE 5 
            END, id ASC
    """
    cursor.execute(query, (wybrana_data,))
    zlecenia = cursor.fetchall()

    # 2. Pobierz palety dla tych zleceń
    zlecenie_ids = [z[0] for z in zlecenia]
    palety_mapa = {}
    
    if zlecenie_ids:
        # Tworzymy string z placeholderami np. %s, %s, %s
        format_strings = ','.join(['%s'] * len(zlecenie_ids))
        cursor.execute(f"SELECT plan_id, waga, DATE_FORMAT(data_dodania, '%H:%i') FROM palety_workowanie WHERE plan_id IN ({format_strings}) ORDER BY id DESC", tuple(zlecenie_ids))
        palety = cursor.fetchall()
        
        # Grupujemy palety po ID zlecenia
        for p in palety:
            pid = p[0]
            if pid not in palety_mapa:
                palety_mapa[pid] = []
            palety_mapa[pid].append({'waga': p[1], 'czas': p[2]})

    conn.close()

    # Data nawigacji
    next_date = (wybrana_data + timedelta(days=1)).isoformat()
    prev_date = (wybrana_data - timedelta(days=1)).isoformat()

    return render_template('planista.html', 
                           zlecenia=zlecenia, 
                           palety_mapa=palety_mapa, 
                           wybrana_data=wybrana_data,
                           next_date=next_date, 
                           prev_date=prev_date)