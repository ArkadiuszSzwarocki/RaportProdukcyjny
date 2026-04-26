from flask import Blueprint, render_template, request, current_app, session, jsonify
from app.db import get_db_connection, get_table_name
from app.dto.paleta import PaletaDTO
from app.services.notification_service import notify_workers_about_plan_change
from app.services.planning_service import PlanningService
from datetime import date, datetime, timedelta
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
    wybrana_data = request.args.get('data', str(date.today()))
    wybrana_linia = request.args.get('linia', 'PSD').upper()
    aktywna_zakladka = request.args.get('tab', '').lower()
    if not aktywna_zakladka:
        aktywna_zakladka = 'agro' if wybrana_linia == 'AGRO' else 'psd'

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        if aktywna_zakladka not in ('psd', 'agro'):
            aktywna_zakladka = 'psd'
            
        table_plan = get_table_name('plan_produkcji', wybrana_linia)
 
        # 1. Fetch primary plans (Zasyp + Czyszczenie)
        cursor.execute(f"""
            SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, 
                   COALESCE(uszkodzone_worki, 0) AS uszkodzone_worki, 
                   COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia, 
                   zasyp_id
            FROM {table_plan} 
            WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
            ORDER BY kolejnosc
        """, (wybrana_data,))
        plany_list = [dict(p) for p in cursor.fetchall()]

        # 2. Add standalone Workowanie rows (avoiding duplicates and cases already covered by Zasyp)
        cursor.execute(f"""
            SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, 
                   COALESCE(uszkodzone_worki, 0) AS uszkodzone_worki, 
                   COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia, 
                   zasyp_id
            FROM {table_plan}
            WHERE data_planu = %s AND LOWER(sekcja) = 'workowanie'
            ORDER BY kolejnosc
        """, (wybrana_data,))
        work_rows = cursor.fetchall()
        for w in work_rows:
            if any(p['id'] == w['id'] for p in plany_list): continue
            prod_name = (w['produkt'] or '').strip().lower()
            matching_zasyp = next(
                (p for p in plany_list if p['sekcja'].lower() == 'zasyp' and (p['produkt'] or '').strip().lower() == prod_name),
                None
            )
            if matching_zasyp is not None:
                # Merge uszkodzone_worki from Workowanie into Zasyp
                matching_zasyp['uszkodzone_worki'] = (matching_zasyp.get('uszkodzone_worki') or 0) + (w.get('uszkodzone_worki') or 0)
                
                # Ghost Zasyp (zakonczone + carry-over): zapisz ID Workowania żeby planista mógł edytować tonaż
                if matching_zasyp.get('status') == 'zakonczone':
                    matching_zasyp['linked_workowanie_id'] = w['id']
                    matching_zasyp['linked_workowanie_tonaz'] = w['tonaz'] or 0
                    matching_zasyp['_work_nazwa'] = w.get('nazwa_zlecenia', '') or ''
                continue
            plany_list.append(dict(w))

        # 2b. Oznacz plany przeniesione z innego dnia (na podstawie plan_history + nazwa_zlecenia)
        if plany_list:
            from datetime import datetime as _dt
            plan_ids = [p['id'] for p in plany_list]
            fmt_ids = ','.join(['%s'] * len(plan_ids))
            cursor.execute(f"""
                SELECT ph.plan_id,
                       SUBSTRING_INDEX(SUBSTRING_INDEX(ph.changes, ' na ', 1), 'Z ', -1) AS stara_data
                FROM plan_history ph
                INNER JOIN (
                    SELECT plan_id, MAX(id) AS max_id FROM plan_history
                    WHERE action = 'przeniesienie' AND plan_id IN ({fmt_ids})
                    GROUP BY plan_id
                ) last ON last.plan_id = ph.plan_id AND last.max_id = ph.id
            """, plan_ids)
            przeniesione_map = {r['plan_id']: r['stara_data'] for r in cursor.fetchall()}
            for p in plany_list:
                stara = przeniesione_map.get(p['id'])
                if stara and stara != wybrana_data:
                    try:
                        p['przeniesiony_z'] = _dt.strptime(stara, '%Y-%m-%d').strftime('%d.%m.%Y')
                    except Exception:
                        p['przeniesiony_z'] = stara
                else:
                    # Sprawdź carry-over przez nazwa_zlecenia (lub fallback z powiązanego Workowania)
                    nazwa = p.get('nazwa_zlecenia', '') or ''
                    src = ''
                    for prefix in ('PRZENIESIONE z ', 'carry-over z '):
                        if nazwa.startswith(prefix):
                            raw_date = nazwa[len(prefix):].strip()
                            try:
                                src = _dt.strptime(raw_date, '%Y-%m-%d').strftime('%d.%m.%Y')
                            except Exception:
                                pass
                            break
                    # Fallback: sprawdź nazwa_zlecenia powiązanego Workowania (gdy ghost Zasyp ma buf_nazwa)
                    if not src and p.get('_work_nazwa'):
                        work_nazwa = p['_work_nazwa']
                        for prefix in ('PRZENIESIONE z ', 'carry-over z '):
                            if work_nazwa.startswith(prefix):
                                raw_date = work_nazwa[len(prefix):].strip()
                                try:
                                    src = _dt.strptime(raw_date, '%Y-%m-%d').strftime('%d.%m.%Y')
                                except Exception:
                                    pass
                                break
                    p['przeniesiony_z'] = src or None
                p['przeniesiony_tonaz'] = 0  # placeholder, wypełniany poniżej

            # Lookup bufor.tonaz_rzeczywisty dla planów carry-over (oryginalna kwota przenosin)
            table_bufor_local = get_table_name('bufor', wybrana_linia)
            zasyp_id_to_plan = {}
            for p in plany_list:
                if p.get('przeniesiony_z') and p.get('zasyp_id'):
                    zasyp_id_to_plan[p['zasyp_id']] = p
            if zasyp_id_to_plan:
                fmt_zids = ','.join(['%s'] * len(zasyp_id_to_plan))
                cursor.execute(f"""
                    SELECT zasyp_id, tonaz_rzeczywisty
                    FROM {table_bufor_local}
                    WHERE zasyp_id IN ({fmt_zids}) AND status IN ('aktywny', 'zamkniete', 'przeniesiony')
                    ORDER BY id DESC
                """, list(zasyp_id_to_plan.keys()))
                seen = set()
                for row in cursor.fetchall():
                    zid = row['zasyp_id']
                    if zid not in seen:
                        seen.add(zid)
                        plan_ref = zasyp_id_to_plan[zid]
                        plan_ref['przeniesiony_tonaz'] = int(row['tonaz_rzeczywisty']) if row['tonaz_rzeczywisty'] else 0
        else:
            for p in plany_list:
                p['przeniesiony_z'] = None
                p['przeniesiony_tonaz'] = 0

        # 3. Process primary list details (Execution, Time, Palety)
        suma_plan, suma_wyk, suma_minut_plan = 0, 0, 0
        palety_mapa = {}
        # Dynamic table names for the current context
        t_sz_curr = get_table_name('szarze', wybrana_linia)
        t_ds_curr = get_table_name('dosypki', wybrana_linia)
        t_pa_curr = get_table_name('palety_workowanie', wybrana_linia)
        t_pp_curr = get_table_name('plan_produkcji', wybrana_linia)

        for p in plany_list:
            w_p = p['tonaz'] or 0
            t_p = p['typ_produkcji']
            norma = calculate_kg_per_hour(t_p) if t_p else calculate_kg_per_hour('bigbag')
            dur = int((w_p / norma) * 60) if norma > 0 else 0
            p['estymacja_minut'] = dur
            
            if p['sekcja'].lower() != 'czyszczenie':
                suma_plan += w_p
                # execution - use current context tables with clean alias
                cursor.execute(f"SELECT (COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {t_ds_curr} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0)) as total FROM {t_sz_curr} WHERE plan_id = %s", (p['id'], p['id']))
                sz_r = cursor.fetchone()
                wyk_val = sz_r['total'] if sz_r and sz_r['total'] is not None else p['tonaz_rzeczywisty'] or 0
                p['tonaz_rzeczywisty'] = wyk_val
                suma_wyk += wyk_val
            suma_minut_plan += dur

            # palety details - use current context tables
            cursor.execute(f"SELECT pw.id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania FROM {t_pa_curr} pw JOIN {t_pp_curr} pp ON pw.plan_id = pp.id WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.sekcja = 'Workowanie' ORDER BY pw.id DESC", (wybrana_data, p['produkt']))
            p_rows = cursor.fetchall()
            palety_mapa[p['id']] = [(r['waga'], (r['data_dodania'].strftime('%H:%M') if hasattr(r['data_dodania'], 'strftime') else str(r['data_dodania'])), r['tara'], r['waga_brutto']) for r in p_rows]

        # 4. Process Agro details (always needed for the side indicators or if requested)
        plany_agro = []
        suma_plan_agro, suma_wyk_agro, suma_minut_plan_agro = 0, 0, 0
        t_pp_agro = get_table_name('plan_produkcji', 'AGRO')
        t_sz_agro = get_table_name('szarze', 'AGRO')
        t_ds_agro = get_table_name('dosypki', 'AGRO')
        t_pa_agro = get_table_name('palety_workowanie', 'AGRO')

        cursor.execute(f"""
            SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, 
                   COALESCE(uszkodzone_worki, 0) AS uszkodzone_worki,
                   COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia,
                   zasyp_id
            FROM {t_pp_agro} 
            WHERE data_planu = %s 
            ORDER BY kolejnosc
        """, (wybrana_data,))
        agro_all = [dict(r) for r in cursor.fetchall()]
        
        # 1. First Pass: Collect products that have a 'Zasyp' entry
        z_prod_a = {(r['produkt'] or '').strip().lower() for r in agro_all if r['sekcja'].lower() == 'zasyp'}
        
        # 2. Second Pass: Filter and Merge
        plany_agro = []
        zasyp_lookup = {}
        
        for r in agro_all:
            sect = r['sekcja'].lower()
            p_name = (r['produkt'] or '').strip().lower()
            
            if sect == 'zasyp':
                zasyp_lookup[p_name] = r
                plany_agro.append(r)
            elif sect == 'workowanie':
                if p_name in z_prod_a:
                    # Merge data into existing Zasyp row (if already encountered) or just wait for aggregation
                    # Since we sorted by kolejnosc, Zasyp might come before OR after Workowanie
                    # We'll handle aggregation in a separate step to be safe
                    continue
                else:
                    # Standalone Workowanie
                    plany_agro.append(r)
            else:
                # Czyszczenie etc
                plany_agro.append(r)
                
        # 3. Third Pass: Aggregate uszkodzone_worki from ALL rows into the displayed row
        for r in agro_all:
            if r['sekcja'].lower() == 'workowanie' and (r['produkt'] or '').strip().lower() in z_prod_a:
                p_name = (r['produkt'] or '').strip().lower()
                target = zasyp_lookup.get(p_name)
                if target:
                    target['uszkodzone_worki'] = (target.get('uszkodzone_worki') or 0) + (r.get('uszkodzone_worki') or 0)

        # 4. Fourth Pass: Detect carry-over (similar to PSD logic)
        if plany_agro:
            from datetime import datetime as _dt
            agro_ids = [p['id'] for p in plany_agro]
            fmt_a_ids = ','.join(['%s'] * len(agro_ids))
            cursor.execute(f"""
                SELECT ph.plan_id,
                       SUBSTRING_INDEX(SUBSTRING_INDEX(ph.changes, ' na ', 1), 'Z ', -1) AS stara_data
                FROM plan_history ph
                INNER JOIN (
                    SELECT plan_id, MAX(id) AS max_id FROM plan_history
                    WHERE action = 'przeniesienie' AND plan_id IN ({fmt_a_ids})
                    GROUP BY plan_id
                ) last ON last.plan_id = ph.plan_id AND last.max_id = ph.id
            """, agro_ids)
            przeniesione_a_map = {r['plan_id']: r['stara_data'] for r in cursor.fetchall()}
            
            for p in plany_agro:
                stara = przeniesione_a_map.get(p['id'])
                if stara and stara != wybrana_data:
                    try:
                        p['przeniesiony_z'] = _dt.strptime(stara, '%Y-%m-%d').strftime('%d.%m.%Y')
                    except Exception:
                        p['przeniesiony_z'] = stara
                else:
                    nazwa = p.get('nazwa_zlecenia', '') or ''
                    src = ''
                    for prefix in ('PRZENIESIONE z ', 'carry-over z '):
                        if nazwa.startswith(prefix):
                            raw_date = nazwa[len(prefix):].strip()
                            try:
                                src = _dt.strptime(raw_date, '%Y-%m-%d').strftime('%d.%m.%Y')
                            except Exception:
                                pass
                            break
                    p['przeniesiony_z'] = src or None
                p['przeniesiony_tonaz'] = 0

            # Lookup bufor.tonaz_rzeczywisty for carry-over Agro
            t_bf_agro = get_table_name('bufor', 'AGRO')
            zasyp_id_to_agro = {p['zasyp_id']: p for p in plany_agro if p.get('przeniesiony_z') and p.get('zasyp_id')}
            if zasyp_id_to_agro:
                fmt_zids_a = ','.join(['%s'] * len(zasyp_id_to_agro))
                cursor.execute(f"""
                    SELECT zasyp_id, tonaz_rzeczywisty
                    FROM {t_bf_agro}
                    WHERE zasyp_id IN ({fmt_zids_a}) AND status IN ('aktywny', 'zamkniete', 'przeniesiony')
                    ORDER BY id DESC
                """, list(zasyp_id_to_agro.keys()))
                seen_a = set()
                for row in cursor.fetchall():
                    zid = row['zasyp_id']
                    if zid not in seen_a:
                        seen_a.add(zid)
                        plan_ref = zasyp_id_to_agro[zid]
                        plan_ref['przeniesiony_tonaz'] = int(row['tonaz_rzeczywisty']) if row['tonaz_rzeczywisty'] else 0
        else:
            for p in plany_agro:
                p['przeniesiony_z'] = None
                p['przeniesiony_tonaz'] = 0

        for p in plany_agro:
            w_a = p['tonaz'] or 0
            t_a = p['typ_produkcji']
            norma_a = calculate_kg_per_hour(t_a) if t_a else calculate_kg_per_hour('bigbag')
            dur_a = int((w_a / norma_a) * 60) if norma_a > 0 else 0
            p['estymacja_minut'] = dur_a
            
            if p['sekcja'].lower() != 'czyszczenie':
                suma_plan_agro += w_a
                # execution - use clean alias
                cursor.execute(f"SELECT (COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {t_ds_agro} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0)) as total FROM {t_sz_agro} WHERE plan_id = %s", (p['id'], p['id']))
                res_a = cursor.fetchone()
                wyk_a = res_a['total'] if res_a and res_a['total'] is not None else p['tonaz_rzeczywisty'] or 0
                p['tonaz_rzeczywisty'] = wyk_a
                suma_wyk_agro += wyk_a
            suma_minut_plan_agro += dur_a

            # palety details Agro
            cursor.execute(f"SELECT pw.id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania FROM {t_pa_agro} pw JOIN {t_pp_agro} pp ON pw.plan_id = pp.id WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.sekcja = 'Workowanie' ORDER BY pw.id DESC", (wybrana_data, p['produkt']))
            pa_rows = cursor.fetchall()
            palety_mapa[p['id']] = [(r['waga'], (r['data_dodania'].strftime('%H:%M') if hasattr(r['data_dodania'], 'strftime') else str(r['data_dodania'])), r['tara'], r['waga_brutto']) for r in pa_rows]

        # 5. Settlement (Rozliczenie)
        rozliczenia = []
        cur_tab_line = 'AGRO' if aktywna_zakladka == 'agro' else 'PSD'
        cur_tab_plany = plany_agro if aktywna_zakladka == 'agro' else plany_list
        t_sz_r = get_table_name('szarze', cur_tab_line)
        t_ds_r = get_table_name('dosypki', cur_tab_line)
        t_pa_r = get_table_name('palety_workowanie', cur_tab_line)
        t_bf_r = get_table_name('bufor', cur_tab_line)
        t_pp_r = get_table_name('plan_produkcji', cur_tab_line)
        
        for p in cur_tab_plany:
            if p['sekcja'].lower() != 'zasyp': continue
            z_id, prod_r, p_z = p['id'], p['produkt'], p['tonaz'] or 0
            cursor.execute(f"SELECT (COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {t_ds_r} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0)) as total FROM {t_sz_r} WHERE plan_id = %s", (z_id, z_id))
            z_kg = cursor.fetchone()['total'] or 0
            cursor.execute(f"SELECT COALESCE(SUM(CASE WHEN waga_potwierdzona > 0 THEN waga_potwierdzona ELSE waga END), 0) as total FROM {t_pa_r} WHERE plan_id IN (SELECT id FROM {t_pp_r} WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie' AND produkt = %s)", (wybrana_data, prod_r))
            spak_kg = cursor.fetchone()['total'] or 0
            cursor.execute(f"SELECT SUM(tonaz_rzeczywisty - spakowano) as total FROM {t_bf_r} WHERE zasyp_id = %s AND data_planu = %s AND status = 'aktywny'", (z_id, wybrana_data))
            buf_kg = cursor.fetchone()['total'] or 0
            cursor.execute(f"SELECT COALESCE(SUM(tonaz), 0) as total FROM {t_pp_r} WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'workowanie' AND produkt = %s", (wybrana_data, prod_r))
            plan_wor_kg = cursor.fetchone()['total'] or 0
            # Dla ghost Zasyp (carry_over): jeśli nie znaleziono przez produkt, użyj linked_workowanie_tonaz
            if plan_wor_kg == 0 and p.get('linked_workowanie_tonaz'):
                plan_wor_kg = p['linked_workowanie_tonaz']
            
            rozliczenia.append({
                'zasyp_id': z_id, 'produkt': prod_r, 'status': p['status'],
                'planowany_zasyp': round(float(p_z), 1), 'zasyp_kg': round(float(z_kg), 1),
                'plan_workowanie': round(float(plan_wor_kg), 1), 'spakowano_palety': round(float(spak_kg), 1),
                'bufor_spakowano': round(float(buf_kg), 1),
                'diff_no_buf': round(float(z_kg) - float(spak_kg), 1), 'diff_with_buf': round(float(z_kg) - (float(spak_kg) + float(buf_kg)), 1)
            })

        # 6. Final aggregated values
        procent = (suma_wyk / suma_plan * 100) if suma_plan > 0 else 0
        procent_agro = (suma_wyk_agro / suma_plan_agro * 100) if suma_plan_agro > 0 else 0
        procent_czasu = (suma_minut_plan / 450 * 100)
        
        # 7. Quality & Incomplete
        cursor.execute(f"SELECT id, produkt, tonaz, sekcja, status FROM {table_plan} WHERE data_planu=%s AND (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') AND status != 'zakonczone' ORDER BY id DESC", (wybrana_data,))
        quality_orders = cursor.fetchall()
        quality_count = len(quality_orders)
        
        has_incomplete_plans = any(p['status'] == 'zakonczone' and (p['tonaz_rzeczywisty'] or 0) < (p['tonaz'] or 0) for p in plany_list + plany_agro)
        has_incomplete_psd = any(p['status'] == 'zakonczone' and (p['tonaz_rzeczywisty'] or 0) < (p['tonaz'] or 0) for p in plany_list)
        has_incomplete_agro = any(p['status'] == 'zakonczone' and (p['tonaz_rzeczywisty'] or 0) < (p['tonaz'] or 0) for p in plany_agro)
        if not has_incomplete_psd:
            t_p_chk = get_table_name('plan_produkcji', 'PSD')
            cursor.execute(f"SELECT COUNT(*) as cnt FROM {t_p_chk} WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'workowanie' AND status = 'zakonczone' AND COALESCE(tonaz_rzeczywisty, 0) < COALESCE(tonaz, 0)", (wybrana_data,))
            if cursor.fetchone()['cnt'] > 0: has_incomplete_psd = True
        if not has_incomplete_agro:
            t_p_chk = get_table_name('plan_produkcji', 'AGRO')
            cursor.execute(f"SELECT COUNT(*) as cnt FROM {t_p_chk} WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'workowanie' AND status = 'zakonczone' AND COALESCE(tonaz_rzeczywisty, 0) < COALESCE(tonaz, 0)", (wybrana_data,))
            if cursor.fetchone()['cnt'] > 0: has_incomplete_agro = True
        has_incomplete_plans = has_incomplete_psd or has_incomplete_agro
        
        # 8. Bufor reminders (only previous day, not all past days)
        #    Baner widoczny tylko do 7:30 rano - po tym czasie zmiana juz trwa i przenoszenie nieaktualne
        bufor_remaining = []
        bufor_source_date = None
        bufor_source_date_fmt = None
        t_bf_now = get_table_name('bufor', wybrana_linia)
        from datetime import time as _time
        _now = datetime.now().time()
        _show_bufor_banner = (_now <= _time(7, 30)) or (wybrana_data != date.today().strftime('%Y-%m-%d'))
        if _show_bufor_banner:
            cursor.execute(f"SELECT produkt, SUM(COALESCE(tonaz_rzeczywisty, 0) - COALESCE(spakowano, 0)) as pozostalo FROM {t_bf_now} WHERE status = 'aktywny' AND data_planu = DATE_SUB(%s, INTERVAL 1 DAY) GROUP BY produkt HAVING pozostalo > 0", (wybrana_data,))
            bufor_remaining = [{'produkt': r['produkt'], 'pozostalo_kg': round(float(r['pozostalo']), 1)} for r in cursor.fetchall()]
            if bufor_remaining:
                # Ukryj produkty, dla których przeniesienie już zostało wykonane (carry_over_ghost istnieje na wybrana_data)
                juz_przeniesione = set()
                for linia_chk in ['PSD', 'AGRO']:
                    t_pp_chk = get_table_name('plan_produkcji', linia_chk)
                    try:
                        produkty_buf = [r['produkt'] for r in bufor_remaining]
                        fmt_buf = ','.join(['%s'] * len(produkty_buf))
                        cursor.execute(
                            f"SELECT DISTINCT produkt FROM {t_pp_chk} "
                            f"WHERE DATE(data_planu) = %s AND COALESCE(typ_zlecenia,'') = 'carry_over_ghost' "
                            f"AND produkt IN ({fmt_buf})",
                            [wybrana_data] + produkty_buf
                        )
                        for row in cursor.fetchall():
                            juz_przeniesione.add((row['produkt'] or '').strip().lower())
                    except Exception:
                        pass
                bufor_remaining = [r for r in bufor_remaining if (r['produkt'] or '').strip().lower() not in juz_przeniesione]
            if bufor_remaining:
                bufor_source_date = str((datetime.strptime(wybrana_data, '%Y-%m-%d') - timedelta(days=1)).date())
                _d = datetime.strptime(bufor_source_date, '%Y-%m-%d')
                bufor_source_date_fmt = _d.strftime('%d.%m.%Y')

        rola = session.get('rola')
        return render_template('planista.html',
                               plany=plany_list, wybrana_data=wybrana_data, wybrana_linia=wybrana_linia,
                               palety_mapa=palety_mapa, suma_plan=suma_plan, suma_wyk=suma_wyk,
                               procent=procent, suma_minut_plan=suma_minut_plan, procent_czasu=procent_czasu,
                               quality_count=quality_count, quality_orders=quality_orders,
                               rozliczenia=rozliczenia, current_role=rola, aktywna_zakladka=aktywna_zakladka,
                               plany_agro=plany_agro, suma_plan_agro=suma_plan_agro, suma_wyk_agro=suma_wyk_agro,
                               suma_minut_plan_agro=suma_minut_plan_agro, procent_agro=procent_agro,
                               has_incomplete_plans=has_incomplete_plans,
                               has_incomplete_psd=has_incomplete_psd, has_incomplete_agro=has_incomplete_agro,
                               bufor_remaining=bufor_remaining,
                               bufor_source_date=bufor_source_date, bufor_source_date_fmt=bufor_source_date_fmt)
    except Exception as e:
        import traceback
        error_msg = f"Error loading panel_planisty: {str(e)}\n{traceback.format_exc()}"
        current_app.logger.error(error_msg)
        return f"<pre>{error_msg}</pre>", 500
    finally:
        try: conn.close()
        except: pass


@planista_bp.route('/planista/add_czyszczenie', methods=['POST'])
@roles_required('planista', 'zarzad', 'admin')
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
            
            # Wpis z innego dnia niz wybrana_data = przeniesiony
            przeniesiony_z = None
            if str(z_data) != wybrana_data:
                try:
                    from datetime import datetime as _dt2
                    przeniesiony_z = _dt2.strptime(str(z_data), '%Y-%m-%d').strftime('%d.%m.%Y')
                except Exception:
                    przeniesiony_z = str(z_data)
            
            bufor_list.append({
                'id': z_id,
                'buf_id': buf_id,
                'zasyp_id': z_id,
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
                'start_time': start_time,
                'przeniesiony_z': przeniesiony_z
            })
        
        conn.close()
        
    except Exception as e:
        app_logger.error(f"ERROR in bufor_page for date {wybrana_data}: {type(e).__name__}: {str(e)}", exc_info=True)
        bufor_list = []
    
    return render_template('bufor.html', bufor_list=bufor_list, wybrana_data=wybrana_data, wybrana_linia=wybrana_linia)


@planista_bp.route('/bufor/rozlicz', methods=['POST'])
@roles_required('planista', 'admin', 'zarzad')
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
@roles_required('planista', 'admin', 'zarzad')
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


@planista_bp.route('/bufor/reorder', methods=['POST'])
@roles_required('planista', 'admin', 'zarzad')
def bufor_reorder():
    """Swap kolejka of two adjacent bufor entries (move up/down)."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        data = request.get_json(silent=True) or {}
        buf_id = data.get('buf_id')
        direction = data.get('direction')  # 'up' or 'down'
        linia = data.get('linia', 'PSD')

        if not buf_id or direction not in ('up', 'down'):
            return jsonify({'success': False, 'message': 'Brak wymaganych parametrów'}), 400

        buf_id = int(buf_id)
        table_bufor = get_table_name('bufor', linia)

        # Get current entry
        cursor.execute(f"SELECT id, kolejka, data_planu FROM {table_bufor} WHERE id = %s AND status = 'aktywny'", (buf_id,))
        current = cursor.fetchone()
        if not current:
            return jsonify({'success': False, 'message': 'Nie znaleziono wpisu w buforze'}), 404

        current_kolejka = current['kolejka']
        data_planu = current['data_planu']

        # Find neighbor
        if direction == 'up':
            cursor.execute(
                f"SELECT id, kolejka FROM {table_bufor} WHERE data_planu = %s AND status = 'aktywny' AND kolejka < %s ORDER BY kolejka DESC LIMIT 1",
                (data_planu, current_kolejka)
            )
        else:
            cursor.execute(
                f"SELECT id, kolejka FROM {table_bufor} WHERE data_planu = %s AND status = 'aktywny' AND kolejka > %s ORDER BY kolejka ASC LIMIT 1",
                (data_planu, current_kolejka)
            )

        neighbor = cursor.fetchone()
        if not neighbor:
            return jsonify({'success': False, 'message': 'Brak sąsiedniej pozycji do zamiany'}), 400

        # Swap kolejka values (use temp value to avoid unique constraint violation)
        neighbor_id = neighbor['id']
        neighbor_kolejka = neighbor['kolejka']

        temp_kolejka = -1
        cursor.execute(f"UPDATE {table_bufor} SET kolejka = %s WHERE id = %s", (temp_kolejka, buf_id))
        cursor.execute(f"UPDATE {table_bufor} SET kolejka = %s WHERE id = %s", (current_kolejka, neighbor_id))
        cursor.execute(f"UPDATE {table_bufor} SET kolejka = %s WHERE id = %s", (neighbor_kolejka, buf_id))
        conn.commit()

        return jsonify({'success': True, 'message': 'Kolejność zmieniona'}), 200
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.exception(f'Error in bufor_reorder: {str(e)}')
        return jsonify({'success': False, 'message': f'Błąd serwera: {str(e)}'}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@planista_bp.route('/bufor/create_zlecenie', methods=['POST'])
@roles_required('planista', 'admin', 'zarzad')
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
            if str(linia).upper() == 'AGRO':
                cursor.execute(f"""
                    SELECT 
                        zasyp_id,
                        data_planu,
                        produkt,
                        COALESCE(tonaz_rzeczywisty, 0) as tonaz_rzeczywisty,
                        typ_produkcji,
                        COALESCE(nazwa_zlecenia, '') as nazwa_zlecenia,
                        COALESCE(SUM(spakowano), 0) as spakowano
                    FROM {table_bufor}
                    WHERE zasyp_id = %s
                    GROUP BY zasyp_id, data_planu, produkt, typ_produkcji, nazwa_zlecenia
                    LIMIT 1
                """, (zasyp_id,))
                zasyp_data = cursor.fetchone()
                
                if not zasyp_data:
                    conn.close()
                    return jsonify({'success': False, 'message': 'Nie znaleziono wpisu w buforze dla tego Zasypu'}), 404
                
                z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa, spakowano = zasyp_data
                z_linia = 'AGRO'
            else:
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
            if str(linia).upper() == 'AGRO':
                cursor.execute(f"""
                    SELECT id, data_planu, produkt, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia
                    FROM {table_plan}
                    WHERE id = %s AND sekcja = 'Zasyp'
                """, (zasyp_id,))
                zasyp = cursor.fetchone()
                
                if not zasyp:
                    conn.close()
                    return jsonify({'success': False, 'message': 'Nie znaleziono Zasypu'}), 404
                
                z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa = zasyp
                z_linia = 'AGRO'
            else:
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
                
                if str(linia).upper() == 'AGRO':
                    cursor.execute(f"""
                        INSERT INTO {table_plan} 
                        (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, typ_zlecenia, tonaz_rzeczywisty)
                        VALUES (%s, %s, %s, 0, 'zakonczone', %s, %s, %s, 'carry_over_ghost', 0)
                    """, (
                        work_date, 'Zasyp', z_produkt, nk_zasyp, 
                        z_typ or 'worki_zgrzewane_25', f"Carry-over {source_date_str}"
                    ))
                else:
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
                if str(linia).upper() == 'AGRO':
                    cursor.execute(f"""
                        INSERT INTO {table_bufor} (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, tonaz_rzeczywisty, spakowano, kolejka, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 0, %s, 'aktywny')
                    """, (
                        final_zasyp_id, work_date, z_produkt, f"Carry-over {source_date_str}", 
                        z_typ or 'worki_zgrzewane_25', round(roznicza, 1), max_kol + 1
                    ))
                else:
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
        if str(linia).upper() == 'AGRO':
            cursor.execute(f"""
                INSERT INTO {table_plan} 
                (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, zasyp_id, tonaz_rzeczywisty)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
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
            ))
        else:
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
@roles_required('planista', 'admin', 'zarzad')
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
        
        linia = data_dict.get('linia') or 'PSD'
        
        # Call service method
        success, message, count = PlanningService.przenies_niezrealizowane(current_data, linia=linia)
        
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
@roles_required('planista', 'admin', 'zarzad')
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
        table_bufor = get_table_name('bufor', linia)
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query for unfinished production (Zasyp finished but Workowanie incomplete)
        # For PSD: uses zasyp_id FK; for AGRO: falls back to product-name matching (zasyp_id not used in AGRO)
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
              AND COALESCE(z.typ_zlecenia, '') != 'carry_over_ghost'
            ORDER BY z.id
        """, (current_data,))
        
        all_plans = cursor.fetchall()

        # Bufor: dla podglądu przeniesienia trzymaj się tej samej definicji co w buforze/przenoszeniu:
        # remaining = SUM(bufor.tonaz_rzeczywisty) - SUM(bufor.spakowano) dla aktywnych wpisów.
        bufor_remaining_by_zasyp_id = {}
        try:
            zasyp_ids = sorted({int(p['zasyp_id']) for p in all_plans if p.get('zasyp_id')})
            if zasyp_ids:
                placeholders = ','.join(['%s'] * len(zasyp_ids))
                cursor.execute(
                    f"""
                    SELECT zasyp_id,
                           COALESCE(SUM(tonaz_rzeczywisty), 0) AS buf_tonaz_rzeczywisty,
                           COALESCE(SUM(spakowano), 0) AS buf_spakowano
                    FROM {table_bufor}
                    WHERE DATE(data_planu) = %s
                      AND status = 'aktywny'
                      AND zasyp_id IN ({placeholders})
                    GROUP BY zasyp_id
                    """,
                    tuple([current_data] + zasyp_ids),
                )
                for r in cursor.fetchall():
                    try:
                        zid = int(r.get('zasyp_id'))
                    except Exception:
                        continue
                    buf_total = float(r.get('buf_tonaz_rzeczywisty') or 0.0)
                    buf_packed = float(r.get('buf_spakowano') or 0.0)
                    bufor_remaining_by_zasyp_id[zid] = max(0.0, buf_total - buf_packed)
        except Exception:
            # Bufor może być chwilowo niedostępny lub brak tabeli w środowisku testowym — wtedy fallback do starej logiki.
            bufor_remaining_by_zasyp_id = {}

        conn.close()
        
        details = []
        total_remaining = 0.0
        
        from datetime import datetime, timedelta
        current_date_obj = datetime.strptime(current_data, '%Y-%m-%d')
        next_date = current_date_obj + timedelta(days=1)
        next_data_str = next_date.strftime('%Y-%m-%d')

        for plan in all_plans:
            zasyp_id = int(plan['zasyp_id'])
            w_plan = float(plan['w_plan'] or 0.0)
            w_real = float(plan['w_real'] or 0.0)
            z_plan = float(plan['z_plan'] or 0.0)
            z_real = float(plan['z_real'] or 0.0)
            has_linked_workowanie = bool(plan.get('workowanie_id'))

            # Workowanie remaining (plan - real)
            rem_kg = max(0.0, w_plan - w_real)
            # Legacy fallback buffer estimate from plans (only when we have a linked Workowanie)
            in_buf_kg = max(0.0, z_real - w_real) if has_linked_workowanie else 0.0
            # Workowanie shortfall vs Zasyp real (informational)
            short_kg = max(0.0, w_plan - z_real)
            # Zasyp shortfall vs plan (may create companion Zasyp+Workowanie next day)
            z_short = max(0.0, z_plan - z_real)

            buf_rem = float(bufor_remaining_by_zasyp_id.get(zasyp_id, 0.0) or 0.0)

            # Preview should match actual move logic: buffer remainder first, then workowanie remainder.
            if buf_rem > 0:
                effective_rem = buf_rem
            elif rem_kg > 0:
                effective_rem = rem_kg
            elif in_buf_kg > 0:
                effective_rem = in_buf_kg
            elif z_short > 0:
                # Jeśli nie ma bufora i Workowania, a Zasyp ma niedobór — pokaż w liście (dla przeniesienia shortfall).
                effective_rem = z_short
            else:
                continue

            total_remaining += effective_rem
            details.append({
                'plan_id': int(plan['zasyp_id']),
                'produkt': str(plan['produkt']),
                'w_plan_kg': float(max(z_plan, w_plan)),
                'w_real_kg': float(w_real),
                'remaining_kg': float(effective_rem),
                'shortfall_kg': float(short_kg),
                'in_buffer_kg': float(buf_rem if buf_rem > 0 else in_buf_kg),
                'zasyp_shortfall_kg': float(z_short)
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
@roles_required('planista', 'admin', 'zarzad')
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
@roles_required('planista', 'admin', 'zarzad')
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
        
        linia = data_dict.get('linia') or 'PSD'
        
        # Use PlanningService to move selected plans
        from app.services.planning_service import PlanningService
        
        success, message, count = PlanningService.przenies_niezrealizowane(
            current_data,
            plan_ids_to_move=plan_ids,  # Pass selected plan IDs
            linia=linia
        )
        
        if success:
            resp_msg = message or 'Operacja zakończona pomyślnie.'
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
@roles_required('planista', 'admin', 'zarzad')
def planista_bulk_page():
    """Render page for bulk adding plans."""
    wybrana_data = request.args.get('data', str(date.today()))
    domyslna_sekcja = request.args.get('sekcja', 'Zasyp')
    return render_template('planista_bulk.html', wybrana_data=wybrana_data, domyslna_sekcja=domyslna_sekcja)
