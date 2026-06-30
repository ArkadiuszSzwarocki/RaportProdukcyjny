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
from app.services.magazyny_nowe_service import MagazynyNoweService
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

    ok, msg = ScannerService.dispatch_to_production(
        surowiec_id=int(surowiec_id),
        ilosc=ilosc,
        worker_login=_worker(),
        linia=linia,
        plan_id=plan_id,
        zbiornik=zbiornik,
        komentarz=komentarz,
        pallet_type=pallet_type,
    )
    return jsonify({'success': ok, 'message': msg})


# ─────────────────────────────────────────────────────────────────────────────
# Move pallet
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/move', methods=['POST'])
def move():
    data = request.get_json(silent=True) or {}
    surowiec_id = data.get('surowiec_id')
    pallet_type = data.get('type')
    nowa_lokalizacja = data.get('lokalizacja')
    linia = data.get('linia', 'AGRO')

    if not surowiec_id or not nowa_lokalizacja:
        return jsonify({'success': False, 'error': 'Brak parametrów: surowiec_id, lokalizacja'}), 400

    # Default to Surowiec if no type is provided (for backward compatibility)
    if not pallet_type:
        pallet_type = 'Surowiec'

    ok, msg = MagazynyNoweService.move_pallet(
        pallet_id=int(surowiec_id),
        pallet_type=pallet_type,
        new_location=nowa_lokalizacja,
        worker_login=_worker(),
        linia=linia,
    )
    return jsonify({'success': ok, 'message': msg})


# ─────────────────────────────────────────────────────────────────────────────
# Print label
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/label/<int:surowiec_id>')
def label(surowiec_id):
    """Renderuje etykietę ZPL dla surowca (podgląd i druk przez przeglądarkę)."""
    linia = request.args.get('linia', 'AGRO')
    autoprint = request.args.get('autoprint', '0') == '1'
    label_data = ScannerService.get_label_data(surowiec_id, linia=linia)
    if not label_data:
        return f"Paleta #{surowiec_id} nie istnieje lub stan=0", 404

    from app.services.print_server import get_printer
    from datetime import datetime

    printer = get_printer()
    zpl_string = printer.build_pallet_label_zpl(label_data)

    return render_template(
        'magazyn_dostawy/etykieta_podglad_system.html',
        zpl_string=zpl_string,
        nr_palety=label_data.get('nr_palety') or f"SUR-{surowiec_id}",
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
    surowiec_id  = data.get('surowiec_id')
    label_type   = data.get('type', 'pallet')   # 'pallet' | 'location'
    linia        = data.get('linia', 'AGRO')
    printer_ip   = data.get('printer_ip')
    printer_name = data.get('printer_name')

    if not surowiec_id:
        return jsonify({'success': False, 'error': 'Brak surowiec_id'}), 400

    label_data = ScannerService.get_label_data(int(surowiec_id), linia=linia)
    if not label_data:
        return jsonify({'success': False, 'error': 'Nie znaleziono palety'}), 404

    # Try TCP printer first
    printer = get_printer()
    ok, msg = False, ''
    try:
        if label_type == 'location':
            ok, msg = printer.print_location_label(label_data)
        else:
            ok, msg = printer.print_pallet_label(
                label_data, 
                override_ip=printer_ip, 
                override_name=printer_name
            )
    except Exception as e:
        ok, msg = False, str(e)

    # Always return label URL so frontend can open it
    label_url = f"/agro/scanner/label/{surowiec_id}?linia={linia}&autoprint=1"
    return jsonify({'success': ok, 'message': msg, 'label_url': label_url})


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


