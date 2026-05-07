from flask import Blueprint, render_template, request
from app.db import get_db_connection, get_table_name

magazyny_nowe_bp = Blueprint('magazyny_nowe', __name__, url_prefix='/magazyny-nowe')

@magazyny_nowe_bp.route('/')
def index():
    linia = request.args.get('linia', 'PSD').upper()
    conn = get_db_connection()
    items = []
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 1. Surowce
        table_surowce = get_table_name('magazyn_surowce', linia)
        try:
            cursor.execute(f"SELECT id, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Surowiec' as type, '' as date FROM {table_surowce} WHERE stan_magazynowy > 0")
            surowce = cursor.fetchall()
            for row in surowce:
                row['displayId'] = f"SUR-{row['id']}"
                items.append(row)
        except Exception as e:
            print(f"Error fetching surowce: {e}")

        # 2. Opakowania
        table_opakowania = get_table_name('magazyn_opakowania', linia)
        try:
            cursor.execute(f"SELECT id, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Opakowanie' as type, created_at as date FROM {table_opakowania} WHERE stan_magazynowy > 0")
            opakowania = cursor.fetchall()
            for row in opakowania:
                row['displayId'] = f"OPK-{row['id']}"
                if row['date']:
                    row['date'] = row['date'].strftime('%Y-%m-%d')
                items.append(row)
        except Exception as e:
            print(f"Error fetching opakowania: {e}")

        # 3. Wyroby Gotowe
        table_palety = get_table_name('magazyn_palety', linia)
        try:
            cursor.execute(f"SELECT id, produkt as productName, '' as location, waga_netto as amount, 'Wyrób Gotowy' as type, data_potwierdzenia as date FROM {table_palety} WHERE waga_netto > 0")
            palety = cursor.fetchall()
            for row in palety:
                row['displayId'] = f"PAL-{row['id']}"
                if row['date']:
                    row['date'] = row['date'].strftime('%Y-%m-%d')
                
                # Przypisz lokalizację MGW01 dla wyrobów gotowych jeśli nie mają
                if not row['location']:
                    row['location'] = 'MGW01'
                
                items.append(row)
        except Exception as e:
            print(f"Error fetching wyroby gotowe: {e}")

    finally:
        conn.close()

    # Struktura magazynów z Mlecznej Drogi
    magazyny_zakladki = [
        {'id': 'all', 'name': 'Wszystkie Magazyny'},
        {'id': 'MS01', 'name': 'Magazyn Główny (MS01)'},
        {'id': 'MP01', 'name': 'Magazyn Pomocniczy (MP01)'},
        {'id': 'MGW01', 'name': 'Wyroby Gotowe (MGW01)'},
        {'id': 'MOP01', 'name': 'Opakowania (MOP01)'},
        {'id': 'OSIP', 'name': 'OSiP / Odpady'}
    ]

    return render_template('magazyny_nowe/dashboard.html', items=items, linia=linia, zakladki=magazyny_zakladki, aktywna_zakladka='all')

from flask import jsonify, session
from app.services.magazyny_nowe_service import MagazynyNoweService

@magazyny_nowe_bp.route('/api/pallet/history', methods=['GET'])
def get_history():
    pallet_id = request.args.get('id')
    pallet_type = request.args.get('type')
    linia = request.args.get('linia', 'PSD')
    
    if not pallet_id or not pallet_type:
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    history = MagazynyNoweService.get_pallet_history(pallet_id, pallet_type, linia)
    return jsonify({'success': True, 'history': history})

@magazyny_nowe_bp.route('/api/pallet/move', methods=['POST'])
def move_pallet():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    new_location = data.get('location')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type, new_location]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.move_pallet(pallet_id, pallet_type, new_location, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/archive', methods=['POST'])
def archive_pallet():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.archive_pallet(pallet_id, pallet_type, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/rename', methods=['POST'])
def rename_pallet():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    new_name = data.get('name')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type, new_name]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.rename_pallet(pallet_id, pallet_type, new_name, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/update-weight', methods=['POST'])
def update_weight():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    new_weight = data.get('weight')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type, new_weight is not None]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.update_weight(pallet_id, pallet_type, new_weight, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/return-to-raw', methods=['POST'])
def pallet_return_to_raw():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.return_pallet_to_raw(pallet_id, pallet_type, worker, linia)
    return jsonify({'success': success, 'message': msg})
