from flask import render_template, request, jsonify, redirect, url_for, current_app, session
import traceback
from app.db import get_db_connection, get_table_name
from app.decorators import login_required
from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
from app.services.magazyn_dostawy.delivery_command_service import DeliveryCommandService
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.magazyn_dostawy.location_service import LocationService
from app.services.magazyn_dostawy.pallet_split_service import PalletSplitService
from app.utils.pallet_label import prepare_pallet_label_data
from app.utils.pallet_id import generate_pallet_id
from ..config import (
    LOKALIZACJE_SZCZEGOLOWE, BUFORY, LOKALIZACJE, LOKALIZACJE_CEL,
    _safe_float, _safe_datetime_str, _format_label_weight
)
import json
from datetime import datetime
from ..base import magazyn_dostawy_bp

@magazyn_dostawy_bp.route('/podglad-etykiety', methods=['GET', 'POST'])
def podglad_etykiety():
    nr_palety = str(request.args.get('nr_palety', '') or '').strip() or '---'
    product_name = str(request.args.get('product_name', '') or '').strip() or 'Brak nazwy'
    nr_partii = str(request.args.get('nr_partii', '') or '').strip() or '---'
    data_produkcji = str(request.args.get('data_produkcji', '') or '').strip() or '---'
    data_przydatnosci = str(request.args.get('data_przydatnosci', '') or '').strip() or '---'
    typ_surowca = str(request.args.get('p_type', 'surowiec') or 'surowiec').strip().lower()
    linia = str(request.args.get('linia', 'PSD') or 'PSD').strip().upper()
    qty = _safe_float(request.args.get('qty', 0))

    nr_upper = nr_palety.upper()
    if nr_upper.startswith('SUR') or nr_upper.startswith('DOD'):
        typ_label = 'SUROWIEC'
    elif nr_upper.startswith('AGR') or nr_upper.startswith('PSD') or nr_upper.startswith('MIX'):
        typ_label = 'WYRÓB GOTOWY'
    elif nr_upper.startswith('OPA'):
        typ_label = 'OPAKOWANIE'
    else:
        if typ_surowca == 'packaging':
            typ_label = 'OPAKOWANIE'
        elif typ_surowca in {'wyrob_gotowy', 'finished', 'gotowy'}:
            typ_label = 'WYRÓB GOTOWY'
        else:
            typ_label = 'SUROWIEC'

    return render_template(
        'magazyn_dostawy/etykieta_podglad.html',
        nr_palety=nr_palety,
        product_name=product_name,
        nr_partii=nr_partii,
        data_produkcji=data_produkcji,
        data_przydatnosci=data_przydatnosci,
        qty=qty,
        typ_label=typ_label,
        linia=linia,
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )

@magazyn_dostawy_bp.route('/podglad-etykiety-system/<int:paleta_id>', methods=['GET', 'POST'])
def podglad_etykiety_system(paleta_id):
    linia = str(request.args.get('linia', 'PSD') or 'PSD').strip().upper()
    autoprint = str(request.args.get('autoprint', '') or '').strip().lower() in {'1', 'true', 'yes'}

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        label_data = prepare_pallet_label_data(cursor, paleta_id, linia, source_table='magazyn')
    finally:
        conn.close()

    if not label_data:
        return 'Nie znaleziono danych etykiety dla tej palety.', 404

    nr_palety = str(label_data.get('nrPalety') or label_data.get('nr_palety') or paleta_id).strip() or str(paleta_id)
    product_name = str(label_data.get('nazwa') or 'Brak nazwy').strip() or 'Brak nazwy'
    nr_partii = str(label_data.get('partia') or '---').strip() or '---'
    data_produkcji = str(label_data.get('data') or '---').strip() or '---'
    data_przydatnosci = str(label_data.get('termin') or '---').strip() or '---'
    qty_display = _format_label_weight(label_data.get('ilosc'))
    nr_palety_lp = label_data.get('nr_palety_lp')
    try:
        if nr_palety_lp not in (None, ''):
            nr_palety_lp = int(nr_palety_lp)
    except Exception:
        nr_palety_lp = None

    nr_upper = nr_palety.upper()
    if nr_upper.startswith('SUR') or nr_upper.startswith('DOD'):
        typ_label_sys = 'SUROWIEC'
    elif nr_upper.startswith('OPA'):
        typ_label_sys = 'OPAKOWANIE'
    else:
        typ_label_sys = 'WYROB GOTOWY'

    return render_template(
        'magazyn_dostawy/etykieta_podglad_system.html',
        nr_palety=nr_palety,
        nr_palety_lp=nr_palety_lp,
        product_name=product_name,
        nr_partii=nr_partii,
        data_produkcji=data_produkcji,
        data_przydatnosci=data_przydatnosci,
        qty_display=qty_display,
        linia=linia,
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        autoprint=autoprint,
        zpl_string=f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FD{typ_label_sys} - {linia}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{product_name}^FS
^FO250,340^BQN,2,10^FDQA,{nr_palety}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{nr_palety}^FS
^FO40,750^A0N,50,50^FDNR PALETY: {nr_palety_lp or ''}^FS
^FO40,850^A0N,50,50^FDPRODUKCJA: {data_produkcji}^FS
^FO40,1000^A0N,70,70^FDWAGA NETTO:^FS
^FO40,1100^A0N,100,100^FD{qty_display} kg^FS
^XZ"""
    )

@magazyn_dostawy_bp.route('/podglad-etykiety-mix', methods=['GET', 'POST'])
def podglad_etykiety_mix():
    import json
    import urllib.parse
    mix_sscc = str(request.args.get('mix_sscc', '')).strip()
    linia = str(request.args.get('linia', 'AGRO')).strip()
    comps_raw = request.args.get('comps', '[]')
    try:
        comps = json.loads(urllib.parse.unquote(comps_raw))
    except Exception:
        comps = []
        
    zpl_string = f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FDSKLADNIKI MIX - {linia}^FS
^FO40,150^A0N,55,55^FB720,1,0,C^FD{mix_sscc}^FS
"""
    y_pos = 250
    for idx, c in enumerate(comps):
        if y_pos > 1050:
            break # out of bounds
        zpl_string += f"""^FO40,{y_pos}^A0N,35,35^FD{idx+1}. {c.get('produkt')[:35]}^FS
^FO60,{y_pos+45}^A0N,30,30^FD{c.get('sscc')} - {c.get('waga')} kg^FS
"""
        y_pos += 100
        
    zpl_string += "^XZ"
    
    return render_template(
        'magazyn_dostawy/etykieta_podglad_system.html',
        nr_palety=mix_sscc,
        linia=linia,
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        autoprint=False,
        zpl_string=zpl_string
    )

@magazyn_dostawy_bp.route('/preprint', methods=['POST','GET'])
@magazyn_dostawy_bp.route('/preprint/', methods=['POST','GET'])
@login_required
def preprint_labels_view():
    """Pre-druk etykiet dla magazynu.

    Tryb A (rezerwacja etykiet dla przyszłych palet):
      {"plan_id": 123, "count": 10, "linia": "PSD"}

    Tryb B (druk istniejących palet bez rezerwacji):
      {"existing_only": true, "count": 10, "linia": "PSD", "only_pending": true, "date": "YYYY-MM-DD"}
    """

    def _as_bool(value, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on', 'tak'}

    payload = {}
    if request.method != 'GET':
        raw_payload = request.get_json(silent=True)
        if isinstance(raw_payload, dict):
            payload = raw_payload

    def _pick(field_name, default=None):
        value = payload.get(field_name)
        if value not in (None, ''):
            return value
        query_value = request.args.get(field_name)
        if query_value not in (None, ''):
            return query_value
        return default

    linia = str(_pick('linia', 'PSD') or 'PSD').upper()
    existing_only = _as_bool(_pick('existing_only', False), default=False)
    only_pending = _as_bool(_pick('only_pending', True), default=True)
    date_filter = str(_pick('date', '') or '').strip()

    try:
        count = int(_pick('count', 0) or 0)
    except (TypeError, ValueError):
        count = 0

    if count <= 0:
        return jsonify({'success': False, 'message': 'count musi być >= 1'}), 400

    def _resolve_workowanie_plan_id(conn_obj, linia_value, date_value=''):
        table_plan_local = get_table_name('plan_produkcji', linia_value)
        date_sql = 'DATE(data_planu) = CURDATE()'
        date_params = []
        if date_value:
            try:
                datetime.strptime(date_value, '%Y-%m-%d')
            except ValueError:
                raise ValueError('Niepoprawny format date (YYYY-MM-DD)')
            date_sql = 'DATE(data_planu) = %s'
            date_params.append(date_value)

        local_cursor = conn_obj.cursor(dictionary=True)
        try:
            local_cursor.execute(
                f'''
                SELECT id
                FROM {table_plan_local}
                WHERE sekcja IN ('Workowanie', 'Czyszczenie')
                  AND {date_sql}
                ORDER BY
                  CASE
                    WHEN LOWER(COALESCE(status, '')) = 'w toku' THEN 0
                    WHEN LOWER(COALESCE(status, '')) = 'zaplanowane' THEN 1
                    ELSE 2
                  END,
                  id ASC
                LIMIT 1
                ''',
                tuple(date_params),
            )
            row = local_cursor.fetchone()
            if row and row.get('id'):
                return int(row.get('id'))
            return None
        finally:
            try:
                local_cursor.close()
            except Exception:
                pass

    def _fetch_existing(conn_obj, limit_count):
        table_pal = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)

        status_filter_sql = "AND COALESCE(pw.status, '') NOT IN ('przyjeta', 'zamknieta', 'w_magazynie')"
        if not only_pending:
            status_filter_sql = "AND COALESCE(pw.status, '') != 'zamknieta'"

        date_filter_sql = 'DATE(pw.data_dodania) = CURDATE()'
        query_params = []
        if date_filter:
            try:
                datetime.strptime(date_filter, '%Y-%m-%d')
            except ValueError:
                raise ValueError('Niepoprawny format date (YYYY-MM-DD)')
            date_filter_sql = 'DATE(pw.data_dodania) = %s'
            query_params.append(date_filter)

        query_params.append(limit_count)

        local_cur = conn_obj.cursor(dictionary=True)
        try:
            local_cur.execute(
                f'''
                SELECT
                    pw.id,
                    pw.plan_id,
                    pw.nr_palety,
                    (SELECT COUNT(1) FROM {table_pal} pw2 WHERE pw2.plan_id = pw.plan_id AND pw2.id <= pw.id) AS nr_palety_lp,
                    COALESCE(NULLIF(TRIM(p.nazwa_zlecenia), ''), CONCAT('PLAN-', p.id)) AS nazwa_zlecenia
                FROM {table_pal} pw
                JOIN {table_plan} p ON p.id = pw.plan_id
                WHERE {date_filter_sql}
                  AND p.sekcja IN ('Workowanie', 'Czyszczenie')
                  AND pw.waga > 0
                  {status_filter_sql}
                ORDER BY pw.id DESC
                LIMIT %s
                ''',
                tuple(query_params),
            )
            rows = local_cur.fetchall() or []
        finally:
            try:
                local_cur.close()
            except Exception:
                pass

        return [
            {
                'id': r.get('id'),
                'plan_id': r.get('plan_id'),
                'nr_palety': r.get('nr_palety'),
                'nr_palety_lp': r.get('nr_palety_lp'),
                'nazwa_zlecenia': r.get('nazwa_zlecenia'),
                'source': 'existing',
            }
            for r in rows[::-1]
        ]

    conn_existing = None
    existing_created = []
    try:
        conn_existing = get_db_connection()
        existing_created = _fetch_existing(conn_existing, count)
    except ValueError as date_err:
        return jsonify({'success': False, 'message': str(date_err)}), 400
    except Exception as e:
        try:
            tb = traceback.format_exc()
            current_app.logger.error('preprint_labels_view existing scan exception: %s\n%s', str(e), tb)
        except Exception:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if conn_existing:
            try:
                conn_existing.close()
            except Exception:
                pass

    existing_count = len(existing_created)

    if existing_only:
        for idx, rec in enumerate(existing_created, start=1):
            rec['kolejnosc'] = idx

        warning_message = None
        if existing_count < count:
            warning_message = f'Znaleziono {existing_count} palet z żądanych {count} (bez rezerwacji nowych).'

        return jsonify({
            'success': True,
            'mode': 'existing',
            'created': existing_created,
            'only_pending': only_pending,
            'date': date_filter or datetime.now().strftime('%Y-%m-%d'),
            'requested_count': count,
            'existing_count': existing_count,
            'generated_count': 0,
            'generation_plan_id': None,
            'warning': warning_message,
        })

    reserve_needed = max(count - existing_count, 0)
    generation_plan_id = None
    generated_created = []

    if reserve_needed > 0:
        plan_id = None
        plan_id_raw = _pick('plan_id')
        if plan_id_raw not in (None, ''):
            try:
                plan_id = int(plan_id_raw)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'Niepoprawny plan_id'}), 400

        if not plan_id:
            resolve_conn = None
            try:
                resolve_conn = get_db_connection()
                plan_id = _resolve_workowanie_plan_id(resolve_conn, linia, date_filter)
            except ValueError as date_err:
                return jsonify({'success': False, 'message': str(date_err)}), 400
            except Exception:
                plan_id = None
            finally:
                if resolve_conn:
                    try:
                        resolve_conn.close()
                    except Exception:
                        pass

        if not plan_id:
            return jsonify({'success': False, 'message': 'Brak aktywnego planu Workowanie dla wybranej daty (potrzebny do rezerwacji brakujących etykiet)'}), 400

        generation_plan_id = plan_id
        try:
            from app.services.pallet_preprint_service import preprint_labels
            generated_created = preprint_labels(plan_id, reserve_needed, linia=linia, user_login=session.get('login', 'System')) or []
            for rec in generated_created:
                rec['source'] = 'reserve'
        except Exception as e:
            try:
                tb = traceback.format_exc()
                current_app.logger.error('preprint_labels_view reserve exception: %s\n%s', str(e), tb)
            except Exception:
                pass
            try:
                conn = get_db_connection()
                cur = conn.cursor(dictionary=True)
                table_pal = get_table_name('palety_workowanie', linia)
                table_plan = get_table_name('plan_produkcji', linia)
                cur.execute(
                    f'''
                    SELECT
                        pw.id,
                        pw.plan_id,
                        pw.nr_palety,
                        pw.nr_palety_lp,
                        COALESCE(NULLIF(TRIM(p.nazwa_zlecenia), ''), CONCAT('PLAN-', p.id)) AS nazwa_zlecenia
                    FROM {table_pal} pw
                    LEFT JOIN {table_plan} p ON p.id = pw.plan_id
                    WHERE pw.plan_id = %s
                      AND pw.status = 'rezerwacja'
                    ORDER BY pw.id DESC
                    LIMIT %s
                    ''',
                    (plan_id, reserve_needed),
                )
                rows = cur.fetchall() or []
                cur.close(); conn.close()
                generated_created = [
                    {
                        'id': r.get('id'),
                        'plan_id': r.get('plan_id'),
                        'nr_palety': r.get('nr_palety'),
                        'nr_palety_lp': r.get('nr_palety_lp'),
                        'nazwa_zlecenia': r.get('nazwa_zlecenia'),
                        'source': 'reserve',
                    }
                    for r in rows[::-1]
                ]
                if not generated_created:
                    return jsonify({'success': False, 'message': str(e)}), 500
            except Exception:
                return jsonify({'success': False, 'message': str(e)}), 500

    created = [*existing_created, *generated_created]
    for idx, rec in enumerate(created, start=1):
        rec['kolejnosc'] = idx

    generated_count = len(generated_created)
    mode = 'mixed' if (existing_count > 0 and generated_count > 0) else ('reserve' if generated_count > 0 else 'existing')

    warning_message = None
    if generated_count > 0 and existing_count > 0:
        warning_message = f'Znaleziono {existing_count} istniejących palet i utworzono {generated_count} rezerwacji.'
    elif existing_count < count and generated_count == 0:
        warning_message = f'Znaleziono {existing_count} palet z żądanych {count}.'

    return jsonify({
        'success': True,
        'mode': mode,
        'created': created,
        'only_pending': only_pending,
        'date': date_filter or datetime.now().strftime('%Y-%m-%d'),
        'requested_count': count,
        'existing_count': existing_count,
        'generated_count': generated_count,
        'generation_plan_id': generation_plan_id,
        'warning': warning_message,
    })

@magazyn_dostawy_bp.route('/api/dodruk-etykiet', methods=['POST'])
def dodruk_etykiet():
    data = request.json
    nr_palety = data.get('nr_palety')
    printer_id = data.get('printer_id')
    product_name = data.get('product_name')
    nr_partii = data.get('nr_partii') or '---'
    data_produkcji = data.get('data_produkcji') or '---'
    data_przydatnosci = data.get('data_przydatnosci') or '---'
    qty = data.get('qty') or 0.0
    p_type = data.get('p_type') or 'surowiec'
    
    if not nr_palety or not printer_id:
        return jsonify({"success": False, "error": "Brak nr_palety lub drukarki"}), 400
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s", (printer_id,))
        printer_row = cursor.fetchone()
        if not printer_row:
            return jsonify({"success": False, "error": "Drukarka nie istnieje"}), 404
            
        printer_ip = printer_row['ip']
        printer_name = printer_row['nazwa']
    finally:
        conn.close()
        
    # Print 2 labels
    try:
        import threading
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        payload = {
            "drukarka": printer_name,
            "ip": printer_ip,
            "typ": p_type,
            "dane": {
                "palletData": {
                    "nrPalety": nr_palety,
                    "productName": product_name,
                    "batchNumber": nr_partii,
                    "productionDate": str(data_produkcji),
                    "expiryDate": str(data_przydatnosci),
                    "currentWeight": float(qty),
                    "labNotes": "Dodruk etykiety"
                }
            }
        }
        def run_print():
            url = "http://127.0.0.1:3001/drukuj-zpl"
            for _ in range(2):
                try:
                    requests.post(url, json=payload, verify=False, timeout=3)
                except Exception:
                    pass
        threading.Thread(target=run_print, daemon=True).start()
        return jsonify({"success": True, "message": f"Wysłano 2 etykiety do drukarki {printer_name}."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@magazyn_dostawy_bp.route('/api/dostepne-palety')
def get_available_pallets():
    linia = request.args.get('linia', 'PSD').upper()
    prefix = (request.args.get('prefix', '') or '').strip()
    skip_lookup_raw = str(request.args.get('skip_warehouse_lookup', '') or '').strip().lower()
    skip_warehouse_lookup = skip_lookup_raw in ('1', 'true', 'yes', 'on')
    
    # Uniwersalny skaner - szukaj we wszystkich liniach gdy podano kod/nr palety
    search_all_lines = bool(prefix and prefix not in ('MP01', 'MS01', 'MGW01', 'MOP01', 'OSIP'))
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Lista linii do przeszukania
        lines_to_search = ['PSD', 'AGRO'] if search_all_lines else [linia]
        
        pallets = []
        for current_linia in lines_to_search:
            table_sur = get_table_name('magazyn_surowce', current_linia)
            table_opk = get_table_name('magazyn_opakowania', current_linia)
            
            # Flexible filtering logic (match dashboard.html + search by pallet id/no/name)
            where_clause = "1=1"
            params = []

            if not prefix:
                where_clause = "1=1"
            elif prefix == 'MP01':
                where_clause = "(lokalizacja LIKE 'MP01%' OR lokalizacja LIKE 'R01%' OR lokalizacja LIKE 'R02%' OR lokalizacja LIKE 'R03%')"
                params = []
            elif prefix == 'MS01':
                where_clause = "(lokalizacja LIKE 'MS01%' OR lokalizacja LIKE 'R04%' OR lokalizacja LIKE 'R05%' OR lokalizacja LIKE 'R06%' OR lokalizacja LIKE 'R07%')"
                params = []
            elif prefix == 'MGW01':
                where_clause = "lokalizacja LIKE 'MGW01%'"
            elif prefix == 'MOP01':
                where_clause = "lokalizacja LIKE 'MOP01%'"
            elif prefix == 'OSIP':
                where_clause = "lokalizacja LIKE '%%OSIP%%'"
            else:
                where_clause = """(
                    REPLACE(REPLACE(REPLACE(lokalizacja, '_', ''), '-', ''), ' ', '') LIKE %s OR
                    nazwa LIKE %s OR
                    COALESCE(nr_partii, '') LIKE %s OR
                    COALESCE(nr_palety, '') LIKE %s OR
                    CAST(id AS CHAR) = %s
                )"""
                clean_prefix = prefix.replace('_', '').replace('-', '').replace(' ', '')
                like_prefix = f"{clean_prefix}%"
                like_any = f"%{prefix}%"
                params = [like_prefix, like_any, like_any, like_any, prefix]

            q1 = f"""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, 'surowiec' as type
                FROM {table_sur} 
                WHERE {'1=1' if skip_warehouse_lookup else 'stan_magazynowy > 0'} AND {where_clause}
            """
            cursor.execute(q1, params if params else [])
            pallets.extend(cursor.fetchall())

            q2 = f"""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, 'opakowanie' as type
                FROM {table_opk}
                WHERE {'1=1' if skip_warehouse_lookup else 'stan_magazynowy > 0'} AND {where_clause}
            """
            cursor.execute(q2, params if params else [])
            pallets.extend(cursor.fetchall())

            # Wyroby gotowe - użyj oddzielnego where_clause dla produkt zamiast nazwa
            table_wg = get_table_name('magazyn_palety', current_linia)
            if params:  # Jeśli mamy parametry wyszukiwania
                where_clause_wg = """(
                    REPLACE(REPLACE(REPLACE(COALESCE(lokalizacja, 'MGW01'), '_', ''), '-', ''), ' ', '') LIKE %s OR
                    COALESCE(produkt, '') LIKE %s OR
                    COALESCE(nr_partii, '') LIKE %s OR
                    COALESCE(nr_palety, '') LIKE %s OR
                    CAST(id AS CHAR) = %s
                )"""
                params_wg = params.copy()
            else:
                where_clause_wg = where_clause
                params_wg = []

            q4 = f"""
                SELECT id, nr_palety, produkt as nazwa, waga_netto as stan_magazynowy, 
                       COALESCE(lokalizacja, 'MGW01') as lokalizacja, nr_partii, 
                       data_produkcji, data_przydatnosci, 'wyrob_gotowy' as type
                FROM {table_wg}
                WHERE {'1=1' if skip_warehouse_lookup else 'COALESCE(waga_netto, 0) > 0'} AND {where_clause_wg}
            """
            cursor.execute(q4, params_wg)
            pallets.extend(cursor.fetchall())

            # Dodatki są wspólne dla wszystkich linii - dodaj tylko raz
            if current_linia == lines_to_search[0]:
                q3 = f"""
                    SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, 'dodatek' as type
                    FROM magazyn_dodatki
                    WHERE {'1=1' if skip_warehouse_lookup else 'stan_magazynowy > 0'} AND {where_clause}
                """
                cursor.execute(q3, params if params else [])
                pallets.extend(cursor.fetchall())
        
        # Sortowanie i deduplikacja
        pallets.sort(key=lambda x: (str(x.get('lokalizacja') or ''), str(x.get('nazwa') or ''), x.get('id') or 0))
        
        unique_pallets = {}
        for p in pallets:
            key = f"{p['type']}_{p['id']}"
            if key not in unique_pallets:
                unique_pallets[key] = p
        pallets = list(unique_pallets.values())

        # Reservation guard: exclude pallets already used in other pending transfers.
        cursor.execute(
            "SELECT id, items FROM magazyn_dostawy WHERE status = 'OCZEKUJE' AND linia = %s",
            (linia,)
        )
        pending_transfers = cursor.fetchall()

        reserved_nrs = set()
        reserved_ids = set()
        for transfer in pending_transfers:
            raw_items = transfer.get('items')
            if not raw_items:
                continue
            try:
                transfer_items = json.loads(raw_items)
            except Exception:
                continue
            if not isinstance(transfer_items, list):
                continue

            for it in transfer_items:
                if not isinstance(it, dict):
                    continue
                if it.get('accepted'):
                    continue

                nr = str(it.get('sourcePalletNo') or it.get('nr_palety') or '').strip().upper()
                if nr:
                    reserved_nrs.add(nr)

                pal_id = it.get('sourcePalletId')
                pal_type = str(it.get('scannedType') or it.get('type') or '').strip().lower()
                if pal_id not in (None, '') and pal_type:
                    reserved_ids.add(f"{pal_type}:{pal_id}")

        filtered_pallets = []
        for pal in pallets:
            pal_nr = str(pal.get('nr_palety') or '').strip().upper()
            pal_id = pal.get('id')
            pal_type = str(pal.get('type') or '').strip().lower()
            pal_key = f"{pal_type}:{pal_id}" if pal_id not in (None, '') and pal_type else ''

            if (pal_nr and pal_nr in reserved_nrs) or (pal_key and pal_key in reserved_ids):
                continue
                
            if pal.get('data_produkcji'):
                try:
                    pal['data_produkcji'] = pal['data_produkcji'].strftime('%Y-%m-%d')
                except AttributeError:
                    pal['data_produkcji'] = str(pal['data_produkcji'])
            if pal.get('data_przydatnosci'):
                try:
                    pal['data_przydatnosci'] = pal['data_przydatnosci'].strftime('%Y-%m-%d')
                except AttributeError:
                    pal['data_przydatnosci'] = str(pal['data_przydatnosci'])

            filtered_pallets.append(pal)

        return jsonify({"success": True, "pallets": filtered_pallets})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@magazyn_dostawy_bp.route('/podzial-palety')
@login_required
def podzial_palety_view():
    return render_template('magazyn_dostawy/podzial_palety.html')

@magazyn_dostawy_bp.route('/api/info-paleta', methods=['GET'])
@login_required
def api_info_paleta():
    sscc = request.args.get('sscc', '').strip()
    if not sscc:
        return jsonify({'success': False, 'error': 'Brak kodu SSCC.'})

    pal = PalletSplitService.find_by_sscc(sscc)
    if pal:
        return jsonify({'success': True, 'pallet': pal})

    return jsonify({'success': False, 'error': 'Nie znaleziono palety o podanym kodzie.'})

@magazyn_dostawy_bp.route('/api/podzial-palety', methods=['POST'])
@login_required
def api_podzial_palety():
    data = request.json or {}
    mother_id = data.get('mother_id')
    mother_sscc = data.get('mother_sscc')
    source = data.get('mother_table') or data.get('source') or 'magazyn'
    weight_to_take = _safe_float(data.get('weight_to_take', 0))
    linia = data.get('linia')
    login = session.get('login', 'System')

    try:
        ok, message, new_pallet = PalletSplitService.split_pallet(
            mother_sscc=mother_sscc,
            weight_to_take=weight_to_take,
            user_login=login,
            linia=linia,
            # Zostawiamy opcjonalne id/source dla kompatybilności, ale SSCC ma priorytet
            mother_id=mother_id,
            source=source
        )
        if not ok:
            return jsonify({'success': False, 'error': message})

        label_url = PalletSplitService.build_label_url(new_pallet)
        return jsonify({
            'success': True,
            'message': message,
            'label_url': label_url,
            'new_pallet': {
                'id': new_pallet['id'],
                'nr_palety': new_pallet['nr_palety'],
                'waga': new_pallet['waga'],
                'linia': new_pallet['linia'],
                'plan_id': new_pallet.get('plan_id'),
                'source': new_pallet.get('source'),
            },
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

