from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, current_app
from app.services.agro_warehouse_service import AgroWarehouseService
from app.services.dashboard_service import DashboardService
from app.decorators import login_required, roles_required, dynamic_role_required
from datetime import datetime, date
from app.services.agro_warehouse_service import AgroWarehouseService
from app.db import get_db_connection, get_table_name

agro_warehouse_bp = Blueprint('agro_warehouse', __name__)

@agro_warehouse_bp.route('/agro/magazyn')
@login_required
@dynamic_role_required('agro_magazyn')
def index():
    linia = request.args.get('linia', 'Agro')
    # Parse optional date (useful for viewing pallets by day)
    from datetime import datetime, date as _date
    try:
        dzisiaj = datetime.strptime(request.args.get('data'), '%Y-%m-%d').date() if request.args.get('data') else _date.today()
    except Exception:
        dzisiaj = _date.today()

    # inventory grouped by material (for compact view)
    inventory = AgroWarehouseService.get_inventory_grouped(linia=linia)
    inventory_by_location = AgroWarehouseService.get_inventory_by_location(linia=linia)
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
    
    # Also include confirmed pallets for this day/line using DashboardService
    magazyn_palety, unconfirmed_palety, suma_wykonanie = DashboardService.get_warehouse_data(dzisiaj, linia=linia)

    return render_template(
        'agro_warehouse/index.html',
        inventory=inventory,
        inventory_by_location=inventory_by_location,
        history=history,
        pending=pending,
        dictionary=dictionary,
        linia=linia,
        current_plan_id=current_plan_id,
        current_plan_name=current_plan_name,
        magazyn_palety=magazyn_palety,
        unconfirmed_palety=unconfirmed_palety,
        dzisiaj=str(dzisiaj),
        rola=session.get('rola')
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
    return render_template('agro_warehouse/opakowania.html', items=items, linia=linia)


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


@agro_warehouse_bp.route('/agro/api/opakowania/link', methods=['POST'])
@login_required
def link_packaging():
    try:
        data = request.get_json()
        success, error = AgroWarehouseService.link_packaging_to_plan(
            data.get('opakowanie_id'),
            data.get('plan_id')
        )
        return jsonify({'success': success, 'error': error})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/api/opakowania/return', methods=['POST'])
@login_required
def return_packaging():
    try:
        data = request.get_json()
        success, error = AgroWarehouseService.return_packaging_from_machine(
            data.get('opakowanie_id'),
            data.get('stan_po'),
            data.get('lokalizacja'),
            session.get('login')
        )
        return jsonify({'success': success, 'error': error})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/api/opakowania/undo_link', methods=['POST'])
@login_required
def undo_link_packaging():
    try:
        data = request.get_json()
        link_id = data.get('link_id')
        if not link_id:
            return jsonify({'success': False, 'error': 'Brak link_id'}), 400
        success, error = AgroWarehouseService.undo_packaging_link(link_id)
        return jsonify({'success': success, 'error': error})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/api/opakowania/undo_return', methods=['POST'])
@login_required
def undo_return_packaging():
    try:
        data = request.get_json()
        link_id = data.get('link_id')
        if not link_id:
            return jsonify({'success': False, 'error': 'Brak link_id'}), 400
        success, error = AgroWarehouseService.undo_packaging_return(link_id, session.get('login'))
        return jsonify({'success': success, 'error': error})
    except Exception as e:
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
                p = it.get('nr_partii')
                dz = it.get('data_przydatnosci')
                pf = it.get('pkg_form', 'bags')
                if not n or q <= 0:
                    return jsonify({'success': False, 'error': 'Nieprawidłowe dane w elementach listy'}), 400
                AgroWarehouseService.add_delivery(n, q, author_login, linia=linia, komentarz=note, nr_partii=p, data_produkcji=dp, data_przydatnosci=dz, pkg_form=pf)
        else:
            try:
                q = float(ilosc or 0)
            except Exception:
                return jsonify({'success': False, 'error': 'Nieprawidłowa wartość ilości (popraw format liczby)'}), 400
            if not nazwa or q <= 0:
                return jsonify({'success': False, 'error': 'Nieprawidłowe dane (nazwa i ilość są wymagane)'}), 400
            
            p = data.get('nr_partii')
            dp = data.get('data_produkcji')
            dz = data.get('data_przydatnosci')
            pf = data.get('pkg_form', 'bags')
            AgroWarehouseService.add_delivery(nazwa, q, author_login, linia=linia, komentarz=komentarz, nr_partii=p, data_produkcji=dp, data_przydatnosci=dz, pkg_form=pf)
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
        
        nr_partii = data.get('nr_partii')
        data_produkcji = data.get('data_produkcji')
        data_przydatnosci = data.get('data_przydatnosci')
        
        if not ruch_id:
            return jsonify({'success': False, 'error': 'Brak ID ruchu'}), 400
            
        worker_login = session.get('login')
        # Try confirming as delivery first
        success = AgroWarehouseService.confirm_delivery(
            ruch_id, 
            worker_login, 
            linia=linia, 
            lokalizacja=lokalizacja,
            nr_partii=nr_partii,
            data_produkcji=data_produkcji,
            data_przydatnosci=data_przydatnosci
        )
        
        # Try as external issue
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
@dynamic_role_required('raporty.agro_warehouse')
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
@dynamic_role_required('raporty.agro_production')
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
@dynamic_role_required('raporty.agro_production')
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
            return jsonify({'success': False, 'error': 'Nieprawidłowe dane'}), 400

        worker_login = session.get('login')
        AgroWarehouseService.return_from_production(
            surowiec_id, ilosc, worker_login,
            plan_id=plan_id, linia=linia, komentarz=komentarz,
            ruch_produkcja_id=ruch_produkcja_id, lokalizacja=lokalizacja
        )
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in return_from_production: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agro_warehouse_bp.route('/agro/api/production_items_for_return', methods=['GET'])
@login_required
def production_items_for_return():
    try:
        linia = request.args.get('linia', 'Agro')
        limit = min(int(request.args.get('limit', 200)), 1000)
        items = AgroWarehouseService.get_production_items_for_return(linia=linia, limit=limit)
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        current_app.logger.error(f"Error in production_items_for_return: {e}")
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

@agro_warehouse_bp.route('/agro/api/inventory', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def api_inventory():
    try:
        data = request.get_json()
        surowiec_id = data.get('surowiec_id')
        actual_qty = data.get('actual_qty')
        komentarz = data.get('komentarz')
        linia = data.get('linia', 'Agro')
        
        if not surowiec_id or actual_qty is None:
            return jsonify({'success': False, 'error': 'Brak ID lub ilości'}), 400
            
        try:
            qty = float(actual_qty)
        except Exception:
            return jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400
            
        worker = session.get('login')
        AgroWarehouseService.adjust_inventory(surowiec_id, qty, worker, linia=linia, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in api_inventory: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@agro_warehouse_bp.route('/agro/api/bulk_inventory', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def api_bulk_inventory():
    try:
        data = request.get_json()
        items = data.get('items', [])
        linia = data.get('linia', 'Agro')
        worker = session.get('login')
        
        updated_count = 0
        for it in items:
            s_id = it.get('surowiec_id')
            qty = it.get('actual_qty')
            note = it.get('komentarz', 'Inwentaryzacja zbiorcza')
            if s_id and qty is not None:
                AgroWarehouseService.adjust_inventory(s_id, float(qty), worker, linia=linia, komentarz=note)
                updated_count += 1
                
        return jsonify({'success': True, 'updated': updated_count})
    except Exception as e:
        current_app.logger.error(f"Error in api_bulk_inventory: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@agro_warehouse_bp.route('/agro/api/locations_inventory', methods=['GET'])
@login_required
def api_locations_inventory():
    try:
        linia = request.args.get('linia', 'Agro')
        # Re-use get_inventory but format for bulk inventory table
        rows = AgroWarehouseService.get_inventory(linia=linia)
        items = []
        for r in rows:
            items.append({
                'id': r['id'],
                'nazwa': r.get('nazwa'),
                'lokalizacja': r.get('lokalizacja'),
                'stan_magazynowy': float(r['stan_magazynowy']) if r.get('stan_magazynowy') is not None else 0
            })
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        current_app.logger.error(f"Error in api_locations_inventory: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
            return jsonify({'success': False, 'error': 'Brak ID lub ilości'}), 400
            
        try:
            qty = float(ilosc)
        except Exception:
            return jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400
            
        worker = session.get('login')
        AgroWarehouseService.issue_warehouse(surowiec_id, qty, worker, linia=linia, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in api_issue_warehouse: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@agro_warehouse_bp.route('/agro/raport_palet', methods=['GET'])
@login_required
def raport_palet():
    """Generates a printable pallet report for AGRO line."""
    data_planu = request.args.get('data', str(date.today()))
    plan_id = request.args.get('plan_id') # Specific order filter
    
    is_ajax = (request.headers.get('X-Requested-With') == 'XMLHttpRequest')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Fetch relevant Workowanie plans
        query = """
            SELECT w.id as work_id, w.produkt, w.tonaz_rzeczywisty as w_kg, 
                   z.id as zasyp_id, z.tonaz_rzeczywisty as z_kg,
                   w.nazwa_zlecenia
            FROM plan_produkcji_agro w
            LEFT JOIN plan_produkcji_agro z ON w.zasyp_id = z.id
            WHERE w.data_planu = %s AND w.sekcja = 'Workowanie' AND (w.is_deleted = 0 OR w.is_deleted IS NULL)
        """
        params = [data_planu]
        
        if plan_id:
            query += " AND w.id = %s"
            params.append(plan_id)
            
        cursor.execute(query, tuple(params))
        plans = cursor.fetchall()

        report_data = []
        for p in plans:
            # 1. Fetch Inputs (Szarże + Mixes)
            # Batches (including confirmed add-ons)
            cursor.execute("""
                SELECT s.id, 
                       (s.waga + COALESCE((SELECT SUM(d.kg) FROM dosypki_agro d WHERE d.szarza_id = s.id AND d.potwierdzone = 1 AND d.anulowana = 0), 0)) as waga, 
                       s.data_dodania 
                FROM szarze_agro s
                WHERE s.plan_id = %s 
                ORDER BY s.data_dodania ASC
            """, (p['zasyp_id'],))
            batches_raw = cursor.fetchall()
            
            # Mixes (already handled, but ensure we use correct plan_id branch)
            cursor.execute("""
                SELECT id, waga_kg as waga, COALESCE(zuzyte_kiedy, created_at) as data_dodania, kategoria 
                FROM agro_mix_rozliczenie 
                WHERE zuzyte_w_id = %s 
                ORDER BY data_dodania ASC
            """, (p['zasyp_id'],))
            mixes_raw = cursor.fetchall()
            
            # Independent Dosypki (not linked to a specific batch)
            cursor.execute("""
                SELECT id, nazwa, kg, data_zlecenia 
                FROM dosypki_agro 
                WHERE plan_id = %s AND szarza_id IS NULL AND potwierdzone = 1 AND anulowana = 0
                ORDER BY data_zlecenia ASC
            """, (p['zasyp_id'],))
            solo_dosypki = cursor.fetchall()
            
            # Combine Inputs
            all_inputs = []
            for b_raw in batches_raw:
                all_inputs.append({
                    'label': f"Zasyp #{b_raw['id']}",
                    'waga': b_raw['waga'] or 0,
                    'time': b_raw['data_dodania']
                })
            for d_raw in solo_dosypki:
                all_inputs.append({
                    'label': f"Dosypka {d_raw['nazwa']} #{d_raw['id']}",
                    'waga': d_raw['kg'] or 0,
                    'time': d_raw['data_zlecenia']
                })
            for m_raw in mixes_raw:
                all_inputs.append({
                    'label': f"MIX {m_raw['kategoria'].replace('_',' ')} #{m_raw['id']}",
                    'waga': m_raw['waga'] or 0,
                    'time': m_raw['data_dodania']
                })
            
            # Order inputs chronologically
            all_inputs.sort(key=lambda x: x['time'] if x['time'] else datetime.min)
            
            # Calculate cumulative ranges for inputs
            current_in_kg = 0
            input_ranges = []
            for inp in all_inputs:
                start = current_in_kg
                end = current_in_kg + inp['waga']
                input_ranges.append({'label': inp['label'], 'start': start, 'end': end})
                current_in_kg = end

            # 2. Fetch Outputs (Pallets)
            cursor.execute("""
                SELECT 
                    p.id, p.waga, p.status, p.data_dodania, 
                    p.dodal_login,
                    COALESCE(m.user_login, p.potwierdzil_login) as potwierdzil_login,
                    COALESCE(m.data_potwierdzenia, p.data_potwierdzenia) as data_potwierdzenia
                FROM palety_agro p
                LEFT JOIN magazyn_palety_agro m ON p.id = m.paleta_workowanie_id
                WHERE p.plan_id = %s
                ORDER BY p.data_dodania ASC
            """, (p['work_id'],))
            pallets_raw = cursor.fetchall()
            
            # Calculate shares for each pallet
            current_out_kg = 0
            processed_pallets = []
            for pal_raw in pallets_raw:
                p_start = current_out_kg
                p_end = current_out_kg + (pal_raw['waga'] or 0)
                
                # Check overlaps with input ranges
                shares = []
                for ir in input_ranges:
                    # Overlap [max(p_start, ir_start), min(p_end, ir_end)]
                    overlap_start = max(p_start, ir['start'])
                    overlap_end = min(p_end, ir['end'])
                    
                    if overlap_end > overlap_start:
                        overlap_kg = overlap_end - overlap_start
                        waga_palety = float(pal_raw['waga'] or 0)
                        percent = (overlap_kg / waga_palety) * 100 if waga_palety > 0 else 0
                        
                        # Only show if significant (> 0.5%)
                        if percent >= 0.5:
                            shares.append(f"{ir['label']} ({round(percent)}%)")
                
                pal_raw['sklad'] = ", ".join(shares) if shares else "Nieznany skład"
                processed_pallets.append(pal_raw)
                current_out_kg = p_end

            # Additional Mix info for the summary table
            cursor.execute("SELECT id, waga_kg as waga_kg, kategoria, autor_login, created_at FROM agro_mix_rozliczenie WHERE zuzyte_w_id = %s", (p['zasyp_id'],))
            mixes_summary = cursor.fetchall()

            # 3. Fetch Packaging Settlements (Rozliczenie Workowania)
            cursor.execute("""
                SELECT id, opakowanie_nazwa, stan_przed, wyprodukowano_szt, szt_na_palecie, zuzyte_worki, stan_po, autor_login, created_at
                FROM agro_workowanie_rozliczenie
                WHERE plan_id = %s
                ORDER BY created_at ASC
            """, (p['work_id'],))
            rozliczenia = cursor.fetchall()

            report_data.append({
                'plan': p,
                'palety': processed_pallets,
                'mixes': mixes_summary,
                'opakowania': rozliczenia,
                'total_pallet_kg': sum(pal['waga'] or 0 for pal in pallets_raw),
                'total_mix_kg': sum(m['waga_kg'] or 0 for m in mixes_summary)
            })

        # If it's a selection call (header button without plan_id)
        if not plan_id and len(plans) > 1 and request.args.get('select') == '1':
            return render_template('agro_warehouse/raport_palet_select.html', plans=plans, data_planu=data_planu, is_ajax=is_ajax)

        return render_template('agro_warehouse/raport_palet.html', 
                               report_data=report_data, 
                               data_planu=data_planu,
                               single_view=bool(plan_id),
                               is_ajax=is_ajax,
                               print_date=datetime.now().strftime('%d.%m.%Y %H:%M'))
    except Exception as e:
        current_app.logger.error(f"Error generating raport_palet: {e}")
        return f"Błąd generowania raportu: {str(e)}", 500
    finally:
        conn.close()
