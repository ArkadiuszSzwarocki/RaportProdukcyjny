from flask import Blueprint, render_template, request, jsonify, session, url_for, redirect, current_app
import traceback
from app.db import get_db_connection, get_table_name
from app.decorators import login_required
from app.services.magazyn_dostawy_service import MagazynDostawyService
from app.utils.pallet_label import prepare_pallet_label_data
from app.utils.pallet_id import generate_pallet_id
from .config import (
    LOKALIZACJE_SZCZEGOLOWE, BUFORY, LOKALIZACJE, LOKALIZACJE_CEL,
    _safe_float, _safe_datetime_str, _format_label_weight
)
import json
from datetime import datetime

magazyn_dostawy_bp = Blueprint('magazyn_dostawy', __name__, url_prefix='/magazyn-dostawy')
@magazyn_dostawy_bp.route('/')
def lista_dostaw():
    linia = request.args.get('linia', 'PSD').upper()
    # Lista przesuniec ma pokazywac tylko ruchy wewnetrzne (z lokalizacja zrodlowa).
    dostawy = [d for d in MagazynDostawyService.get_dostawy(linia) if d.get('lokalizacja_z')]
    return render_template('magazyn_dostawy/lista.html', dostawy=dostawy, linia=linia)

@magazyn_dostawy_bp.route('/przyjecie')
def reception_view():
    """Widok listy przyjęć zewnętrznych."""
    linia = request.args.get('linia', 'PSD').upper()
    dostawy = MagazynDostawyService.get_dostawy(linia)
    # Filtrujemy tylko te, które nie mają lokalizacji źródłowej (zewnętrzne)
    receptions = [d for d in dostawy if not d.get('lokalizacja_z')]
    return render_template('magazyn_dostawy/lista_receptions.html', dostawy=receptions, linia=linia)

@magazyn_dostawy_bp.route('/przyjecie/nowe')
@magazyn_dostawy_bp.route('/przyjecie/<dostawa_id>')
def reception_edit(dostawa_id=None):
    """Formularz przyjęcia zewnętrznego do buforów."""
    linia = request.args.get('linia', 'PSD').upper()
    conn = get_db_connection()
    dostawa = None
    wszystkie_produkty = []
    printers = []
    try:
        cursor = conn.cursor(dictionary=True)
        if dostawa_id:
            cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if dostawa and str(dostawa.get('status') or '').upper() == 'COMPLETED':
                return redirect(url_for('magazyn_dostawy.raport_przesuniecia', dostawa_id=dostawa_id, linia=linia))
            if dostawa and dostawa.get('items'):
                dostawa['items'] = json.loads(dostawa['items'])

        table_sur = get_table_name('magazyn_surowce', linia)
        table_opk = get_table_name('magazyn_opakowania', linia)
        wszystkie_produkty = set()
        for query, p in [
            ("SELECT DISTINCT nazwa FROM slownik_surowcow", ()),
            (f"SELECT DISTINCT nazwa FROM {table_sur}", ()),
            (f"SELECT DISTINCT nazwa FROM {table_opk}", ()),
            ("SELECT DISTINCT nazwa FROM magazyn_dodatki WHERE linia = %s", (linia,))
        ]:
            cursor.execute(query, p)
            wszystkie_produkty.update([r['nazwa'] for r in cursor.fetchall() if r and r.get('nazwa')])
        wszystkie_produkty = sorted(list(wszystkie_produkty))

        try:
            cursor.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1")
            printers = cursor.fetchall()
        except Exception as pe:
            print(f"Error fetching printers in reception_edit: {pe}")

    finally:
        conn.close()

    return render_template(
        'magazyn_dostawy/reception_form.html',
        dostawa=dostawa, linia=linia,
        wszystkie_produkty=wszystkie_produkty,
        lokalizacje=BUFORY,
        printers=printers,
        now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

@magazyn_dostawy_bp.route('/oczekujace')
def oczekujace():
    linia = request.args.get('linia', 'PSD').upper()
    dostawy = MagazynDostawyService.get_oczekujace(linia)
    pending_scan_items = []

    def _safe_date(value):
        if not value:
            return ''
        if isinstance(value, str):
            return value[:10]
        try:
            return value.strftime('%Y-%m-%d')
        except Exception:
            return ''

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        items_changed = False
        for d in dostawy.get('dostawy', []) or []:
            items = d.get('items_parsed') or []
            delivery_changed = False

            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    item = {}
                    items[idx] = item
                    delivery_changed = True
                if item.get('id') in (None, ''):
                    item['id'] = f"legacy_{idx}"
                    delivery_changed = True

            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get('accepted') or item.get('rejected'):
                    continue

                nr_palety = item.get('nr_palety') or item.get('sourcePalletNo')
                if not nr_palety:
                    p_type = 'opakowanie' if item.get('packageForm') == 'packaging' else 'surowiec'
                    item['nr_palety'] = generate_pallet_id(linia, type=p_type)
                    nr_palety = item.get('nr_palety')
                    delivery_changed = True
                if not nr_palety:
                    continue

                qty_raw = item.get('netWeight') if item.get('netWeight') not in (None, '') else item.get('unitsPerPallet')
                qty = _safe_float(qty_raw) if qty_raw not in (None, '') else 0

                pending_scan_items.append({
                    'dostawa_id': d.get('id'),
                    'order_ref': d.get('order_ref') or '',
                    'lokalizacja_do': d.get('lokalizacja_do') or '',
                    'item_id': item.get('id'),
                    'nr_palety': str(nr_palety).strip().upper(),
                    'product_name': item.get('productName') or '',
                    'nr_partii': item.get('nr_partii') or '',
                    'data_produkcji': _safe_date(item.get('data_produkcji')),
                    'data_przydatnosci': _safe_date(item.get('data_przydatnosci')),
                    'qty': qty,
                    'p_type': 'packaging' if item.get('packageForm') == 'packaging' else 'surowiec',
                })

            if delivery_changed:
                cursor.execute(
                    "UPDATE magazyn_dostawy SET items = %s WHERE id = %s",
                    (json.dumps(items), d.get('id'))
                )
                d['items_parsed'] = items
                items_changed = True

        if items_changed:
            conn.commit()
    finally:
        conn.close()

    return render_template('magazyn_dostawy/oczekujace.html',
                           dostawy=dostawy, linia=linia,
                           lok_grupy=LOKALIZACJE_SZCZEGOLOWE,
                           pending_scan_items=pending_scan_items)


@magazyn_dostawy_bp.route('/podglad-etykiety')
def podglad_etykiety():
    nr_palety = str(request.args.get('nr_palety', '') or '').strip() or '---'
    product_name = str(request.args.get('product_name', '') or '').strip() or 'Brak nazwy'
    nr_partii = str(request.args.get('nr_partii', '') or '').strip() or '---'
    data_produkcji = str(request.args.get('data_produkcji', '') or '').strip() or '---'
    data_przydatnosci = str(request.args.get('data_przydatnosci', '') or '').strip() or '---'
    typ_surowca = str(request.args.get('p_type', 'surowiec') or 'surowiec').strip().lower()
    linia = str(request.args.get('linia', 'PSD') or 'PSD').strip().upper()
    qty = _safe_float(request.args.get('qty', 0))

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


@magazyn_dostawy_bp.route('/podglad-etykiety-system/<int:paleta_id>')
def podglad_etykiety_system(paleta_id):
    linia = str(request.args.get('linia', 'PSD') or 'PSD').strip().upper()
    autoprint = str(request.args.get('autoprint', '') or '').strip().lower() in {'1', 'true', 'yes'}

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        label_data = prepare_pallet_label_data(cursor, paleta_id, linia)
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
^FO40,60^A0N,50,50^FDWYROB GOTOWY - {linia}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{product_name}^FS
^FO250,340^BQN,2,10^FDQA,{nr_palety}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{nr_palety}^FS
^FO40,750^A0N,50,50^FDNR PALETY: {nr_palety_lp or ''}^FS
^FO40,850^A0N,50,50^FDPRODUKCJA: {data_produkcji}^FS
^FO40,1000^A0N,70,70^FDWAGA NETTO:^FS
^FO40,1100^A0N,100,100^FD{qty_display} kg^FS
^XZ"""
    )


@magazyn_dostawy_bp.route('/api/active-printers', methods=['GET'])
@login_required
def active_printers_api():
    """Zwraca połączoną listę drukarek z bazy danych (aktywnych) oraz drukarek sieciowych z mostka."""
    printers = []
    seen_ips = set()

    # 1. Najpierw pobieramy zdefiniowane i aktywne drukarki z bazy danych (priorytet)
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1 ORDER BY id ASC")
        rows = cur.fetchall() or []
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
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

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
                WHERE sekcja = 'Workowanie'
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

        status_filter_sql = "AND COALESCE(pw.status, '') NOT IN ('przyjeta', 'zamknieta')"
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
                  AND p.sekcja = 'Workowanie'
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

@magazyn_dostawy_bp.route('/raport')
def raport():
    linia = request.args.get('linia', 'PSD').upper()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    dostawy = MagazynDostawyService.get_raport(date_from, date_to)
    
    # User mapping for names
    user_mapping = {}
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.login, p.imie_nazwisko 
            FROM uzytkownicy u 
            JOIN pracownicy p ON u.pracownik_id = p.id
        """)
        user_mapping = {r['login']: r['imie_nazwisko'] for r in cursor.fetchall()}
    except Exception as e:
        print(f"Error fetching user mapping: {e}")
    finally:
        conn.close()

    return render_template('magazyn_dostawy/raport.html',
                           dostawy=dostawy, linia=linia,
                           date_from=date_from, date_to=date_to,
                           user_mapping=user_mapping,
                           now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


@magazyn_dostawy_bp.route('/raport-przesuniecia/<dostawa_id>')
def raport_przesuniecia(dostawa_id):
    """Raport do druku z pojedynczego przesunięcia/dostawy."""
    autoprint = request.args.get('autoprint', '').lower() in ('1', 'true', 'yes')
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
        dostawa = cursor.fetchone()
        if not dostawa:
            return 'Nie znaleziono raportu przesunięcia', 404

        try:
            items = json.loads(dostawa.get('items') or '[]')
        except Exception:
            items = []

        rows = []
        summary_map = {}
        reported_totals_by_unit = {}
        moved_totals_by_unit = {}
        rejected_totals_by_unit = {}
        for idx, item in enumerate(items, start=1):
            qty_raw = item.get('netWeight') if item.get('netWeight') not in (None, '') else item.get('unitsPerPallet')
            qty = _safe_float(qty_raw)
            unit = 'szt' if item.get('packageForm') == 'packaging' else 'kg'
            product_name = (item.get('productName') or 'Brak nazwy').strip() or 'Brak nazwy'
            source_location = item.get('sourceSpot') or dostawa.get('lokalizacja_z') or '-'
            target_location = item.get('lokalizacja_przyjecia') or dostawa.get('lokalizacja_do') or '-'
            accepted = bool(item.get('accepted'))
            rejected = bool(item.get('rejected'))

            if rejected:
                status_label = 'ODRZUCONA'
            elif accepted:
                status_label = 'PRZYJETA'
            else:
                status_label = 'OCZEKUJE'

            row_data = {
                'lp': idx,
                'product_name': product_name,
                'qty': qty,
                'unit': unit,
                'nr_palety': item.get('nr_palety') or '-',
                'nr_partii': item.get('nr_partii') or '-',
                'data_produkcji': item.get('data_produkcji') or '-',
                'data_przydatnosci': item.get('data_przydatnosci') or '-',
                'source_location': source_location,
                'target_location': target_location,
                'issued_by': item.get('issued_by') or dostawa.get('created_by') or '-',
                'accepted_by': item.get('accepted_by') or '-',
                'accepted_at': item.get('accepted_at') or '-',
                'accepted': accepted,
                'rejected': rejected,
                'rejected_by': item.get('rejected_by') or '-',
                'rejected_at': item.get('rejected_at') or '-',
                'rejected_reason': item.get('rejected_reason') or '-',
                'status_label': status_label,
            }
            rows.append(row_data)

            summary_key = (product_name, unit)
            reported_totals_by_unit[unit] = reported_totals_by_unit.get(unit, 0.0) + qty
            if accepted:
                summary_map[summary_key] = summary_map.get(summary_key, 0.0) + qty
                moved_totals_by_unit[unit] = moved_totals_by_unit.get(unit, 0.0) + qty
            elif rejected:
                rejected_totals_by_unit[unit] = rejected_totals_by_unit.get(unit, 0.0) + qty

        summary_rows = []
        for idx, ((name, unit), qty) in enumerate(sorted(summary_map.items(), key=lambda x: x[0][0].lower()), start=1):
            summary_rows.append({'lp': idx, 'product_name': name, 'unit': unit, 'qty': qty})

        def _to_total_rows(totals_dict):
            return [
                {'unit': unit, 'qty': qty}
                for unit, qty in sorted(totals_dict.items(), key=lambda x: x[0])
                if qty > 0
            ]

        reported_total_rows = _to_total_rows(reported_totals_by_unit)
        moved_total_rows = _to_total_rows(moved_totals_by_unit)
        rejected_total_rows = _to_total_rows(rejected_totals_by_unit)
        accepted_count = sum(1 for r in rows if r.get('accepted'))
        rejected_count = sum(1 for r in rows if r.get('rejected'))
        pending_count = max(len(rows) - accepted_count - rejected_count, 0)

        return render_template(
            'magazyn_dostawy/raport_przesuniecia_print.html',
            dostawa=dostawa,
            rows=rows,
            summary_rows=summary_rows,
            total_rows=moved_total_rows,
            reported_total_rows=reported_total_rows,
            moved_total_rows=moved_total_rows,
            rejected_total_rows=rejected_total_rows,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            pending_count=pending_count,
            created_at_str=_safe_datetime_str(dostawa.get('created_at')),
            confirmed_at_str=_safe_datetime_str(dostawa.get('potwierdzone_at')),
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            autoprint=autoprint,
        )
    finally:
        conn.close()

@magazyn_dostawy_bp.route('/nowa')
@magazyn_dostawy_bp.route('/<dostawa_id>')
def edycja_dostawy(dostawa_id=None):
    linia = request.args.get('linia', 'PSD').upper()
    conn = get_db_connection()
    dostawa = None
    wszystkie_produkty = []
    try:
        cursor = conn.cursor(dictionary=True)
        if dostawa_id:
            cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if dostawa and dostawa.get('items'):
                dostawa['items'] = json.loads(dostawa['items'])

            if dostawa and str(dostawa.get('status') or '').upper() == 'COMPLETED':
                return redirect(url_for('magazyn_dostawy.raport_przesuniecia', dostawa_id=dostawa_id, linia=linia))

        table_sur = get_table_name('magazyn_surowce', linia)
        table_opk = get_table_name('magazyn_opakowania', linia)
        wszystkie_produkty = set()
        for query, p in [
            ("SELECT DISTINCT nazwa FROM slownik_surowcow", ()),
            (f"SELECT DISTINCT nazwa FROM {table_sur}", ()),
            (f"SELECT DISTINCT nazwa FROM {table_opk}", ()),
            ("SELECT DISTINCT nazwa FROM magazyn_dodatki WHERE linia = %s", (linia,))
        ]:
            cursor.execute(query, p)
            wszystkie_produkty.update([r['nazwa'] for r in cursor.fetchall() if r and r.get('nazwa')])
        wszystkie_produkty = sorted(list(wszystkie_produkty))

    finally:
        conn.close()

    return render_template(
        'magazyn_dostawy/edycja.html',
        dostawa=dostawa, linia=linia,
        wszystkie_produkty=wszystkie_produkty,
        lokalizacje=LOKALIZACJE,
        lokalizacje_do=LOKALIZACJE_CEL,
        now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )


@magazyn_dostawy_bp.route('/przyjecie-ruchu/<dostawa_id>')
def przyjecie_ruchu(dostawa_id):
    """Formularz etapu 2: potwierdzenie przyjęcia przesunięcia lub dostawy zewnętrznej."""
    linia = request.args.get('linia', 'PSD').upper()
    conn = get_db_connection()
    dostawa = None
    pending_items = []
    accepted_count = 0
    total_count = 0
    is_external_delivery = False
    try:
        cursor = conn.cursor(dictionary=True)
        # Szukamy tylko po ID, bo ID jest unikalne. Pozwala to otworzyć dostawę 
        # nawet gdy linia w URL to 'ALL'.
        cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
        dostawa = cursor.fetchone()
        if not dostawa:
            return f"Nie znaleziono przesunięcia o ID: {dostawa_id}", 404
        
        # Pobieramy linię z bazy, jeśli ta w URL to 'ALL'
        if linia == 'ALL':
            linia = str(dostawa.get('linia', 'PSD')).upper()

        if dostawa.get('items'):
            try:
                dostawa['items_parsed'] = json.loads(dostawa['items'])
            except Exception:
                dostawa['items_parsed'] = []
        else:
            dostawa['items_parsed'] = []

        # Backward compatibility: ensure each item has a stable id for template/actions.
        items_changed = False
        for idx, item in enumerate(dostawa['items_parsed']):
            if not isinstance(item, dict):
                item = {}
                dostawa['items_parsed'][idx] = item
                items_changed = True
            if item.get('id') in (None, ''):
                item['id'] = f"legacy_{idx}"
                items_changed = True

        # Pre-assign SSCC for pending items without pallet number.
        for item in dostawa['items_parsed']:
            if not isinstance(item, dict):
                continue
            if item.get('accepted') or item.get('rejected'):
                continue
            if item.get('nr_palety') or item.get('sourcePalletNo'):
                continue

            p_type = 'opakowanie' if item.get('packageForm') == 'packaging' else 'surowiec'
            item['nr_palety'] = generate_pallet_id(linia, type=p_type)
            items_changed = True

        if items_changed:
            cursor.execute(
                "UPDATE magazyn_dostawy SET items = %s WHERE id = %s",
                (json.dumps(dostawa['items_parsed']), dostawa_id)
            )
            conn.commit()

        total_count = len(dostawa['items_parsed'])
        accepted_count = sum(1 for it in dostawa['items_parsed'] if it.get('accepted') or it.get('rejected'))
        pending_items = [it for it in dostawa['items_parsed'] if not it.get('accepted') and not it.get('rejected')]

        has_item_source = any(
            bool(str(it.get('sourceSpot') or '').strip())
            for it in dostawa['items_parsed']
            if isinstance(it, dict)
        )
        lokalizacja_z = str(dostawa.get('lokalizacja_z') or '').strip()
        is_external_delivery = (not lokalizacja_z) and (not has_item_source)

        printers = []
        try:
            cursor.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1")
            printers = cursor.fetchall()
        except Exception as pe:
            print(f"Error fetching printers in przyjecie_ruchu: {pe}")
    finally:
        conn.close()

    def _safe_date(value):
        if not value:
            return ''
        if isinstance(value, str):
            return value[:10]
        try:
            return value.strftime('%Y-%m-%d')
        except Exception:
            return ''

    pending_print_items = []
    for item in dostawa.get('items_parsed', []) or []:
        if not isinstance(item, dict):
            continue
        if item.get('accepted') or item.get('rejected'):
            continue

        raw_qty = item.get('netWeight')
        if raw_qty in (None, ''):
            raw_qty = item.get('unitsPerPallet')

        qty = 0
        if raw_qty not in (None, ''):
            try:
                qty = float(str(raw_qty).replace(',', '.'))
            except (TypeError, ValueError):
                qty = 0

        pending_print_items.append({
            'nr_palety': item.get('nr_palety') or item.get('sourcePalletNo'),
            'product_name': item.get('productName'),
            'nr_partii': item.get('nr_partii'),
            'data_produkcji': _safe_date(item.get('data_produkcji')),
            'data_przydatnosci': _safe_date(item.get('data_przydatnosci')),
            'qty': qty,
            'p_type': 'packaging' if item.get('packageForm') == 'packaging' else 'surowiec',
        })

    return render_template(
        'magazyn_dostawy/przyjecie_ruchu.html',
        dostawa=dostawa,
        pending_items=pending_items,
        accepted_count=accepted_count,
        total_count=total_count,
        linia=linia,
        is_external_delivery=is_external_delivery,
        printers=printers,
        pending_print_items=pending_print_items,
        now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

@magazyn_dostawy_bp.route('/api/zapisz', methods=['POST'])
def zapisz_dostawe():
    success, result = MagazynDostawyService.save_dostawa(request.json, session.get('login', 'system'))
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

    success, error, result = MagazynDostawyService.accept_item(
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
            report_url = url_for(
                'magazyn_dostawy.raport_przesuniecia',
                dostawa_id=result.get('dostawa_id') or dostawa_id,
                linia=result.get('linia', 'PSD'),
                autoprint=1,
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


@magazyn_dostawy_bp.route('/api/odrzuc-pozycje/<dostawa_id>', methods=['POST'])
def odrzuc_pozycje(dostawa_id):
    data = request.json or {}
    success, error, result = MagazynDostawyService.reject_item(
        dostawa_id,
        data.get('item_id'),
        reason=data.get('reason', ''),
        login=session.get('login', 'system'),
    )

    if success:
        report_url = None
        if result.get('all_processed'):
            report_url = url_for(
                'magazyn_dostawy.raport_przesuniecia',
                dostawa_id=result.get('dostawa_id') or dostawa_id,
                linia=result.get('linia', 'PSD'),
                autoprint=1,
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

    success, msg = MagazynDostawyService.accept_production_pallet(
        pallet_id,
        lokalizacja,
        linia=data.get('linia', 'PSD').upper(),
        login=session.get('login', 'system'),
        confirmed_weight=waga,
    )
    return jsonify({"success": success, "message": msg if success else None, "error": msg if not success else None})

@magazyn_dostawy_bp.route('/api/anuluj/<dostawa_id>', methods=['POST'])
def anuluj_dostawe(dostawa_id):
    success, msg = MagazynDostawyService.cancel_dostawa(dostawa_id, session.get('login', 'system'))
    return jsonify({"success": success, "message": msg})

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
        suggestions = MagazynDostawyService.get_location_suggestions(
            prefix=prefix,
            linia=linia,
            only_free_for_racks=only_free_for_racks,
            limit=limit,
        )
        return jsonify({"success": True, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "suggestions": []}), 500

@magazyn_dostawy_bp.route('/api/dostepne-palety')
def get_available_pallets():
    linia = request.args.get('linia', 'PSD').upper()
    prefix = (request.args.get('prefix', '') or '').strip()
    skip_lookup_raw = str(request.args.get('skip_warehouse_lookup', '') or '').strip().lower()
    skip_warehouse_lookup = skip_lookup_raw in ('1', 'true', 'yes', 'on')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        table_sur = get_table_name('magazyn_surowce', linia)
        table_opk = get_table_name('magazyn_opakowania', linia)
        
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
                lokalizacja LIKE %s OR
                nazwa LIKE %s OR
                COALESCE(nr_partii, '') LIKE %s OR
                COALESCE(nr_palety, '') LIKE %s OR
                CAST(id AS CHAR) = %s
            )"""
            like_prefix = f"{prefix}%"
            like_any = f"%{prefix}%"
            params = [like_prefix, like_any, like_any, like_any, prefix]

        pallets = []
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

        q3 = f"""
            SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, 'dodatek' as type
            FROM magazyn_dodatki
            WHERE {'1=1' if skip_warehouse_lookup else 'stan_magazynowy > 0'} AND {where_clause} AND linia = %s
        """
        cursor.execute(q3, (params if params else []) + [linia])
        pallets.extend(cursor.fetchall())

        pallets.sort(key=lambda x: (str(x.get('lokalizacja') or ''), str(x.get('nazwa') or ''), x.get('id') or 0))

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

            filtered_pallets.append(pal)

        return jsonify({"success": True, "pallets": filtered_pallets})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

# ==========================================
# PODZIAŁ PALETY (WORKOWANIE) W MAGAZYNIE
# ==========================================

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

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Szukaj w magazynie (najpierw AGRO, potem PSD)
        for linia in ['AGRO', 'PSD']:
            table_mag = get_table_name('magazyn_palety', linia)
            cursor.execute(f'''
                SELECT id, nr_palety, waga_netto as waga, produkt, lokalizacja, plan_id, 'magazyn' as source, %s as linia, data_planu
                FROM {table_mag}
                WHERE UPPER(nr_palety) = UPPER(%s) AND waga_netto > 0
                LIMIT 1
            ''', (linia, sscc))
            pal = cursor.fetchone()
            if pal:
                return jsonify({'success': True, 'pallet': pal})

        # Szukaj w produkcji (jeśli nieprzyjęta do magazynu formalnie)
        for linia in ['AGRO', 'PSD']:
            table_pal = get_table_name('palety_workowanie', linia)
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f'''
                SELECT pw.id, pw.nr_palety, pw.waga, p.produkt, '' as lokalizacja, pw.plan_id, 'produkcja' as source, %s as linia, p.data as data_planu
                FROM {table_pal} pw
                JOIN {table_plan} p ON pw.plan_id = p.id
                WHERE UPPER(pw.nr_palety) = UPPER(%s) AND pw.waga > 0
                LIMIT 1
            ''', (linia, sscc))
            pal = cursor.fetchone()
            if pal:
                return jsonify({'success': True, 'pallet': pal})

        # Szukaj w surowcach
        for linia in ['AGRO', 'PSD']:
            table_sur = get_table_name('magazyn_surowce', linia)
            cursor.execute(f'''
                SELECT id, nr_palety, stan_magazynowy as waga, nazwa as produkt, lokalizacja, NULL as plan_id, 'surowiec' as source, %s as linia, data_produkcji as data_planu
                FROM {table_sur}
                WHERE UPPER(nr_palety) = UPPER(%s) AND stan_magazynowy > 0
                LIMIT 1
            ''', (linia, sscc))
            pal = cursor.fetchone()
            if pal:
                return jsonify({'success': True, 'pallet': pal})

        # Szukaj w opakowaniach
        for linia in ['AGRO', 'PSD']:
            table_opak = get_table_name('magazyn_opakowania', linia)
            cursor.execute(f'''
                SELECT id, nr_palety, stan_magazynowy as waga, nazwa as produkt, lokalizacja, NULL as plan_id, 'opakowanie' as source, %s as linia, data_produkcji as data_planu
                FROM {table_opak}
                WHERE UPPER(nr_palety) = UPPER(%s) AND stan_magazynowy > 0
                LIMIT 1
            ''', (linia, sscc))
            pal = cursor.fetchone()
            if pal:
                return jsonify({'success': True, 'pallet': pal})

        # Szukaj w dodatkach
        cursor.execute(f'''
            SELECT id, nr_palety, stan_magazynowy as waga, nazwa as produkt, lokalizacja, NULL as plan_id, 'dodatek' as source, 'PSD' as linia, data_produkcji as data_planu
            FROM magazyn_dodatki
            WHERE UPPER(nr_palety) = UPPER(%s) AND stan_magazynowy > 0
            LIMIT 1
        ''', (sscc,))
        pal = cursor.fetchone()
        if pal:
            return jsonify({'success': True, 'pallet': pal})

        return jsonify({'success': False, 'error': 'Nie znaleziono palety o podanym kodzie.'})
    finally:
        conn.close()


@magazyn_dostawy_bp.route('/api/podzial-palety', methods=['POST'])
@login_required
def api_podzial_palety():
    data = request.json or {}
    mother_id = data.get('mother_id')
    mother_table = data.get('mother_table', 'magazyn') # 'magazyn' or 'produkcja'
    weight_to_take = _safe_float(data.get('weight_to_take', 0))

    if not mother_id or weight_to_take <= 0:
        return jsonify({'success': False, 'error': 'Błędne dane wejściowe.'})

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Najpierw musimy namierzyć z jakiej linii pochodzi paleta
        linia = None
        pal = None
        
        if mother_table == 'surowiec':
            for test_linia in ['AGRO', 'PSD']:
                t = get_table_name('magazyn_surowce', test_linia)
                cursor.execute(f"SELECT * FROM {t} WHERE id = %s", (mother_id,))
                pal = cursor.fetchone()
                if pal:
                    linia = test_linia
                    break
        elif mother_table == 'opakowanie':
            for test_linia in ['AGRO', 'PSD']:
                t = get_table_name('magazyn_opakowania', test_linia)
                cursor.execute(f"SELECT * FROM {t} WHERE id = %s", (mother_id,))
                pal = cursor.fetchone()
                if pal:
                    linia = test_linia
                    break
        elif mother_table == 'dodatek':
            t = 'magazyn_dodatki'
            cursor.execute(f"SELECT * FROM {t} WHERE id = %s", (mother_id,))
            pal = cursor.fetchone()
            if pal:
                linia = 'PSD'
        else:
            for test_linia in ['AGRO', 'PSD']:
                t = get_table_name('magazyn_palety' if mother_table == 'magazyn' else 'palety_workowanie', test_linia)
                cursor.execute(f"SELECT * FROM {t} WHERE id = %s", (mother_id,))
                pal = cursor.fetchone()
                if pal:
                    linia = test_linia
                    break

        if not pal:
            return jsonify({'success': False, 'error': 'Nie znaleziono palety bazowej w bazie danych.'})

        if mother_table in ('surowiec', 'opakowanie', 'dodatek'):
            waga_obecna = float(pal.get('stan_magazynowy') or 0)
        else:
            waga_obecna = float(pal.get('waga_netto') if mother_table == 'magazyn' else pal.get('waga') or 0)
        
        if weight_to_take >= waga_obecna:
            return jsonify({'success': False, 'error': f'Waga do zabrania ({weight_to_take} kg) jest równa lub większa niż stan palety ({waga_obecna} kg).'})

        nowa_waga = round(waga_obecna - weight_to_take, 3)

        if mother_table == 'opakowanie':
            new_sscc = f"OPA-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        elif mother_table == 'dodatek':
            new_sscc = f"DOD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        elif mother_table == 'surowiec':
            new_sscc = f"SUR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        else:
            new_sscc = f"QA-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        login = session.get('login', 'System')
        now_dt = datetime.now()

        new_pallet_id = None
        
        if mother_table in ('surowiec', 'opakowanie', 'dodatek'):
            if mother_table == 'surowiec':
                t_sur = get_table_name('magazyn_surowce', linia)
            elif mother_table == 'opakowanie':
                t_sur = get_table_name('magazyn_opakowania', linia)
            else:
                t_sur = 'magazyn_dodatki'
                
            cursor.execute(f"UPDATE {t_sur} SET stan_magazynowy = %s WHERE id = %s", (nowa_waga, mother_id))
            
            cursor.execute(f'''
                INSERT INTO {t_sur} (
                    nr_palety, nazwa, stan_magazynowy, data_produkcji, termin_przydatnosci,
                    nr_partii, certyfikat, lokalizacja, uzytkownik_dodajacy, data_dodania
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                new_sscc, pal.get('nazwa'), weight_to_take, pal.get('data_produkcji'), pal.get('termin_przydatnosci'),
                pal.get('nr_partii'), pal.get('certyfikat'), pal.get('lokalizacja'), login, now_dt
            ))
            new_pallet_id = cursor.lastrowid
        else:
            # Update mother pallet
            t_mother = get_table_name('magazyn_palety' if mother_table == 'magazyn' else 'palety_workowanie', linia)
            waga_col = 'waga_netto' if mother_table == 'magazyn' else 'waga'
            cursor.execute(f"UPDATE {t_mother} SET {waga_col} = %s WHERE id = %s", (nowa_waga, mother_id))

            plan_id = pal.get('plan_id')

            # Zawsze musi zostać utworzony rekord w produkcji
            t_prod = get_table_name('palety_workowanie', linia)
            cursor.execute(f'''
                INSERT INTO {t_prod} (plan_id, waga, data_dodania, nr_palety, status, data_potwierdzenia, dodal_login, potwierdzil_login)
                VALUES (%s, %s, %s, %s, 'przyjeta', %s, %s, %s)
            ''', (
                plan_id, weight_to_take, now_dt, new_sscc, now_dt, login, login
            ))
            new_prod_id = cursor.lastrowid
            new_pallet_id = new_prod_id

            # Jeśli paleta była w magazynie, nowa też musi wylądować w magazynie
            if mother_table == 'magazyn':
                t_mag = get_table_name('magazyn_palety', linia)
                cursor.execute(f'''
                    INSERT INTO {t_mag} (
                        paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, 
                        nr_palety, lokalizacja, user_login, data_potwierdzenia, created_at, linia
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    new_prod_id, plan_id, pal.get('data_planu'), pal.get('produkt'), weight_to_take,
                    new_sscc, pal.get('lokalizacja'), login, now_dt, now_dt, linia
                ))

        conn.commit()

        return jsonify({
            'success': True, 
            'label_url': f"/magazyn-dostawy/podglad-etykiety-system/{new_pallet_id}?linia={linia}",
            'new_pallet': {
                'id': new_pallet_id,
                'nr_palety': new_sscc,
                'waga': weight_to_take,
                'linia': linia,
                'plan_id': plan_id
            }
        })
    except Exception as e:
        conn.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# ==========================================
# USTAWIENIA LOKALIZACJI
# ==========================================

@magazyn_dostawy_bp.route('/ustawienia_lokalizacji')
@login_required
def ustawienia_lokalizacji():
    linia = request.args.get('linia', 'PSD').upper()
    if linia not in ['PSD', 'AGRO']:
        linia = 'PSD'
        
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM magazyn_dozwolone_lokalizacje ORDER BY nazwa ASC")
        lokalizacje = cur.fetchall()
    finally:
        conn.close()
        
    return render_template('magazyn_dostawy/ustawienia_lokalizacji.html', linia=linia, lokalizacje=lokalizacje)

@magazyn_dostawy_bp.route('/api/ustawienia_lokalizacji', methods=['POST'])
@login_required
def api_add_lokalizacja():
    data = request.json
    nazwa = data.get('nazwa', '').strip().upper()
    opis = data.get('opis', '').strip()
    
    if not nazwa:
        return jsonify({'success': False, 'error': 'Nazwa lokalizacji jest wymagana.'}), 400
        
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO magazyn_dozwolone_lokalizacje (nazwa, opis) VALUES (%s, %s)", (nazwa, opis))
        conn.commit()
        return jsonify({'success': True, 'message': 'Lokalizacja dodana pomyślnie.'})
    except Exception as e:
        conn.rollback()
        if 'Duplicate entry' in str(e):
            return jsonify({'success': False, 'error': 'Taka lokalizacja już istnieje.'}), 400
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@magazyn_dostawy_bp.route('/api/ustawienia_lokalizacji/<int:loc_id>', methods=['DELETE'])
@login_required
def api_delete_lokalizacja(loc_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM magazyn_dozwolone_lokalizacje WHERE id = %s", (loc_id,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
