import re
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from flask import Blueprint, jsonify, render_template, request, session, current_app
from app.db import get_db_connection, get_table_name
from .blueprint import warehouse_v2_bp

def parse_date_obj(d_val):
    if not d_val:
        return None
    if isinstance(d_val, (datetime, date)):
        return d_val if isinstance(d_val, date) else d_val.date()
    if isinstance(d_val, str):
        for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%Y-%m-%d %H:%M:%S', '%d-%m-%Y'):
            try:
                return datetime.strptime(d_val.strip()[:10], fmt).date()
            except Exception:
                pass
    return None

def compute_expiry_date(exp_val, prod_date_val=None, fmt='%Y-%m-%d'):
    if not exp_val:
        return '-'
    if hasattr(exp_val, 'strftime'):
        try:
            return exp_val.strftime(fmt)
        except Exception:
            return str(exp_val)
    exp_str = str(exp_val).strip()
    if not exp_str or exp_str in ('-', 'None', 'null', 'brak'):
        return '-'
    parsed_exp = parse_date_obj(exp_str)
    if parsed_exp and ('-' in exp_str or '.' in exp_str or '/' in exp_str) and len(exp_str) >= 8:
        return parsed_exp.strftime(fmt)
    base_date = parse_date_obj(prod_date_val) or date.today()
    match_months = re.search(r'(\d+)\s*(?:miesi|m-c|m\b|mies)', exp_str, re.IGNORECASE)
    if match_months:
        months = int(match_months.group(1))
        return (base_date + relativedelta(months=months)).strftime(fmt)
    match_days = re.search(r'(\d+)\s*(?:dni|d\b|dzień)', exp_str, re.IGNORECASE)
    if match_days:
        days = int(match_days.group(1))
        return (base_date + timedelta(days=days)).strftime(fmt)
    match_years = re.search(r'(\d+)\s*(?:rok|lat|lata)', exp_str, re.IGNORECASE)
    if match_years:
        years = int(match_years.group(1))
        return (base_date + relativedelta(years=years)).strftime(fmt)
    if exp_str.isdigit():
        months = int(exp_str)
        return (base_date + relativedelta(months=months)).strftime(fmt)
    return exp_str

def format_date_val(val, fmt='%Y-%m-%d'):
    if not val:
        return '-'
    if hasattr(val, 'strftime'):
        try:
            return val.strftime(fmt)
        except Exception:
            return str(val)
    return str(val)

def classify_packaging_type(product_name: str, type_str: str, amount: float = 0, unit: str = 'kg', raw_pkg: str = '') -> str:
    p_name = str(product_name or '').upper()
    t_str = str(type_str or '').upper()
    pkg_raw = str(raw_pkg or '').upper()
    
    if 'BIG' in pkg_raw or 'BB' in pkg_raw or 'BIG BAG' in p_name or 'BIGBAG' in p_name or ' BB' in p_name or '1000KG' in p_name or '1000 KG' in p_name or 'WAPNO BB' in p_name:
        return 'Big Bag (1000kg)'
    if '25KG' in p_name or '25 KG' in p_name or 'WOREK' in pkg_raw or 'WORKI' in pkg_raw or 'WOREK' in p_name or 'WORK' in p_name:
        return 'Worek (25kg)'
    if '50KG' in p_name or '50 KG' in p_name:
        return 'Worek (50kg)'
    if '20KG' in p_name or '20 KG' in p_name:
        return 'Worek (20kg)'
    if 'KARTON' in pkg_raw or 'KARTON' in p_name:
        return 'Karton'
    if 'FOLIA' in p_name or 'ROLKA' in pkg_raw or 'ROLKA' in p_name or 'KALKA' in p_name:
        return 'Rolka / Folia'
    if 'WIADRO' in p_name or 'WIADRA' in p_name:
        return 'Wiadro'
    if 'KANISTER' in p_name or 'BECZKA' in p_name:
        return 'Kanister / Beczka'
    if t_str == 'OPAKOWANIE':
        return 'Opakowanie / Karton'
    if t_str in ('WYRÓB GOTOWY', 'SUROWIEC', 'DODATEK'):
        if amount and amount >= 800 and ('BB' in p_name or ('SUROWIEC' in t_str and amount % 25 != 0)):
            return 'Big Bag (1000kg)'
        return 'Worek (25kg)'
    return 'Worek (25kg)'

@warehouse_v2_bp.route('/')
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
            cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Surowiec' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked, created_at, typ_opakowania FROM {table_surowce} WHERE stan_magazynowy > 0")
            surowce = cursor.fetchall()
            for row in surowce:
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"SUR-{row['id']}"
                row['linia'] = shared_linia
                row['date_prod'] = format_date_val(row.get('data_produkcji'))
                row['date_exp'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                row['date_added'] = format_date_val(row.get('created_at'), '%Y-%m-%d %H:%M')
                row['batch'] = row.get('nr_partii') or '-'
                row['unit'] = 'kg'
                row['is_blocked'] = row.get('is_blocked', 0)
                row['packaging_type'] = classify_packaging_type(row['productName'], row['type'], row['amount'], row['unit'], row.get('typ_opakowania'))
                items.append(row)
        except Exception as e:
            print(f"Error fetching surowce: {e}")

        # 2. Opakowania
        table_opakowania = get_table_name('magazyn_opakowania', linia)
        try:
            cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Opakowanie' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked, created_at, typ_opakowania FROM {table_opakowania} WHERE stan_magazynowy > 0")
            opakowania = cursor.fetchall()
            for row in opakowania:
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"OPK-{row['id']}"
                row['linia'] = shared_linia
                row['date_prod'] = format_date_val(row.get('data_produkcji'))
                row['date_exp'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                row['date_added'] = format_date_val(row.get('created_at'), '%Y-%m-%d %H:%M')
                row['batch'] = row.get('nr_partii') or '-'
                row['unit'] = 'szt'
                row['is_blocked'] = row.get('is_blocked', 0)
                row['packaging_type'] = classify_packaging_type(row['productName'], row['type'], row['amount'], row['unit'], row.get('typ_opakowania'))
                items.append(row)
        except Exception as e:
            print(f"Error fetching opakowania: {e}")

        # 3. Wyroby Gotowe (dla ALL łączymy PSD + AGRO)
        for linia_palety in palety_linie:
            table_palety = get_table_name('magazyn_palety', linia_palety)
            table_plan = get_table_name('plan_produkcji', linia_palety)
            line_condition = "AND (m.linia = 'PSD' OR m.linia IS NULL OR m.linia = '')" if table_palety == 'magazyn_palety' else ""
            try:
                cursor.execute(
                    f"""
                    SELECT m.id, m.nr_palety, 
                           COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Nieznany produkt') as productName, 
                           COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'OCZEKUJĄCE') as location, 
                           m.waga_netto as amount, 
                           'Wyrób Gotowy' as type, 
                           COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji, m.data_planu, plan.data_planu) as data_produkcji, 
                           COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci, 
                           COALESCE(NULLIF(TRIM(m.linia), ''), '{linia_palety}') as linia, 
                           COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii) as nr_partii, 
                           m.is_blocked, 
                           COALESCE(m.created_at, m.data_potwierdzenia) as created_at,
                           COALESCE(m.typ_opakowania, plan.typ_opakowania, '') as typ_opakowania
                    FROM {table_palety} m
                    LEFT JOIN {table_plan} plan ON m.plan_id = plan.id
                    WHERE m.waga_netto > 0 {line_condition}
                    """
                )
                palety = cursor.fetchall()

                for row in palety:
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"PAL-{row['id']}"
                    row['linia'] = (row.get('linia') or linia_palety)
                    row['date_prod'] = format_date_val(row.get('data_produkcji'))
                    row['date_exp'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                    row['date_added'] = format_date_val(row.get('created_at'), '%Y-%m-%d %H:%M')
                    row['batch'] = row.get('nr_partii') or '-'
                    row['unit'] = 'kg'
                    row['is_blocked'] = row.get('is_blocked', 0)
                    row['packaging_type'] = classify_packaging_type(row['productName'], row['type'], row['amount'], row['unit'], row.get('typ_opakowania'))

                    # Przypisz domyślną lokalizację OCZEKUJĄCE dla wyrobów gotowych jeśli nie mają
                    if not row['location']:
                        row['location'] = 'OCZEKUJĄCE'

                    items.append(row)
            except Exception as e:
                print(f"Error fetching wyroby gotowe ({linia_palety}): {e}")

        # 4. Dodatki (NEW)
        try:
            cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Dodatek' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked, created_at, typ_opakowania FROM magazyn_dodatki WHERE stan_magazynowy > 0")
            dodatki = cursor.fetchall()
            for row in dodatki:
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"DOD-{row['id']}"
                row['linia'] = shared_linia
                row['date_prod'] = format_date_val(row.get('data_produkcji'))
                row['date_exp'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                row['date_added'] = format_date_val(row.get('created_at'), '%Y-%m-%d %H:%M')
                row['batch'] = row.get('nr_partii') or '-'
                row['unit'] = 'kg'
                row['is_blocked'] = row.get('is_blocked', 0)
                row['packaging_type'] = classify_packaging_type(row['productName'], row['type'], row['amount'], row['unit'], row.get('typ_opakowania'))
                items.append(row)
        except Exception as e:
            print(f"Error fetching dodatki: {e}")

    except Exception as e:
        print(f"Error in dashboard: {e}")

    # Mark expired pallets as system-blocked
    today_str = datetime.now().strftime('%Y-%m-%d')
    for it in items:
        exp = it.get('date_exp')
        if exp and exp not in ('-', 'brak', '', 'None') and exp < today_str:
            it['is_blocked'] = 1
            it['is_system_blocked'] = 1

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

    items.sort(key=get_sort_key)

    # Struktura magazynów z Mlecznej Drogi
    magazyny_zakladki = [
        {'id': 'all', 'name': 'Wszystkie Magazyny'},
        {'id': 'MS01', 'name': 'Magazyn Surowcowy (MS01)'},
        {'id': 'MP01', 'name': 'Magazyn Produkcyjny (MP01)'},
        {'id': 'OSIP', 'name': 'Magazyn OSIP (OSIP)'},
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
                occupied = len([it for it in items if (it.get('location') or '').upper() == zid or (it.get('type') == 'Wyrób Gotowy' and not it.get('location') and zid == 'MGW01')])
            else:
                # Pozostałe (bufory, opakowania itp.)
                occupied = len([it for it in items if zid in (it.get('location') or '').upper()])

            stats[zid] = {
                'occupied': occupied,
                'total': total,
                'percent': round((occupied / total * 100), 1) if total > 0 else 0
            }

            
        # Global 'all' (wykluczamy palety z magazynu zewnętrznego OSIP)
        non_osip_items = [it for it in items if not ('OSIP' in (it.get('location') or '').upper() or (it.get('location') or '').upper().startswith('OS'))]
        total_non_osip_cap = sum(v for k, v in caps.items() if k != 'OSIP')
        stats['all'] = {
            'occupied': len(non_osip_items),
            'total': total_non_osip_cap,
            'percent': min(100, round((len(non_osip_items) / total_non_osip_cap * 100), 1)) if total_non_osip_cap > 0 else 0
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

    aktywna_zakladka = request.args.get('zakladka', 'all')
    return render_template('warehouse_v2/dashboard.html', items=items, linia=linia, zakladki=magazyny_zakladki, aktywna_zakladka=aktywna_zakladka, stats=stats, printers=printers, fefo_pallets=fefo_pallets)

@warehouse_v2_bp.route('/summary')
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
        cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Surowiec' as type, nr_partii, data_produkcji, data_przydatnosci FROM {table_surowce} WHERE stan_magazynowy > 0")
        for row in cursor.fetchall():
            row['unit'] = 'kg'
            row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"SUR-{row['id']}"
            row['data_produkcji'] = format_date_val(row.get('data_produkcji'))
            row['data_przydatnosci'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
            items.append(row)
            
        # 2. Opakowania
        table_opakowania = get_table_name('magazyn_opakowania', linia)
        cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Opakowanie' as type, nr_partii, data_produkcji, data_przydatnosci FROM {table_opakowania} WHERE stan_magazynowy > 0")
        for row in cursor.fetchall():
            row['unit'] = 'szt'
            row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"OPK-{row['id']}"
            row['data_produkcji'] = format_date_val(row.get('data_produkcji'))
            row['data_przydatnosci'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
            items.append(row)
            
        # 3. Wyroby Gotowe (dla ALL łączymy PSD + AGRO)
        for linia_palety in palety_linie:
            table_palety = get_table_name('magazyn_palety', linia_palety)
            table_plan = get_table_name('plan_produkcji', linia_palety)
            line_condition = "AND (m.linia = 'PSD' OR m.linia IS NULL OR m.linia = '')" if table_palety == 'magazyn_palety' else ""
            cursor.execute(f"""
                SELECT m.id, m.nr_palety, 
                       COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Nieznany produkt') as productName, 
                       COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'MGW01') as location, 
                       m.waga_netto as amount, 
                       'Wyrób Gotowy' as type, 
                       COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii) as nr_partii, 
                       COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji, m.data_planu, plan.data_planu) as data_produkcji, 
                       COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci 
                FROM {table_palety} m
                LEFT JOIN {table_plan} plan ON m.plan_id = plan.id
                WHERE m.waga_netto > 0 {line_condition}
            """)
            for row in cursor.fetchall():
                row['unit'] = 'kg'
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"PAL-{row['id']}"
                row['data_produkcji'] = format_date_val(row.get('data_produkcji'))
                row['data_przydatnosci'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                items.append(row)

        # 4. Dodatki (NEW)
        cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Dodatek' as type, nr_partii, data_produkcji, data_przydatnosci FROM magazyn_dodatki WHERE stan_magazynowy > 0")
        for row in cursor.fetchall():
            row['unit'] = 'kg'
            row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"DOD-{row['id']}"
            row['data_produkcji'] = format_date_val(row.get('data_produkcji'))
            row['data_przydatnosci'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
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

    def _summary_batch_key(p):
        exp = str(p.get('data_przydatnosci') or '')
        if not exp or exp == '-': exp = '9999-99-99'
        prod = str(p.get('data_produkcji') or '')
        if not prod or prod == '-': prod = '9999-99-99'
        return (exp, prod)

    def _summary_fifo_key(p):
        bk = _summary_batch_key(p)
        pid = int(p.get('id') or 0)
        return (bk[0], bk[1], pid)

    today_str = datetime.now().strftime('%Y-%m-%d')
    for name, data in summary_data.items():
        data['pallets'].sort(key=_summary_fifo_key)
        
        for p in data['pallets']:
            p_exp = str(p.get('data_przydatnosci') or '').strip()
            if p_exp and p_exp not in ('-', 'brak', '', 'None') and p_exp < today_str:
                p['is_blocked'] = 1
                p['is_system_blocked'] = 1

        valid_pallets = [p for p in data['pallets'] if not p.get('is_blocked')]
        earliest_bk = _summary_batch_key(valid_pallets[0]) if valid_pallets else ('9999-99-99', '9999-99-99')
        has_multiple_batches = any(_summary_batch_key(p) != earliest_bk for p in valid_pallets)

        unique_batches = []
        for p in data['pallets']:
            bk = _summary_batch_key(p)
            if bk not in unique_batches:
                unique_batches.append(bk)

        for idx, p in enumerate(data['pallets'], 1):
            bk = _summary_batch_key(p)
            batch_num = unique_batches.index(bk) + 1 if bk in unique_batches else 1
            is_eligible = not p.get('is_blocked')
            is_earliest = is_eligible and (bk == earliest_bk)
            p['fifo_index'] = idx
            p['fifo_batch_num'] = batch_num
            p['is_first_fifo'] = is_earliest and (has_multiple_batches or len(valid_pallets) > 1)

    return render_template('warehouse_v2/summary.html', summary=summary_data, linia=linia)

@warehouse_v2_bp.route('/production-status')
def production_status():
    """Strona podsumowania stanu 24 stanowisk produkcyjnych."""
    linia = request.args.get('linia', 'PSD').upper()
    return render_template('warehouse_v2/production_status.html', linia=linia)

@warehouse_v2_bp.route('/zamowienia')
def zamowienia():
    """Strona zamówień surowców z magazynu (lista)."""
    linia = request.args.get('linia', 'PSD').upper()
    return render_template('warehouse_v2/zamowienia.html', linia=linia)

@warehouse_v2_bp.route('/zamowienia/nowe')
def zamowienie_nowe():
    """Strona tworzenia nowego zamówienia (koszyk)."""
    linia = request.args.get('linia', 'PSD').upper()
    return render_template('warehouse_v2/zamowienie_nowe.html', linia=linia)

@warehouse_v2_bp.route('/archiwum')
def archiwum():
    """Strona z archiwum palet."""
    linia = request.args.get('linia', 'PSD').upper()
    conn = get_db_connection()
    archive_items = []
    try:
        cursor = conn.cursor(dictionary=True)
        # Pobieramy najnowsze 1000 rekordów z archiwum
        cursor.execute('''
            SELECT id, original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, 
                   waga_ostatnia, lokalizacja_ostatnia, data_archiwizacji, user_login, komentarz
            FROM magazyn_archiwum
            ORDER BY data_archiwizacji DESC
            LIMIT 1000
        ''')
        archive_items = cursor.fetchall()
        for row in archive_items:
            row['data_archiwizacji_str'] = row['data_archiwizacji'].strftime('%Y-%m-%d %H:%M:%S') if row['data_archiwizacji'] else '-'
    except Exception as e:
        print(f"Error fetching archive: {e}")
    finally:
        if conn:
            conn.close()
            
    return render_template('warehouse_v2/archiwum.html', linia=linia, items=archive_items)

@warehouse_v2_bp.route('/psd/raport_palet', methods=['GET'])
def raport_palet():
    """Generates a printable pallet report for PSD line."""
    from datetime import date
    today = date.today()
    
    # Accept date parameters, but default to today
    data_od = request.args.get('data_od') or request.args.get('data') or str(today)
    data_do = request.args.get('data_do') or request.args.get('data') or data_od
    plan_id = request.args.get('plan_id')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
       query = """
           SELECT w.id as work_id, w.produkt, w.tonaz_rzeczywisty as w_kg, 
                  z.id as zasyp_id, z.tonaz_rzeczywisty as z_kg,
                  w.nazwa_zlecenia, w.typ_produkcji, w.typ_opakowania, w.nr_partii,
                  z.typ_produkcji as zasyp_typ_produkcji, w.data_planu,
                  w.status,
                  0 as odrzuty_przesiewacz
           FROM plan_produkcji w
           LEFT JOIN plan_produkcji z ON w.zasyp_id = z.id
           WHERE (w.sekcja IN ('Workowanie', 'Czyszczenie') OR LOWER(w.produkt) LIKE '%czyszczenie%') 
             AND (w.is_deleted = 0 OR w.is_deleted IS NULL)
       """
       params = []
       if plan_id:
           query += ' AND w.id = %s'
           params.append(plan_id)
       else:
           query += ' AND ((w.data_planu BETWEEN %s AND %s) OR w.id IN (SELECT plan_id FROM palety_workowanie WHERE DATE(data_dodania) BETWEEN %s AND %s))'
           params.extend([data_od, data_do, data_od, data_do])
           query += ' ORDER BY w.data_planu DESC, w.id DESC'
       cursor.execute(query, tuple(params))
       plans = cursor.fetchall()
       if plan_id and plans:
           data_planu = str(plans[0]['data_planu'])
       else:
           data_planu = data_od
       report_data = []
       for p in plans:
            target_zasyp_id = p['zasyp_id'] if p.get('zasyp_id') else p['work_id']
            cursor.execute('''
                SELECT s.id, 
                       s.waga as waga, 
                       s.data_dodania 
                FROM szarze s
                WHERE s.plan_id = %s 
                ORDER BY s.data_dodania ASC
            ''', (target_zasyp_id,))
            batches_raw = cursor.fetchall()
            mixes_raw = []
            try:
                cursor.execute('''
                    SELECT id, waga, COALESCE(data_dodania, created_at) as data_dodania, kategoria 
                    FROM psd_mix_rozliczenie 
                    WHERE plan_id = %s 
                    ORDER BY data_dodania ASC
                ''', (target_zasyp_id,))
                mixes_raw = cursor.fetchall() or []
            except Exception:
                mixes_raw = []

            solo_dosypki = []
            try:
                cursor.execute('''
                    SELECT id, nazwa, kg, data_zlecenia 
                    FROM dosypki 
                    WHERE plan_id = %s AND szarza_id IS NULL AND potwierdzone = 1 AND anulowana = 0
                    ORDER BY data_zlecenia ASC
                ''', (target_zasyp_id,))
                solo_dosypki = cursor.fetchall() or []
            except Exception:
                solo_dosypki = []

            # Pobierz wskanowane Big Bagi (wsad do produkcji)
            bigbags_raw = []
            try:
                cursor.execute("""
                    SELECT id, paleta_id, nr_palety, nazwa_produktu, waga_kg,
                           nr_partii, data_produkcji, data_przydatnosci, typ_palety,
                           lokalizacja_zrodlowa, autor_login, created_at, status
                    FROM agro_workowanie_bigbagi
                    WHERE plan_id = %s AND status = 'ZUZYTY'
                    ORDER BY created_at ASC, id ASC
                """, (p['work_id'],))
                bigbags_raw = cursor.fetchall() or []
            except Exception:
                bigbags_raw = []
            total_bigbag_kg = sum(float(b['waga_kg'] or 0) for b in bigbags_raw)

            all_inputs = []
            for b_raw in batches_raw:
                all_inputs.append({'label': f"Zasyp #{b_raw['id']}", 'waga': b_raw['waga'] or 0, 'time': b_raw['data_dodania']})
            for d_raw in solo_dosypki:
                all_inputs.append({'label': f"Dosypka {d_raw['nazwa']} #{d_raw['id']}", 'waga': d_raw['kg'] or 0, 'time': d_raw['data_zlecenia']})
            for m_raw in mixes_raw:
                cat = m_raw.get('kategoria', 'MIX').replace('_', ' ') if m_raw.get('kategoria') else 'MIX'
                all_inputs.append({'label': f"MIX {cat} #{m_raw['id']}", 'waga': m_raw.get('waga') or m_raw.get('waga_kg') or 0, 'time': m_raw.get('data_dodania')})
            for bb in bigbags_raw:
                all_inputs.append({
                    'label': f"Big Bag {bb['nazwa_produktu']} #{bb['nr_palety'] or bb['id']}",
                    'waga': float(bb['waga_kg'] or 0),
                    'time': bb['created_at']
                })
            all_inputs.sort(key=lambda x: x['time'] if x['time'] else datetime.min)
            current_in_kg = 0
            input_ranges = []
            for inp in all_inputs:
                start = current_in_kg
                end = current_in_kg + inp['waga']
                input_ranges.append({'label': inp['label'], 'start': start, 'end': end})
                current_in_kg = end
            cursor.execute("""
                SELECT 
                    p.id, p.waga, p.status, p.data_dodania, 
                    p.dodal_login,
                    NULLIF(TRIM(COALESCE(m.user_login, p.potwierdzil_login)), '') as potwierdzil_login,
                    COALESCE(m.data_potwierdzenia, p.data_potwierdzenia) as data_potwierdzenia,
                    COALESCE(m.nr_plomby, p.nr_plomby) as nr_plomby,
                    COALESCE(m.nr_palety, p.nr_palety) as nr_palety
                FROM palety_workowanie p
                LEFT JOIN magazyn_palety m ON p.id = m.paleta_workowanie_id
                WHERE p.plan_id = %s OR (%s IS NOT NULL AND p.plan_id = %s)
                ORDER BY p.data_dodania ASC
            """, (p['work_id'], target_zasyp_id, target_zasyp_id))
            pallets_raw = cursor.fetchall()
            current_out_kg = 0
            processed_pallets = []
            for pal_raw in pallets_raw:
                p_start = current_out_kg
                p_end = current_out_kg + (pal_raw['waga'] or 0)
                shares = []
                for ir in input_ranges:
                    overlap_start = max(p_start, ir['start'])
                    overlap_end = min(p_end, ir['end'])
                    if overlap_end > overlap_start:
                        overlap_kg = overlap_end - overlap_start
                        waga_palety = float(pal_raw['waga'] or 0)
                        percent = overlap_kg / waga_palety * 100 if waga_palety > 0 else 0
                        if percent >= 0.5:
                            shares.append(f"{ir['label']} ({round(percent)}%)")
                pal_raw['sklad'] = ', '.join(shares) if shares else 'Nieznany skład'
                processed_pallets.append(pal_raw)
                current_out_kg = p_end

            total_pallet_kg = sum(float(pal['waga'] or 0) for pal in pallets_raw)
            total_mix_kg = sum(float(m.get('waga') or m.get('waga_kg') or 0) for m in mixes_raw)

            report_data.append({
                'plan': p,
                'palety': processed_pallets,
                'pallets': processed_pallets,
                'mixes': mixes_raw,
                'bigbags': bigbags_raw,
                'opakowania': [],
                'aktywne_opakowania': [],
                'packaging_stocks': {},
                'total_pallet_kg': total_pallet_kg,
                'total_mix_kg': total_mix_kg,
                'total_bigbag_kg': total_bigbag_kg,
                'input_summary': ', '.join([f"{inp['label']} ({inp['waga']:.1f}kg)" for inp in all_inputs])
            })
       return render_template('warehouse_v2/raport_palet.html', report_data=report_data, data_planu=data_planu, single_view=bool(plan_id), is_ajax=is_ajax, print_date=datetime.now().strftime('%d.%m.%Y %H:%M'))
    except Exception as e:
       current_app.logger.error(f'Error generating raport_palet: {e}')
       return jsonify({'success': False, 'error': str(e)}) if is_ajax else render_template('warehouse_v2/raport_palet.html', report_data=[], data_planu='', error=str(e))
    finally:
       cursor.close()
       conn.close()

@warehouse_v2_bp.route('/podglad-etykiety/<paleta_id>', methods=['GET'])
@warehouse_v2_bp.route('/psd/podglad-etykiety/<paleta_id>', methods=['GET'])
def podglad_etykiety_psd(paleta_id):
    """Generates HTML preview of a pallet label for any pallet type (Surowiec, Opakowanie, Dodatek, Wyrób Gotowy) using Labelary API."""
    from app.utils.pallet_label import prepare_pallet_label_data, is_packaging_item, calculate_expiry_date
    import json

    linia = request.args.get('linia', 'PSD').strip().upper()
    pallet_type = request.args.get('type', '').strip()
    sscc = request.args.get('sscc', '').strip()

    search_id = str(paleta_id).strip()
    search_sscc = sscc or search_id

    conn = get_db_connection()
    label_data = None
    resolved_type = pallet_type

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Primary lookup using unified prepare_pallet_label_data
        try:
            label_data = prepare_pallet_label_data(cursor, search_sscc or search_id, linia=linia)
        except Exception:
            label_data = None

        # 2. Targeted lookup based on type if not yet resolved
        if not label_data:
            if pallet_type.lower() in ('surowiec', 'raw_material', 'surowce') or search_sscc.upper().startswith('SUR'):
                tables = ['magazyn_surowce', 'magazyn_agro_surowce'] if linia != 'AGRO' else ['magazyn_agro_surowce', 'magazyn_surowce']
                for tbl in tables:
                    cursor.execute(
                        f"SELECT id, nazwa, stan_magazynowy as waga_netto, nr_partii, data_produkcji, data_przydatnosci, nr_palety, lokalizacja FROM {tbl} WHERE id = %s OR nr_palety = %s OR nr_palety = %s ORDER BY stan_magazynowy > 0 DESC, id DESC LIMIT 1",
                        (search_id, search_id, search_sscc)
                    )
                    row = cursor.fetchone()
                    if row:
                        label_data = {
                            'id': row['id'],
                            'nr_palety': row.get('nr_palety') or search_sscc,
                            'nazwa': row.get('nazwa') or 'Surowiec',
                            'ilosc': float(row.get('waga_netto') or 0),
                            'data': str(row.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')),
                            'termin': str(row.get('data_przydatnosci') or ''),
                            'partia': row.get('nr_partii') or '---',
                            'jednostka': 'kg',
                            'typ': 'SUROWIEC',
                            'linia': linia
                        }
                        resolved_type = 'Surowiec'
                        break

            elif pallet_type.lower() in ('opakowanie', 'packaging', 'opakowania') or search_sscc.upper().startswith(('OPK', 'OPA')):
                tables = ['magazyn_opakowania', 'magazyn_agro_opakowania'] if linia != 'AGRO' else ['magazyn_agro_opakowania', 'magazyn_opakowania']
                for tbl in tables:
                    cursor.execute(
                        f"SELECT id, nazwa, stan_magazynowy as waga_netto, nr_partii, data_produkcji, data_przydatnosci, nr_palety, lokalizacja FROM {tbl} WHERE id = %s OR nr_palety = %s OR nr_palety = %s ORDER BY stan_magazynowy > 0 DESC, id DESC LIMIT 1",
                        (search_id, search_id, search_sscc)
                    )
                    row = cursor.fetchone()
                    if row:
                        label_data = {
                            'id': row['id'],
                            'nr_palety': row.get('nr_palety') or search_sscc,
                            'nazwa': row.get('nazwa') or 'Opakowanie',
                            'ilosc': float(row.get('waga_netto') or 0),
                            'data': str(row.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')),
                            'termin': str(row.get('data_przydatnosci') or ''),
                            'partia': row.get('nr_partii') or '---',
                            'jednostka': 'szt.',
                            'typ': 'OPAKOWANIE',
                            'linia': linia
                        }
                        resolved_type = 'Opakowanie'
                        break

            elif pallet_type.lower() in ('dodatek', 'dodatki') or search_sscc.upper().startswith('DOD'):
                cursor.execute(
                    "SELECT id, nazwa, stan_magazynowy as waga_netto, nr_partii, data_produkcji, data_przydatnosci, nr_palety, lokalizacja FROM magazyn_dodatki WHERE id = %s OR nr_palety = %s OR nr_palety = %s ORDER BY stan_magazynowy > 0 DESC, id DESC LIMIT 1",
                    (search_id, search_id, search_sscc)
                )
                row = cursor.fetchone()
                if row:
                    label_data = {
                        'id': row['id'],
                        'nr_palety': row.get('nr_palety') or search_sscc,
                        'nazwa': row.get('nazwa') or 'Dodatek',
                        'ilosc': float(row.get('waga_netto') or 0),
                        'data': str(row.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')),
                        'termin': str(row.get('data_przydatnosci') or ''),
                        'partia': row.get('nr_partii') or '---',
                        'jednostka': 'kg',
                        'typ': 'DODATEK',
                        'linia': linia
                    }
                    resolved_type = 'Dodatek'

        # 3. Fallback scan across all tables if not found
        if not label_data:
            all_candidate_tables = [
                ('magazyn_surowce', 'SUROWIEC', 'kg'),
                ('magazyn_agro_surowce', 'SUROWIEC', 'kg'),
                ('magazyn_opakowania', 'OPAKOWANIE', 'szt.'),
                ('magazyn_agro_opakowania', 'OPAKOWANIE', 'szt.'),
                ('magazyn_dodatki', 'DODATEK', 'kg'),
                ('magazyn_palety', 'WYRÓB GOTOWY', 'kg'),
                ('magazyn_palety_agro', 'WYRÓB GOTOWY', 'kg')
            ]
            for tbl, def_typ, def_unit in all_candidate_tables:
                col_name = 'produkt' if 'palety' in tbl else 'nazwa'
                col_qty = 'waga_netto' if 'palety' in tbl else 'stan_magazynowy'
                try:
                    cursor.execute(
                        f"SELECT id, {col_name} as nazwa, {col_qty} as waga_netto, nr_partii, data_produkcji, data_przydatnosci, nr_palety FROM {tbl} WHERE id = %s OR nr_palety = %s OR nr_palety = %s ORDER BY {col_qty} > 0 DESC, id DESC LIMIT 1",
                        (search_id, search_id, search_sscc)
                    )
                    row = cursor.fetchone()
                    if row:
                        label_data = {
                            'id': row['id'],
                            'nr_palety': row.get('nr_palety') or search_sscc,
                            'nazwa': row.get('nazwa') or 'Produkt',
                            'ilosc': float(row.get('waga_netto') or 0),
                            'data': str(row.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')),
                            'termin': str(row.get('data_przydatnosci') or ''),
                            'partia': row.get('nr_partii') or '---',
                            'jednostka': def_unit,
                            'typ': def_typ,
                            'linia': linia
                        }
                        resolved_type = def_typ
                        break
                except Exception:
                    continue

    finally:
        conn.close()

    if not label_data:
        return 'Nie znaleziono danych etykiety dla tej palety.', 404

    nr_palety = str(label_data.get('nrPalety') or label_data.get('nr_palety') or search_sscc or paleta_id).strip()
    product_name = str(label_data.get('nazwa') or label_data.get('produkt') or 'Brak nazwy').strip()
    nr_partii = str(label_data.get('partia') or label_data.get('nr_partii') or '---').strip() or '---'
    data_produkcji = str(label_data.get('data') or label_data.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')).strip()[:10]
    data_przydatnosci_raw = str(label_data.get('termin') or label_data.get('data_przydatnosci') or '').strip()
    data_przydatnosci = calculate_expiry_date(data_przydatnosci_raw, data_produkcji) if data_przydatnosci_raw else ''
    qty_display = float(label_data.get('ilosc') or label_data.get('waga_netto') or 0)
    nr_palety_lp = label_data.get('nr_palety_lp')
    nr_plomby = label_data.get('nr_plomby') or None

    try:
        if nr_palety_lp not in (None, ''):
            nr_palety_lp = int(nr_palety_lp)
        else:
            nr_palety_lp = None
    except Exception:
        nr_palety_lp = None

    nr_upper = nr_palety.upper()
    prod_lower = product_name.lower()
    is_pkg = is_packaging_item(
        product_name,
        unit=label_data.get('jednostka') or label_data.get('unit'),
        typ=resolved_type or label_data.get('typ'),
        pallet_nr=nr_palety
    )
    is_surowiec = (
        nr_upper.startswith('SUR') or 
        nr_upper.startswith('DOD') or 
        'surowiec' in prod_lower or 
        (str(resolved_type or label_data.get('typ') or '')).lower() in ('surowiec', 'dodatek')
    )

    if is_pkg:
        typ_label = 'OPAKOWANIE'
        unit_str = 'szt.'
        qty_header = 'ILOSC:'
    elif is_surowiec:
        typ_label = 'SUROWIEC'
        unit_str = 'kg'
        qty_header = 'WAGA NETTO:'
    else:
        typ_label = 'WYRÓB GOTOWY'
        unit_str = 'kg'
        qty_header = 'WAGA NETTO:'

    qr_details = {
        "sscc": nr_palety,
        "prod": product_name,
        "lp": str(nr_palety_lp or ''),
        "partia": nr_partii,
        "plomba": str(nr_plomby or ''),
        "data_prod": data_produkcji,
        "data_przyd": data_przydatnosci or '---',
        "ilosc": f"{qty_display:.2f}",
        "jm": unit_str,
        "typ": f"{typ_label} - {linia}"
    }
    qr_details_safe = json.dumps(qr_details, ensure_ascii=False).replace('^', '').replace('~', '')

    partia_line = f"^FO40,900^A0N,45,45^FDNR PARTII: {nr_partii}^FS" if nr_partii and nr_partii != '---' else ""
    przydatnosc_line = f"^FO40,950^A0N,45,45^FDTERMIN PRZYDATNOŚCI: {data_przydatnosci}^FS" if data_przydatnosci and data_przydatnosci != '---' else ""
    plomba_line = f"^FO40,1000^A0N,45,45^FDNR PLOMBY: {nr_plomby}^FS" if nr_plomby else ""

    zpl_string = f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FD{typ_label} - {linia}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{product_name}^FS
^FO250,320^BQN,2,12^FDQA,{nr_palety}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{nr_palety}^FS
^FO40,750^A0N,50,50^FDNR PALETY: {nr_palety_lp or '---'}^FS
^FO40,850^A0N,50,50^FDPRODUKCJA: {data_produkcji}^FS
{partia_line}
{przydatnosc_line}
{plomba_line}
^FO40,1050^A0N,70,70^FD{qty_header}^FS
^FO40,1150^A0N,100,100^FD{qty_display:.2f} {unit_str}^FS
^FO583,975^BQN,2,3^FDQA,{qr_details_safe}^FS
^PQ1
^XZ"""

    return render_template(
        'magazyn_dostawy/etykieta_podglad.html',
        nr_palety=nr_palety,
        product_name=product_name,
        nr_partii=nr_partii,
        data_produkcji=data_produkcji,
        data_przydatnosci=data_przydatnosci,
        qty=qty_display,
        typ_label=typ_label,
        linia=linia,
        qr_details_json=json.dumps(qr_details),
        zpl_string=zpl_string,
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )

@warehouse_v2_bp.route('/racks-3d')
@warehouse_v2_bp.route('/widok-3d')
def racks_3d_view():
    """Interactive 3D Warehouse Rack visualization view."""
    linia = request.args.get('linia', 'ALL').upper()
    active_rack = request.args.get('rack_id', 'R01')
    from app.services.warehouse_3d_service import Warehouse3dService
    racks_config = Warehouse3dService.get_rack_configurations()
    
    # Magazyny zakladki for standard header navigation
    magazyny_zakladki = [
        {'id': 'all', 'name': 'Wszystkie Magazyny'},
        {'id': 'MS01', 'name': 'Magazyn Surowcowy (MS01)'},
        {'id': 'MP01', 'name': 'Magazyn Produkcyjny (MP01)'},
        {'id': 'OSIP', 'name': 'Magazyn OSIP (OSIP)'},
        {'id': 'PSD01', 'name': 'Magazyn Produkcyjny (PSD01)'},
        {'id': 'MDO01', 'name': 'Magazyn Dodatków (MDO01)'},
        {'id': 'MOP01', 'name': 'Magazyn Opakowań (MOP01)'},
        {'id': 'MGW01', 'name': 'Wyroby Gotowe (MGW01)'},
        {'id': 'MGW02', 'name': 'Wyroby Gotowe (MGW02)'},
        {'id': 'BF_MS01', 'name': 'BUFOR MS01'},
        {'id': 'BF_MP01', 'name': 'BUFOR MP01'}
    ]

    return render_template(
        'warehouse_v2/racks_3d.html',
        linia=linia,
        active_rack=active_rack,
        racks_config=racks_config,
        zakladki=magazyny_zakladki,
        aktywna_zakladka='all',
        aktywna_podzakladka='all',
        stats={}
    )


