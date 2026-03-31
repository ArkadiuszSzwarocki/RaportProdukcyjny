from flask import Blueprint, render_template, request, current_app, session, jsonify
from app.db import get_db_connection, get_table_name
from app.dto.paleta import PaletaDTO
from app.services.notification_service import notify_workers_about_plan_change
from app.services.planning_service import PlanningService
from datetime import date
from app.decorators import roles_required, dynamic_role_required
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
@dynamic_role_required('planista')
def panel_planisty():

    conn = get_db_connection()
    cursor = conn.cursor()

    wybrana_data = request.args.get('data', str(date.today()))
    wybrana_linia = request.args.get('linia', 'PSD')
 
    # Use PlanningService/DashboardService where possible
    table_plan = get_table_name('plan_produkcji', wybrana_linia)
 
    # Include both Zasyp and Czyszczenie entries so planner sees cleaning slots
    # Exclude ghost carry-over Zasyp records (technical records linked to bufor, not real production)
    query_plans = f"""
        SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
        FROM {table_plan} 
        WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
        ORDER BY kolejnosc
    """
    query_params = [wybrana_data]
    
    cursor.execute(query_plans, tuple(query_params))
    
    plany = cursor.fetchall()
    plany_list = [list(p) for p in plany] # Lista edytowalna

    # DODATKOWO: dołącz wpisy Workowanie jako osobną grupę, tak by były widoczne w UI
    try:
        query_work = f"""
            SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
            FROM {table_plan}
            WHERE data_planu = %s AND LOWER(sekcja) = 'workowanie'
            ORDER BY kolejnosc
        """
        work_params = [wybrana_data]
        
        cursor.execute(query_work, tuple(work_params))
        work_rows = cursor.fetchall()
        for w in work_rows:
            # unikaj duplikatów gdyby rekord już wystąpił (id)
            if any(p[0] == w[0] for p in plany_list):
                continue
            # jeśli istnieje odpowiadający Zasyp dla tego produktu, nie dopisuj Workowania
            prod = (w[2] or '').strip().lower()
            has_zasyp = any(((p[1] or '').strip().lower() == 'zasyp') and ((p[2] or '').strip().lower() == prod) for p in plany_list)
            if has_zasyp:
                # skip: already represented by Zasyp
                continue
            plany_list.append(list(w))
    except Exception:
        current_app.logger.exception('Error loading Workowanie entries for planner')

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
            cursor.execute(f"SELECT COALESCE(uszkodzone_worki, 0) FROM {table_plan} WHERE DATE(data_planu)=%s AND sekcja='Workowanie' AND produkt=%s LIMIT 1", (wybrana_data, p[2]))
            work_result = cursor.fetchone()
            if work_result:
                p[11] = work_result[0]  # Zastąp uszkodzone_worki z Zasyp wartością z Workowania

        # Jeśli to nie jest wpis "Czyszczenie", wliczamy do planu wagowego.
        # Suma minut planu powinna obejmować także wpisy "Czyszczenie",
        # bo zajmują czas zmiany, dlatego dodajemy `suma_minut_plan` zawsze.
        if sekcja != 'czyszczenie':
            suma_plan += waga_plan
        suma_minut_plan += czas_trwania_min

        # 2. POBIERANIE WYKONANIA
        # Dla planów Zasyp: oblicz z szarży (rzeczywistych wpisów) + dosypki potwierdzone
        # Dla planów innych sekcji: pobierz z planów Workowania/Magazynu
        # For cleaning entries there are no szarze; skip calculation of wykonanie
        plan_id = p[0]
        sekcja = (p[1] or '').lower()
        wykonanie_rzeczywiste = 0
        if sekcja != 'czyszczenie':
            table_szarze = get_table_name('szarze', wybrana_linia)
            table_dosypki = get_table_name('dosypki', wybrana_linia)
            cursor.execute(f"SELECT COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) FROM {table_szarze} WHERE plan_id = %s", (plan_id, plan_id))
            szarze_result = cursor.fetchone()
            wykonanie_rzeczywiste = szarze_result[0] if szarze_result and szarze_result[0] else 0
            # Fallback: jeśli nie ma szarży, użyj tonaz_rzeczywisty z bazy
            if wykonanie_rzeczywiste == 0:
                wykonanie_rzeczywiste = p[8] if p[8] else 0
            p[8] = wykonanie_rzeczywiste
            suma_wyk += wykonanie_rzeczywiste

        # 3. POBIERANIE PALET
        table_pal = get_table_name('palety_workowanie', wybrana_linia)
        cursor.execute(f"""
            SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, pp.produkt, pp.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s
            FROM {table_pal} pw
            JOIN {table_plan} pp ON pw.plan_id = pp.id
            WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.sekcja = 'Workowanie'
            ORDER BY pw.id DESC
        """, (wybrana_data, p[2]))
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

    # Zasoby jakościowe (zgłoszone na wybraną datę)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, produkt, tonaz, sekcja, status FROM {table_plan} WHERE data_planu=%s AND (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') AND status != 'zakonczone' ORDER BY id DESC", (wybrana_data,))
        quality_orders = cursor.fetchall()
        quality_count = len(quality_orders)
        conn.close()
    except Exception:
        quality_orders = []
        quality_count = 0

    rola = session.get('rola')
    aktywna_zakladka = request.args.get('tab', 'psd').lower()
    if aktywna_zakladka not in ('psd', 'agro'):
        aktywna_zakladka = 'psd'

    # Prepare for secondary lookups
    palety_mapa = {}
    
    # Process PSD plans (plany_list)
    suma_plan, suma_wyk, suma_minut_plan = 0, 0, 0
    t_szarze_psd = get_table_name('szarze', 'PSD')
    t_dosypki_psd = get_table_name('dosypki', 'PSD')
    t_pal_psd = get_table_name('palety_workowanie', 'PSD')
    t_plan_psd = get_table_name('plan_produkcji', 'PSD')
    
    for p in plany_list:
        w_p = p[3] or 0
        t_p = p[9]
        norma = calculate_kg_per_hour(t_p) if t_p else calculate_kg_per_hour('bigbag')
        dur = int((w_p / norma) * 60) if norma > 0 else 0
        p.append(dur) # index 12
        if p[1].lower() != 'czyszczenie': suma_plan += w_p
        suma_minut_plan += dur
        
        # execution (wyk)
        if p[1].lower() != 'czyszczenie':
            cursor.execute(f"SELECT COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {t_dosypki_psd} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) FROM {t_szarze_psd} WHERE plan_id = %s", (p[0], p[0]))
            sz_r = cursor.fetchone()
            wyk_val = sz_r[0] if sz_r and sz_r[0] else p[8] or 0
            p[8] = wyk_val
            suma_wyk += wyk_val
            
        # palety for details
        cursor.execute(f"SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, pp.produkt, pp.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s FROM {t_pal_psd} pw JOIN {t_plan_psd} pp ON pw.plan_id = pp.id WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.sekcja = 'Workowanie' ORDER BY pw.id DESC", (wybrana_data, p[2]))
        p_rows = cursor.fetchall()
        palety_mapa[p[0]] = [(r[2], (r[5].strftime('%H:%M') if hasattr(r[5], 'strftime') else str(r[5])), r[3], r[4]) for r in p_rows]

    # Process Agro plans
    plany_agro = []
    suma_plan_agro, suma_wyk_agro, suma_minut_plan_agro = 0, 0, 0
    try:
        t_plan_agro = get_table_name('plan_produkcji', 'Agro')
        t_sz_agro = get_table_name('szarze', 'Agro')
        t_ds_agro = get_table_name('dosypki', 'Agro')
        t_pal_agro = get_table_name('palety_workowanie', 'Agro')
        
        cursor.execute(f"SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0) FROM {t_plan_agro} WHERE data_planu = %s ORDER BY kolejnosc", (wybrana_data,))
        agro_raw = cursor.fetchall()
        z_prod_a = {(r[2] or '').strip().lower() for r in agro_raw if r[1].lower() == 'zasyp'}
        
        for r in agro_raw:
            if r[1].lower() == 'workowanie' and (r[2] or '').strip().lower() in z_prod_a: continue
            plany_agro.append(list(r))
            
        for p in plany_agro:
            w_a = p[3] or 0
            t_a = p[9]
            norma_a = calculate_kg_per_hour(t_a) if t_a else calculate_kg_per_hour('bigbag')
            dur_a = int((w_a / norma_a) * 60) if norma_a > 0 else 0
            p.append(dur_a) # index 12
            suma_plan_agro += w_a
            suma_minut_plan_agro += dur_a
            
            # execution Agro
            cursor.execute(f"SELECT COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {t_ds_agro} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) FROM {t_sz_agro} WHERE plan_id = %s", (p[0], p[0]))
            sz_a = cursor.fetchone()
            wyk_a = sz_a[0] if sz_a and sz_a[0] else p[8] or 0
            p[8] = wyk_a
            suma_wyk_agro += wyk_a
            
            # palety Agro (for details)
            cursor.execute(f"SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, pp.produkt, pp.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s FROM {t_pal_agro} pw JOIN {t_plan_agro} pp ON pw.plan_id = pp.id WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.sekcja = 'Workowanie' ORDER BY pw.id DESC", (wybrana_data, p[2]))
            pa_rows = cursor.fetchall()
            palety_mapa[p[0]] = [(r[2], (r[5].strftime('%H:%M') if hasattr(r[5], 'strftime') else str(r[5])), r[3], r[4]) for r in pa_rows]
    except Exception as e:
        current_app.logger.error(f'Error Agro: {e}')

    procent = (suma_wyk / suma_plan * 100) if suma_plan > 0 else 0
    procent_agro = (suma_wyk_agro / suma_plan_agro * 100) if suma_plan_agro > 0 else 0
    procent_czasu = (suma_minut_plan / 450 * 100)

    # Rozliczenia summary table (active tab)
    rozliczenia = []
    try:
        ln_r = 'Agro' if aktywna_zakladka == 'agro' else 'PSD'
        pl_r = plany_agro if aktywna_zakladka == 'agro' else plany_list
        t_sz_r = get_table_name('szarze', ln_r)
        t_ds_r = get_table_name('dosypki', ln_r)
        t_pa_r = get_table_name('palety_workowanie', ln_r)
        t_bf_r = get_table_name('bufor', ln_r)
        t_pp_r = get_table_name('plan_produkcji', ln_r)
        
        for p in pl_r:
            if p[1].lower() != 'zasyp': continue
            z_id, prod_r, p_z = p[0], p[2], p[3] or 0
            cursor.execute(f"SELECT COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {t_ds_r} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) FROM {t_sz_r} WHERE plan_id = %s", (z_id, z_id))
            z_kg = cursor.fetchone()[0] or 0
            cursor.execute(f"SELECT COALESCE(SUM(CASE WHEN waga_potwierdzona > 0 THEN waga_potwierdzona ELSE waga END), 0) FROM {t_pa_r} WHERE plan_id IN (SELECT id FROM {t_pp_r} WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie' AND produkt = %s)", (wybrana_data, prod_r))
            spak_kg = cursor.fetchone()[0] or 0
            cursor.execute(f"SELECT SUM(tonaz_rzeczywisty - spakowano) FROM {t_bf_r} WHERE zasyp_id = %s AND data_planu = %s AND status = 'aktywny'", (z_id, wybrana_data))
            buf_kg = cursor.fetchone()[0] or 0
            
            rozliczenia.append({
                'zasyp_id': z_id, 'produkt': prod_r, 'status': p[4],
                'planowany_zasyp': round(float(p_z), 1), 'zasyp_kg': round(float(z_kg), 1),
                'plan_workowanie': round(float(z_kg), 1), 'spakowano_palety': round(float(spak_kg), 1),
                'bufor_spakowano': round(float(buf_kg), 1),
                'diff_no_buf': round(z_kg - spak_kg, 1), 'diff_with_buf': round(z_kg - (spak_kg + buf_kg), 1)
            })
    except Exception as er:
        current_app.logger.error(f'Rozliczenie error: {er}')

    # Check incomplete plans
    has_incomplete_plans = False
    try:
        psd_incomplete = any(p[4] == 'zakonczone' and (p[8] or 0) < (p[3] or 0) for p in plany_list)
        agro_incomplete = any(p[4] == 'zakonczone' and (p[8] or 0) < (p[3] or 0) for p in plany_agro)
        
        work_inc = False
        for l_chk in ['PSD', 'Agro']:
            t_p_chk = get_table_name('plan_produkcji', l_chk)
            cursor.execute(f"SELECT tonaz, tonaz_rzeczywisty, status FROM {t_p_chk} WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'workowanie'", (wybrana_data,))
            for rw in cursor.fetchall():
                if rw[2] == 'zakonczone' and (rw[1] or 0) < (rw[0] or 0):
                    work_inc = True; break
            if work_inc: break
        has_incomplete_plans = psd_incomplete or agro_incomplete or work_inc
    except Exception as e:
        current_app.logger.warning(f'Error checking incomplete plans: {e}')

    try:
        role_now = (session.get('rola') or '')
        for p in plany_list + plany_agro:
            try:
                plan_val = float(p[3] or 0)
                wyk_val = float(p[8] or 0)
            except Exception:
                plan_val, wyk_val = 0.0, 0.0
            remaining = round(plan_val - wyk_val, 3)
            show_btn = (p[4] == 'zakonczone' and remaining > 0 and role_now.lower() in ['planista', 'admin', 'zarzad'])
            current_app.logger.debug(f'[PLANISTA-LOG] id={p[0]} produkt="{p[2]}" sekcja="{p[1]}" status="{p[4]}" plan={plan_val} wyk={wyk_val} remaining={remaining} role="{role_now}" show_button={show_btn}')
    except Exception:
        current_app.logger.exception('Error logging detailed planista info')

    # ===== PRZYPOMNIENIE O TOWARZE W BUFORZE =====
    bufor_remaining = []
    bufor_source_date = None
    try:
        conn_buf = get_db_connection()
        cur_buf = conn_buf.cursor()
        table_bufor = get_table_name('bufor', wybrana_linia)
        cur_buf.execute(f"""
            SELECT b.produkt,
                   SUM(COALESCE(b.tonaz_rzeczywisty, 0) - COALESCE(b.spakowano, 0)) as pozostalo
            FROM {table_bufor} b
            WHERE b.status = 'aktywny'
              AND b.data_planu < %s
            GROUP BY b.produkt
            HAVING pozostalo > 0
        """, (wybrana_data,))
        bufor_remaining = [
            {'produkt': r[0], 'pozostalo_kg': round(float(r[1]), 1)}
            for r in cur_buf.fetchall()
        ]
        # Pobierz datę źródłową bufora (najnowsza data_planu < wybrana_data)
        if bufor_remaining:
            cur_buf.execute(f"""
                SELECT MAX(b.data_planu) FROM {table_bufor} b
                WHERE b.status = 'aktywny' AND b.data_planu < %s
            """, (wybrana_data,))
            row = cur_buf.fetchone()
            if row and row[0]:
                bufor_source_date = str(row[0])
        cur_buf.close()
        conn_buf.close()
    except Exception:
        current_app.logger.exception('Error checking bufor remainder for reminder')

    return render_template('planista.html',
                           plany=plany_list,
                           wybrana_data=wybrana_data,
                           wybrana_linia=wybrana_linia,
                           palety_mapa=palety_mapa,
                           suma_plan=suma_plan,
                           suma_wyk=suma_wyk,
                           procent=procent,
                           suma_minut_plan=suma_minut_plan,
                           procent_czasu=procent_czasu,
                           quality_count=quality_count,
                           quality_orders=quality_orders,
                           rozliczenia=rozliczenia,
                           current_role=rola,
                           aktywna_zakladka=aktywna_zakladka,
                           plany_agro=plany_agro,
                           suma_plan_agro=suma_plan_agro,
                           suma_wyk_agro=suma_wyk_agro,
                           suma_minut_plan_agro=suma_minut_plan_agro,
                           procent_agro=procent_agro,
                           has_incomplete_plans=has_incomplete_plans,
                           bufor_remaining=bufor_remaining,
                           bufor_source_date=bufor_source_date)


@planista_bp.route('/planista/add_czyszczenie', methods=['POST'])
@roles_required('planista', 'zarzad', 'lider', 'admin')
def add_czyszczenie():
    """Dodaj wpis "Czyszczenie" do plan_produkcji na konkretną datę i pozycję (kolejnosc)."""
    from flask import request, redirect, url_for, current_app
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # prefer form data; if not present, try JSON payload (silently)
        json_body = request.get_json(silent=True) or {}
        data_planu = request.form.get('data_planu') or (json_body.get('data_planu') if json_body else None)
        tonaz = request.form.get('tonaz') or (json_body.get('tonaz') if json_body else None)
        kolejnosc = request.form.get('kolejnosc') or (json_body.get('kolejnosc') if json_body else None)
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
        linia = request.form.get('linia') or json_body.get('linia') or 'PSD'
        table_plan = get_table_name('plan_produkcji', linia)
 
        if kolejnosc_val is not None:
            cursor.execute(f"UPDATE {table_plan} SET kolejnosc = kolejnosc + 1 WHERE data_planu = %s AND kolejnosc >= %s", (data_planu, kolejnosc_val))
 
        insert_sql = (f"INSERT INTO {table_plan} (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_zlecenia, linia) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")
        cursor.execute(insert_sql, (data_planu, 'Czyszczenie', 'Czyszczenie', tonaz_val, 'zaplanowane', kolejnosc_val or 9999, 'jakosc', linia))
        notify_workers_about_plan_change(
            plan_context={
                'id': cursor.lastrowid if hasattr(cursor, 'lastrowid') else None,
                'produkt': 'Czyszczenie',
                'sekcja': 'Czyszczenie',
                'data_planu': data_planu,
            },
            action_label='dodał',
            author_name=session.get('imie_nazwisko') or session.get('login'),
            conn=conn,
            cursor=cursor,
            created_by_user_id=session.get('user_id'),
        )
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
@dynamic_role_required('bufor')
def bufor_page():
    from flask import current_app
    from app.db import refresh_bufor_queue
    
    app_logger = current_app.logger
    app_logger.info(f"[BUFOR] bufor_page() called")
    
    wybrana_data = request.args.get('data', str(date.today()))
    wybrana_linia = request.args.get('linia', 'PSD')
    app_logger.info(f"[BUFOR] Starting bufor_page for date {wybrana_data}, line {wybrana_linia}")
    
    bufor_list = []
    
    try:
        # Odśwież bufor - dodaj nowe zpecenia które się pojawiły
        from app.db import get_table_name
        refresh_bufor_queue(linia=wybrana_linia)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        table_bufor = get_table_name('bufor', wybrana_linia)
        table_plan = get_table_name('plan_produkcji', wybrana_linia)
        
        # Czytaj z nowej tabeli bufor - posortowane po kolejce
        cursor.execute(f"""
             SELECT b.id, b.zasyp_id, b.data_planu, b.produkt, b.nazwa_zlecenia,
                 b.typ_produkcji, b.kolejka,
                 z.tonaz, z.tonaz_rzeczywisty, z.real_start, z.status,
                 w.tonaz, w.tonaz_rzeczywisty
            FROM {table_bufor} b
            LEFT JOIN {table_plan} z ON z.id = b.zasyp_id
             LEFT JOIN {table_plan} w ON w.zasyp_id = b.zasyp_id AND w.sekcja = 'Workowanie'
            WHERE b.data_planu = %s AND b.status = 'aktywny'
            ORDER BY b.kolejka ASC
        """, (wybrana_data,))
        
        rows = cursor.fetchall()
        app_logger.info(f"[BUFOR] Loaded {len(rows)} active bufor entries for date {wybrana_data}")
        
        for row in rows:
            (buf_id, z_id, z_data, z_produkt, z_nazwa, z_typ, z_kolejka,
             zasyp_plan_tonaz, zasyp_rzeczywisty_tonaz, z_real_start, z_status,
             workowanie_plan_tonaz, workowanie_rzeczywisty_tonaz) = row
            
            pozostalo_do_spakowania = (zasyp_rzeczywisty_tonaz or 0) - (workowanie_rzeczywisty_tonaz or 0)
            needs_reconciliation = round(pozostalo_do_spakowania, 1) != 0
            start_time = z_real_start.strftime('%H:%M') if z_real_start else 'N/A'
            
            bufor_list.append({
                'id': z_id,
                'data': str(z_data),
                'produkt': z_produkt,
                'nazwa': z_nazwa or '',
                'typ_produkcji': z_typ or '',
                'plan_zasypu': zasyp_plan_tonaz or 0,
                'do_spakowania': zasyp_rzeczywisty_tonaz or 0,
                'spakowane': workowanie_rzeczywisty_tonaz or 0,
                'pozostalo_do_spakowania': round(pozostalo_do_spakowania, 1),
                'kolejka': z_kolejka,
                'needs_reconciliation': needs_reconciliation,
                'status': z_status or 'zaplanowane',
                'real_start': z_real_start,
                'start_time': start_time
            })
        
        conn.close()
        
    except Exception as e:
        app_logger.error(f"ERROR in bufor_page for date {wybrana_data}: {type(e).__name__}: {str(e)}", exc_info=True)
        bufor_list = []
    
    return render_template('bufor.html', bufor_list=bufor_list, wybrana_data=wybrana_data, wybrana_linia=wybrana_linia)


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

            linia = request.form.get('linia') or (request.json.get('linia') if request.json else 'PSD')
            table_plan = get_table_name('plan_produkcji', linia)
     
            if parts:
                sql += ', '.join(parts) + f' WHERE id=%s'
                params.append(plan_id)
                cursor.execute(sql.replace('plan_produkcji', table_plan), tuple(params))
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
        # Try to get sekcja from query string first (URL parameters), then from form
        sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
        data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return redirect(url_for('planista.panel_planisty', sekcja=sekcja, data=data))


@planista_bp.route('/bufor/archiwizuj', methods=['POST'])
@roles_required('planista', 'lider', 'admin')
def bufor_archiwizuj():
    """Endpoint obsługujący archiwizację zlecenia — zmienia status na 'archiwizowany'."""
    from flask import request, jsonify
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        data = request.get_json(silent=True) or {}
        plan_id = data.get('plan_id') or request.form.get('plan_id') or request.args.get('plan_id')
        linia = data.get('linia') or request.form.get('linia') or request.args.get('linia', 'PSD')
        
        if not plan_id:
            return jsonify({'ok': False, 'message': 'Brak plan_id'}), 400
        
        plan_id = int(plan_id)
        table_plan = get_table_name('plan_produkcji', linia)
        
        # Update status to 'archiwizowany' in plan_produkcji
        cursor.execute(
            f"UPDATE {table_plan} SET status=%s WHERE id=%s",
            ('archiwizowany', plan_id)
        )
        
        # ALSO update buffer status to 'zamkniete' so it disappears from active view
        table_bufor = get_table_name('bufor', linia)
        cursor.execute(
            f"UPDATE {table_bufor} SET status=%s WHERE zasyp_id=%s",
            ('zamkniete', plan_id)
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


@planista_bp.route('/bufor/create_zlecenie', methods=['POST'])
@roles_required('planista', 'admin', 'lider')
def bufor_create_zlecenie():
    """Create new Workowanie zlecenie based on buffer remainder (Zasyp.tonaz_rzeczywisty - spakowano).
    
    OPCJA 1 (standardowa): zasyp_id - czyta z Zasypu
    OPCJA 2 (nowa): use_buffer_data=true + zasyp_id - czyta bezpośrednio z bufora 
                    (działa nawet gdy Zasyp jest zamknięty)
    OPCJA 3: workowanie_date (optionalne) - data dla nowego Workowania (domyślnie data z Zasypu/bufora)
    """
    from flask import jsonify
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
    except Exception:
        data = request.form.to_dict()
    
    zasyp_id = data.get('zasyp_id')
    use_buffer = data.get('use_buffer_data') == 'true' or data.get('use_buffer_data') == True
    override_work_date = data.get('workowanie_date')  # Np. zmiana daty dla nowego dnia
    
    if not zasyp_id:
        return jsonify({'success': False, 'message': 'Brak zasyp_id'}), 400
    
    try:
        zasyp_id = int(zasyp_id)
    except Exception:
        return jsonify({'success': False, 'message': 'Nieprawidłowy zasyp_id'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    linia = data.get('linia') or 'PSD'
    from app.db import get_table_name
    table_bufor = get_table_name('bufor', linia)
    table_plan = get_table_name('plan_produkcji', linia)
    
    try:
        if use_buffer:
            # OPCJA 2: Czytaj bezpośrednio z bufora (niezależnie od statusu Zasypu)
            cursor.execute(f"""
                SELECT 
                    zasyp_id,
                    data_planu,
                    produkt,
                    COALESCE(tonaz_rzeczywisty, 0) as tonaz_rzeczywisty,
                    typ_produkcji,
                    COALESCE(nazwa_zlecenia, '') as nazwa_zlecenia,
                    COALESCE(SUM(spakowano), 0) as spakowano,
                    MAX(linia) as linia
                FROM {table_bufor}
                WHERE zasyp_id = %s
                GROUP BY zasyp_id, data_planu, produkt, typ_produkcji, nazwa_zlecenia
                LIMIT 1
            """, (zasyp_id,))
            zasyp_data = cursor.fetchone()
            
            if not zasyp_data:
                conn.close()
                return jsonify({'success': False, 'message': 'Nie znaleziono wpisu w buforze dla tego Zasypu'}), 404
            
            z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa, spakowano, z_linia = zasyp_data
            # Calculate remainder from buffer directly
            roznicza = (z_tonaz_rz or 0) - spakowano
        else:
            # OPCJA 1 (standardowa): Czytaj z Zasypu
            # Get Zasyp details (tonaz_rzeczywisty, date, product, type, linia)
            cursor.execute(f"""
                SELECT id, data_planu, produkt, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia, linia
                FROM {table_plan}
                WHERE id = %s AND sekcja = 'Zasyp'
            """, (zasyp_id,))
            zasyp = cursor.fetchone()
            
            if not zasyp:
                conn.close()
                return jsonify({'success': False, 'message': 'Nie znaleziono Zasypu'}), 404
            
            z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa, z_linia = zasyp
            
            # Get how much was already packed (sum from bufor.spakowano)
            cursor.execute(f"""
                SELECT SUM(spakowano) FROM {table_bufor}
                WHERE zasyp_id = %s AND data_planu = %s
            """, (zasyp_id, z_data))
            
            result = cursor.fetchone()
            spakowano = result[0] or 0 if result else 0
            
            # Calculate remainder: Zasyp.tonaz_rzeczywisty - spakowano
            roznicza = (z_tonaz_rz or 0) - spakowano
        
        # OPCJA 3: Override workowanie date if provided (dla rana następnego dnia)
        work_date = str(override_work_date) if override_work_date else str(z_data)
        
        # Determine if we are moving to a NEW date (compared to source Zasyp)
        source_date_str = str(z_data)
        is_new_day = work_date != source_date_str

        if roznicza <= 0:
            conn.close()
            return jsonify({'success': False, 'message': 'Nie ma pozostałego towaru do spakowania (różnica <= 0)'}), 400
        
        # Check if Workowanie for this product/date already exists (in any status)
        cursor.execute(f"""
            SELECT id FROM {table_plan}
            WHERE data_planu = %s AND produkt = %s AND sekcja = 'Workowanie'
            LIMIT 1
        """, (work_date, z_produkt))
        
        existing_work = cursor.fetchone()
        
        if existing_work:
            conn.close()
            return jsonify({
                'success': False, 
                'message': f'Zlecenie Workowanie na produkt "{z_produkt}" już istnieje dla tej daty'
            }), 400
        
        # GHOST ZASYP LOGIC: If moving to a new day, create a placeholder Zasyp on that day
        final_zasyp_id = z_id
        if is_new_day:
            # Check if Ghost Zasyp already exists for this product and new date
            cursor.execute(f"""
                SELECT id FROM {table_plan}
                WHERE data_planu = %s AND produkt = %s AND sekcja = 'Zasyp' AND typ_zlecenia = 'carry_over_ghost'
                LIMIT 1
            """, (work_date, z_produkt))
            existing_ghost = cursor.fetchone()
            
            if existing_ghost:
                final_zasyp_id = existing_ghost[0]
            else:
                # Create NEW Ghost Zasyp (plan 0kg)
                cursor.execute(f"""
                    SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu = %s AND sekcja = 'Zasyp'
                """, (work_date,))
                res_max = cursor.fetchone()
                nk_zasyp = (res_max[0] or 0) + 1
                
                cursor.execute(f"""
                    INSERT INTO {table_plan} 
                    (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, typ_zlecenia, linia, tonaz_rzeczywisty)
                    VALUES (%s, %s, %s, 0, 'zakonczone', %s, %s, %s, 'carry_over_ghost', %s, 0)
                """, (
                    work_date, 'Zasyp', z_produkt, nk_zasyp, 
                    z_typ or 'worki_zgrzewane_25', f"Carry-over {source_date_str}", z_linia
                ))
                final_zasyp_id = cursor.lastrowid
                
                # Also create a NEW buffer entry for the new day so it's visible there
                cursor.execute(f"SELECT COALESCE(MAX(kolejka),0) FROM {table_bufor} WHERE data_planu=%s", (work_date,))
                max_kol = cursor.fetchone()[0] or 0
                cursor.execute(f"""
                    INSERT INTO {table_bufor} (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, tonaz_rzeczywisty, spakowano, kolejka, status, linia)
                    VALUES (%s, %s, %s, %s, %s, %s, 0, %s, 'aktywny', %s)
                """, (
                    final_zasyp_id, work_date, z_produkt, f"Carry-over {source_date_str}", 
                    z_typ or 'worki_zgrzewane_25', round(roznicza, 1), max_kol + 1, z_linia
                ))

        # Get next sequence number for Workowanie section (dla dnia Workowania)
        cursor.execute(f"""
            SELECT MAX(kolejnosc) FROM {table_plan} 
            WHERE data_planu = %s AND sekcja = 'Workowanie'
        """, (work_date,))
        
        result = cursor.fetchone()
        next_kolejnosc = (result[0] or 0) + 1 if result else 1
        
        # Create new Workowanie zlecenie with plan = roznicza
        cursor.execute(f"""
            INSERT INTO {table_plan} 
            (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, zasyp_id, linia, tonaz_rzeczywisty)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
        """, (
            work_date,
            'Workowanie',
            z_produkt,
            round(roznicza, 1),  # plan = różnica
            'zaplanowane',
            next_kolejnosc,
            z_typ or 'worki_zgrzewane_25',
            z_nazwa or '',
            final_zasyp_id,  # Link to local Ghost Zasyp or original Zasyp
            z_linia
        ))
        
        conn.commit()
        new_id = cursor.lastrowid
        
        conn.close()
        return jsonify({
            'success': True,
            'message': f'Utworzono zlecenie Workowanie z planem {round(roznicza, 1)} kg',
            'new_id': new_id,
            'plan_kg': round(roznicza, 1)
        }), 201
        
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.exception('Error in bufor_create_zlecenie')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@planista_bp.route('/api/przenies_niezrealizowane', methods=['POST'])
@roles_required('planista', 'admin', 'lider')
def api_przenies_niezrealizowane():
    """Move incomplete plans to next day, creating new Zasyp and Workowanie plans."""
    import traceback
    
    # ULTRA DEBUG - Log immediately to stderr and file
    current_app.logger.debug('api_przenies_niezrealizowane called')
    
    try:
        data_dict = request.get_json() or {}
        current_data = data_dict.get('data')
        current_app.logger.debug(f'[PRZENIES API] Request body: {data_dict}')
        current_app.logger.debug(f'[PRZENIES API] Extracted current_data: {current_data} (type: {type(current_data).__name__})')
        
        if not current_data:
            current_app.logger.warning(f'[PRZENIES API] Data is missing!')
            return jsonify({'success': False, 'message': 'Data jest wymagana'}), 400
        
        # Call service method
        success, message, count = PlanningService.przenies_niezrealizowane(current_data)
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'count': count
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 400
            
    except Exception as e:
        current_app.logger.exception(f'Error in api_przenies_niezrealizowane: {str(e)}')
        return jsonify({'success': False, 'message': f'Błąd serwera: {str(e)}'}), 500


@planista_bp.route('/api/check_niezrealizowane', methods=['POST', 'GET'])
@roles_required('planista', 'admin', 'lider')
def api_check_niezrealizowane():
    """Check what incomplete plans exist and would be moved."""
    try:
        # Support both methods
        if request.method == 'POST':
            data_dict = request.get_json() or {}
            current_data = data_dict.get('data')
            linia = data_dict.get('linia') or 'PSD'
        else:
            current_data = request.args.get('data')
            linia = request.args.get('linia') or 'PSD'
            
        if not current_data:
            current_data = date.today().strftime('%Y-%m-%d')
        
        table_plan = get_table_name('plan_produkcji', linia)
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query for unfinished production (Zasyp finished but Workowanie incomplete)
        cursor.execute(f"""
            SELECT z.id AS zasyp_id, z.produkt,
                   COALESCE(z.tonaz, 0) AS z_plan,
                   COALESCE(z.tonaz_rzeczywisty, 0) AS z_real,
                   w.id AS workowanie_id,
                   COALESCE(w.tonaz, 0) AS w_plan,
                   COALESCE(w.tonaz_rzeczywisty, 0) AS w_real
            FROM {table_plan} z
            LEFT JOIN {table_plan} w
                ON w.zasyp_id = z.id AND LOWER(w.sekcja) = 'workowanie'
            WHERE DATE(z.data_planu) = %s
              AND z.status = 'zakonczone'
              AND LOWER(z.sekcja) = 'zasyp'
            ORDER BY z.id
        """, (current_data,))
        
        all_plans = cursor.fetchall()
        conn.close()
        
        details = []
        total_remaining = 0.0
        
        from datetime import datetime, timedelta
        current_date_obj = datetime.strptime(current_data, '%Y-%m-%d')
        next_date = current_date_obj + timedelta(days=1)
        next_data_str = next_date.strftime('%Y-%m-%d')

        for plan in all_plans:
            if plan['workowanie_id'] is None:
                continue

            w_plan = float(plan['w_plan'] or 0.0)
            w_real = float(plan['w_real'] or 0.0)
            z_real = float(plan['z_real'] or 0.0)

            rem_kg = max(0.0, w_plan - w_real)
            if rem_kg <= 0:
                continue

            in_buf_kg = max(0.0, z_real - w_real)
            short_kg = max(0.0, w_plan - z_real)

            total_remaining += rem_kg
            details.append({
                'plan_id': int(plan['zasyp_id']),
                'produkt': str(plan['produkt']),
                'w_plan_kg': float(w_plan),
                'w_real_kg': float(w_real),
                'remaining_kg': float(rem_kg),
                'shortfall_kg': float(short_kg),
                'in_buffer_kg': float(in_buf_kg)
            })

        if not details:
            return jsonify({'success': False, 'message': 'Brak zleceń do przeniesienia.'}), 400

        return jsonify({
            'success': True,
            'current_data': current_data,
            'next_date': next_data_str,
            'current_date_formatted': current_date_obj.strftime('%d.%m.%Y'),
            'next_date_formatted': next_date.strftime('%d.%m.%Y'),
            'plans': details,
            'total_remaining_kg': float(total_remaining),
            'count': len(details)
        }), 200

    except Exception as e:
        current_app.logger.exception(f'Error in api_check_niezrealizowane: {str(e)}')
        return jsonify({'success': False, 'message': f'Błąd serwera: {str(e)}'}), 500


@planista_bp.route('/api/check_zlecenie', methods=['POST', 'GET'])
@roles_required('planista', 'admin', 'lider')
def api_check_zlecenie():
    """Check given plan (zlecenie) and report which parts are still active / not closed and in which section."""
    try:
        # Get parameters from query string (sent via fetch?plan_id=...) or form
        plan_id = request.args.get('plan_id') or request.form.get('plan_id')
        linia = request.args.get('linia') or request.form.get('linia', 'PSD')
        
        if not plan_id:
            return jsonify({'success': False, 'message': 'Brak plan_id'}), 400
        try:
            plan_id = int(plan_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowe plan_id'}), 400

        table_plan = get_table_name('plan_produkcji', linia)
        table_szarze = get_table_name('szarze', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        table_bufor = get_table_name('bufor', linia)
 
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
 
        cursor.execute(f"SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, status, real_start, real_stop FROM {table_plan} WHERE id = %s", (plan_id,))
        plan = cursor.fetchone()
        if not plan:
            conn.close()
            return jsonify({'success': False, 'message': 'Zlecenie nie znalezione'}), 404

        # compute remaining for this plan
        plan_ton = float(plan.get('tonaz') or 0)
        real_ton = float(plan.get('tonaz_rzeczywisty') or 0)
        remaining = max(0.0, plan_ton - real_ton)

        # gather related info: Workowanie (if this is Zasyp), szarze, palety, bufor entries
        related = {}
        try:
            # If this plan is a Zasyp, find its Workowanie record
            if (plan.get('sekcja') or '').strip().lower() == 'zasyp':
                cursor.execute(f"SELECT id, sekcja, tonaz, tonaz_rzeczywisty, status FROM {table_plan} WHERE zasyp_id = %s AND LOWER(sekcja) = 'workowanie' LIMIT 1", (plan_id,))
                w = cursor.fetchone()
                if w:
                    w_ton = float(w.get('tonaz') or 0)
                    w_real = float(w.get('tonaz_rzeczywisty') or 0)
                    related['workowanie'] = {
                        'id': w.get('id'),
                        'sekcja': w.get('sekcja'),
                        'plan_kg': w_ton,
                        'real_kg': w_real,
                        'remaining_kg': max(0.0, w_ton - w_real),
                        'status': w.get('status')
                    }

            # szarze sum (actual weights entered)
            cursor.execute(f"SELECT COALESCE(SUM(waga),0) AS szarze_sum FROM {table_szarze} WHERE plan_id = %s", (plan_id,))
            r = cursor.fetchone()
            related['szarze_sum_kg'] = float(r.get('szarze_sum') or 0)
 
            # palety summary (for Workowanie)
            cursor.execute(f"SELECT COUNT(*) AS count, COALESCE(SUM(waga),0) AS total_kg FROM {table_pal} WHERE plan_id = %s", (plan_id,))
            r = cursor.fetchone()
            related['palety_count'] = int(r.get('count') or 0)
            related['palety_total_kg'] = float(r.get('total_kg') or 0)
 
            # bufor entries related (zasyp_id or plan_id)
            cursor.execute(f"SELECT id, zasyp_id, data_planu, produkt, spakowano, status FROM {table_bufor} WHERE zasyp_id = %s OR plan_id = %s", (plan_id, plan_id))
            buf_rows = cursor.fetchall()
            related['bufor'] = buf_rows or []
        except Exception:
            current_app.logger.exception('Error gathering related info for plan')

        conn.close()

        is_active = False
        reasons = []
        if (plan.get('status') or '').strip().lower() != 'zakonczone':
            is_active = True
            reasons.append('status != zakonczone')
        if remaining > 0:
            is_active = True
            reasons.append(f'Nie spakowano {remaining:.1f} kg')
        # also if there are pending bufor entries or palety not confirmed
        if related.get('bufor'):
            for b in related.get('bufor'):
                if (b.get('status') or '').strip().lower() != 'zamkniete' and (b.get('spakowano') is None or float(b.get('spakowano') or 0) < 0.0001):
                    is_active = True
                    reasons.append('Istnieją aktywne wpisy w buforze')
                    break

        payload = {
            'success': True,
            'plan': {
                'id': plan.get('id'),
                'sekcja': plan.get('sekcja'),
                'produkt': plan.get('produkt'),
                'status': plan.get('status'),
                'plan_kg': plan_ton,
                'real_kg': real_ton,
                'remaining_kg': remaining
            },
            'related': related,
            'active': is_active,
            'reasons': reasons
        }

        return jsonify(payload), 200

    except Exception as e:
        current_app.logger.exception(f'Error in api_check_zlecenie: {str(e)}')
        return jsonify({'success': False, 'message': f'Błąd serwera: {str(e)}'}), 500


@planista_bp.route('/api/przenies_wybrane_zlecenia', methods=['POST'])
@roles_required('planista', 'admin', 'lider', 'zarzad')
def api_przenies_wybrane_zlecenia():
    """Move selected incomplete plans to next day."""
    try:
        data_dict = request.get_json() or {}
        current_data = data_dict.get('data')
        plan_ids = data_dict.get('plan_ids', [])
        
        if not current_data:
            return jsonify({'success': False, 'message': 'Data jest wymagana'}), 400
        
        if not plan_ids or not isinstance(plan_ids, list):
            return jsonify({'success': False, 'message': 'Wybierz przynajmniej jedno zlecenie'}), 400
        
        # Use PlanningService to move selected plans
        from app.services.planning_service import PlanningService
        
        success, message, count = PlanningService.przenies_niezrealizowane(
            current_data,
            plan_ids_to_move=plan_ids  # Pass selected plan IDs
        )
        
        if success:
            from datetime import datetime, timedelta
            try:
                next_date_str = (datetime.strptime(current_data, '%Y-%m-%d') + timedelta(days=1)).strftime('%d.%m.%Y')
            except Exception:
                next_date_str = '?'
            product_count = count // 2 if count >= 2 else count
            if product_count == 0:
                resp_msg = f'Zlecenia były już wcześniej przeniesione na {next_date_str} — brak duplikatów do dodania.'
            else:
                resp_msg = f'✓ Przeniesiono {product_count} {"zlecenie" if product_count == 1 else "zlecenia" if product_count in (2,3,4) else "zleceń"} na {next_date_str}'
            return jsonify({
                'success': True,
                'message': resp_msg
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 400
            
    except Exception as e:
        current_app.logger.exception(f'Error in api_przenies_wybrane_zlecenia: {str(e)}')
        return jsonify({'success': False, 'message': f'Błąd serwera: {str(e)}'}), 500


@planista_bp.route('/planista/bulk', methods=['GET'])
@roles_required('planista', 'admin', 'lider')
def planista_bulk_page():
    """Render page for bulk adding plans."""
    wybrana_data = request.args.get('data', str(date.today()))
    domyslna_sekcja = request.args.get('sekcja', 'Zasyp')
    return render_template('planista_bulk.html', wybrana_data=wybrana_data, domyslna_sekcja=domyslna_sekcja)
