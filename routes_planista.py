from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from db import get_db_connection
from datetime import date, datetime
from decorators import login_required

planista_bp = Blueprint('planista', __name__)

# --- KONFIGURACJA NORM (KG NA GODZINĘ) ---
# Tutaj możesz dostosować prędkość maszyny
NORMY_KG_H = {
    'standard': 3500,  # 3.5 tony na godzinę (Worki 25kg)
    'bigbag': 5000,    # 5.0 ton na godzinę
    'szycie': 2500     # 2.5 tony na godzinę
}

@planista_bp.route('/planista', methods=['GET', 'POST'])
@login_required
def panel_planisty():
    if session.get('rola') not in ['planista', 'admin', 'zarzad', 'lider']:
        return redirect('/')

    conn = get_db_connection()
    cursor = conn.cursor()

    wybrana_data = request.args.get('data', str(date.today()))

    cursor.execute("""
        SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci 
        FROM plan_produkcji 
        WHERE data_planu = %s AND sekcja = 'Zasyp'
        ORDER BY kolejnosc
    """, (wybrana_data,))
    
    plany = cursor.fetchall()
    plany_list = [list(p) for p in plany] # Lista edytowalna

    palety_mapa = {}
    suma_plan = 0
    suma_wyk = 0
    
    # NOWE ZMIENNE DO CZASU
    suma_minut_plan = 0 
    
    for p in plany_list:
        waga_plan = p[3] if p[3] else 0
        typ_prod = p[9]
        
        # 1. OBLICZANIE CZASU (Waga / Norma * 60 min)
        norma = NORMY_KG_H.get(typ_prod, 3000) # Domyślnie 3000 jeśli nieznany typ
        czas_trwania_min = int((waga_plan / norma) * 60)
        
        # Dodajemy obliczony czas do listy p (index 11)
        p.append(czas_trwania_min) 
        
        suma_plan += waga_plan
        suma_minut_plan += czas_trwania_min

        # 2. POBIERANIE WYKONANIA
        cursor.execute("""
            SELECT SUM(tonaz_rzeczywisty) 
            FROM plan_produkcji 
            WHERE data_planu=%s AND produkt=%s AND typ_produkcji=%s AND sekcja IN ('Workowanie', 'Magazyn')
        """, (wybrana_data, p[2], typ_prod))
        res_wyk = cursor.fetchone()
        wykonanie_rzeczywiste = res_wyk[0] if res_wyk and res_wyk[0] else 0
        
        p[8] = wykonanie_rzeczywiste
        suma_wyk += wykonanie_rzeczywiste

        # 3. POBIERANIE PALET
        cursor.execute("""
            SELECT pw.waga, DATE_FORMAT(pw.data_dodania, '%H:%i'), pw.tara, pw.waga_brutto 
            FROM palety_workowanie pw
            JOIN plan_produkcji pp ON pw.plan_id = pp.id
            WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.typ_produkcji = %s AND pp.sekcja = 'Workowanie'
            ORDER BY pw.id DESC
        """, (wybrana_data, p[2], typ_prod))
        palety_mapa[p[0]] = cursor.fetchall()

    conn.close()

    procent = (suma_wyk / suma_plan * 100) if suma_plan > 0 else 0
    
    # Obliczenie obłożenia zmiany (450 min to 7.5h pracy netto)
    procent_czasu = (suma_minut_plan / 450 * 100)

    return render_template('planista.html', 
                           plany=plany_list, 
                           wybrana_data=wybrana_data, 
                           palety_mapa=palety_mapa,
                           suma_plan=suma_plan,
                           suma_wyk=suma_wyk,
                           procent=procent,
                           suma_minut_plan=suma_minut_plan, # Przekazujemy sumę minut
                           procent_czasu=procent_czasu)     # Przekazujemy % zajętości zmiany