from flask import Blueprint, jsonify, request, session
from app.services.production_bom_variance_service import ProductionBomVarianceService
from app.decorators import login_required

def register_api_production_variance_routes(bp: Blueprint):
    """Register endpoints for production recipe BOM variance monitoring."""

    @bp.route('/api/production/plan/<int:plan_id>/variances', methods=['GET'])
    @login_required
    def get_plan_variances(plan_id: int):
        linia = request.args.get('linia', 'PSD').upper()
        summary = ProductionBomVarianceService.get_plan_variance_summary(plan_id=plan_id, linia=linia)
        return jsonify({
            'success': True,
            'data': summary
        })

    @bp.route('/api/production/plan/<int:plan_id>/variance', methods=['POST'])
    @login_required
    def record_plan_variance(plan_id: int):
        payload = request.get_json(silent=True) or {}
        linia = str(payload.get('linia', 'PSD')).upper()
        kod_produktu = str(payload.get('kod_produktu', '')).strip()
        skladnik = str(payload.get('skladnik', '')).strip()
        waga_recepturowa = float(payload.get('waga_recepturowa', 0.0))
        waga_rzeczywista = float(payload.get('waga_rzeczywista', 0.0))
        tolerancja_procent = payload.get('tolerancja_procent')
        if tolerancja_procent is not None:
            tolerancja_procent = float(tolerancja_procent)
        is_micro = bool(payload.get('is_micro_ingredient', False))
        user_login = session.get('user', 'system')

        if not skladnik:
            return jsonify({'success': False, 'message': 'Brak nazwy składnika.'}), 400

        result = ProductionBomVarianceService.calculate_and_record_variance(
            plan_id=plan_id,
            linia=linia,
            kod_produktu=kod_produktu,
            skladnik=skladnik,
            waga_recepturowa=waga_recepturowa,
            waga_rzeczywista=waga_rzeczywista,
            tolerancja_procent=tolerancja_procent,
            is_micro_ingredient=is_micro,
            user_login=user_login
        )

        return jsonify({
            'success': True,
            'message': 'Odchyłka składnika została zarejestrowana.',
            'data': result
        })
