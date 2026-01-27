from flask import Blueprint, render_template, request
from db import get_db_connection
from dto.paleta import PaletaDTO
from datetime import date
from decorators import roles_required

planista_bp = Blueprint('planista', __name__)

# --- KONFIGURACJA NORM (KG NA GODZINĘ) ---
# Tutaj możesz dostosować prędkość maszyny dla różnych typów opakowań
NORMY_KG_H = {
    'worki_zgrzewane_25': 3500,  # worki zgrzewane 25 kg
    'worki_zgrzewane_20': 3500,  # worki zgrzewane 20 kg (można dopasować)
    'worki_zszywane_25': 2500,   # worki zszywane 25 kg
    'worki_zszywane_20': 2500,   # worki zszywane 20 kg
    'bigbag': 5000,              # BigBag
}

@planista_bp.route('/planista', methods=['GET', 'POST'])
@roles_required('planista', 'zarzad', 'lider', 'admin', 'laboratorium')
def panel_planisty():

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
            SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, pp.produkt, pp.typ_produkcji
            FROM palety_workowanie pw
            JOIN plan_produkcji pp ON pw.plan_id = pp.id
            WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.typ_produkcji = %s AND pp.sekcja = 'Workowanie'
            ORDER BY pw.id DESC
        """, (wybrana_data, p[2], typ_prod))
        raw_pal = cursor.fetchall()
        formatted = []
        for r in raw_pal:
            dto = PaletaDTO.from_db_row(r)
            dt = dto.data_dodania
            try:
                sdt = dt.strftime('%H:%M') if hasattr(dt, 'strftime') else str(dt)
            except Exception:
                sdt = str(dt)
            formatted.append((dto.waga, sdt, dto.tara, dto.waga_brutto))
        palety_mapa[p[0]] = formatted

    conn.close()

    procent = (suma_wyk / suma_plan * 100) if suma_plan > 0 else 0
    
    # Obliczenie obłożenia zmiany (450 min to 7.5h pracy netto)
    procent_czasu = (suma_minut_plan / 450 * 100)

    # Pobierz zlecenia jakościowe zgłoszone na wybraną datę (laboratorium)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, produkt, tonaz, sekcja, status FROM plan_produkcji WHERE data_planu=%s AND (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') AND status != 'zakonczone' ORDER BY id DESC", (wybrana_data,))
        quality_orders = cursor.fetchall()
        quality_count = len(quality_orders)
        conn.close()
    except Exception:
        quality_orders = []
        quality_count = 0

    return render_template('planista.html', 
                           plany=plany_list, 
                           wybrana_data=wybrana_data, 
                           palety_mapa=palety_mapa,
                           suma_plan=suma_plan,
                           suma_wyk=suma_wyk,
                           procent=procent,
                           suma_minut_plan=suma_minut_plan, # Przekazujemy sumę minut
                           procent_czasu=procent_czasu,     # Przekazujemy % zajętości zmiany
                           quality_count=quality_count,
                           quality_orders=quality_orders)