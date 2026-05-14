from flask import Blueprint, render_template, request, current_app, session, jsonify
from app.blueprints.routes_planista_bulk import register_planista_bulk_routes
from app.blueprints.routes_planista_buffer import register_planista_buffer_routes
from app.blueprints.routes_planista_panel_data import (
    build_agro_plan_metrics,
    build_bufor_banner_context,
    build_panel_summary_context,
    build_primary_plan_metrics,
    enrich_agro_plan_carryover,
    enrich_primary_plan_carryover,
    load_agro_plan_rows,
    load_primary_plan_rows,
)
from app.blueprints.routes_planista_processing import calculate_kg_per_hour
from app.db import get_db_connection, get_table_name
from app.blueprints.routes_planista_rollover import register_planista_rollover_routes
from app.dto.paleta import PaletaDTO
from app.services.notification_service import notify_workers_about_plan_change
from app.services.planning_service import PlanningService
from datetime import date, datetime, timedelta
from app.decorators import roles_required, dynamic_role_required

planista_bp = Blueprint('planista', __name__)
register_planista_bulk_routes(planista_bp)
register_planista_buffer_routes(planista_bp)
register_planista_rollover_routes(planista_bp)

@planista_bp.route('/planista', methods=['GET', 'POST'])
@dynamic_role_required('planista')
def panel_planisty():
    wybrana_data = request.args.get('data', str(date.today()))
    wybrana_linia = request.args.get('linia', 'PSD').upper()
    aktywna_zakladka = request.args.get('tab', '').lower()
    if not aktywna_zakladka:
        aktywna_zakladka = 'agro' if wybrana_linia == 'AGRO' else 'psd'

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        if aktywna_zakladka not in ('psd', 'agro'):
            aktywna_zakladka = 'psd'

        table_plan = get_table_name('plan_produkcji', wybrana_linia)
        plany_list = load_primary_plan_rows(cursor, wybrana_data, wybrana_linia)
        plany_list = enrich_primary_plan_carryover(cursor, plany_list, wybrana_data, wybrana_linia)

        primary_plan_metrics = build_primary_plan_metrics(
            cursor,
            plany_list,
            wybrana_data,
            wybrana_linia,
            calculate_kg_per_hour,
        )
        plany_list = primary_plan_metrics['plany_list']
        palety_mapa = primary_plan_metrics['palety_mapa']
        suma_plan = primary_plan_metrics['suma_plan']
        suma_wyk = primary_plan_metrics['suma_wyk']
        suma_minut_plan = primary_plan_metrics['suma_minut_plan']

        # 4. Process Agro details (always needed for the side indicators or if requested)
        plany_agro = load_agro_plan_rows(cursor, wybrana_data)

        plany_agro = enrich_agro_plan_carryover(cursor, plany_agro, wybrana_data)

        agro_plan_metrics = build_agro_plan_metrics(
            cursor,
            plany_agro,
            wybrana_data,
            calculate_kg_per_hour,
            palety_mapa,
        )
        plany_agro = agro_plan_metrics['plany_agro']
        palety_mapa = agro_plan_metrics['palety_mapa']
        suma_plan_agro = agro_plan_metrics['suma_plan_agro']
        suma_wyk_agro = agro_plan_metrics['suma_wyk_agro']
        suma_minut_plan_agro = agro_plan_metrics['suma_minut_plan_agro']
        suma_uszkodzone_agro = agro_plan_metrics.get('suma_uszkodzone_agro', 0)

        summary_context = build_panel_summary_context(
            cursor,
            wybrana_data,
            aktywna_zakladka,
            wybrana_linia,
            table_plan,
            plany_list,
            plany_agro,
            suma_plan,
            suma_wyk,
            suma_minut_plan,
            suma_plan_agro,
            suma_wyk_agro,
        )
        rozliczenia = summary_context['rozliczenia']
        procent = summary_context['procent']
        procent_agro = summary_context['procent_agro']
        procent_czasu = summary_context['procent_czasu']
        quality_orders = summary_context['quality_orders']
        quality_count = summary_context['quality_count']
        has_incomplete_plans = summary_context['has_incomplete_plans']
        has_incomplete_psd = summary_context['has_incomplete_psd']
        has_incomplete_agro = summary_context['has_incomplete_agro']
        
        bufor_context = build_bufor_banner_context(cursor, wybrana_data, wybrana_linia)
        bufor_remaining = bufor_context['bufor_remaining']
        bufor_source_date = bufor_context['bufor_source_date']
        bufor_source_date_fmt = bufor_context['bufor_source_date_fmt']

        rola = session.get('rola')
        return render_template('planista.html',
                               plany=plany_list, wybrana_data=wybrana_data, wybrana_linia=wybrana_linia,
                               palety_mapa=palety_mapa, suma_plan=suma_plan, suma_wyk=suma_wyk,
                               procent=procent, suma_minut_plan=suma_minut_plan, procent_czasu=procent_czasu,
                               quality_count=quality_count, quality_orders=quality_orders,
                               rozliczenia=rozliczenia, current_role=rola, aktywna_zakladka=aktywna_zakladka,
                               plany_agro=plany_agro, suma_plan_agro=suma_plan_agro, suma_wyk_agro=suma_wyk_agro,
                               suma_minut_plan_agro=suma_minut_plan_agro, procent_agro=procent_agro,
                               suma_uszkodzone_agro=suma_uszkodzone_agro,
                               has_incomplete_plans=has_incomplete_plans,
                               has_incomplete_psd=has_incomplete_psd, has_incomplete_agro=has_incomplete_agro,
                               bufor_remaining=bufor_remaining,
                               bufor_source_date=bufor_source_date, bufor_source_date_fmt=bufor_source_date_fmt)
    except Exception as e:
        import traceback
        error_msg = f"Error loading panel_planisty: {str(e)}\n{traceback.format_exc()}"
        current_app.logger.error(error_msg)
        return f"<pre>{error_msg}</pre>", 500
    finally:
        try: conn.close()
        except: pass
