import re
from flask import render_template, request, jsonify, session, redirect, url_for, current_app, flash
from app.services.agro.agro_surowce_service import AgroSurowceService
from app.services.agro.agro_tanks_service import AgroTanksService
from app.services.dashboard_service import DashboardService
from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
from app.services.magazyn_dostawy.delivery_command_service import DeliveryCommandService
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.magazyn_dostawy.location_service import LocationService
from app.services.production_inventory_service import ProductionInventoryService
from app.decorators import login_required, roles_required, dynamic_role_required
from datetime import datetime, date
from app.db import get_db_connection, get_table_name
from .blueprint import agro_warehouse_bp

@agro_warehouse_bp.route('/agro/magazyn/inwentaryzacja-produkcji')
@login_required
@dynamic_role_required('magazyn.inventory')
def production_inventory_page():
    linia = request.args.get('linia', 'AGRO').upper()
    active_sessions = ProductionInventoryService.get_active_sessions(linia=linia)
    sessions = ProductionInventoryService.get_all_sessions(linia=linia, limit=100)
    return render_template('agro_warehouse/production_inventory_sessions.html', linia=linia, rola=session.get('rola'), active_sessions=active_sessions, sessions=sessions)

@agro_warehouse_bp.route('/agro/magazyn/inwentaryzacja-produkcji/start', methods=['POST'])
@login_required
@dynamic_role_required('magazyn.inventory')
def start_production_inventory():
    linia = request.args.get('linia', 'AGRO').upper()
    lokalizacja = request.form.get('lokalizacja', '').strip()
    comment = request.form.get('comment', '').strip()
    user_login = session.get('login', 'system')
    if not lokalizacja:
        flash('Lokalizacja jest wymagana', 'error')
        return redirect(url_for('agro_warehouse.production_inventory_page', linia=linia))
    success, result = ProductionInventoryService.start_session(linia, user_login, lokalizacja, comment)
    if success:
        return redirect(url_for('agro_warehouse.skaner_production_inventory', sesja_id=result, linia=linia))
    else:
        flash(f'Błąd przy tworzeniu sesji: {result}', 'error')
        return redirect(url_for('agro_warehouse.production_inventory_page', linia=linia))

@agro_warehouse_bp.route('/agro/magazyn/inwentaryzacja-produkcji/skaner/<int:sesja_id>')
@login_required
@dynamic_role_required('magazyn.inventory')
def skaner_production_inventory(sesja_id):
    import re
    linia = request.args.get('linia', 'AGRO').upper()
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM magazyn_inwentaryzacja_produkcji_sesje WHERE id = %s', (sesja_id,))
        sesj = cursor.fetchone()
        if not sesj:
            flash('Nie znaleziono sesji', 'error')
            return redirect(url_for('agro_warehouse.production_inventory_page', linia=linia))
    finally:
        conn.close()
    entries = ProductionInventoryService.get_session_entries(sesja_id)

    def get_group(tank):
        m = re.match('([A-Z]+)[ -]?(\\d+)', tank.upper())
        if not m:
            return None
        prefix = m.group(1)
        num = int(m.group(2))
        if prefix == 'BB':
            if 1 <= num <= 6:
                return 'Waga01'
            if 11 <= num <= 14:
                return 'Waga02'
            if 15 <= num <= 22:
                return 'Waga03'
            return None
        if prefix == 'MZ':
            if 7 <= num <= 10:
                return 'Waga02'
            if 23 <= num <= 24:
                return 'Waga03'
            return None
        if prefix == 'KO':
            if 1 <= num <= 12:
                return 'KO - Rząd 1'
            if 13 <= num <= 24:
                return 'KO - Rząd 2'
            return None
        return None
    grouped_entries = {}
    for entry in entries:
        g = get_group(entry.get('zbiornik', ''))
        if g is not None:
            if g not in grouped_entries:
                grouped_entries[g] = []
            grouped_entries[g].append(entry)
    sorted_groups = {}
    for k in sorted(grouped_entries.keys()):
        sorted_groups[k] = grouped_entries[k]
    return render_template('agro_warehouse/production_inventory_skaner.html', sesja_id=sesja_id, linia=linia, sesja=sesj, grouped_entries=sorted_groups)

@agro_warehouse_bp.route('/agro/api/inwentaryzacja-produkcji/zapisz', methods=['POST'])
@login_required
@dynamic_role_required('magazyn.inventory')
def save_production_inventory_entries():
    data = request.json
    sesja_id = data.get('sesja_id')
    updates = data.get('updates', [])
    user_login = session.get('login', 'system')
    success, msg = ProductionInventoryService.update_entries(sesja_id, updates, user_login)
    return jsonify({'success': success, 'message': msg})

@agro_warehouse_bp.route('/agro/api/inwentaryzacja-produkcji/zmien-surowiec', methods=['POST'])
@login_required
@dynamic_role_required('magazyn.inventory')
def change_production_inventory_material():
    data = request.json
    sesja_id = data.get('sesja_id')
    entry_id = data.get('entry_id')
    nowy_surowiec = data.get('nowy_surowiec')
    paleta_id = data.get('paleta_id')
    nr_palety = data.get('nr_palety')
    nr_partii = data.get('nr_partii')
    data_produkcji = data.get('data_produkcji')
    data_przydatnosci = data.get('data_przydatnosci')
    waga_faktyczna = data.get('waga_faktyczna')
    if data_produkcji == '':
        data_produkcji = None
    if data_przydatnosci == '':
        data_przydatnosci = None
    if waga_faktyczna in (None, ''):
        waga_faktyczna = None
    else:
        try:
            waga_faktyczna = float(str(waga_faktyczna).replace(',', '.'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Nieprawidłowy stan faktyczny.'})
    user_login = session.get('login', 'system')
    success, msg = ProductionInventoryService.update_material(sesja_id, entry_id, nowy_surowiec, user_login, paleta_id=paleta_id, nr_palety=nr_palety, nr_partii=nr_partii, data_produkcji=data_produkcji, data_przydatnosci=data_przydatnosci, waga_faktyczna=waga_faktyczna)
    return jsonify({'success': success, 'message': msg})

@agro_warehouse_bp.route('/agro/magazyn/inwentaryzacja-produkcji/raport/<int:sesja_id>')
@login_required
@dynamic_role_required('magazyn.inventory')
def raport_production_inventory(sesja_id):
    import re
    linia = request.args.get('linia', 'AGRO').upper()
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM magazyn_inwentaryzacja_produkcji_sesje WHERE id = %s', (sesja_id,))
        sesj = cursor.fetchone()
    finally:
        conn.close()
    entries = ProductionInventoryService.get_session_entries(sesja_id)

    def is_valid_group(tank):
        m = re.match('([A-Z]+)[ -]?(\\d+)', tank.upper())
        if not m:
            return False
        prefix = m.group(1)
        num = int(m.group(2))
        if prefix == 'BB':
            if 1 <= num <= 6:
                return True
            if 11 <= num <= 14:
                return True
            if 15 <= num <= 22:
                return True
            return False
        if prefix == 'MZ':
            if 7 <= num <= 10:
                return True
            if 23 <= num <= 24:
                return True
            return False
        if prefix == 'KO':
            if 1 <= num <= 12:
                return True
            if 13 <= num <= 24:
                return True
            return False
        return False
    filtered_entries = [e for e in entries if is_valid_group(e.get('zbiornik', ''))]
    return render_template('agro_warehouse/production_inventory_raport.html', sesja_id=sesja_id, linia=linia, sesja=sesj, entries=filtered_entries)

@agro_warehouse_bp.route('/agro/api/inwentaryzacja-produkcji/zamknij', methods=['POST'])
@login_required
@dynamic_role_required('magazyn.inventory')
def close_production_inventory():
    sesja_id = request.json.get('sesja_id')
    success, msg = ProductionInventoryService.close_session(sesja_id)
    if success:
        from app.services.office_print_service import trigger_office_print_url
        print_url = url_for('agro_warehouse.raport_production_inventory', sesja_id=sesja_id, linia=request.args.get('linia', 'AGRO').upper(), internal_print=1, _external=True)
        trigger_office_print_url(print_url, typ_raportu='raport_przyjecia_z_produkcji')
    return jsonify({'success': success, 'message': msg})

@agro_warehouse_bp.route('/agro/api/inwentaryzacja-produkcji/zatwierdz', methods=['POST'])
@login_required
@dynamic_role_required('magazyn.inventory')
def apply_production_inventory():
    sesja_id = request.json.get('sesja_id')
    user_login = session.get('login', 'system')
    success, msg = ProductionInventoryService.apply_inventory(sesja_id, user_login)
    return jsonify({'success': success, 'message': msg})

@agro_warehouse_bp.route('/agro/api/inwentaryzacja-produkcji/usun', methods=['POST'])
@login_required
@dynamic_role_required('magazyn.inventory')
def delete_production_inventory():
    sesja_id = request.json.get('sesja_id')
    success, msg = ProductionInventoryService.delete_session(sesja_id)
    return jsonify({'success': success, 'message': msg})

@agro_warehouse_bp.route('/agro/api/inwentaryzacja-produkcji/edytuj-sesje', methods=['POST'])
@login_required
@dynamic_role_required('magazyn.inventory')
def edit_production_inventory_session():
    data = request.json
    success, msg = ProductionInventoryService.edit_session(data.get('sesja_id'), data.get('lokalizacja'), data.get('comment'))
    return jsonify({'success': success, 'message': msg})

@agro_warehouse_bp.route('/agro/api/inwentaryzacja-produkcji/wznow-sesje', methods=['POST'])
@login_required
@dynamic_role_required('magazyn.inventory')
def resume_production_inventory_session():
    sesja_id = request.json.get('sesja_id')
    success, msg = ProductionInventoryService.resume_session(sesja_id)
    return jsonify({'success': success, 'message': msg})

@agro_warehouse_bp.route('/agro/api/inwentaryzacja-produkcji/cofnij-zatwierdzenie', methods=['POST'])
@login_required
@dynamic_role_required('magazyn.inventory')
def revert_production_inventory_session():
    sesja_id = request.json.get('sesja_id')
    success, msg = ProductionInventoryService.revert_session(sesja_id)
    return jsonify({'success': success, 'message': msg})

@agro_warehouse_bp.route('/agro/magazyn/inwentaryzacja-produkcji/historia/<tank_code>')
@login_required
@dynamic_role_required('magazyn.inventory')
def history_production_inventory(tank_code):
    linia = request.args.get('linia', 'AGRO')
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('\n            SELECT w.*, s.status, s.lokalizacja, s.comment \n            FROM magazyn_inwentaryzacja_produkcji_wpisy w\n            JOIN magazyn_inwentaryzacja_produkcji_sesje s ON w.sesja_id = s.id\n            WHERE w.zbiornik = %s AND s.linia = %s\n            ORDER BY w.data_wpisu DESC\n        ', (tank_code, linia))
        historia = cursor.fetchall()
        return jsonify({'success': True, 'historia': historia})
    finally:
        conn.close()

@agro_warehouse_bp.route('/agro/magazyn/inwentaryzacja-produkcji/historia-stara/<tank_code>')
@login_required
@dynamic_role_required('magazyn.inventory')
def production_inventory_tank_history(tank_code):
    linia = request.args.get('linia', 'Agro')
    normalized_tank = AgroTanksService.normalize_production_tank(tank_code)
    if not normalized_tank:
        return redirect(url_for('agro_warehouse.production_inventory_page', linia=linia))
    limit = min(int(request.args.get('limit', 300)), 2000)
    history_rows = AgroTanksService.get_production_tank_history(normalized_tank, limit=limit, linia=linia)
    return render_template('agro_warehouse/production_inventory_history.html', linia=linia, rola=session.get('rola'), tank_code=normalized_tank, history_rows=history_rows)

@agro_warehouse_bp.route('/agro/api/inventory', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def api_inventory():
    try:
        data = request.get_json()
        surowiec_id = data.get('surowiec_id')
        actual_qty = data.get('actual_qty')
        komentarz = data.get('komentarz')
        linia = data.get('linia', 'Agro')
        if not surowiec_id or actual_qty is None:
            return (jsonify({'success': False, 'error': 'Brak ID lub ilości'}), 400)
        try:
            qty = float(actual_qty)
        except Exception:
            return (jsonify({'success': False, 'error': 'Nieprawidłowa ilość'}), 400)
        worker = session.get('login')
        AgroSurowceService.adjust_inventory(surowiec_id, qty, worker, linia=linia, komentarz=komentarz)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f'Error in api_inventory: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/bulk_inventory', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def api_bulk_inventory():
    try:
        data = request.get_json()
        items = data.get('items', [])
        linia = data.get('linia', 'Agro')
        worker = session.get('login')
        updated_count = 0
        for it in items:
            s_id = it.get('surowiec_id')
            qty = it.get('actual_qty')
            note = it.get('komentarz', 'Inwentaryzacja zbiorcza')
            if s_id and qty is not None:
                AgroSurowceService.adjust_inventory(s_id, float(qty), worker, linia=linia, komentarz=note)
                updated_count += 1
        return jsonify({'success': True, 'updated': updated_count})
    except Exception as e:
        current_app.logger.error(f'Error in api_bulk_inventory: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/locations_inventory', methods=['GET'])
@login_required
def api_locations_inventory():
    try:
        linia = request.args.get('linia', 'Agro')
        rows = AgroSurowceService.get_inventory(linia=linia)
        items = []
        for r in rows:
            items.append({'id': r['id'], 'nazwa': r.get('nazwa'), 'lokalizacja': r.get('lokalizacja'), 'stan_magazynowy': float(r['stan_magazynowy']) if r.get('stan_magazynowy') is not None else 0})
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        current_app.logger.error(f'Error in api_locations_inventory: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/production_inventory', methods=['GET'])
@login_required
def api_production_inventory():
    try:
        linia = request.args.get('linia', 'Agro')
        limit = min(int(request.args.get('limit', 500)), 2000)
        items = AgroTanksService.get_production_inventory(limit=limit, linia=linia)
        return jsonify({'success': True, 'items': items, 'count': len(items)})
    except Exception as e:
        current_app.logger.error(f'Error in api_production_inventory: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/production_inventory_snapshot', methods=['GET'])
@login_required
def api_production_inventory_snapshot():
    try:
        linia = request.args.get('linia', 'Agro')
        limit = min(int(request.args.get('limit', 4000)), 8000)
        show_empty_raw = str(request.args.get('show_empty', '')).strip().lower()
        show_empty = show_empty_raw in ('1', 'true', 'yes', 'y', 'on')
        items = AgroTanksService.get_production_inventory_snapshot(limit=limit, linia=linia, show_empty=show_empty)
        return jsonify({'success': True, 'items': items, 'count': len(items)})
    except Exception as e:
        current_app.logger.error(f'Error in api_production_inventory_snapshot: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/api/production_inventory', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def api_adjust_production_inventory():
    try:
        data = request.get_json() or {}
        items = data.get('items', [])
        linia = data.get('linia', 'Agro')
        worker = session.get('login')
        if not isinstance(items, list):
            return (jsonify({'success': False, 'error': 'Pole items musi być listą.'}), 400)
        updated = 0
        errors = []
        for item in items:
            ruch_id = item.get('ruch_id')
            actual_qty = item.get('actual_qty')
            komentarz = item.get('komentarz', 'Inwentaryzacja produkcji')
            if not ruch_id or actual_qty is None:
                continue
            try:
                qty_val = float(actual_qty)
            except (TypeError, ValueError):
                errors.append({'ruch_id': ruch_id, 'error': 'Nieprawidłowa ilość'})
                continue
            if qty_val < 0:
                errors.append({'ruch_id': ruch_id, 'error': 'Ilość nie może być ujemna'})
                continue
            ok, err = AgroTanksService.adjust_production_inventory(ruch_id, qty_val, worker_login=worker, linia=linia, komentarz=komentarz)
            if ok:
                updated += 1
            else:
                errors.append({'ruch_id': ruch_id, 'error': err or 'Błąd zapisu'})
        if errors:
            return (jsonify({'success': False, 'updated': updated, 'errors': errors}), 400)
        return jsonify({'success': True, 'updated': updated})
    except Exception as e:
        current_app.logger.error(f'Error in api_adjust_production_inventory: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)
