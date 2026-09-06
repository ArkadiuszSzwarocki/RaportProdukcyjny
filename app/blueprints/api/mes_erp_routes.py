from flask import Blueprint, jsonify, request, session
from app.services.oee_service import OeeService
from app.services.lab_quality_service import LabQualityService
from app.services.safety_stock_service import SafetyStockService
from app.decorators import login_required

def register_api_mes_erp_routes(bp: Blueprint):
    """
    Register REST API endpoints for:
    - Real-time OEE metrics
    - Quality Control: Blokada LAB & QA Releases
    - Safety Stock & Reorder Points
    """

    # --- 1. OEE REAL-TIME ---
    @bp.route('/api/production/oee/realtime', methods=['GET'])
    @login_required
    def get_realtime_oee():
        target_date = request.args.get('date')
        linia = request.args.get('linia', 'PSD').upper()
        res = OeeService.calculate_realtime_oee(target_date=target_date, linia=linia)
        return jsonify({
            'success': True,
            'data': res
        })

    # --- 2. BLOKADA LAB & QA RELEASES ---
    @bp.route('/api/lab/block', methods=['POST'])
    @login_required
    def block_pallet_lab():
        payload = request.get_json(silent=True) or {}
        pallet_id = int(payload.get('pallet_id', 0))
        pallet_code = str(payload.get('pallet_code', '')).strip()
        pallet_type = str(payload.get('pallet_type', 'surowiec')).strip()
        linia = str(payload.get('linia', 'PSD')).strip()
        reason = str(payload.get('reason', '')).strip()
        user_login = session.get('user', 'system')

        if not pallet_code:
            return jsonify({'success': False, 'message': 'Brak kodu palety.'}), 400

        res = LabQualityService.block_pallet_by_lab(
            pallet_id=pallet_id,
            pallet_code=pallet_code,
            pallet_type=pallet_type,
            linia=linia,
            reason=reason,
            user_login=user_login
        )
        return jsonify(res)

    @bp.route('/api/lab/release', methods=['POST'])
    @login_required
    def release_pallet_lab():
        payload = request.get_json(silent=True) or {}
        pallet_code = str(payload.get('pallet_code', '')).strip()
        pallet_type = str(payload.get('pallet_type', 'surowiec')).strip()
        linia = str(payload.get('linia', 'PSD')).strip()
        comment = str(payload.get('comment', '')).strip()
        user_login = session.get('user', 'system')

        if not pallet_code:
            return jsonify({'success': False, 'message': 'Brak kodu palety.'}), 400

        res = LabQualityService.release_pallet_by_lab(
            pallet_code=pallet_code,
            pallet_type=pallet_type,
            linia=linia,
            user_login=user_login,
            comment=comment
        )
        return jsonify(res)

    @bp.route('/api/lab/active-blocks', methods=['GET'])
    @login_required
    def get_active_lab_blocks():
        linia = request.args.get('linia')
        blocks = LabQualityService.get_all_active_blocks(linia=linia)
        return jsonify({
            'success': True,
            'count': len(blocks),
            'data': blocks
        })

    @bp.route('/api/lab/check/<string:pallet_code>', methods=['GET'])
    @login_required
    def check_pallet_lab(pallet_code: str):
        res = LabQualityService.check_pallet_lab_status(pallet_code=pallet_code)
        return jsonify({
            'success': True,
            'data': res
        })

    # --- 3. SAFETY STOCK & REORDER POINTS ---
    @bp.route('/api/warehouse/safety-stock/status', methods=['GET'])
    @login_required
    def get_safety_stock_status():
        linia = request.args.get('linia')
        res = SafetyStockService.evaluate_safety_stock_levels(linia=linia)
        return jsonify({
            'success': True,
            'data': res
        })

    @bp.route('/api/warehouse/safety-stock/configure', methods=['POST'])
    @login_required
    def configure_safety_stock():
        payload = request.get_json(silent=True) or {}
        kod_pozycji = str(payload.get('kod_pozycji', '')).strip()
        nazwa = str(payload.get('nazwa', '')).strip()
        typ = str(payload.get('typ', 'surowiec')).strip()
        linia = str(payload.get('linia', 'PSD')).strip()
        stan_minimalny = float(payload.get('stan_minimalny', 0.0))
        punkt_zamowienia = float(payload.get('punkt_zamowienia', 0.0))
        jednostka = str(payload.get('jednostka', 'kg')).strip()
        czas_dostawy_dni = int(payload.get('czas_dostawy_dni', 7))

        if not kod_pozycji or not nazwa:
            return jsonify({'success': False, 'message': 'Brak kodu lub nazwy pozycji.'}), 400

        res = SafetyStockService.configure_threshold(
            kod_pozycji=kod_pozycji,
            nazwa=nazwa,
            typ=typ,
            linia=linia,
            stan_minimalny=stan_minimalny,
            punkt_zamowienia=punkt_zamowienia,
            jednostka=jednostka,
            czas_dostawy_dni=czas_dostawy_dni
        )
        return jsonify(res)
