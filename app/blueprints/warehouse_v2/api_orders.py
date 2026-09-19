"""
API endpointy zamówień magazynowych i kompletacji (Picking).

Endpointy — Zamówienia:
- GET  /api/orders             — lista zamówień (filtr ?status=NOWE)
- GET  /api/orders/surowce     — lista surowców ze słownika
- POST /api/orders/create      — tworzenie zamówienia
- POST /api/orders/<id>/confirm — potwierdzenie odczytania

Endpointy — Kompletacja (Picking):
- POST /api/orders/start-picking              — tworzy dyspozycję kompletacji
- GET  /api/orders/picking/<order_ref>         — szczegóły zamówienia kompletacji
- GET  /api/orders/picking/active              — lista aktywnych kompletacji
- POST /api/orders/picking/<order_ref>/confirm — potwierdź pobranie palety (skan SSCC)
- POST /api/orders/picking/<order_ref>/cancel  — anuluj zamówienie kompletacji
"""
from flask import jsonify, request, session
from app.services.warehouse_order_service import WarehouseOrderService
from app.services.picking_service import PickingService
from .blueprint import warehouse_v2_bp

_order_service = WarehouseOrderService()
_picking_service = PickingService()


@warehouse_v2_bp.route('/api/orders', methods=['GET'])
def api_orders_list():
    """Zwraca listę zamówień z opcjonalnym filtrem statusu."""
    status_filter = request.args.get('status')
    orders = _order_service.get_all_orders(status_filter)
    return jsonify({'success': True, 'orders': orders})


@warehouse_v2_bp.route('/api/sidebar-badges', methods=['GET'])
def api_sidebar_badges():
    """Zwraca zaktualizowane liczniki dla menu bocznego (zamówienia, kompletacja)."""
    orders_nowe = 0
    active_picking = 0
    try:
        orders = _order_service.get_all_orders('NOWE')
        orders_nowe = len(orders)
    except Exception:
        pass
    try:
        picking_orders = _picking_service.get_active_orders()
        active_picking = len(picking_orders)
    except Exception:
        pass
    return jsonify({
        'success': True,
        'orders_nowe': orders_nowe,
        'active_picking': active_picking
    })


@warehouse_v2_bp.route('/api/orders/surowce', methods=['GET'])
def api_orders_surowce():
    """Zwraca listę surowców ze słownika do formularza zamówienia."""
    surowce = _order_service.get_available_surowce()
    return jsonify({'success': True, 'surowce': surowce})


@warehouse_v2_bp.route('/api/orders/create', methods=['POST'])
def api_orders_create():
    """Tworzy nowe zamówienie na surowiec."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Brak danych wejściowych.'}), 400

    items = data.get('items', [])
    komentarz = data.get('komentarz', '')
    operator_login = session.get('login', 'nieznany')

    success, message, order_id = _order_service.create_order(
        items=items,
        operator_login=operator_login,
        komentarz=komentarz
    )

    status_code = 201 if success else 400
    response = {'success': success, 'message': message}
    if order_id:
        response['order_id'] = order_id

    return jsonify(response), status_code


@warehouse_v2_bp.route('/api/orders/<int:order_id>/confirm', methods=['POST'])
def api_orders_confirm(order_id):
    """Potwierdza odczytanie zamówienia przez magazyniera."""
    magazynier_login = session.get('login', 'nieznany')

    success, message = _order_service.confirm_order(order_id, magazynier_login)

    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': message}), status_code


@warehouse_v2_bp.route('/api/orders/<int:order_id>/delete', methods=['POST', 'DELETE'])
@warehouse_v2_bp.route('/api/orders/delete', methods=['POST', 'DELETE'])
def api_orders_delete(order_id=None):
    """Trwale usuwa zamówienie (wymaga ról: masteradmin, admin, zarząd)."""
    user_role = str(session.get('rola') or session.get('role') or session.get('login') or '').lower().replace(' ', '').replace('_', '').strip()

    if order_id is None:
        data = request.get_json(silent=True) or {}
        order_id = data.get('order_id') or request.args.get('order_id')
        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Brak wymaganego parametru order_id.'}), 400

    success, message = _order_service.delete_order(order_id, user_role)

    status_code = 200 if success else 403 if 'Brak uprawnień' in message else 400
    return jsonify({'success': success, 'message': message}), status_code

@warehouse_v2_bp.route('/api/orders/check_stock', methods=['POST'])
def api_orders_check_stock():
    """Kalkulator: przelicza zapotrzebowanie na surowce i weryfikuje stany magazynowe (bez zapisywania)."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Brak danych wejściowych.', 'results': []}), 400

    items = data.get('items', [])
    order_tons = data.get('order_tons', 0)
    linia = request.args.get('linia') or session.get('grupa') or 'AGRO'
    if linia.upper() not in ['AGRO', 'PSD']:
        linia = 'AGRO'

    success, message, payload = _order_service.calculate_and_check_stock(items, order_tons, linia.upper())

    status_code = 200 if success else 400
    if not success:
        return jsonify({'success': False, 'message': message, 'results': []}), status_code

    items_res = payload.get('items', []) if isinstance(payload, dict) else payload
    scanned_zones = payload.get('scanned_zones', []) if isinstance(payload, dict) else []

    return jsonify({
        'success': True,
        'message': message,
        'results': items_res,
        'scanned_zones': scanned_zones,
        'order_tons': order_tons
    }), 200


# ───────────────────────────────────────────────
#  PICKING / COMPLETION ENDPOINTS
# ───────────────────────────────────────────────

@warehouse_v2_bp.route('/api/orders/start-picking', methods=['POST'])
def api_orders_start_picking():
    """Creates a picking/completion order from calculator results."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Brak danych wejściowych.'}), 400

    operator_login = session.get('login', 'nieznany')

    success, message, payload = _picking_service.start_picking(data, operator_login)

    status_code = 201 if success else 400
    return jsonify({
        'success': success,
        'message': message,
        'data': payload
    }), status_code


@warehouse_v2_bp.route('/api/orders/picking/active', methods=['GET'])
def api_orders_picking_active():
    """Returns list of active picking orders."""
    operator_login = request.args.get('operator')
    orders = _picking_service.get_active_orders(operator_login or None)
    return jsonify({'success': True, 'data': orders, 'orders': orders})


@warehouse_v2_bp.route('/api/orders/picking/<order_ref>', methods=['GET'])
def api_orders_picking_details(order_ref):
    """Returns full details of a picking order."""
    details = _picking_service.get_picking_order_details(order_ref)
    if not details:
        return jsonify({'success': False, 'message': f'Zamówienie {order_ref} nie istnieje.'}), 404

    return jsonify({'success': True, 'data': details})


@warehouse_v2_bp.route('/api/orders/picking/<order_ref>/confirm', methods=['POST'])
def api_orders_picking_confirm(order_ref):
    """Confirms a pick by SSCC scan or item ID."""
    data = request.get_json() or {}
    magazynier_login = session.get('login', 'nieznany')

    sscc_code = data.get('sscc_code', '').strip()
    item_id = data.get('item_id')

    if sscc_code:
        success, message, item_data = _picking_service.confirm_pick_by_sscc(
            order_ref, sscc_code, magazynier_login
        )
    elif item_id:
        success, message, item_data = _picking_service.confirm_pick_by_id(
            item_id, magazynier_login
        )
    else:
        return jsonify({'success': False, 'message': 'Podaj sscc_code lub item_id.'}), 400

    status_code = 200 if success else 400
    return jsonify({
        'success': success,
        'message': message,
        'data': item_data
    }), status_code


@warehouse_v2_bp.route('/api/orders/picking/<order_ref>/cancel', methods=['POST'])
def api_orders_picking_cancel(order_ref):
    """Cancels all pending items in a picking order."""
    success, message = _picking_service.cancel_picking_order(order_ref)

    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': message}), status_code


@warehouse_v2_bp.route('/api/orders/picking/<order_ref>/delete', methods=['POST', 'DELETE'])
@warehouse_v2_bp.route('/api/orders/picking/delete', methods=['POST', 'DELETE'])
def api_orders_picking_delete(order_ref=None):
    """Trwale usuwa dyspozycję kompletacji (wymaga ról: masteradmin, admin, zarząd)."""
    user_role = str(session.get('rola') or session.get('role') or session.get('login') or '').lower().replace(' ', '').replace('_', '').strip()

    if not order_ref:
        data = request.get_json(silent=True) or {}
        order_ref = data.get('order_ref') or request.args.get('order_ref')

    if not order_ref:
        return jsonify({'success': False, 'message': 'Brak wymaganego parametru order_ref.'}), 400

    success, message = _picking_service.delete_picking_order(str(order_ref).strip(), user_role)

    status_code = 200 if success else 403 if 'Brak uprawnień' in message else 400
    return jsonify({'success': success, 'message': message}), status_code


