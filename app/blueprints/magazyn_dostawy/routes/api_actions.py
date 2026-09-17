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

    success, msg = AcceptanceService.accept_production_pallet(
        pallet_id,
        lokalizacja,
        linia=data.get('linia', 'PSD').upper(),
        login=session.get('login', 'system'),
        confirmed_weight=waga,
    )
    return jsonify({"success": success, "message": msg if success else None, "error": msg if not success else None})

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


# ======================== 4-STEP DELIVERY WORKFLOW ========================

@magazyn_dostawy_bp.route('/api/workflow/awizuj/<dostawa_id>', methods=['POST'])
def api_workflow_awizuj(dostawa_id):
    """Step 1: Confirm avization — verify WZ/ASN against physical delivery."""
    from app.services.magazyn_dostawy.commands.delivery_reception_workflow import (
        DeliveryReceptionWorkflow, DeliveryStatus
    )
    login = session.get('login', 'system')
    data = request.json or {}
    awizacja_ref = data.get('awizacja_ref', '')

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status, linia FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Nie znaleziono dostawy."}), 404

        current = row['status']
        valid, err = DeliveryReceptionWorkflow.validate_transition(current, DeliveryStatus.AWIZOWANE)
        if not valid:
            return jsonify({"success": False, "error": err}), 400

        cursor.execute("""
            UPDATE magazyn_dostawy
            SET status = %s, awizacja_ref = %s, awizacja_by = %s, awizacja_at = NOW()
            WHERE id = %s
        """, (DeliveryStatus.AWIZOWANE, awizacja_ref, login, dostawa_id))

        # Log to palety_historia for each item
        cursor.execute("SELECT items FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
        d = cursor.fetchone()
        items = json.loads(d['items'] or '[]') if d else []
        linia = row.get('linia') or 'PSD'
        for it in items:
            nr_p = it.get('nr_palety')
            if nr_p:
                cursor.execute(
                    "INSERT INTO palety_historia (nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'AWIZACJA', %s, %s, %s, %s)",
                    (nr_p, linia, 'surowiec', 'BRAMA', 'RAMPA', f"Awizacja dostawy WZ: {awizacja_ref}", login)
                )
        conn.commit()
        return jsonify({"success": True, "message": "Dostawa awizowana."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@magazyn_dostawy_bp.route('/api/workflow/etykiety/<dostawa_id>', methods=['POST'])
def api_workflow_etykiety(dostawa_id):
    """Step 2: Generate SSCC labels and move pallets to reception zone."""
    from app.services.magazyn_dostawy.commands.delivery_reception_workflow import (
        DeliveryReceptionWorkflow, DeliveryStatus, PalletItemStatus
    )
    from app.utils.pallet_id import generate_pallet_id

    login = session.get('login', 'system')
    data = request.json or {}
    printer_id = data.get('printer_id')

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
        dostawa = cursor.fetchone()
        if not dostawa:
            return jsonify({"success": False, "error": "Nie znaleziono dostawy."}), 404

        current = dostawa['status']
        valid, err = DeliveryReceptionWorkflow.validate_transition(current, DeliveryStatus.W_STREFIE_PRZYJEC)
        if not valid:
            return jsonify({"success": False, "error": err}), 400

        items = json.loads(dostawa['items'] or '[]')
        linia = dostawa.get('linia', 'PSD')
        strefa = dostawa.get('strefa_przyjec') or 'STREFA_PRZYJEC_01'
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        printer_ip = None
        printer_name = None
        if printer_id:
            cursor.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s", (printer_id,))
            pi = cursor.fetchone()
            if pi:
                printer_ip = pi['ip']
                printer_name = pi['nazwa']

        for it in items:
            if it.get('rejected'):
                continue
            if not it.get('nr_palety'):
                p_type = 'opakowanie' if it.get('packageForm') == 'packaging' else 'surowiec'
                it['nr_palety'] = generate_pallet_id(linia, type=p_type)
            it['sscc_generated_at'] = now_str
            it['sscc_generated_by'] = login
            it['pallet_status'] = PalletItemStatus.IN_RECEPTION_ZONE

            nr_p = it.get('nr_palety')
            if nr_p:
                cursor.execute(
                    "INSERT INTO palety_historia (nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'PZ_STREFA_PRZYJEC', %s, %s, %s, %s)",
                    (nr_p, linia, 'surowiec', 'DOSTAWA', strefa, f"Przyjęcie z dostawy do strefy przyjęć: {strefa}", login)
                )
                cursor.execute(
                    "INSERT INTO palety_historia (nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'SSCC_NADANIE', %s, %s, %s, %s)",
                    (nr_p, linia, 'surowiec', strefa, strefa, f"Nadanie SSCC: {nr_p}, strefa: {strefa}", login)
                )

        cursor.execute("""
            UPDATE magazyn_dostawy
            SET status = %s, items = %s
            WHERE id = %s
        """, (DeliveryStatus.W_STREFIE_PRZYJEC, json.dumps(items), dostawa_id))

        conn.commit()

        # Dispatch label printing in background
        if printer_ip and printer_name:
            from app.services.magazyn_dostawy.commands.pallet_print_dispatcher import PalletPrintDispatcher
            print_payloads = []
            for it in items:
                if it.get('rejected') or not it.get('nr_palety'):
                    continue
                try:
                    qty = float(it.get('quantity') or it.get('netWeight') or 0)
                    payload = PalletPrintDispatcher.build_pallet_payload(
                        printer_name, printer_ip,
                        'opakowanie' if it.get('packageForm') == 'packaging' else 'surowiec',
                        it, qty
                    )
                    print_payloads.append(payload)
                except Exception:
                    pass
            if print_payloads:
                PalletPrintDispatcher.dispatch_print_queue(print_payloads)

        return jsonify({
            "success": True,
            "message": f"Wygenerowano {len([i for i in items if not i.get('rejected')])} etykiet SSCC.",
            "items": items
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@magazyn_dostawy_bp.route('/api/workflow/putaway/<dostawa_id>', methods=['POST'])
def api_workflow_putaway(dostawa_id):
    """Step 3: Assign putaway tasks — system suggests locations for each pallet."""
    from app.services.magazyn_dostawy.commands.delivery_reception_workflow import (
        DeliveryReceptionWorkflow, DeliveryStatus, PalletItemStatus
    )
    from app.services.magazyn_dostawy.commands.putaway_suggestion_service import PutawaySuggestionService

    login = session.get('login', 'system')

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
        dostawa = cursor.fetchone()
        if not dostawa:
            return jsonify({"success": False, "error": "Nie znaleziono dostawy."}), 404

        current = dostawa['status']
        valid, err = DeliveryReceptionWorkflow.validate_transition(current, DeliveryStatus.PUTAWAY_IN_PROGRESS)
        if not valid:
            return jsonify({"success": False, "error": err}), 400

        items = json.loads(dostawa['items'] or '[]')
        linia = dostawa.get('linia', 'PSD')
        algorithm = dostawa.get('putaway_algorithm') or 'MANUAL'

        for it in items:
            if it.get('rejected') or it.get('putaway_confirmed_at'):
                continue
            suggested = PutawaySuggestionService.suggest_location(it, linia, algorithm)
            it['putaway_suggested_location'] = suggested
            it['pallet_status'] = PalletItemStatus.PUTAWAY_PENDING

            nr_p = it.get('nr_palety')
            if nr_p:
                loc_suggestion = suggested or 'MANUAL'
                cursor.execute(
                    "INSERT INTO palety_historia (nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'PUTAWAY_ZLECENIE', %s, %s, %s, %s)",
                    (nr_p, linia, 'surowiec', dostawa.get('strefa_przyjec') or 'STREFA_PRZYJEC_01', 'OCZEKUJĄCE', f"Putaway: przeniesienie do bufora OCZEKUJĄCE (sugestia: {loc_suggestion})", login)
                )

        cursor.execute("""
            UPDATE magazyn_dostawy
            SET status = %s, items = %s
            WHERE id = %s
        """, (DeliveryStatus.PUTAWAY_IN_PROGRESS, json.dumps(items), dostawa_id))

        conn.commit()
        return jsonify({
            "success": True,
            "message": "Zadania rozmieszczenia przydzielone.",
            "items": items
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@magazyn_dostawy_bp.route('/api/workflow/confirm-putaway/<dostawa_id>', methods=['POST'])
@magazyn_dostawy_bp.route('/api/dostawy/<dostawa_id>/confirm-putaway', methods=['POST'])
def api_workflow_confirm_putaway(dostawa_id):
    """Step 4: Confirm putaway for a single pallet — scan location barcode.

    This is the final step. Once all pallets are confirmed, delivery status becomes COMPLETED
    and the PZ document is generated.
    """
    from app.services.magazyn_dostawy.commands.delivery_reception_workflow import (
        DeliveryReceptionWorkflow, DeliveryStatus, PalletItemStatus
    )
    from app.services.magazyn_dostawy.commands.putaway_suggestion_service import PutawaySuggestionService

    login = session.get('login', 'system')
    data = request.json or {}
    item_id = data.get('item_id')
    scanned_location = str(data.get('lokalizacja', '')).strip().upper()
    strict_mode = bool(data.get('strict_mode', False))

    if not item_id:
        return jsonify({"success": False, "error": "Brak identyfikatora pozycji."}), 400
    if not scanned_location:
        return jsonify({"success": False, "error": "Zeskanuj kod lokalizacji docelowej."}), 400

    if strict_mode:
        conn_v = get_db_connection()
        try:
            cur_v = conn_v.cursor(dictionary=True)
            cur_v.execute("SELECT items, status FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            row_v = cur_v.fetchone()
            if not row_v:
                return jsonify({"success": False, "error": "Nie znaleziono dostawy."}), 404
            if str(row_v.get('status') or '').upper() != 'PUTAWAY_IN_PROGRESS':
                return jsonify({"success": False, "error": "Putaway można potwierdzać tylko dla statusu PUTAWAY_IN_PROGRESS."}), 400
            items_v = json.loads(row_v.get('items') or '[]')
            target_v = next((i for i in items_v if str(i.get('id')) == str(item_id)), None)
            if not target_v:
                return jsonify({"success": False, "error": "Nie znaleziono pozycji."}), 404
            suggested_v = target_v.get('putaway_suggested_location')
            if suggested_v:
                loc_valid_v, loc_msg_v = PutawaySuggestionService.validate_putaway_location(
                    scanned_location, suggested_v, strict_mode=True
                )
                if not loc_valid_v:
                    return jsonify({"success": False, "error": loc_msg_v}), 400
        finally:
            conn_v.close()

    # Delegate to AcceptanceService which handles inventory creation, location validation, and history logging
    printer_ip = None
    printer_name = None
    printer_id = data.get('printer_id')
    if printer_id:
        conn_p = get_db_connection()
        try:
            cur_p = conn_p.cursor(dictionary=True)
            cur_p.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s", (printer_id,))
            pi = cur_p.fetchone()
            if pi:
                printer_ip = pi['ip']
                printer_name = pi['nazwa']
        finally:
            conn_p.close()

    if not strict_mode:
        conn_v = get_db_connection()
        try:
            cur_v = conn_v.cursor(dictionary=True)
            cur_v.execute("SELECT status FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            row_v = cur_v.fetchone()
            if not row_v:
                return jsonify({"success": False, "error": "Nie znaleziono dostawy."}), 404
            if str(row_v.get('status') or '').upper() != 'PUTAWAY_IN_PROGRESS':
                return jsonify({"success": False, "error": "Putaway można potwierdzać tylko dla statusu PUTAWAY_IN_PROGRESS."}), 400
        finally:
            conn_v.close()

    success, error, result = AcceptanceService.accept_item(
        dostawa_id,
        item_id,
        scanned_location,
        login,
        nr_partii=data.get('nr_partii'),
        data_produkcji=data.get('data_produkcji'),
        data_przydatnosci=data.get('data_przydatnosci'),
        printer_ip=printer_ip,
        printer_name=printer_name
    )

    if not success:
        return jsonify({"success": False, "error": error}), 400

    # Update item-level putaway fields
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT items, status, linia, strefa_przyjec FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
        row = cursor.fetchone()
        if row:
            items = json.loads(row['items'] or '[]')
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for it in items:
                if str(it.get('id')) == str(item_id):
                    it['putaway_confirmed_location'] = scanned_location
                    it['putaway_confirmed_by'] = login
                    it['putaway_confirmed_at'] = now_str
                    it['pallet_status'] = PalletItemStatus.STORED

                    suggested = it.get('putaway_suggested_location')
                    if suggested:
                        loc_valid, loc_warn = PutawaySuggestionService.validate_putaway_location(
                            scanned_location, suggested, strict_mode=strict_mode
                        )
                        if loc_warn:
                            it['putaway_location_warning'] = loc_warn

                    # Log putaway confirmation
                    nr_p = it.get('nr_palety')
                    if nr_p:
                        linia = row.get('linia') or 'PSD'
                        cursor.execute(
                            "INSERT INTO palety_historia (nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'PUTAWAY_POTWIERDZENIE', %s, %s, %s, %s)",
                            (nr_p, linia, 'surowiec', 'OCZEKUJĄCE', scanned_location, f"Przesunięcie z bufora OCZEKUJĄCE na {scanned_location}", login)
                        )
                    break

            # Check if all items are confirmed → close delivery
            all_done = all(
                it.get('putaway_confirmed_at') or it.get('accepted') or it.get('rejected')
                for it in items
            )
            new_status = DeliveryStatus.COMPLETED if all_done else DeliveryStatus.PUTAWAY_IN_PROGRESS

            cursor.execute("""
                UPDATE magazyn_dostawy SET items = %s, status = %s WHERE id = %s
            """, (json.dumps(items), new_status, dostawa_id))
            conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    return jsonify({
        "success": True,
        "all_accepted": result.get("all_accepted", False),
        "accepted_count": result.get("accepted_count", 0),
        "total": result.get("total", 0),
        "nr_palety": result.get("nr_palety"),
        "message": f"Paleta rozmieszczona na {scanned_location}."
    })
