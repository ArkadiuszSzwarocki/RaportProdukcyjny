import re
from flask import render_template, request, jsonify, session, redirect, url_for, current_app, flash
from app.services.agro.agro_surowce_service import AgroSurowceService
from app.services.agro.agro_tanks_service import AgroTanksService
from app.services.dashboard_service import DashboardService
from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
from app.services.magazyn_dostawy.delivery_command_service import DeliveryCommandService
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.magazyn_dostawy.location_service import LocationService
from app.services.production_inventory_service import ProductionInventoryService
from app.decorators import login_required, roles_required, dynamic_role_required
from datetime import datetime, date
from app.db import get_db_connection, get_table_name
from .blueprint import agro_warehouse_bp

@agro_warehouse_bp.route('/agro/api/magazyn/surowce-w-produkcji/historia/<tank_code>')
@login_required
def api_surowce_w_produkcji_historia(tank_code):
    linia = request.args.get('linia', 'AGRO')
    limit = min(int(request.args.get('limit', 50)), 100)
    history_rows = AgroTanksService.get_production_tank_history(tank_code, limit=limit, linia=linia)
    for row in history_rows:
        if row.get('autor_data'):
            data_val = row['autor_data']
            if hasattr(data_val, 'strftime'):
                # Jest to obiekt datetime
                row['autor_data_str'] = data_val.strftime('%d.%m.%Y %H:%M')
            else:
                # Już jest stringiem
                row['autor_data_str'] = str(data_val)
        else:
            row['autor_data_str'] = ''
    return jsonify({'success': True, 'historia': history_rows})

@agro_warehouse_bp.route('/agro/api/confirm', methods=['POST'])
@login_required
def confirm_move():
    try:
        data = request.get_json()
        ruch_id = data.get('ruch_id')
        lokalizacja = data.get('lokalizacja')
        linia = data.get('linia', 'Agro')
        nr_partii = data.get('nr_partii')
        data_produkcji = data.get('data_produkcji')
        data_przydatnosci = data.get('data_przydatnosci')
        if not ruch_id:
            return (jsonify({'success': False, 'error': 'Brak ID ruchu'}), 400)
        worker_login = session.get('login')
        success = AgroSurowceService.confirm_delivery(ruch_id, worker_login, linia=linia, lokalizacja=lokalizacja, nr_partii=nr_partii, data_produkcji=data_produkcji, data_przydatnosci=data_przydatnosci)
        if not success:
            success = AgroSurowceService.confirm_external_issue(ruch_id, worker_login, linia=linia)
        if success:
            return jsonify({'success': True})
        return (jsonify({'success': False, 'error': 'Nie można potwierdzić tego ruchu (być może został już przetworzony)'}), 400)
    except Exception as e:
        current_app.logger.error(f'Error in confirm_move: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/usage', methods=['POST'])
@login_required
def use_material():
    try:
        data = request.get_json()
        surowiec_id = data.get('surowiec_id')
        ilosc = float(data.get('ilosc', 0))
        plan_id = data.get('plan_id')
        komentarz = data.get('komentarz')
        zbiornik = data.get('zbiornik')
        linia = data.get('linia', 'Agro')
        zbiornik_raw = str(zbiornik or '').strip().upper()
        zbiornik_norm = AgroTanksService.normalize_production_tank(zbiornik_raw)
        if not surowiec_id or ilosc <= 0:
            return (jsonify({'success': False, 'error': 'Nieprawidłowe dane'}), 400)
        if zbiornik_raw and (not zbiornik_norm):
            return (jsonify({'success': False, 'error': 'Nieprawidłowy zbiornik. Dozwolone: BB01-BB24, MZ01-MZ06, MZ05-01, MZ06-01, KO01-KO22.'}), 400)
        worker_login = session.get('login')
        AgroSurowceService.use_for_production(surowiec_id, ilosc, worker_login, plan_id=plan_id, linia=linia, komentarz=komentarz, zbiornik=zbiornik_norm)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f'Error in use_material: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/history', methods=['GET'])
@login_required
def api_history():
    linia = request.args.get('linia', 'Agro')
    data = request.args.get('data') or None
    plan_id = request.args.get('plan_id') or None
    limit = min(int(request.args.get('limit', 200)), 500)
    try:
        rows = AgroSurowceService.get_history(limit=limit, linia=linia, data=data, plan_id=plan_id)
        result = []
        for h in rows:
            # Helper to safely format datetime or string
            def safe_format_date(val, fmt):
                if not val:
                    return ''
                if hasattr(val, 'strftime'):
                    return val.strftime(fmt)
                return str(val)
            
            result.append({
                'id': h['id'],
                'surowiec_nazwa': h.get('surowiec_nazwa') or '',
                'lokalizacja': h.get('lokalizacja') or '',
                'typ_ruchu': h.get('typ_ruchu') or '',
                'ilosc': float(h['ilosc']) if h.get('ilosc') is not None else 0,
                'ilosc_po': float(h['ilosc_po']) if h.get('ilosc_po') is not None else None,
                'status': h.get('status') or '',
                'autor_login': h.get('autor_login') or '',
                'autor_data': safe_format_date(h.get('autor_data'), '%d.%m.%Y %H:%M'),
                'autor_date_only': safe_format_date(h.get('autor_data'), '%d.%m.%Y'),
                'autor_time_only': safe_format_date(h.get('autor_data'), '%H:%M'),
                'potwierdzil_login': h.get('potwierdzil_login') or '',
                'potwierdzil_data': safe_format_date(h.get('potwierdzil_data'), '%H:%M'),
                'plan_id': h.get('plan_id'),
                'plan_name': h.get('plan_name') or '',
                'zbiornik': h.get('zbiornik') or '',
                'komentarz': h.get('komentarz') or ''
            })
        return jsonify({'success': True, 'history': result, 'count': len(result)})
    except Exception as e:
        current_app.logger.error(f'Error in api_history: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/rename', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def rename_pallet():
    try:
        data = request.get_json()
        surowiec_id = data.get('surowiec_id')
        new_name = data.get('new_name')
        linia = data.get('linia', 'Agro')
        if not surowiec_id or not new_name:
            return (jsonify({'success': False, 'error': 'Brak id lub nowej nazwy'}), 400)
        worker_login = session.get('login')
        success = AgroTanksService.rename_pallet(surowiec_id, new_name, worker_login, linia=linia)
        if success:
            return jsonify({'success': True})
        return (jsonify({'success': False, 'error': 'Nie udało się zmienić nazwy'}), 400)
    except Exception as e:
        current_app.logger.error(f'Error in rename_pallet: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/current_plan', methods=['GET'])
@login_required
def api_current_plan():
    try:
        linia = request.args.get('linia', 'Agro')
        current_plan = AgroTanksService.get_current_running_plan(linia=linia)
        if current_plan:
            return jsonify({'success': True, 'plan_id': current_plan.get('id'), 'plan_name': current_plan.get('produkt')})
        return jsonify({'success': True, 'plan_id': None, 'plan_name': None})
    except Exception as e:
        current_app.logger.error(f'Error in api_current_plan: {e}', exc_info=True)
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/production_moves', methods=['GET'])
@login_required
def production_moves():
    try:
        linia = request.args.get('linia', 'Agro')
        limit = min(int(request.args.get('limit', 100)), 1000)
        rows = AgroTanksService.get_production_moves(limit=limit, linia=linia)
        result = []
        for h in rows:
            result.append({'id': h.get('id'), 'surowiec_nazwa': h.get('surowiec_nazwa') or '', 'surowiec_id': h.get('surowiec_id'), 'ilosc': float(h['ilosc']) if h.get('ilosc') is not None else 0, 'autor_login': h.get('autor_login') or '', 'autor_data': h['autor_data'].strftime('%d.%m.%Y %H:%M') if h.get('autor_data') else '', 'plan_id': h.get('plan_id'), 'plan_name': h.get('plan_name') or '', 'zbiornik': h.get('zbiornik') or '', 'lokalizacja': h.get('lokalizacja') or ''})
        return jsonify({'success': True, 'moves': result, 'count': len(result)})
    except Exception as e:
        current_app.logger.error(f'Error in production_moves: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/issue', methods=['POST'])
@login_required
def issue_external():
    try:
        data = request.get_json()
        surowiec_id = data.get('surowiec_id')
        ilosc = float(data.get('ilosc', 0))
        komentarz = data.get('komentarz')
        linia = data.get('linia', 'Agro')
        if not surowiec_id or ilosc <= 0:
            return (jsonify({'success': False, 'error': 'Nieprawidłowe dane'}), 400)
        worker_login = session.get('login')
        AgroSurowceService.issue_external(surowiec_id, ilosc, worker_login, linia=linia, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f'Error in issue_external: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/return', methods=['POST'])
@login_required
def return_from_production():
    try:
        data = request.get_json()
        surowiec_id = data.get('surowiec_id')
        ilosc = float(data.get('ilosc', 0))
        plan_id = data.get('plan_id')
        komentarz = data.get('komentarz')
        linia = data.get('linia', 'Agro')
        ruch_produkcja_id = data.get('ruch_produkcja_id')
        lokalizacja = data.get('lokalizacja')
        if not surowiec_id or ilosc <= 0:
            return (jsonify({'success': False, 'error': 'Nieprawidłowe dane'}), 400)
        worker_login = session.get('login')
        AgroTanksService.return_from_production(surowiec_id, ilosc, worker_login, plan_id=plan_id, linia=linia, komentarz=komentarz, ruch_produkcja_id=ruch_produkcja_id, lokalizacja=lokalizacja)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f'Error in return_from_production: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/production_items_for_return', methods=['GET'])
@login_required
def production_items_for_return():
    try:
        linia = request.args.get('linia', 'Agro')
        limit = min(int(request.args.get('limit', 200)), 1000)
        items = AgroTanksService.get_production_items_for_return(linia=linia, limit=limit)
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        current_app.logger.error(f'Error in production_items_for_return: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/suggest-location', methods=['POST'])
@login_required
def suggest_location():
    try:
        data = request.get_json()
        nazwa = data.get('nazwa')
        linia = data.get('linia', 'Agro')
        if not nazwa:
            return (jsonify({'success': False, 'error': 'Brak nazwy surowca'}), 400)
        suggestion = AgroSurowceService.get_suggested_location(nazwa, linia=linia)
        return jsonify({'success': True, 'suggestion': suggestion})
    except Exception as e:
        current_app.logger.error(f'Error in suggest_location: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/issue_warehouse', methods=['POST'])
@login_required
def api_issue_warehouse():
    try:
        data = request.get_json()
        surowiec_id = data.get('surowiec_id')
        ilosc = data.get('ilosc')
        komentarz = data.get('komentarz')
        linia = data.get('linia', 'Agro')
        if not surowiec_id or not ilosc:
            return (jsonify({'success': False, 'error': 'Brak ID lub ilości'}), 400)
        try:
            qty = float(ilosc)
        except Exception:
            return (jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400)
        worker = session.get('login')
        AgroSurowceService.issue_warehouse(surowiec_id, qty, worker, linia=linia, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f'Error in api_issue_warehouse: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)
