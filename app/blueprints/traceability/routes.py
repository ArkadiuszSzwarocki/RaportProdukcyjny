from flask import render_template, request, jsonify
from . import traceability_bp
from app.services.traceability_service import TraceabilityService

@traceability_bp.route('/traceability', methods=['GET'])
def index():
    return render_template('traceability/index.html')

@traceability_bp.route('/api/traceability/search', methods=['GET'])
def search():
    query = request.args.get('q', '').strip()
    search_type = request.args.get('type', 'auto') # 'auto', 'pallet', 'lot'
    
    if not query:
        return jsonify({"error": "Puste zapytanie"}), 400
        
    result = None
    
    # Simple heuristic if type is auto
    if search_type == 'auto':
        if query.startswith('PSD') or query.startswith('AGR') or len(query) >= 15:
            search_type = 'pallet'
        elif 'LOT' in query.upper():
            search_type = 'lot'
        else:
            # Try pallet first, if error try lot
            search_type = 'pallet_then_lot'
            
    if search_type == 'pallet':
        result = TraceabilityService.get_pallet_trace(query)
    elif search_type == 'lot':
        result = TraceabilityService.get_lot_trace(query)
    elif search_type == 'pallet_then_lot':
        result = TraceabilityService.get_pallet_trace(query)
        if "error" in result:
            result = TraceabilityService.get_lot_trace(query)
            result['search_type'] = 'lot'
        else:
            result['search_type'] = 'pallet'
            
    return jsonify(result)
