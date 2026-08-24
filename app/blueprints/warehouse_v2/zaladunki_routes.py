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
    worker_login = session.get('username') or session.get('login') or 'Magazynier'
    raw_history = dispatch_service.get_dispatches_history(limit=200, linia=linia)
    history_grouped = dispatch_service.group_dispatches_by_wz(raw_history)
    return render_template(
        'warehouse_v2/zaladunki.html',
        linia=linia,
        worker_login=worker_login,
        history=raw_history,
        history_grouped=history_grouped
    )


@warehouse_v2_bp.route('/api/zaladunki/lookup-pallet', methods=['GET', 'POST'])
@warehouse_v2_bp.route('/api/zaladunki/lookup_pallet', methods=['GET', 'POST'])
@login_required
def api_lookup_pallet():
    """API do wyszukiwania palety do załadunku po kodzie kreskowym, SSCC lub ID."""
    payload = request.get_json(silent=True) or {}
    code = (payload.get('code') or request.args.get('code') or '').strip()
    linia = (payload.get('linia') or request.args.get('linia') or 'AGRO').upper()

    if not code:
        return jsonify({'success': False, 'message': 'Nie podano kodu palety do zeskanowania.'}), 400

    pallet = dispatch_service.lookup_pallet_for_dispatch(code, preferred_line=linia)
    if not pallet:
        return jsonify({
            'success': False,
            'message': f'Nie znaleziono aktywnej palety dla kodu: "{code}". Paleta mogła zostać już wydana lub zarchiwizowana.'
        }), 404

    return jsonify({
        'success': True,
        'pallet': pallet
    })


@warehouse_v2_bp.route('/api/zaladunki/dispatch', methods=['POST'])
@login_required
def api_dispatch_vehicle():
    """API do rejestracji wydania zewnętrznego palety na samochód."""
    payload = request.get_json() or {}
    magazynier_login = session.get('username') or session.get('login') or 'Magazynier'
    success, message = dispatch_service.dispatch_pallet_to_vehicle(payload, magazynier_login)
    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': message}), status_code


@warehouse_v2_bp.route('/api/zaladunki/history', methods=['GET'])
@login_required
def api_dispatch_history():
    """API do pobierania aktualnej historii wydań zewnętrznych."""
    raw_history = dispatch_service.get_dispatches_history(limit=200)
    history_grouped = dispatch_service.group_dispatches_by_wz(raw_history)
    return jsonify({'success': True, 'history': raw_history, 'grouped': history_grouped})
