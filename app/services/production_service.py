"""
Wersja: 1.1.0
Opis: Serwis planowania i realizacji produkcji. Zarządza zleceniami i wagami.
"""
import logging
from datetime import date, datetime
from typing import Dict, List, Tuple, Any, Optional
from app.db import get_db_connection, get_table_name, refresh_bufor_queue
from app.utils.queries import QueryHelper
from app.services.warehouse_service import WarehouseService
from app.services.zasyp_etapy_support import _format_date

_logger = logging.getLogger(__name__)

class ProductionService:
    @staticmethod
    def get_production_plans(dzisiaj: date, sekcja: str, linia='PSD', cursor=None, data_od=None, data_do=None, include_details=True) -> Tuple[List, Dict, int, int]:
        """Get production plans for section with formatting and palety mapping."""
        conn = None
        if cursor is None:
            conn = get_db_connection()

        try:
            if cursor is None:
                cursor = conn.cursor()

            # Read views use weights maintained by production/pallet mutations.
            # Full queue synchronization here used to block every AGRO page load.

            plan_dnia = QueryHelper.get_plan_produkcji(
                dzisiaj, 
                sekcja if sekcja != 'Dashboard' else 'Workowanie',
                linia=linia,
                cursor=cursor,
                data_od=data_od,
                data_do=data_do
            )
        
            _logger.info(f"get_production_plans(linia={linia}, sekcja={sekcja}) -> Found {len(plan_dnia)} plans from DB")
        
            if sekcja in ('Workowanie', 'Czyszczenie') and not plan_dnia:
                plan_dnia = ProductionService._get_workowanie_fallback(dzisiaj, linia=linia, cursor=cursor)
        
            # Format times
            for p in plan_dnia:
                try:
                    p[4] = p[4].strftime('%H:%M') if p[4] else ''
                except Exception:
                    p[4] = str(p[4]) if p[4] else ''
                try:
                    p[5] = p[5].strftime('%H:%M') if p[5] else ''
                except Exception:
                    p[5] = str(p[5]) if p[5] else ''

            # Transfer map logic
            przeniesione_map = ProductionService._get_transfer_map(plan_dnia, linia, cursor)

            # Fallback recipe lookup from produkty_receptury table if missing in plan
            product_names_needing_recipe = {p[1] for p in plan_dnia if (len(p) <= 17 or not p[17]) and len(p) > 1 and p[1]}
            recipe_lookup = {}
            if include_details and product_names_needing_recipe:
                try:
                    placeholders = ', '.join(['%s'] * len(product_names_needing_recipe))
                    cursor.execute(
                        f"SELECT nazwa_produktu, nr_receptury FROM produkty_receptury WHERE nazwa_produktu IN ({placeholders}) AND nr_receptury IS NOT NULL AND nr_receptury != ''",
                        tuple(product_names_needing_recipe)
                    )
                    for row in cursor.fetchall():
                        if isinstance(row, dict):
                            recipe_lookup[row.get('nazwa_produktu')] = row.get('nr_receptury')
                        elif isinstance(row, (list, tuple)) and len(row) >= 2:
                            recipe_lookup[row[0]] = row[1]
                except Exception as e:
                    _logger.warning(f"Error looking up product recipes: {e}")
        
            zasyp_id_original_map = {}
            for p in plan_dnia:
                if len(p) > 14 and p[14]:
                    zasyp_id_original_map[p[0]] = p[14]
            
                # Extract extra columns properly based on SQL select list
                odrzuty = p[15] if len(p) > 15 else 0
                rodzaj_palety = p[16] if len(p) > 16 else 'krajowa'
                nr_receptury_val = p[17] if len(p) > 17 and p[17] else recipe_lookup.get(p[1], '')
                opak_nazwa = p[18] if len(p) > 18 else None
                etyk_nazwa = p[19] if len(p) > 19 else None
            
                # Shrink back to 15 items (indices 0-14) to clear the dynamically added extra_cols
                while len(p) > 15:
                    p.pop()

                # Ensure we have enough space for extra metadata (indices 15-30)
                while len(p) < 31:
                    p.append(None)
                
                p[15] = odrzuty
                p[27] = opak_nazwa
                p[28] = etyk_nazwa
                p[29] = rodzaj_palety
                p[30] = nr_receptury_val
            
                src = przeniesione_map.get(p[0], '')
                if not src:
                    nazwa = (p[12] if len(p) > 12 and p[12] is not None else '')
                    for prefix in ('PRZENIESIONE z ', 'carry-over z '):
                        if nazwa.startswith(prefix):
                            raw_date = nazwa[len(prefix):].strip()
                            try:
                                src = datetime.strptime(raw_date, '%Y-%m-%d').strftime('%d.%m.%Y')
                            except Exception: pass
                            break
                p[15] = src
                p[16] = 0

            # Carry-over tonaz lookup
            if include_details:
                ProductionService._populate_carry_over_tonaz(plan_dnia, linia, zasyp_id_original_map, cursor=cursor)

            # Batch lookups for Workowanie/Zasyp sync
            ProductionService._sync_sections_weights(dzisiaj, sekcja, linia, plan_dnia, cursor)
            ProductionService._populate_agro_start_requirements(plan_dnia, linia, cursor)

            if not include_details:
                # The overview renders plan rows, weights and start requirements;
                # it never renders batch/pallet histories, recipe fallbacks or totals.
                return plan_dnia, {}, 0, 0
        
            # Final aggregation
            try:
                res = ProductionService._aggregate_final_results(dzisiaj, sekcja, linia, plan_dnia, cursor)
                return res
            except Exception as e:
                _logger.exception(f"Error in get_production_plans finishing: {e}")
                return [], {}, 0, 0
        finally:
            if conn:
                conn.close()

    @staticmethod
    def _get_transfer_map(plan_dnia, linia, cursor) -> Dict[int, str]:
        if not plan_dnia: return {}
        plan_ids = [p[0] for p in plan_dnia]
        fmt_ids = ','.join(['%s'] * len(plan_ids))
        przeniesione_map = {}
        try:
            cursor.execute(f"""
                SELECT ph.plan_id,
                       SUBSTRING_INDEX(SUBSTRING_INDEX(ph.changes, ' na ', 1), 'Z ', -1) AS stara_data
                FROM plan_history ph
                INNER JOIN (
                    SELECT plan_id, MAX(id) AS max_id FROM plan_history
                    WHERE action = 'przeniesienie' AND plan_id IN ({fmt_ids})
                    GROUP BY plan_id
                ) last ON last.plan_id = ph.plan_id AND last.max_id = ph.id
            """, plan_ids)
            for row in cursor.fetchall():
                stara = str(row[1]).strip() if row[1] else ''
                if stara:
                    try: przeniesione_map[row[0]] = datetime.strptime(stara, '%Y-%m-%d').strftime('%d.%m.%Y')
                    except Exception: pass
        except Exception: pass
        return przeniesione_map

    @staticmethod
    def _populate_carry_over_tonaz(plan_dnia, linia, zasyp_id_original_map, cursor=None):
        carry_over_plans = [p for p in plan_dnia if p[15]]
        if not carry_over_plans: return
        conn = None
        try:
            table_bufor = get_table_name('bufor', linia)
            zasyp_id_map = {p[0]: zasyp_id_original_map.get(p[0]) for p in carry_over_plans if zasyp_id_original_map.get(p[0])}
            if zasyp_id_map:
                ids = list(zasyp_id_map.values())
                fmt = ','.join(['%s'] * len(ids))
                if cursor is None:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                cursor.execute(f"SELECT zasyp_id, tonaz_rzeczywisty FROM {table_bufor} WHERE zasyp_id IN ({fmt})", ids)
                weights = {r[0]: int(r[1] or 0) for r in cursor.fetchall()}
                for p in plan_dnia:
                    zid = zasyp_id_map.get(p[0])
                    if zid: p[16] = weights.get(zid, 0)
        except Exception: pass
        finally:
            if conn:
                try:
                    cursor.close()
                finally:
                    conn.close()

    @staticmethod
    def _sync_sections_weights(dzisiaj, sekcja, linia, plan_dnia, cursor):
        if not plan_dnia: return
        table_plan = get_table_name('plan_produkcji', linia)
        prods = [p[1] for p in plan_dnia]
        fmt = ",".join(["%s"] * len(prods))
        if sekcja in ('Workowanie', 'Czyszczenie') and prods:
            work_ids = [p[0] for p in plan_dnia]
            fmt_w = ",".join(["%s"] * len(work_ids))
            
            cursor.execute(f"""
                SELECT w.id, COALESCE(z.tonaz_rzeczywisty, 0)
                FROM {table_plan} w
                JOIN {table_plan} z ON w.zasyp_id = z.id
                WHERE w.id IN ({fmt_w}) AND z.sekcja = 'Zasyp'
            """, work_ids)
            zasyp_by_id = {r[0]: r[1] for r in cursor.fetchall()}
            
            cursor.execute(f"SELECT produkt, COALESCE(tonaz_rzeczywisty, 0) FROM {table_plan} WHERE DATE(data_planu) = %s AND sekcja = 'Zasyp' AND produkt IN ({fmt})", (dzisiaj, *prods))
            weights = {r[0]: r[1] for r in cursor.fetchall()}
            for p in plan_dnia: 
                zw = zasyp_by_id.get(p[0])
                if not zw:
                    zw = weights.get(p[1])
                if zw: p[2] = zw
        elif sekcja == 'Zasyp' and prods:
            cursor.execute(f"SELECT produkt, SUM(uszkodzone_worki) FROM {table_plan} WHERE DATE(data_planu) = %s AND sekcja IN ('Workowanie', 'Czyszczenie') AND produkt IN ({fmt}) GROUP BY produkt", (dzisiaj, *prods))
            uszk = {r[0]: r[1] for r in cursor.fetchall()}
            for p in plan_dnia: p[11] = (p[11] or 0) + int(uszk.get(p[1], 0))

    @staticmethod
    def _populate_agro_start_requirements(plan_dnia, linia, cursor):
        if linia != 'AGRO' or not plan_dnia:
            return

        plan_ids = [p[0] for p in plan_dnia if p and p[0] is not None]
        if not plan_ids:
            return

        table_plan = get_table_name('plan_produkcji', linia)
        fmt_ids = ','.join(['%s'] * len(plan_ids))
        meta_map = {}

        try:
            cursor.execute(
                f"""
                SELECT p.id,
                       p.opakowanie_id,
                       p.etykieta_id,
                       COALESCE(o.nazwa, ''),
                       COALESCE(e.nazwa, ''),
                       COALESCE(p.start_checklist_operator_login, ''),
                       p.start_checklist_operator_at,
                       COALESCE(p.start_checklist_quality_login, ''),
                       p.start_checklist_quality_at
                FROM {table_plan} p
                LEFT JOIN magazyn_opakowania o ON p.opakowanie_id = o.id
                LEFT JOIN slownik_etykiety_agro e ON p.etykieta_id = e.id
                WHERE p.id IN ({fmt_ids})
                """,
                plan_ids,
            )
            meta_map = {
                row[0]: (
                    row[1],
                    row[2],
                    row[3] or '',
                    row[4] or '',
                    row[5] or '',
                    row[6],
                    row[7] or '',
                    row[8],
                )
                for row in cursor.fetchall()
            }
        except Exception as exc:
            _logger.warning("Unable to load AGRO start requirements metadata: %s", exc)

        for p in plan_dnia:
            while len(p) < 27:
                p.append(None)
            (
                opak_id,
                etyk_id,
                opak_name,
                etyk_name,
                checklist_operator_login,
                checklist_operator_at,
                checklist_quality_login,
                checklist_quality_at,
            ) = meta_map.get(p[0], (None, None, '', '', '', None, '', None))
            p[18] = opak_id
            p[19] = etyk_id
            p[20] = opak_name
            p[21] = etyk_name
            p[22] = checklist_operator_login
            p[23] = checklist_operator_at
            p[24] = checklist_quality_login
            p[25] = checklist_quality_at
            p[26] = bool(checklist_operator_login and checklist_operator_at and checklist_quality_login and checklist_quality_at)

    @staticmethod
    def _aggregate_final_results(dzisiaj, sekcja, linia, plan_dnia, cursor) -> Tuple[List, Dict, int, int]:
        palety_mapa = {}
        suma_plan = 0
        suma_wykonanie = 0
        plan_ids = [p[0] for p in plan_dnia]
        fmt_ids = ','.join(['%s'] * len(plan_ids)) if plan_ids else '0'

        # Batch counts
        counts = {}
        if plan_ids:
            table = get_table_name('szarze' if sekcja == 'Zasyp' else 'palety_workowanie', linia)
            cursor.execute(f"SELECT plan_id, COUNT(*) FROM {table} WHERE plan_id IN ({fmt_ids}) GROUP BY plan_id", plan_ids)
            counts = {r[0]: r[1] for r in cursor.fetchall()}

        # Batch quality
        quality_map = {}
        if plan_ids:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f"SELECT id, typ_zlecenia, sekcja FROM {table_plan} WHERE id IN ({fmt_ids})", plan_ids)
            quality_map = {r[0]: (r[1] == 'jakosc' or r[2] == 'Jakosc') for r in cursor.fetchall()}

        if sekcja == 'Magazyn':
            palety_mapa = WarehouseService.get_palety_for_plans_batch(dzisiaj, plan_dnia, linia, cursor)

        for p in plan_dnia:
            p[7] = p[7] or 0
            is_q = quality_map.get(p[0], False)
            if not is_q: suma_plan += p[2] or 0
            
            if sekcja == 'Magazyn':
                p[7] = sum(pal[2] for pal in palety_mapa.get(p[0], [])) # PaletaDTO weight is at index 2 in WarehouseService return
            
            if sekcja == 'Zasyp':
                p.extend([p[7], (p[2] or 0) - p[7], abs((p[2] or 0) - p[7]) > 10])
            
            while len(p) <= 26: p.append(None)
            p[17] = int(counts.get(p[0], 0))
            if not is_q: suma_wykonanie += p[7] or 0

        # Detailed Szarze/Palety logic
        if plan_ids:
            if sekcja == 'Zasyp':
                table_szarze = get_table_name('szarze', linia)
                table_dosypki = get_table_name('dosypki', linia)

                cursor.execute(
                    f"""
                    SELECT
                        s.plan_id,
                        s.id,
                        s.waga,
                        s.godzina,
                        s.status,
                        COALESCE(p.imie_nazwisko, s.pracownik_id),
                        COALESCE(s.uwagi, ''),
                        s.nr_szarzy,
                        s.data_dodania
                    FROM {table_szarze} s
                    LEFT JOIN pracownicy p ON s.pracownik_id = p.id
                    WHERE s.plan_id IN ({fmt_ids})
                    ORDER BY s.id ASC
                    """,
                    plan_ids,
                )
                szarze_rows = cursor.fetchall() or []

                emptied_zasypy = set()
                try:
                    linia_u = (linia or 'PSD').strip().upper()
                    if linia_u == 'AGRO':
                        cursor.execute(
                            f"""
                            SELECT plan_id, szarza_nr
                            FROM zasyp_etapy
                            WHERE linia = 'AGRO' AND plan_id IN ({fmt_ids})
                              AND etap = 5 AND czas_stop IS NOT NULL
                            """,
                            plan_ids,
                        )
                    else:
                        cursor.execute(
                            f"""
                            SELECT plan_id, szarza_nr
                            FROM zasyp_etapy
                            WHERE linia = %s AND plan_id IN ({fmt_ids})
                              AND (
                                (etap = 6 AND czas_stop IS NOT NULL)
                                OR (etap = 5 AND czas_stop IS NOT NULL)
                              )
                            """,
                            [linia_u] + plan_ids,
                        )
                    for erow in cursor.fetchall() or []:
                        emptied_zasypy.add((erow[0], erow[1]))
                except Exception:
                    _logger.debug('Failed to fetch emptied_zasypy for dashboard', exc_info=True)

                cursor.execute(
                    f"""
                    SELECT d.szarza_id, d.nazwa, COALESCE(d.kg_wydozowane, d.kg), COALESCE(d.kg_planowane, d.kg), d.id
                    FROM {table_dosypki} d
                    WHERE d.plan_id IN ({fmt_ids})
                      AND d.szarza_id IS NOT NULL
                      AND d.potwierdzone = 1
                      AND COALESCE(d.anulowana, 0) = 0
                    ORDER BY d.data_potwierdzenia ASC, d.id ASC
                    """,
                    plan_ids,
                )
                dosypki_rows = cursor.fetchall() or []

                dosypki_by_szarza: Dict[int, List[Tuple[str, float, float, int]]] = {}
                dosypki_sum_by_szarza: Dict[int, float] = {}
                for d_row in dosypki_rows:
                    try:
                        szarza_id = int(d_row[0])
                    except Exception:
                        continue
                    nazwa = str(d_row[1] or '').strip()
                    kg_wyd = float(d_row[2] or 0)
                    kg_plan = float(d_row[3] or d_row[2] or 0)
                    dosypki_by_szarza.setdefault(szarza_id, []).append((nazwa, kg_wyd, kg_plan, int(d_row[4])))
                    dosypki_sum_by_szarza[szarza_id] = float(dosypki_sum_by_szarza.get(szarza_id, 0.0)) + kg_wyd

                # Load dumped Wiaderka z Maluchami
                cursor.execute(
                    f"""
                    SELECT w.szarza_id, w.id, w.kod_wiadra, w.waga_calkowita, DATE_FORMAT(w.data_zasypania, '%H:%i'), COALESCE(w.mieszalnik_kod, 'MI01')
                    FROM wiaderka_maluchy w
                    WHERE w.plan_id IN ({fmt_ids})
                      AND w.status = 'wrzucone_do_mieszalnika'
                    ORDER BY w.data_zasypania ASC, w.id ASC
                    """,
                    plan_ids,
                )
                wiaderka_rows = cursor.fetchall() or []
                bucket_ids = [int(w[1]) for w in wiaderka_rows if w[1] is not None]
                items_by_bucket: Dict[int, List[Dict[str, Any]]] = {}
                ko_pallet_map = ProductionService.get_ko_station_pallet_map(cursor=cursor, linia=linia)
                if bucket_ids:
                    fmt_b_ids = ','.join(['%s'] * len(bucket_ids))
                    cursor.execute(
                        f"""
                        SELECT wiaderko_id, stacja_kod, surowiec_nazwa, waga_faktyczna
                        FROM wiaderka_maluchy_pozycje
                        WHERE wiaderko_id IN ({fmt_b_ids})
                        ORDER BY id ASC
                        """,
                        bucket_ids,
                    )
                    for item_row in cursor.fetchall() or []:
                        b_id = int(item_row[0])
                        stacja_kod = str(item_row[1] or '').strip().upper()
                        surowiec_nazwa = str(item_row[2] or '').strip()
                        ko_info = ko_pallet_map.get(stacja_kod) or {}
                        is_premix = ProductionService.is_ko_premix(stacja_kod, surowiec_nazwa or ko_info.get('surowiec', ''))
                        items_by_bucket.setdefault(b_id, []).append({
                            'stacja': stacja_kod,
                            'surowiec': surowiec_nazwa,
                            'waga': float(item_row[3] or 0),
                            'is_premix': is_premix,
                            'nr_palety': ko_info.get('nr_palety') or '',
                            'nr_partii': ko_info.get('nr_partii') or '',
                        })

                wiaderka_by_szarza: Dict[int, List[Dict[str, Any]]] = {}
                for w_row in wiaderka_rows:
                    sz_id = int(w_row[0]) if w_row[0] is not None else 0
                    b_id = int(w_row[1])
                    w_kod = str(w_row[2] or '')
                    w_waga = float(w_row[3] or 0)
                    w_godz = str(w_row[4] or '')
                    w_mieszalnik = str(w_row[5] or 'MI01')
                    b_pozycje = items_by_bucket.get(b_id, [])
                    wiaderko_obj = {
                        'id': b_id,
                        'kod': w_kod,
                        'waga': w_waga,
                        'godzina': w_godz,
                        'mieszalnik': w_mieszalnik,
                        'pozycje': b_pozycje,
                        'premix_pozycje': [poz for poz in b_pozycje if poz.get('is_premix')],
                    }
                    wiaderka_by_szarza.setdefault(sz_id, []).append(wiaderko_obj)

                for row in szarze_rows:
                    pid = row[0]
                    szarza_id = int(row[1]) if row[1] is not None else 0
                    baza_waga = float(row[2] or 0)
                    suma_dosypki = float(dosypki_sum_by_szarza.get(szarza_id, 0.0))
                    godzina = row[3]
                    status = row[4] or ''
                    autor = row[5] or ''
                    uwagi = row[6] or ''
                    nr_sz = row[7] if len(row) > 7 and row[7] is not None else None
                    is_emptied = bool((pid, nr_sz) in emptied_zasypy) if nr_sz else False

                    # Łączna waga szarży: zasyp + dosypki + wiaderka maluchów
                    suma_wiaderka = sum(float(w.get('waga') or 0.0) for w in wiaderka_by_szarza.get(szarza_id, []))
                    waga_laczna = baza_waga + suma_dosypki + suma_wiaderka

                    if pid not in palety_mapa:
                        palety_mapa[pid] = []
                    palety_mapa[pid].append(
                        [
                            waga_laczna,
                            godzina,
                            szarza_id,
                            dosypki_by_szarza.get(szarza_id, []),
                            status,
                            autor,
                            uwagi,
                            wiaderka_by_szarza.get(szarza_id, []),
                            nr_sz,
                            is_emptied,
                            _format_date(row[8] if len(row) > 8 else None),
                        ]
                    )

            else:
                table_details = get_table_name('palety_workowanie', linia)
                # Ujednolicony kształt dla widoku kart dashboardu:
                # [0]=waga, [1]=godzina, [2]=paleta_id, [3]=lista_dodatkowa, [4]=status, [5]=autor, [6]=uwagi, [7]=nr_palety_lp, [8]=nr_palety
                cursor.execute(f"SHOW COLUMNS FROM {table_details} LIKE 'nr_palety_lp'")
                has_lp_col = bool(cursor.fetchone())
                lp_field = "COALESCE(nr_palety_lp, 0)" if has_lp_col else "0"

                cursor.execute(
                    f"SELECT plan_id, id, waga, DATE_FORMAT(data_dodania, '%Y-%m-%d %H:%i'), status, COALESCE(dodal_login, ''), {lp_field}, nr_palety "
                    f"FROM {table_details} WHERE plan_id IN ({fmt_ids}) ORDER BY id ASC",
                    plan_ids,
                )
                for row in cursor.fetchall():
                    pid = row[0]
                    if pid not in palety_mapa:
                        palety_mapa[pid] = []
                    palety_mapa[pid].append(
                        [
                            float(row[2] or 0),
                            row[3],
                            int(row[1]) if row[1] is not None else 0,
                            [],
                            row[4] or '',
                            row[5] or '',
                            '',
                            int(row[6] or 0),
                            str(row[7] or ''),
                        ]
                    )


        return plan_dnia, palety_mapa, suma_plan, suma_wykonanie

    @staticmethod
    def _get_workowanie_fallback(dzisiaj: date, linia='PSD', cursor=None) -> List:
        table_plan = get_table_name('plan_produkcji', linia)
        table_szarze = get_table_name('szarze', linia)
        table_bufor = get_table_name('bufor', linia)
        cursor.execute(f"""
            SELECT id, produkt, tonaz, status, real_start, real_stop, 
                   TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, 
                   kolejnosc, typ_produkcji, wyjasnienie_rozbieznosci,
                   COALESCE(uszkodzone_worki, 0), COALESCE(nazwa_zlecenia, ''), data_planu, zasyp_id
            FROM {table_plan} p
            WHERE DATE(p.data_planu) = %s AND p.sekcja IN ('Workowanie', 'Czyszczenie') AND p.status IN ('w toku', 'zaplanowane')
            AND (EXISTS (SELECT 1 FROM {table_szarze} s WHERE s.plan_id = p.id AND s.status = 'zarejestowana')
                 OR EXISTS (SELECT 1 FROM {table_bufor} b WHERE b.produkt = p.produkt AND b.status = 'aktywny'))
            ORDER BY CASE p.status WHEN 'zakonczone' THEN 2 ELSE 1 END, p.id ASC
        """, (dzisiaj,))
        return [list(r) for r in cursor.fetchall()]

    @staticmethod
    def get_zasyp_started_produkty(data_planu, linia='PSD', cursor=None) -> List[str]:
        return QueryHelper.get_zasyp_started_produkty(data_planu, linia=linia, cursor=cursor)

    @staticmethod
    def get_pending_quality_count(linia='PSD', cursor=None) -> int:
        return QueryHelper.get_pending_quality_count(linia=linia, cursor=cursor)

    @staticmethod
    def is_ko_premix(stacja_kod: str, surowiec_nazwa: str) -> bool:
        """Sprawdza, czy pozycja na stacji KO jest premiksem (np. C, C/Cu, C+chelaty, Witamina C, Witamina Chelaty)."""
        station = str(stacja_kod or '').strip().upper()
        if not station.startswith('KO'):
            return False
        name = str(surowiec_nazwa or '').strip().lower()
        if not name:
            return station in ('KO21', 'KO22', 'KO23')
        premix_tokens = (
            'premix',
            'premiks',
            'chelat',
            'c/cu',
            'c / cu',
            'c+chelat',
            'c + chelat',
            'witamina c',
            'wit c',
            'wit. c',
            'vit c',
            'vit. c',
        )
        if any(tok in name for tok in premix_tokens):
            return True
        if name in ('c', 'cu', 'c/cu'):
            return True
        if station in ('KO21', 'KO22', 'KO23'):
            return True
        return False

    @staticmethod
    def get_ko_station_pallet_map(cursor=None, linia='AGRO') -> Dict[str, Dict[str, Any]]:
        """Zwraca mapę stacji KO -> {stacja, surowiec, nr_palety, nr_partii, is_premix} dla wsypanych palet."""
        conn = None
        result: Dict[str, Dict[str, Any]] = {}
        try:
            if cursor is None:
                conn = get_db_connection()
                cursor = conn.cursor()

            # 1. Konfiguracja zbiorników KO
            try:
                cursor.execute(
                    "SELECT UPPER(TRIM(kod_zbiornika)), TRIM(COALESCE(nazwa_surowca, '')) "
                    "FROM konfiguracja_zbiornikow WHERE is_active = 1 AND UPPER(TRIM(kod_zbiornika)) LIKE 'KO%'"
                )
                for row in cursor.fetchall() or []:
                    st = str(row[0] or '').strip().upper()
                    nazwa = str(row[1] or '').strip()
                    if st:
                        result[st] = {
                            'stacja': st,
                            'surowiec': nazwa,
                            'nr_palety': '',
                            'nr_partii': '',
                            'is_premix': ProductionService.is_ko_premix(st, nazwa),
                        }
            except Exception:
                pass

            # 2. Ruchy produkcyjne z magazyn_agro_ruch i magazyn_ruch na stacje KO
            for ruch_tbl in ('magazyn_agro_ruch', 'magazyn_ruch'):
                try:
                    cursor.execute(
                        f"""
                        SELECT UPPER(TRIM(r.zbiornik)) AS stacja,
                               COALESCE(NULLIF(TRIM(s.nazwa), ''), TRIM(COALESCE(r.surowiec_nazwa, ''))) AS nazwa,
                               COALESCE(TRIM(s.nr_palety), '') AS nr_palety,
                               COALESCE(TRIM(s.nr_partii), '') AS nr_partii
                        FROM {ruch_tbl} r
                        LEFT JOIN magazyn_surowce s ON r.surowiec_id = s.id
                        WHERE r.status = 'POTWIERDZONE'
                          AND r.typ_ruchu IN ('PRODUKCJA', 'INWENTARYZACJA_PROD')
                          AND UPPER(TRIM(COALESCE(r.zbiornik, ''))) LIKE 'KO%'
                        ORDER BY r.autor_data DESC, r.id DESC
                        """
                    )
                    for row in cursor.fetchall() or []:
                        st = str(row[0] or '').strip().upper()
                        nazwa = str(row[1] or '').strip()
                        nr_pal = str(row[2] or '').strip()
                        nr_par = str(row[3] or '').strip()
                        if not st:
                            continue
                        entry = result.setdefault(st, {
                            'stacja': st,
                            'surowiec': nazwa,
                            'nr_palety': '',
                            'nr_partii': '',
                            'is_premix': ProductionService.is_ko_premix(st, nazwa),
                        })
                        if nazwa and not entry.get('surowiec'):
                            entry['surowiec'] = nazwa
                        if nr_pal and not entry.get('nr_palety'):
                            entry['nr_palety'] = nr_pal
                            entry['nr_partii'] = nr_par
                        entry['is_premix'] = ProductionService.is_ko_premix(st, entry.get('surowiec') or nazwa)
                except Exception:
                    pass

            # 3. Fallback z magazyn_surowce po lokalizacji KOxx
            try:
                cursor.execute(
                    """
                    SELECT UPPER(TRIM(lokalizacja)) AS stacja,
                           TRIM(COALESCE(nazwa, '')) AS nazwa,
                           TRIM(COALESCE(nr_palety, '')) AS nr_palety,
                           TRIM(COALESCE(nr_partii, '')) AS nr_partii
                    FROM magazyn_surowce
                    WHERE UPPER(TRIM(COALESCE(lokalizacja, ''))) LIKE 'KO%'
                    ORDER BY updated_at DESC, id DESC
                    """
                )
                for row in cursor.fetchall() or []:
                    st = str(row[0] or '').strip().upper()
                    nazwa = str(row[1] or '').strip()
                    nr_pal = str(row[2] or '').strip()
                    nr_par = str(row[3] or '').strip()
                    if not st:
                        continue
                    entry = result.setdefault(st, {
                        'stacja': st,
                        'surowiec': nazwa,
                        'nr_palety': '',
                        'nr_partii': '',
                        'is_premix': ProductionService.is_ko_premix(st, nazwa),
                    })
                    if nazwa and not entry.get('surowiec'):
                        entry['surowiec'] = nazwa
                    if nr_pal and not entry.get('nr_palety'):
                        entry['nr_palety'] = nr_pal
                        entry['nr_partii'] = nr_par
                    elif nr_par and not entry.get('nr_partii') and entry.get('nr_palety') == nr_pal:
                        entry['nr_partii'] = nr_par
                    entry['is_premix'] = ProductionService.is_ko_premix(st, entry.get('surowiec') or nazwa)
            except Exception:
                pass

        except Exception as exc:
            _logger.warning("get_ko_station_pallet_map error: %s", exc)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        return result

    @staticmethod
    def get_active_ko_premixes(cursor=None, linia='AGRO') -> List[Dict[str, Any]]:
        """Zwraca listę aktywnych premiksów wsypanych na stacje KO (wraz z nr palety, partią i stanem kg)."""
        try:
            from app.repositories.agro_tanks_repository import AgroTanksRepository
            snapshot = AgroTanksRepository.get_production_inventory_snapshot(linia=linia, show_empty=False)
        except Exception:
            snapshot = []

        ko_map = ProductionService.get_ko_station_pallet_map(cursor=cursor, linia=linia)
        active_by_station: Dict[str, Dict[str, Any]] = {}

        for item in snapshot:
            st = str(item.get('zbiornik') or '').strip().upper()
            if not st.startswith('KO'):
                continue
            stan_kg = float(item.get('stan_systemowy') or 0.0)
            if stan_kg <= 0:
                continue
            info = ko_map.get(st) or {}
            nazwa = str(item.get('surowiec_nazwa') or item.get('nazwa') or info.get('surowiec') or '').strip()
            if not ProductionService.is_ko_premix(st, nazwa):
                continue
            nr_pal = str(item.get('nr_palety') or info.get('nr_palety') or '').strip()
            nr_par = str(item.get('nr_partii') or info.get('nr_partii') or '').strip()
            active_by_station[st] = {
                'stacja': st,
                'surowiec': nazwa,
                'nr_palety': nr_pal,
                'nr_partii': nr_par,
                'stan_kg': stan_kg,
            }

        for st, info in ko_map.items():
            if st in active_by_station:
                continue
            if info.get('is_premix') and info.get('nr_palety'):
                active_by_station[st] = {
                    'stacja': st,
                    'surowiec': info.get('surowiec') or '',
                    'nr_palety': info.get('nr_palety') or '',
                    'nr_partii': info.get('nr_partii') or '',
                    'stan_kg': 0.0,
                }

        return sorted(active_by_station.values(), key=lambda x: x.get('stacja') or '')
