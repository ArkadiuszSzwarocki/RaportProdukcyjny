import os
import sys
import re
from datetime import date, datetime
from flask import Blueprint, render_template, request, session, redirect, url_for, current_app as app

from app.db import get_db_connection, get_table_name
from app.decorators import roles_required, login_required, dynamic_role_required, masteradmin_required
from app.services.dashboard_service import DashboardService
from app.blueprints.routes_main_index_data import (
    build_dashboard_halls_context,
    build_allowed_work_start_ids,
    build_dosypki_maps,
    build_zasyp_etapy_context,
    build_agro_mix_context
)
from app.services.mqtt_service import get_latest_data
from app.blueprints.routes_main_layout import register_main_layout_routes
from app.blueprints.routes_main_misc import register_main_misc_routes
from app.blueprints.routes_main_reporting import register_main_reporting_routes

main_bp = Blueprint('main', __name__)

register_main_misc_routes(main_bp)
register_main_layout_routes(main_bp)
register_main_reporting_routes(main_bp)

@main_bp.route('/')
@login_required
def index():
    try:
        # Detect hall view from session or query param
        sess_hall = session.get('selected_hall_view')
        user_grupa = session.get('grupa', 'PSD').upper()
        aktywna_linia = request.args.get('linia') or sess_hall or user_grupa or 'PSD'
        
        # Force hall view if user has limited access
        if user_grupa != 'ALL' and user_grupa != 'ADMIN' and user_grupa != 'ZARZAD' and user_grupa != 'MASTERADMIN':
            if aktywna_linia != user_grupa:
                aktywna_linia = user_grupa
                
        aktywna_sekcja = request.args.get('sekcja', 'Dashboard')
        dzisiaj_str = request.args.get('data', str(date.today()))
        
        try:
            dzisiaj = date.fromisoformat(dzisiaj_str)
        except:
            dzisiaj = date.today()

        # Load everything via the central helper to ensure data parity with original system
        role = session.get('rola')
        halls_ctx = build_dashboard_halls_context(dzisiaj, aktywna_sekcja, aktywna_linia, role)
        
        halls_data = halls_ctx['halls_data']
        halls_to_fetch = halls_ctx['halls_to_fetch']
        hr_data = halls_ctx['hr_data']
        
        # We take the first hall data as primary (for single-hall views)
        main_h_data = halls_data.get(aktywna_linia, list(halls_data.values())[0] if halls_data else {})

        # Resolve allowed START ids
        allowed_work_start_ids = build_allowed_work_start_ids(
            dzisiaj, aktywna_linia, main_h_data.get('work_first_map', {}), app.logger
        )

        # Dosypki
        dosypki_mapa, dosypki_oczekujace_mapa = build_dosypki_maps(dzisiaj, aktywna_sekcja, aktywna_linia, app.logger)

        # Etapy Zasyp (kg/h, durations)
        zasyp_etapy_context = build_zasyp_etapy_context(
            main_h_data.get('plan_dnia', []),
            dzisiaj,
            aktywna_sekcja,
            aktywna_linia,
            app.logger,
        )
        
        # AGRO MIX
        agro_mix_mapa, agro_mix_dostepne = build_agro_mix_context(dzisiaj, aktywna_linia, app.logger)

        # Build final context
        context = {
            'halls_data': halls_data,
            'halls_to_fetch': halls_to_fetch,
            'sekcja': aktywna_sekcja,
            'linia': aktywna_linia,
            'pracownicy': hr_data['hr_dostepni'],
            'wszyscy_pracownicy': hr_data['hr_pracownicy'],
            'hr_pracownicy': hr_data['hr_pracownicy'],
            'hr_dostepni': hr_data['hr_dostepni'],
            'obsada': main_h_data.get('obsada'),
            'wpisy': main_h_data.get('wpisy'),
            'plan': main_h_data.get('plan_dnia'),
            'palety_mapa': main_h_data.get('palety_mapa'),
            'magazyn_palety': main_h_data.get('magazyn_palety'),
            'unconfirmed_palety': main_h_data.get('unconfirmed_palety'),
            'suma_plan': main_h_data.get('suma_plan'),
            'suma_wykonanie': main_h_data.get('suma_wykonanie'),
            'rola': role,
            'dzisiaj': dzisiaj,
            'dzisiaj_fmt': dzisiaj.strftime('%d.%m.%Y'),
            'raporty_hr': hr_data['raporty_hr'],
            'zasyp_rozpoczete': main_h_data.get('zasyp_rozpoczete'),
            'next_workowanie_id': main_h_data.get('next_workowanie_id'),
            'now_time': datetime.now().strftime('%H:%M'),
            'quality_count': main_h_data.get('quality_data', {}).get('quality_count'),
            'wnioski_pending': main_h_data.get('quality_data', {}).get('wnioski_pending'),
            'planned_leaves': hr_data['planned_leaves'],
            'recent_absences': hr_data['recent_absences'],
            'shift_notes': main_h_data.get('shift_notes'),
            'plans_zasyp': main_h_data.get('plans_zasyp'),
            'plans_workowanie': main_h_data.get('plans_workowanie'),
            'buffer_map': main_h_data.get('buffer_queue'),
            'global_active': main_h_data.get('global_active'),
            'active_products': main_h_data.get('active_products'),
            'zasyp_has_active': main_h_data.get('zasyp_has_active'),
            'work_first_map': main_h_data.get('work_first_map'),
            'zasyp_product_order': main_h_data.get('zasyp_product_order'),
            'allowed_work_start_ids': allowed_work_start_ids,
            'dosypki_mapa': dosypki_mapa,
            'dosypki_oczekujace_mapa': dosypki_oczekujace_mapa,
            'etapy_mapa': zasyp_etapy_context['etapy_mapa'],
            'etapy_parametry': zasyp_etapy_context['etapy_parametry'],
            'etapy_total': zasyp_etapy_context['etapy_total'],
            'etapy_curr_szarza': zasyp_etapy_context['etapy_curr_szarza'],
            'etapy_sesje_mapa': zasyp_etapy_context['etapy_sesje_mapa'],
            'kgph_stats_mapa': zasyp_etapy_context['kgph_stats_mapa'],
            'agro_mix_mapa': agro_mix_mapa,
            'agro_mix_dostepne': agro_mix_dostepne,
        }

        # --- AGRO Workowanie: focus mode + rozliczenie context ---
        agro_focus_mode = False
        workowanie_rozliczenie_ctx = None
        
        clean_sekcja = str(aktywna_sekcja or '').strip().lower()
        clean_linia = str(aktywna_linia or '').strip().upper()

        if clean_sekcja == 'workowanie' and clean_linia == 'AGRO':
            agro_ctx = DashboardService.get_agro_packaging_context(dzisiaj)
            workowanie_rozliczenie_ctx = {
                'active_plan': agro_ctx.get('active_plan'),
                'bag_kg': agro_ctx.get('bag_kg'),
                'palety_kg_wykonane': agro_ctx.get('palety_kg_wykonane'),
                'palety_count': agro_ctx.get('palety_count'),
                'estimated_bags': agro_ctx.get('estimated_bags'),
                'packaging_items': agro_ctx.get('packaging_items'),
                'history': agro_ctx.get('history', []),
                'available_packaging': agro_ctx.get('available_packaging', []),
                'all_linked_packaging': agro_ctx.get('all_linked_packaging', []),
                'total_actual_consumed': agro_ctx.get('total_actual_consumed', 0.0),
                'straty_workow': agro_ctx.get('straty_workow', 0.0),
            }
            context['maszyna_opakowania'] = agro_ctx.get('maszyna_opakowania', [])
            context['available_packaging'] = agro_ctx.get('available_packaging', [])
            context['all_linked_packaging'] = agro_ctx.get('all_linked_packaging', [])
            context['total_actual_consumed'] = agro_ctx.get('total_actual_consumed', 0.0)
            context['straty_workow'] = agro_ctx.get('straty_workow', 0.0)
            context['wrctx_error'] = agro_ctx.get('wrctx_error')
            
            # agro_focus_mode should only be True if the active_plan is actually in progress ('w toku').
            # Since the packaging context can return a finished plan of the day as a fallback (for report/settlement view),
            # we query the plan status directly from the database.
            active_plan_obj = agro_ctx.get('active_plan')
            if active_plan_obj:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    table_plan = get_table_name('plan_produkcji', 'AGRO')
                    cursor.execute(f"SELECT status FROM {table_plan} WHERE id = %s", (int(active_plan_obj['id']),))
                    status_row = cursor.fetchone()
                    conn.close()
                    if status_row and str(status_row[0]).strip().lower() == 'w toku':
                        agro_focus_mode = True
                except Exception:
                    pass

        context['agro_focus_mode'] = agro_focus_mode
        context['workowanie_rozliczenie_ctx'] = workowanie_rozliczenie_ctx

        # --- BEZPIECZNIK ---
        # Wymuszenie focus mode jeśli w słowniku plan jest cokolwiek 'w toku'
        if clean_sekcja == 'workowanie' and clean_linia == 'AGRO':
            for p in context.get('plan', []):
                if len(p) > 3 and str(p[3]).lower() == 'w toku':
                    context['agro_focus_mode'] = True
                    break

        if aktywna_sekcja == 'Dashboard':
            return render_template('dashboard_global.html', **context)
        else:
            return render_template('dashboard.html', **context)
    except Exception as e:
        import traceback
        with open('error_500.txt', 'w') as f:
            f.write(str(e) + '\n')
            f.write(traceback.format_exc())
        raise e

@main_bp.route('/set_hall_view')
@login_required
def set_hall_view():
    hall = request.args.get('hall', 'PSD')
    sekcja = request.args.get('sekcja', 'Dashboard')
    data = request.args.get('data')
    session['selected_hall_view'] = hall
    return redirect(url_for('main.index', sekcja=sekcja, data=data, linia=hall))

@main_bp.route('/machine-telemetry')
@login_required
def machine_telemetry_proxy():
    """Mostek serwerowy dla danych MQTT."""
    try:
        from app.services.mqtt_service import get_latest_data
        from app.db import get_db_connection
        
        data = get_latest_data().copy()
        
        # Fetch start_machine_counter for the active AGRO Workowanie order
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT start_machine_counter FROM plan_produkcji_agro WHERE sekcja='Workowanie' AND status='w toku' LIMIT 1")
        row = cursor.fetchone()
        data['start_counter'] = row[0] if row else 0
        conn.close()
        
        return {'success': True, 'data': data}
    except Exception as e:
        return {'success': False, 'error': str(e)}, 500
from app.decorators import roles_required, login_required, masteradmin_required

# ... (other code)

@main_bp.route('/performance')
@dynamic_role_required('performance')
def performance():
    """Page to display client-side performance metrics."""
    return render_template('performance.html')

@main_bp.route('/api/perf_log', methods=['POST'])
@dynamic_role_required('performance')
def perf_log():
    """Optional endpoint if we want to store performance logs on the server."""
    data = request.json
    # For now we just log it to app logger
    app.logger.info(f"PERF_LOG: {data}")
    return {"success": True}
