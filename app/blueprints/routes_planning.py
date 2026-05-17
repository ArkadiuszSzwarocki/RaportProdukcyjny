"""Planning and management routes (formerly in routes_api.py ZARZĄDZANIE section)."""

from flask import Blueprint, request, session, url_for
from datetime import date, datetime
from app.blueprints.routes_planning_adjustments import register_planning_adjustment_routes
from app.blueprints.routes_planning_creation import register_planning_creation_routes
from app.blueprints.routes_planning_lifecycle import register_planning_lifecycle_routes
from app.blueprints.routes_planning_quality import register_planning_quality_routes
from app.decorators import roles_required

planning_bp = Blueprint('planning', __name__)


def bezpieczny_powrot():
    """Return to appropriate view based on user role."""
    # Prefer returning to explicit context from current action.
    sekcja = request.args.get('sekcja') or request.form.get('sekcja')
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())

    if sekcja:
        return url_for('main.index', sekcja=sekcja, data=data, linia=linia)

    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        return url_for('planista.panel_planisty', data=data)

    role = session.get('rola', '')
    if role in ['lider', 'produkcja']:
        return url_for('planista.bufor_page')
    if role == 'admin':
        return url_for('admin.admin_panel')

    return url_for('main.index', sekcja='Zasyp', data=data, linia=linia)


# Use `log_plan_history` implementation from `app.db` to avoid duplicate logic
register_planning_adjustment_routes(planning_bp, return_url_builder=bezpieczny_powrot)
register_planning_creation_routes(planning_bp, return_url_builder=bezpieczny_powrot)
register_planning_lifecycle_routes(planning_bp, return_url_builder=bezpieczny_powrot)
register_planning_quality_routes(planning_bp, return_url_builder=bezpieczny_powrot)


@planning_bp.route('/api/plan/<int:plan_id>/summary', methods=['GET'])
@roles_required('planista', 'admin', 'zarzad', 'masteradmin')
def plan_summary_report(plan_id):
    from app.db import get_db_connection, get_table_name
    from flask import request
    
    is_agro = request.args.get('is_agro', '0') == '1'
    linia = 'AGRO' if is_agro else 'PSD'
    
    table_plan = get_table_name('plan_produkcji', linia)
    table_szarze = get_table_name('szarze', linia)
    table_palety = get_table_name('palety_workowanie', linia)
    table_dosypki = get_table_name('dosypki', linia)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Fetch primary plan
        cursor.execute(f"""
            SELECT id, produkt, tonaz, status, real_start, real_stop, tonaz_rzeczywisty, 
                   typ_produkcji, uszkodzone_worki, nr_receptury, zasyp_id, sekcja, data_planu
            FROM {table_plan} WHERE id = %s AND is_deleted = 0
        """, (plan_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {'success': False, 'error': 'Plan not found'}, 404
            
        plan_data = {
            'id': row[0],
            'produkt': row[1],
            'tonaz_plan': float(row[2] or 0),
            'status': row[3],
            'real_start': row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None,
            'real_stop': row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else None,
            'tonaz_rzeczywisty': float(row[6] or 0),
            'typ_produkcji': row[7],
            'uszkodzone_worki': int(row[8] or 0),
            'nr_receptury': row[9],
            'zasyp_id': row[10],
            'sekcja': row[11],
            'data_planu': str(row[12])
        }
        
        # 2. Fetch linked plan (Zasyp <-> Workowanie)
        linked_plan_data = None
        if plan_data['sekcja'] == 'Zasyp':
            if is_agro:
                cursor.execute(f"""
                    SELECT id, tonaz, status, real_start, real_stop, tonaz_rzeczywisty, uszkodzone_worki
                    FROM {table_plan} WHERE zasyp_id = %s AND sekcja = 'Workowanie' AND is_deleted = 0 LIMIT 1
                """, (plan_id,))
            else:
                cursor.execute(f"""
                    SELECT id, tonaz, status, real_start, real_stop, tonaz_rzeczywisty, uszkodzone_worki
                    FROM {table_plan} 
                    WHERE DATE(data_planu) = %s AND produkt = %s AND sekcja = 'Workowanie' AND is_deleted = 0 LIMIT 1
                """, (row[12], plan_data['produkt']))
            w_row = cursor.fetchone()
            if w_row:
                linked_plan_data = {
                    'id': w_row[0],
                    'sekcja': 'Workowanie',
                    'tonaz_plan': float(w_row[1] or 0),
                    'status': w_row[2],
                    'real_start': w_row[3].strftime('%Y-%m-%d %H:%M:%S') if w_row[3] else None,
                    'real_stop': w_row[4].strftime('%Y-%m-%d %H:%M:%S') if w_row[4] else None,
                    'tonaz_rzeczywisty': float(w_row[5] or 0),
                    'uszkodzone_worki': int(w_row[6] or 0)
                }
        else:
            if is_agro and plan_data['zasyp_id']:
                cursor.execute(f"""
                    SELECT id, tonaz, status, real_start, real_stop, tonaz_rzeczywisty
                    FROM {table_plan} WHERE id = %s AND sekcja = 'Zasyp' AND is_deleted = 0 LIMIT 1
                """, (plan_data['zasyp_id'],))
            else:
                cursor.execute(f"""
                    SELECT id, tonaz, status, real_start, real_stop, tonaz_rzeczywisty
                    FROM {table_plan} 
                    WHERE DATE(data_planu) = %s AND produkt = %s AND sekcja = 'Zasyp' AND is_deleted = 0 LIMIT 1
                """, (row[12], plan_data['produkt']))
            z_row = cursor.fetchone()
            if z_row:
                linked_plan_data = {
                    'id': z_row[0],
                    'sekcja': 'Zasyp',
                    'tonaz_plan': float(z_row[1] or 0),
                    'status': z_row[2],
                    'real_start': z_row[3].strftime('%Y-%m-%d %H:%M:%S') if z_row[3] else None,
                    'real_stop': z_row[4].strftime('%Y-%m-%d %H:%M:%S') if z_row[4] else None,
                    'tonaz_rzeczywisty': float(z_row[5] or 0)
                }

        zasyp_plan_id = plan_id if plan_data['sekcja'] == 'Zasyp' else (linked_plan_data['id'] if linked_plan_data else None)
        work_plan_id = plan_id if plan_data['sekcja'] == 'Workowanie' else (linked_plan_data['id'] if linked_plan_data else None)

        # 3. Fetch Szarże
        szarze = []
        if zasyp_plan_id:
            cursor.execute(f"""
                SELECT s.id, s.waga, s.godzina, s.status, COALESCE(p.imie_nazwisko, s.pracownik_id), COALESCE(s.uwagi, '')
                FROM {table_szarze} s
                LEFT JOIN pracownicy p ON s.pracownik_id = p.id
                WHERE s.plan_id = %s ORDER BY s.id ASC
            """, (zasyp_plan_id,))
            sz_rows = cursor.fetchall()
            
            dosypki = {}
            if sz_rows:
                sz_ids = [r[0] for r in sz_rows]
                fmt_sz = ','.join(['%s'] * len(sz_ids))
                cursor.execute(f"""
                    SELECT szarza_id, nazwa, kg FROM {table_dosypki}
                    WHERE szarza_id IN ({fmt_sz}) AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0
                """, sz_ids)
                for d_row in cursor.fetchall():
                    sz_id = d_row[0]
                    dosypki.setdefault(sz_id, []).append({'nazwa': d_row[1], 'kg': float(d_row[2] or 0)})
            
            for r in sz_rows:
                sz_id = r[0]
                sz_dosypki = dosypki.get(sz_id, [])
                suma_dosypki = sum(d['kg'] for d in sz_dosypki)
                szarze.append({
                    'id': sz_id,
                    'waga_baza': float(r[1] or 0),
                    'waga_total': float(r[1] or 0) + suma_dosypki,
                    'godzina': r[2].strftime('%H:%M:%S') if r[2] else '',
                    'status': r[3],
                    'pracownik': r[4],
                    'uwagi': r[5],
                    'dosypki': sz_dosypki
                })

        # 4. Fetch Palety
        palety = []
        if work_plan_id:
            cursor.execute(f"""
                SELECT id, waga, data_dodania, COALESCE(dodal_login, ''), status
                FROM {table_palety} WHERE plan_id = %s ORDER BY id ASC
            """, (work_plan_id,))
            for r in cursor.fetchall():
                palety.append({
                    'id': r[0],
                    'waga': float(r[1] or 0),
                    'godzina': r[2].strftime('%H:%M:%S') if r[2] else '',
                    'dodal': r[3],
                    'status': r[4]
                })

        # 5. Fetch Packaging Foil (for Agro)
        foil_info = None
        if is_agro and work_plan_id:
            cursor.execute("""
                SELECT mo.nazwa, mo.symbol, mo.lokalizacja
                FROM agro_plan_opakowania apo
                INNER JOIN magazyn_opakowania mo ON apo.opakowanie_id = mo.id
                WHERE apo.plan_id = %s AND apo.is_active = 1 LIMIT 1
            """, (work_plan_id,))
            f_row = cursor.fetchone()
            if f_row:
                foil_info = {
                    'nazwa': f_row[0],
                    'symbol': f_row[1],
                    'lokalizacja': f_row[2]
                }

        # 6. Calculate times and efficiencies
        zasyp_time_min = 0
        zasyp_yield = 0
        zasyp_actual_kg = 0
        if zasyp_plan_id:
            z_plan = plan_data if plan_data['sekcja'] == 'Zasyp' else linked_plan_data
            zasyp_actual_kg = sum(s['waga_total'] for s in szarze)
            if z_plan['real_start'] and z_plan['real_stop']:
                start_dt = datetime.fromisoformat(z_plan['real_start'])
                stop_dt = datetime.fromisoformat(z_plan['real_stop'])
                zasyp_time_min = int((stop_dt - start_dt).total_seconds() / 60)
                if zasyp_time_min > 0:
                    zasyp_yield = int((zasyp_actual_kg / zasyp_time_min) * 60)
                    
        work_time_min = 0
        work_yield = 0
        work_actual_kg = 0
        if work_plan_id:
            w_plan = plan_data if plan_data['sekcja'] == 'Workowanie' else linked_plan_data
            work_actual_kg = sum(p['waga'] for p in palety)
            if w_plan['real_start'] and w_plan['real_stop']:
                start_dt = datetime.fromisoformat(w_plan['real_start'])
                stop_dt = datetime.fromisoformat(w_plan['real_stop'])
                work_time_min = int((stop_dt - start_dt).total_seconds() / 60)
                if work_time_min > 0:
                    work_yield = int((work_actual_kg / work_time_min) * 60)

        conn.close()
        
        return {
            'success': True,
            'is_agro': is_agro,
            'plan': plan_data,
            'linked_plan': linked_plan_data,
            'szarze': szarze,
            'palety': palety,
            'foil': foil_info,
            'metrics': {
                'zasyp_actual_kg': zasyp_actual_kg,
                'zasyp_time_min': zasyp_time_min,
                'zasyp_yield_kg_h': zasyp_yield,
                'work_actual_kg': work_actual_kg,
                'work_time_min': work_time_min,
                'work_yield_kg_h': work_yield,
                'total_uszkodzone_worki': plan_data['uszkodzone_worki'] if plan_data['sekcja'] == 'Workowanie' else (linked_plan_data['uszkodzone_worki'] if linked_plan_data else 0)
            }
        }
        
    except Exception as e:
        if conn:
            conn.close()
        return {'success': False, 'error': str(e)}, 500



