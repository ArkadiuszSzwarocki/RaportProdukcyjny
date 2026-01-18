from flask import Blueprint, render_template, request, redirect, session, url_for
from datetime import date, timedelta, datetime
from db import get_db_connection
from decorators import login_required

planista_bp = Blueprint('planista', __name__)

@planista_bp.route('/planista')
@login_required
def panel_planisty():
    if session.get('rola') not in ['planista', 'admin']:
        return redirect('/')

    data_str = request.args.get('data', str(date.today()))
    try:
        wybrana_data = datetime.strptime(data_str, '%Y-%m-%d').date()
    except:
        wybrana_data = date.today()

    conn = get_db_connection()
    cursor = conn.cursor()

    # --- NOWE: Naprawa kolejności (jeśli są nulle, wstawiamy ID) ---
    # To zapewnia, że stare zlecenia też będą miały numerki
    cursor.execute("UPDATE plan_produkcji SET kolejnosc = id WHERE kolejnosc IS NULL OR kolejnosc = 0")
    conn.commit()

    # --- NOWE ZAPYTANIE SORTUJĄCE PO 'kolejnosc' ---
    # Sortujemy najpierw po tym czy 'w toku' (zawsze góra), a potem ręczna kolejność
    query = """
        SELECT id, sekcja, produkt, tonaz, status, tonaz_rzeczywisty, 
               TIME_FORMAT(real_start, '%H:%i') as start, 
               TIME_FORMAT(real_stop, '%H:%i') as stop,
               kolejnosc
        FROM plan_produkcji 
        WHERE data_planu = %s 
        ORDER BY 
            CASE status WHEN 'w toku' THEN 1 ELSE 2 END, 
            kolejnosc ASC
    """
    cursor.execute(query, (wybrana_data,))
    zlecenia = cursor.fetchall()

    zlecenie_ids = [z[0] for z in zlecenia]
    palety_mapa = {}
    
    if zlecenie_ids:
        format_strings = ','.join(['%s'] * len(zlecenie_ids))
        cursor.execute(f"SELECT plan_id, waga, DATE_FORMAT(data_dodania, '%H:%i') FROM palety_workowanie WHERE plan_id IN ({format_strings}) ORDER BY id DESC", tuple(zlecenie_ids))
        palety = cursor.fetchall()
        for p in palety:
            pid = p[0]
            if pid not in palety_mapa: palety_mapa[pid] = []
            palety_mapa[pid].append({'waga': p[1], 'czas': p[2]})

    conn.close()

    next_date = (wybrana_data + timedelta(days=1)).isoformat()
    prev_date = (wybrana_data - timedelta(days=1)).isoformat()

    return render_template('planista.html', zlecenia=zlecenia, palety_mapa=palety_mapa, wybrana_data=wybrana_data, next_date=next_date, prev_date=prev_date)