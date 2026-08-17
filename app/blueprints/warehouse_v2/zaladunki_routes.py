"""
Kontroler i trasy dla Wydań Zewnętrznych na Samochód (Załadunki ZZA/ZZL).

Odpowiedzialność: Punkty końcowe HTTP widoku załadunku pojazdów oraz API rejestracji wyjazdu.
"""

from flask import render_template, request, jsonify, session
from app.blueprints.warehouse_v2.blueprint import warehouse_v2_bp
from app.services.warehouse_dispatch_service import WarehouseDispatchService
from app.decorators import login_required

dispatch_service = WarehouseDispatchService()


@warehouse_v2_bp.route('/zaladunki', methods=['GET'])
@login_required
def zaladunki_view():
    """Dedykowany widok Wydań Zewnętrznych na Samochód (Załadunki ZZA/ZZL)."""
    linia = request.args.get('linia', 'AGRO').upper()
    available_pallets = dispatch_service.get_available_pallets()
    history = dispatch_service.get_dispatches_history(limit=50)
    return render_template(
        'warehouse_v2/zaladunki.html',
        linia=linia,
        available_pallets=available_pallets,
        history=history
    )


@warehouse_v2_bp.route('/api/zaladunki/dispatch', methods=['POST'])
@login_required
def api_dispatch_vehicle():
    """API do rejestracji wydania zewnętrznego palety na samochód."""
    payload = request.get_json() or {}
    magazynier_login = session.get('login', 'Magazynier')
    success, message = dispatch_service.dispatch_pallet_to_vehicle(payload, magazynier_login)
    return jsonify({'success': success, 'message': message})
