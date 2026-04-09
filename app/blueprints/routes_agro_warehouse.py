from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, current_app
from app.services.agro_warehouse_service import AgroWarehouseService
from app.decorators import login_required, roles_required, dynamic_role_required
from datetime import datetime
from app.services.agro_warehouse_service import AgroWarehouseService
from app.db import get_db_connection, get_table_name

agro_warehouse_bp = Blueprint('agro_warehouse', __name__)

@agro_warehouse_bp.route('/agro/magazyn')
@login_required
@dynamic_role_required('agro_magazyn')
def index():
    linia = request.args.get('linia', 'Agro')
    # inventory grouped by material (for compact view)
    inventory = AgroWarehouseService.get_inventory_grouped(linia=linia)
    history = AgroWarehouseService.get_history(limit=50, linia=linia)
    pending = AgroWarehouseService.get_history(status='OCZEKUJACE', linia=linia)
    dictionary = AgroWarehouseService.get_dictionary()
    # current running production plan (if any) for this line — used to pre-fill usage modal
    try:
        current_plan = AgroWarehouseService.get_current_running_plan(linia=linia)
        current_plan_id = current_plan['id'] if current_plan else None
        current_plan_name = current_plan['produkt'] if current_plan else None
    except Exception:
        current_plan_id = None
        current_plan_name = None
    
    return render_template(
        'agro_magazyn.html',
        inventory=inventory,
        history=history,
        pending=pending,
        dictionary=dictionary,
        linia=linia,
        current_plan_id=current_plan_id,
        current_plan_name=current_plan_name
    )


@agro_warehouse_bp.route('/agro/magazyn/opakowania')
@login_required
@dynamic_role_required('agro_magazyn')
def opakowania():
    """Simple view for packaging warehouse (magazyn_opakowania) in AGRO."""
    linia = request.args.get('linia', 'Agro')
    try:
        items = AgroWarehouseService.get_packaging_inventory(linia=linia)
    except Exception:
        items = []
    return render_template('agro_magazyn_opakowania.html', items=items, linia=linia)


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
            return jsonify({'success': False, 'error': 'Brak nazwy'}), 400
        try:
            il = float(ilosc or 0)
        except Exception:
            return jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400
        new_id = AgroWarehouseService.create_packaging(nazwa, il, lokalizacja, linia=linia)
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
        current_app.logger.error(f"Error in create_opakowanie: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/api/opakowania', methods=['PUT'])
@roles_required('admin')
def edit_opakowanie():
    try:
        data = request.get_json()
        record_id = data.get('id')
        if not record_id:
            return jsonify({'success': False, 'error': 'Brak id'}), 400
        nazwa = data.get('nazwa')
        ilosc = data.get('ilosc')
        lokalizacja = data.get('lokalizacja')
        il_val = None
        if ilosc is not None and ilosc != '':
            try:
                il_val = float(ilosc)
            except Exception:
                return jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400
        AgroWarehouseService.edit_packaging(record_id, nazwa=nazwa, ilosc=il_val, lokalizacja=lokalizacja)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in edit_opakowanie: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/api/opakowania', methods=['DELETE'])
@roles_required('admin')
def delete_opakowanie():
    try:
        data = request.get_json()
        record_id = data.get('id')
        if not record_id:
            return jsonify({'success': False, 'error': 'Brak id'}), 400
        success = AgroWarehouseService.delete_packaging(record_id)
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Nie udało się usunąć rekordu'}), 400
    except Exception as e:
        current_app.logger.error(f"Error in delete_opakowanie: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
            return jsonify({'success': False, 'error': 'Brak id'}), 400
        try:
            qty = float(actual_qty)
        except Exception:
            return jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400
        worker = session.get('login')
        AgroWarehouseService.adjust_packaging_inventory(record_id, qty, worker_login=worker, linia=linia)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in inventory_opakowanie: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@agro_warehouse_bp.route('/agro/api/delivery', methods=['POST'])
@roles_required('magazynier', 'admin')
def add_delivery():
    try:
        data = request.get_json()
        # support single item or list of items
        nazwa = data.get('nazwa')
        ilosc = data.get('ilosc')
        komentarz = data.get('komentarz')
        items = data.get('items')
        linia = data.get('linia', 'Agro')
        
        author_login = session.get('login')

        if items and isinstance(items, list):
            # validate items
            for it in items:
                n = it.get('nazwa')
                try:
                    q = float(it.get('ilosc', 0))
                except Exception:
                    return jsonify({'success': False, 'error': 'Nieprawidłowa wartość ilości w jednym z elementów (popraw format liczby)'}), 400
                note = it.get('komentarz')
                if not n or q <= 0:
                    return jsonify({'success': False, 'error': 'Nieprawidłowe dane w elementach listy'}), 400
                AgroWarehouseService.add_delivery(n, q, author_login, linia=linia, komentarz=note)
        else:
            try:
                q = float(ilosc or 0)
            except Exception:
                return jsonify({'success': False, 'error': 'Nieprawidłowa wartość ilości (popraw format liczby)'}), 400
            if not nazwa or q <= 0:
                return jsonify({'success': False, 'error': 'Nieprawidłowe dane (nazwa i ilość są wymagane)'}), 400
            AgroWarehouseService.add_delivery(nazwa, q, author_login, linia=linia, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in add_delivery: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
            return jsonify({'success': False, 'error': 'Brak ID ruchu'}), 400

        # allow partial updates
        ilosc_val = None
        if ilosc is not None and ilosc != '':
            try:
                ilosc_val = float(ilosc)
            except Exception:
                return jsonify({'success': False, 'error': 'Nieprawidłowa wartość ilości (popraw format liczby)'}), 400
        AgroWarehouseService.edit_delivery(ruch_id, nazwa=nazwa, ilosc=ilosc_val, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in edit_delivery: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/api/delivery', methods=['DELETE'])
@roles_required('admin')
def delete_delivery():
    try:
        data = request.get_json()
        ruch_id = data.get('ruch_id')
        if not ruch_id:
            return jsonify({'success': False, 'error': 'Brak ID ruchu'}), 400

        success = AgroWarehouseService.delete_delivery(ruch_id)
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Nie można usunąć tego ruchu'}), 400
    except Exception as e:
        current_app.logger.error(f"Error in delete_delivery: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@agro_warehouse_bp.route('/agro/api/confirm', methods=['POST'])
@login_required
def confirm_move():
    try:
        data = request.get_json()
        ruch_id = data.get('ruch_id')
        lokalizacja = data.get('lokalizacja')
        linia = data.get('linia', 'Agro')
        
        if not ruch_id:
            return jsonify({'success': False, 'error': 'Brak ID ruchu'}), 400
            
        worker_login = session.get('login')
        # Try confirming as delivery first
        success = AgroWarehouseService.confirm_delivery(ruch_id, worker_login, linia=linia, lokalizacja=lokalizacja)
        
        # If not a delivery (or already confirmed), try as external issue
        if not success:
            success = AgroWarehouseService.confirm_external_issue(ruch_id, worker_login, linia=linia)
            
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Nie można potwierdzić tego ruchu (być może został już przetworzony)'}), 400
    except Exception as e:
        current_app.logger.error(f"Error in confirm_move: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
        
        if not surowiec_id or ilosc <= 0:
            return jsonify({'success': False, 'error': 'Nieprawidłowe dane'}), 400
            
        worker_login = session.get('login')
        AgroWarehouseService.use_for_production(surowiec_id, ilosc, worker_login, plan_id=plan_id, linia=linia, komentarz=komentarz, zbiornik=zbiornik)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in use_material: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@agro_warehouse_bp.route('/agro/api/history', methods=['GET'])
@login_required
def api_history():
    linia = request.args.get('linia', 'Agro')
    data = request.args.get('data') or None
    plan_id = request.args.get('plan_id') or None
    limit = min(int(request.args.get('limit', 200)), 500)
    try:
        rows = AgroWarehouseService.get_history(limit=limit, linia=linia, data=data, plan_id=plan_id)
        result = []
        for h in rows:
            result.append({
                'id': h['id'],
                'surowiec_nazwa': h.get('surowiec_nazwa') or '',
                'lokalizacja': h.get('lokalizacja') or '',
                'typ_ruchu': h.get('typ_ruchu') or '',
                'ilosc': float(h['ilosc']) if h.get('ilosc') is not None else 0,
                'ilosc_po': float(h['ilosc_po']) if h.get('ilosc_po') is not None else None,
                'status': h.get('status') or '',
                'autor_login': h.get('autor_login') or '',
                'autor_data': h['autor_data'].strftime('%d.%m.%Y %H:%M') if h.get('autor_data') else '',
                'autor_date_only': h['autor_data'].strftime('%d.%m.%Y') if h.get('autor_data') else '',
                'autor_time_only': h['autor_data'].strftime('%H:%M') if h.get('autor_data') else '',
                'potwierdzil_login': h.get('potwierdzil_login') or '',
                'potwierdzil_data': h['potwierdzil_data'].strftime('%H:%M') if h.get('potwierdzil_data') else '',
                'plan_id': h.get('plan_id'),
                'plan_name': h.get('plan_name') or '',
                'zbiornik': h.get('zbiornik') or '',
                'komentarz': h.get('komentarz') or '',
            })
        return jsonify({'success': True, 'history': result, 'count': len(result)})
    except Exception as e:
        current_app.logger.error(f"Error in api_history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@agro_warehouse_bp.route('/agro/api/inventory', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def inventory():
    try:
        data = request.get_json()
        surowiec_id = data.get('surowiec_id')
        actual_qty = float(data.get('actual_qty', 0))
        komentarz = data.get('komentarz')
        linia = data.get('linia', 'Agro')
        
        if not surowiec_id:
            return jsonify({'success': False, 'error': 'Brak ID surowca'}), 400
            
        worker_login = session.get('login')
        AgroWarehouseService.perform_inventory(surowiec_id, actual_qty, worker_login, linia=linia, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in inventory: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
            return jsonify({'success': False, 'error': 'Brak id lub nowej nazwy'}), 400

        worker_login = session.get('login')
        success = AgroWarehouseService.rename_pallet(surowiec_id, new_name, worker_login, linia=linia)
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Nie udało się zmienić nazwy'}), 400
    except Exception as e:
        current_app.logger.error(f"Error in rename_pallet: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/api/current_plan', methods=['GET'])
@login_required
def api_current_plan():
    try:
        linia = request.args.get('linia', 'Agro')
        current_plan = AgroWarehouseService.get_current_running_plan(linia=linia)
        if current_plan:
            return jsonify({'success': True, 'plan_id': current_plan.get('id'), 'plan_name': current_plan.get('produkt')})
        return jsonify({'success': True, 'plan_id': None, 'plan_name': None})
    except Exception as e:
        current_app.logger.error(f"Error in api_current_plan: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/api/production_moves', methods=['GET'])
@login_required
def production_moves():
    try:
        linia = request.args.get('linia', 'Agro')
        limit = min(int(request.args.get('limit', 100)), 1000)
        rows = AgroWarehouseService.get_production_moves(limit=limit, linia=linia)
        result = []
        for h in rows:
            result.append({
                'id': h.get('id'),
                'surowiec_nazwa': h.get('surowiec_nazwa') or '',
                'surowiec_id': h.get('surowiec_id'),
                'ilosc': float(h['ilosc']) if h.get('ilosc') is not None else 0,
                'autor_login': h.get('autor_login') or '',
                'autor_data': h['autor_data'].strftime('%d.%m.%Y %H:%M') if h.get('autor_data') else '',
                'plan_id': h.get('plan_id'),
                'plan_name': h.get('plan_name') or '',
                'zbiornik': h.get('zbiornik') or '',
                'lokalizacja': h.get('lokalizacja') or '',
            })
        return jsonify({'success': True, 'moves': result, 'count': len(result)})
    except Exception as e:
        current_app.logger.error(f"Error in production_moves: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/report/warehouse', methods=['GET'])
@login_required
@roles_required('lider', 'admin')
def report_warehouse():
    try:
        linia = request.args.get('linia', 'Agro')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        fmt = request.args.get('format', 'csv')
        limit = min(int(request.args.get('limit', 1000)), 10000)

        rows = AgroWarehouseService.get_warehouse_entries(limit=limit, linia=linia, date_from=date_from, date_to=date_to)
        if fmt == 'json':
            return jsonify({'success': True, 'rows': rows, 'count': len(rows)})

        # CSV
        import io, csv
        si = io.StringIO()
        w = csv.writer(si)
        w.writerow(['id','surowiec_id','nazwa','ilosc','autor_login','autor_data','potwierdzil_login','potwierdzil_data','lokalizacja','obecna_lokalizacja','komentarz','plan_id','plan_name','zbiornik','typ_ruchu','status','ilosc_po'])
        for r in rows:
            w.writerow([
                r.get('id'), r.get('surowiec_id'), r.get('surowiec_nazwa'), r.get('ilosc'), r.get('autor_login'), r.get('autor_data').strftime('%Y-%m-%d %H:%M') if r.get('autor_data') else '',
                r.get('potwierdzil_login'), r.get('potwierdzil_data').strftime('%Y-%m-%d %H:%M') if r.get('potwierdzil_data') else '', r.get('lokalizacja'), r.get('obecna_lokalizacja'), r.get('komentarz'), r.get('plan_id'), r.get('plan_name'), r.get('zbiornik'), r.get('typ_ruchu'), r.get('status'), r.get('ilosc_po')
            ])
        output = si.getvalue()
        return current_app.response_class(output, mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename=warehouse_report_{linia}.csv'
        })
    except Exception as e:
        current_app.logger.error(f"Error in report_warehouse: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/report/production', methods=['GET'])
@login_required
@roles_required('lider', 'admin')
def report_production():
    try:
        linia = request.args.get('linia', 'Agro')
        fmt = request.args.get('format', 'csv')
        limit = min(int(request.args.get('limit', 500)), 10000)
        rows = AgroWarehouseService.get_production_moves(limit=limit, linia=linia)
        if fmt == 'json':
            return jsonify({'success': True, 'rows': rows, 'count': len(rows)})
        import io, csv
        si = io.StringIO()
        w = csv.writer(si)
        w.writerow(['id','surowiec_id','nazwa','ilosc','autor_login','autor_data','lokalizacja','zbiornik','plan_id','plan_name','komentarz','ilosc_po'])
        for r in rows:
            w.writerow([
                r.get('id'), r.get('surowiec_id'), r.get('surowiec_nazwa'), r.get('ilosc'), r.get('autor_login'), r.get('autor_data').strftime('%Y-%m-%d %H:%M') if r.get('autor_data') else '',
                r.get('lokalizacja'), r.get('zbiornik'), r.get('plan_id'), r.get('plan_name'), r.get('komentarz'), r.get('ilosc_po')
            ])
        output = si.getvalue()
        return current_app.response_class(output, mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename=production_report_{linia}.csv'
        })
    except Exception as e:
        current_app.logger.error(f"Error in report_production: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/report/combined', methods=['GET'])
@login_required
@roles_required('lider', 'admin')
def report_combined():
    try:
        linia = request.args.get('linia', 'Agro')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        fmt = request.args.get('format', 'csv')
        limit = min(int(request.args.get('limit', 2000)), 20000)
        rows = AgroWarehouseService.get_combined_report(limit=limit, linia=linia, date_from=date_from, date_to=date_to)
        if fmt == 'json':
            return jsonify({'success': True, 'rows': rows, 'count': len(rows)})
        import io, csv
        si = io.StringIO()
        w = csv.writer(si)
        w.writerow(['id','typ_ruchu','surowiec_id','nazwa','ilosc','autor_login','autor_data','potwierdzil_login','potwierdzil_data','lokalizacja','obecna_lokalizacja','zbiornik','plan_id','plan_name','komentarz','status','ilosc_po'])
        for r in rows:
            w.writerow([
                r.get('id'), r.get('typ_ruchu'), r.get('surowiec_id'), r.get('surowiec_nazwa'), r.get('ilosc'), r.get('autor_login'), r.get('autor_data').strftime('%Y-%m-%d %H:%M') if r.get('autor_data') else '',
                r.get('potwierdzil_login'), r.get('potwierdzil_data').strftime('%Y-%m-%d %H:%M') if r.get('potwierdzil_data') else '', r.get('lokalizacja'), r.get('obecna_lokalizacja'), r.get('zbiornik'), r.get('plan_id'), r.get('plan_name'), r.get('komentarz'), r.get('status'), r.get('ilosc_po')
            ])
        output = si.getvalue()
        return current_app.response_class(output, mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename=combined_report_{linia}.csv'
        })
    except Exception as e:
        current_app.logger.error(f"Error in report_combined: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
            return jsonify({'success': False, 'error': 'Nieprawidłowe dane'}), 400
            
        worker_login = session.get('login')
        AgroWarehouseService.issue_external(surowiec_id, ilosc, worker_login, linia=linia, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in issue_external: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@agro_warehouse_bp.route('/agro/api/suggest-location', methods=['POST'])
@login_required
def suggest_location():
    try:
        data = request.get_json()
        nazwa = data.get('nazwa')
        linia = data.get('linia', 'Agro')
        
        if not nazwa:
            return jsonify({'success': False, 'error': 'Brak nazwy surowca'}), 400
            
        suggestion = AgroWarehouseService.get_suggested_location(nazwa, linia=linia)
        return jsonify({'success': True, 'suggestion': suggestion})
    except Exception as e:
        current_app.logger.error(f"Error in suggest_location: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
