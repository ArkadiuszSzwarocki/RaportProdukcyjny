from flask import jsonify, request, session
from app.services.warehouse_v2_service import WarehouseV2Service

class PalletRelocationController:
    @staticmethod
    def move_pallet():
        """Handle pallet relocation or split movement command."""
        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        new_location = data.get('location')
        linia = data.get('linia', 'PSD')
        amount = data.get('amount')
        worker = session.get('login', 'nieznany')
        
        if not all([pallet_id, pallet_type, new_location]):
            return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
            
        res = WarehouseV2Service.move_pallet(pallet_id, pallet_type, new_location, worker, linia, amount_to_move=amount)
        if isinstance(res, tuple) and len(res) == 3:
            success, msg, split_info = res
        else:
            success, msg = res[0], res[1]
            split_info = None
        return jsonify({'success': success, 'message': msg, 'split_info': split_info})
