from flask import render_template, request, jsonify, session
from app.decorators import login_required
from .blueprint import agro_warehouse_bp
from app.services.lp01_service import Lp01Service
from app.services.warehouse_v2_service import WarehouseV2Service
from app.utils.location_validator import validate_warehouse_location

@agro_warehouse_bp.route('/agro/maszyna/lp01')
@login_required
def lp01_view():
    """Widok główny stanowiska maszyny LP01 (materiały eksploatacyjne i archiwum)."""
    linia = request.args.get('linia', 'AGRO')
    kpis = Lp01Service.get_lp01_kpis(linia=linia)
    active_items = Lp01Service.get_active_lp01_items(linia=linia)
    history = Lp01Service.get_lp01_history(linia=linia, limit=50)
    available_stock = Lp01Service.get_available_warehouse_consumables(linia=linia)
    return render_template(
        'agro_warehouse/lp01_materials.html',
        linia=linia,
        kpis=kpis,
        active_items=active_items,
        history=history,
        available_stock=available_stock
    )

@agro_warehouse_bp.route('/api/lp01/items', methods=['GET'])
@login_required
def api_lp01_items():
    linia = request.args.get('linia', 'AGRO')
    items = Lp01Service.get_active_lp01_items(linia=linia)
    kpis = Lp01Service.get_lp01_kpis(linia=linia)
    return jsonify({'success': True, 'items': items, 'kpis': kpis})

@agro_warehouse_bp.route('/api/lp01/history', methods=['GET'])
@login_required
def api_lp01_history():
    linia = request.args.get('linia', 'AGRO')
    limit = int(request.args.get('limit', 100))
    history = Lp01Service.get_lp01_history(linia=linia, limit=limit)
    return jsonify({'success': True, 'history': history})

@agro_warehouse_bp.route('/api/lp01/available-consumables', methods=['GET'])
@login_required
def api_lp01_available():
    linia = request.args.get('linia', 'AGRO')
    items = Lp01Service.get_available_warehouse_consumables(linia=linia)
    return jsonify({'success': True, 'items': items})

@agro_warehouse_bp.route('/api/lp01/archive', methods=['POST'])
@login_required
def api_lp01_archive():
    data = request.get_json(silent=True) or {}
    item_id = data.get('id')
    item_type = data.get('type', 'Opakowanie')
    consumed_qty = data.get('consumed_qty')
    komentarz = data.get('komentarz')
    linia = data.get('linia', 'AGRO')
    user = session.get('login', 'nieznany')

    if not item_id:
        return jsonify({'success': False, 'error': 'Brak ID materiału'}), 400

    ok, msg = Lp01Service.archive_lp01_item(
        item_id=int(item_id),
        item_type=item_type,
        user_login=user,
        consumed_qty=float(consumed_qty) if consumed_qty is not None else None,
        linia=linia,
        komentarz=komentarz
    )
    return jsonify({'success': ok, 'message': msg})

@agro_warehouse_bp.route('/api/lp01/dispatch', methods=['POST'])
@login_required
def api_lp01_dispatch():
    """Wydanie materiału z magazynu na maszynę LP01."""
    data = request.get_json(silent=True) or {}
    item_id = data.get('id')
    item_type = data.get('type', 'Opakowanie')
    amount = data.get('amount')
    linia = data.get('linia', 'AGRO')
    user = session.get('login', 'nieznany')

    if not item_id:
        return jsonify({'success': False, 'error': 'Brak ID materiału do wydania'}), 400

    res = WarehouseV2Service.move_pallet(
        pallet_id=item_id,
        pallet_type=item_type,
        new_location='LP01',
        worker_login=user,
        linia=linia,
        amount_to_move=float(amount) if amount is not None else None
    )
    ok = res[0]
    msg = res[1]
    split_info = res[2] if len(res) > 2 else None
    return jsonify({'success': ok, 'message': msg, 'split_info': split_info})

@agro_warehouse_bp.route('/api/lp01/return', methods=['POST'])
@login_required
def api_lp01_return():
    """Zwrot materiału z maszyny LP01 z powrotem na regał w magazynie."""
    data = request.get_json(silent=True) or {}
    item_id = data.get('id')
    item_type = data.get('type', 'Opakowanie')
    target_loc = data.get('location')
    amount = data.get('amount')
    linia = data.get('linia', 'AGRO')
    user = session.get('login', 'nieznany')

    if not item_id or not target_loc:
        return jsonify({'success': False, 'error': 'Brak parametrów (id, location)'}), 400

    is_valid, err_msg = validate_warehouse_location(target_loc, allow_empty=False)
    if not is_valid:
        return jsonify({'success': False, 'error': err_msg}), 400

    res = WarehouseV2Service.move_pallet(
        pallet_id=item_id,
        pallet_type=item_type,
        new_location=target_loc.strip().upper(),
        worker_login=user,
        linia=linia,
        amount_to_move=float(amount) if amount is not None else None
    )
    ok = res[0]
    msg = res[1]
    split_info = res[2] if len(res) > 2 else None
    return jsonify({'success': ok, 'message': msg, 'split_info': split_info})

