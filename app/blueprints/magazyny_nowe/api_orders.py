"""
API endpointy zamówień magazynowych.

Endpointy:
- GET  /api/orders           — lista zamówień (filtr ?status=NOWE)
- GET  /api/orders/surowce   — lista surowców ze słownika
- POST /api/orders/create    — tworzenie zamówienia
- POST /api/orders/<id>/confirm — potwierdzenie odczytania
"""
from flask import jsonify, request, session
from app.services.warehouse_order_service import WarehouseOrderService
from .blueprint import magazyny_nowe_bp

_order_service = WarehouseOrderService()


@magazyny_nowe_bp.route('/api/orders', methods=['GET'])
def api_orders_list():
    """Zwraca listę zamówień z opcjonalnym filtrem statusu."""
    status_filter = request.args.get('status')
    orders = _order_service.get_all_orders(status_filter)
    return jsonify({'success': True, 'orders': orders})


@magazyny_nowe_bp.route('/api/orders/surowce', methods=['GET'])
def api_orders_surowce():
    """Zwraca listę surowców ze słownika do formularza zamówienia."""
    surowce = _order_service.get_available_surowce()
    return jsonify({'success': True, 'surowce': surowce})


@magazyny_nowe_bp.route('/api/orders/create', methods=['POST'])
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


@magazyny_nowe_bp.route('/api/orders/<int:order_id>/confirm', methods=['POST'])
def api_orders_confirm(order_id):
    """Potwierdza odczytanie zamówienia przez magazyniera."""
    magazynier_login = session.get('login', 'nieznany')

    success, message = _order_service.confirm_order(order_id, magazynier_login)

    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': message}), status_code

@magazyny_nowe_bp.route('/api/orders/check_stock', methods=['POST'])
def api_orders_check_stock():
    """Kalkulator: przelicza zapotrzebowanie na surowce i weryfikuje stany magazynowe (bez zapisywania)."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Brak danych wejściowych.'}), 400

    items = data.get('items', [])
    order_tons = data.get('order_tons', 0)
    linia = request.args.get('linia') or session.get('grupa') or 'AGRO'
    if linia.upper() not in ['AGRO', 'PSD']:
        linia = 'AGRO'

    success, message, results = _order_service.calculate_and_check_stock(items, order_tons, linia.upper())

    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': message, 'results': results}), status_code

