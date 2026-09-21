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

def _select_preferred_printer(cursor, linia='AGRO'):
    """Pick preferred printer based on production line (PSD -> 17/236, AGRO -> 160, OSIP -> 47/86)."""
    try:
        linia_clean = str(linia or '').strip().upper()
        if linia_clean == 'PSD':
            cursor.execute(
                """
                SELECT nazwa, ip
                FROM drukarki
                WHERE aktywna = 1
                ORDER BY
                    CASE
                        WHEN LOWER(COALESCE(nazwa, '')) LIKE '%psd%' THEN 0
                        WHEN LOWER(COALESCE(nazwa, '')) LIKE '%tsc%' THEN 1
                        WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%magazyn%' THEN 2
                        ELSE 3
                    END,
                    id ASC
                LIMIT 1
                """
            )
        elif linia_clean == 'OSIP':
            cursor.execute(
                """
                SELECT nazwa, ip
                FROM drukarki
                WHERE aktywna = 1
                ORDER BY
                    CASE
                        WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%osip%' THEN 0
                        WHEN LOWER(COALESCE(nazwa, '')) LIKE '%osip%' THEN 1
                        ELSE 2
                    END,
                    id ASC
                LIMIT 1
                """
            )
        else:
            cursor.execute(
                """
                SELECT nazwa, ip
                FROM drukarki
                WHERE aktywna = 1
                ORDER BY
                    CASE
                        WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%agro%' THEN 0
                        WHEN LOWER(COALESCE(nazwa, '')) LIKE '%agro%' THEN 1
                        WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 2
                        WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 3
                        ELSE 4
                    END,
                    id ASC
                LIMIT 1
                """
            )
        row = cursor.fetchone()
        if not row:
            return None, None
        if isinstance(row, dict):
            return row.get('nazwa'), row.get('ip')
        return row[0], row[1]
    except Exception as printer_err:
        try:
            current_app.logger.warning('Nie udało się pobrać preferowanej drukarki: %s', printer_err)
        except Exception:
            pass
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

    @warehouse_bp.route('/api/plan_preprint_info/<int:plan_id>', methods=['GET'])
    @login_required
    def api_plan_preprint_info(plan_id):
        try:
            linia = str(resolve_request_linia()).upper()
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f"SELECT id, produkt, tonaz, nazwa_zlecenia, sekcja, status, zasyp_id FROM {table_plan} WHERE id = %s", (plan_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return jsonify({'success': False, 'message': 'Plan nie znaleziony'}), 404
            
            tonaz = float(row.get('tonaz') or 0)
            if tonaz <= 1 and row.get('zasyp_id'):
                cursor.execute(f"SELECT tonaz FROM {table_plan} WHERE id = %s", (row['zasyp_id'],))
                z_row = cursor.fetchone()
                if z_row and float(z_row.get('tonaz') or 0) > tonaz:
                    tonaz = float(z_row['tonaz'])

            conn.close()
            calculated_pallets = max(1, int((tonaz + 999) // 1000)) if tonaz > 0 else 1
            return jsonify({
                'success': True,
                'plan_id': plan_id,
                'produkt': row.get('produkt') or 'Nieznany',
                'nazwa_zlecenia': row.get('nazwa_zlecenia') or '',
                'tonaz': tonaz,
                'suggested_pallets': calculated_pallets,
                'linia': linia
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @warehouse_bp.route('/drukuj_etykiete/<int:paleta_id>', methods=['GET'])
    @login_required
    def drukuj_etykiete(paleta_id):
        """Generates a 100x150 mm printable label for a palette in Magazyn."""
        from app.utils.pallet_label import prepare_pallet_label_data
        linia = str(resolve_request_linia()).upper()
        source = request.args.get('source')
        req_plan_id = request.args.get('plan_id')
    
        conn = get_db_connection()
        cursor = conn.cursor()
    
        try:
            label_data = prepare_pallet_label_data(cursor, paleta_id, linia, requested_plan_id=req_plan_id, source_table=source)
            if not label_data:
                abort(404, description='Paleta nie znaleziona')
    
            data_wydruku = datetime.now().strftime('%Y-%m-%d %H:%M')
            termin_przydatnosci = request.args.get('termin') or label_data.get('data_przydatnosci') or label_data.get('termin_przydatnosci')
    
            return render_template(
                'warehouse/label.html',
                plan_id=label_data.get('plan_id') or 'Brak',
                produkt=label_data.get('nazwa') or 'Nieznany',
                nr_szarzy=label_data.get('nr_szarzy') or '1',
                waga=label_data.get('ilosc') or 0,
                nr_palety=label_data.get('nr_palety_lp') or label_data.get('nrPalety') or paleta_id,
                nr_palety_sscc=label_data.get('nrPalety') or str(paleta_id),
                nr_partii=label_data.get('nr_partii') or label_data.get('partia') or 'Brak',
                data_workowanie=label_data.get('data') or label_data.get('data_produkcji') or 'Ręczna paleta',
                data_produkcji=label_data.get('data') or label_data.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d'),
                data_wydruku=data_wydruku,
                termin_przydatnosci=termin_przydatnosci,
                linia=linia
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
    @warehouse_bp.route('/drukuj_etykiete_zpl/<int:paleta_id>', methods=['POST'])
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
                override_name, override_ip = _select_preferred_printer(cursor, linia=linia)

            target_name = override_name or printer.printer_name
            target_ip = override_ip or printer.printer_ip

            local_bridge_fallback = None
            try:
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
                    'printers': [{'name': target_name, 'ip': target_ip}],
                    'reason': 'server_printer_timeout',
                }
            except Exception as fallback_err:
                current_app.logger.warning('Nie udało się przygotować fallbacku lokalnego wydruku: %s', fallback_err)

            ok, msg = printer.print_finished_product_label(
                label_data,
                override_ip=target_ip,
                override_name=target_name,
                copies=2
            )
            job_id = getattr(printer, 'last_job_id', None)

            if ok:
                msg = f"Wysłano do drukarki {target_name} ({target_ip})"
            else:
                current_app.logger.warning(
                    'Ręczny wydruk paleta_id=%s nieudany (drukarka=%s, ip=%s): %s',
                    paleta_id,
                    target_name,
                    target_ip,
                    msg,
                )
            
            if ok:
                audit_log('Wydruk etykiety ZPL (ręczny)', f'paleta_id={paleta_id}, produkt={label_data["nazwa"]}, nr_palety={label_data["nrPalety"]}, kopie=2')
    
            response_payload = {
                'success': ok,
                'message': msg,
                'job_id': job_id,
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
