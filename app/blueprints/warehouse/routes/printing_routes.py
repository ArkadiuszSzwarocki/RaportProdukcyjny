from datetime import date, datetime
import os
import threading

import mysql.connector
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required, masteradmin_required
from app.services.planning.status import PlanningStatusService
from app.utils.validation import require_field
from app.utils.pallet_id import generate_pallet_id

from .palety_helpers import _resolve_plan_id_for_paleta
from .misc_routes import _parse_data_produkcji_input

def _select_preferred_printer(cursor):
    """Pick production printer first, then fallback to any active printer."""
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
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            return None, None
        return row[0], row[1]
    except Exception as printer_err:
        current_app.logger.warning('Nie udało się pobrać preferowanej drukarki: %s', printer_err)
        return None, None

def _list_active_printers(cursor):
    """Return active printers in preferred order for automatic fallback attempts."""
    try:
        cursor.execute(
            """
            SELECT id, nazwa, ip
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
        return cursor.fetchall() or []
    except Exception as printer_err:
        current_app.logger.warning('Nie udało się pobrać listy drukarek aktywnych: %s', printer_err)
        return []

def register_printing_routes(warehouse_bp, *, resolve_request_linia, resolve_payload_linia, update_paleta_workowanie, update_paleta_magazyn, safe_return):

    @warehouse_bp.route('/api/printers', methods=['GET'])
    @login_required
    def api_printers():
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, nazwa, ip FROM drukarki WHERE aktywna = 1 ORDER BY nazwa")
            printers = cursor.fetchall()
            conn.close()
            return jsonify({'success': True, 'printers': printers})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    @warehouse_bp.route('/drukuj_etykiete/<int:paleta_id>', methods=['GET'])
    @login_required
    def drukuj_etykiete(paleta_id):
        """Generates a 100x150 mm printable label for a palette in Magazyn."""
        linia = str(resolve_request_linia()).upper()
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        table_zasypy = get_table_name('szarze', linia)
        table_mag = get_table_name('magazyn_palety', linia)
    
        conn = get_db_connection()
        cursor = conn.cursor()
    
        try:
            cursor.execute(
                f'''
                SELECT 
                    COALESCE(mp.plan_id, pw.plan_id) AS plan_id,
                    mp.waga_netto, 
                    COALESCE(p.produkt, pw_p.produkt, mp.produkt) AS produkt,
                    mp.paleta_workowanie_id,
                    pw.data_dodania
                FROM {table_mag} mp
                LEFT JOIN {table_plan} p ON mp.plan_id = p.id
                LEFT JOIN {table_pal} pw ON mp.paleta_workowanie_id = pw.id
                LEFT JOIN {table_plan} pw_p ON pw.plan_id = pw_p.id
                WHERE mp.id = %s
                ''',
                (paleta_id,),
            )
            row = cursor.fetchone()
    
            data_workowanie = None
    
            if row:
                plan_id, paleta_waga, produkt, workowanie_id, pw_data = row
                if pw_data:
                    data_workowanie = pw_data.strftime('%Y-%m-%d %H:%M:%S') if hasattr(pw_data, 'strftime') else str(pw_data)
                if plan_id:
                    if workowanie_id:
                        cursor.execute(
                            f'''
                            SELECT COALESCE(SUM(waga), 0) 
                            FROM {table_pal}
                            WHERE plan_id = %s AND id <= %s
                            ''',
                            (plan_id, workowanie_id),
                        )
                        cumulative_paleta_waga = cursor.fetchone()[0]
                    else:
                        cursor.execute(
                            f'''
                            SELECT COALESCE(SUM(waga_netto), 0) 
                            FROM {table_mag} 
                            WHERE plan_id = %s AND id <= %s
                            ''',
                            (plan_id, paleta_id),
                        )
                        cumulative_paleta_waga = cursor.fetchone()[0]
                else:
                    cumulative_paleta_waga = paleta_waga
            else:
                cursor.execute(
                    f'''
                    SELECT pw.plan_id, pw.waga, p.produkt, pw.data_dodania, pw.id
                    FROM {table_pal} pw
                    JOIN {table_plan} p ON pw.plan_id = p.id
                    WHERE pw.id = %s
                    ''',
                    (paleta_id,),
                )
                row = cursor.fetchone()
                if not row:
                    abort(404, description='Paleta nie znaleziona')
    
                work_plan_id, paleta_waga, produkt, pw_data, wk_id = row
                if pw_data:
                    data_workowanie = pw_data.strftime('%Y-%m-%d %H:%M:%S') if hasattr(pw_data, 'strftime') else str(pw_data)
    
                plan_id = work_plan_id
                workowanie_id = wk_id
    
                cursor.execute(
                    f'''
                    SELECT COALESCE(SUM(waga), 0) 
                    FROM {table_pal}
                    WHERE plan_id = %s AND id <= %s
                    ''',
                    (plan_id, paleta_id),
                )
                cumulative_paleta_waga = cursor.fetchone()[0]
    
            zasyp_nr = '?'
            zasyp_plan_id = None
    
            if plan_id:
                cursor.execute(f'SELECT zasyp_id FROM {table_plan} WHERE id = %s', (plan_id,))
                zasyp_check = cursor.fetchone()
                if zasyp_check and zasyp_check[0]:
                    zasyp_plan_id = zasyp_check[0]
                else:
                    zasyp_plan_id = plan_id
    
                cursor.execute(
                    f'''
                    SELECT id, waga, nr_szarzy
                    FROM {table_zasypy}
                    WHERE plan_id = %s 
                    ORDER BY data_dodania ASC, id ASC
                    ''',
                    (zasyp_plan_id,),
                )
                zasypy_rows = cursor.fetchall()
    
                cumulative_zasyp = 0
                for index, s_row in enumerate(zasypy_rows):
                    cumulative_zasyp += s_row[1]
                    zasyp_nr = s_row[2] if s_row[2] is not None else (index + 1)
                    if cumulative_zasyp >= cumulative_paleta_waga:
                        break
    
            # Obliczanie numeru Lp. palety w zleceniu
            nr_palety_lp = 'Brak'
            if plan_id:
                if workowanie_id:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, workowanie_id))
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_mag} WHERE plan_id = %s AND id <= %s", (plan_id, paleta_id))
                res_lp = cursor.fetchone()
                nr_palety_lp = res_lp[0] if res_lp else 1
    
            data_wydruku = datetime.now().strftime('%Y-%m-%d %H:%M')
            termin_przydatnosci = request.args.get('termin') or None
    
            return render_template(
                'warehouse/label.html',
                plan_id=zasyp_plan_id or 'Brak',
                produkt=produkt or 'Nieznany',
                nr_szarzy=zasyp_nr,
                waga=paleta_waga,
                nr_palety=nr_palety_lp,
                data_workowanie=data_workowanie or 'Ręczna paleta',
                data_wydruku=data_wydruku,
                termin_przydatnosci=termin_przydatnosci,
            )
        except HTTPException:
            raise
        except Exception as error:
            current_app.logger.exception('Error generating label for paleta %s: %s', paleta_id, error)
            abort(500, description='Wystąpił błąd przy generowaniu etykiety.')
        finally:
            cursor.close()
            conn.close()

    @warehouse_bp.route('/api/drukuj_etykiete_zpl/<int:paleta_id>', methods=['POST'])
    @login_required
    def drukuj_etykiete_zpl(paleta_id):
        """Send ZPL label via print bridge (2 copies)."""
        from app.services.print_server import get_printer
        linia = str(resolve_request_linia()).upper()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            payload = request.get_json(silent=True) or {}
            requested_printer_id = None
            requested_printer_ip = None
            requested_printer_name = None
            selected_printer_raw = None
            if isinstance(payload, dict):
                selected_printer_raw = payload.get('printer_id') or payload.get('printerId')
                requested_printer_ip = payload.get('printer_ip') or payload.get('printerIp')
                requested_printer_name = payload.get('printer_name') or payload.get('printerName')
            if selected_printer_raw in (None, ''):
                selected_printer_raw = request.form.get('printer_id') or request.args.get('printer_id')
            if requested_printer_ip in (None, ''):
                requested_printer_ip = request.form.get('printer_ip') or request.args.get('printer_ip')
            if requested_printer_name in (None, ''):
                requested_printer_name = request.form.get('printer_name') or request.args.get('printer_name')
    
            requested_printer_ip = str(requested_printer_ip or '').strip() or None
            requested_printer_name = str(requested_printer_name or '').strip() or None
    
            if selected_printer_raw not in (None, '', 'auto', 'AUTO', 'default', 'DEFAULT', '0', 0):
                try:
                    requested_printer_id = int(selected_printer_raw)
                except (TypeError, ValueError):
                    return jsonify({'success': False, 'message': 'Nieprawidlowy printer_id'}), 400
    
            raw_requested_date = None
            if isinstance(payload, dict):
                raw_requested_date = (
                    payload.get('data_produkcji')
                    or payload.get('dataProdukcji')
                    or payload.get('productionDate')
                )
            if not raw_requested_date:
                raw_requested_date = request.form.get('data_produkcji') or request.args.get('data_produkcji')
    
            current_app.logger.info(
                'Manual ZPL request: paleta_id=%s, linia=%s, content_type=%s, requested_data_produkcji=%s, payload_keys=%s',
                paleta_id,
                linia,
                request.content_type,
                raw_requested_date,
                sorted(list(payload.keys())) if isinstance(payload, dict) else [],
            )
    
            requested_data_produkcji = None
            try:
                requested_data_produkcji = _parse_data_produkcji_input(raw_requested_date)
            except ValueError as error:
                return jsonify({'success': False, 'message': str(error)}), 400
    
            if requested_data_produkcji:
                table_plan = get_table_name('plan_produkcji', linia)
                plan_id = _resolve_plan_id_for_paleta(
                    cursor,
                    paleta_id,
                    linia,
                    requested_plan_id=payload.get('plan_id') if isinstance(payload, dict) else None,
                )
                if not plan_id:
                    return jsonify({'success': False, 'message': 'Nie znaleziono powiazanego zlecenia dla palety'}), 404
    
                cursor.execute(f"SELECT sekcja FROM {table_plan} WHERE id=%s", (plan_id,))
                row_plan = cursor.fetchone()
                if not row_plan:
                    return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia dla palety'}), 404
    
                sekcja = str(row_plan[0] or '')
                if sekcja.lower() != 'workowanie':
                    return jsonify({'success': False, 'message': 'Zmiana daty jest dostepna tylko dla Workowania'}), 400
    
                cursor.execute(
                    f"UPDATE {table_plan} SET data_produkcji=%s WHERE id=%s",
                    (requested_data_produkcji, plan_id),
                )
                conn.commit()
                current_app.logger.info(
                    'Ręczny wydruk: ustawiono data_produkcji=%s dla plan_id=%s (paleta_id=%s, linia=%s, user=%s)',
                    requested_data_produkcji,
                    plan_id,
                    paleta_id,
                    linia,
                    session.get('login'),
                )
    
            from app.utils.pallet_label import prepare_pallet_label_data
            source = request.args.get('source')
            
            # Pobierz plan_id z requestu
            req_plan_id_raw = None
            if isinstance(payload, dict):
                req_plan_id_raw = payload.get('plan_id') or payload.get('planId')
            if req_plan_id_raw in (None, ''):
                req_plan_id_raw = request.form.get('plan_id') or request.args.get('plan_id')
    
            label_data = prepare_pallet_label_data(cursor, paleta_id, linia, requested_plan_id=req_plan_id_raw, source_table=source)
            
            if not label_data:
                return jsonify({'success': False, 'message': 'Nie znaleziono palety (ani w buforze, ani w magazynie)'}), 404
    
            # Always prefer the date explicitly chosen by the operator for this print job.
            # DB update still persists this value on the linked Workowanie order.
            if requested_data_produkcji:
                label_data['data'] = requested_data_produkcji
            
            printer = get_printer()
            override_name = None
            override_ip = None
            if requested_printer_id:
                cursor.execute(
                    "SELECT nazwa, ip FROM drukarki WHERE id = %s AND aktywna = 1 LIMIT 1",
                    (requested_printer_id,),
                )
                selected_printer = cursor.fetchone()
                if not selected_printer:
                    return jsonify({'success': False, 'message': 'Wybrana drukarka nie istnieje lub jest nieaktywna'}), 404
                override_name, override_ip = selected_printer[0], selected_printer[1]
            elif requested_printer_ip:
                if len(requested_printer_ip) > 120:
                    return jsonify({'success': False, 'message': 'Nieprawidlowy adres drukarki'}), 400
                override_ip = requested_printer_ip
                override_name = requested_printer_name or requested_printer_ip
            else:
                override_name, override_ip = _select_preferred_printer(cursor)
    
            candidate_printers = []
            seen_targets = set()
    
            def _append_candidate(name, ip):
                key = ((name or '').strip().lower(), (ip or '').strip().lower())
                if key in seen_targets:
                    return
                seen_targets.add(key)
                candidate_printers.append((name, ip))
    
            _append_candidate(override_name, override_ip)
    
            # Niezależnie od wyboru ręcznego warto próbować kolejne aktywne drukarki,
            # bo timeout pojedynczej drukarki jest częsty i chwilowy.
            for printer_row in _list_active_printers(cursor):
                cand_name = printer_row[1] if len(printer_row) > 1 else None
                cand_ip = printer_row[2] if len(printer_row) > 2 else None
                _append_candidate(cand_name, cand_ip)
    
            # Last resort: fallback to configured default in PrintServer.
            _append_candidate(None, None)
    
            local_bridge_fallback = None
            try:
                fallback_printers = []
                fallback_seen = set()
                for cand_name, cand_ip in candidate_printers:
                    final_name = cand_name or printer.printer_name
                    final_ip = cand_ip or printer.printer_ip
                    if not final_ip:
                        continue
                    fallback_key = (str(final_name).strip().lower(), str(final_ip).strip().lower())
                    if fallback_key in fallback_seen:
                        continue
                    fallback_seen.add(fallback_key)
                    fallback_printers.append({'name': final_name, 'ip': final_ip})
    
                if fallback_printers:
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
    
                    primary_endpoint = endpoint_entries[0] if endpoint_entries else None
                    local_bridge_fallback = {
                        'endpoint': (primary_endpoint or {}).get('endpoint'),
                        'status_endpoint': (primary_endpoint or {}).get('status_endpoint'),
                        'endpoints': endpoint_entries,
                        'copies': 2,
                        'zpl': printer.build_finished_product_label_zpl(label_data),
                        'printers': fallback_printers,
                        'reason': 'server_printer_timeout',
                    }
            except Exception as fallback_err:
                current_app.logger.warning('Nie udało się przygotować fallbacku lokalnego wydruku: %s', fallback_err)
    
            ok = False
            msg = 'Błąd druku'
            target_name = override_name or printer.printer_name
            target_ip = override_ip or printer.printer_ip
    
            for candidate_index, (cand_name, cand_ip) in enumerate(candidate_printers, start=1):
                candidate_target_name = cand_name or printer.printer_name
                candidate_target_ip = cand_ip or printer.printer_ip
                candidate_ok = True
    
                print_ok, print_msg = printer.print_finished_product_label(
                    label_data,
                    override_ip=cand_ip,
                    override_name=cand_name,
                    copies=2
                )
                if not print_ok:
                    candidate_ok = False
                    msg = print_msg
                    current_app.logger.warning(
                        'Ręczny wydruk paleta_id=%s nieudany (drukarka=%s, ip=%s, próba=%s): %s',
                        paleta_id,
                        candidate_target_name,
                        candidate_target_ip,
                        candidate_index,
                        print_msg,
                    )
    
                if candidate_ok:
                    ok = True
                    target_name = candidate_target_name
                    target_ip = candidate_target_ip
                    if candidate_index > 1:
                        msg = f"Wysłano do drukarki {target_name} ({target_ip}) po fallbacku"
                    else:
                        msg = f"Wysłano do drukarki {target_name} ({target_ip})"
                    break
            
            if ok:
                audit_log('Wydruk etykiety ZPL (ręczny)', f'paleta_id={paleta_id}, produkt={label_data["nazwa"]}, nr_palety={label_data["nrPalety"]}, kopie=2')
    
            response_payload = {
                'success': ok,
                'message': msg,
                'printer_name': target_name,
                'printer_ip': target_ip,
            }
    
            if not ok and local_bridge_fallback:
                response_payload['local_bridge_fallback'] = local_bridge_fallback
    
            if requested_printer_id:
                response_payload['printer_id'] = requested_printer_id
            if requested_data_produkcji:
                response_payload['data_produkcji'] = requested_data_produkcji
            elif label_data.get('data'):
                response_payload['data_produkcji'] = str(label_data.get('data'))
    
            return jsonify(response_payload)
        except Exception as e:
            current_app.logger.exception('ZPL Print failed: %s', e)
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            cursor.close()
            conn.close()

    @warehouse_bp.route('/drukuj-zpl/<int:paleta_id>', methods=['GET'])
    def legacy_drukuj_zpl_redirect(paleta_id):
        """Redirect legacy manual GET requests to the label preview page."""
        linia = request.args.get('linia', 'PSD')
        return redirect(url_for('magazyn_dostawy.podglad_etykiety_system', paleta_id=paleta_id, linia=linia))
