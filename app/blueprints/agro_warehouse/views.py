import re
from flask import render_template, request, jsonify, session, redirect, url_for, current_app, flash
from app.services.agro.agro_opakowania_service import AgroOpakowaniaService
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
from .api_reports import _resolve_report_bag_kg

@agro_warehouse_bp.route('/agro/magazyn')
@login_required
@dynamic_role_required('magazyn.agro_total')
def index():
    linia = request.args.get('linia', 'Agro')
    from datetime import datetime, date as _date
    try:
        dzisiaj = datetime.strptime(request.args.get('data'), '%Y-%m-%d').date() if request.args.get('data') else _date.today()
    except Exception:
        dzisiaj = _date.today()
    inventory = AgroSurowceService.get_inventory_grouped(linia=linia)
    inventory_by_location = AgroSurowceService.get_inventory_by_location(linia=linia)
    history = AgroSurowceService.get_history(limit=50, linia=linia)
    pending = AgroSurowceService.get_history(status='OCZEKUJACE', linia=linia)
    dictionary = AgroSurowceService.get_dictionary()
    try:
        current_plan = AgroTanksService.get_current_running_plan(linia=linia)
        current_plan_id = current_plan['id'] if current_plan else None
        current_plan_name = current_plan['produkt'] if current_plan else None
    except Exception:
        current_plan_id = None
        current_plan_name = None
    try:
        pending_wg = DeliveryQueries.get_pending_production_pallets('AGRO')
    except Exception:
        pending_wg = []
    try:
        production_tanks = AgroTanksService.get_production_tanks()
    except Exception:
        production_tanks = {'BB': [], 'MZ': [], 'KO': [], 'ALL': []}
    magazyn_palety, unconfirmed_palety, suma_wykonanie = DashboardService.get_warehouse_data(dzisiaj, linia=linia)
    return render_template('agro_warehouse/index.html', inventory=inventory, inventory_by_location=inventory_by_location, history=history, pending=pending, dictionary=dictionary, linia=linia, current_plan_id=current_plan_id, current_plan_name=current_plan_name, production_tanks=production_tanks, pending_wg=pending_wg, magazyn_palety=magazyn_palety, unconfirmed_palety=unconfirmed_palety, dzisiaj=str(dzisiaj), rola=session.get('rola'))

@agro_warehouse_bp.route('/agro/magazyn/opakowania')
@login_required
@dynamic_role_required('magazyn.agro_packaging')
def opakowania():
    """Simple view for packaging warehouse (magazyn_opakowania) in AGRO."""
    linia = request.args.get('linia', 'Agro')
    try:
        items = AgroOpakowaniaService.get_packaging_inventory(linia=linia)
    except Exception:
        items = []
    return render_template('agro_warehouse/opakowania.html', items=items, linia=linia)

@agro_warehouse_bp.route('/agro/magazyn/surowce-w-produkcji')
@login_required
@dynamic_role_required('agro.magazyn')
def surowce_w_produkcji():
    linia = request.args.get('linia', 'AGRO')
    snapshot = AgroTanksService.get_production_inventory_snapshot(linia=linia, show_empty=True)
    import re

    def get_group(tank):
        m = re.match('([A-Z]+)[ -]?(\\d+)', tank.upper())
        if not m:
            return None
        prefix = m.group(1)
        num = int(m.group(2))
        if prefix == 'BB':
            if 1 <= num <= 6:
                return 'Waga01 (BB01-BB06)'
            if 11 <= num <= 14:
                return 'Waga02 (BB11-BB14)'
            if 15 <= num <= 22:
                return 'Waga03 (BB15-BB22)'
            return None
        if prefix == 'MZ':
            if 7 <= num <= 10:
                return 'Waga02 (MZ07-MZ10)'
            if 23 <= num <= 24:
                return 'Waga03 (MZ23-MZ24)'
            return None
        if prefix == 'KO':
            if 1 <= num <= 12:
                return 'KO - Rząd 1 (KO01-KO12)'
            if 13 <= num <= 24:
                return 'KO - Rząd 2 (KO13-KO24)'
            return None
        return None
    grouped_entries = {}
    for item in snapshot:
        g = get_group(item.get('zbiornik', ''))
        if g is not None:
            if g not in grouped_entries:
                grouped_entries[g] = []
            grouped_entries[g].append(item)

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s.get('zbiornik', ''))]
    for g in grouped_entries:
        grouped_entries[g].sort(key=natural_sort_key)
    order = ['Waga01 (BB01-BB06)', 'Waga02 (BB11-BB14)', 'Waga03 (BB15-BB22)', 'Waga02 (MZ07-MZ10)', 'Waga03 (MZ23-MZ24)', 'KO - Rząd 1 (KO01-KO12)', 'KO - Rząd 2 (KO13-KO24)']
    sorted_grouped_entries = {k: grouped_entries[k] for k in order if k in grouped_entries}
    return render_template('agro_warehouse/surowce_w_produkcji.html', grouped_entries=sorted_grouped_entries, linia=linia)

@agro_warehouse_bp.route('/agro/raport_palet', methods=['GET'])
@login_required
def raport_palet():
    """Generates a printable pallet report for AGRO line."""
    from datetime import date, timedelta
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    data_od = request.args.get('data_od', str(start_of_week))
    data_do = request.args.get('data_do', str(end_of_week))
    legacy_data = request.args.get('data')
    if legacy_data and (not request.args.get('data_od')):
        data_od = legacy_data
        data_do = legacy_data
    plan_id = request.args.get('plan_id')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = "\n            SELECT w.id as work_id, w.produkt, w.tonaz_rzeczywisty as w_kg, \n                   z.id as zasyp_id, z.tonaz_rzeczywisty as z_kg,\n                   w.nazwa_zlecenia, w.typ_produkcji, w.typ_opakowania, w.nr_partii,\n                   z.typ_produkcji as zasyp_typ_produkcji, w.data_planu,\n                   w.start_machine_counter, w.stop_machine_counter, w.status,\n                   COALESCE(z.odrzuty_przesiewacz, w.odrzuty_przesiewacz, 0) as odrzuty_przesiewacz\n            FROM plan_produkcji_agro w\n            LEFT JOIN plan_produkcji_agro z ON w.zasyp_id = z.id\n            WHERE (w.sekcja IN ('Workowanie', 'Czyszczenie') OR LOWER(w.produkt) LIKE '%czyszczenie%') AND (w.is_deleted = 0 OR w.is_deleted IS NULL)\n        "
        params = []
        if plan_id:
            query += ' AND w.id = %s'
            params.append(plan_id)
        else:
            query += ' AND w.data_planu BETWEEN %s AND %s'
            params.extend([data_od, data_do])
            query += " AND w.status = 'zakonczone'"
            query += ' ORDER BY w.data_planu DESC, w.id DESC'
        cursor.execute(query, tuple(params))
        plans = cursor.fetchall()
        if plan_id and plans:
            data_planu = str(plans[0]['data_planu'])
        else:
            data_planu = data_od
        from app.services.mqtt_service import get_latest_data
        live_data = get_latest_data()
        report_data = []
        product_typ_cache = {}
        for p in plans:
            if p.get('status') == 'w toku':
                p['live_local_counter'] = live_data.get('local_counter', 0)
            cursor.execute('\n                SELECT s.id, \n                       (s.waga + COALESCE((SELECT SUM(d.kg) FROM dosypki_agro d WHERE d.szarza_id = s.id AND d.potwierdzone = 1 AND d.anulowana = 0), 0)) as waga, \n                       s.data_dodania \n                FROM szarze_agro s\n                WHERE s.plan_id = %s \n                ORDER BY s.data_dodania ASC\n            ', (p['zasyp_id'],))
            batches_raw = cursor.fetchall()
            cursor.execute('\n                SELECT id, waga_kg as waga, COALESCE(zuzyte_kiedy, created_at) as data_dodania, kategoria \n                FROM agro_mix_rozliczenie \n                WHERE zuzyte_w_id = %s \n                ORDER BY data_dodania ASC\n            ', (p['zasyp_id'],))
            mixes_raw = cursor.fetchall()
            cursor.execute('\n                SELECT id, nazwa, kg, data_zlecenia \n                FROM dosypki_agro \n                WHERE plan_id = %s AND szarza_id IS NULL AND potwierdzone = 1 AND anulowana = 0\n                ORDER BY data_zlecenia ASC\n            ', (p['zasyp_id'],))
            solo_dosypki = cursor.fetchall()
            all_inputs = []
            for b_raw in batches_raw:
                all_inputs.append({'label': f"Zasyp #{b_raw['id']}", 'waga': b_raw['waga'] or 0, 'time': b_raw['data_dodania']})
            for d_raw in solo_dosypki:
                all_inputs.append({'label': f"Dosypka {d_raw['nazwa']} #{d_raw['id']}", 'waga': d_raw['kg'] or 0, 'time': d_raw['data_zlecenia']})
            for m_raw in mixes_raw:
                all_inputs.append({'label': f"MIX {m_raw['kategoria'].replace('_', ' ')} #{m_raw['id']}", 'waga': m_raw['waga'] or 0, 'time': m_raw['data_dodania']})
            all_inputs.sort(key=lambda x: x['time'] if x['time'] else datetime.min)
            current_in_kg = 0
            input_ranges = []
            for inp in all_inputs:
                start = current_in_kg
                end = current_in_kg + inp['waga']
                input_ranges.append({'label': inp['label'], 'start': start, 'end': end})
                current_in_kg = end
            cursor.execute("\n                SELECT \n                    p.id, p.waga, p.status, p.data_dodania, \n                    p.dodal_login,\n                    NULLIF(TRIM(COALESCE(m.user_login, p.potwierdzil_login)), '') as potwierdzil_login,\n                    COALESCE(m.data_potwierdzenia, p.data_potwierdzenia) as data_potwierdzenia,\n                    COALESCE(m.nr_plomby, p.nr_plomby) as nr_plomby,\n                    COALESCE(m.nr_palety, p.nr_palety) as nr_palety\n                FROM palety_agro p\n                LEFT JOIN magazyn_palety_agro m ON p.id = m.paleta_workowanie_id\n                WHERE p.plan_id = %s\n                ORDER BY p.data_dodania ASC\n            ", (p['work_id'],))
            pallets_raw = cursor.fetchall()
            current_out_kg = 0
            processed_pallets = []
            for pal_raw in pallets_raw:
                p_start = current_out_kg
                p_end = current_out_kg + (pal_raw['waga'] or 0)
                shares = []
                for ir in input_ranges:
                    overlap_start = max(p_start, ir['start'])
                    overlap_end = min(p_end, ir['end'])
                    if overlap_end > overlap_start:
                        overlap_kg = overlap_end - overlap_start
                        waga_palety = float(pal_raw['waga'] or 0)
                        percent = overlap_kg / waga_palety * 100 if waga_palety > 0 else 0
                        if percent >= 0.5:
                            shares.append(f"{ir['label']} ({round(percent)}%)")
                pal_raw['sklad'] = ', '.join(shares) if shares else 'Nieznany skład'
                processed_pallets.append(pal_raw)
                current_out_kg = p_end
            cursor.execute('SELECT id, waga_kg as waga_kg, kategoria, autor_login, created_at FROM agro_mix_rozliczenie WHERE zuzyte_w_id = %s', (p['zasyp_id'],))
            mixes_summary = cursor.fetchall()
            cursor.execute('\n                SELECT id, opakowanie_nazwa, stan_przed, wyprodukowano_szt, szt_na_palecie, zuzyte_worki, stan_po, autor_login, created_at, kg_na_worek\n                FROM agro_workowanie_rozliczenie\n                WHERE plan_id = %s\n                ORDER BY created_at ASC\n            ', (p['work_id'],))
            rozliczenia = cursor.fetchall()
            cursor.execute('\n                SELECT ap.id, o.nazwa as opakowanie_nazwa, ap.stan_poczatkowy as stan_przed, ap.created_at\n                FROM agro_plan_opakowania ap\n                JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id\n                WHERE ap.plan_id = %s AND ap.is_active = TRUE\n                ORDER BY ap.created_at ASC\n            ', (p['work_id'],))
            aktywne_opakowania = cursor.fetchall()
            bag_kg = _resolve_report_bag_kg(cursor, p, rozliczenia, product_typ_cache)
            packaging_stocks = {}
            unique_names = set()
            for op in rozliczenia:
                if op.get('opakowanie_nazwa'):
                    unique_names.add(op['opakowanie_nazwa'])
            for aop in aktywne_opakowania:
                if aop.get('opakowanie_nazwa'):
                    unique_names.add(aop['opakowanie_nazwa'])
            for name in unique_names:
                cursor.execute("\n                    SELECT COALESCE(SUM(stan_magazynowy), 0) as total_stock \n                    FROM magazyn_opakowania \n                    WHERE nazwa = %s AND (lokalizacja != 'ZUŻYTE' OR lokalizacja IS NULL)\n                ", (name,))
                stock_row = cursor.fetchone()
                packaging_stocks[name] = float(stock_row['total_stock']) if stock_row else 0.0
            report_data.append({'plan': p, 'palety': processed_pallets, 'mixes': mixes_summary, 'opakowania': rozliczenia, 'aktywne_opakowania': aktywne_opakowania, 'bag_kg': bag_kg, 'packaging_stocks': packaging_stocks, 'total_pallet_kg': sum((pal['waga'] or 0 for pal in pallets_raw)), 'total_mix_kg': sum((m['waga_kg'] or 0 for m in mixes_summary))})
        if not plan_id:
            return render_template('agro_warehouse/raport_palet_select.html', plans=plans, data_od=data_od, data_do=data_do, is_ajax=is_ajax)
        return render_template('agro_warehouse/raport_palet.html', report_data=report_data, data_planu=data_planu, single_view=bool(plan_id), is_ajax=is_ajax, print_date=datetime.now().strftime('%d.%m.%Y %H:%M'))
    except Exception as e:
        current_app.logger.error(f'Error generating raport_palet: {e}')
        return (f'Błąd generowania raportu: {str(e)}', 500)
    finally:
        conn.close()


@agro_warehouse_bp.route('/agro/raport_palet_daily', methods=['GET'])
@login_required
def raport_palet_daily():
    """Daily pallet report for AGRO line. Shows pallets created on a given day and allows CSV export."""
    from datetime import datetime, date, timedelta
    data_str = request.args.get('data') or request.args.get('date') or date.today().isoformat()
    try:
        day = datetime.strptime(data_str, '%Y-%m-%d').date()
    except Exception:
        day = date.today()
    next_day = day + timedelta(days=1)

    export = request.args.get('export') == 'csv'
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT p.id as paleta_id, COALESCE(m.nr_palety, p.nr_palety) as nr_palety, p.waga, p.status,
                   p.data_dodania, p.dodal_login as dodal, COALESCE(m.potwierdzil_login, p.potwierdzil_login) as potwierdzil,
                   w.produkt, w.id as plan_id, w.nr_partii
            FROM palety_agro p
            LEFT JOIN magazyn_palety_agro m ON m.paleta_workowanie_id = p.id
            LEFT JOIN plan_produkcji_agro w ON w.id = p.plan_id
            WHERE p.data_dodania >= %s AND p.data_dodania < %s
            ORDER BY p.data_dodania ASC
            """,
            (day.isoformat(), next_day.isoformat()),
        )
        rows = cursor.fetchall()
        if export:
            # stream CSV
            import io, csv
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['data_dodania', 'nr_palety', 'produkt', 'nr_partii', 'waga_kg', 'plan_id', 'dodal', 'potwierdzil', 'status'])
            for r in rows:
                writer.writerow([
                    r.get('data_dodania').strftime('%Y-%m-%d %H:%M:%S') if r.get('data_dodania') else '',
                    r.get('nr_palety') or '',
                    r.get('produkt') or '',
                    r.get('nr_partii') or '',
                    r.get('waga') or 0,
                    r.get('plan_id') or '',
                    r.get('dodal') or '',
                    r.get('potwierdzil') or '',
                    r.get('status') or '',
                ])
            output.seek(0)
            return Response(output.getvalue(), mimetype='text/csv', headers={
                'Content-Disposition': f'attachment; filename=raport_palet_agro_{day.isoformat()}.csv'
            })

        return render_template('agro_warehouse/raport_palet_daily.html', rows=rows, day=day)
    except Exception as e:
        current_app.logger.error(f'Error generating daily pallet report: {e}')
        return (f'Błąd generowania raportu: {e}', 500)
    finally:
        conn.close()
