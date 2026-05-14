from flask import Blueprint, render_template, request
from app.db import get_db_connection, get_table_name

magazyny_nowe_bp = Blueprint('magazyny_nowe', __name__, url_prefix='/magazyny-nowe')

@magazyny_nowe_bp.route('/')
def index():
    linia = request.args.get('linia', 'PSD').upper()
    palety_linie = ['PSD', 'AGRO'] if linia == 'ALL' else [linia]
    shared_linia = linia if linia in ('PSD', 'AGRO') else 'PSD'
    conn = get_db_connection()
    items = []
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 1. Surowce
        table_surowce = get_table_name('magazyn_surowce', linia)
        try:
            cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Surowiec' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked, created_at FROM {table_surowce} WHERE stan_magazynowy > 0")
            surowce = cursor.fetchall()
            for row in surowce:
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"SUR-{row['id']}"
                row['linia'] = shared_linia
                row['date_prod'] = row['data_produkcji'].strftime('%Y-%m-%d') if row['data_produkcji'] else '-'
                row['date_exp'] = row['data_przydatnosci'].strftime('%Y-%m-%d') if row['data_przydatnosci'] else '-'
                row['date_added'] = row['created_at'].strftime('%Y-%m-%d %H:%M') if row.get('created_at') else '-'
                row['batch'] = row.get('nr_partii') or '-'
                row['unit'] = 'kg'
                row['is_blocked'] = row.get('is_blocked', 0)
                items.append(row)
        except Exception as e:
            print(f"Error fetching surowce: {e}")

        # 2. Opakowania
        table_opakowania = get_table_name('magazyn_opakowania', linia)
        try:
            cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Opakowanie' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked, created_at FROM {table_opakowania} WHERE stan_magazynowy > 0")
            opakowania = cursor.fetchall()
            for row in opakowania:
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"OPK-{row['id']}"
                row['linia'] = shared_linia
                row['date_prod'] = row['data_produkcji'].strftime('%Y-%m-%d') if row['data_produkcji'] else '-'
                row['date_exp'] = row['data_przydatnosci'].strftime('%Y-%m-%d') if row['data_przydatnosci'] else '-'
                row['date_added'] = row['created_at'].strftime('%Y-%m-%d %H:%M') if row.get('created_at') else '-'
                row['batch'] = row.get('nr_partii') or '-'
                row['unit'] = 'szt'
                row['is_blocked'] = row.get('is_blocked', 0)
                items.append(row)
        except Exception as e:
            print(f"Error fetching opakowania: {e}")

        # 3. Wyroby Gotowe (dla ALL łączymy PSD + AGRO)
        for linia_palety in palety_linie:
            table_palety = get_table_name('magazyn_palety', linia_palety)
            try:
                try:
                    cursor.execute(
                        f"SELECT id, nr_palety, produkt as productName, lokalizacja as location, waga_netto as amount, 'Wyrób Gotowy' as type, data_produkcji, data_przydatnosci, linia, nr_partii, is_blocked FROM {table_palety} WHERE waga_netto > 0"
                    )
                    palety = cursor.fetchall()
                except Exception:
                    cursor.execute(
                        f"SELECT id, nr_palety, produkt as productName, lokalizacja as location, waga_netto as amount, 'Wyrób Gotowy' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked FROM {table_palety} WHERE waga_netto > 0"
                    )
                    palety = cursor.fetchall()

                for row in palety:
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"PAL-{row['id']}"
                    row['linia'] = (row.get('linia') or linia_palety)
                    row['date_prod'] = row['data_produkcji'].strftime('%Y-%m-%d') if row['data_produkcji'] else '-'
                    row['date_exp'] = row['data_przydatnosci'].strftime('%Y-%m-%d') if row['data_przydatnosci'] else '-'
                    row['date_added'] = row['data_produkcji'].strftime('%Y-%m-%d %H:%M') if row.get('data_produkcji') else '-'
                    row['batch'] = row.get('nr_partii') or '-'
                    row['unit'] = 'kg'
                    row['is_blocked'] = row.get('is_blocked', 0)

                    # Przypisz lokalizację MGW01 dla wyrobów gotowych jeśli nie mają
                    if not row['location']:
                        row['location'] = 'MGW01'

                    items.append(row)
            except Exception as e:
                print(f"Error fetching wyroby gotowe ({linia_palety}): {e}")

        # 4. Dodatki (NEW)
        try:
            cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Dodatek' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked, created_at FROM magazyn_dodatki WHERE stan_magazynowy > 0")
            dodatki = cursor.fetchall()
            for row in dodatki:
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"DOD-{row['id']}"
                row['linia'] = shared_linia
                row['date_prod'] = row['data_produkcji'].strftime('%Y-%m-%d') if row['data_produkcji'] else '-'
                row['date_exp'] = row['data_przydatnosci'].strftime('%Y-%m-%d') if row['data_przydatnosci'] else '-'
                row['date_added'] = row['created_at'].strftime('%Y-%m-%d %H:%M') if row.get('created_at') else '-'
                row['batch'] = row.get('nr_partii') or '-'
                row['unit'] = 'kg'
                row['is_blocked'] = row.get('is_blocked', 0)
                items.append(row)
        except Exception as e:
            print(f"Error fetching dodatki: {e}")

    except Exception as e:
        print(f"Error in dashboard: {e}")

    # Sortowanie: Regał -> Rząd -> Gniazdo
    def get_sort_key(item):
        loc = (item.get('location') or '').strip().upper()
        if loc.startswith('R') and len(loc) >= 7:
            try:
                rack = loc[:3]
                gniazdo = loc[3:5]
                rzad = loc[5:7]
                # Sortujemy: najpierw regał, potem rząd (poziom), potem gniazdo (miejsce)
                return (0, rack, rzad, gniazdo)
            except:
                return (1, loc, '', '')
        return (1, loc, '', '')

    # Usunięto deduplikację na prośbę użytkownika (pokaż wszystkie wpisy, nawet duplikaty)
    # seen_pallets = set()
    # deduplicated_items = []
    # for item in items:
    #     pid = item.get('nr_palety')
    #     if pid:
    #         if pid not in seen_pallets:
    #             seen_pallets.add(pid)
    #             deduplicated_items.append(item)
    #     else:
    #         deduplicated_items.append(item)
    # items = deduplicated_items

    items.sort(key=get_sort_key)

    # Struktura magazynów z Mlecznej Drogi
    magazyny_zakladki = [
        {'id': 'all', 'name': 'Wszystkie Magazyny'},
        {'id': 'MS01', 'name': 'Magazyn Surowcowy (MS01)'},
        {'id': 'MP01', 'name': 'Magazyn Produkcyjny (MP01)'},
        {'id': 'PSD01', 'name': 'Magazyn Produkcyjny (PSD01)'},
        {'id': 'MDO01', 'name': 'Magazyn Dodatków (MDO01)'},
        {'id': 'MOP01', 'name': 'Magazyn Opakowań (MOP01)'},
        {'id': 'MGW01', 'name': 'Wyroby Gotowe (MGW01)'},
        {'id': 'MGW02', 'name': 'Wyroby Gotowe (MGW02)'},
        {'id': 'BF_MS01', 'name': 'BUFOR MS01'},
        {'id': 'BF_MP01', 'name': 'BUFOR MP01'}
    ]

    # Calculate occupancy stats
    stats = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM magazyn_pojemnosci")
        caps = {r['sekcja']: r['pojemnosc_max'] for r in cursor.fetchall()}
        
        # sections like MS01, MP01, MOP01, MDO01, MGW01, MGW02, BF_MS01, BF_MP01, R01, R02...
        all_sections = list(caps.keys())
        # Regały przypisane do MP01
        regały_mp01 = ['R01', 'R02', 'R03', 'R04', 'R07']
        
        for zid in all_sections:
            total = caps.get(zid, 100)
            occupied = 0
            
            # Precyzyjne zliczanie dla regałów R01, R02...
            if zid.startswith('R'):
                occupied = len([it for it in items if (it.get('location') or '').startswith(zid)])
            elif zid == 'MP01':
                # MP01 to teraz konkretna lokalizacja (np. podłoga), a nie suma regałów
                occupied = len([it for it in items if ('MP01' in (it.get('location') or '').upper() or 'PODŁOGA' in (it.get('location') or '').upper()) and 'R0' not in (it.get('location') or '').upper()])
                total = caps.get('MP01', 20)
            elif zid == 'MS01':
                occupied = len([it for it in items if 'MS01' in (it.get('location') or '').upper() or 'PODŁOGA' in (it.get('location') or '').upper()])
                total = caps.get('MS01', 0)
            elif zid in ['MGW01', 'MGW02']:
                occupied = len([it for it in items if (it.get('location') or '').upper() == zid or (it.get('type') == 'Wyrób Gotowy' and not it.get('location'))])
            else:
                # Pozostałe (bufory, opakowania itp.)
                occupied = len([it for it in items if zid in (it.get('location') or '').upper()])

            stats[zid] = {
                'occupied': occupied,
                'total': total,
                'percent': round((occupied / total * 100), 1) if total > 0 else 0
            }

            
        # Global 'all'
        stats['all'] = {
            'occupied': len(items),
            'total': sum(caps.values()),
            'percent': min(100, round((len(items) / sum(caps.values()) * 100), 1)) if sum(caps.values()) > 0 else 0
        }
    except Exception as e:
        print(f"Error calculating stats: {e}")
        stats = {}
    finally:
        conn.close()

    return render_template('magazyny_nowe/dashboard.html', items=items, linia=linia, zakladki=magazyny_zakladki, aktywna_zakladka='all', stats=stats)

@magazyny_nowe_bp.route('/summary')
def summary():
    linia = request.args.get('linia', 'PSD').upper()
    palety_linie = ['PSD', 'AGRO'] if linia == 'ALL' else [linia]
    conn = get_db_connection()
    items = []
    try:
        cursor = conn.cursor(dictionary=True)
        # Pobierz wszystkie dane (identycznie jak w index)
        # 1. Surowce
        table_surowce = get_table_name('magazyn_surowce', linia)
        cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Surowiec' as type, nr_partii FROM {table_surowce} WHERE stan_magazynowy > 0")
        for row in cursor.fetchall():
            row['unit'] = 'kg'
            row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"SUR-{row['id']}"
            items.append(row)
            
        # 2. Opakowania
        table_opakowania = get_table_name('magazyn_opakowania', linia)
        cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Opakowanie' as type, nr_partii FROM {table_opakowania} WHERE stan_magazynowy > 0")
        for row in cursor.fetchall():
            row['unit'] = 'szt'
            row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"OPK-{row['id']}"
            items.append(row)
            
        # 3. Wyroby Gotowe (dla ALL łączymy PSD + AGRO)
        for linia_palety in palety_linie:
            table_palety = get_table_name('magazyn_palety', linia_palety)
            cursor.execute(f"SELECT id, nr_palety, produkt as productName, lokalizacja as location, waga_netto as amount, 'Wyrób Gotowy' as type, nr_partii FROM {table_palety} WHERE waga_netto > 0")
            for row in cursor.fetchall():
                row['unit'] = 'kg'
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"PAL-{row['id']}"
                items.append(row)

        # 4. Dodatki (NEW)
        cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Dodatek' as type, nr_partii FROM magazyn_dodatki WHERE stan_magazynowy > 0")
        for row in cursor.fetchall():
            row['unit'] = 'kg'
            row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"DOD-{row['id']}"
            items.append(row)
            
        conn.close()
    except Exception as e:
        print(f"Error in summary: {e}")
        if conn: conn.close()

    # Grupowanie danych po nazwie produktu
    summary_data = {}
    for it in items:
        name = it['productName']
        if name not in summary_data:
            summary_data[name] = {
                'total': 0,
                'count': 0,
                'type': it['type'],
                'unit': it['unit'],
                'pallets': []
            }
        summary_data[name]['total'] += it['amount']
        summary_data[name]['count'] += 1
        summary_data[name]['pallets'].append(it)

    return render_template('magazyny_nowe/summary.html', summary=summary_data, linia=linia)

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

@magazyny_nowe_bp.route('/production-status')
def production_status():
    """Strona podsumowania stanu 24 stanowisk produkcyjnych."""
    linia = request.args.get('linia', 'PSD').upper()
    return render_template('magazyny_nowe/production_status.html', linia=linia)

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

@magazyny_nowe_bp.route('/api/pallet/dispatch', methods=['POST'])
def dispatch_pallet():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.dispatch_pallet(pallet_id, pallet_type, worker, linia)
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

@magazyny_nowe_bp.route('/api/pallet/toggle-block', methods=['POST'])
def toggle_block():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.toggle_block(pallet_id, pallet_type, worker, linia)
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
