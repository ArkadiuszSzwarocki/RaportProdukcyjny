import os
import sys
import re
from datetime import date, datetime
from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, current_app as app

from app.db import get_db_connection, get_table_name
from app.decorators import roles_required, login_required, dynamic_role_required, masteradmin_required
from app.services.dashboard_service import DashboardService
from .index_data import (
    build_dashboard_halls_context,
    build_dosypki_maps,
    build_zasyp_etapy_context,
    build_agro_mix_context
)
from app.services.workowanie_queue_service import WorkowanieQueueService
from app.services.zasyp_queue_service import ZasypQueueService
from app.services.mqtt_service import get_latest_data
from .layout import register_main_layout_routes
from .misc import register_main_misc_routes
from .reporting import register_main_reporting_routes

main_bp = Blueprint('main', __name__)

register_main_misc_routes(main_bp)
register_main_layout_routes(main_bp)
register_main_reporting_routes(main_bp)

@main_bp.route('/')
@login_required
def index():
    try:
        # Default redirect to scanner if no section/args are provided
        if not request.args:
            return redirect('/agro/scanner/ui')

        # Detect hall view from session or query param
        sess_hall = session.get('selected_hall_view')
        user_grupa = session.get('grupa', 'PSD').upper()
        aktywna_linia = request.args.get('linia') or sess_hall or user_grupa or 'PSD'
        
        # Force hall view if user has limited access
        role = str(session.get('rola') or '').lower().strip()
        role_aliases = {'master admin': 'masteradmin', 'master_admin': 'masteradmin', 'master-admin': 'masteradmin', 'laboratorium': 'laborant'}
        role = role_aliases.get(role, role)
        
        is_exempt = role in ['admin', 'masteradmin', 'zarzad', 'laborant', 'laboratorium', 'planista', 'magazynier']
        if not is_exempt and user_grupa != 'ALL' and user_grupa != 'ADMIN' and user_grupa != 'ZARZAD' and user_grupa != 'MASTERADMIN':
            if aktywna_linia != user_grupa:
                aktywna_linia = user_grupa
                
        aktywna_sekcja = request.args.get('sekcja', 'Dashboard')
        dzisiaj_str = request.args.get('data', str(date.today()))
        
        app.logger.info(f"[DEBUG INDEX] role={role}, user_grupa={user_grupa}, aktywna_linia={aktywna_linia}, aktywna_sekcja={aktywna_sekcja}, args={request.args}")
        
        try:
            dzisiaj = date.fromisoformat(dzisiaj_str)
        except:
            dzisiaj = date.today()
            
        data_od_str = request.args.get('data_od')
        data_do_str = request.args.get('data_do')
        
        # If user is on AGRO Workowanie or Zasyp, default to week range if no data_od/data_do is provided but they didn't explicitly pick a specific single day
        if aktywna_linia == 'AGRO' and aktywna_sekcja in ('Workowanie', 'Zasyp'):
            if not data_od_str and not data_do_str:
                # If they just navigated without params, default to current week
                from datetime import timedelta
                start_of_week = dzisiaj - timedelta(days=dzisiaj.weekday())
                end_of_week = start_of_week + timedelta(days=6)
                data_od_str = str(start_of_week)
                data_do_str = str(end_of_week)
            elif data_od_str and not data_do_str:
                data_do_str = data_od_str
            elif data_do_str and not data_od_str:
                data_od_str = data_do_str

        # Enforce dashboard access restriction: only MasterAdmin, Admin, Lider, Planista can view the dashboard
        if aktywna_sekcja.strip().lower() == 'dashboard':
            allowed_dashboard_roles = ['masteradmin', 'admin', 'lider', 'planista']
            if role not in allowed_dashboard_roles:
                # User cannot access Dashboard! Try to auto-route them to their first allowed production section
                from app.core.contexts import inject_role_permissions
                role_checker = inject_role_permissions().get('role_has_access')
                
                line_lower = aktywna_linia.lower().strip()
                sections_to_check = ['Zasyp', 'Workowanie', 'Bufor', 'Magazyn']
                found_allowed_sec = None
                for sec in sections_to_check:
                    page_key = f"{line_lower}.{sec.lower()}"
                    if role_checker and role_checker(page_key):
                        found_allowed_sec = sec
                        break
                
                if found_allowed_sec:
                    return redirect(url_for('main.index', sekcja=found_allowed_sec, linia=aktywna_linia, data=dzisiaj_str))
                else:
                    return render_template(
                        'errors/403.html',
                        page_url=request.path,
                        user_role=role,
                        allowed_roles=allowed_dashboard_roles
                    ), 403

        # Load everything via the central helper to ensure data parity with original system
        role = session.get('rola')
        halls_ctx = build_dashboard_halls_context(
            dzisiaj, 
            aktywna_sekcja, 
            aktywna_linia, 
            role,
            data_od=data_od_str,
            data_do=data_do_str
        )
        
        halls_data = halls_ctx['halls_data']
        halls_to_fetch = halls_ctx['halls_to_fetch']
        hr_data = halls_ctx['hr_data']
        
        # We take the first hall data as primary (for single-hall views)
        main_h_data = halls_data.get(aktywna_linia, list(halls_data.values())[0] if halls_data else {})

        # Resolve allowed START ids for Workowanie and Zasyp
        allowed_work_start_ids = WorkowanieQueueService.get_allowed_start_ids(
            dzisiaj, aktywna_linia, main_h_data.get('work_first_map', {}), app.logger
        )
        allowed_zasyp_start_ids = ZasypQueueService.get_allowed_start_ids(
            dzisiaj, aktywna_linia, app.logger
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

        # FEFO Pallets
        from app.services.dashboard_service import DashboardService
        fefo_pallets = []
        if aktywna_sekcja in ['dashboard', 'zasyp']:
            fefo_pallets = DashboardService.get_expiring_pallets(dzisiaj, aktywna_linia, days_threshold=30)

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
            'pending_wg': main_h_data.get('pending_wg', []),
            'suma_plan': main_h_data.get('suma_plan'),
            'suma_wykonanie': main_h_data.get('suma_wykonanie'),
            'rola': role,
            'dzisiaj': dzisiaj,
            'dzisiaj_fmt': dzisiaj.strftime('%d.%m.%Y'),
            'data_od': data_od_str,
            'data_do': data_do_str,
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
            'allowed_zasyp_start_ids': allowed_zasyp_start_ids,
            'agro_mix_mapa': agro_mix_mapa,
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
            'fefo_pallets': fefo_pallets,
        }

        # --- focus mode + rozliczenie context ---
        agro_focus_mode = False
        workowanie_rozliczenie_ctx = None
        
        clean_sekcja = aktywna_sekcja.strip().lower()
        
        # Check if there is any active order ('w toku') in the current daily plan
        has_active_order = False
        plan_dnia = main_h_data.get('plan_dnia', [])
        if plan_dnia:
            for p in plan_dnia:
                status = str(p[3]).strip().lower()
                if len(p) > 3 and status == 'w toku':
                    has_active_order = True
                    break

        if clean_sekcja in ['zasyp', 'workowanie'] and has_active_order:
            agro_focus_mode = True
            
        if clean_sekcja == 'workowanie' and aktywna_linia == 'AGRO':
            try:
                from app.services.dashboard_service import DashboardService
                workowanie_rozliczenie_ctx = DashboardService.get_agro_packaging_context(dzisiaj)
            except Exception as e:
                import traceback
                app.logger.error(f"Error fetching agro packaging context: {str(e)}\n{traceback.format_exc()}")
        context['agro_focus_mode'] = agro_focus_mode
        context['workowanie_rozliczenie_ctx'] = workowanie_rozliczenie_ctx

        if clean_sekcja == 'dashboard':
            return render_template('dashboard_global.html', **context)
        return render_template('dashboard.html', **context)

    except Exception as e:
        import traceback
        error_msg = f"Error loading dashboard: {str(e)}\n{traceback.format_exc()}"
        app.logger.error(error_msg)
        return f"<pre>{error_msg}</pre>", 500

@main_bp.route('/machine-telemetry')
@login_required
def machine_telemetry():
    from app.services.mqtt_service import get_latest_data
    return jsonify({
        'success': True,
        'data': get_latest_data()
    })

