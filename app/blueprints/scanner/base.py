"""
routes_scanner.py — API dla skanera i drukowania etykiet.

Endpointy:
  POST /agro/scanner/lookup          — szukaj palety po QR/lokalizacji
  POST /agro/scanner/dispatch        — wydaj na produkcję
  POST /agro/scanner/split           — podziel paletę na worki
  POST /agro/scanner/print           — wydrukuj etykietę
  GET  /agro/scanner/printer/status  — sprawdź drukarkę
  GET  /agro/scanner/ui              — interfejs skanera (HTML)
"""

from flask import Blueprint, request, jsonify, session, render_template
from datetime import datetime
from app.services.scanner_service import ScannerService
from app.services.warehouse_v2_service import WarehouseV2Service
from app.services.print_server import get_printer

scanner_bp = Blueprint('scanner', __name__, url_prefix='/agro/scanner')


def _linia():
    return request.args.get('linia', request.json.get('linia', 'AGRO') if request.is_json else 'AGRO')


def _worker():
    return session.get('login', 'nieznany')


# ─────────────────────────────────────────────────────────────────────────────
# Lookup
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/lookup', methods=['POST'])
def lookup():
    data = request.get_json(silent=True) or {}
    code = data.get('code', '').strip()
    linia = data.get('linia', 'AGRO')

    if not code:
        return jsonify({'success': False, 'error': 'Brak kodu'}), 400

    pallet = ScannerService.lookup_by_location(code, linia=linia)
    if not pallet:
        return jsonify({'success': False, 'error': f'Nie znaleziono palety: {code}'}), 404

    return jsonify({'success': True, 'pallet': pallet})


@scanner_bp.route('/pallet/history', methods=['GET'])
def get_pallet_history():
    pallet_id = request.args.get('id')
    sscc = request.args.get('sscc') or (pallet_id if pallet_id and not str(pallet_id).isdigit() else None)
    pallet_type = request.args.get('type') or 'Surowiec'
    linia = request.args.get('linia') or _linia() or 'AGRO'
    
    if not pallet_id and not sscc:
        return jsonify({'success': False, 'error': 'Brak ID lub numeru palety'}), 400
        
    history = WarehouseV2Service.get_pallet_history(pallet_id, pallet_type, linia, sscc=sscc)
    return jsonify({'success': True, 'history': history})


# ─────────────────────────────────────────────────────────────────────────────
# Restore from archive / consumption (MasterAdmin & Liderzy)
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/restore', methods=['POST'])
def restore_pallet():
    user_role = str(session.get('rola') or session.get('role') or '').lower().strip()
    if user_role not in ['masteradmin', 'lider', 'admin', 'zarzad']:
        return jsonify({
            'success': False, 
            'error': 'Brak uprawnień. Tylko MasterAdmin i Liderzy mogą przywracać zużyte palety.'
        }), 403

    data = request.get_json(silent=True) or {}
    archive_id = data.get('archive_id')
    nr_palety = data.get('nr_palety')
    waga = data.get('waga')
    lokalizacja = data.get('lokalizacja')
    
    if not archive_id and not nr_palety:
        return jsonify({'success': False, 'error': 'Brak numeru palety lub ID archiwum'}), 400

    ok, msg, restored_info = WarehouseV2Service.restore_pallet_from_archive(
        archive_id=int(archive_id) if archive_id else None,
        nr_palety=nr_palety,
        new_weight=float(waga) if waga is not None else None,
        new_location=lokalizacja,
        user_login=_worker()
    )

    if not ok:
        return jsonify({'success': False, 'error': msg}), 400

    return jsonify({
        'success': True,
        'message': msg,
        'pallet': restored_info
    })


# ─────────────────────────────────────────────────────────────────────────────
# Validate station / tank before dispatch
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/validate-station', methods=['POST'])
def validate_station():
    data = request.get_json(silent=True) or {}
    zbiornik = str(data.get('zbiornik') or '').strip().upper()
    surowiec_nazwa = str(data.get('surowiec_nazwa') or '').strip()
    surowiec_id = data.get('surowiec_id')
    pallet_type = data.get('pallet_type') or 'Surowiec'

    if not zbiornik:
        return jsonify({'success': False, 'error': 'Brak kodu lokalizacji/stacji'}), 400

    from app.utils.location_validator import is_production_tank_code, is_deleted_station_code
    if is_deleted_station_code(zbiornik):
        return jsonify({
            'success': False,
            'is_production': True,
            'error': f'❌ Stacja {zbiornik} została wycofana/usunięta z systemu!'
        }), 400

    if not is_production_tank_code(zbiornik):
        # Nie jest to stacja produkcyjna (np. regał magazynowy)
        return jsonify({'success': True, 'is_production': False})

    # Do stacji produkcyjnych nie wolno wydawać wyrobów gotowych ani opakowań
    if pallet_type == 'Wyrób Gotowy':
        return jsonify({
            'success': False,
            'is_production': True,
            'error': f'❌ Wyrobów gotowych nie można przekazać na stację produkcyjną ({zbiornik})!'
        }), 400

    if pallet_type == 'Opakowanie':
        return jsonify({
            'success': False,
            'is_production': True,
            'error': f'❌ Opakowań nie można wydawać do stacji produkcyjnej ({zbiornik})!'
        }), 400

    from app.services.tank_validation_service import TankValidationService
    is_valid, err_msg = TankValidationService.validate_tank_material(
        kod_zbiornika=zbiornik,
        surowiec_nazwa=surowiec_nazwa,
        surowiec_id=surowiec_id
    )

    if not is_valid:
        return jsonify({
            'success': False,
            'is_production': True,
            'error': err_msg
        }), 400

    return jsonify({
        'success': True,
        'is_production': True,
        'message': 'OK'
    })


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch to production
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/dispatch', methods=['POST'])
def dispatch():
    data = request.get_json(silent=True) or {}
    surowiec_id = data.get('surowiec_id')
    pallet_type = data.get('type')
    ilosc       = data.get('ilosc')
    linia       = data.get('linia', 'AGRO')
    plan_id     = data.get('plan_id')
    zbiornik    = data.get('zbiornik')
    komentarz   = data.get('komentarz')

    if not surowiec_id or ilosc is None:
        return jsonify({'success': False, 'error': 'Brak parametrów: surowiec_id, ilosc'}), 400

    if not pallet_type:
        pallet_type = 'Surowiec'

    try:
        ilosc = float(ilosc)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400

    ok, msg, extra_data = ScannerService.dispatch_to_production(
        surowiec_id=int(surowiec_id),
        ilosc=ilosc,
        worker_login=_worker(),
        linia=linia,
        plan_id=plan_id,
        zbiornik=zbiornik,
        komentarz=komentarz,
        pallet_type=pallet_type,
    )

    if ok and extra_data and extra_data.get('is_partial'):
        try:
            from app.services.print_server import get_printer
            from datetime import datetime
            printer = get_printer()
            
            # 1. Drukowanie zaktualizowanej palety matki (2 sztuki z pozostałą ilością)
            label_data = ScannerService.get_label_data(int(surowiec_id), linia=linia)
            if label_data:
                printer.print_pallet_label(label_data, copies=2)
                
            # 2. Drukowanie etykiety dla zasypanej ilości na zbiornik / stację KO (1 sztuka)
            tank_code = str(extra_data.get('zbiornik') or '').strip().upper()
            tank_label_data = dict(label_data) if label_data else {}
            from app.utils.pallet_id import is_valid_pallet_id, generate_pallet_id
            target_sscc = str(extra_data.get('nr_palety') or (label_data.get('nr_palety') if label_data else '') or '').strip()
            if not target_sscc or not is_valid_pallet_id(target_sscc):
                target_sscc = generate_pallet_id(linia, 'surowiec')
            tank_label_data.update({
                'id': str(surowiec_id),
                'nr_palety': target_sscc,
                'sscc': target_sscc,
                'nazwa': extra_data.get('pallet_name') or (label_data.get('nazwa') if label_data else ''),
                'ilosc': extra_data.get('ilosc_pobrana', 0),
                'lokalizacja': tank_code,
                'zbiornik': tank_code,
                'stacja': tank_code,
                'typ': label_data.get('typ') if label_data else 'SUROWIEC',
                'inventory_type': 'Surowiec',
                'jednostka': (label_data.get('jednostka') if label_data else 'kg') or 'kg',
                'linia': linia,
            })
            printer.print_pallet_label(tank_label_data, copies=1)
            msg += f" (Wysłano etykiety do druku: 2x paleta-matka, 1x zbiornik {tank_code})"
        except Exception as e:
            msg += f" (Błąd automatycznego druku etykiet: {e})"

    return jsonify({'success': ok, 'message': msg})


# ─────────────────────────────────────────────────────────────────────────────
# Move pallet
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/move', methods=['POST'])
def move():
    data = request.get_json(silent=True) or {}
    surowiec_id = data.get('surowiec_id')
    nr_palety = data.get('nr_palety')
    pallet_type = data.get('type')
    nowa_lokalizacja = data.get('lokalizacja')
    linia = data.get('linia', 'AGRO')

    identifier = surowiec_id or nr_palety
    if not identifier or not nowa_lokalizacja:
        return jsonify({'success': False, 'error': 'Brak parametrów: surowiec_id/nr_palety, lokalizacja'}), 400

    # Default to Surowiec if no type is provided or is TRANSFER (for backward compatibility)
    if not pallet_type or pallet_type == 'TRANSFER':
        pallet_type = 'Surowiec'

    if isinstance(identifier, str) and identifier.isdigit():
        pallet_id_val = int(identifier)
    else:
        pallet_id_val = identifier

    amount = data.get('amount')
    if amount is None:
        amount = data.get('amount_to_move')

    res = WarehouseV2Service.move_pallet(
        pallet_id=pallet_id_val,
        pallet_type=pallet_type,
        new_location=nowa_lokalizacja,
        worker_login=_worker(),
        linia=linia,
        amount_to_move=float(amount) if amount is not None else None,
    )
    if isinstance(res, tuple) and len(res) == 3:
        ok, msg, split_info = res
    else:
        ok, msg = res[0], res[1]
        split_info = None
    return jsonify({'success': ok, 'message': msg, 'split_info': split_info})


# ─────────────────────────────────────────────────────────────────────────────
# Print label
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/label/<path:identifier>')
def label(identifier):
    """Renderuje etykietę ZPL dla palety/surowca/wyrobu gotowego (podgląd i druk przez przeglądarkę)."""
    linia = request.args.get('linia', 'AGRO')
    autoprint = request.args.get('autoprint', '0') == '1'
    pallet_type = request.args.get('pallet_type')
    
    label_data = ScannerService.get_label_data(identifier, linia=linia, pallet_type=pallet_type)
    if not label_data:
        return f"Paleta {identifier} nie istnieje lub stan=0", 404

    from app.services.print_server import get_printer
    from datetime import datetime

    printer = get_printer()
    if label_data.get('is_finished_product') or label_data.get('typ') == 'WYRÓB GOTOWY':
        zpl_string = printer.build_finished_product_label_zpl(label_data)
    else:
        zpl_string = printer.build_pallet_label_zpl(label_data)

    return render_template(
        'magazyn_dostawy/etykieta_podglad_system.html',
        zpl_string=zpl_string,
        nr_palety=label_data.get('nr_palety') or str(identifier),
        linia=linia,
        generated_at=datetime.now().strftime('%d.%m.%Y %H:%M'),
        autoprint=autoprint
    )


# ─────────────────────────────────────────────────────────────────────────────
# Print label
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/label_location')
def label_location():
    loc = request.args.get('loc', 'BRAK')
    linia = request.args.get('linia', 'AGRO')
    
    zpl = f"^XA^CI28^PW812^LL1214^FO20,20^GB772,1174,4^FS"
    zpl += f"^FO60,100^A0N,100,100^FDREGAŁ: {loc}^FS"
    zpl += f"^FO60,250^BY4^BQN,2,10^FDMA,{loc}^FS"
    zpl += "^XZ"
    
    return render_template(
        'magazyn_dostawy/etykieta_podglad_system.html',
        zpl_string=zpl,
        print_url=f"/agro/scanner/print_location_direct?loc={loc}&linia={linia}",
        close_btn=True
    )

@scanner_bp.route('/print_location_direct', methods=['POST'])
def print_location_direct():
    loc = request.args.get('loc', 'BRAK')
    printer = get_printer()
    ok, msg = printer.print_location_label({'lokalizacja': loc})
    return jsonify({'success': ok, 'message': msg})

@scanner_bp.route('/print', methods=['POST'])
def print_label():
    data = request.get_json(silent=True) or {}
    sscc         = data.get('sscc') or data.get('nr_palety')
    surowiec_id  = data.get('surowiec_id')
    pallet_type  = data.get('pallet_type')
    label_type   = data.get('type', 'pallet')   # 'pallet' | 'location'
    linia        = data.get('linia', 'AGRO')
    printer_ip   = data.get('printer_ip') or data.get('override_ip')
    printer_name = data.get('printer_name') or data.get('override_name')
    copies       = int(data.get('copies') or 2)

    identifier = sscc or surowiec_id
    if not identifier:
        return jsonify({'success': False, 'error': 'Brak identyfikatora palety (SSCC/ID)'}), 400

    label_data = ScannerService.get_label_data(identifier, linia=linia, pallet_type=pallet_type)
    if not label_data:
        return jsonify({'success': False, 'error': f'Nie znaleziono palety: {identifier}'}), 404

    # Try TCP printer first
    printer = get_printer()
    ok, msg = False, ''
    job_id = None
    try:
        if label_type == 'location':
            ok, msg = printer.print_location_label(label_data)
        elif label_data.get('is_finished_product') or label_data.get('typ') == 'WYRÓB GOTOWY':
            ok, msg = printer.print_finished_product_label(
                label_data,
                override_ip=printer_ip,
                override_name=printer_name,
                copies=copies
            )
        else:
            ok, msg = printer.print_pallet_label(
                label_data, 
                override_ip=printer_ip, 
                override_name=printer_name,
                copies=copies
            )
        job_id = getattr(printer, 'last_job_id', None)
    except Exception as e:
        ok, msg = False, str(e)

    # Always return label URL so frontend can open it
    safe_id = label_data.get('nr_palety') or label_data.get('id') or identifier
    label_url = f"/agro/scanner/label/{safe_id}?linia={linia}&autoprint=1"
    return jsonify({
        'success': ok,
        'message': msg,
        'job_id': job_id,
        'printer_name': printer_name or '',
        'printer_ip': printer_ip or '',
        'label_url': label_url
    })


@scanner_bp.route('/test-print', methods=['POST'])
def test_print():
    """Wysyła demo etykietę do drukarki przez mostek (backend-to-backend)."""
    printer = get_printer()
    label_data = {
        'id': '99999',
        'nazwa': 'PRODUKT TESTOWY 4x6',
        'ilosc': 1234.5,
        'lokalizacja': 'TEST-01',
        'partia': 'BATCH-TEST-2024',
        'data': datetime.now().strftime('%Y-%m-%d'),
        'termin': '2025-12-31',
        'uwagi': 'To jest wydruk testowy nowego formatu 4x6 cala (812x1214 dots).'
    }
    ok, msg = printer.print_pallet_label(label_data)
    return jsonify({'success': ok, 'message': msg})



# ─────────────────────────────────────────────────────────────────────────────
# Printer status
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/printer/status', methods=['GET'])
def printer_status():
    ok, msg = get_printer().test_connection()
    return jsonify({'online': ok, 'message': msg})

@scanner_bp.route('/printers', methods=['GET'])
def get_printers():
    from app.db import get_db_connection
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1")
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify([])
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Scanner UI
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/ui')
def scanner_ui():
    linia = request.args.get('linia', 'AGRO').upper()
    return render_template('scanner/index.html', linia=linia)


@scanner_bp.route('/simulator')
def scanner_simulator():
    linia = request.args.get('linia', 'AGRO').upper()
    printer_ip = get_printer().printer_ip
    return render_template('scanner/simulator.html', linia=linia, printer_ip=printer_ip)


