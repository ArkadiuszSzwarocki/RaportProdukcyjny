from app.blueprints.routes_api_attendance_admin import register_api_attendance_admin_routes
from app.blueprints.routes_api_plan_ops import register_api_plan_ops_routes
from app.blueprints.routes_api_plan_validation import register_api_plan_validation_routes
from app.blueprints.routes_api_products import register_api_product_routes
from app.blueprints.routes_api_runtime import register_api_runtime_routes
from flask import Blueprint, jsonify, request
from app.services.agro_warehouse_service import AgroWarehouseService

api_bp = Blueprint('api', __name__)
register_api_runtime_routes(api_bp)
register_api_product_routes(api_bp)
register_api_attendance_admin_routes(api_bp)
register_api_plan_validation_routes(api_bp)
register_api_plan_ops_routes(api_bp)

@api_bp.route('/raport-zbiorczy/<int:zasyp_id>', methods=['GET'])
def get_raport_zbiorczy(zasyp_id):
    linia = request.args.get('linia', 'AGRO')
    raport = AgroWarehouseService.get_collective_order_report(zasyp_id, linia=linia)
    
    if not raport:
        return jsonify({"success": False, "message": "Nie znaleziono zlecenia"}), 404
        
    return jsonify({"success": True, "raport": raport})
