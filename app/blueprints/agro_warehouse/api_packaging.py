import re
from flask import render_template, request, jsonify, session, redirect, url_for, current_app, flash
from app.services.agro.agro_opakowania_service import AgroOpakowaniaService
from app.services.agro.agro_opakowaniaplan_service import AgroOpakowaniaPlanService
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

@agro_warehouse_bp.route('/agro/api/opakowania', methods=['POST'])
@roles_required('magazynier', 'admin')
def create_opakowanie():
    try:
        data = request.get_json()
        nazwa = data.get('nazwa')
        ilosc = data.get('ilosc')
        lokalizacja = data.get('lokalizacja')
        linia = data.get('linia', 'Agro')
        if not nazwa:
            return (jsonify({'success': False, 'error': 'Brak nazwy'}), 400)
        try:
            il = float(ilosc or 0)
        except Exception:
            return (jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400)
        new_id = AgroOpakowaniaService.create_packaging(nazwa, il, lokalizacja, linia=linia)
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
        current_app.logger.error(f'Error in create_opakowanie: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/opakowania', methods=['PUT'])
@roles_required('admin')
def edit_opakowanie():
    try:
        data = request.get_json()
        record_id = data.get('id')
        if not record_id:
            return (jsonify({'success': False, 'error': 'Brak id'}), 400)
        nazwa = data.get('nazwa')
        ilosc = data.get('ilosc')
        lokalizacja = data.get('lokalizacja')
        il_val = None
        if ilosc is not None and ilosc != '':
            try:
                il_val = float(ilosc)
            except Exception:
                return (jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400)
        AgroOpakowaniaService.edit_packaging(record_id, nazwa=nazwa, ilosc=il_val, lokalizacja=lokalizacja)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f'Error in edit_opakowanie: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/opakowania', methods=['DELETE'])
@roles_required('admin')
def delete_opakowanie():
    try:
        data = request.get_json()
        record_id = data.get('id')
        if not record_id:
            return (jsonify({'success': False, 'error': 'Brak id'}), 400)
        success = AgroOpakowaniaService.delete_packaging(record_id)
        if success:
            return jsonify({'success': True})
        return (jsonify({'success': False, 'error': 'Nie udało się usunąć rekordu'}), 400)
    except Exception as e:
        current_app.logger.error(f'Error in delete_opakowanie: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/opakowania/inventory', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def inventory_opakowanie():
    try:
        data = request.get_json()
        record_id = data.get('id')
        actual_qty = data.get('actual_qty')
        linia = data.get('linia', 'Agro')
        if not record_id:
            return (jsonify({'success': False, 'error': 'Brak id'}), 400)
        try:
            qty = float(actual_qty)
        except Exception:
            return (jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400)
        worker = session.get('login')
        AgroOpakowaniaService.adjust_packaging_inventory(record_id, qty, worker_login=worker, linia=linia)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f'Error in inventory_opakowanie: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/opakowania/link', methods=['POST'])
@login_required
def link_packaging():
    try:
        data = request.get_json()
        success, error = AgroOpakowaniaPlanService.link_packaging_to_plan(data.get('opakowanie_id'), data.get('plan_id'), ilosc_pobrana=data.get('ilosc_pobrana'), user_login=session.get('login'))
        return jsonify({'success': success, 'error': error})
    except Exception as e:
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/opakowania/return', methods=['POST'])
@login_required
def return_packaging():
    try:
        data = request.get_json() or {}
        raw_print_label = data.get('print_label')
        if isinstance(raw_print_label, str):
            print_label = raw_print_label.strip().lower() in {'1', 'true', 'tak', 'yes', 'on'}
        else:
            print_label = bool(raw_print_label)
        raw_is_partial = data.get('is_partial', False)
        if isinstance(raw_is_partial, str):
            is_partial = raw_is_partial.strip().lower() in {'1', 'true', 'tak', 'yes', 'on'}
        else:
            is_partial = bool(raw_is_partial)
        result = AgroOpakowaniaPlanService.return_packaging_from_machine(data.get('opakowanie_id'), data.get('stan_po'), data.get('lokalizacja'), session.get('login'), is_partial=is_partial, print_label=print_label)
        extra = {}
        if isinstance(result, tuple):
            if len(result) >= 3:
                success, error, extra = (result[0], result[1], result[2] or {})
            else:
                success, error = (result[0], result[1])
        else:
            success, error = (False, 'Nieprawidłowy wynik operacji zwrotu')
        response = {'success': success, 'error': error}
        if isinstance(extra, dict):
            response.update(extra)
            if success:
                last_label = extra.get('return_label')
                if isinstance(last_label, dict) and last_label:
                    session['agro_last_return_label'] = last_label
        return jsonify(response)
    except Exception as e:
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/opakowania/reprint_last_return_label', methods=['POST'])
@login_required
def reprint_last_return_label():
    try:
        label_data = session.get('agro_last_return_label')
        if not isinstance(label_data, dict) or not label_data:
            return (jsonify({'success': False, 'error': 'Brak danych ostatniego zwrotu do ponownego wydruku'}), 404)
        ok, message = AgroOpakowaniaPlanService.print_packaging_return_label(label_data)
        return jsonify({'success': bool(ok), 'error': None if ok else message, 'message': message, 'print_result': {'requested': True, 'success': bool(ok), 'message': message}})
    except Exception as e:
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/opakowania/undo_link', methods=['POST'])
@login_required
def undo_link_packaging():
    try:
        data = request.get_json()
        link_id = data.get('link_id')
        if not link_id:
            return (jsonify({'success': False, 'error': 'Brak link_id'}), 400)
        success, error = AgroOpakowaniaPlanService.undo_packaging_link(link_id)
        return jsonify({'success': success, 'error': error})
    except Exception as e:
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/opakowania/undo_return', methods=['POST'])
@login_required
def undo_return_packaging():
    try:
        data = request.get_json()
        link_id = data.get('link_id')
        if not link_id:
            return (jsonify({'success': False, 'error': 'Brak link_id'}), 400)
        success, error = AgroOpakowaniaPlanService.undo_packaging_return(link_id, session.get('login'))
        return jsonify({'success': success, 'error': error})
    except Exception as e:
        return (jsonify({'success': False, 'error': str(e)}), 500)
