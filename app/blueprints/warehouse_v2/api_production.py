from flask import Blueprint, jsonify, request, session
from app.db import get_db_connection, get_table_name
from .blueprint import warehouse_v2_bp

@warehouse_v2_bp.route('/api/production/stations', methods=['GET'])
def get_production_stations():
    """Pobiera stan 24 stanowisk produkcyjnych Agro."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Pobierz stanowiska i dołącz nazwę surowca jeśli paleta jest przypisana
        cursor.execute("""
            SELECT s.id, s.nazwa as hardwareName, s.typ, s.current_pallet_id, s.updated_at,
                   ms.nazwa as productName, ms.nr_palety, ms.stan_magazynowy as amount, ms.nr_partii as batch
            FROM agro_stanowiska s
            LEFT JOIN magazyn_surowce ms ON s.current_pallet_id = ms.id
            ORDER BY s.id ASC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        # Mapowanie hardware name (BB1-18, ZB1-6) na logiczne numery 1-24
        # BB1-6 -> 1-6
        # ZB1-4 -> 7-10
        # BB7-18 -> 11-22
        # ZB5-6 -> 23-24
        
        def get_logical_nr(hw_name):
            hw_name = hw_name.upper()
            if hw_name.startswith('BB'):
                num = int(hw_name[2:])
                if num <= 6: return num
                else: return num + 4 # BB7 becomes 11, BB18 becomes 22
            elif hw_name.startswith('ZB'):
                num = int(hw_name[2:])
                if num <= 4: return num + 6 # ZB1 becomes 7, ZB4 becomes 10
                else: return num + 18 # ZB5 becomes 23, ZB6 becomes 24
            return 99
            
        stations = []
        for r in rows:
            logical_nr = get_logical_nr(r['hardwareName'])
            if logical_nr > 24: continue
            
            stations.append({
                'nr': logical_nr,
                'hw': r['hardwareName'],
                'type': 'bigbag' if r['hardwareName'].startswith('BB') else 'manual',
                'product': r['productName'] or 'PUSTE',
                'pallet': r['nr_palety'] or '-',
                'amount': r['amount'] or 0,
                'batch': r['batch'] or '-',
                'updated': r['updated_at'].strftime('%H:%M') if r['updated_at'] else '-'
            })
            
        # Sortuj według numeru logicznego
        stations.sort(key=lambda x: x['nr'])
        
        return jsonify({'success': True, 'stations': stations})
    except Exception as e:
        if conn: conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500

@warehouse_v2_bp.route('/historia-stacji/data')
def get_station_history():
    from app.services.warehouse_history_service import WarehouseHistoryService
    linia = (request.args.get('linia') or 'ALL').upper()
    data_od = request.args.get('dataOd')
    data_do = request.args.get('dataDo')
    surowiec = request.args.get('surowiec')
    stacja = request.args.get('stacja')
    
    data = WarehouseHistoryService.get_unified_station_and_movement_history(
        linia=linia,
        data_od=data_od,
        data_do=data_do,
        surowiec=surowiec,
        stacja=stacja,
        limit=500
    )
    return jsonify({'success': True, 'data': data})

