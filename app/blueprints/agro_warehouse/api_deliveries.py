import re
from flask import render_template, request, jsonify, session, redirect, url_for, current_app, flash
from app.services.agro.agro_surowce_service import AgroSurowceService
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

@agro_warehouse_bp.route('/agro/api/delivery', methods=['POST'])
@roles_required('magazynier', 'admin')
def add_delivery():
    try:
        data = request.get_json()
        nazwa = data.get('nazwa')
        ilosc = data.get('ilosc')
        komentarz = data.get('komentarz')
        items = data.get('items')
        linia = data.get('linia', 'Agro')
        author_login = session.get('login')
        if items and isinstance(items, list):
            for it in items:
                n = it.get('nazwa')
                try:
                    q = float(it.get('ilosc', 0))
                except Exception:
                    return (jsonify({'success': False, 'error': 'Nieprawidłowa wartość ilości w jednym z elementów (popraw format liczby)'}), 400)
                note = it.get('komentarz')
                p = it.get('nr_partii')
                dz = it.get('data_przydatnosci')
                pf = it.get('pkg_form', 'bags')
                if not n or q <= 0:
                    return (jsonify({'success': False, 'error': 'Nieprawidłowe dane w elementach listy'}), 400)
                AgroSurowceService.add_delivery(n, q, author_login, linia=linia, komentarz=note, nr_partii=p, data_produkcji=dp, data_przydatnosci=dz, pkg_form=pf)
        else:
            try:
                q = float(ilosc or 0)
            except Exception:
                return (jsonify({'success': False, 'error': 'Nieprawidłowa wartość ilości (popraw format liczby)'}), 400)
            if not nazwa or q <= 0:
                return (jsonify({'success': False, 'error': 'Nieprawidłowe dane (nazwa i ilość są wymagane)'}), 400)
            p = data.get('nr_partii')
            dp = data.get('data_produkcji')
            dz = data.get('data_przydatnosci')
            pf = data.get('pkg_form', 'bags')
            AgroSurowceService.add_delivery(nazwa, q, author_login, linia=linia, komentarz=komentarz, nr_partii=p, data_produkcji=dp, data_przydatnosci=dz, pkg_form=pf)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f'Error in add_delivery: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/delivery', methods=['PUT'])
@roles_required('admin')
def edit_delivery():
    try:
        data = request.get_json()
        ruch_id = data.get('ruch_id')
        nazwa = data.get('nazwa')
        ilosc = data.get('ilosc')
        komentarz = data.get('komentarz')
        if not ruch_id:
            return (jsonify({'success': False, 'error': 'Brak ID ruchu'}), 400)
        ilosc_val = None
        if ilosc is not None and ilosc != '':
            try:
                ilosc_val = float(ilosc)
            except Exception:
                return (jsonify({'success': False, 'error': 'Nieprawidłowa wartość ilości (popraw format liczby)'}), 400)
        AgroSurowceService.edit_delivery(ruch_id, nazwa=nazwa, ilosc=ilosc_val, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f'Error in edit_delivery: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/delivery', methods=['DELETE'])
@roles_required('admin')
def delete_delivery():
    try:
        data = request.get_json()
        ruch_id = data.get('ruch_id')
        if not ruch_id:
            return (jsonify({'success': False, 'error': 'Brak ID ruchu'}), 400)
        success = AgroSurowceService.delete_delivery(ruch_id)
        if success:
            return jsonify({'success': True})
        return (jsonify({'success': False, 'error': 'Nie można usunąć tego ruchu'}), 400)
    except Exception as e:
        current_app.logger.error(f'Error in delete_delivery: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)
