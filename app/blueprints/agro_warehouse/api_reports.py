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

def _extract_bag_kg(value):
    """Extract bag weight (kg) from values like 'worki_zgrzewane_20'."""
    if value is None:
        return None
    match = re.search('(\\d+(?:[\\.,]\\d+)?)', str(value))
    if not match:
        return None
    raw = match.group(1).replace(',', '.')
    try:
        kg = float(raw)
    except (TypeError, ValueError):
        return None
    return kg if kg > 0 else None
def _resolve_report_bag_kg(cursor, plan_row, rozliczenia, product_typ_cache):
    """Resolve kg/worek for AGRO report using most reliable available source."""
    for row in rozliczenia or []:
        kg = row.get('kg_na_worek')
        if kg is None:
            continue
        try:
            kg_val = float(kg)
        except (TypeError, ValueError):
            continue
        if kg_val > 0:
            return kg_val
    for key in ('typ_produkcji', 'zasyp_typ_produkcji'):
        kg = _extract_bag_kg(plan_row.get(key))
        if kg:
            return kg
    produkt = (plan_row.get('produkt') or '').strip()
    if produkt:
        if produkt not in product_typ_cache:
            cursor.execute('SELECT typ_produkcji FROM produkty_receptury WHERE nazwa_produktu = %s ORDER BY id DESC LIMIT 1', (produkt,))
            product_row = cursor.fetchone()
            product_typ_cache[produkt] = (product_row or {}).get('typ_produkcji')
        kg = _extract_bag_kg(product_typ_cache.get(produkt))
        if kg:
            return kg
    produkt_lc = produkt.lower()
    if 'mleko' in produkt_lc or 'milk' in produkt_lc or '20' in produkt_lc:
        return 20.0
    return 25.0
@agro_warehouse_bp.route('/agro/report/warehouse', methods=['GET'])
@login_required
@dynamic_role_required('raporty.agro_warehouse')
def report_warehouse():
    try:
        linia = request.args.get('linia', 'Agro')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        fmt = request.args.get('format', 'csv')
        limit = min(int(request.args.get('limit', 1000)), 10000)
        rows = AgroSurowceService.get_warehouse_entries(limit=limit, linia=linia, date_from=date_from, date_to=date_to)
        if fmt == 'json':
            return jsonify({'success': True, 'rows': rows, 'count': len(rows)})
        import io, csv
        si = io.StringIO()
        w = csv.writer(si)
        w.writerow(['id', 'surowiec_id', 'nazwa', 'ilosc', 'autor_login', 'autor_data', 'potwierdzil_login', 'potwierdzil_data', 'lokalizacja', 'obecna_lokalizacja', 'komentarz', 'plan_id', 'plan_name', 'zbiornik', 'typ_ruchu', 'status', 'ilosc_po'])
        for r in rows:
            w.writerow([r.get('id'), r.get('surowiec_id'), r.get('surowiec_nazwa'), r.get('ilosc'), r.get('autor_login'), r.get('autor_data').strftime('%Y-%m-%d %H:%M') if r.get('autor_data') else '', r.get('potwierdzil_login'), r.get('potwierdzil_data').strftime('%Y-%m-%d %H:%M') if r.get('potwierdzil_data') else '', r.get('lokalizacja'), r.get('obecna_lokalizacja'), r.get('komentarz'), r.get('plan_id'), r.get('plan_name'), r.get('zbiornik'), r.get('typ_ruchu'), r.get('status'), r.get('ilosc_po')])
        output = si.getvalue()
        return current_app.response_class(output, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=warehouse_report_{linia}.csv'})
    except Exception as e:
        current_app.logger.error(f'Error in report_warehouse: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/report/production', methods=['GET'])
@login_required
@dynamic_role_required('raporty.agro_production')
def report_production():
    try:
        linia = request.args.get('linia', 'Agro')
        fmt = request.args.get('format', 'csv')
        limit = min(int(request.args.get('limit', 500)), 10000)
        rows = AgroTanksService.get_production_moves(limit=limit, linia=linia)
        if fmt == 'json':
            return jsonify({'success': True, 'rows': rows, 'count': len(rows)})
        import io, csv
        si = io.StringIO()
        w = csv.writer(si)
        w.writerow(['id', 'surowiec_id', 'nazwa', 'ilosc', 'autor_login', 'autor_data', 'lokalizacja', 'zbiornik', 'plan_id', 'plan_name', 'komentarz', 'ilosc_po'])
        for r in rows:
            w.writerow([r.get('id'), r.get('surowiec_id'), r.get('surowiec_nazwa'), r.get('ilosc'), r.get('autor_login'), r.get('autor_data').strftime('%Y-%m-%d %H:%M') if r.get('autor_data') else '', r.get('lokalizacja'), r.get('zbiornik'), r.get('plan_id'), r.get('plan_name'), r.get('komentarz'), r.get('ilosc_po')])
        output = si.getvalue()
        return current_app.response_class(output, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=production_report_{linia}.csv'})
    except Exception as e:
        current_app.logger.error(f'Error in report_production: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)

@agro_warehouse_bp.route('/agro/report/combined', methods=['GET'])
@login_required
@dynamic_role_required('raporty.agro_production')
def report_combined():
    try:
        linia = request.args.get('linia', 'Agro')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        fmt = request.args.get('format', 'csv')
        limit = min(int(request.args.get('limit', 2000)), 20000)
        rows = AgroSurowceService.get_combined_report(limit=limit, linia=linia, date_from=date_from, date_to=date_to)
        if fmt == 'json':
            return jsonify({'success': True, 'rows': rows, 'count': len(rows)})
        import io, csv
        si = io.StringIO()
        w = csv.writer(si)
        w.writerow(['id', 'typ_ruchu', 'surowiec_id', 'nazwa', 'ilosc', 'autor_login', 'autor_data', 'potwierdzil_login', 'potwierdzil_data', 'lokalizacja', 'obecna_lokalizacja', 'zbiornik', 'plan_id', 'plan_name', 'komentarz', 'status', 'ilosc_po'])
        for r in rows:
            w.writerow([r.get('id'), r.get('typ_ruchu'), r.get('surowiec_id'), r.get('surowiec_nazwa'), r.get('ilosc'), r.get('autor_login'), r.get('autor_data').strftime('%Y-%m-%d %H:%M') if r.get('autor_data') else '', r.get('potwierdzil_login'), r.get('potwierdzil_data').strftime('%Y-%m-%d %H:%M') if r.get('potwierdzil_data') else '', r.get('lokalizacja'), r.get('obecna_lokalizacja'), r.get('zbiornik'), r.get('plan_id'), r.get('plan_name'), r.get('komentarz'), r.get('status'), r.get('ilosc_po')])
        output = si.getvalue()
        return current_app.response_class(output, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=combined_report_{linia}.csv'})
    except Exception as e:
        current_app.logger.error(f'Error in report_combined: {e}')
        return (jsonify({'success': False, 'error': str(e)}), 500)
