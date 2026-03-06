"""Main application routes: dashboard index, shift closing, reports."""

from typing import Tuple, Dict, Any, Optional, Union
from flask import Blueprint, render_template, request, redirect, url_for, session, send_file, jsonify, Response
from datetime import date, datetime, timedelta
import json
import os
from app.decorators import login_required, roles_required, dynamic_role_required
from app.services.dashboard_service import DashboardService
from app.services.report_generation_service import ReportGenerationService
from app.db import get_db_connection

main_bp = Blueprint('main', __name__)


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
                        return redirect(f'/?sekcja={fallback_sekcja}')
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
    # --- End dynamic section access check ---
    
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
    
    # Get basic staff data
    staff_data = DashboardService.get_basic_staff_data(dzisiaj)
    wszyscy = staff_data['wszyscy']
    zajeci_ids = staff_data['zajeci_ids']
    dostepni = staff_data['dostepni']
    obsada = staff_data['obsada']
    
    # Get journal entries for section
    wpisy = DashboardService.get_journal_entries(dzisiaj, aktywna_sekcja)
    
    # Get section-specific data
    plan_dnia = []
    palety_mapa = {}
    magazyn_palety = []
    unconfirmed_palety = []
    suma_plan = 0
    suma_wykonanie = 0
    
    # Warehouse section
    if aktywna_sekcja == 'Magazyn':
        magazyn_palety, unconfirmed_palety, suma_wykonanie = \
            DashboardService.get_warehouse_data(dzisiaj)
    
    # Production plans (don't overwrite Magazyn aggregates when viewing Magazyn)
    if aktywna_sekcja != 'Magazyn':
        plan_dnia, palety_mapa, suma_plan, suma_wykonanie = \
            DashboardService.get_production_plans(dzisiaj, aktywna_sekcja)
    else:
        # Ensure plan_dnia and palety_mapa are still populated for the template
        plan_dnia, palety_mapa, suma_plan = [], {}, 0
    
    # Get zasyp started products
    zasyp_rozpoczete = DashboardService.get_zasyp_started_products(dzisiaj)
    
    # Get HR and leave data
    hr_data = DashboardService.get_hr_and_leave_data(dzisiaj, wszyscy, zajeci_ids)
    
    # Get quality and leave requests
    quality_data = DashboardService.get_quality_and_leave_requests(role)
    
    # Get shift notes
    shift_notes = DashboardService.get_shift_notes(dzisiaj)
    
    # Get full plans for Dashboard
    plans_zasyp, plans_workowanie = DashboardService.get_full_plans_for_sections(dzisiaj)
    
    # Get next Workowanie ID
    next_workowanie_id = DashboardService.get_next_workowanie_id(plan_dnia)

    # Global flag: is any plan in progress today (affects Start button availability across sections)
    global_active = DashboardService.any_plan_in_progress(dzisiaj)
    # Products that have an active 'w toku' plan (used to selectively disable START for matching products)
    active_products = DashboardService.get_active_products(dzisiaj)
    # Check if ANY plan on Zasyp is 'w toku' — if so, block ALL START buttons for Zasyp
    zasyp_has_active = DashboardService.get_zasyp_active_status(dzisiaj)
    # Buffer queue: mapping product -> ordered list of Zasyp plan ids (first = next to be processed)
    buffer_queue = DashboardService.get_buffer_queue(dzisiaj)
    # Map product -> first Workowanie plan id (ordered by status/kolejnosc)
    work_first_map = DashboardService.get_first_workowanie_map(dzisiaj)
    # Number products by Zasyp execution order and determine allowed Workowanie starts
    zasyp_product_order = DashboardService.get_zasyp_product_order(dzisiaj)
    
    # Nowa logika: START aktywny tylko dla Workowania z MINIMUM kolejka w buforze
    allowed_work_start_ids = set()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Krok 1: Znajdź GLOBALNE minimum kolejka w buforze
        cursor.execute("""
            SELECT MIN(kolejka) as global_min_queue
            FROM bufor 
            WHERE DATE(data_planu) = %s AND status = 'aktywny'
        """, (dzisiaj,))
        
        result = cursor.fetchone()
        global_min_queue = result[0] if result and result[0] is not None else None
        
        app.logger.info(f"[DEBUG-START] GLOBAL MIN kolejka w buforze: {global_min_queue}")
        
        if global_min_queue is not None:
            # Krok 2: Pobierz wszystkie produkty z tym minimum
            cursor.execute("""
                SELECT DISTINCT produkt
                FROM bufor 
                WHERE DATE(data_planu) = %s AND status = 'aktywny' AND kolejka = %s
            """, (dzisiaj, global_min_queue))
            
            products_with_min_queue = [row[0] for row in cursor.fetchall()]
            app.logger.info(f"[DEBUG-START] Produkty z kolejka={global_min_queue}: {products_with_min_queue}")
            
            # Krok 3: Dla tych produktów, aktywuj START jeśli mają Workowanie
            for prod in products_with_min_queue:
                if prod in work_first_map:
                    allowed_work_start_ids.add(work_first_map[prod])
                    app.logger.info(f"[DEBUG-START] Aktywny START dla {prod} (id={work_first_map[prod]}, kolejka={global_min_queue})")
        
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
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.plan_id, d.nazwa, d.kg, d.data_zlecenia, d.data_potwierdzenia, d.szarza_id
                FROM dosypki d
                JOIN plan_produkcji p ON d.plan_id = p.id
                WHERE d.potwierdzone = 1 AND DATE(p.data_planu) = %s AND p.sekcja = 'Zasyp'
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
            cursor.execute("""
                SELECT d.plan_id, COUNT(*)
                FROM dosypki d
                JOIN plan_produkcji p ON d.plan_id = p.id
                WHERE d.potwierdzone = 0 AND DATE(p.data_planu) = %s AND p.sekcja = 'Zasyp'
                GROUP BY d.plan_id
            """, (dzisiaj,))
            for plan_id, pending_count in cursor.fetchall():
                dosypki_oczekujace_mapa[plan_id] = pending_count
            cursor.close()
            conn.close()
        except Exception as e:
            app.logger.error(f"[ERROR-DOSYPKI] Błąd pobierania potwierdzonych dosypek: {e}")
            
    # Build template context
    context = {
        'sekcja': aktywna_sekcja,
        'pracownicy': dostepni,
        'wszyscy_pracownicy': wszyscy,
        'hr_pracownicy': hr_data['hr_pracownicy'],
        'hr_dostepni': hr_data['hr_dostepni'],
        'obsada': obsada,
        'wpisy': wpisy,
        'plan': plan_dnia,
        'palety_mapa': palety_mapa,
        'magazyn_palety': magazyn_palety,
        'unconfirmed_palety': unconfirmed_palety,
        'suma_plan': suma_plan,
        'suma_wykonanie': suma_wykonanie,
        'rola': session.get('rola'),
        'dzisiaj': dzisiaj,
        'raporty_hr': hr_data['raporty_hr'],
        'zasyp_rozpoczete': zasyp_rozpoczete,
        'next_workowanie_id': next_workowanie_id,
        'now_time': datetime.now().strftime('%H:%M'),
        'quality_count': quality_data['quality_count'],
        'wnioski_pending': quality_data['wnioski_pending'],
        'planned_leaves': hr_data['planned_leaves'],
        'recent_absences': hr_data['recent_absences'],
        'shift_notes': shift_notes,
        'plans_zasyp': plans_zasyp,
        'plans_workowanie': plans_workowanie,
        'buffer_map': buffer_queue,
        'global_active': global_active,
        'active_products': active_products,
        'zasyp_has_active': zasyp_has_active,
        'work_first_map': work_first_map,
        'zasyp_product_order': zasyp_product_order,
        'allowed_work_start_ids': allowed_work_start_ids,
        'dosypki_mapa': dosypki_mapa,
        'dosypki_oczekujace_mapa': dosypki_oczekujace_mapa,
    }
    
    # Render appropriate template
    try:
        # Log what we're passing to template
        app.logger.info('===BEGIN DEBUG DASHBOARD===')
        app.logger.info('sekcja=%s, len(plan)=%d', aktywna_sekcja, len(plan_dnia))
        if plan_dnia:
            app.logger.info('First plan item: id=%s, name=%s, status=%s', plan_dnia[0][0], plan_dnia[0][1], plan_dnia[0][3])
        else:
            app.logger.info('plan_dnia is EMPTY!')
        app.logger.info('palety_mapa keys=%s', list(palety_mapa.keys()) if palety_mapa else 'EMPTY')
        app.logger.info('===END DEBUG DASHBOARD===')
        
        if aktywna_sekcja == 'Dashboard':
            app.logger.info('index(): rendering dashboard_global.html for sekcja=%s', aktywna_sekcja)
            return render_template('dashboard_global.html', **context)
        else:
            app.logger.info('index(): rendering dashboard.html for sekcja=%s', aktywna_sekcja)
            return render_template('dashboard.html', **context)
    except Exception as e:
        # Log exception and fallback to global dashboard on error
        try:
            app.logger.exception('index(): render failed for sekcja=%s, falling back to dashboard_global: %s', aktywna_sekcja, e)
        except Exception:
            pass
        return render_template('dashboard_global.html', **context)


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
        plan_dnia, palety_mapa, suma_plan, suma_wykonanie = \
            DashboardService.get_production_plans(dzisiaj, sekcja)
        
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
    zip_path, mime_type = ReportGenerationService.close_shift_and_generate_reports(uwagi_lidera)
    
    # Return ZIP file if successfully generated
    if zip_path:
        return send_file(zip_path, as_attachment=True, mimetype=mime_type)
    
    # Fallback: redirect to login if nothing to download
    return redirect('/login')


@main_bp.route('/wyslij_raport_email', methods=['POST'])
def wyslij_raport_email() -> Response:
    """Email a generated report (placeholder for future functionality)."""
    return redirect('/')
