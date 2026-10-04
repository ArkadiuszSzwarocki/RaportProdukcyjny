"""
API endpointy zamówień magazynowych i kompletacji (Picking).
"""
from flask import jsonify, request, session

from app.services.warehouse_order_service import WarehouseOrderService
from app.services.picking_service import PickingService
from .blueprint import warehouse_v2_bp

_order_service = WarehouseOrderService()
_picking_service = PickingService()


def _resolve_line():
    linia = str(request.args.get('linia') or session.get('grupa') or 'AGRO').upper()
    return linia if linia in ('AGRO', 'PSD') else 'AGRO'


@warehouse_v2_bp.route('/api/orders', methods=['GET'])
def api_orders_list():
    status_filter = request.args.get('status')
    orders = _order_service.get_all_orders(status_filter)
    return jsonify({'success': True, 'orders': orders})


@warehouse_v2_bp.route('/api/sidebar-badges', methods=['GET'])
def api_sidebar_badges():
    from app.core.contexts import (_fetch_delivery_counters, _fetch_osip_transfers_count,
                                   inject_delivery_counters, inject_osip_transfers_count)
    orders_nowe = 0
    active_picking = 0
    try:
        orders_nowe = len(_order_service.get_all_orders('NOWE'))
    except Exception:
        pass
    try:
        active_picking = len(_picking_service.get_active_orders())
    except Exception:
        pass
    fresh = request.args.get('fresh') == '1'
    counters = (_fetch_delivery_counters() if fresh else inject_delivery_counters())
    transfers = (_fetch_osip_transfers_count() if fresh else inject_osip_transfers_count())
    return jsonify({
        'success': True,
        'orders_nowe': orders_nowe,
        'active_picking': active_picking,
        **counters,
        **transfers,
    })


@warehouse_v2_bp.route('/api/orders/surowce', methods=['GET'])
def api_orders_surowce():
    surowce = _order_service.get_available_surowce()
    return jsonify({'success': True, 'surowce': surowce})


@warehouse_v2_bp.route('/api/orders/create', methods=['POST'])
def api_orders_create():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'success': False, 'error': 'Brak danych wejściowych.'}), 400

    success, message, order_id = _order_service.create_order(
        items=data.get('items', []),
        operator_login=session.get('login', 'nieznany'),
        komentarz=data.get('komentarz', ''),
        linia=_resolve_line(),
    )

    response = {'success': success, 'message': message}
    if order_id:
        response['order_id'] = order_id
    return jsonify(response), 201 if success else 400


@warehouse_v2_bp.route('/api/orders/<int:order_id>/confirm', methods=['POST'])
def api_orders_confirm(order_id):
    success, message = _order_service.confirm_order(
        order_id,
        session.get('login', 'nieznany'),
    )
    return jsonify({'success': success, 'message': message}), 200 if success else 400


@warehouse_v2_bp.route('/api/orders/<int:order_id>/delete', methods=['POST', 'DELETE'])
@warehouse_v2_bp.route('/api/orders/delete', methods=['POST', 'DELETE'])
def api_orders_delete(order_id=None):
    user_role = str(
        session.get('rola') or session.get('role') or session.get('login') or ''
    ).lower().replace(' ', '').replace('_', '').strip()

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
    """Przelicza recepturę i pokazuje aktualnie dostępne palety bez zapisywania."""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'success': False, 'message': 'Brak danych wejściowych.', 'results': []}), 400

    linia = _resolve_line()
    success, message, payload = _order_service.calculate_and_check_stock(
        data.get('items', []),
        data.get('order_tons', 0),
        linia,
    )
    if not success:
        return jsonify({'success': False, 'message': message, 'results': []}), 400

    return jsonify({
        'success': True,
        'message': message,
        'results': payload.get('items', []),
        'scanned_zones': payload.get('scanned_zones', []),
        'order_tons': payload.get('order_tons', data.get('order_tons', 0)),
        'linia': linia,
    }), 200


# ───────────────────────────────────────────────
# PICKING / COMPLETION ENDPOINTS
# ───────────────────────────────────────────────

@warehouse_v2_bp.route('/api/orders/start-picking', methods=['POST'])
def api_orders_start_picking():
    """Tworzy kompletację po ponownym serwerowym sprawdzeniu aktualnego magazynu."""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'success': False, 'message': 'Brak danych wejściowych.'}), 400

    # Linia jest ustalana po stronie serwera. Klient nie decyduje, z jakiej bazy
    # ma zostać wykonana finalna rewalidacja palet.
    data['linia'] = _resolve_line()
    success, message, payload = _picking_service.start_picking(
        data,
        session.get('login', 'nieznany'),
    )
    return jsonify({
        'success': success,
        'message': message,
        'data': payload,
    }), 201 if success else 400


@warehouse_v2_bp.route('/api/orders/picking/active', methods=['GET'])
def api_orders_picking_active():
    operator_login = request.args.get('operator')
    orders = _picking_service.get_active_orders(operator_login or None)
    return jsonify({'success': True, 'data': orders, 'orders': orders})


@warehouse_v2_bp.route('/api/orders/picking/all', methods=['GET'])
def api_orders_picking_all():
    limit = request.args.get('limit', 50, type=int)
    orders = _picking_service.get_all_orders(limit=limit)
    return jsonify({'success': True, 'data': orders, 'orders': orders})


@warehouse_v2_bp.route('/api/orders/picking/<order_ref>', methods=['GET'])
def api_orders_picking_details(order_ref):
    details = _picking_service.get_picking_order_details(order_ref)
    if not details:
        return jsonify({'success': False, 'message': f'Zamówienie {order_ref} nie istnieje.'}), 404
    return jsonify({'success': True, 'data': details})


@warehouse_v2_bp.route('/api/orders/picking/<order_ref>/confirm', methods=['POST'])
def api_orders_picking_confirm(order_ref):
    data = request.get_json(silent=True) or {}
    magazynier_login = session.get('login', 'nieznany')

    sscc_code = str(data.get('sscc_code') or '').strip()
    item_id = data.get('item_id')
    if sscc_code:
        success, message, item_data = _picking_service.confirm_pick_by_sscc(
            order_ref,
            sscc_code,
            magazynier_login,
        )
    elif item_id:
        success, message, item_data = _picking_service.confirm_pick_by_id(
            item_id,
            magazynier_login,
        )
    else:
        return jsonify({'success': False, 'message': 'Podaj sscc_code lub item_id.'}), 400

    return jsonify({
        'success': success,
        'message': message,
        'data': item_data,
    }), 200 if success else 400


@warehouse_v2_bp.route('/api/orders/picking/<order_ref>/cancel', methods=['POST'])
@warehouse_v2_bp.route('/api/orders/picking/cancel', methods=['POST'])
def api_orders_picking_cancel(order_ref=None):
    if not order_ref:
        data = request.get_json(silent=True) or {}
        order_ref = data.get('order_ref') or request.args.get('order_ref')
    if not order_ref:
        return jsonify({'success': False, 'message': 'Brak wymaganego parametru order_ref.'}), 400

    success, message = _picking_service.cancel_picking_order(str(order_ref).strip())
    return jsonify({'success': success, 'message': message}), 200 if success else 400


@warehouse_v2_bp.route('/api/orders/picking/<order_ref>/delete', methods=['POST', 'DELETE'])
@warehouse_v2_bp.route('/api/orders/picking/delete', methods=['POST', 'DELETE'])
def api_orders_picking_delete(order_ref=None):
    user_role = str(
        session.get('rola') or session.get('role') or session.get('login') or ''
    ).lower().replace(' ', '').replace('_', '').strip()

    if not order_ref:
        data = request.get_json(silent=True) or {}
        order_ref = data.get('order_ref') or request.args.get('order_ref')
    if not order_ref:
        return jsonify({'success': False, 'message': 'Brak wymaganego parametru order_ref.'}), 400

    success, message = _picking_service.delete_picking_order(str(order_ref).strip(), user_role)
    status_code = 200 if success else 403 if 'Brak uprawnień' in message else 400
    return jsonify({'success': success, 'message': message}), status_code
