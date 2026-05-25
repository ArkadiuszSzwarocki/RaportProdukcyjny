from flask import Blueprint, render_template, request, jsonify, session, url_for, redirect, current_app
import traceback
from app.db import get_db_connection, get_table_name
from app.decorators import login_required
from app.services.magazyn_dostawy_service import MagazynDostawyService
from app.utils.pallet_label import prepare_pallet_label_data
import json
from datetime import datetime

magazyn_dostawy_bp = Blueprint('magazyn_dostawy', __name__, url_prefix='/magazyn-dostawy')

# Lokalizacje z systemu Mleczna Droga
LOKALIZACJE_ZRODLO = [
    'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02',
    'OSIP', 'BF_MS01', 'BF_MP01', 'KO01', 'PSD', 'PSD01',
    'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP',
]

# Regały R04 (20 poz.), R05 (20 poz.), R06 (10 poz.), R07 (20 poz.)
_r04 = [f'R04{str(i+1).zfill(2)}01' for i in range(20)]
_r05 = [f'R05{str(i+1).zfill(2)}01' for i in range(20)]
_r06 = [f'R06{str(i+1).zfill(2)}01' for i in range(10)]
_r07 = [f'R07{str(i+1).zfill(2)}01' for i in range(20)]
# OSIP – 77 lokalizacji OS01..OS77
_osip = [f'OS{str(i+1).zfill(2)}' for i in range(77)]
# Stanowiska produkcyjne BB01..BB24, MZ01..MZ06
_bb = [f'BB{str(i+1).zfill(2)}' for i in range(24)]
_mz = ['MZ01', 'MZ02', 'MZ03', 'MZ04', 'MZ05', 'MZ06', 'MZ05-01', 'MZ06-01']

LOKALIZACJE_SZCZEGOLOWE = {
    'Magazyny': LOKALIZACJE_ZRODLO,
    'Regał R04': _r04,
    'Regał R05': _r05,
    'Regał R06': _r06,
    'Regał R07': _r07,
    'OSIP (OS01-OS77)': _osip,
    'Stanowiska BB': _bb,
    'Stanowiska MZ': _mz,
}

# Płaska lista na potrzeby selecta źródło/cel
LOKALIZACJE = sorted(list(set(LOKALIZACJE_ZRODLO + ['R04', 'R05', 'R06', 'R07', 'PSD01'])))
LOKALIZACJE_CEL = ['BF_MS01', 'BF_MP01', 'MS01', 'MP01', 'PSD01']
BUFORY = ['BF_MS01', 'BF_MP01']


def _safe_float(value):
    try:
        if value in (None, ''):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_datetime_str(value):
    if not value:
        return '-'
    if isinstance(value, str):
        return value
    try:
        return value.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(value)


def _format_label_weight(value):
    qty = _safe_float(value)
    if abs(qty - round(qty)) < 1e-6:
        return str(int(round(qty)))
    return f"{qty:.2f}".rstrip('0').rstrip('.')

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
        cursor.execute(
            f"SELECT DISTINCT nazwa FROM {table_sur}"
            f" UNION SELECT DISTINCT nazwa FROM {table_opk}"
            f" UNION SELECT DISTINCT nazwa FROM magazyn_dodatki WHERE linia = %s",
            (linia,)
        )
        wszystkie_produkty = [r['nazwa'] for r in cursor.fetchall()]

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
    return render_template('magazyn_dostawy/oczekujace.html',
                           dostawy=dostawy, linia=linia,
                           lok_grupy=LOKALIZACJE_SZCZEGOLOWE)


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
    )


@magazyn_dostawy_bp.route('/api/active-printers', methods=['GET'])
@login_required
def active_printers_api():
    """Zwraca listę drukarek sieciowych (bridge), a gdy niedostępne - fallback DB."""
    printers = []

    try:
        from app.services.print_server import get_printer
        network_printers = get_printer().list_network_printers()
        for p in network_printers:
            ip = str(p.get('ip') or '').strip()
            if not ip:
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
        if printers:
            return jsonify({'success': True, 'printers': printers, 'source': 'network'})
    except Exception as network_err:
        try:
            current_app.logger.warning('active_printers_api: network printers unavailable, fallback to DB: %s', network_err)
        except Exception:
            pass

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1 ORDER BY id ASC")
        rows = cur.fetchall() or []
        printers = [
            {
                'id': r.get('id'),
                'selection_value': f"db:{r.get('id')}",
                'nazwa': r.get('nazwa'),
                'ip': r.get('ip'),
                'lokalizacja': r.get('lokalizacja'),
                'source': 'db',
            }
            for r in rows
        ]
        return jsonify({'success': True, 'printers': printers, 'source': 'db'})
    except Exception as e:
        try:
            current_app.logger.exception('active_printers_api failed: %s', e)
        except Exception:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
        cursor.execute(
            f"SELECT DISTINCT nazwa FROM {table_sur}"
            f" UNION SELECT DISTINCT nazwa FROM {table_opk}"
            f" UNION SELECT DISTINCT nazwa FROM magazyn_dodatki WHERE linia = %s",
            (linia,)
        )
        wszystkie_produkty = [r['nazwa'] for r in cursor.fetchall()]

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

    return render_template(
        'magazyn_dostawy/przyjecie_ruchu.html',
        dostawa=dostawa,
        pending_items=pending_items,
        accepted_count=accepted_count,
        total_count=total_count,
        linia=linia,
        is_external_delivery=is_external_delivery,
        printers=printers,
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
            "message": f"Przyjęto pomyślnie."
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
            url = "https://127.0.0.1:3001/drukuj-zpl"
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

        q = f"""
            SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, 'surowiec' as type
            FROM {table_sur} 
            WHERE {'1=1' if skip_warehouse_lookup else 'stan_magazynowy > 0'} AND {where_clause}
            UNION ALL
            SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, 'opakowanie' as type
            FROM {table_opk}
            WHERE {'1=1' if skip_warehouse_lookup else 'stan_magazynowy > 0'} AND {where_clause}
            UNION ALL
            SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, 'dodatek' as type
            FROM magazyn_dodatki
            WHERE {'1=1' if skip_warehouse_lookup else 'stan_magazynowy > 0'} AND {where_clause} AND linia = %s
            ORDER BY lokalizacja, nazwa, id
        """
        # We need to repeat params 3 times because of 3 parts in UNION, and add 'linia' at the end
        all_params = (params * 3 if params else []) + [linia]
        cursor.execute(q, all_params)
        pallets = cursor.fetchall()

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
