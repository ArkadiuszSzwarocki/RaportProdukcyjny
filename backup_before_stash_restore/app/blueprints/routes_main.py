"""Main application routes: dashboard index and shared entrypoint registration."""

from typing import Tuple, Dict, Any, Optional, Union
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import date, datetime, timedelta
from app.decorators import login_required, roles_required, dynamic_role_required
from app.blueprints.routes_main_layout import register_main_layout_routes
from app.blueprints.routes_main_misc import register_main_misc_routes
from app.blueprints.routes_main_reporting import register_main_reporting_routes
from app.blueprints.routes_main_index_data import (
    build_agro_mix_context,
    build_allowed_work_start_ids,
    build_dashboard_halls_context,
    build_dosypki_maps,
    build_zasyp_etapy_context,
)
from app.services.dashboard_service import DashboardService
from app.db import get_db_connection

main_bp = Blueprint('main', __name__)
register_main_misc_routes(main_bp)
register_main_layout_routes(main_bp)
register_main_reporting_routes(main_bp)


@main_bp.route('/')
@login_required
def index() -> str:
    """Main dashboard: displays production plans, palety inventory, absence/leave management.

    Supports sections: Dashboard, Zasyp, Workowanie, Magazyn, and others.
    Dynamically loads data based on selected sekcja and date parameters.

    Returns:
        str: Rendered HTML template with dashboard data
    """
    from flask import current_app
    app = current_app
    
    # Parse parameters
    aktywna_sekcja = request.args.get('sekcja', 'Dashboard')
    
    role = (session.get('rola') or '').lower()
    user_grupa = session.get('grupa')
    sess_hall = session.get('selected_hall_view')
    
    # Priority for deciding which hall(s) to view:
    # 1. Explicit 'linia' URL parameter
    # 2. Pinned hall from session 'selected_hall_view' (via /set_hall_view)
    # 3. User's assigned group from database session['grupa'] (e.g. 'PSD', 'AGRO', or 'ALL')
    # 4. Fallback default 'PSD'
    aktywna_linia = request.args.get('linia') or sess_hall or user_grupa or 'PSD'

    # Laborant should not access AGRO warehouse views.
    if role in ['laborant', 'laboratorium'] and aktywna_sekcja == 'Magazyn' and str(aktywna_linia).upper() == 'AGRO':
        flash('Brak dostępu do magazynu AGRO dla roli laboratorium.', 'warning')
        return redirect(url_for('main.index', sekcja='Zasyp', linia='AGRO'))

    # Hall Isolation: if user has a group and is not an admin/manager/lider/planista, restrict them to their hall
    # Users with group 'ALL' (like rotating leaders, admins, managers) are NOT isolated.
    if user_grupa and user_grupa.upper() != 'ALL' and role not in ['admin', 'zarzad', 'planista', 'lider', 'magazynier', 'laborant']:
        if aktywna_linia != user_grupa:
            return redirect(url_for('main.index', sekcja=aktywna_sekcja, linia=user_grupa))

    # --- Dynamic section access check ---
    # Map sekcja param to the key used in role_permissions.json
    _sekcja_to_page = {
        'Dashboard': 'dashboard',
        'Zasyp': 'zasyp',
        'Workowanie': 'workowanie',
        'Magazyn': 'magazyn',
    }
    _page_key = _sekcja_to_page.get(aktywna_sekcja)
    if _page_key:
        from app.core.contexts import inject_role_permissions
        _checker = inject_role_permissions().get('role_has_access')
        if _checker and not _checker(_page_key):
            # If default Dashboard is denied, try to redirect to first accessible section
            if aktywna_sekcja == 'Dashboard':
                for fallback_sekcja, fallback_key in [('Zasyp','zasyp'),('Workowanie','workowanie'),('Magazyn','magazyn')]:
                    if _checker(fallback_key):
                        return redirect(url_for('main.index', sekcja=fallback_sekcja, linia=aktywna_linia))
            # No accessible section found — show denied page (raw HTML, no template)
            return (
                '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Brak dostępu</title>'
                '<style>body{font-family:Arial,sans-serif;display:flex;justify-content:center;'
                'align-items:center;height:100vh;margin:0;background:#f5f5f5;}'
                '.box{text-align:center;padding:40px;background:#fff;border-radius:12px;'
                'box-shadow:0 2px 12px rgba(0,0,0,.1);}'
                'a{display:inline-block;margin-top:20px;padding:10px 24px;background:#3498db;'
                'color:#fff;border-radius:6px;text-decoration:none;}</style></head>'
                '<body><div class="box"><h2>&#128683; Brak dostępu</h2>'
                '<p>Nie masz uprawnień do tej sekcji.<br>Skontaktuj się z administratorem.</p>'
                '<a href="/logout">Wyloguj się</a></div></body></html>'
            ), 403
    
    # Log open_stop param if present
    try:
        if request.args.get('open_stop') is not None:
            app.logger.info('index() called with open_stop=%s from %s', 
                          request.args.get('open_stop'), request.remote_addr)
    except Exception:
        pass
    
    # Parse date parameter
    try:
        dzisiaj = datetime.strptime(request.args.get('data'), '%Y-%m-%d').date() \
                  if request.args.get('data') else date.today()
    except Exception:
        dzisiaj = date.today()

    dashboard_context = build_dashboard_halls_context(dzisiaj, aktywna_sekcja, aktywna_linia, role)
    halls_to_fetch = dashboard_context['halls_to_fetch']
    halls_data = dashboard_context['halls_data']
    wszyscy = dashboard_context['wszyscy']
    dostepni = dashboard_context['dostepni']
    hr_data = dashboard_context['hr_data']

    # Global flag: is any plan in progress today (affects Start button availability across sections)
    global_active = DashboardService.any_plan_in_progress(dzisiaj, linia=aktywna_linia)
    # Products that have an active 'w toku' plan (used to selectively disable START for matching products)
    active_products = DashboardService.get_active_products(dzisiaj, linia=aktywna_linia)
    # Check if ANY plan on Zasyp is 'w toku' — if so, block ALL START buttons for Zasyp
    zasyp_has_active = DashboardService.get_zasyp_active_status(dzisiaj, linia=aktywna_linia)
    # Buffer queue: mapping product -> ordered list of Zasyp plan ids (first = next to be processed)
    buffer_queue = DashboardService.get_buffer_queue(dzisiaj, linia=aktywna_linia)
    # Map product -> first Workowanie plan id (ordered by status/kolejnosc)
    work_first_map = DashboardService.get_first_workowanie_map(dzisiaj, linia=aktywna_linia)
    # Number products by Zasyp execution order and determine allowed Workowanie starts
    zasyp_product_order = DashboardService.get_zasyp_product_order(dzisiaj, linia=aktywna_linia)
    
    allowed_work_start_ids = build_allowed_work_start_ids(dzisiaj, aktywna_linia, work_first_map, app.logger)
    dosypki_mapa, dosypki_oczekujace_mapa = build_dosypki_maps(dzisiaj, aktywna_sekcja, aktywna_linia, app.logger)

    # Build template context
    main_h_data = halls_data[halls_to_fetch[0]]

    zasyp_etapy_context = build_zasyp_etapy_context(
        main_h_data['plan_dnia'],
        dzisiaj,
        aktywna_sekcja,
        aktywna_linia,
        app.logger,
    )
    etapy_mapa = zasyp_etapy_context['etapy_mapa']
    etapy_parametry = zasyp_etapy_context['etapy_parametry']
    etapy_total = zasyp_etapy_context['etapy_total']
    etapy_curr_szarza = zasyp_etapy_context['etapy_curr_szarza']
    etapy_sesje_mapa = zasyp_etapy_context['etapy_sesje_mapa']
    kgph_stats_mapa = zasyp_etapy_context['kgph_stats_mapa']

    agro_mix_mapa, agro_mix_dostepne = build_agro_mix_context(dzisiaj, aktywna_linia, app.logger)

    context = {
        'halls_data': halls_data,
        'halls_to_fetch': halls_to_fetch,
        'sekcja': aktywna_sekcja,
        'linia': aktywna_linia,
        'pracownicy': dostepni,
        'wszyscy_pracownicy': wszyscy,
        'hr_pracownicy': hr_data['hr_pracownicy'],
        'hr_dostepni': hr_data['hr_dostepni'],
        'obsada': main_h_data['obsada'],
        'wpisy': main_h_data['wpisy'],
        'plan': main_h_data['plan_dnia'],
        'palety_mapa': main_h_data['palety_mapa'],
        'magazyn_palety': main_h_data['magazyn_palety'],
        'unconfirmed_palety': main_h_data['unconfirmed_palety'],
        'suma_plan': main_h_data['suma_plan'],
        'suma_wykonanie': main_h_data['suma_wykonanie'],
        'rola': session.get('rola'),
        'dzisiaj': dzisiaj,
        'dzisiaj_fmt': dzisiaj.strftime('%d.%m.%Y'),
        'raporty_hr': hr_data['raporty_hr'],
        'zasyp_rozpoczete': main_h_data['zasyp_rozpoczete'],
        'next_workowanie_id': main_h_data['next_workowanie_id'],
        'now_time': datetime.now().strftime('%H:%M'),
        'quality_count': main_h_data['quality_data']['quality_count'],
        'wnioski_pending': main_h_data['quality_data']['wnioski_pending'],
        'planned_leaves': hr_data['planned_leaves'],
        'recent_absences': hr_data['recent_absences'],
        'shift_notes': main_h_data['shift_notes'],
        'plans_zasyp': main_h_data['plans_zasyp'],
        'plans_workowanie': main_h_data['plans_workowanie'],
        'buffer_map': main_h_data['buffer_queue'],
        'global_active': main_h_data['global_active'],
        'active_products': main_h_data['active_products'],
        'zasyp_has_active': main_h_data['zasyp_has_active'],
        'work_first_map': main_h_data['work_first_map'],
        'zasyp_product_order': main_h_data['zasyp_product_order'],
        'allowed_work_start_ids': allowed_work_start_ids,
        'dosypki_mapa': dosypki_mapa,
        'dosypki_oczekujace_mapa': dosypki_oczekujace_mapa,
        'etapy_mapa': etapy_mapa,
        'etapy_parametry': etapy_parametry,
        'etapy_total': etapy_total,
        'etapy_curr_szarza': etapy_curr_szarza,
        'etapy_sesje_mapa': etapy_sesje_mapa,
        'kgph_stats_mapa': kgph_stats_mapa,
        'agro_mix_mapa': agro_mix_mapa,
        'agro_mix_dostepne': agro_mix_dostepne,
    }
    
    # Render appropriate template
    # Log what we're passing to template
    app.logger.info('===BEGIN DEBUG DASHBOARD===')
    app.logger.info('sekcja=%s, len(plan)=%d', aktywna_sekcja, len(main_h_data['plan_dnia']))
    if main_h_data['plan_dnia']:
        app.logger.info('First plan item: id=%s, name=%s, status=%s', main_h_data['plan_dnia'][0][0], main_h_data['plan_dnia'][0][1], main_h_data['plan_dnia'][0][3])
    else:
        app.logger.info('plan_dnia is EMPTY!')
    app.logger.info('palety_mapa keys=%s', list(main_h_data['palety_mapa'].keys()) if main_h_data['palety_mapa'] else 'EMPTY')
    app.logger.info('===END DEBUG DASHBOARD===')
    
    if aktywna_sekcja == 'Dashboard':
        app.logger.info('index(): rendering dashboard_global.html for sekcja=%s', aktywna_sekcja)
        return render_template('dashboard_global.html', **context)
    else:
        app.logger.info('index(): rendering dashboard.html for sekcja=%s', aktywna_sekcja)
        return render_template('dashboard.html', **context)


