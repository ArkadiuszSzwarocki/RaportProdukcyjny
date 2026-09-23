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

from app.blueprints.warehouse_v2.utils.packaging_classifier import classify_packaging_type
from app.blueprints.warehouse_v2.controllers.warehouse_index_controller import WarehouseIndexController
from app.blueprints.warehouse_v2.controllers.warehouse_summary_controller import WarehouseSummaryController

@warehouse_v2_bp.route('/')
def index():
    return WarehouseIndexController.render_index()

@warehouse_v2_bp.route('/summary')
def summary():
    return WarehouseSummaryController.render_summary()

@warehouse_v2_bp.route('/transfers')
def transfers_osip_view():
    """Widok transferów międzymagazynowych na magazyn OSIP z poziomu Wszystkich Magazynów."""
    linia = request.args.get('linia', 'PSD').upper()
    return render_template('osip/osip_transfers.html', scope='centrala', linia=linia)


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

@warehouse_v2_bp.route('/kompletacja')
def kompletacja():
    """Strona dyspozycji kompletacji zamówień (FIFO Picking)."""
    linia = request.args.get('linia', 'PSD').upper()
    order_ref = request.args.get('order_ref', '')
    return render_template('warehouse_v2/kompletacja.html', linia=linia, initial_order_ref=order_ref)

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
                    COALESCE(m.nr_palety, p.nr_palety) as nr_palety,
                    COALESCE(p.nr_palety_lp, m.nr_palety_lp) as nr_palety_lp
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
    """Generates HTML preview of a pallet label for any pallet type using PalletLabelController."""
    from app.blueprints.warehouse_v2.controllers.pallet_label_controller import PalletLabelController
    return PalletLabelController.render_label_preview(paleta_id)

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


