from flask import render_template, request, jsonify, redirect, url_for, current_app, session
import traceback
from app.decorators import login_required
from app.services.magazyn_dostawy.location_service import LocationService
from app.repositories.settings_repository import SettingsRepository
from ..config import (
    LOKALIZACJE_SZCZEGOLOWE, BUFORY, LOKALIZACJE, LOKALIZACJE_CEL,
    _safe_float, _safe_datetime_str, _format_label_weight
)
import json
from datetime import datetime
from ..base import magazyn_dostawy_bp

@magazyn_dostawy_bp.route('/api/sugerowane-lokalizacje')
def sugerowane_lokalizacje():
    linia = str(request.args.get('linia', 'PSD') or 'PSD').upper()
    prefix = (request.args.get('prefix', '') or '').strip()
    only_free_raw = str(request.args.get('only_free_for_racks', '1') or '1').strip().lower()
    only_free_for_racks = only_free_raw in ('1', 'true', 'yes', 'on', 'tak')

    try:
        limit = int(request.args.get('limit', '40'))
    except (TypeError, ValueError):
        limit = 40

    try:
        suggestions = LocationService.get_location_suggestions(
            prefix=prefix,
            linia=linia,
            only_free_for_racks=only_free_for_racks,
            limit=limit,
        )
        return jsonify({"success": True, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "suggestions": []}), 500

@magazyn_dostawy_bp.route('/ustawienia_lokalizacji')
@login_required
def ustawienia_lokalizacji():
    linia = request.args.get('linia', 'PSD').upper()
    if linia not in ['PSD', 'AGRO']:
        linia = 'PSD'
        
    lokalizacje = SettingsRepository.get_allowed_locations()
    return render_template('magazyn_dostawy/ustawienia_lokalizacji.html', linia=linia, lokalizacje=lokalizacje)

@magazyn_dostawy_bp.route('/api/ustawienia_lokalizacji', methods=['POST'])
@login_required
def api_add_lokalizacja():
    data = request.json
    nazwa = data.get('nazwa', '').strip().upper()
    opis = data.get('opis', '').strip()
    
    if not nazwa:
        return jsonify({'success': False, 'error': 'Nazwa lokalizacji jest wymagana.'}), 400
        
    try:
        success, message = SettingsRepository.add_allowed_location(nazwa, opis)
        if success:
            return jsonify({'success': True, 'message': message})
        return jsonify({'success': False, 'error': message}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@magazyn_dostawy_bp.route('/api/ustawienia_lokalizacji/<int:loc_id>', methods=['DELETE'])
@login_required
def api_delete_lokalizacja(loc_id):
    try:
        SettingsRepository.delete_allowed_location(loc_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@magazyn_dostawy_bp.route('/api/active-printers', methods=['GET'])
@login_required
def active_printers_api():
    """Zwraca połączoną listę drukarek z bazy danych (aktywnych) oraz drukarek sieciowych z mostka."""
    printers = []
    seen_ips = set()

    # 1. Najpierw pobieramy zdefiniowane i aktywne drukarki z bazy danych (priorytet)
    try:
        rows = SettingsRepository.get_active_printers()
        for r in rows:
            ip = str(r.get('ip') or '').strip()
            if not ip:
                continue
            printers.append({
                'id': r.get('id'),
                'selection_value': f"db:{r.get('id')}",
                'nazwa': r.get('nazwa'),
                'ip': ip,
                'lokalizacja': r.get('lokalizacja') or 'Baza danych',
                'source': 'db',
            })
            seen_ips.add(ip)
    except Exception as db_err:
        try:
            current_app.logger.warning('active_printers_api: error loading printers from DB: %s', db_err)
        except Exception:
            pass

    # 2. Następnie pobieramy drukarki sieciowe z mostka i dodajemy te, których nie ma w bazie
    try:
        from app.services.print_server import get_printer
        network_printers = get_printer().list_network_printers()
        for p in network_printers:
            ip = str(p.get('ip') or '').strip()
            if not ip or ip in seen_ips:
                continue
            nazwa = str(p.get('nazwa') or p.get('name') or f'Drukarka {ip}').strip()
            printers.append({
                'id': None,
                'selection_value': f'net:{ip}',
                'nazwa': nazwa,
                'ip': ip,
                'lokalizacja': str(p.get('lokalizacja') or 'Sieć').strip(),
                'source': 'network',
            })
            seen_ips.add(ip)
    except Exception as network_err:
        try:
            current_app.logger.warning('active_printers_api: network printers unavailable: %s', network_err)
        except Exception:
            pass

    return jsonify({'success': True, 'printers': printers})

