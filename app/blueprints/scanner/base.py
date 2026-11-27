# cspell:words skladniki
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
from app.services.print_server import get_printer, _zpl_text
from app.decorators import login_required_response

scanner_bp = Blueprint('scanner', __name__, url_prefix='/agro/scanner')


@scanner_bp.before_request
def require_scanner_login():
    denied = login_required_response()
    if denied is not None:
        return denied
    if not session.get('zalogowany'):
        # Header-only internal printing is limited to rendering labels.
        if request.endpoint in {'scanner.label', 'scanner.label_location'} and request.method in {'GET', 'HEAD'}:
            return None
        return jsonify(success=False, error='unauthenticated'), 401
    from app.core.scanner_permissions import enforce_scanner_permissions
    return enforce_scanner_permissions()


def _linia():
    return request.args.get('linia', request.json.get('linia', 'AGRO') if request.is_json else 'AGRO')


def _worker():
    return session.get('login', 'nieznany')


# ─────────────────────────────────────────────────────────────────────────────
# Lookup
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/pallet-suggestions', methods=['GET'])
def pallet_suggestions():
    import re
    from app.core.scanner_permissions import scanner_resource_read_allowed
    from app.services.scanner.scanner_suggestions_service import find_pallet_suggestions
    digits = request.args.get('digits', '').strip()
    if not re.fullmatch(r'[0-9]{6}', digits):
        return jsonify(success=False, message='Wpisz ostatnie 6 cyfr numeru palety.'), 400
    results = [row for row in find_pallet_suggestions(digits) if scanner_resource_read_allowed(row)]
    return jsonify(success=True, pallets=results[:30])


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

    from app.core.scanner_permissions import scanner_resource_read_allowed
    if not scanner_resource_read_allowed(pallet):
        return jsonify(success=False, error='forbidden'), 403
    # A shared shelf can contain stock with separate production permissions.
    for key in ('items', 'skladniki'):
        if isinstance(pallet.get(key), list):
            pallet[key] = [item for item in pallet[key] if scanner_resource_read_allowed(item)]

    return jsonify({'success': True, 'pallet': pallet})


@scanner_bp.route('/station-stock', methods=['GET'])
def get_station_stock():
    station_code = request.args.get('station', '').strip()
    linia = request.args.get('linia') or _linia()
    if not station_code:
        return jsonify({'success': False, 'error': 'Brak kodu stacji'}), 400

    from app.services.scanner.station_warehouse_material_service import StationWarehouseMaterialService
    data = StationWarehouseMaterialService.get_available_warehouse_materials_for_station(
        station_code=station_code,
        linia=linia
    )
    return jsonify({'success': True, 'data': data})


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
    raw_zbiornik = str(data.get('zbiornik') or '').strip().upper()
    surowiec_nazwa = str(data.get('surowiec_nazwa') or '').strip()
    surowiec_id = data.get('surowiec_id')
    pallet_type = data.get('pallet_type') or 'Surowiec'

    if not raw_zbiornik:
        return jsonify({'success': False, 'error': 'Brak kodu lokalizacji/stacji'}), 400

    from app.utils.location_validator import (
        is_production_tank_code,
        is_deleted_station_code,
        normalize_production_tank_code,
        validate_production_tank,
    )

    norm_zbiornik = normalize_production_tank_code(raw_zbiornik)

    if is_deleted_station_code(raw_zbiornik) or is_deleted_station_code(norm_zbiornik):
        return jsonify({
            'success': False,
            'is_production': True,
            'error': f'❌ Stacja {norm_zbiornik or raw_zbiornik} została wycofana/usunięta z systemu!'
        }), 400

    is_tank_ok, norm_zbiornik, tank_err = validate_production_tank(raw_zbiornik)
    if not is_tank_ok:
        return jsonify({
            'success': False,
            'is_production': True,
            'error': tank_err
        }), 400

    # Do stacji produkcyjnych nie wolno wydawać wyrobów gotowych ani opakowań
    if pallet_type == 'Wyrób Gotowy':
        return jsonify({
            'success': False,
            'is_production': True,
            'error': f'❌ Wyrobów gotowych nie można przekazać na stację produkcyjną ({norm_zbiornik})!'
        }), 400

    if pallet_type == 'Opakowanie':
        return jsonify({
            'success': False,
            'is_production': True,
            'error': f'❌ Opakowań nie można wydawać do stacji produkcyjnej ({norm_zbiornik})!'
        }), 400

    from app.services.tank_validation_service import TankValidationService
    is_valid, err_msg = TankValidationService.validate_tank_material(
        kod_zbiornika=norm_zbiornik,
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
        'normalized_station': norm_zbiornik,
        'message': 'OK'
    })


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch to production
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/dispatch', methods=['POST'])
def dispatch():
    data = request.get_json(silent=True) or {}
    surowiec_id = data.get('surowiec_id')
    pallet_type = data.get('type') or data.get('pallet_type')
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
            
            # 1. Drukowanie zaktualizowanej palety matki (2 sztuki z pozostałą ilością) — wyłącznie po unikalnym SSCC
            mother_sscc = str(extra_data.get('nr_palety') or '').strip()
            label_data = ScannerService.get_label_data(mother_sscc, linia=linia, pallet_type=pallet_type) if mother_sscc else None
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
        return jsonify(success=False, error=f"Paleta {identifier} nie istnieje lub stan=0"), 404

    from app.core.scanner_permissions import scanner_resource_read_allowed
    if not scanner_resource_read_allowed(label_data):
        return jsonify(success=False, error='forbidden'), 403

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
    safe_location = _zpl_text(loc, 60)
    linia = request.args.get('linia', 'AGRO')
    
    zpl = f"^XA^CI28^PW812^LL1214^FO20,20^GB772,1174,4^FS"
    zpl += f"^FO60,100^A0N,100,100^FDREGAŁ: {safe_location}^FS"
    zpl += f"^FO60,250^BY4^BQN,2,10^FDMA,{safe_location}^FS"
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
    if not sscc and not pallet_type and label_type != 'location':
        return jsonify({'success': False, 'error': 'Wymagany kod SSCC lub jawny typ palety przy druku etykiety'}), 400

    label_data = ScannerService.get_label_data(identifier, linia=linia, pallet_type=pallet_type)
    if not label_data:
        return jsonify({'success': False, 'error': f'Nie znaleziono palety: {identifier}'}), 404

    from app.core.scanner_permissions import scanner_resource_read_allowed
    if not scanner_resource_read_allowed(label_data):
        return jsonify(success=False, error='forbidden'), 403

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
    pt_query = f"&pallet_type={pallet_type}" if pallet_type else ""
    label_url = f"/agro/scanner/label/{safe_id}?linia={linia}&autoprint=1{pt_query}"
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

@scanner_bp.route('/split-tape-rolls', methods=['POST'])
def split_tape_rolls():
    """Rozbija paletę taśmy w magazyn_opakowania bezpośrednio na pojedyncze rolki (bez inwentaryzacji)."""
    import random
    import time
    from app.db import get_db_connection
    from app.services.inwentaryzacja_service import InwentaryzacjaService
    from app.services.warehouse_history.movement_recorder import MovementRecorder

    data = request.get_json(silent=True) or {}
    pallet_id = data.get('pallet_id') or data.get('surowiec_id') or data.get('id')
    nr_palety = str(data.get('nr_palety') or data.get('sscc') or '').strip()
    rolls_szt = data.get('rolls_szt')
    bag_weight_kg = data.get('bag_weight_kg')
    save_bag_weight = bool(data.get('save_bag_weight', False))
    print_labels = bool(data.get('print_labels', True))
    printer_ip = data.get('printer_ip') or data.get('override_ip')
    printer_name = data.get('printer_name') or data.get('override_name')
    copies = int(data.get('copies') or 2)
    worker = _worker()

    if not pallet_id and not nr_palety:
        return jsonify({'success': False, 'error': 'Brak identyfikatora palety taśmy.'}), 400
    if not isinstance(rolls_szt, list) or len(rolls_szt) < 2:
        return jsonify({'success': False, 'error': 'Podaj co najmniej 2 rolki do rozbicia.'}), 400

    cleaned_rolls = []
    for idx, raw_val in enumerate(rolls_szt, start=1):
        try:
            qty = int(round(float(str(raw_val).replace(',', '.'))))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': f'Nieprawidłowa ilość dla rolki #{idx}.'}), 400
        if qty <= 0:
            return jsonify({'success': False, 'error': f'Ilość dla rolki #{idx} musi być większa od 0.'}), 400
        cleaned_rolls.append(qty)

    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        if pallet_id:
            cur.execute("SELECT * FROM magazyn_opakowania WHERE id = %s LIMIT 1 FOR UPDATE", (pallet_id,))
        else:
            cur.execute("SELECT * FROM magazyn_opakowania WHERE UPPER(nr_palety) = %s LIMIT 1 FOR UPDATE", (nr_palety.upper(),))
        pal = cur.fetchone()
        if not pal:
            conn.rollback()
            return jsonify({'success': False, 'error': 'Nie znaleziono palety taśmy w magazynie opakowań.'}), 404

        old_qty = float(pal.get('stan_magazynowy') or 0)
        if old_qty <= 0:
            conn.rollback()
            return jsonify({'success': False, 'error': 'Paleta ma zerowy stan magazynowy.'}), 400

        pal_linia = pal.get('linia') or _linia()
        pal_loc = pal.get('lokalizacja') or 'MOP01'
        pal_pkg = pal.get('typ_opakowania') or 'Taśma'
        src_sscc = pal.get('nr_palety') or f"OPK-{pal['id']}"

        # 1. Roll #1 updates original pallet
        first_qty = cleaned_rolls[0]
        cur.execute(
            "UPDATE magazyn_opakowania SET stan_magazynowy = %s WHERE id = %s",
            (first_qty, pal['id']),
        )
        MovementRecorder.record_movement(
            pal['id'], pal_linia, 'opakowanie', 'ROZBICIE_ROLEK',
            pal_loc, pal_loc,
            f"Rozbicie palety taśmy na {len(cleaned_rolls)} rolek (Rolka #1: {old_qty:g} -> {first_qty} szt)",
            worker, src_sscc,
            cursor=cur, connection=conn,
            quantity_before=old_qty, quantity_after=first_qty,
        )

        result_rolls = [{
            'id': pal['id'],
            'nr_palety': src_sscc,
            'stan_magazynowy': first_qty,
            'is_source': True,
        }]

        # 2. Rolls #2..#N inserted as separate pallets in magazyn_opakowania
        base_ts = int(time.time() * 1000)
        for idx, roll_qty in enumerate(cleaned_rolls[1:], start=2):
            suffix = f"{(base_ts + idx) % 10000000000000:013d}{random.randint(10, 99)}"
            new_sscc = f"OPK000{suffix}"
            cur.execute(
                """
                INSERT INTO magazyn_opakowania
                    (nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci,
                     typ_opakowania, is_blocked, linia, is_loaded, is_depozyt)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, 0, 0)
                """,
                (
                    new_sscc, pal['nazwa'], roll_qty, pal_loc,
                    pal.get('nr_partii'), pal.get('data_produkcji'), pal.get('data_przydatnosci'),
                    pal_pkg, pal_linia,
                ),
            )
            new_id = cur.lastrowid
            MovementRecorder.record_movement(
                new_id, pal_linia, 'opakowanie', 'ROZBICIE_ROLEK',
                pal_loc, pal_loc,
                f"Rolka #{idx} z rozbicia palety {src_sscc} ({roll_qty} szt)",
                worker, new_sscc,
                cursor=cur, connection=conn,
                quantity_before=0, quantity_after=roll_qty,
            )
            result_rolls.append({
                'id': new_id,
                'nr_palety': new_sscc,
                'stan_magazynowy': roll_qty,
                'is_source': False,
            })

        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': f'Błąd rozbijania palety: {e}'}), 500
    finally:
        conn.close()

    if save_bag_weight and bag_weight_kg not in (None, ''):
        try:
            InwentaryzacjaService.save_tape_conversions_bulk(
                [{'nazwa': pal['nazwa'], 'waga_worka_kg': bag_weight_kg}],
                user_login=worker,
            )
        except Exception:
            pass

    printed_count = 0
    print_errors = []
    if print_labels:
        printer = get_printer()
        for r_item in result_rolls:
            try:
                lbl_data = ScannerService.get_label_data(r_item['nr_palety'], linia=pal_linia, pallet_type='opakowanie')
                if lbl_data:
                    ok, msg = printer.print_pallet_label(
                        lbl_data,
                        override_ip=printer_ip,
                        override_name=printer_name,
                        copies=copies,
                    )
                    if ok:
                        printed_count += 1
                    else:
                        print_errors.append(f"{r_item['nr_palety']}: {msg}")
            except Exception as pe:
                print_errors.append(f"{r_item['nr_palety']}: {pe}")

    total_szt = sum(cleaned_rolls)
    return jsonify({
        'success': True,
        'message': f"Rozbito na {len(cleaned_rolls)} rolek (razem {total_szt} szt)",
        'source_sscc': src_sscc,
        'rolls': result_rolls,
        'printed_count': printed_count,
        'print_errors': print_errors,
    })


@scanner_bp.route('/ui')
def scanner_ui():
    linia = request.args.get('linia', 'AGRO').upper()
    return render_template('scanner/index.html', linia=linia)


@scanner_bp.route('/simulator')
def scanner_simulator():
    linia = request.args.get('linia', 'AGRO').upper()
    printer_ip = get_printer().printer_ip
    return render_template('scanner/simulator.html', linia=linia, printer_ip=printer_ip)


