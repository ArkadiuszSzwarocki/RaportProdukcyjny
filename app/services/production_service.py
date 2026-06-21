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

_logger = logging.getLogger(__name__)

class ProductionService:
    @staticmethod
    def get_production_plans(dzisiaj: date, sekcja: str, linia='PSD', cursor=None, data_od=None, data_do=None) -> Tuple[List, Dict, int, int]:
        """Get production plans for section with formatting and palety mapping."""
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()

        # Trigger buffer sync for AGRO to ensure weights are correct (especially in test DB)
        if linia == 'AGRO':
            try:
                refresh_bufor_queue(linia='AGRO')
            except Exception as e:
                _logger.warning(f"Failed to refresh AGRO buffer: {e}")

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
        
        zasyp_id_original_map = {}
        for p in plan_dnia:
            if len(p) > 14 and p[14]:
                zasyp_id_original_map[p[0]] = p[14]
            
            # Extract opakowanie_nazwa and etykieta_nazwa if present
            opak_nazwa = p[15] if len(p) > 15 else None
            etyk_nazwa = p[16] if len(p) > 16 else None
            
            # Shrink back to 15 items to not mess up fixed index assignments
            while len(p) > 15:
                p.pop()

            # Ensure we have enough space for extra metadata (indices 15+)
            while len(p) < 29:
                p.append(None)
                
            p[27] = opak_nazwa
            p[28] = etyk_nazwa
            
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
        ProductionService._populate_carry_over_tonaz(plan_dnia, linia, zasyp_id_original_map)

        # Batch lookups for Workowanie/Zasyp sync
        ProductionService._sync_sections_weights(dzisiaj, sekcja, linia, plan_dnia, cursor)
        ProductionService._populate_agro_start_requirements(plan_dnia, linia, cursor)
        
        # Final aggregation
        try:
            res = ProductionService._aggregate_final_results(dzisiaj, sekcja, linia, plan_dnia, cursor)
            if conn:
                conn.close()
            return res
        except Exception as e:
            _logger.exception(f"Error in get_production_plans finishing: {e}")
            if conn:
                conn.close()
            return [], {}, 0, 0

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
    def _populate_carry_over_tonaz(plan_dnia, linia, zasyp_id_original_map):
        carry_over_plans = [p for p in plan_dnia if p[15]]
        if not carry_over_plans: return
        try:
            table_bufor = get_table_name('bufor', linia)
            zasyp_id_map = {p[0]: zasyp_id_original_map.get(p[0]) for p in carry_over_plans if zasyp_id_original_map.get(p[0])}
            if zasyp_id_map:
                ids = list(zasyp_id_map.values())
                fmt = ','.join(['%s'] * len(ids))
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(f"SELECT zasyp_id, tonaz_rzeczywisty FROM {table_bufor} WHERE zasyp_id IN ({fmt})", ids)
                weights = {r[0]: int(r[1] or 0) for r in cursor.fetchall()}
                for p in plan_dnia:
                    zid = zasyp_id_map.get(p[0])
                    if zid: p[16] = weights.get(zid, 0)
                conn.close()
        except Exception: pass

    @staticmethod
    def _sync_sections_weights(dzisiaj, sekcja, linia, plan_dnia, cursor):
        if not plan_dnia: return
        table_plan = get_table_name('plan_produkcji', linia)
        prods = [p[1] for p in plan_dnia]
        fmt = ",".join(["%s"] * len(prods))
        if sekcja in ('Workowanie', 'Czyszczenie') and prods:
            cursor.execute(f"SELECT produkt, COALESCE(tonaz_rzeczywisty, 0) FROM {table_plan} WHERE DATE(data_planu) = %s AND sekcja = 'Zasyp' AND produkt IN ({fmt})", (dzisiaj, *prods))
            weights = {r[0]: r[1] for r in cursor.fetchall()}
            for p in plan_dnia: 
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
                        COALESCE(s.uwagi, '')
                    FROM {table_szarze} s
                    LEFT JOIN pracownicy p ON s.pracownik_id = p.id
                    WHERE s.plan_id IN ({fmt_ids})
                    ORDER BY s.id ASC
                    """,
                    plan_ids,
                )
                szarze_rows = cursor.fetchall() or []

                cursor.execute(
                    f"""
                    SELECT d.szarza_id, d.nazwa, d.kg
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

                dosypki_by_szarza: Dict[int, List[Tuple[str, float]]] = {}
                dosypki_sum_by_szarza: Dict[int, float] = {}
                for d_row in dosypki_rows:
                    try:
                        szarza_id = int(d_row[0])
                    except Exception:
                        continue
                    nazwa = str(d_row[1] or '').strip()
                    kg = float(d_row[2] or 0)
                    dosypki_by_szarza.setdefault(szarza_id, []).append((nazwa, kg))
                    dosypki_sum_by_szarza[szarza_id] = float(dosypki_sum_by_szarza.get(szarza_id, 0.0)) + kg

                for row in szarze_rows:
                    pid = row[0]
                    szarza_id = int(row[1]) if row[1] is not None else 0
                    baza_waga = float(row[2] or 0)
                    suma_dosypki = float(dosypki_sum_by_szarza.get(szarza_id, 0.0))
                    godzina = row[3]
                    status = row[4] or ''
                    autor = row[5] or ''
                    uwagi = row[6] or ''

                    # Dla widoku szarży pokazujemy łączną wagę: zasyp + potwierdzone dosypki.
                    waga_laczna = baza_waga + suma_dosypki

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
                        ]
                    )

            else:
                table_details = get_table_name('palety_workowanie', linia)
                # Ujednolicony kształt dla widoku kart dashboardu:
                # [0]=waga, [1]=godzina, [2]=paleta_id, [3]=lista_dodatkowa, [4]=status, [5]=autor, [6]=uwagi
                cursor.execute(
                    f"SELECT plan_id, id, waga, TIME(data_dodania), status, COALESCE(dodal_login, '') "
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
