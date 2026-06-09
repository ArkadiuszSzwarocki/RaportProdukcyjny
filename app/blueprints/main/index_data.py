"""
Wersja: 1.1.0
Opis: Agregator danych dashboardu. Ładuje dane HR, plany produkcji i kontekst dla poszczególnych hal.
"""
from app.db import get_db_connection, get_table_name
from app.services.dashboard_service import DashboardService
from app.services.dashboard_context_service import DashboardContextService
from app.services.magazyn_dostawy_service import MagazynDostawyService


def build_dashboard_halls_context(dzisiaj, aktywna_sekcja, aktywna_linia, role):
    """Load shared HR data and per-hall dashboard payload using a single connection."""
    halls_to_fetch = ['PSD', 'AGRO'] if aktywna_linia == 'ALL' else [aktywna_linia]
    halls_data = {}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        from flask import current_app
        current_app.logger.info(f"build_dashboard_halls_context(sekcja={aktywna_sekcja}, linia={aktywna_linia}, fetch={halls_to_fetch})")
    except Exception: pass

    staff_data_global = DashboardService.get_basic_staff_data(dzisiaj, linia='PSD', cursor=cursor)
    wszyscy = staff_data_global['wszyscy']
    dostepni = staff_data_global['dostepni']
    hr_data = DashboardService.get_hr_and_leave_data(dzisiaj, cursor=cursor)

    for linia in halls_to_fetch:
        staff_data = DashboardService.get_basic_staff_data(dzisiaj, linia=linia, cursor=cursor)
        wpisy = DashboardService.get_journal_entries(dzisiaj, aktywna_sekcja, linia=linia, cursor=cursor)
        zasyp_rozpoczete = DashboardService.get_zasyp_started_products(dzisiaj, linia=linia, cursor=cursor)
        quality_data = DashboardService.get_quality_and_leave_requests(role, linia=linia, cursor=cursor)
        shift_notes = DashboardService.get_shift_notes(dzisiaj, linia=linia) # TODO: support cursor in shift_notes if needed
        plans_zasyp, plans_workowanie = DashboardService.get_full_plans_for_sections(dzisiaj, linia=linia, cursor=cursor)
        global_active = DashboardService.any_plan_in_progress(dzisiaj, linia=linia, cursor=cursor)
        buffer_queue = DashboardService.get_buffer_queue(dzisiaj, linia=linia, cursor=cursor)
        work_first_map = DashboardService.get_first_workowanie_map(dzisiaj, linia=linia, cursor=cursor)
        zasyp_product_order = DashboardService.get_zasyp_product_order(dzisiaj, linia=linia, cursor=cursor)
        zasyp_has_active = DashboardService.get_zasyp_active_status(dzisiaj, linia=linia, cursor=cursor)
        active_products = DashboardService.get_active_products(dzisiaj, linia=linia, cursor=cursor)

        plan_dnia = []
        palety_mapa = {}
        magazyn_palety = []
        unconfirmed_palety = []
        pending_wg = []
        suma_plan = 0
        suma_wykonanie = 0

        if aktywna_sekcja == 'Magazyn':
            magazyn_palety, unconfirmed_palety, suma_wykonanie = DashboardService.get_warehouse_data(dzisiaj, linia=linia, cursor=cursor)
            try:
                pending_wg = MagazynDostawyService.get_pending_production_pallets(str(linia).upper())
            except Exception:
                pending_wg = []

        if aktywna_sekcja != 'Magazyn':
            plan_dnia, palety_mapa, suma_plan, suma_wykonanie = DashboardService.get_production_plans(
                dzisiaj,
                aktywna_sekcja,
                linia=linia,
                cursor=cursor
            )

        halls_data[linia] = {
            'linia': linia,
            'obsada': staff_data['obsada'],
            'wpisy': wpisy,
            'zasyp_rozpoczete': zasyp_rozpoczete,
            'quality_data': quality_data,
            'shift_notes': shift_notes,
            'plans_zasyp': plans_zasyp,
            'plans_workowanie': plans_workowanie,
            'plan_dnia': plan_dnia,
            'palety_mapa': palety_mapa,
            'suma_plan': suma_plan,
            'suma_wykonanie': suma_wykonanie,
            'magazyn_palety': magazyn_palety,
            'unconfirmed_palety': unconfirmed_palety,
            'pending_wg': pending_wg,
            'global_active': global_active,
            'buffer_queue': buffer_queue,
            'work_first_map': work_first_map,
            'next_workowanie_id': DashboardService.get_next_workowanie_id(plan_dnia),
            'zasyp_product_order': zasyp_product_order,
            'zasyp_has_active': zasyp_has_active,
            'active_products': active_products,
        }

    conn.close()

    return {
        'halls_to_fetch': halls_to_fetch,
        'halls_data': halls_data,
        'wszyscy': wszyscy,
        'dostepni': dostepni,
        'hr_data': hr_data,
    }




def build_dosypki_maps(dzisiaj, aktywna_sekcja, aktywna_linia, logger):
    return DashboardContextService.build_dosypki_maps(dzisiaj, aktywna_sekcja, aktywna_linia, logger)


def build_zasyp_etapy_context(plan_dnia, dzisiaj, aktywna_sekcja, aktywna_linia, logger):
    return DashboardContextService.build_zasyp_etapy_context(plan_dnia, dzisiaj, aktywna_sekcja, aktywna_linia, logger)


def build_agro_mix_context(dzisiaj, aktywna_linia, logger):
    return DashboardContextService.build_agro_mix_context(dzisiaj, aktywna_linia, logger)