from flask import render_template, request, jsonify, redirect, url_for, current_app, session
import traceback
from app.db import get_db_connection, get_table_name
from app.decorators import login_required
from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
from app.services.magazyn_dostawy.delivery_command_service import DeliveryCommandService
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.magazyn_dostawy.location_service import LocationService
from app.utils.pallet_label import prepare_pallet_label_data
from app.utils.pallet_id import generate_pallet_id
from ..config import (
    LOKALIZACJE_SZCZEGOLOWE, BUFORY, LOKALIZACJE, LOKALIZACJE_CEL,
    _safe_float, _safe_datetime_str, _format_label_weight
)
import json
from datetime import datetime
from ..base import magazyn_dostawy_bp

@magazyn_dostawy_bp.route('/api/zapisz', methods=['POST'])
def zapisz_dostawe():
    success, result = DeliveryCommandService.save_dostawa(request.json, session.get('login', 'system'))
    if success:
        dostawa_id = result
        is_external = bool(request.json.get('supplier')) or not request.json.get('lokalizacja_z')
        
        # Drukujemy od razu po etapie 1 TYLKO dla dostaw zewnętrznych.
        # Przesunięcia wewnętrzne drukują się dopiero po etapie 2 (przyjęciu).
        # Auto-print disabled - report available in delivery list for manual viewing

        return jsonify({"success": True, "id": result})
    return jsonify({"success": False, "error": result}), 500

@magazyn_dostawy_bp.route('/api/przyjmij-pozycje/<dostawa_id>', methods=['POST'])
def przyjmij_pozycje(dostawa_id):
    data = request.json
    printer_id = data.get('printer_id')
    
    printer_ip = None
    printer_name = None
    if printer_id:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s", (printer_id,))
            printer_info = cursor.fetchone()
            if printer_info:
                printer_ip = printer_info['ip']
                printer_name = printer_info['nazwa']
        except Exception as e:
            print(f"Error loading printer in route: {e}")
        finally:
            conn.close()

    # Sprawdź uprawnienia do ręcznego zatwierdzania w przesunięciu wewnętrznym
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT lokalizacja_z, items FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
        chk_d = cursor.fetchone()
        if chk_d and chk_d.get('lokalizacja_z'): # to jest przesunięcie wewnętrzne
            user_role = str(session.get('rola') or session.get('role') or '').lower().strip()
            if user_role not in ['masteradmin', 'admin', 'zarzad']:
                return jsonify({'success': False, 'error': 'Brak uprawnień. W przesunięciu magazynowym przyjęcie jest możliwe wyłącznie poprzez zeskanowanie palety skanerem.'}), 403
    finally:
        conn.close()

    success, error, result = AcceptanceService.accept_item(
        dostawa_id, 
        data.get('item_id'), 
        data.get('lokalizacja', '').strip(), 
        session.get('login', 'system'),
        nr_partii=data.get('nr_partii'),
        data_produkcji=data.get('data_produkcji'),
        data_przydatnosci=data.get('data_przydatnosci'),
        printer_ip=printer_ip,
        printer_name=printer_name
    )
    if success:
        return jsonify({
            "success": True,
            "all_accepted": result["all_accepted"],
            "accepted_count": result["accepted_count"],
            "total": result["total"],
            "report_url": None,
            "nr_palety": result.get("nr_palety"),
            "message": f"Przyjęto pomyślnie. SSCC: {result.get('nr_palety')}" if result.get("nr_palety") else "Przyjęto pomyślnie."
        })
    return jsonify({"success": False, "error": error}), 400

@magazyn_dostawy_bp.route('/api/odrzuc-pozycje/<dostawa_id>', methods=['POST'])
def odrzuc_pozycje(dostawa_id):
    data = request.json or {}
    success, error, result = AcceptanceService.reject_item(
        dostawa_id,
        data.get('item_id'),
        reason=data.get('reason', ''),
        login=session.get('login', 'system'),
    )

    if success:
        return jsonify({
            "success": True,
            "all_accepted": result.get('all_accepted', False),
            "all_processed": result.get('all_processed', False),
            "accepted_count": result.get('accepted_count', 0),
            "rejected_count": result.get('rejected_count', 0),
            "total": result.get('total', 0),
            "report_url": None,
            "message": "Pozycja została odrzucona.",
        })

    return jsonify({"success": False, "error": error}), 400

@magazyn_dostawy_bp.route('/api/przyjmij-wg', methods=['POST'])
def przyjmij_wg():
    data = request.json or {}
    pallet_id = data.get('id')
    lokalizacja = str(data.get('lokalizacja', '')).strip().upper()

    if not pallet_id:
        return jsonify({"success": False, "error": "Brak ID palety do przyjęcia."}), 400

    if not lokalizacja:
        return jsonify({"success": False, "error": "Podaj docelową lokalizację palety."}), 400

    waga_raw = data.get('waga')
    waga = None
    if waga_raw not in (None, ''):
        try:
            waga = float(str(waga_raw).replace(',', '.'))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Nieprawidłowa waga palety."}), 400
        if waga <= 0:
            return jsonify({"success": False, "error": "Waga palety musi być większa od zera."}), 400

    res = AcceptanceService.accept_production_pallet(
        pallet_id,
        lokalizacja,
        linia=data.get('linia', 'PSD').upper(),
        login=session.get('login', 'system'),
        confirmed_weight=waga,
    )
    success = res[0]
    msg = res[1]
    open_report_url = getattr(res, 'open_report_url', None)
    is_last_pallet = getattr(res, 'is_last_pallet', False)
    plan_id = getattr(res, 'plan_id', None)

    resp = {
        "success": success,
        "message": msg if success else None,
        "error": msg if not success else None
    }
    if open_report_url:
        resp["open_report_url"] = open_report_url
        resp["is_last_pallet"] = is_last_pallet
        resp["plan_id"] = plan_id
    return jsonify(resp)

@magazyn_dostawy_bp.route('/api/anuluj/<dostawa_id>', methods=['POST'])
def anuluj_dostawe(dostawa_id):
    success, msg = DeliveryCommandService.cancel_dostawa(dostawa_id, session.get('login', 'system'))
    return jsonify({"success": success, "message": msg})

@magazyn_dostawy_bp.route('/api/send-daily-report', methods=['POST'])
@login_required
def api_send_daily_report():
    """Wymusza wysyłkę e-mail dziennego raportu zbiorczego (dostawy i przesunięcia)."""
    data = request.json or {}
    date_str = data.get('date') or datetime.now().strftime('%Y-%m-%d')
    force = bool(data.get('force', True))
    from app.services.osip_report_email_service import OsipReportEmailService
    service = OsipReportEmailService()
    ok, msg = service.send_daily_warehouse_summary_report(date_str=date_str, force=force)
    return jsonify({"success": ok, "message": msg}), (200 if ok else 400)


@magazyn_dostawy_bp.route('/api/draft/lock', methods=['POST'])
def api_draft_lock():
    """Locks pallets present in a draft transfer list."""
    data = request.json or {}
    items = data.get('items') or []
    linia = data.get('linia', 'AGRO')
    login = session.get('login', 'system')
    success, msg = DeliveryCommandService.lock_draft_pallets(items, linia=linia, user_login=login)
    return jsonify({"success": success, "message": msg})


@magazyn_dostawy_bp.route('/api/draft/unlock', methods=['POST'])
def api_draft_unlock():
    """Unlocks pallets removed from a draft transfer list."""
    data = request.json or {}
    items = data.get('items') or []
    linia = data.get('linia', 'AGRO')
    login = session.get('login', 'system')
    success, msg = DeliveryCommandService.unlock_draft_pallets(items, linia=linia, user_login=login)
    return jsonify({"success": success, "message": msg})


@magazyn_dostawy_bp.route('/api/draft/sync', methods=['POST'])
def api_draft_sync():
    """Synchronizes draft items with active DB state (refreshes locations and locks pallets)."""
    data = request.json or {}
    items = data.get('items') or []
    linia = data.get('linia', 'AGRO')
    login = session.get('login', 'system')
    success, result = DeliveryCommandService.sync_draft_pallets(items, linia=linia, user_login=login)
    if success:
        return jsonify({"success": True, "result": result})
    return jsonify({"success": False, "error": str(result)}), 500


@magazyn_dostawy_bp.route('/api/live-transfer/init', methods=['POST'])
def api_live_transfer_init():
    """Initializes a new open live transfer order in the database."""
    data = request.json or {}
    linia = data.get('linia', 'AGRO')
    order_ref = data.get('order_ref')
    login = session.get('login', 'system')
    success, res = DeliveryCommandService.init_live_transfer(linia=linia, order_ref=order_ref, login=login)
    if success:
        return jsonify({"success": True, "result": res})
    return jsonify({"success": False, "error": str(res)}), 500


@magazyn_dostawy_bp.route('/api/live-transfer/add-item', methods=['POST'])
def api_live_transfer_add_item():
    """Adds a pallet to an active live transfer in real time."""
    data = request.json or {}
    dostawa_id = data.get('dostawa_id')
    item = data.get('item')
    linia = data.get('linia', 'AGRO')
    login = session.get('login', 'system')
    success, res = DeliveryCommandService.add_live_transfer_item(dostawa_id=dostawa_id, item=item, linia=linia, login=login)
    if success:
        return jsonify({"success": True, "result": res})
    return jsonify({"success": False, "error": str(res)}), 400


@magazyn_dostawy_bp.route('/api/live-transfer/remove-item', methods=['POST'])
def api_live_transfer_remove_item():
    """Removes a pallet from an active live transfer in real time."""
    data = request.json or {}
    dostawa_id = data.get('dostawa_id')
    item_id = data.get('item_id')
    nr_palety = data.get('nr_palety')
    linia = data.get('linia', 'AGRO')
    login = session.get('login', 'system')
    success, res = DeliveryCommandService.remove_live_transfer_item(
        dostawa_id=dostawa_id, item_id=item_id, nr_palety=nr_palety, linia=linia, login=login
    )
    if success:
        return jsonify({"success": True, "result": res})
    return jsonify({"success": False, "error": str(res)}), 400


@magazyn_dostawy_bp.route('/api/live-transfer/status/<dostawa_id>', methods=['GET'])
def api_live_transfer_status(dostawa_id):
    """Fetches live execution status and accepted pallets for an active transfer order."""
    success, res = DeliveryQueries.get_live_transfer_status(dostawa_id)
    if success:
        return jsonify({"success": True, "result": res})
    return jsonify({"success": False, "error": str(res)}), 404


@magazyn_dostawy_bp.route('/api/live-transfer/close/<dostawa_id>', methods=['POST'])
def api_live_transfer_close(dostawa_id):
    """Explicitly closes an active live transfer order."""
    login = session.get('login', 'system')
    success, msg = DeliveryCommandService.close_live_transfer(dostawa_id, login=login)
    if success:
        return jsonify({"success": True, "message": msg})
    return jsonify({"success": False, "error": str(msg)}), 400




