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
        report_url = None
        if result.get('all_accepted'):
            # Trigger background print
            from app.services.office_print_service import trigger_office_print_url
            
            # Determine if it's external delivery or internal transfer
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT typ_operacji FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
                d_row = cursor.fetchone()
                typ_operacji = d_row['typ_operacji'] if d_row else 'przesuniecie'
            except:
                typ_operacji = 'przesuniecie'
            finally:
                conn.close()
                
            report_type_str = 'raport_dostawy_zewnetrznej' if typ_operacji == 'dostawa_zewnetrzna' else 'raport_przesuniecia'
            
            # This is the exact URL that the frontend would open, but we use internal_print=1
            print_url = url_for(
                'magazyn_dostawy.raport_przesuniecia',
                dostawa_id=result.get('dostawa_id') or dostawa_id,
                linia=result.get('linia', 'PSD'),
                internal_print=1,
                _external=True
            )
            trigger_office_print_url(print_url, typ_raportu=report_type_str)
            
            # Still provide report_url to frontend so it can navigate back to list or show the report without autoprint
            report_url = url_for(
                'magazyn_dostawy.raport_przesuniecia',
                dostawa_id=result.get('dostawa_id') or dostawa_id,
                linia=result.get('linia', 'PSD')
            )

        return jsonify({
            "success": True,
            "all_accepted": result["all_accepted"],
            "accepted_count": result["accepted_count"],
            "total": result["total"],
            "report_url": report_url,
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
        report_url = None
        if result.get('all_processed'):
            # Determine if it's external delivery or internal transfer
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT typ_operacji FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
                d_row = cursor.fetchone()
                typ_operacji = d_row['typ_operacji'] if d_row else 'przesuniecie'
            except:
                typ_operacji = 'przesuniecie'
            finally:
                conn.close()
                
            report_type_str = 'raport_dostawy_zewnetrznej' if typ_operacji == 'dostawa_zewnetrzna' else 'raport_przesuniecia'
            
            from app.services.office_print_service import trigger_office_print_url
            print_url = url_for(
                'magazyn_dostawy.raport_przesuniecia',
                dostawa_id=result.get('dostawa_id') or dostawa_id,
                linia=result.get('linia', 'PSD'),
                internal_print=1,
                _external=True
            )
            trigger_office_print_url(print_url, typ_raportu=report_type_str)
            
            report_url = url_for(
                'magazyn_dostawy.raport_przesuniecia',
                dostawa_id=result.get('dostawa_id') or dostawa_id,
                linia=result.get('linia', 'PSD')
            )

        return jsonify({
            "success": True,
            "all_accepted": result.get('all_accepted', False),
            "all_processed": result.get('all_processed', False),
            "accepted_count": result.get('accepted_count', 0),
            "rejected_count": result.get('rejected_count', 0),
            "total": result.get('total', 0),
            "report_url": report_url,
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

