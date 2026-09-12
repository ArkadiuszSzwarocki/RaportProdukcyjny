import sys
from flask import jsonify, request, session
from app.services.warehouse_v2_service import WarehouseV2Service

class PalletMutationController:
    @staticmethod
    def update_packaging():
        """Update packaging type for a pallet."""
        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        new_packaging = data.get('packaging_type')
        linia = data.get('linia', 'PSD')
        worker = session.get('login', 'nieznany')
        
        if not all([pallet_id, pallet_type, new_packaging]):
            return jsonify({'success': False, 'error': 'Brak parametrów (id, type, packaging_type)'}), 400
            
        success, msg = WarehouseV2Service.update_packaging_type(pallet_id, pallet_type, new_packaging, worker, linia)
        return jsonify({'success': success, 'message': msg})

    @staticmethod
    def update_material_type():
        """Update material type category."""
        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        new_material_type = data.get('material_type')
        linia = data.get('linia', 'PSD')
        worker = session.get('login', 'nieznany')
        
        print(f"[UPDATE-MATERIAL-TYPE] ID={pallet_id}, Type={pallet_type}, NewMaterial={new_material_type}, Linia={linia}, Worker={worker}", file=sys.stderr)
        
        if not all([pallet_id, pallet_type, new_material_type]):
            return jsonify({'success': False, 'error': 'Brak parametrów (id, type, material_type)'}), 400
        
        if pallet_type not in ('Opakowanie', 'Surowiec'):
            return jsonify({'success': False, 'error': 'Zmiana typu materiału dostępna tylko dla opakowań i surowców'}), 400
        
        success, msg = WarehouseV2Service.update_material_type(pallet_id, pallet_type, new_material_type, worker, linia)
        print(f"[UPDATE-MATERIAL-TYPE] Result: success={success}, msg={msg}", file=sys.stderr)
        return jsonify({'success': success, 'message': msg})

    @staticmethod
    def bulk_update_material_type():
        """Bulk update material types for multiple packaging items."""
        data = request.get_json() or {}
        pallet_ids = data.get('ids', [])
        new_material_type = data.get('material_type')
        pallet_type = data.get('type', 'Opakowanie')
        linia = data.get('linia', 'PSD')
        worker = session.get('login', 'nieznany')
        
        if not pallet_ids or not new_material_type:
            return jsonify({'success': False, 'error': 'Brak parametrów (ids, material_type)'}), 400
        
        if new_material_type not in ('Karton', 'Taśma'):
            return jsonify({'success': False, 'error': 'Błędny typ materiału. Wybierz Karton lub Taśma'}), 400
        
        if pallet_type not in ('Opakowanie', 'Surowiec'):
            return jsonify({'success': False, 'error': 'Zmiana typu materiału dostępna tylko dla opakowań i surowców'}), 400
        
        success, msg, count = WarehouseV2Service.bulk_update_material_type(pallet_ids, pallet_type, new_material_type, worker, linia)
        return jsonify({'success': success, 'message': msg, 'updated_count': count})

    @staticmethod
    def archive_pallet():
        """Archive pallet from active warehouse."""
        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        linia = data.get('linia', 'PSD')
        worker = session.get('login', 'nieznany')
        
        if not all([pallet_id, pallet_type]):
            return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
            
        success, msg = WarehouseV2Service.archive_pallet(pallet_id, pallet_type, worker, linia)
        return jsonify({'success': success, 'message': msg})

    @staticmethod
    def dispatch_pallet():
        """Dispatch pallet to EXPEDITION."""
        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        linia = data.get('linia', 'PSD')
        worker = session.get('login', 'nieznany')
        
        if not all([pallet_id, pallet_type]):
            return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
            
        success, msg = WarehouseV2Service.dispatch_pallet(pallet_id, pallet_type, worker, linia)
        return jsonify({'success': success, 'message': msg})

    @staticmethod
    def rename_pallet():
        """Rename product on a pallet."""
        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        new_name = data.get('name')
        linia = data.get('linia', 'PSD')
        worker = session.get('login', 'nieznany')
        
        if not all([pallet_id, pallet_type, new_name]):
            return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
            
        success, msg = WarehouseV2Service.rename_pallet(pallet_id, pallet_type, new_name, worker, linia)
        return jsonify({'success': success, 'message': msg})

    @staticmethod
    def update_weight():
        """Update weight or count on a pallet."""
        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        new_weight = data.get('weight')
        linia = data.get('linia', 'PSD')
        worker = session.get('login', 'nieznany')
        
        if not all([pallet_id, pallet_type, new_weight is not None]):
            return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
            
        success, msg = WarehouseV2Service.update_weight(pallet_id, pallet_type, new_weight, worker, linia)
        return jsonify({'success': success, 'message': msg})

    @staticmethod
    def toggle_block():
        """Toggle pallet quality lock/block."""
        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        linia = data.get('linia', 'PSD')
        worker = session.get('login', 'nieznany')
        
        if not all([pallet_id, pallet_type]):
            return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
            
        success, msg = WarehouseV2Service.toggle_block(pallet_id, pallet_type, worker, linia)
        return jsonify({'success': success, 'message': msg})

    @staticmethod
    def pallet_return_to_raw():
        """Return finished goods to raw materials buffer."""
        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        linia = data.get('linia', 'PSD')
        worker = session.get('login', 'nieznany')
        
        if not all([pallet_id, pallet_type]):
            return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
            
        success, msg = WarehouseV2Service.return_pallet_to_raw(pallet_id, pallet_type, worker, linia)
        return jsonify({'success': success, 'message': msg})

    @staticmethod
    def restore_from_archive(archive_id):
        """Restore pallet from archive back to active stock."""
        user_role = str(session.get('rola') or session.get('role') or '').lower().strip()
        if user_role not in ['masteradmin', 'lider', 'admin', 'zarzad']:
            return jsonify({
                'success': False, 
                'error': 'Brak uprawnień. Tylko MasterAdmin i Liderzy mogą przywracać zużyte palety.'
            }), 403

        try:
            data = request.json or {}
            new_weight = data.get('waga')
            new_location = data.get('lokalizacja')
            user_login = session.get('login', 'admin')

            ok, msg, restored_info = WarehouseV2Service.restore_pallet_from_archive(
                archive_id=archive_id,
                new_weight=new_weight,
                new_location=new_location,
                user_login=user_login
            )

            if not ok:
                return jsonify({'success': False, 'error': msg}), 400

            return jsonify({
                'success': True,
                'message': msg,
                'pallet': restored_info
            })
        except Exception as e:
            print(f"Error restoring pallet: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
