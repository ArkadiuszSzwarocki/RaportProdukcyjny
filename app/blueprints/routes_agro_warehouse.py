from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, current_app
from app.services.agro_warehouse_service import AgroWarehouseService
from app.decorators import login_required, roles_required, dynamic_role_required
from datetime import datetime

agro_warehouse_bp = Blueprint('agro_warehouse', __name__)

@agro_warehouse_bp.route('/agro/magazyn')
@login_required
@dynamic_role_required('agro_magazyn')
def index():
    linia = request.args.get('linia', 'Agro')
    inventory = AgroWarehouseService.get_inventory(linia=linia)
    history = AgroWarehouseService.get_history(limit=50, linia=linia)
    pending = AgroWarehouseService.get_history(status='OCZEKUJACE', linia=linia)
    dictionary = AgroWarehouseService.get_dictionary()
    
    return render_template(
        'agro_magazyn.html',
        inventory=inventory,
        history=history,
        pending=pending,
        dictionary=dictionary,
        linia=linia
    )

@agro_warehouse_bp.route('/agro/api/delivery', methods=['POST'])
@roles_required('magazynier', 'admin')
def add_delivery():
    try:
        data = request.get_json()
        nazwa = data.get('nazwa')
        ilosc = float(data.get('ilosc', 0))
        komentarz = data.get('komentarz')
        linia = data.get('linia', 'Agro')
        
        if not nazwa or ilosc <= 0:
            return jsonify({'success': False, 'error': 'Nieprawidłowe dane (nazwa i ilość są wymagane)'}), 400
            
        author_login = session.get('login')
        AgroWarehouseService.add_delivery(nazwa, ilosc, author_login, linia=linia, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error in add_delivery: {e}")
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
