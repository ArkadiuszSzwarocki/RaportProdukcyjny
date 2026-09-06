"""
API Routes for 3D Warehouse Visualization.
Provides endpoints for retrieving rack structures, slot states, and 3D pallet payloads.
"""
from flask import Blueprint, jsonify, request
from app.services.warehouse_3d_service import Warehouse3dService

def register_api_warehouse_3d_routes(bp: Blueprint):
    """Register 3D warehouse API endpoints."""

    @bp.route('/warehouse/3d/state', methods=['GET'])
    def get_warehouse_3d_state():
        """Returns the full 3D layout, rack configurations, slots, and stored pallets."""
        linia = str(request.args.get('linia', 'ALL') or 'ALL').upper()
        rack_id = request.args.get('rack_id')
        try:
            data = Warehouse3dService.get_warehouse_3d_state(linia=linia, rack_filter=rack_id)
            return jsonify(data)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/warehouse/3d/racks-config', methods=['GET'])
    def get_warehouse_racks_config():
        """Returns rack dimensions and structural configurations."""
        try:
            configs = Warehouse3dService.get_rack_configurations()
            return jsonify({'success': True, 'racks': configs})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
