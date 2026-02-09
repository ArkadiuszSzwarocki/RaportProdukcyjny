from flask import Blueprint, render_template, request, current_app
from app.db import get_db_connection
from app.dto.paleta import PaletaDTO
from datetime import date
from app.decorators import roles_required
import json
import os

planista_bp = Blueprint('planista', __name__)

def get_processing_times_config():
    """Load workowanie processing times from config JSON file."""
    try:
        cfg_path = os.path.join(current_app.root_path, 'config', 'workowanie_processing_times.json')
        if not os.path.exists(cfg_path):
            # Skip if config doesn't exist - will use fallback
            return None
        with open(cfg_path, 'r') as f:
            data = json.load(f)
        return data.get('processing_times_minutes', {})
    except Exception as e:
        current_app.logger.error(f'Error loading processing times config: {e}')
        return None

def calculate_kg_per_hour(product_type: str) -> int:
    """
    Calculate kg/hour from config file.
    Config file stores: processing_time_minutes (1000kg per X minutes)
    We need to convert to kg/hour for calculation: (1000 / minutes) * 60 = kg/hour
    """
    config = get_processing_times_config()
    
    # Fallback hardcoded normas if config not available
    FALLBACK_NORMY_KG_H = {
        'worki_zgrzewane_25': 3000,  # 1000kg in 20 min = 3000kg/h
        'worki_zgrzewane_20': 3000,  # 1000kg in 20 min = 3000kg/h
        'worki_zszywane_25': 2000,   # 1000kg in 30 min = 2000kg/h
        'worki_zszywane_20': 2000,   # 1000kg in 30 min = 2000kg/h
        'bigbag': 4000,              # 1000kg in 15 min = 4000kg/h
    }
    
    if config is None:
        return FALLBACK_NORMY_KG_H.get(product_type, 3000)
    
    # Get config for this product type
    product_config = config.get(product_type, {})
    if not product_config:
        return FALLBACK_NORMY_KG_H.get(product_type, 3000)
    
    minutes = product_config.get('processing_time_minutes', 20)
    kg_per_1000 = product_config.get('weight_kg', 1000)
    
    # Convert: if 1000kg takes X minutes, then kg/hour = (1000 / X) * 60
    kg_per_hour = int((kg_per_1000 / minutes) * 60) if minutes > 0 else 3000
    return kg_per_hour

@planista_bp.route('/planista', methods=['GET', 'POST'])
@roles_required('planista', 'zarzad', 'lider', 'admin', 'laboratorium')
def panel_planisty():

    conn = get_db_connection()
    cursor = conn.cursor()

    wybrana_data = request.args.get('data', str(date.today()))

    # Include both Zasyp and Czyszczenie entries so planner sees cleaning slots
    cursor.execute("""
        SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
        FROM plan_produkcji 
        WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
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
        norma = calculate_kg_per_hour(typ_prod) if typ_prod else calculate_kg_per_hour('bigbag')
        czas_trwania_min = int((waga_plan / norma) * 60) if norma > 0 else 0

        # Dodajemy obliczony czas do listy p (index 11)
        p.append(czas_trwania_min)

        # 1b. Dla planów Zasyp - pobierz uszkodzone_worki z odpowiadającego planu Workowania
        sekcja = (p[1] or '').lower()
        if sekcja == 'zasyp':
            cursor.execute(
                "SELECT COALESCE(uszkodzone_worki, 0) FROM plan_produkcji WHERE DATE(data_planu)=%s AND sekcja='Workowanie' AND produkt=%s LIMIT 1",
                (wybrana_data, p[2])
            )
            work_result = cursor.fetchone()
            if work_result:
                p[11] = work_result[0]  # Zastąp uszkodzone_worki z Zasyp wartością z Workowania

        # Jeśli to nie jest wpis "Czyszczenie", wliczamy do planu wydajnościowego
        if sekcja != 'czyszczenie':
            suma_plan += waga_plan
            suma_minut_plan += czas_trwania_min

        # 2. POBIERANIE WYKONANIA
        # Dla planów Zasyp: oblicz z szarży (rzeczywistych wpisów)
        # Dla planów innych sekcji: pobierz z planów Workowania/Magazynu
        # For cleaning entries there are no szarze; skip calculation of wykonanie
        plan_id = p[0]
        sekcja = (p[1] or '').lower()
        wykonanie_rzeczywiste = 0
        if sekcja != 'czyszczenie':
            cursor.execute("SELECT SUM(waga) FROM szarze WHERE plan_id = %s", (plan_id,))
            szarze_result = cursor.fetchone()
            wykonanie_rzeczywiste = szarze_result[0] if szarze_result and szarze_result[0] else 0
            # Fallback: jeśli nie ma szarży, użyj tonaz_rzeczywisty z bazy
            if wykonanie_rzeczywiste == 0:
                wykonanie_rzeczywiste = p[8] if p[8] else 0
            p[8] = wykonanie_rzeczywiste
            suma_wyk += wykonanie_rzeczywiste

        # 3. POBIERANIE PALET
        cursor.execute("""
            SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, pp.produkt, pp.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s
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


@planista_bp.route('/planista/add_czyszczenie', methods=['POST'])
@roles_required('planista', 'zarzad', 'lider', 'admin')
def add_czyszczenie():
    """Dodaj wpis "Czyszczenie" do plan_produkcji na konkretną datę i pozycję (kolejnosc)."""
    from flask import request, redirect, url_for, current_app
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        data_planu = request.form.get('data_planu') or (request.json.get('data_planu') if request.json else None)
        tonaz = request.form.get('tonaz') or (request.json.get('tonaz') if request.json else None)
        kolejnosc = request.form.get('kolejnosc') or (request.json.get('kolejnosc') if request.json else None)
        try:
            tonaz_val = float(str(tonaz).replace(',', '.')) if tonaz is not None and tonaz != '' else 0
        except Exception:
            tonaz_val = 0
        try:
            kolejnosc_val = int(kolejnosc) if kolejnosc is not None and kolejnosc != '' else None
        except Exception:
            kolejnosc_val = None

        if not data_planu:
            return ("data_planu required", 400)

        # If kolejnosc specified, shift existing entries to make room
        if kolejnosc_val is not None:
            cursor.execute("UPDATE plan_produkcji SET kolejnosc = kolejnosc + 1 WHERE data_planu = %s AND kolejnosc >= %s", (data_planu, kolejnosc_val))

        insert_sql = ("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_zlecenia) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s)")
        cursor.execute(insert_sql, (data_planu, 'Czyszczenie', 'Czyszczenie', tonaz_val, 'zaplanowane', kolejnosc_val or 9999, 'jakosc'))
        conn.commit()
        return redirect(url_for('planista.panel_planisty', data=data_planu))
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.exception('Error adding czyszczenie: %s', e)
        return (str(e), 500)
    finally:
        try:
            conn.close()
        except Exception:
            pass


@planista_bp.route('/bufor', methods=['GET'])
@roles_required('planista', 'zarzad', 'lider', 'admin', 'laboratorium')
def bufor_page():
    from flask import current_app
    from app.db import refresh_bufor_queue
    
    app_logger = current_app.logger
    app_logger.info(f"[BUFOR] bufor_page() called")
    
    wybrana_data = request.args.get('data', str(date.today()))
    app_logger.info(f"[BUFOR] Starting bufor_page for date {wybrana_data}")
    
    bufor_list = []
    
    try:
        # Odśwież bufor - dodaj nowe zpecenia które się pojawiły
        refresh_bufor_queue()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Czytaj z nowej tabeli bufor - posortowane po kolejce
        cursor.execute("""
            SELECT b.id, b.zasyp_id, b.data_planu, b.produkt, b.nazwa_zlecenia, 
                   b.typ_produkcji, b.tonaz_rzeczywisty, b.spakowano, b.kolejka,
                   z.real_start, z.status
            FROM bufor b
            LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id
            WHERE b.data_planu = %s AND b.status = 'aktywny'
            ORDER BY b.kolejka ASC
        """, (wybrana_data,))
        
        rows = cursor.fetchall()
        app_logger.info(f"[BUFOR] Loaded {len(rows)} active bufor entries for date {wybrana_data}")
        
        for row in rows:
            (buf_id, z_id, z_data, z_produkt, z_nazwa, z_typ, z_tonaz, z_spakowano, 
             z_kolejka, z_real_start, z_status) = row
            
            pozostalo_w_silosie = (z_tonaz or 0) - (z_spakowano or 0)
            needs_reconciliation = round((z_spakowano or 0) - (z_tonaz or 0), 1) != 0
            start_time = z_real_start.strftime('%H:%M') if z_real_start else 'N/A'
            
            bufor_list.append({
                'id': z_id,
                'data': str(z_data),
                'produkt': z_produkt,
                'nazwa': z_nazwa or '',
                'w_silosie': round(max(pozostalo_w_silosie, 0), 1),
                'typ_produkcji': z_typ or '',
                'zasyp_total': z_tonaz or 0,
                'spakowano_total': z_spakowano or 0,
                'kolejka': z_kolejka,
                'needs_reconciliation': needs_reconciliation,
                'raw_pozostalo': round(pozostalo_w_silosie, 1),
                'status': z_status or 'zaplanowane',
                'real_start': z_real_start,
                'start_time': start_time
            })
        
        conn.close()
        
    except Exception as e:
        app_logger.error(f"ERROR in bufor_page for date {wybrana_data}: {type(e).__name__}: {str(e)}", exc_info=True)
        bufor_list = []
    
    return render_template('bufor.html', bufor_list=bufor_list, wybrana_data=wybrana_data)


@planista_bp.route('/bufor/rozlicz', methods=['POST'])
@roles_required('planista', 'lider', 'admin')
def bufor_rozlicz():
    """Endpoint obsługujący rozliczenie zasypu: zapisuje `tonaz_rzeczywisty` i opcjonalnie zamyka zlecenie."""
    from flask import request, redirect
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        plan_id = int(request.form.get('plan_id'))
    except Exception:
        try:
            plan_id = int(request.json.get('plan_id'))
        except Exception:
            plan_id = None
    if not plan_id:
        conn.close()
        return ("Brak plan_id", 400)

    final = request.form.get('final_tonaz') or (request.json.get('final_tonaz') if request.json else None)
    note = request.form.get('note') or (request.json.get('note') if request.json else None)
    close = request.form.get('close') == '1' or (request.json.get('close') if request.json else False)

    try:
        if final is not None and final != '':
            try:
                val = int(float(str(final).replace(',', '.')))
            except Exception:
                val = None
        else:
            val = None

        sql = "UPDATE plan_produkcji SET "
        parts = []
        params = []
        if val is not None:
            parts.append('tonaz_rzeczywisty=%s')
            params.append(val)
        if note:
            parts.append('wyjasnienie_rozbieznosci=%s')
            params.append(note)
        if close:
            parts.append("status='zakonczone'")
            parts.append('real_stop=NOW()')

        if parts:
            sql += ', '.join(parts) + ' WHERE id=%s'
            params.append(plan_id)
            cursor.execute(sql, tuple(params))
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # If called by JS, return JSON success
    try:
        from flask import jsonify
        return jsonify({'ok': True})
    except Exception:
        return redirect('/bufor')


@planista_bp.route('/bufor/archiwizuj', methods=['POST'])
@roles_required('planista', 'lider', 'admin')
def bufor_archiwizuj():
    """Endpoint obsługujący archiwizację zlecenia — zmienia status na 'archiwizowany'."""
    from flask import request, jsonify
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        try:
            plan_id = int(request.json.get('plan_id'))
        except Exception:
            plan_id = None
        
        if not plan_id:
            return jsonify({'ok': False, 'message': 'Brak plan_id'}), 400
        
        # Update status to 'archiwizowany'
        cursor.execute(
            "UPDATE plan_produkcji SET status=%s WHERE id=%s",
            ('archiwizowany', plan_id)
        )
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify({'ok': False, 'message': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

