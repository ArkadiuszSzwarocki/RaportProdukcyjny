"""
Trasy (Routes & API endpoints) dla modułu OSIP oraz Transferów Wewnętrznych.
"""
from flask import render_template, request, jsonify, session, redirect, url_for
from app.blueprints.osip import osip_bp
from app.services.osip_warehouse_service import OsipWarehouseService
from app.services.osip_transfer_service import OsipTransferService
from app.decorators import login_required, roles_required

warehouse_service = OsipWarehouseService()
transfer_service = OsipTransferService()


@osip_bp.route('/warehouse', methods=['GET'])
@login_required
def warehouse_view():
    """Główny widok Magazynu Zewnętrznego OSIP dla magazyniera."""
    return redirect(url_for('warehouse_v2.index', zakladka='OSIP'))


@osip_bp.route('/expedition', methods=['GET'])
@login_required
def expedition_view():
    """Dedykowany widok Wydań Zewnętrznych wyłącznie z Magazynu OSIP dla magazyniera OSIP."""
    inventory = warehouse_service.get_osip_inventory()
    expeditions = warehouse_service.get_osip_expeditions()
    return render_template('osip/osip_expedition.html', inventory=inventory, expeditions=expeditions)


@osip_bp.route('/api/expedition/dispatch', methods=['POST'])
@login_required
def dispatch_osip_pallet_api():
    """API do zatwierdzenia wydania zewnętrznego palety wyłącznie z Magazynu OSIP."""
    payload = request.get_json() or {}
    pallet_id = payload.get('pallet_id')
    pallet_type = payload.get('pallet_type', 'Surowiec')
    customer = payload.get('customer', '')
    notes = payload.get('notes', '')
    worker = session.get('login', 'Magazynier OSIP')
    
    if not pallet_id:
        return jsonify({'success': False, 'error': 'Brak identyfikatora palety'}), 400
        
    success, msg = warehouse_service.dispatch_osip_pallet(pallet_id, pallet_type, worker, customer, notes)
    return jsonify({'success': success, 'message': msg})


@osip_bp.route('/transfers', methods=['GET'])
@login_required
def transfers_view():
    """Widok listy i obsługi transferów wewnętrznych."""
    return render_template('osip/osip_transfers.html')


@osip_bp.route('/transfers/<int:transfer_id>', methods=['GET'])
@login_required
def transfer_details_view(transfer_id):
    """Widok dedykowanej pełnej strony ze szczegółami zlecenia transferu OSIP."""
    transfer = transfer_service.get_transfer_by_id(transfer_id)
    if not transfer:
        flash('Nie znaleziono zlecenia transferu.', 'danger')
        return redirect(url_for('osip.transfers_view'))
    return render_template('osip/osip_transfer_details.html', transfer=transfer)


@osip_bp.route('/api/inventory', methods=['GET'])
@login_required
def get_inventory_api():
    """API zwracające stan surowców i wyrobów w OSIP."""
    search_term = request.args.get('search', '')
    data = warehouse_service.get_osip_inventory(search_term)
    return jsonify({"success": True, "data": data})


@osip_bp.route('/api/layout', methods=['GET'])
@login_required
def get_layout_api():
    """API zwracające układ 77 alejek hali OSIP."""
    layout = warehouse_service.get_osip_layout_stats()
    return jsonify({"success": True, "data": layout})


@osip_bp.route('/api/transfers', methods=['GET'])
@login_required
def get_transfers_api():
    """API zwracające listę transferów wewnętrznych."""
    user_role = session.get('rola', 'magazynier')
    user_subrole = session.get('subrole', 'OSIP')
    transfers = transfer_service.get_transfers_list(user_role, user_subrole)
    
    result = []
    for t in transfers:
        result.append({
            "id": t.id,
            "transfer_code": t.transfer_code,
            "source_warehouse": t.source_warehouse,
            "destination_warehouse": t.destination_warehouse,
            "status": t.status,
            "created_by": t.created_by,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else None,
            "items_count": len(t.items),
            "items": [
                {
                    "id": item.id,
                    "pallet_id": item.pallet_id,
                    "nr_palety": item.nr_palety,
                    "product_name": item.product_name,
                    "requested_qty": item.requested_qty,
                    "loaded_qty": item.loaded_qty,
                    "unit": item.unit,
                    "status": item.status
                }
                for item in t.items
            ]
        })
    return jsonify({"success": True, "transfers": result})


@osip_bp.route('/api/transfers', methods=['POST'])
@login_required
def create_transfer_api():
    """API tworzące nowe zlecenie transferu."""
    payload = request.get_json() or {}
    source = payload.get('source_warehouse', 'MS01')
    destination = payload.get('destination_warehouse', 'OSIP')
    items = payload.get('items', [])
    notes = payload.get('notes')
    created_by = session.get('login', 'magazynier')

    try:
        transfer = transfer_service.create_transfer_order(source, destination, items, created_by, notes)
        return jsonify({"success": True, "message": f"Utworzono zlecenie transferu {transfer.transfer_code}", "transfer_id": transfer.id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@osip_bp.route('/api/transfers/<int:transfer_id>/dispatch', methods=['POST'])
@login_required
def dispatch_transfer_api(transfer_id):
    """API realizujące załadunek zlecenia."""
    payload = request.get_json() or {}
    loaded_pallets = payload.get('loaded_pallets', [])
    user_login = session.get('login', 'magazynier')

    try:
        transfer = transfer_service.dispatch_transfer(transfer_id, loaded_pallets, user_login)
        return jsonify({"success": True, "message": f"Załadowano transfer {transfer.transfer_code}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@osip_bp.route('/api/transfers/<int:transfer_id>/receive', methods=['POST'])
@login_required
def receive_transfer_api(transfer_id):
    """API realizujące przyjęcie zlecenia (masowe lub wg mapy) w magazynie docelowym."""
    payload = request.get_json() or {}
    target_locations = payload.get('target_locations', {})  # Dict[pallet_id/nr_palety/item_id -> loc]
    default_loc = payload.get('default_location') or payload.get('location') or 'OS01'
    if not isinstance(target_locations, dict):
        target_locations = {}
    if default_loc and 'default' not in target_locations:
        target_locations['default'] = default_loc

    user_login = session.get('login', 'magazynier')

    try:
        transfer = transfer_service.receive_transfer(transfer_id, target_locations, user_login)
        return jsonify({"success": True, "message": f"Przyjęto transfer {transfer.transfer_code}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@osip_bp.route('/api/transfers/<int:transfer_id>/scan_receive', methods=['POST'])
@login_required
def scan_receive_api(transfer_id):
    """API szybkiego skanowania w locie: przyjęcie pojedynczej palety do lokalizacji."""
    payload = request.get_json() or {}
    pallet_code = payload.get('pallet_code') or payload.get('code') or payload.get('nr_palety')
    target_location = payload.get('target_location') or payload.get('location') or 'OS01'
    user_login = session.get('login', 'magazynier')

    if not pallet_code:
        return jsonify({"success": False, "message": "Nie podano kodu palety."}), 400

    try:
        result = transfer_service.receive_single_item(transfer_id, pallet_code, target_location, user_login)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@osip_bp.route('/api/transfers/<int:transfer_id>/cancel', methods=['POST'])
@login_required
def cancel_transfer_api(transfer_id):
    """API anulujące zlecenie transferu ze zwrotem palet."""
    user_login = session.get('login', 'magazynier')
    try:
        transfer = transfer_service.cancel_transfer(transfer_id, user_login)
        return jsonify({"success": True, "message": f"Anulowano transfer {transfer.transfer_code}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400
