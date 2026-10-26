from datetime import date
from flask import render_template, request, jsonify, session, abort, flash, redirect, url_for
from app.decorators import login_required
from app.services.production_consumption_service import ProductionConsumptionService
from .blueprint import warehouse_v2_bp


def _history_selection():
    role = str(session.get('rola') or session.get('role') or '').lower().replace('_', '').replace(' ', '')
    can_search = role == 'masteradmin'
    raw = request.args.get('data')
    if raw is not None and not can_search:
        abort(403, description='Wyszukiwanie historii według daty jest dostępne tylko dla MasterAdmina.')
    selected = date.today()
    if raw:
        try:
            selected = date.fromisoformat(raw)
            if selected.isoformat() != raw or selected == date.max:
                raise ValueError
        except ValueError:
            raise ValueError('Podaj prawidłową datę w formacie RRRR-MM-DD.') from None
    return selected, can_search


@warehouse_v2_bp.route('/zuzycie', methods=['GET'])
@login_required
def zuzycie_view():
    """Główny widok modułu Zużycie w produkcji."""
    linia = request.args.get('linia', 'PSD').upper()
    worker_login = session.get('login') or session.get('username') or 'Magazynier'
    
    try:
        history_date, can_search_history = _history_selection()
    except ValueError as error:
        flash(str(error), 'danger')
        return redirect(url_for('warehouse_v2.zuzycie_view', linia=linia))
    daily_history = ProductionConsumptionService.get_daily_consumption_history(
        worker_login=worker_login, history_date=history_date, all_workers=can_search_history)

    
    return render_template(
        'warehouse_v2/zuzycie.html',
        linia=linia,
        worker_login=worker_login,
        daily_history=daily_history,
        history_date=history_date.isoformat(),
        can_search_history=can_search_history
    )


@warehouse_v2_bp.route('/api/zuzycie/lookup', methods=['POST'])
@login_required
def api_zuzycie_lookup():
    """Wyszukuje paletę po zeskanowanym kodzie kreskowym, SSCC lub identyfikatorze."""
    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    linia = (data.get('linia') or 'PSD').upper()
    
    if not code:
        return jsonify({'success': False, 'message': 'Nie podano kodu do wyszukania.'}), 400
        
    pallet = ProductionConsumptionService.lookup_pallet_for_consumption(code, preferred_line=linia)
    if not pallet:
        return jsonify({
            'success': False, 
            'message': f'Nie znaleziono aktywnej palety dla kodu: "{code}". Paleta mogła zostać już wcześniej zużyta lub zarchiwizowana.'
        }), 404
        
    return jsonify({
        'success': True,
        'pallet': pallet
    })


@warehouse_v2_bp.route('/api/zuzycie/confirm', methods=['POST'])
@login_required
def api_zuzycie_confirm():
    """Zatwierdza zużycie palety do 0 kg i przenosi ją do archiwum."""
    data = request.get_json() or {}
    pallet_id = data.get('pallet_id')
    pallet_type = data.get('pallet_type')
    linia = (data.get('linia') or 'PSD').upper()
    worker_login = session.get('login') or session.get('username') or 'Magazynier'
    comment = data.get('comment') or 'Zużycie w produkcji (wydozowano do 0 kg)'
    
    if not pallet_id or not pallet_type:
        return jsonify({'success': False, 'message': 'Brak wymaganych parametrów palety (id/typ).'}), 400
        
    try:
        pallet_id = int(pallet_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Nieprawidłowe ID palety.'}), 400

    success, msg, archived_summary = ProductionConsumptionService.consume_and_archive_pallet(
        pallet_id=pallet_id,
        pallet_type=pallet_type,
        linia=linia,
        worker_login=worker_login,
        comment=comment
    )
    
    if not success:
        return jsonify({'success': False, 'message': msg}), 400
        
    return jsonify({
        'success': True,
        'message': msg,
        'archived': archived_summary
    })


@warehouse_v2_bp.route('/api/zuzycie/history', methods=['GET'])
@login_required
def api_zuzycie_history():
    """Return the selected day for MasterAdmin, today for other employees."""
    worker_login = session.get('login') or session.get('username') or 'Magazynier'
    try:
        history_date, can_search_history = _history_selection()
    except ValueError as error:
        return jsonify(success=False, message=str(error)), 400
    history = ProductionConsumptionService.get_daily_consumption_history(
        worker_login=worker_login, history_date=history_date, all_workers=can_search_history)
    return jsonify({
        'success': True,
        'history': history,
        'date': history_date.isoformat()
    })
