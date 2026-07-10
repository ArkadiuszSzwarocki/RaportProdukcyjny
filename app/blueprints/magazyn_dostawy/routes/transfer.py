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

@magazyn_dostawy_bp.route('/')
def lista_dostaw():
    linia = request.args.get('linia', 'PSD').upper()
    # Lista przesuniec ma pokazywac tylko ruchy wewnetrzne (z lokalizacja zrodlowa).
    dostawy = [d for d in DeliveryQueries.get_dostawy(linia) if d.get('lokalizacja_z')]
    return render_template('magazyn_dostawy/lista.html', dostawy=dostawy, linia=linia)

@magazyn_dostawy_bp.route('/oczekujace')
def oczekujace():
    linia = request.args.get('linia', 'PSD').upper()
    # Uniwersalny skaner - pobieraj dane ze wszystkich linii dla pending_scan_items
    dostawy = DeliveryQueries.get_oczekujace('ALL')
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

@magazyn_dostawy_bp.route('/raport')
def raport():
    linia = request.args.get('linia', 'PSD').upper()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    dostawy = DeliveryQueries.get_raport(date_from, date_to)
    
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

        actual_locations = {}
        actual_times = {}
        if items:
            linia = dostawa.get('linia', 'PSD').upper()
            from app.db import get_table_name
            table_sur = get_table_name('magazyn_surowce', linia)
            table_opk = get_table_name('magazyn_opakowania', linia)
            
            nr_palet_sur = []
            nr_palet_opk = []
            for it in items:
                nr = it.get('nr_palety')
                if nr:
                    if it.get('packageForm') == 'packaging' or it.get('scannedType') == 'opakowanie':
                        nr_palet_opk.append(nr)
                    else:
                        nr_palet_sur.append(nr)
            
            still_pending = False
            try:
                if nr_palet_sur:
                    placeholders = ','.join(['%s']*len(nr_palet_sur))
                    cursor.execute(f"SELECT nr_palety, lokalizacja, updated_at FROM {table_sur} WHERE nr_palety IN ({placeholders}) AND stan_magazynowy > 0", tuple(nr_palet_sur))
                    for row in cursor.fetchall():
                        actual_locations[row['nr_palety']] = row['lokalizacja']
                        actual_times[row['nr_palety']] = row['updated_at']
                        if row['lokalizacja'] == 'OCZEKUJĄCE':
                            still_pending = True
                if nr_palet_opk:
                    placeholders = ','.join(['%s']*len(nr_palet_opk))
                    cursor.execute(f"SELECT nr_palety, lokalizacja, updated_at FROM {table_opk} WHERE nr_palety IN ({placeholders}) AND stan_magazynowy > 0", tuple(nr_palet_opk))
                    for row in cursor.fetchall():
                        actual_locations[row['nr_palety']] = row['lokalizacja']
                        actual_times[row['nr_palety']] = row['updated_at']
                        if row['lokalizacja'] == 'OCZEKUJĄCE':
                            still_pending = True
                
                is_external = not dostawa.get('lokalizacja_z')
                if is_external and dostawa.get('status') == 'OCZEKUJE' and not still_pending and (nr_palet_sur or nr_palet_opk):
                    # Zmieniamy tymczasowo dla raportu (lub można zupdatować w DB)
                    dostawa['status'] = 'COMPLETED'
                    cursor.execute("UPDATE magazyn_dostawy SET status='COMPLETED' WHERE id=%s", (dostawa_id,))
                    conn.commit()
            except Exception as e:
                import logging
                logging.warning(f"Error checking physical pallet locations for delivery {dostawa_id}: {e}")

        rows = []
        summary_map = {}
        reported_totals_by_unit = {}
        moved_totals_by_unit = {}
        rejected_totals_by_unit = {}
        all_target_locations = set() # reload trigger
        for idx, item in enumerate(items, start=1):
            qty_raw = item.get('quantity') or item.get('netWeight') or item.get('unitsPerPallet') or 0
            qty = _safe_float(qty_raw)
            unit = 'szt' if item.get('packageForm') == 'packaging' else 'kg'
            product_name = (item.get('productName') or 'Brak nazwy').strip() or 'Brak nazwy'
            source_location = item.get('sourceSpot') or dostawa.get('lokalizacja_z') or '-'
            target_location = item.get('lokalizacja_przyjecia') or dostawa.get('lokalizacja_do') or '-'
            nr_pal = item.get('nr_palety')
            
            accepted_at = item.get('accepted_at') or '-'
            if nr_pal and actual_locations.get(nr_pal):
                if actual_locations.get(nr_pal) != 'OCZEKUJĄCE':
                    target_location = actual_locations.get(nr_pal)
                    if actual_times.get(nr_pal):
                        time_val = actual_times.get(nr_pal)
                        try:
                            accepted_at = time_val.strftime('%Y-%m-%d %H:%M:%S')
                        except AttributeError:
                            accepted_at = str(time_val)
            
            if target_location != '-':
                all_target_locations.add(target_location)
                
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
                'accepted_at': accepted_at,
                'accepted': accepted,
                'rejected': rejected,
                'rejected_by': item.get('rejected_by') or '-',
                'rejected_at': item.get('rejected_at') or '-',
                'rejected_reason': item.get('rejected_reason') or '-',
                'status_label': status_label,
            }
            rows.append(row_data)

            summary_key = (product_name, unit, status_label)
            reported_totals_by_unit[unit] = reported_totals_by_unit.get(unit, 0.0) + qty
            summary_map[summary_key] = summary_map.get(summary_key, 0.0) + qty
            if accepted:
                moved_totals_by_unit[unit] = moved_totals_by_unit.get(unit, 0.0) + qty
            elif rejected:
                rejected_totals_by_unit[unit] = rejected_totals_by_unit.get(unit, 0.0) + qty
            else:
                if 'pending_totals_by_unit' not in locals():
                    pending_totals_by_unit = {}
                pending_totals_by_unit[unit] = pending_totals_by_unit.get(unit, 0.0) + qty

        summary_rows = []
        for idx, ((name, unit, status_label), qty) in enumerate(sorted(summary_map.items(), key=lambda x: (x[0][0].lower(), x[0][2])), start=1):
            summary_rows.append({'lp': idx, 'product_name': name, 'unit': unit, 'qty': qty, 'status_label': status_label})

        def _to_total_rows(totals_dict):
            return [
                {'unit': unit, 'qty': qty}
                for unit, qty in sorted(totals_dict.items(), key=lambda x: x[0])
                if qty > 0
            ]

        reported_total_rows = _to_total_rows(reported_totals_by_unit)
        moved_total_rows = _to_total_rows(moved_totals_by_unit)
        rejected_total_rows = _to_total_rows(rejected_totals_by_unit)
        pending_total_rows = _to_total_rows(locals().get('pending_totals_by_unit', {}))
        accepted_count = sum(1 for r in rows if r.get('accepted'))
        rejected_count = sum(1 for r in rows if r.get('rejected'))
        pending_count = max(len(rows) - accepted_count - rejected_count, 0)
        
        lokalizacja_do_str = dostawa.get('lokalizacja_do')
        if not lokalizacja_do_str:
            lokalizacja_do_str = ", ".join(sorted(all_target_locations)) if all_target_locations else '-'

        is_external = bool(dostawa.get('supplier')) or not dostawa.get('lokalizacja_z')
        template_name = 'magazyn_dostawy/raport_dostawy_zewnetrznej_print.html' if is_external else 'magazyn_dostawy/raport_przesuniecia_print.html'
        
        return render_template(
            template_name,
            dostawa=dostawa,
            rows=rows,
            summary_rows=summary_rows,
            total_rows=moved_total_rows,
            reported_total_rows=reported_total_rows,
            moved_total_rows=moved_total_rows,
            rejected_total_rows=rejected_total_rows,
            pending_total_rows=pending_total_rows,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            pending_count=pending_count,
            lokalizacja_do_str=lokalizacja_do_str,
            created_at_str=_safe_datetime_str(dostawa.get('created_at')),
            confirmed_at_str=_safe_datetime_str(dostawa.get('potwierdzone_at')),
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            autoprint=autoprint,
        )
    finally:
        conn.close()

