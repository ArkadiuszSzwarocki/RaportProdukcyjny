from datetime import datetime
import os
from flask import Blueprint, jsonify, request, session
from app.db import get_db_connection, get_table_name
from app.services.magazyny_nowe_service import MagazynyNoweService
from .blueprint import magazyny_nowe_bp

@magazyny_nowe_bp.route('/api/pallet/history', methods=['GET'])
def get_history():
    pallet_id = request.args.get('id')
    pallet_type = request.args.get('type')
    linia = request.args.get('linia', 'PSD')
    
    if not pallet_id or not pallet_type:
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    history = MagazynyNoweService.get_pallet_history(pallet_id, pallet_type, linia)
    return jsonify({'success': True, 'history': history})

@magazyny_nowe_bp.route('/api/pallet/move', methods=['POST'])
def move_pallet():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    new_location = data.get('location')
    linia = data.get('linia', 'PSD')
    amount = data.get('amount')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type, new_location]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.move_pallet(pallet_id, pallet_type, new_location, worker, linia, amount_to_move=amount)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/archive', methods=['POST'])
def archive_pallet():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.archive_pallet(pallet_id, pallet_type, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/dispatch', methods=['POST'])
def dispatch_pallet():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.dispatch_pallet(pallet_id, pallet_type, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/rename', methods=['POST'])
def rename_pallet():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    new_name = data.get('name')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type, new_name]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.rename_pallet(pallet_id, pallet_type, new_name, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/update-weight', methods=['POST'])
def update_weight():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    new_weight = data.get('weight')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type, new_weight is not None]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.update_weight(pallet_id, pallet_type, new_weight, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/toggle-block', methods=['POST'])
def toggle_block():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.toggle_block(pallet_id, pallet_type, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/return-to-raw', methods=['POST'])
def pallet_return_to_raw():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    linia = data.get('linia', 'PSD')
    worker = session.get('login', 'nieznany')
    
    if not all([pallet_id, pallet_type]):
        return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
        
    success, msg = MagazynyNoweService.return_pallet_to_raw(pallet_id, pallet_type, worker, linia)
    return jsonify({'success': success, 'message': msg})

@magazyny_nowe_bp.route('/api/pallet/print', methods=['POST'])
def print_pallet_label():
    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    printer_selection = data.get('printer_id')
    linia = data.get('linia', 'PSD')
    
    if not all([pallet_id, pallet_type, printer_selection]):
        return jsonify({'success': False, 'error': 'Brak parametrów (id, typ, drukarka)'}), 400
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        printer_ip = None
        printer_name = None
        
        printer_selection_str = str(printer_selection).strip()
        if printer_selection_str.startswith('net:'):
            printer_ip = printer_selection_str[4:].strip()
            printer_name = f"Drukarka {printer_ip}"
        elif printer_selection_str.startswith('db:'):
            db_id = printer_selection_str[3:].strip()
            cursor.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s", (db_id,))
            printer_info = cursor.fetchone()
            if printer_info:
                printer_ip = printer_info['ip']
                printer_name = printer_info['nazwa']
        else:
            # Fallback to pure numeric ID if possible
            try:
                db_id = int(printer_selection)
                cursor.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s", (db_id,))
                printer_info = cursor.fetchone()
                if printer_info:
                    printer_ip = printer_info['ip']
                    printer_name = printer_info['nazwa']
            except (ValueError, TypeError):
                # Try treating as IP directly
                if '.' in printer_selection_str:
                    printer_ip = printer_selection_str
                    printer_name = f"Drukarka {printer_ip}"
        
        if not printer_ip:
            return jsonify({'success': False, 'error': 'Nieprawidłowa lub nieaktywna drukarka w systemie'}), 404
            
        # Determine correct table
        if pallet_type == 'Wyrób Gotowy':
            table_mag = 'magazyn_palety' if linia == 'PSD' else 'magazyn_palety_agro'
            cursor.execute(f"SELECT produkt as productName, waga_netto as amount, nr_partii as batch, data_produkcji as date_prod, nr_palety, nr_plomby FROM {table_mag} WHERE id = %s", (pallet_id,))
        elif pallet_type == 'Surowiec':
            table = 'magazyn_surowce' if linia == 'PSD' else 'magazyn_surowce_agro'
            cursor.execute(f"SELECT nazwa as productName, stan_magazynowy as amount, nr_partii as batch, data_produkcji as date_prod, nr_palety FROM {table} WHERE id = %s", (pallet_id,))
        elif pallet_type == 'Opakowanie':
            table = 'magazyn_opakowania' if linia == 'PSD' else 'magazyn_opakowania_agro'
            cursor.execute(f"SELECT nazwa as productName, stan_magazynowy as amount, nr_partii as batch, data_produkcji as date_prod, nr_palety FROM {table} WHERE id = %s", (pallet_id,))
        elif pallet_type == 'Dodatek':
            cursor.execute(f"SELECT nazwa as productName, stan_magazynowy as amount, nr_partii as batch, data_produkcji as date_prod, nr_palety FROM magazyn_dodatki WHERE id = %s", (pallet_id,))
        else:
            return jsonify({'success': False, 'error': 'Nieznany typ palety'}), 400
            
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Nie znaleziono palety w bazie'}), 404
            
        from app.services.print_server import get_printer
        label_data = {
            'id': pallet_id,
            'nr_palety': row.get('nr_palety') or '',
            'nazwa': row['productName'],
            'ilosc': row['amount'],
            'data': row['date_prod'].strftime('%Y-%m-%d') if row.get('date_prod') else datetime.now().strftime('%Y-%m-%d'),
            'partia': row.get('batch') or f"{pallet_type[:3]}-{pallet_id}",
            'linia': linia,
            'nr_plomby': row.get('nr_plomby') if pallet_type == 'Wyrób Gotowy' else None
        }

        printer_service = get_printer()

        candidate_printers = []
        seen_printers = set()

        def _append_candidate(name, ip):
            key = (str(name or '').strip().lower(), str(ip or '').strip().lower())
            if key in seen_printers:
                return
            seen_printers.add(key)
            candidate_printers.append({'name': name, 'ip': ip})

        _append_candidate(printer_name, printer_ip)

        try:
            cursor.execute(
                """
                SELECT nazwa, ip
                FROM drukarki
                WHERE aktywna = 1
                ORDER BY
                    CASE
                        WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                        WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                        ELSE 2
                    END,
                    id ASC
                """
            )
            for row_printer in cursor.fetchall() or []:
                _append_candidate(row_printer.get('nazwa'), row_printer.get('ip'))
        except Exception as printer_list_err:
            print(f"Warning: could not list active printers for fallback: {printer_list_err}")

        _append_candidate(getattr(printer_service, 'printer_name', None), getattr(printer_service, 'printer_ip', None))

        if pallet_type == 'Wyrób Gotowy':
            zpl_payload = printer_service.build_finished_product_label_zpl(label_data)
        else:
            zpl_payload = printer_service.build_pallet_label_zpl(label_data)

        fallback_printers = []
        fallback_seen = set()
        for candidate in candidate_printers:
            final_name = str(candidate.get('name') or getattr(printer_service, 'printer_name', '') or '').strip() or 'Drukarka'
            final_ip = str(candidate.get('ip') or getattr(printer_service, 'printer_ip', '') or '').strip()
            if not final_ip:
                continue
            fallback_key = (final_name.lower(), final_ip.lower())
            if fallback_key in fallback_seen:
                continue
            fallback_seen.add(fallback_key)
            fallback_printers.append({'name': final_name, 'ip': final_ip})

        endpoint_entries = []
        endpoint_seen = set()

        def _append_bridge_endpoints(base_name, raw_base):
            base_value = str(raw_base or '').strip().rstrip('/')
            if not base_value:
                return

            lowered = base_value.lower()
            if lowered.endswith('/drukuj-zpl'):
                base_value = base_value[:-11]
            elif lowered.endswith('/status'):
                base_value = base_value[:-7]

            if '://' not in base_value:
                base_value = f'https://{base_value}'

            variants = [base_value]
            if base_value.lower().startswith('https://'):
                variants.append('http://' + base_value[8:])
            elif base_value.lower().startswith('http://'):
                variants.append('https://' + base_value[7:])

            for variant_index, variant_base in enumerate(variants, start=1):
                normalized_variant = variant_base.strip().rstrip('/')
                if not normalized_variant:
                    continue
                dedupe_key = normalized_variant.lower()
                if dedupe_key in endpoint_seen:
                    continue
                endpoint_seen.add(dedupe_key)
                suffix = '' if variant_index == 1 else '_alt'
                endpoint_entries.append(
                    {
                        'name': f'{base_name}{suffix}',
                        'endpoint': normalized_variant + '/drukuj-zpl',
                        'status_endpoint': normalized_variant + '/status',
                    }
                )

        shared_bridge_base = str(os.getenv('PRINTER_CLIENT_BRIDGE_URL', '') or '').strip().rstrip('/')
        if not shared_bridge_base:
            shared_bridge_base = str(os.getenv('PRINTER_BRIDGE_URL', '') or '').strip().rstrip('/')

        _append_bridge_endpoints('shared_bridge', shared_bridge_base)
        _append_bridge_endpoints('localhost_bridge', 'http://127.0.0.1:3001')

        local_bridge_fallback = None
        if fallback_printers:
            local_bridge_fallback = {
                'endpoint': endpoint_entries[0]['endpoint'],
                'status_endpoint': endpoint_entries[0]['status_endpoint'],
                'endpoints': endpoint_entries,
                'copies': 1,
                'zpl': zpl_payload,
                'printers': fallback_printers,
                'reason': 'server_printer_timeout',
            }

        ok = False
        msg = 'Błąd druku'
        used_name = printer_name
        used_ip = printer_ip

        for candidate_idx, candidate in enumerate(candidate_printers, start=1):
            candidate_name = candidate.get('name')
            candidate_ip = candidate.get('ip')
            if pallet_type == 'Wyrób Gotowy':
                print_ok, print_msg = printer_service.print_finished_product_label(
                    label_data,
                    override_ip=candidate_ip,
                    override_name=candidate_name,
                )
            else:
                print_ok, print_msg = printer_service.print_pallet_label(
                    label_data,
                    override_ip=candidate_ip,
                    override_name=candidate_name,
                )

            if print_ok:
                ok = True
                used_name = candidate_name or getattr(printer_service, 'printer_name', printer_name)
                used_ip = candidate_ip or getattr(printer_service, 'printer_ip', printer_ip)
                if candidate_idx > 1:
                    msg = f'Wysłano do drukarki {used_name} ({used_ip}) po fallbacku'
                else:
                    msg = f'Wysłano do drukarki {used_name} ({used_ip})'
                break

            msg = print_msg

        if ok:
            return jsonify({'success': True, 'message': msg, 'printer_name': used_name, 'printer_ip': used_ip})

        response_payload = {'success': False, 'message': msg, 'error': msg}
        if local_bridge_fallback:
            response_payload['local_bridge_fallback'] = local_bridge_fallback

        return jsonify(response_payload), 500
    except Exception as e:
        print(f"Error printing label: {e}")
        return jsonify({'success': False, 'message': str(e), 'error': str(e)}), 500
    finally:
        conn.close()

@magazyny_nowe_bp.route('/api/pallet/delete', methods=['POST'])
def delete_pallet():
    """Trwałe usunięcie palety z bazy danych (np. duplikaty testowe). Wymaga roli admin/masteradmin."""
    from flask import session as flask_session
    role = (flask_session.get('rola') or '').lower().replace(' ', '').replace('_', '').strip()
    if role not in ('masteradmin', 'admin', 'administrator'):
        return jsonify({'success': False, 'error': 'Brak uprawnień. Wymagana rola admin.'}), 403

    data = request.get_json()
    pallet_id = data.get('id')
    pallet_type = data.get('type')
    linia = data.get('linia', 'PSD')

    if not all([pallet_id, pallet_type]):
        return jsonify({'success': False, 'error': 'Brak parametrów id lub type'}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        if pallet_type in ('Surowiec',):
            table = get_table_name('magazyn_surowce', linia)
            col_amount = 'stan_magazynowy'
            col_name = 'nazwa'
        elif pallet_type in ('Opakowanie',):
            table = get_table_name('magazyn_opakowania', linia)
            col_amount = 'stan_magazynowy'
            col_name = 'nazwa'
        else:
            table = get_table_name('magazyn_palety', linia)
            col_amount = 'waga_netto'
            col_name = 'produkt'

        cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (pallet_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': f'Paleta ID {pallet_id} nie istnieje w tabeli {table}'}), 404

        # Archive before delete
        try:
            cursor.execute("""
                INSERT INTO magazyn_archiwum (original_id, nr_palety, nazwa, typ_palety, linia, waga_ostatnia, lokalizacja_ostatnia, user_login, komentarz)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (row['id'], row.get('nr_palety'), row.get(col_name), pallet_type, linia,
                  row.get(col_amount, 0), row.get('lokalizacja'), flask_session.get('login', 'admin'),
                  'USUNIĘTO: duplikat/paleta testowa'))
        except Exception as ae:
            print(f"Archive warning (non-fatal): {ae}")

        cursor.execute(f"DELETE FROM {table} WHERE id = %s", (pallet_id,))
        
        # Log to palety_historia - trwałe usunięcie
        try:
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, komentarz, user_login) VALUES (%s, %s, %s, 'USUNIECIE_TRWALE', %s, %s, %s)",
                (pallet_id, linia, pallet_type.lower(), row.get('lokalizacja'), f"Trwałe usunięcie palety: {row.get('nr_palety', pallet_id)}, powód: duplikat/testowa", flask_session.get('login', 'admin'))
            )
        except Exception as hist_err:
            print(f"History log warning: {hist_err}")
        
        conn.commit()
        return jsonify({'success': True, 'message': f'Paleta {row.get("nr_palety", pallet_id)} usunięta trwale.'})
    except Exception as e:
        conn.rollback()
        print(f"Error deleting pallet: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

