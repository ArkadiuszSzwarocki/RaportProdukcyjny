from flask import Blueprint, jsonify, request, session
from app.db import get_db_connection, get_table_name
from .blueprint import magazyny_nowe_bp

@magazyny_nowe_bp.route('/api/production/stations', methods=['GET'])
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

@magazyny_nowe_bp.route('/historia-stacji/data')
def get_station_history():
    linia = request.args.get('linia', 'PSD').upper()
    table_ruch = get_table_name('magazyn_ruch', linia)
    timestamp_col = 'autor_data' if linia == 'AGRO' else 'created_at'
    
    conn = get_db_connection()
    try:
        data_od = request.args.get('dataOd')
        data_do = request.args.get('dataDo')
        surowiec = request.args.get('surowiec')
        stacja = request.args.get('stacja')
        
        cursor = conn.cursor(dictionary=True)
        
        where_clauses = ["r.typ_ruchu = 'PRODUKCJA'"]
        where_params = []
        
        # Obowiązkowy filtr dla stanowisk, chyba że wybrano konkretną stację
        if stacja:
            where_clauses.append("(r.zbiornik LIKE %s OR r.lokalizacja LIKE %s)")
            where_params.extend([f"%{stacja}%", f"%{stacja}%"])
        else:
            where_clauses.append("(r.lokalizacja LIKE 'BB%%' OR r.lokalizacja LIKE 'MZ%%' OR r.lokalizacja LIKE 'WZ%%' OR r.lokalizacja LIKE 'KO%%' OR r.lokalizacja LIKE 'ZB%%' OR r.zbiornik LIKE 'BB%%' OR r.zbiornik LIKE 'MZ%%' OR r.zbiornik LIKE 'WZ%%' OR r.zbiornik LIKE 'KO%%' OR r.zbiornik LIKE 'ZB%%')")

        if data_od:
            where_clauses.append(f"r.{timestamp_col} >= %s")
            where_params.append(f"{data_od} 00:00:00")
        if data_do:
            where_clauses.append(f"r.{timestamp_col} <= %s")
            where_params.append(f"{data_do} 23:59:59")
        if surowiec:
            where_clauses.append("r.surowiec_nazwa LIKE %s")
            where_params.append(f"%{surowiec}%")
            
        where_sql = " AND ".join(where_clauses)
        
        query = f"""
            SELECT 
                r.id, 
                r.surowiec_nazwa, 
                r.typ_ruchu, 
                r.ilosc, 
                r.ilosc_po, 
                r.lokalizacja, 
                r.zbiornik, 
                r.autor_login, 
                r.{timestamp_col} AS created_at, 
                r.komentarz,
                pal.nr_palety
            FROM {table_ruch} r
            LEFT JOIN magazyn_surowce pal ON r.surowiec_id = pal.id
            WHERE {where_sql}
            ORDER BY r.{timestamp_col} DESC
            LIMIT 500
        """
        cursor.execute(query, where_params)
        rows = cursor.fetchall()
        
        data = []
        for r in rows:
            stacja = r.get('zbiornik') or r.get('lokalizacja') or '-'
            data.append({
                'id': r['id'],
                'data': r['created_at'].strftime('%Y-%m-%d %H:%M') if r.get('created_at') else '-',
                'stacja': stacja,
                'nazwa': r.get('surowiec_nazwa') or '-',
                'nr_palety': r.get('nr_palety') or '-',
                'ilosc': float(r.get('ilosc') or 0),
                'typ': r.get('typ_ruchu') or '-',
                'user': r.get('autor_login') or '-',
                'komentarz': r.get('komentarz') or '-'
            })
            
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        print(f"Error fetching station history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

