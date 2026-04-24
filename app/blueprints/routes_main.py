"""Main application routes: dashboard index, shift closing, reports."""

from typing import Tuple, Dict, Any, Optional, Union
from flask import Blueprint, render_template, request, redirect, url_for, session, send_file, jsonify, Response, flash
from datetime import date, datetime, timedelta
import json
import os
from app.decorators import login_required, roles_required, dynamic_role_required
from app.services.dashboard_service import DashboardService
from app.services.report_generation_service import ReportGenerationService
from app.db import get_db_connection

main_bp = Blueprint('main', __name__)


@main_bp.route('/set_hall_view/<hall>')
def set_hall_view(hall):
    """Pin the current view to a specific hall for users with multi-hall access."""
    if hall in ['PSD', 'AGRO']:
        session['selected_hall_view'] = hall
        flash(f'Widok przełączony na: { "Hala 1 (PSD)" if hall=="PSD" else "Hala 2 (Agro)" }', 'info')
    elif hall == 'ALL':
        session.pop('selected_hall_view', None)
        flash('Widok przełączony na: Wszystkie hale', 'info')
    
    # Próbuj wrócić na tę samą sekcję jeśli to możliwe
    sekcja = request.args.get('sekcja')
    data = request.args.get('data')
    
    return redirect(url_for('main.index', linia=hall, sekcja=sekcja, data=data))


@main_bp.route('/favicon.ico')
@main_bp.route('/apple-touch-icon.png')
@main_bp.route('/apple-touch-icon-precomposed.png')
def favicon():
    """Silence favicon/apple-touch-icon 404 noise in logs."""
    return ('', 204)


@main_bp.route('/debug/modal-move', methods=['POST'])
def debug_modal_move() -> Tuple[str, int]:
    """Log modal-move debug data from client (AJAX).
    
    This endpoint accepts JSON payloads from the UI for debugging modal drag/drop behavior.
    
    Returns:
        Tuple[str, int]: Empty response with 204 No Content status
    """
    from flask import current_app
    app = current_app
    try:
        data = request.get_json(force=True)
        # Log as info; JSON-encode to keep single-line entries
        try:
            app.logger.info('Modal-move debug: %s', json.dumps(data, ensure_ascii=False))
        except Exception:
            app.logger.info('Modal-move debug: %s', str(data))
    except Exception as e:
        try:
            app.logger.exception('Failed to record modal-move debug: %s', e)
        except Exception:
            pass
    return ('', 204)


@main_bp.route('/debug/whoami')
def debug_whoami():
    """Temporary debug endpoint: returns session role and session keys.
    Only responds when request comes from localhost (127.0.0.1 or ::1).
    """
    from flask import current_app, jsonify
    ip = request.remote_addr
    if ip not in ('127.0.0.1', '::1', 'localhost'):
        return 'Forbidden', 403
    role = session.get('rola')
    data = {
        'remote_addr': ip,
        'session_role': role,
        'session_keys': list(session.keys())
    }
    return jsonify(data)


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

    # Determine which halls to fetch data for
    halls_to_fetch = ['PSD', 'AGRO'] if aktywna_linia == 'ALL' else [aktywna_linia]
    halls_data = {}

    # Global data (shared across halls)
    staff_data_global = DashboardService.get_basic_staff_data(dzisiaj, linia='PSD')
    wszyscy = staff_data_global['wszyscy']
    zajeci_ids = staff_data_global['zajeci_ids']
    dostepni = staff_data_global['dostepni']
    hr_data = DashboardService.get_hr_and_leave_data(dzisiaj, wszyscy, zajeci_ids)

    for h in halls_to_fetch:
        h_staff = DashboardService.get_basic_staff_data(dzisiaj, linia=h)
        h_wpisy = DashboardService.get_journal_entries(dzisiaj, aktywna_sekcja, linia=h)
        h_zasyp_rozpoczete = DashboardService.get_zasyp_started_products(dzisiaj, linia=h)
        h_quality = DashboardService.get_quality_and_leave_requests(role, linia=h)
        h_notes = DashboardService.get_shift_notes(dzisiaj, linia=h)
        h_plans_zasyp, h_plans_work = DashboardService.get_full_plans_for_sections(dzisiaj, linia=h)
        h_active = DashboardService.any_plan_in_progress(dzisiaj, linia=h)
        h_buffer_q = DashboardService.get_buffer_queue(dzisiaj, linia=h)
        h_work_first = DashboardService.get_first_workowanie_map(dzisiaj, linia=h)
        h_product_order = DashboardService.get_zasyp_product_order(dzisiaj, linia=h)
        h_zasyp_has_active = DashboardService.get_zasyp_active_status(dzisiaj, linia=h)
        h_active_products = DashboardService.get_active_products(dzisiaj, linia=h)
        
        # Section specific data
        h_plan_dnia = []
        h_palety_mapa = {}
        h_mag_palety = []
        h_unconf_palety = []
        h_suma_plan = 0
        h_suma_wyk = 0
        
        if aktywna_sekcja == 'Magazyn':
            h_mag_palety, h_unconf_palety, h_suma_wyk = DashboardService.get_warehouse_data(dzisiaj, linia=h)
        
        if aktywna_sekcja != 'Magazyn':
            h_plan_dnia, h_palety_mapa, h_suma_plan, h_suma_wyk = DashboardService.get_production_plans(dzisiaj, aktywna_sekcja, linia=h)
        
        halls_data[h] = {
            'linia': h,
            'obsada': h_staff['obsada'],
            'wpisy': h_wpisy,
            'zasyp_rozpoczete': h_zasyp_rozpoczete,
            'quality_data': h_quality,
            'shift_notes': h_notes,
            'plans_zasyp': h_plans_zasyp,
            'plans_workowanie': h_plans_work,
            'plan_dnia': h_plan_dnia,
            'palety_mapa': h_palety_mapa,
            'suma_plan': h_suma_plan,
            'suma_wykonanie': h_suma_wyk,
            'magazyn_palety': h_mag_palety,
            'unconfirmed_palety': h_unconf_palety,
            'global_active': h_active,
            'buffer_queue': h_buffer_q,
            'work_first_map': h_work_first,
            'next_workowanie_id': DashboardService.get_next_workowanie_id(h_plan_dnia),
            'zasyp_product_order': h_product_order,
            'zasyp_has_active': h_zasyp_has_active,
            'active_products': h_active_products
        }

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
    
    # Nowa logika: START aktywny tylko dla Workowania z MINIMUM kolejka w buforze
    allowed_work_start_ids = set()
    try:
        from app.db import get_table_name
        table_bufor = get_table_name('bufor', aktywna_linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        # Krok 1: Znajdź GLOBALNE minimum kolejka w buforze DLA PRODUKTÓW, KTÓRE SĄ W PLANIE (nie zakończone)
        table_plan = get_table_name('plan_produkcji', aktywna_linia)
        cursor.execute(f"""
            SELECT MIN(b.kolejka) as global_min_queue
            FROM {table_bufor} b
            WHERE DATE(b.data_planu) = %s AND b.status = 'aktywny'
              AND EXISTS (
                  SELECT 1 FROM {table_plan} w
                  WHERE w.sekcja = 'Workowanie' AND w.status IN ('zaplanowane', 'w toku')
                    AND w.produkt = b.produkt
              )
        """, (dzisiaj,))
        
        result = cursor.fetchone()
        global_min_queue = result[0] if result and result[0] is not None else None
        
        app.logger.info(f"[DEBUG-START] GLOBAL MIN kolejka w {table_bufor}: {global_min_queue}")
        
        if global_min_queue is not None:
            # Krok 2: Pobierz wszystkie produkty z tym minimum
            cursor.execute(f"""
                SELECT DISTINCT produkt
                FROM {table_bufor} 
                WHERE DATE(data_planu) = %s AND status = 'aktywny' AND kolejka = %s
            """, (dzisiaj, global_min_queue))
            
            products_with_min_queue = [row[0] for row in cursor.fetchall()]
            app.logger.info(f"[DEBUG-START] Produkty z kolejka={global_min_queue}: {products_with_min_queue}")
            
            # Krok 3: Dla tych produktów, aktywuj START jeśli mają Workowanie
            # Szukamy w pełnym planie (bez ograniczenia daty) — obsługuje carry-over z poprzednich dni
            for prod in products_with_min_queue:
                # Najpierw sprawdź w work_first_map (dzisiejsze plany)
                matched_key = next((k for k in work_first_map if k.strip().casefold() == prod.strip().casefold()), None)
                if matched_key:
                    allowed_work_start_ids.add(work_first_map[matched_key])
                    app.logger.info(f"[DEBUG-START] Aktywny START dla {prod} (id={work_first_map[matched_key]}, kolejka={global_min_queue})")
                else:
                    # Fallback: szukaj w bazie danych (carry-over z poprzednich dni)
                    try:
                        cursor.execute(f"""
                            SELECT id FROM {table_plan}
                            WHERE sekcja = 'Workowanie'
                              AND status IN ('zaplanowane', 'w toku')
                              AND LOWER(TRIM(produkt)) = LOWER(TRIM(%s))
                              AND is_deleted = 0
                            ORDER BY CASE status WHEN 'w toku' THEN 1 ELSE 2 END, data_planu DESC, kolejnosc ASC, id ASC
                            LIMIT 1
                        """, (prod,))
                        row = cursor.fetchone()
                        if row:
                            allowed_work_start_ids.add(row[0])
                            app.logger.info(f"[DEBUG-START] Aktywny START (fallback carry-over) dla {prod} (id={row[0]}, kolejka={global_min_queue})")
                        else:
                            app.logger.warning(f"[DEBUG-START] Brak Workowania dla produktu: '{prod}' (work_first_map keys: {list(work_first_map.keys())})")
                    except Exception as fe:
                        app.logger.error(f"[DEBUG-START] Błąd fallback dla '{prod}': {fe}")

        cursor.close()
        conn.close()
        
        app.logger.info(f"[DEBUG-START] Final allowed_work_start_ids: {allowed_work_start_ids}")
    except Exception as e:
        import traceback
        app.logger.error(f"[ERROR-START] Błąd: {e}")
        app.logger.error(traceback.format_exc())
        allowed_work_start_ids = set()
    
    # Krok: Pobranie zrealizowanych (potwierdzonych) dosypek dla sekcji Zasyp
    dosypki_mapa = {}
    dosypki_oczekujace_mapa = {}
    if aktywna_sekcja == 'Zasyp':
        try:
            from app.db import get_table_name
            table_dosypki = get_table_name('dosypki', aktywna_linia)
            table_plan = get_table_name('plan_produkcji', aktywna_linia)
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT d.plan_id, d.nazwa, d.kg, d.data_zlecenia, d.data_potwierdzenia, d.szarza_id
                FROM {table_dosypki} d
                JOIN {table_plan} p ON d.plan_id = p.id
                WHERE d.potwierdzone = 1 AND COALESCE(d.anulowana, 0) = 0 AND DATE(p.data_planu) = %s AND p.sekcja = 'Zasyp'
                ORDER BY d.data_potwierdzenia ASC
            """, (dzisiaj,))
            for row in cursor.fetchall():
                pid = row[0]
                if pid not in dosypki_mapa:
                    dosypki_mapa[pid] = []
                dosypki_mapa[pid].append({
                    'nazwa': row[1],
                    'kg': row[2],
                    'zlecono': str(row[3])[:16] if row[3] else '',
                    'potwierdzono': str(row[4])[:16] if row[4] else '',
                    'szarza_id': row[5]
                })
            cursor.execute(f"""
                SELECT d.plan_id, COUNT(*)
                FROM {table_dosypki} d
                JOIN {table_plan} p ON d.plan_id = p.id
                WHERE d.potwierdzone = 0 AND COALESCE(d.anulowana, 0) = 0 AND DATE(p.data_planu) = %s AND p.sekcja = 'Zasyp'
                GROUP BY d.plan_id
            """, (dzisiaj,))
            for plan_id, pending_count in cursor.fetchall():
                dosypki_oczekujace_mapa[plan_id] = pending_count
            cursor.close()
            conn.close()
        except Exception as e:
            app.logger.error(f"[ERROR-DOSYPKI] Błąd pobierania potwierdzonych dosypek: {e}")

    # Build template context
    main_h_data = halls_data[halls_to_fetch[0]]

    # Etapy Zasyp — wczytaj dla aktywnych zleceń Zasyp
    etapy_mapa = {}      # plan_id -> latest session list of etap dicts (compat)
    etapy_parametry = {} # plan_id -> {wielkosc_szarzy_kg}
    etapy_total = {}     # plan_id -> latest session formatted total time string (compat)
    etapy_total_s = {}   # plan_id -> latest session total duration in seconds
    etapy_curr_szarza = {} # plan_id -> latest session curr_szarza_nr (compat)
    etapy_sesje_mapa = {} # plan_id -> list of session payloads
    kgph_stats_mapa = {}  # plan_id -> {'real_work': float|None, 'timeline': float|None}
    if aktywna_sekcja == 'Zasyp':
        try:
            from app.services.zasyp_etapy_service import ZasypEtapyService
            for p in main_h_data['plan_dnia']:
                if p[3] == 'w toku':
                    pid = p[0]
                    sessions = ZasypEtapyService.get_etapy_sessions(plan_id=pid, linia=aktywna_linia)
                    latest = sessions[0] if sessions else ZasypEtapyService.get_etapy(plan_id=pid, linia=aktywna_linia)
                    etapy_sesje_mapa[pid] = sessions
                    etapy_mapa[pid] = latest.get('etapy') or []
                    etapy_total[pid] = latest.get('total_duration_str') or ''
                    etapy_total_s[pid] = int(latest.get('total_duration_s') or 0)
                    etapy_curr_szarza[pid] = latest.get('curr_szarza_nr') or 1
                    etapy_parametry[pid] = ZasypEtapyService.get_parametry(plan_id=pid, linia=aktywna_linia)
        except Exception as _e:
            app.logger.warning('Etapy Zasyp load failed: %s', _e)

        # Metrics: kg/h from plan START/STOP (real) and from summed etap production time.
        try:
            table_plan = get_table_name('plan_produkcji', aktywna_linia)
            plan_ids = [int(p[0]) for p in main_h_data['plan_dnia'] if p and len(p) > 0]
            plan_realized_kg = {}
            plan_status = {}
            for p in main_h_data['plan_dnia']:
                try:
                    plan_realized_kg[int(p[0])] = float(p[7] or 0.0)
                    plan_status[int(p[0])] = str(p[3] or '').strip().lower()
                except Exception:
                    continue
            if plan_ids:
                conn_stats = get_db_connection()
                cursor_stats = conn_stats.cursor(dictionary=True)
                fmt_ids = ','.join(['%s'] * len(plan_ids))

                cursor_stats.execute(
                    f"SELECT id, COALESCE(tonaz_rzeczywisty, 0) AS tonaz_rzeczywisty, real_start, real_stop FROM {table_plan} WHERE id IN ({fmt_ids})",
                    plan_ids,
                )
                plan_meta = {int(r['id']): r for r in (cursor_stats.fetchall() or [])}

                # Aggregate directly from DB so manual operator edits in zasyp_etapy are reflected immediately.
                cursor_stats.execute(
                    f"""
                    SELECT
                        plan_id,
                        MIN(czas_start) AS first_start,
                        MAX(COALESCE(czas_stop, NOW())) AS last_end,
                            MAX(CASE WHEN czas_stop IS NULL THEN 1 ELSE 0 END) AS has_running
                    FROM zasyp_etapy
                    WHERE linia = %s AND plan_id IN ({fmt_ids}) AND czas_start IS NOT NULL
                    GROUP BY plan_id
                    """,
                    [aktywna_linia] + plan_ids,
                )
                etapy_agg_map = {int(r['plan_id']): r for r in (cursor_stats.fetchall() or [])}

                now_dt = datetime.now()
                for pid in plan_ids:
                    meta = plan_meta.get(pid) or {}
                    tonaz_plan = float(meta.get('tonaz_rzeczywisty') or 0.0)
                    tonaz_realized = float(plan_realized_kg.get(pid) or 0.0)
                    parametry = etapy_parametry.get(pid) or {}
                    status = plan_status.get(pid, '')
                    agg = etapy_agg_map.get(pid) or {}

                    # Real efficiency should always use actually produced mass when available.
                    # Fallback to plan tonaz only if execution is still zero/missing.
                    tonaz = tonaz_realized if tonaz_realized > 0 else tonaz_plan
                    batch_tonaz = float(parametry.get('wielkosc_szarzy_kg') or 0.0)
                    real_start = meta.get('real_start')
                    real_stop = meta.get('real_stop')
                    real_seconds = 0

                    real_work_kgph = None
                    if tonaz > 0:
                        metric_start = real_start or agg.get('first_start')
                        if status == 'w toku':
                            metric_end = now_dt
                        else:
                            metric_end = agg.get('last_end') or real_stop or now_dt

                        if metric_start:
                            try:
                                real_seconds = max(0, int((metric_end - metric_start).total_seconds()))
                                real_hours = real_seconds / 3600.0
                                if real_hours > 0:
                                    real_work_kgph = tonaz / real_hours
                            except Exception:
                                real_work_kgph = None
                                real_seconds = 0

                    timeline_kgph = None
                    sessions_for_plan = etapy_sesje_mapa.get(pid) or []
                    def _session_etapy_breakdown(session_payload):
                        etapy_out = []
                        for e in (session_payload.get('etapy') or []):
                            try:
                                dur_s = int(e.get('duration_s') or 0)
                            except Exception:
                                dur_s = 0
                            if dur_s <= 0:
                                continue
                            try:
                                etap_nr = int(e.get('etap'))
                            except Exception:
                                etap_nr = e.get('etap')
                            etapy_out.append({
                                'etap': etap_nr,
                                'duration_s': dur_s,
                                'duration_str': e.get('duration_str') or '',
                            })
                        return etapy_out

                    closed_sessions = [
                        s for s in sessions_for_plan
                        if int(s.get('total_duration_s') or 0) > 0 and not bool(s.get('has_running'))
                    ]

                    if closed_sessions:
                        timeline_seconds = sum(int(s.get('total_duration_s') or 0) for s in closed_sessions)
                        timeline_mass = (batch_tonaz * len(closed_sessions)) if batch_tonaz > 0 else tonaz
                        timeline_sources = []
                        for s in closed_sessions:
                            timeline_sources.append({
                                'szarza_nr': int(s.get('szarza_nr') or s.get('curr_szarza_nr') or 0),
                                'total_duration_s': int(s.get('total_duration_s') or 0),
                                'total_duration_str': s.get('total_duration_str') or '',
                                'etapy': _session_etapy_breakdown(s),
                            })
                    else:
                        timeline_seconds = int(etapy_total_s.get(pid) or 0)
                        timeline_mass = batch_tonaz if batch_tonaz > 0 else tonaz
                        current_session = sessions_for_plan[0] if sessions_for_plan else None
                        if current_session:
                            timeline_sources = [{
                                'szarza_nr': int(current_session.get('szarza_nr') or current_session.get('curr_szarza_nr') or 0),
                                'total_duration_s': int(current_session.get('total_duration_s') or 0),
                                'total_duration_str': current_session.get('total_duration_str') or '',
                                'etapy': _session_etapy_breakdown(current_session),
                            }]
                        else:
                            timeline_sources = []

                    if timeline_mass > 0:
                        if timeline_seconds > 0:
                            try:
                                timeline_hours = timeline_seconds / 3600.0
                                if timeline_hours > 0:
                                    timeline_kgph = timeline_mass / timeline_hours
                            except Exception:
                                timeline_kgph = None

                    kgph_stats_mapa[pid] = {
                        'real_work': real_work_kgph,
                        'timeline': timeline_kgph,
                        'real_mass_kg': tonaz,
                        'real_seconds': real_seconds,
                        'timeline_mass_kg': timeline_mass,
                        'timeline_batch_mass_kg': batch_tonaz if batch_tonaz > 0 else None,
                        'timeline_seconds': timeline_seconds,
                        'timeline_closed_sessions': len(closed_sessions),
                        'timeline_mode': 'closed_sessions' if closed_sessions else 'current_session',
                        'timeline_sources': timeline_sources,
                    }

                cursor_stats.close()
                conn_stats.close()
        except Exception as _e:
            app.logger.warning('kgph stats load failed: %s', _e)

    # Fetch AGRO MIX data (only if on AGRO or ALL)
    agro_mix_mapa = {}
    agro_mix_dostepne = []
    if aktywna_linia in ['AGRO', 'ALL']:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            # 1. Map for consumption display (linked to specific plan)
            cursor.execute("""
                SELECT id, nastepne_zlecenie_id, zuzyte_w_id, kategoria, waga_kg, created_at, autor_login, status
                FROM agro_mix_rozliczenie 
                WHERE (data_planu = %s OR status='DOSTEPNY')
            """, (dzisiaj,))
            mixes = cursor.fetchall()
            for m in mixes:
                # If specifically linked or consumed in this plan
                nid = m['zuzyte_w_id'] or m['nastepne_zlecenie_id']
                if nid:
                    agro_mix_mapa.setdefault(nid, []).append(m)
                
                # If currently available for use
                if m['status'] == 'DOSTEPNY':
                    agro_mix_dostepne.append(m)
            conn.close()
        except Exception as _e:
            app.logger.warning('AGRO MIX load failed: %s', _e)

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


@main_bp.route('/layout-editor')
@login_required
@roles_required('admin', 'lider')
def layout_editor() -> str:
    """Visual layout editor for production sections.
    
    Allows editing of component styling (fonts, padding, visibility) for
    Zasyp, Workowanie, and Magazyn sections.
    
    Returns:
        str: Rendered HTML template for layout editor
    """
    return render_template('layout_editor.html')


@main_bp.route('/sekcja/<name>/edit')
@login_required
@roles_required('admin', 'lider')
def edit_layout(name: str) -> str:
    """Visual layout editor for section (Zasyp, Workowanie, etc).
    
    Allows drag-and-drop reordering of components, font size adjustments,
    column visibility toggles, and other layout customizations.
    
    Args:
        name: Section name (e.g., 'Zasyp', 'Workowanie')
        
    Returns:
        str: Rendered layout editor template
    """
    from flask import current_app
    app = current_app
    
    # Validate section name
    valid_sections = ['Zasyp', 'Workowanie', 'Magazyn']
    if name not in valid_sections:
        return (f'<h2>Nieznana sekcja: {name}</h2><a href="/">Wróć do dashboard</a>', 404)
    
    # Fallback configuration (if file not found)
    default_layouts = {
        'Zasyp': {
            'version': '1.0',
            'layout': {
                'header': {'enabled': True, 'order': 1, 'fontSize': '21px', 'padding': '20px', 'gap': '20px', 'description': 'Tytuł sekcji i info'},
                'stats': {'enabled': True, 'order': 2, 'fontSize': '16px', 'padding': '12px', 'gap': '12px', 'description': 'Plan, Wykonanie, % Realizacja'},
                'table': {'enabled': True, 'order': 3, 'fontSize': '14px', 'padding': '10px', 'columns': [
                    {'name': 'Produkt', 'visible': True, 'width': 'auto'},
                    {'name': 'Waga Planu', 'visible': True, 'width': 'auto'},
                    {'name': 'Wykonanie', 'visible': True, 'width': 'auto'},
                    {'name': 'Status', 'visible': True, 'width': 'auto'},
                    {'name': 'Szarże', 'visible': True, 'width': 'auto'},
                    {'name': 'Akcje', 'visible': True, 'width': 'auto'}
                ], 'description': 'Tabela planów produkcji'},
                'details': {'enabled': True, 'order': 4, 'fontSize': '12px', 'padding': '10px', 'description': 'Szczegóły palety/szarży'}
            }
        },
        'Workowanie': {
            'version': '1.0',
            'layout': {
                'header': {'enabled': True, 'order': 1, 'fontSize': '21px', 'padding': '20px', 'description': 'Tytuł sekcji'},
                'stats': {'enabled': True, 'order': 2, 'fontSize': '16px', 'padding': '12px', 'description': 'Statystyki'},
                'table': {'enabled': True, 'order': 3, 'fontSize': '14px', 'padding': '10px', 'columns': [
                    {'name': 'Produkt', 'visible': True, 'width': 'auto'},
                    {'name': 'Waga', 'visible': True, 'width': 'auto'},
                    {'name': 'Status', 'visible': True, 'width': 'auto'},
                    {'name': 'Palety', 'visible': True, 'width': 'auto'},
                    {'name': 'Akcje', 'visible': True, 'width': 'auto'}
                ], 'description': 'Tabela planów'}
            }
        }
    }
    
    # Load layout configuration
    layouts_config = {}
    try:
        config_path = os.path.join(app.root_path, '../config/layouts.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                layouts_config = json.load(f)
                app.logger.info(f"[EDIT-LAYOUT] Wczytano konfigurację z {config_path}")
        else:
            app.logger.warning(f"[EDIT-LAYOUT] Plik {config_path} nie istnieje, używam domyślnej konfiguracji")
    except Exception as e:
        app.logger.error(f"[EDIT-LAYOUT] Błąd wczytywania config/layouts.json: {e}")
    
    # Use fallback if needed
    if name not in layouts_config:
        app.logger.info(f"[EDIT-LAYOUT] Sekcja {name} nie znaleziona, używam domyślnej konfiguracji")
        if name in default_layouts:
            layouts_config[name] = default_layouts[name]
    
    # Get current layout for section
    layout = layouts_config.get(name, {'version': '1.0', 'layout': {}})
    
    return render_template('layout_editor.html', 
                          sekcja=name, 
                          layout_config=json.dumps(layout),
                          layout_data=layout,
                          debug_mode=True)


@main_bp.route('/api/layout/get/<name>', methods=['GET'])
@login_required
def get_layout(name: str) -> Tuple[Dict, int]:
    """Get layout configuration for a section (AJAX endpoint).
    
    Args:
        name: Section name (Zasyp, Workowanie, Magazyn)
        
    Returns:
        Tuple[Dict, int]: JSON layout configuration and status code
    """
    from flask import current_app
    app = current_app
    
    try:
        config_path = os.path.join(app.root_path, '../config/layouts.json')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                layouts_config = json.load(f)
                
            if name in layouts_config:
                return jsonify(layouts_config[name]), 200
        
        # Return empty if not found (client will use defaults)
        return jsonify({'version': '1.0', 'layout': {}}), 200
        
    except Exception as e:
        app.logger.exception(f"[GET-LAYOUT] Błąd wczytywania: {e}")
        return jsonify({'version': '1.0', 'layout': {}}), 200


@main_bp.route('/api/layout/save/<name>', methods=['POST'])
@login_required
@roles_required('admin', 'lider')
def save_layout(name: str) -> Tuple[Dict, int]:
    """Save layout configuration (AJAX endpoint).
    
    Args:
        name: Section name
        
    Returns:
        Tuple[Dict, int]: JSON response and status code
    """
    from flask import current_app
    app = current_app
    
    try:
        data = request.get_json()
        layout_updates = data.get('layout', {})
        
        # Load or create config
        config_path = os.path.join(app.root_path, '../config/layouts.json')
        
        layouts_config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                layouts_config = json.load(f)
        
        # Update section layout
        if name not in layouts_config:
            layouts_config[name] = {'version': '1.0', 'layout': {}}
        
        layouts_config[name]['layout'].update(layout_updates)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # Save back with indent for readability
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(layouts_config, f, indent=2, ensure_ascii=False)
        
        app.logger.info(f"[SAVE-LAYOUT] Zapisano layout dla {name}")
        return jsonify({'status': 'ok', 'message': f'Layout dla {name} został zapisany'}), 200
    
    except Exception as e:
        app.logger.exception(f"[SAVE-LAYOUT] Błąd zapisu: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@main_bp.route('/api/sekcja/dashboard-data', methods=['GET'])
@login_required
def api_get_section_data() -> Tuple[dict, int]:
    """Load production data for layout editor preview.
    
    Returns:
        JSON with plan_total, execution_total, percent, and items list
    """
    from datetime import date as date_type
    sekcja = request.args.get('sekcja', 'Zasyp')
    dzisiaj = date_type.today()
    
    try:
        linia = request.args.get('linia', 'PSD')
        plan_dnia, palety_mapa, suma_plan, suma_wykonanie = \
            DashboardService.get_production_plans(dzisiaj, sekcja, linia=linia)
        
        percent = int((suma_wykonanie / suma_plan * 100) if suma_plan > 0 else 0)
        
        # Build items list for preview
        items = []
        for p in plan_dnia[:5]:  # First 5 items
            items.append({
                'product': p[1] if len(p) > 1 else 'N/A',
                'plan': f"{p[2] if len(p) > 2 else 0} kg",
                'status': p[3] if len(p) > 3 else 'zaplanowane'
            })
        
        return jsonify({
            'plan_total': f"{suma_plan:.0f} kg",
            'execution_total': f"{suma_wykonanie:.0f} kg",
            'percent_complete': percent,
            'items': items
        }), 200
    
    except Exception as e:
        app.logger.exception(f"[API-SECTION-DATA] Błąd: {e}")
        return jsonify({
            'plan_total': '0 kg',
            'execution_total': '0 kg',
            'percent_complete': 0,
            'items': []
        }), 200


@main_bp.route('/zamknij_zmiane', methods=['GET'])
@roles_required('lider', 'admin')
def zamknij_zmiane_get() -> Response:
    """Redirect GET requests on shift close endpoint to index."""
    return redirect(url_for('main.index'))


@main_bp.route('/zamknij_zmiane', methods=['POST'])
@roles_required('lider', 'admin')
def zamknij_zmiane() -> Union[Response, Tuple[str, int]]:
    """Close current shift (zmiana) and generate final reports.
    
    - Closes all 'w toku' (in progress) production plans
    - Generates Excel and text reports
    - Optionally sends report via Outlook if available
    - Returns ZIP file with generated reports for download
    
    Returns:
        Union[Response, Tuple[str, int]]: Redirect response or ZIP file download
    """
    from flask import current_app
    app = current_app
    
    # Get leader notes/comments from form
    uwagi_lidera = request.form.get('uwagi_lidera', '')
    
    # Use service to perform shift closing and report generation
    aktywna_linia = request.form.get('linia', request.args.get('linia', 'PSD'))
    zip_path, mime_type = ReportGenerationService.close_shift_and_generate_reports(uwagi_lidera, linia=aktywna_linia)
    
    # Return ZIP file if successfully generated
    if zip_path:
        return send_file(zip_path, as_attachment=True, mimetype=mime_type)
    
    # Fallback: generacja raportu nie powiodła się, wróć na stronę główną
    flash('⚠️ Nie udało się wygenerować raportu. Sprawdź logi serwera.', 'warning')
    return redirect(url_for('main.index'))


@main_bp.route('/wyslij_raport_email', methods=['POST'])
def wyslij_raport_email() -> Response:
    """Email a generated report (placeholder for future functionality)."""
    return redirect(url_for('main.index'))


@main_bp.route('/api/zglos_blad_systemu', methods=['POST'])
@login_required
def zglos_blad_systemu() -> Response:
    """Zgłoś błąd z możliwością uploadu do 3 zrzutów ekranu."""
    from flask import current_app, jsonify
    import time
    
    opis = (request.form.get('opis', '') or '').strip()
    gdzie = (request.form.get('gdzie', '') or '').strip()
    sciezka = request.form.get('sciezka', '')
    login = session.get('login', 'Nieznany')

    if not opis:
        return jsonify({'success': False, 'message': 'Opis problemu jest wymagany.'}), 400

    if gdzie:
        opis = f"[Miejsce występowania] {gdzie}\n\n{opis}"
    
    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'bugs')
    os.makedirs(upload_dir, exist_ok=True)
    
    report_id = int(time.time() * 1000)
    saved_files = []
    
    files = request.files.getlist('zalaczniki')
    for i, file in enumerate(files[:3]):
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
            if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                filename = f"bug_{report_id}_{i}.{ext}"
                try:
                    file.save(os.path.join(upload_dir, filename))
                    saved_files.append(filename)
                except Exception as e:
                    current_app.logger.warning("Błąd zapisu pliku: %s", e)
    
    # Save to Database instead of just JSON file
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO zgloszenia_bledow (id, timestamp, login, opis, sciezka, zalaczniki, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            report_id,
            datetime.now(),
            login,
            opis,
            sciezka,
            json.dumps(saved_files),
            'nowy'
        ))
        conn.commit()
    except Exception as e:
        current_app.logger.error("Błąd zapisu zgłoszenia do bazy: %s", e)
        return jsonify({'success': False, 'message': 'Błąd zapisu zgłoszenia'}), 500
    finally:
        conn.close()
        
    return jsonify({'success': True, 'message': 'Zgłoszenie zostało przyjęte.'})
