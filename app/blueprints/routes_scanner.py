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
from app.services.scanner_service import ScannerService
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
    ilosc       = data.get('ilosc')
    linia       = data.get('linia', 'AGRO')
    plan_id     = data.get('plan_id')
    zbiornik    = data.get('zbiornik')
    komentarz   = data.get('komentarz')

    if not surowiec_id or ilosc is None:
        return jsonify({'success': False, 'error': 'Brak parametrów: surowiec_id, ilosc'}), 400

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
    )
    return jsonify({'success': ok, 'message': msg})


# ─────────────────────────────────────────────────────────────────────────────
# Split pallet
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/split', methods=['POST'])
def split():
    data = request.get_json(silent=True) or {}
    surowiec_id = data.get('surowiec_id')
    bags        = data.get('bags', [])          # [{ilosc, lokalizacja, nazwa?}, ...]
    linia       = data.get('linia', 'AGRO')

    if not surowiec_id:
        return jsonify({'success': False, 'error': 'Brak surowiec_id'}), 400
    if not bags:
        return jsonify({'success': False, 'error': 'Brak listy worków (bags)'}), 400

    ok, msg, new_pallets = ScannerService.split_pallet(
        surowiec_id=int(surowiec_id),
        bags=bags,
        worker_login=_worker(),
        linia=linia,
    )
    return jsonify({'success': ok, 'message': msg, 'new_pallets': new_pallets})


# ─────────────────────────────────────────────────────────────────────────────
# Print label
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/label/<int:surowiec_id>')
def label(surowiec_id):
    """Renderuje etykietę HTML dla surowca (do druku przez przeglądarkę)."""
    linia = request.args.get('linia', 'AGRO')
    label_data = ScannerService.get_label_data(surowiec_id, linia=linia)
    if not label_data:
        return f"Paleta #{surowiec_id} nie istnieje lub stan=0", 404

    from datetime import datetime
    return render_template(
        'agro_surowiec_etykieta.html',
        id=label_data['id'],
        nazwa=label_data['nazwa'],
        ilosc=label_data['ilosc'],
        lokalizacja=label_data['lokalizacja'],
        data=datetime.now().strftime('%d.%m.%Y %H:%M'),
        termin=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Print label (ZPL — optional TCP printer)
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/print', methods=['POST'])
def print_label():
    data = request.get_json(silent=True) or {}
    surowiec_id  = data.get('surowiec_id')
    label_type   = data.get('type', 'pallet')   # 'pallet' | 'location'
    linia        = data.get('linia', 'AGRO')

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
            ok, msg = printer.print_pallet_label(label_data)
    except Exception as e:
        ok, msg = False, str(e)

    # Always return label URL so frontend can open it
    label_url = f"/agro/scanner/label/{surowiec_id}?linia={linia}&autoprint=1"
    return jsonify({'success': ok, 'message': msg, 'label_url': label_url})



# ─────────────────────────────────────────────────────────────────────────────
# Printer status
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/printer/status', methods=['GET'])
def printer_status():
    ok, msg = get_printer().test_connection()
    return jsonify({'online': ok, 'message': msg})


# ─────────────────────────────────────────────────────────────────────────────
# Scanner UI
# ─────────────────────────────────────────────────────────────────────────────

@scanner_bp.route('/ui')
def scanner_ui():
    linia = request.args.get('linia', 'AGRO').upper()
    return render_template('scanner/index.html', linia=linia)
