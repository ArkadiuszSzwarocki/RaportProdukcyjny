from flask import Blueprint, jsonify, render_template, request, session
from app.db import get_db_connection, get_table_name
from .blueprint import magazyny_nowe_bp

@magazyny_nowe_bp.route('/')
def index():
    linia = request.args.get('linia', 'PSD').upper()
    palety_linie = ['PSD', 'AGRO'] if linia == 'ALL' else [linia]
    shared_linia = linia if linia in ('PSD', 'AGRO') else 'PSD'
    conn = get_db_connection()
    items = []
    printers = []
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Load active printers
        try:
            cursor.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1")
            printers = cursor.fetchall()
        except Exception as e:
            print(f"Error fetching printers: {e}")
        
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

                    # Przypisz lokalizację MGW01/MGW02 dla wyrobów gotowych jeśli nie mają
                    if not row['location']:
                        row['location'] = 'MGW02' if row.get('linia') == 'AGRO' else 'MGW01'

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

    # FEFO Pallets
    from app.services.dashboard_service import DashboardService
    from datetime import date
    fefo_pallets = DashboardService.get_expiring_pallets(date.today(), linia, days_threshold=30)

    return render_template('magazyny_nowe/dashboard.html', items=items, linia=linia, zakladki=magazyny_zakladki, aktywna_zakladka='all', stats=stats, printers=printers, fefo_pallets=fefo_pallets)

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

@magazyny_nowe_bp.route('/production-status')
def production_status():
    """Strona podsumowania stanu 24 stanowisk produkcyjnych."""
    linia = request.args.get('linia', 'PSD').upper()
    return render_template('magazyny_nowe/production_status.html', linia=linia)

