import logging
from datetime import date, datetime
from typing import Dict, List, Tuple, Any, Optional, Set
from app.db import get_db_connection, get_table_name
from app.services.dashboard_service import DashboardService

_logger = logging.getLogger(__name__)

class DashboardContextService:
    """Service for building complex dashboard data contexts."""

    @staticmethod
    def build_allowed_work_start_ids(dzisiaj: date, aktywna_linia: str, work_first_map: Dict[str, int], logger=None) -> Set[int]:
        """Resolve Workowanie plans that may expose START based on current buffer queue."""
        log = logger or _logger
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
                      WHERE w.sekcja IN ('Workowanie', 'Czyszczenie') AND w.status IN ('zaplanowane', 'w toku')
                        AND w.produkt = b.produkt
                  )
                """,
                (dzisiaj,),
            )
            result = cursor.fetchone()
            global_min_queue = result[0] if result and result[0] is not None else None
            log.info('[DEBUG-START] GLOBAL MIN kolejka w %s: %s', table_bufor, global_min_queue)

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
                log.info('[DEBUG-START] Produkty z kolejka=%s: %s', global_min_queue, products_with_min_queue)

                for produkt in products_with_min_queue:
                    matched_key = next((key for key in work_first_map if key.strip().casefold() == produkt.strip().casefold()), None)
                    if matched_key:
                        allowed_work_start_ids.add(work_first_map[matched_key])
                        continue

                    try:
                        cursor.execute(
                            f"""
                            SELECT id FROM {table_plan}
                            WHERE sekcja IN ('Workowanie', 'Czyszczenie')
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
                    except Exception as fallback_error:
                        log.error("[DEBUG-START] Błąd fallback dla '%s': %s", produkt, fallback_error)

            cursor.close()
            conn.close()
        except Exception as error:
            log.error('[ERROR-START] Błąd: %s', error)
            allowed_work_start_ids = set()

        return allowed_work_start_ids

    @staticmethod
    def build_dosypki_maps(dzisiaj: date, aktywna_sekcja: str, aktywna_linia: str, logger=None) -> Tuple[Dict, Dict]:
        """Load confirmed and pending dosypki maps for the active Zasyp view."""
        log = logger or _logger
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
            log.error('[ERROR-DOSYPKI] Błąd pobierania potwierdzonych dosypek: %s', error)

        return dosypki_mapa, dosypki_oczekujace_mapa

    @staticmethod
    def build_zasyp_etapy_context(plan_dnia: List, dzisiaj: date, aktywna_sekcja: str, aktywna_linia: str, logger=None) -> Dict[str, Any]:
        """Load Zasyp etap sessions, parameters and kg/h metrics."""
        log = logger or _logger
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
                if plan[3] in ['w toku', 'zakonczone', 'zamkniete']:
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
            log.warning('Etapy Zasyp load failed: %s', error)

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

                # Pobieramy zarejestrowane przestoje dla sekcji Zasyp w dniu dzisiejszym
                awarie_zasyp_min = 0
                try:
                    from app.repositories.downtime_repository import DowntimeRepository
                    downtimes_all = DowntimeRepository().get_downtimes(aktywna_linia, str(dzisiaj), str(dzisiaj))
                    for dt in downtimes_all:
                        if (dt.get('sekcja') or '').strip().lower() == 'zasyp':
                            dur = dt.get('czas_trwania_min')
                            if dur is not None:
                                try:
                                    awarie_zasyp_min += int(dur)
                                except: pass
                except Exception:
                    pass

                from app.services.shift_time_service import ShiftTimeService
                brutto_min, start_str, end_str = ShiftTimeService.get_shift_time_range(str(dzisiaj))
                czas_netto_min = max(1, brutto_min - awarie_zasyp_min)

                for plan_id in plan_ids:
                    meta = plan_meta.get(plan_id) or {}
                    tonaz_plan = float(meta.get('tonaz_rzeczywisty') or 0.0)
                    tonaz_realized = float(plan_realized_kg.get(plan_id) or 0.0)
                    parametry = etapy_parametry.get(plan_id) or {}

                    tonaz = tonaz_realized if tonaz_realized > 0 else tonaz_plan
                    batch_tonaz = float(parametry.get('wielkosc_szarzy_kg') or 0.0)

                    # Dynamiczne wyliczenie od startu do zamknięcia/teraz
                    prod_metrics = ShiftTimeService.calculate_productivity(
                        mass_kg=tonaz,
                        awarie_min=awarie_zasyp_min,
                        date_str=str(dzisiaj)
                    )
                    wydajnosc_efektywna = prod_metrics['wydajnosc_efektywna'] if tonaz > 0 else None
                    wydajnosc_rzeczywista = prod_metrics['wydajnosc_rzeczywista'] if tonaz > 0 else None

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

                    kgph_stats_mapa[plan_id] = {
                        'real_work': wydajnosc_rzeczywista,
                        'timeline': wydajnosc_efektywna,
                        'real_mass_kg': tonaz,
                        'real_seconds': brutto_min * 60,
                        'timeline_mass_kg': tonaz,
                        'timeline_batch_mass_kg': batch_tonaz if batch_tonaz > 0 else None,
                        'timeline_seconds': czas_netto_min * 60,
                        'timeline_closed_sessions': len(closed_sessions),
                        'timeline_mode': f"Wydajność efektywna ({start_str}–{end_str}, netto: {czas_netto_min} min [{brutto_min} min - {awarie_zasyp_min} min awarie])",
                        'timeline_sources': timeline_sources,
                    }

                cursor_stats.close()
                conn_stats.close()
        except Exception as error:
            log.warning('kgph stats load failed: %s', error)

        return {
            'etapy_mapa': etapy_mapa,
            'etapy_parametry': etapy_parametry,
            'etapy_total': etapy_total,
            'etapy_curr_szarza': etapy_curr_szarza,
            'etapy_sesje_mapa': etapy_sesje_mapa,
            'kgph_stats_mapa': kgph_stats_mapa,
        }

    @staticmethod
    def build_agro_mix_context(dzisiaj: date, aktywna_linia: str, logger=None) -> Tuple[Dict, List]:
        """Load AGRO MIX consumption and available-mix context."""
        log = logger or _logger
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
            log.warning('AGRO MIX load failed: %s', error)

        return agro_mix_mapa, agro_mix_dostepne
