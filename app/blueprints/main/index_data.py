"""
Wersja: 1.1.0
Opis: Agregator danych dashboardu. Ładuje dane HR, plany produkcji i kontekst dla poszczególnych hal.
"""
from app.db import get_db_connection, get_table_name
from app.services.dashboard_service import DashboardService
from app.services.dashboard_context_service import DashboardContextService
from app.services.planning.start_guard import get_unfinished_section_orders
from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
from app.services.magazyn_dostawy.delivery_command_service import DeliveryCommandService
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.magazyn_dostawy.location_service import LocationService


def build_dashboard_halls_context(dzisiaj, aktywna_sekcja, aktywna_linia, role, data_od=None, data_do=None):
    """Load shared HR data and per-hall dashboard payload using a single connection."""
    halls_to_fetch = ['PSD', 'AGRO'] if aktywna_linia == 'ALL' else [aktywna_linia]
    halls_data = {}

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
    except Exception:
        conn.close()
        raise

    try:
        from flask import current_app
        current_app.logger.info(f"build_dashboard_halls_context(sekcja={aktywna_sekcja}, linia={aktywna_linia}, fetch={halls_to_fetch})")
    except Exception: pass

    try:
        staff_data_global = DashboardService.get_basic_staff_data(dzisiaj, linia='PSD', cursor=cursor)
        wszyscy = staff_data_global['wszyscy']
        dostepni = staff_data_global['dostepni']
        hr_data = DashboardService.get_hr_and_leave_data(dzisiaj, cursor=cursor, staff_data=staff_data_global)

        for linia in halls_to_fetch:
            staff_data = staff_data_global if linia == 'PSD' else DashboardService.get_basic_staff_data(dzisiaj, linia=linia, cursor=cursor)
            wpisy = DashboardService.get_journal_entries(dzisiaj, aktywna_sekcja, linia=linia, cursor=cursor)
            zasyp_rozpoczete = DashboardService.get_zasyp_started_products(dzisiaj, linia=linia, cursor=cursor)
            quality_data = DashboardService.get_quality_and_leave_requests(role, linia=linia, cursor=cursor, pending_requests=hr_data['wnioski_pending'])
            shift_notes = DashboardService.get_shift_notes(dzisiaj, linia=linia, cursor=cursor)
            zasyp_result, workowanie_result = DashboardService.get_full_plan_results_for_sections(dzisiaj, linia=linia, cursor=cursor, data_od=data_od, data_do=data_do)
            plans_zasyp, plans_workowanie = zasyp_result[0], workowanie_result[0]
            global_active = DashboardService.any_plan_in_progress(dzisiaj, linia=linia, cursor=cursor)
            buffer_queue = DashboardService.get_buffer_queue(dzisiaj, linia=linia, cursor=cursor)
            work_first_map = DashboardService.get_first_workowanie_map(dzisiaj, linia=linia, cursor=cursor)
            zasyp_product_order = DashboardService.get_zasyp_product_order(dzisiaj, linia=linia, cursor=cursor)
            zasyp_has_active = DashboardService.get_zasyp_active_status(dzisiaj, linia=linia, cursor=cursor)
            active_products = DashboardService.get_active_products(dzisiaj, linia=linia, cursor=cursor)
            unfinished_section_orders = get_unfinished_section_orders(
                cursor, get_table_name('plan_produkcji', linia), aktywna_sekcja
            )

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
                    pending_wg = DeliveryQueries.get_pending_production_pallets(str(linia).upper())
                except Exception:
                    pending_wg = []

            if aktywna_sekcja in ('Zasyp', 'Workowanie'):
                plan_dnia, palety_mapa, suma_plan, suma_wykonanie = zasyp_result if aktywna_sekcja == 'Zasyp' else workowanie_result
            elif aktywna_sekcja != 'Magazyn':
                plan_dnia, palety_mapa, suma_plan, suma_wykonanie = DashboardService.get_production_plans(
                    dzisiaj,
                    aktywna_sekcja,
                    linia=linia,
                    cursor=cursor,
                    data_od=data_od,
                    data_do=data_do
                )

            zasyp_excel_mapa = {}
            if linia == 'AGRO' and aktywna_sekcja == 'Workowanie' and plan_dnia:
                from app.services.zasyp_excel_service import ZasypExcelService
                zasyp_excel_mapa = ZasypExcelService.for_work_orders(conn, [p[0] for p in plan_dnia])
            excel_values = [zasyp_excel_mapa.get(p[0]) for p in plan_dnia] if zasyp_excel_mapa else []
            zasyp_excel_total = sum(excel_values) if excel_values and all(v is not None for v in excel_values) else None

            bigbagi_mapa = {}
            if linia == 'AGRO' and plan_dnia:
                plan_ids = [p[0] for p in plan_dnia]
                fmt_ids = ','.join(['%s'] * len(plan_ids))
                try:
                    cursor.execute(
                        f"""SELECT plan_id, id, nr_palety, nazwa_produktu, waga_kg, nr_partii,
                                   lokalizacja_zrodlowa, autor_login, DATE_FORMAT(created_at, %s)
                            FROM agro_workowanie_bigbagi
                            WHERE plan_id IN ({fmt_ids}) AND status = 'ZUZYTY'
                            ORDER BY created_at ASC, id ASC""",
                        ['%H:%i:%s', *plan_ids]
                    )
                    for bb_row in cursor.fetchall():
                        pid = bb_row[0]
                        bigbagi_mapa.setdefault(pid, []).append({
                            'id': bb_row[1],
                            'nr_palety': bb_row[2],
                            'nazwa_produktu': bb_row[3],
                            'waga_kg': float(bb_row[4] or 0),
                            'nr_partii': bb_row[5],
                            'lokalizacja_zrodlowa': bb_row[6],
                            'autor_login': bb_row[7],
                            'godzina': bb_row[8]
                        })
                except Exception as _e_bb:
                    pass

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
                'bigbagi_mapa': bigbagi_mapa,
                'zasyp_excel_mapa': zasyp_excel_mapa,
                'zasyp_excel_total': zasyp_excel_total,
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
                'unfinished_section_orders': unfinished_section_orders,
            }

    finally:
        try:
            cursor.close()
        finally:
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


def build_production_overview_context(dzisiaj, linia, role, data_od=None, data_do=None):
    """Read exactly the data used by dashboard_global and its included templates."""
    from app.services.production_service import ProductionService
    from app.services.ipomiar_service import read_dashboard
    halls = ['PSD', 'AGRO'] if linia == 'ALL' else [linia]
    halls_data = {}
    notes = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            for hall in halls:
                zasyp, _, _, _ = ProductionService.get_production_plans(
                    dzisiaj, 'Zasyp', hall, cursor, data_od=data_od, data_do=data_do, include_details=False)
                workowanie, _, _, _ = ProductionService.get_production_plans(
                    dzisiaj, 'Workowanie', hall, cursor, data_od=data_od, data_do=data_do, include_details=False)
                halls_data[hall] = {'linia': hall, 'plans_zasyp': zasyp, 'plans_workowanie': workowanie}
                if hall == halls[0]:
                    notes = DashboardService.get_shift_notes(dzisiaj, linia=hall, cursor=cursor)
        finally:
            cursor.close()
    finally:
        conn.close()
    return {
        'halls_to_fetch': halls, 'halls_data': halls_data, 'shift_notes': notes,
        'dzisiaj': dzisiaj, 'dzisiaj_fmt': dzisiaj.strftime('%d.%m.%Y'),
        'linia': linia, 'sekcja': 'Dashboard', 'rola': role,
        'data_od': data_od, 'data_do': data_do,
        'agro_measurements': read_dashboard(dzisiaj),
    }


def build_production_section_halls_context(dzisiaj, sekcja, linia, role, data_od=None, data_do=None):
    """Load the selected production section without unrelated HR/other-section data."""
    halls = ['PSD', 'AGRO'] if linia == 'ALL' else [linia]
    halls_data = {}
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            for hall in halls:
                plans, pallets, total, completed = DashboardService.get_production_plans(
                    dzisiaj, sekcja, linia=hall, cursor=cursor, data_od=data_od, data_do=data_do)
                active = DashboardService.get_active_products(dzisiaj, linia=hall, cursor=cursor)
                data = {
                    'linia': hall, 'plan_dnia': plans, 'palety_mapa': pallets,
                    'suma_plan': total, 'suma_wykonanie': completed,
                    'wpisy': DashboardService.get_journal_entries(dzisiaj, sekcja, linia=hall, cursor=cursor),
                    'active_products': active, 'zasyp_has_active': bool(active.get('Zasyp')),
                    'unfinished_section_orders': get_unfinished_section_orders(cursor, get_table_name('plan_produkcji', hall), sekcja),
                    'work_first_map': DashboardService.get_first_workowanie_map(dzisiaj, linia=hall, cursor=cursor) if sekcja == 'Workowanie' else {},
                    'quality_data': {'quality_count': DashboardService.get_quality_and_leave_requests(role, linia=hall, cursor=cursor, pending_requests=[])['quality_count'] if role == 'planista' else 0},
                    'bigbagi_mapa': {},
                }
                if hall == 'AGRO' and plans:
                    ids = [p[0] for p in plans]
                    fmt = ','.join(['%s'] * len(ids))
                    cursor.execute(
                        f"""SELECT plan_id, id, nr_palety, nazwa_produktu, waga_kg, nr_partii,
                                   lokalizacja_zrodlowa, autor_login, DATE_FORMAT(created_at, %s)
                            FROM agro_workowanie_bigbagi
                            WHERE plan_id IN ({fmt}) AND status = 'ZUZYTY'
                            ORDER BY created_at ASC, id ASC""", ['%H:%i:%s', *ids])
                    for row in cursor.fetchall():
                        data['bigbagi_mapa'].setdefault(row[0], []).append({
                            'id': row[1], 'nr_palety': row[2], 'nazwa_produktu': row[3],
                            'waga_kg': float(row[4] or 0), 'nr_partii': row[5],
                            'lokalizacja_zrodlowa': row[6], 'autor_login': row[7], 'godzina': row[8],
                        })
                halls_data[hall] = data
        finally:
            cursor.close()
    finally:
        conn.close()
    return {
        'halls_to_fetch': halls, 'halls_data': halls_data,
        'hr_data': dict.fromkeys(('hr_dostepni', 'hr_pracownicy', 'raporty_hr', 'planned_leaves', 'recent_absences'), []),
    }
