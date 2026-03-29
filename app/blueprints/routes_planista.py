from flask import Blueprint, render_template, request, current_app, session, jsonify
from app.db import get_db_connection
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

    # Include both Zasyp and Czyszczenie entries so planner sees cleaning slots
    # Exclude ghost carry-over Zasyp records (technical records linked to bufor, not real production)
    cursor.execute("""
        SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
        FROM plan_produkcji 
        WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
          AND COALESCE(typ_zlecenia, '') != 'carry_over_ghost'
        ORDER BY kolejnosc
    """, (wybrana_data,))
    
    plany = cursor.fetchall()
    plany_list = [list(p) for p in plany] # Lista edytowalna

    # DODATKOWO: dołącz wpisy Workowanie jako osobną grupę, tak by były widoczne w UI
    try:
        cursor.execute("""
            SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
            FROM plan_produkcji
            WHERE data_planu = %s AND LOWER(sekcja) = 'workowanie'
            ORDER BY kolejnosc
        """, (wybrana_data,))
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
            cursor.execute(
                "SELECT COALESCE(uszkodzone_worki, 0) FROM plan_produkcji WHERE DATE(data_planu)=%s AND sekcja='Workowanie' AND produkt=%s LIMIT 1",
                (wybrana_data, p[2])
            )
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
            cursor.execute(
                "SELECT COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM dosypki WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) FROM szarze WHERE plan_id = %s",
                (plan_id, plan_id)
            )
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

    # Przygotuj dane rozliczeniowe (Rozliczenie) — dla każdego Zasypu policz: Zasyp, Plan Workowanie, Spakowano (palety), Bufor (spakowano z bufor)
    rozliczenia = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        for p in plany_list:
            sekcja = (p[1] or '').lower()
            if sekcja != 'zasyp':
                continue

            zasyp_id = p[0]
            produkt = p[2]
            planowany_zasyp = p[3] or 0  # tonaz z tabeli plan_produkcji (kolumna tonaz dla Zasypu)

            # Zasyp = SUM(szarże) + SUM(dosypki potwierdzone) - co faktycznie wyjechało z Zasypu
            cursor.execute("""
                SELECT COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM dosypki WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) FROM szarze
                WHERE plan_id = %s
            """, (zasyp_id, zasyp_id))
            row = cursor.fetchone()
            zasyp_kg = row[0] or 0 if row else 0
            plan_work = zasyp_kg  # Plan Workowanie = Zasyp (co wyjechało = co ma spakować)

            # Spakowano (sumarycznie z palet Workowanie dla tego produktu/daty - rzeczywiste spakowanie)
            cursor.execute("""
                SELECT COALESCE(SUM(CASE WHEN waga_potwierdzona > 0 THEN waga_potwierdzona ELSE waga END), 0) 
                FROM palety_workowanie 
                WHERE plan_id IN (SELECT id FROM plan_produkcji WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie' AND produkt = %s)
            """, (wybrana_data, produkt))
            row_pal = cursor.fetchone()
            spakowano_palety = row_pal[0] or 0 if row_pal else 0

            # Bufor: ile czeka w buforze do spakowania (tonaz_rzeczywisty - spakowano)
            cursor.execute("SELECT SUM(tonaz_rzeczywisty - spakowano) FROM bufor WHERE zasyp_id = %s AND data_planu = %s AND status = 'aktywny'", (zasyp_id, wybrana_data))
            rowb = cursor.fetchone()
            bufor_czeka = rowb[0] or 0 if rowb else 0

            diff_no_buf = round((zasyp_kg - spakowano_palety), 1)
            diff_with_buf = round((zasyp_kg - (spakowano_palety + bufor_czeka)), 1)

            rozliczenia.append({
                'zasyp_id': zasyp_id,
                'produkt': produkt,
                'status': p[4],  # Dodaj status zlecenia
                'planowany_zasyp': round(float(planowany_zasyp), 1),
                'zasyp_kg': round(float(zasyp_kg), 1),
                'plan_workowanie': round(float(plan_work), 1),
                'spakowano_palety': round(float(spakowano_palety), 1),
                'bufor_spakowano': round(float(bufor_czeka), 1),
                'diff_no_buf': diff_no_buf,
                'diff_with_buf': diff_with_buf,
            })
    except Exception as e:
        current_app.logger.error(f'[PLANISTA] Error calculating rozliczenia: {e}', exc_info=True)
        rozliczenia = []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    rola = session.get('rola')
    aktywna_zakladka = request.args.get('tab', 'psd').lower()
    if aktywna_zakladka not in ('psd', 'agro'):
        aktywna_zakladka = 'psd'

    current_app.logger.debug(f'[PLANISTA] Rendering template: current_role={rola}, tab={aktywna_zakladka}, session_keys={list(session.keys())}')

    # ===== DANE DLA ZAKŁADKI AGRO =====
    plany_agro = []
    suma_plan_agro = 0
    suma_wyk_agro = 0
    suma_minut_plan_agro = 0
    procent_agro = 0

    try:
        conn_agro = get_db_connection()
        cursor_agro = conn_agro.cursor()
        cursor_agro.execute("""
            SELECT id, 'Agro' as sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
            FROM plan_agro
            WHERE data_planu = %s
            ORDER BY kolejnosc
        """, (wybrana_data,))
        agro_rows = cursor_agro.fetchall()
        plany_agro = [list(r) for r in agro_rows]

        for p in plany_agro:
            waga_plan = p[3] if p[3] else 0
            typ_prod = p[9]
            norma = calculate_kg_per_hour(typ_prod) if typ_prod else calculate_kg_per_hour('bigbag')
            czas_min = int((waga_plan / norma) * 60) if norma > 0 else 0
            p.append(czas_min)  # index 12
            suma_plan_agro += waga_plan
            suma_minut_plan_agro += czas_min

            # Wykonanie
            cursor_agro.execute(
                "SELECT COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM dosypki WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) FROM szarze WHERE plan_id = %s",
                (p[0], p[0])
            )
            sz = cursor_agro.fetchone()
            wyk = sz[0] if sz and sz[0] else (p[8] if p[8] else 0)
            p[8] = wyk
            suma_wyk_agro += wyk

        conn_agro.close()
        procent_agro = (suma_wyk_agro / suma_plan_agro * 100) if suma_plan_agro > 0 else 0
    except Exception as e:
        current_app.logger.error(f'[PLANISTA AGRO] Błąd ładowania danych AGRO: {e}')
        plany_agro = []

    # Check if there are incomplete plans (status 'zakonczone' with wykonanie < plan)
    has_incomplete_plans = False
    try:
        psd_incomplete = any(
            p[4] == 'zakonczone' and (p[8] or 0) < (p[3] or 0)
            for p in plany_list
        )
        agro_incomplete = any(
            p[4] == 'zakonczone' and (p[8] or 0) < (p[3] or 0)
            for p in plany_agro
        )
        # ALSO check Workowanie entries: show banner if any Workowanie is 'zakonczone' but not fully packed
        workowanie_incomplete = False
        try:
            conn_w = get_db_connection()
            cur_w = conn_w.cursor()
            cur_w.execute("""
                SELECT id, tonaz, tonaz_rzeczywisty, status
                FROM plan_produkcji
                WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'workowanie'
            """, (wybrana_data,))
            for rw in cur_w.fetchall():
                try:
                    plan_val = float(rw[1] or 0)
                except Exception:
                    plan_val = 0.0
                try:
                    real_val = float(rw[2] or 0)
                except Exception:
                    real_val = 0.0
                if (rw[3] == 'zakonczone') and real_val < plan_val:
                    workowanie_incomplete = True
                    break
        except Exception:
            current_app.logger.exception('Error checking Workowanie incomplete')
        finally:
            try:
                conn_w.close()
            except Exception:
                pass

        has_incomplete_plans = psd_incomplete or agro_incomplete or workowanie_incomplete
        
        current_app.logger.debug(f'DEBUG has_incomplete_plans: psd={psd_incomplete} (plany_list={len(plany_list)}), agro={agro_incomplete} (plany_agro={len(plany_agro)}), result={has_incomplete_plans}')
        for p in plany_list:
            if p[4] == 'zakonczone':
                current_app.logger.debug(f'  Zasyp: {p[2]} status={p[4]}, tonaz_rz={p[8]}, tonaz_plan={p[3]}, incomplete={(p[8] or 0) < (p[3] or 0)}')
        for p in plany_agro:
            if p[4] == 'zakonczone':
                current_app.logger.debug(f'  Agro: {p[2]} status={p[4]}, tonaz_rz={p[8]}, tonaz_plan={p[3]}, incomplete={(p[8] or 0) < (p[3] or 0)}')
        # Dodatkowe logi: oblicz remaining i czy przycisk zostanie pokazany dla aktualnej roli
        try:
            role_now = (session.get('rola') or '')
            for p in plany_list:
                try:
                    plan_val = float(p[3] or 0)
                except Exception:
                    plan_val = 0.0
                try:
                    wyk_val = float(p[8] or 0)
                except Exception:
                    wyk_val = 0.0
                remaining = round(plan_val - wyk_val, 3)
                show_btn = (p[4] == 'zakonczone' and remaining > 0 and role_now.lower() in ['planista', 'admin', 'zarzad'])
                current_app.logger.debug(f'[PLANISTA-LOG] id={p[0]} produkt="{p[2]}" sekcja="{p[1]}" status="{p[4]}" plan={plan_val} wyk={wyk_val} remaining={remaining} role="{role_now}" show_button={show_btn}')
        except Exception as _:
            current_app.logger.exception('Error logging detailed planista info')
    except Exception as e:
        current_app.logger.warning(f'Error checking incomplete plans: {e}')

    # ===== PRZYPOMNIENIE O TOWARZE W BUFORZE =====
    bufor_remaining = []
    bufor_source_date = None
    try:
        conn_buf = get_db_connection()
        cur_buf = conn_buf.cursor()
        cur_buf.execute("""
            SELECT b.produkt,
                   SUM(COALESCE(b.tonaz_rzeczywisty, 0) - COALESCE(b.spakowano, 0)) as pozostalo
            FROM bufor b
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
            cur_buf.execute("""
                SELECT MAX(b.data_planu) FROM bufor b
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
        if kolejnosc_val is not None:
            cursor.execute("UPDATE plan_produkcji SET kolejnosc = kolejnosc + 1 WHERE data_planu = %s AND kolejnosc >= %s", (data_planu, kolejnosc_val))

        insert_sql = ("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_zlecenia) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s)")
        cursor.execute(insert_sql, (data_planu, 'Czyszczenie', 'Czyszczenie', tonaz_val, 'zaplanowane', kolejnosc_val or 9999, 'jakosc'))
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
                 b.typ_produkcji, b.kolejka,
                 z.tonaz, z.tonaz_rzeczywisty, z.real_start, z.status,
                 w.tonaz, w.tonaz_rzeczywisty
            FROM bufor b
            LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id
             LEFT JOIN plan_produkcji w ON w.zasyp_id = b.zasyp_id AND w.sekcja = 'Workowanie'
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
    
    try:
        if use_buffer:
            # OPCJA 2: Czytaj bezpośrednio z bufora (niezależnie od statusu Zasypu)
            cursor.execute("""
                SELECT 
                    zasyp_id,
                    data_planu,
                    produkt,
                    COALESCE(tonaz_rzeczywisty, 0) as tonaz_rzeczywisty,
                    typ_produkcji,
                    COALESCE(nazwa_zlecenia, '') as nazwa_zlecenia,
                    COALESCE(SUM(spakowano), 0) as spakowano
                FROM bufor
                WHERE zasyp_id = %s
                GROUP BY zasyp_id, data_planu, produkt, typ_produkcji, nazwa_zlecenia
                LIMIT 1
            """, (zasyp_id,))
            zasyp_data = cursor.fetchone()
            
            if not zasyp_data:
                conn.close()
                return jsonify({'success': False, 'message': 'Nie znaleziono wpisu w buforze dla tego Zasypu'}), 404
            
            z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa, spakowano = zasyp_data
            # Calculate remainder from buffer directly
            roznicza = (z_tonaz_rz or 0) - spakowano
        else:
            # OPCJA 1 (standardowa): Czytaj z Zasypu
            # Get Zasyp details (tonaz_rzeczywisty, date, product, type)
            cursor.execute("""
                SELECT id, data_planu, produkt, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia
                FROM plan_produkcji
                WHERE id = %s AND sekcja = 'Zasyp'
            """, (zasyp_id,))
            zasyp = cursor.fetchone()
            
            if not zasyp:
                conn.close()
                return jsonify({'success': False, 'message': 'Nie znaleziono Zasypu'}), 404
            
            z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa = zasyp
            
            # Get how much was already packed (sum from bufor.spakowano)
            cursor.execute("""
                SELECT SUM(spakowano) FROM bufor
                WHERE zasyp_id = %s AND data_planu = %s
            """, (zasyp_id, z_data))
            
            result = cursor.fetchone()
            spakowano = result[0] or 0 if result else 0
            
            # Calculate remainder: Zasyp.tonaz_rzeczywisty - spakowano
            roznicza = (z_tonaz_rz or 0) - spakowano
        
        # OPCJA 3: Override workowanie date if provided (dla rana następnego dnia)
        work_date = override_work_date if override_work_date else z_data
        
        if roznicza <= 0:
            conn.close()
            return jsonify({'success': False, 'message': 'Nie ma pozostałego towaru do spakowania (różnica <= 0)'}), 400
        
        # Check if Workowanie for this product/date already exists (in any status)
        cursor.execute("""
            SELECT id FROM plan_produkcji
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
        
        # Get next sequence number for Workowanie section (dla dnia Workowania)
        cursor.execute("""
            SELECT MAX(kolejnosc) FROM plan_produkcji 
            WHERE data_planu = %s AND sekcja = 'Workowanie'
        """, (work_date,))
        
        result = cursor.fetchone()
        next_kolejnosc = (result[0] or 0) + 1 if result else 1
        
        # Create new Workowanie zlecenie with plan = roznicza
        cursor.execute("""
            INSERT INTO plan_produkcji 
            (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, zasyp_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            work_date,
            'Workowanie',
            z_produkt,
            round(roznicza, 1),  # plan = różnica
            'zaplanowane',
            next_kolejnosc,
            z_typ or 'worki_zgrzewane_25',
            z_nazwa or '',
            z_id  # Link to source Zasyp
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


@planista_bp.route('/api/check_niezrealizowane', methods=['POST'])
@roles_required('planista', 'admin', 'lider')
def api_check_niezrealizowane():
    """Check what incomplete plans exist and would be moved."""
    try:
        data_dict = request.get_json() or {}
        current_data = data_dict.get('data')
        
        if not current_data:
            return jsonify({'success': False, 'message': 'Data jest wymagana'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get next date
        from datetime import datetime, timedelta
        try:
            current_date = datetime.strptime(current_data, '%Y-%m-%d').date()
            next_date = current_date + timedelta(days=1)
            next_data_str = next_date.isoformat()
        except Exception as e:
            return jsonify({'success': False, 'message': f'Nieprawidłowy format daty: {str(e)}'}), 400
        
        # Find closed Zasyp plans with their Workowanie counterparts.
        # Remaining to pack = Workowanie.tonaz - Workowanie.tonaz_rzeczywisty
        # Zasyp shortfall   = Zasyp.tonaz    - Zasyp.tonaz_rzeczywisty
        cursor.execute("""
            SELECT z.id AS zasyp_id, z.produkt,
                   COALESCE(z.tonaz, 0) AS z_plan,
                   COALESCE(z.tonaz_rzeczywisty, 0) AS z_real,
                   w.id AS workowanie_id,
                   COALESCE(w.tonaz, 0) AS w_plan,
                   COALESCE(w.tonaz_rzeczywisty, 0) AS w_real
            FROM plan_produkcji z
            LEFT JOIN plan_produkcji w
                ON w.zasyp_id = z.id AND LOWER(w.sekcja) = 'workowanie'
            WHERE DATE(z.data_planu) = %s
              AND z.status = 'zakonczone'
              AND LOWER(z.sekcja) = 'zasyp'
            ORDER BY z.id
        """, (current_data,))
        
        all_plans = cursor.fetchall()
        conn.close()
        
        details = []
        total_remaining = 0
        
        for plan in all_plans:
            # Only consider entries that have a Workowanie plan — transfer is based on Workowanie
            if plan['workowanie_id'] is None:
                continue

            w_plan = plan['w_plan']
            w_real = plan['w_real']

            # Remaining to pack = Workowanie.tonaz - Workowanie.tonaz_rzeczywisty
            workowanie_remaining = max(0.0, w_plan - w_real)

            if workowanie_remaining <= 0:
                continue

            total_remaining += workowanie_remaining
            details.append({
                'plan_id': plan['zasyp_id'],
                'produkt': plan['produkt'],
                # Show 'Zasypano' as the Workowanie planned tonage (we base on Workowanie)
                'plan_kg': w_plan,
                'wykonanie_kg': w_real,
                'remaining_kg': workowanie_remaining,
                'zasyp_shortfall_kg': 0,
            })
        
        if not details:
            # Return a simple, user-facing message: if anything is not closed, transfer is not allowed
            simple_msg = 'Jeśli coś jest niezamknięte, nie można przenieść zlecenia.'
            return jsonify({'success': False, 'message': simple_msg}), 400
        
        return jsonify({
            'success': True,
            'current_date': current_data,
            'next_date': next_data_str,
            'current_date_formatted': current_date.strftime('%d.%m.%Y'),
            'next_date_formatted': next_date.strftime('%d.%m.%Y'),
            'plans': details,
            'total_remaining_kg': total_remaining,
            'count': len(details)
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Error in api_check_niezrealizowane: {str(e)}')
        return jsonify({'success': False, 'message': f'Błąd serwera: {str(e)}'}), 500


@planista_bp.route('/api/check_zlecenie', methods=['POST'])
@roles_required('planista', 'admin', 'lider')
def api_check_zlecenie():
    """Check given plan (zlecenie) and report which parts are still active / not closed and in which section."""
    try:
        data = request.get_json() or {}
        plan_id = data.get('plan_id') or request.args.get('plan_id')
        if not plan_id:
            return jsonify({'success': False, 'message': 'Brak plan_id'}), 400
        try:
            plan_id = int(plan_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowe plan_id'}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, status, real_start, real_stop FROM plan_produkcji WHERE id = %s", (plan_id,))
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
                cursor.execute("SELECT id, sekcja, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji WHERE zasyp_id = %s AND LOWER(sekcja) = 'workowanie' LIMIT 1", (plan_id,))
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
            cursor.execute("SELECT COALESCE(SUM(waga),0) AS szarze_sum FROM szarze WHERE plan_id = %s", (plan_id,))
            r = cursor.fetchone()
            related['szarze_sum_kg'] = float(r.get('szarze_sum') or 0)

            # palety summary (for Workowanie)
            cursor.execute("SELECT COUNT(*) AS count, COALESCE(SUM(waga),0) AS total_kg FROM palety_workowanie WHERE plan_id = %s", (plan_id,))
            r = cursor.fetchone()
            related['palety_count'] = int(r.get('count') or 0)
            related['palety_total_kg'] = float(r.get('total_kg') or 0)

            # bufor entries related (zasyp_id or plan_id)
            cursor.execute("SELECT id, zasyp_id, data_planu, produkt, spakowano, status FROM bufor WHERE zasyp_id = %s OR plan_id = %s", (plan_id, plan_id))
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
