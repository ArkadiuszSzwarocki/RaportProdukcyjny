from datetime import datetime

from app.db import get_db_connection, get_table_name
from app.services.dashboard_service import DashboardService


def build_dashboard_halls_context(dzisiaj, aktywna_sekcja, aktywna_linia, role):
    """Load shared HR data and per-hall dashboard payload for the main index view."""
    halls_to_fetch = ['PSD', 'AGRO'] if aktywna_linia == 'ALL' else [aktywna_linia]
    halls_data = {}

    staff_data_global = DashboardService.get_basic_staff_data(dzisiaj, linia='PSD')
    wszyscy = staff_data_global['wszyscy']
    zajeci_ids = staff_data_global['zajeci_ids']
    dostepni = staff_data_global['dostepni']
    hr_data = DashboardService.get_hr_and_leave_data(dzisiaj, wszyscy, zajeci_ids)

    for linia in halls_to_fetch:
        staff_data = DashboardService.get_basic_staff_data(dzisiaj, linia=linia)
        wpisy = DashboardService.get_journal_entries(dzisiaj, aktywna_sekcja, linia=linia)
        zasyp_rozpoczete = DashboardService.get_zasyp_started_products(dzisiaj, linia=linia)
        quality_data = DashboardService.get_quality_and_leave_requests(role, linia=linia)
        shift_notes = DashboardService.get_shift_notes(dzisiaj, linia=linia)
        plans_zasyp, plans_workowanie = DashboardService.get_full_plans_for_sections(dzisiaj, linia=linia)
        global_active = DashboardService.any_plan_in_progress(dzisiaj, linia=linia)
        buffer_queue = DashboardService.get_buffer_queue(dzisiaj, linia=linia)
        work_first_map = DashboardService.get_first_workowanie_map(dzisiaj, linia=linia)
        zasyp_product_order = DashboardService.get_zasyp_product_order(dzisiaj, linia=linia)
        zasyp_has_active = DashboardService.get_zasyp_active_status(dzisiaj, linia=linia)
        active_products = DashboardService.get_active_products(dzisiaj, linia=linia)

        plan_dnia = []
        palety_mapa = {}
        magazyn_palety = []
        unconfirmed_palety = []
        suma_plan = 0
        suma_wykonanie = 0

        if aktywna_sekcja == 'Magazyn':
            magazyn_palety, unconfirmed_palety, suma_wykonanie = DashboardService.get_warehouse_data(dzisiaj, linia=linia)

        if aktywna_sekcja != 'Magazyn':
            plan_dnia, palety_mapa, suma_plan, suma_wykonanie = DashboardService.get_production_plans(
                dzisiaj,
                aktywna_sekcja,
                linia=linia,
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
            'global_active': global_active,
            'buffer_queue': buffer_queue,
            'work_first_map': work_first_map,
            'next_workowanie_id': DashboardService.get_next_workowanie_id(plan_dnia),
            'zasyp_product_order': zasyp_product_order,
            'zasyp_has_active': zasyp_has_active,
            'active_products': active_products,
        }

    return {
        'halls_to_fetch': halls_to_fetch,
        'halls_data': halls_data,
        'wszyscy': wszyscy,
        'dostepni': dostepni,
        'hr_data': hr_data,
    }


def build_allowed_work_start_ids(dzisiaj, aktywna_linia, work_first_map, logger):
    """Resolve Workowanie plans that may expose START based on current buffer queue."""
    allowed_work_start_ids = set()
    try:
        table_bufor = get_table_name('bufor', aktywna_linia)
        table_plan = get_table_name('plan_produkcji', aktywna_linia)
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT MIN(b.kolejka) as global_min_queue
            FROM {table_bufor} b
            WHERE DATE(b.data_planu) = %s AND b.status = 'aktywny'
              AND EXISTS (
                  SELECT 1 FROM {table_plan} w
                  WHERE w.sekcja = 'Workowanie' AND w.status IN ('zaplanowane', 'w toku')
                    AND w.produkt = b.produkt
              )
            """,
            (dzisiaj,),
        )
        result = cursor.fetchone()
        global_min_queue = result[0] if result and result[0] is not None else None
        logger.info('[DEBUG-START] GLOBAL MIN kolejka w %s: %s', table_bufor, global_min_queue)

        if global_min_queue is not None:
            cursor.execute(
                f"""
                SELECT DISTINCT produkt
                FROM {table_bufor}
                WHERE DATE(data_planu) = %s AND status = 'aktywny' AND kolejka = %s
                """,
                (dzisiaj, global_min_queue),
            )
            products_with_min_queue = [row[0] for row in cursor.fetchall()]
            logger.info('[DEBUG-START] Produkty z kolejka=%s: %s', global_min_queue, products_with_min_queue)

            for produkt in products_with_min_queue:
                matched_key = next((key for key in work_first_map if key.strip().casefold() == produkt.strip().casefold()), None)
                if matched_key:
                    allowed_work_start_ids.add(work_first_map[matched_key])
                    logger.info(
                        '[DEBUG-START] Aktywny START dla %s (id=%s, kolejka=%s)',
                        produkt,
                        work_first_map[matched_key],
                        global_min_queue,
                    )
                    continue

                try:
                    cursor.execute(
                        f"""
                        SELECT id FROM {table_plan}
                        WHERE sekcja = 'Workowanie'
                          AND status IN ('zaplanowane', 'w toku')
                          AND LOWER(TRIM(produkt)) = LOWER(TRIM(%s))
                          AND is_deleted = 0
                        ORDER BY CASE status WHEN 'w toku' THEN 1 ELSE 2 END, data_planu DESC, kolejnosc ASC, id ASC
                        LIMIT 1
                        """,
                        (produkt,),
                    )
                    row = cursor.fetchone()
                    if row:
                        allowed_work_start_ids.add(row[0])
                        logger.info(
                            '[DEBUG-START] Aktywny START (fallback carry-over) dla %s (id=%s, kolejka=%s)',
                            produkt,
                            row[0],
                            global_min_queue,
                        )
                    else:
                        logger.warning(
                            "[DEBUG-START] Brak Workowania dla produktu: '%s' (work_first_map keys: %s)",
                            produkt,
                            list(work_first_map.keys()),
                        )
                except Exception as fallback_error:
                    logger.error("[DEBUG-START] Błąd fallback dla '%s': %s", produkt, fallback_error)

        cursor.close()
        conn.close()
        logger.info('[DEBUG-START] Final allowed_work_start_ids: %s', allowed_work_start_ids)
    except Exception as error:
        import traceback

        logger.error('[ERROR-START] Błąd: %s', error)
        logger.error(traceback.format_exc())
        allowed_work_start_ids = set()

    return allowed_work_start_ids


def build_dosypki_maps(dzisiaj, aktywna_sekcja, aktywna_linia, logger):
    """Load confirmed and pending dosypki maps for the active Zasyp view."""
    dosypki_mapa = {}
    dosypki_oczekujace_mapa = {}
    if aktywna_sekcja != 'Zasyp':
        return dosypki_mapa, dosypki_oczekujace_mapa

    try:
        table_dosypki = get_table_name('dosypki', aktywna_linia)
        table_plan = get_table_name('plan_produkcji', aktywna_linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT d.plan_id, d.nazwa, d.kg, d.data_zlecenia, d.data_potwierdzenia, d.szarza_id
            FROM {table_dosypki} d
            JOIN {table_plan} p ON d.plan_id = p.id
            WHERE d.potwierdzone = 1 AND COALESCE(d.anulowana, 0) = 0 AND DATE(p.data_planu) = %s AND p.sekcja = 'Zasyp'
            ORDER BY d.data_potwierdzenia ASC
            """,
            (dzisiaj,),
        )
        for row in cursor.fetchall():
            plan_id = row[0]
            dosypki_mapa.setdefault(plan_id, []).append(
                {
                    'nazwa': row[1],
                    'kg': row[2],
                    'zlecono': str(row[3])[:16] if row[3] else '',
                    'potwierdzono': str(row[4])[:16] if row[4] else '',
                    'szarza_id': row[5],
                }
            )

        cursor.execute(
            f"""
            SELECT d.plan_id, COUNT(*)
            FROM {table_dosypki} d
            JOIN {table_plan} p ON d.plan_id = p.id
            WHERE d.potwierdzone = 0 AND COALESCE(d.anulowana, 0) = 0 AND DATE(p.data_planu) = %s AND p.sekcja = 'Zasyp'
            GROUP BY d.plan_id
            """,
            (dzisiaj,),
        )
        for plan_id, pending_count in cursor.fetchall():
            dosypki_oczekujace_mapa[plan_id] = pending_count

        cursor.close()
        conn.close()
    except Exception as error:
        logger.error('[ERROR-DOSYPKI] Błąd pobierania potwierdzonych dosypek: %s', error)

    return dosypki_mapa, dosypki_oczekujace_mapa


def build_zasyp_etapy_context(plan_dnia, dzisiaj, aktywna_sekcja, aktywna_linia, logger):
    """Load Zasyp etap sessions, parameters and kg/h metrics for the active dashboard view."""
    etapy_mapa = {}
    etapy_parametry = {}
    etapy_total = {}
    etapy_total_s = {}
    etapy_curr_szarza = {}
    etapy_sesje_mapa = {}
    kgph_stats_mapa = {}

    if aktywna_sekcja != 'Zasyp':
        return {
            'etapy_mapa': etapy_mapa,
            'etapy_parametry': etapy_parametry,
            'etapy_total': etapy_total,
            'etapy_curr_szarza': etapy_curr_szarza,
            'etapy_sesje_mapa': etapy_sesje_mapa,
            'kgph_stats_mapa': kgph_stats_mapa,
        }

    try:
        from app.services.zasyp_etapy_service import ZasypEtapyService

        for plan in plan_dnia:
            if plan[3] == 'w toku':
                plan_id = plan[0]
                sessions = ZasypEtapyService.get_etapy_sessions(plan_id=plan_id, linia=aktywna_linia)
                latest = sessions[0] if sessions else ZasypEtapyService.get_etapy(plan_id=plan_id, linia=aktywna_linia)
                etapy_sesje_mapa[plan_id] = sessions
                etapy_mapa[plan_id] = latest.get('etapy') or []
                etapy_total[plan_id] = latest.get('total_duration_str') or ''
                etapy_total_s[plan_id] = int(latest.get('total_duration_s') or 0)
                etapy_curr_szarza[plan_id] = latest.get('curr_szarza_nr') or 1
                etapy_parametry[plan_id] = ZasypEtapyService.get_parametry(plan_id=plan_id, linia=aktywna_linia)
    except Exception as error:
        logger.warning('Etapy Zasyp load failed: %s', error)

    try:
        table_plan = get_table_name('plan_produkcji', aktywna_linia)
        plan_ids = [int(plan[0]) for plan in plan_dnia if plan and len(plan) > 0]
        plan_realized_kg = {}
        plan_status = {}
        for plan in plan_dnia:
            try:
                plan_realized_kg[int(plan[0])] = float(plan[7] or 0.0)
                plan_status[int(plan[0])] = str(plan[3] or '').strip().lower()
            except Exception:
                continue

        if plan_ids:
            conn_stats = get_db_connection()
            cursor_stats = conn_stats.cursor(dictionary=True)
            fmt_ids = ','.join(['%s'] * len(plan_ids))
            cursor_stats.execute(
                f'SELECT id, COALESCE(tonaz_rzeczywisty, 0) AS tonaz_rzeczywisty, real_start, real_stop FROM {table_plan} WHERE id IN ({fmt_ids})',
                plan_ids,
            )
            plan_meta = {int(row['id']): row for row in (cursor_stats.fetchall() or [])}

            cursor_stats.execute(
                f"""
                SELECT
                    plan_id,
                    MIN(czas_start) AS first_start,
                    MAX(COALESCE(czas_stop, NOW())) AS last_end,
                    MAX(CASE WHEN czas_stop IS NULL THEN 1 ELSE 0 END) AS has_running
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id IN ({fmt_ids}) AND czas_start IS NOT NULL
                GROUP BY plan_id
                """,
                [aktywna_linia] + plan_ids,
            )
            etapy_agg_map = {int(row['plan_id']): row for row in (cursor_stats.fetchall() or [])}

            now_dt = datetime.now()
            for plan_id in plan_ids:
                meta = plan_meta.get(plan_id) or {}
                tonaz_plan = float(meta.get('tonaz_rzeczywisty') or 0.0)
                tonaz_realized = float(plan_realized_kg.get(plan_id) or 0.0)
                parametry = etapy_parametry.get(plan_id) or {}
                status = plan_status.get(plan_id, '')
                agg = etapy_agg_map.get(plan_id) or {}

                tonaz = tonaz_realized if tonaz_realized > 0 else tonaz_plan
                batch_tonaz = float(parametry.get('wielkosc_szarzy_kg') or 0.0)
                real_start = meta.get('real_start')
                real_stop = meta.get('real_stop')
                real_seconds = 0
                real_work_kgph = None
                if tonaz > 0:
                    metric_start = real_start or agg.get('first_start')
                    metric_end = now_dt if status == 'w toku' else agg.get('last_end') or real_stop or now_dt
                    if metric_start:
                        try:
                            real_seconds = max(0, int((metric_end - metric_start).total_seconds()))
                            real_hours = real_seconds / 3600.0
                            if real_hours > 0:
                                real_work_kgph = tonaz / real_hours
                        except Exception:
                            real_work_kgph = None
                            real_seconds = 0

                timeline_kgph = None
                sessions_for_plan = etapy_sesje_mapa.get(plan_id) or []

                def _session_etapy_breakdown(session_payload):
                    etapy_out = []
                    for etap in (session_payload.get('etapy') or []):
                        try:
                            duration_seconds = int(etap.get('duration_s') or 0)
                        except Exception:
                            duration_seconds = 0
                        if duration_seconds <= 0:
                            continue
                        try:
                            etap_nr = int(etap.get('etap'))
                        except Exception:
                            etap_nr = etap.get('etap')
                        etapy_out.append(
                            {
                                'etap': etap_nr,
                                'duration_s': duration_seconds,
                                'duration_str': etap.get('duration_str') or '',
                            }
                        )
                    return etapy_out

                closed_sessions = [
                    session_payload
                    for session_payload in sessions_for_plan
                    if int(session_payload.get('total_duration_s') or 0) > 0 and not bool(session_payload.get('has_running'))
                ]

                if closed_sessions:
                    timeline_seconds = sum(int(session_payload.get('total_duration_s') or 0) for session_payload in closed_sessions)
                    timeline_mass = (batch_tonaz * len(closed_sessions)) if batch_tonaz > 0 else tonaz
                    timeline_sources = []
                    for session_payload in closed_sessions:
                        timeline_sources.append(
                            {
                                'szarza_nr': int(session_payload.get('szarza_nr') or session_payload.get('curr_szarza_nr') or 0),
                                'total_duration_s': int(session_payload.get('total_duration_s') or 0),
                                'total_duration_str': session_payload.get('total_duration_str') or '',
                                'etapy': _session_etapy_breakdown(session_payload),
                            }
                        )
                else:
                    timeline_seconds = int(etapy_total_s.get(plan_id) or 0)
                    timeline_mass = batch_tonaz if batch_tonaz > 0 else tonaz
                    current_session = sessions_for_plan[0] if sessions_for_plan else None
                    if current_session:
                        timeline_sources = [
                            {
                                'szarza_nr': int(current_session.get('szarza_nr') or current_session.get('curr_szarza_nr') or 0),
                                'total_duration_s': int(current_session.get('total_duration_s') or 0),
                                'total_duration_str': current_session.get('total_duration_str') or '',
                                'etapy': _session_etapy_breakdown(current_session),
                            }
                        ]
                    else:
                        timeline_sources = []

                if timeline_mass > 0 and timeline_seconds > 0:
                    try:
                        timeline_hours = timeline_seconds / 3600.0
                        if timeline_hours > 0:
                            timeline_kgph = timeline_mass / timeline_hours
                    except Exception:
                        timeline_kgph = None

                kgph_stats_mapa[plan_id] = {
                    'real_work': real_work_kgph,
                    'timeline': timeline_kgph,
                    'real_mass_kg': tonaz,
                    'real_seconds': real_seconds,
                    'timeline_mass_kg': timeline_mass,
                    'timeline_batch_mass_kg': batch_tonaz if batch_tonaz > 0 else None,
                    'timeline_seconds': timeline_seconds,
                    'timeline_closed_sessions': len(closed_sessions),
                    'timeline_mode': 'closed_sessions' if closed_sessions else 'current_session',
                    'timeline_sources': timeline_sources,
                }

            cursor_stats.close()
            conn_stats.close()
    except Exception as error:
        logger.warning('kgph stats load failed: %s', error)

    return {
        'etapy_mapa': etapy_mapa,
        'etapy_parametry': etapy_parametry,
        'etapy_total': etapy_total,
        'etapy_curr_szarza': etapy_curr_szarza,
        'etapy_sesje_mapa': etapy_sesje_mapa,
        'kgph_stats_mapa': kgph_stats_mapa,
    }


def build_agro_mix_context(dzisiaj, aktywna_linia, logger):
    """Load AGRO MIX consumption and available-mix context for AGRO dashboard views."""
    agro_mix_mapa = {}
    agro_mix_dostepne = []
    if aktywna_linia not in ['AGRO', 'ALL']:
        return agro_mix_mapa, agro_mix_dostepne

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, nastepne_zlecenie_id, zuzyte_w_id, kategoria, waga_kg, created_at, autor_login, status
            FROM agro_mix_rozliczenie
            WHERE (data_planu = %s OR status='DOSTEPNY')
            """,
            (dzisiaj,),
        )
        mixes = cursor.fetchall()
        for mix in mixes:
            next_plan_id = mix['zuzyte_w_id'] or mix['nastepne_zlecenie_id']
            if next_plan_id:
                agro_mix_mapa.setdefault(next_plan_id, []).append(mix)
            if mix['status'] == 'DOSTEPNY':
                agro_mix_dostepne.append(mix)
        conn.close()
    except Exception as error:
        logger.warning('AGRO MIX load failed: %s', error)

    return agro_mix_mapa, agro_mix_dostepne