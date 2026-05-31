"""Warehouse management routes.
Handles warehouse stock views, pallet confirmations, and inventory reports.
"""
from datetime import date

from flask import Blueprint, request, session, url_for

from .buffer import register_warehouse_buffer_routes
from .management import register_warehouse_management_routes
from .summary import register_warehouse_summary_routes
from app.db import get_db_connection, get_table_name


warehouse_bp = Blueprint('warehouse', __name__)
register_warehouse_summary_routes(warehouse_bp)
register_warehouse_buffer_routes(warehouse_bp)


def _get_request_linia(default='PSD'):
    return request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or default


def _get_payload_linia(data, default='PSD'):
    return (data or {}).get('linia') or request.args.get('linia') or session.get('selected_hall_view') or default


def _update_paleta_workowanie(cursor, paleta_id, waga, linia='PSD'):
    """Helper: update palety_workowanie weight or confirmed weight."""
    table_pal = get_table_name('palety_workowanie', linia)
    table_plan = get_table_name('plan_produkcji', linia)
    cursor.execute(f"SELECT COALESCE(status,''), plan_id FROM {table_pal} WHERE id=%s", (paleta_id,))
    row = cursor.fetchone()
    if not row:
        return {'found': False}

    status = row[0] if row[0] else ''
    plan_id = row[1]

    if status == 'przyjeta':
        cursor.execute(f"UPDATE {table_pal} SET waga_potwierdzona=%s WHERE id=%s", (waga, paleta_id))
        action = 'waga_potwierdzona'
    else:
        cursor.execute(f"UPDATE {table_pal} SET waga=%s WHERE id=%s", (waga, paleta_id))
        cursor.execute(
            f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s",
            (plan_id, plan_id),
        )
        action = 'waga'

    return {'found': True, 'action': action, 'plan_id': plan_id, 'status': status}


def _update_paleta_magazyn(cursor, paleta_id, nowa_waga, linia='PSD'):
    """Helper: update magazyn_palety weight and refresh plan aggregate."""
    table_mag = get_table_name('magazyn_palety', linia)
    table_plan = get_table_name('plan_produkcji', linia)

    cursor.execute(f"SELECT plan_id FROM {table_mag} WHERE id=%s", (paleta_id,))
    row = cursor.fetchone()
    if not row:
        return {'found': False}

    plan_id = row[0]
    cursor.execute(f"UPDATE {table_mag} SET waga_netto=%s WHERE id=%s", (nowa_waga, paleta_id))
    cursor.execute(
        f"""
            UPDATE {table_plan} pp
            SET tonaz_rzeczywisty = (
                SELECT COALESCE(SUM(mp.waga_netto), 0)
                FROM {table_mag} mp
                WHERE mp.plan_id = pp.id
            )
            WHERE pp.id = %s
        """,
        (plan_id,),
    )
    return {'found': True, 'plan_id': plan_id}


def bezpieczny_powrot():
    """Default return path: planner view or dashboard."""
    data_val = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data')
    sekcja = request.args.get('sekcja') or request.form.get('sekcja')
    
    if request.referrer:
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(request.referrer)
            qs = parse_qs(parsed.query)
            if not data_val:
                if 'data' in qs: data_val = qs['data'][0]
                elif 'dzisiaj' in qs: data_val = qs['dzisiaj'][0]
            if not sekcja and 'sekcja' in qs:
                sekcja = qs['sekcja'][0]
        except Exception:
            pass

    data_val = data_val or str(date.today())
    sekcja = sekcja or 'Zasyp'

    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        return url_for('planista.panel_planisty', data=data_val)
        
    linia = _get_request_linia()
    if request.form.get('widok_powrotu') == 'agro' or linia == 'AGRO' and request.args.get('source') == 'agro':
        return url_for('production.agro_workowanie_rozliczenie_page', data=data_val)

    return url_for('main.index', sekcja=sekcja, data=data_val, linia=linia)


register_warehouse_management_routes(
    warehouse_bp,
    resolve_request_linia=_get_request_linia,
    resolve_payload_linia=_get_payload_linia,
    update_paleta_workowanie=_update_paleta_workowanie,
    update_paleta_magazyn=_update_paleta_magazyn,
    safe_return=bezpieczny_powrot,
)
