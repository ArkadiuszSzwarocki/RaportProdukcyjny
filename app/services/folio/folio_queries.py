"""Read-only CQRS queries and settlement validations for AGRO film rolls."""
from __future__ import annotations

import re
import unicodedata

from app.core.database import get_db_connection, get_table_name

NON_WAREHOUSE_LOCATIONS = (
    'LP01',
    'MASZYNA',
    'ZUZYTE',
    'ZUŻYTE',
    'ARCHIWUM',
    'DO_ZWROTU',
)

DEPLETED_LOCATIONS = (
    '',
    'NONE',
    'ZUZYTE',
    'ZUŻYTE',
    'DO_ZWROTU',
    'ARCHIWUM',
)


def normalize_film_name(value: str | None) -> str:
    """Normalize packaging name for case-insensitive and whitespace-safe comparisons."""
    return ' '.join(unicodedata.normalize('NFC', str(value or '')).casefold().split())


class FolioQueries:
    """Query service for AGRO film inventory, coverage checks, and planning options."""

    @staticmethod
    def is_bagged_workowanie_plan(
        sekcja: str | None,
        typ_produkcji: str | None,
        produkt: str | None,
        typ_opakowania: str | None = None,
    ) -> bool:
        """Determine whether an AGRO order packs product into film bags."""
        section_norm = str(sekcja or '').strip().lower()
        if section_norm != 'workowanie':
            return False
        prod_name = str(produkt or '').strip().lower()
        if 'czyszczenie' in prod_name:
            return False
        prod_type = str(typ_produkcji or '').strip().lower()
        pack_type = str(typ_opakowania or '').strip().lower()
        if 'big_bag' in prod_type or 'bigbag' in prod_type or 'big_bag' in pack_type:
            return False
        return True

    @staticmethod
    def calculate_plan_bag_weight(produkt: str | None, typ_produkcji: str | None) -> float:
        """Resolve single bag weight in kg for an AGRO bagging plan."""
        prod_type = str(typ_produkcji or '').strip().lower()
        if 'big_bag' in prod_type or 'bigbag' in prod_type:
            return 0.0
        match = re.search(r'(\d+)\s*$', prod_type)
        if match:
            weight = float(match.group(1))
            if weight > 0:
                return weight
        prod_lc = str(produkt or '').strip().lower()
        if 'mleko' in prod_lc or '20' in prod_lc:
            return 20.0
        return 25.0

    @staticmethod
    def resolve_effective_start_counter(
        cursor,
        plan_id: int,
        plan_start_counter: int | None,
        live_counter: int,
    ) -> int:
        """Compute roll start counter without leaving uncounted gaps on the order."""
        cursor.execute(
            """
            SELECT MAX(licznik_stop) AS last_stop
            FROM agro_workowanie_rozliczenie
            WHERE plan_id = %s AND typ_zdarzenia = 'ZAMKNIECIE'
            """,
            (plan_id,),
        )
        row = cursor.fetchone()
        last_stop_raw = (
            row.get('last_stop')
            if isinstance(row, dict)
            else (row[0] if row else None)
        )
        last_stop = int(last_stop_raw or 0)
        if 0 < last_stop <= live_counter:
            return last_stop

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM agro_plan_opakowania
            WHERE plan_id = %s AND licznik_start IS NOT NULL
            """,
            (plan_id,),
        )
        cnt_row = cursor.fetchone()
        raw_cnt = (
            cnt_row.get('cnt')
            if isinstance(cnt_row, dict)
            else (cnt_row[0] if cnt_row else 0)
        )
        prior_used = int(raw_cnt or 0)
        order_start = int(plan_start_counter or 0)
        if prior_used == 0 and 0 < order_start <= live_counter:
            return order_start

        return live_counter

    @staticmethod
    def get_plan_produced_bags(cursor, plan_id: int) -> dict:
        """Return pallet count, total pallet weight, bag weight, and expected bag count."""
        table_plan = get_table_name('plan_produkcji', 'AGRO')
        cursor.execute(
            f"""
            SELECT id, sekcja, produkt, typ_produkcji, typ_opakowania, opakowanie_id,
                   start_machine_counter, stop_machine_counter
            FROM {table_plan}
            WHERE id = %s
            LIMIT 1
            """,
            (plan_id,),
        )
        plan_row = cursor.fetchone()
        if not plan_row:
            return {
                'exists': False,
                'requires_foil': False,
                'palety_count': 0,
                'palety_kg': 0.0,
                'bag_kg': 0.0,
                'expected_bags': 0,
            }

        if not isinstance(plan_row, dict):
            plan_meta = {
                'id': plan_row[0],
                'sekcja': plan_row[1],
                'produkt': plan_row[2],
                'typ_produkcji': plan_row[3],
                'typ_opakowania': plan_row[4],
                'opakowanie_id': plan_row[5],
                'start_machine_counter': plan_row[6],
                'stop_machine_counter': plan_row[7],
            }
        else:
            plan_meta = plan_row

        requires_foil = FolioQueries.is_bagged_workowanie_plan(
            plan_meta.get('sekcja'),
            plan_meta.get('typ_produkcji'),
            plan_meta.get('produkt'),
            plan_meta.get('typ_opakowania'),
        ) and bool(plan_meta.get('opakowanie_id'))

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(
                       CASE
                           WHEN status IN ('przyjeta', 'w_magazynie')
                               THEN COALESCE(NULLIF(waga_potwierdzona, 0), waga)
                           ELSE waga
                       END
                   ), 0) AS total_kg
            FROM palety_agro
            WHERE plan_id = %s AND COALESCE(status, '') != 'rezerwacja'
            """,
            (plan_id,),
        )
        pal_row = cursor.fetchone()
        if isinstance(pal_row, dict):
            palety_count = int(pal_row.get('cnt') or 0)
            palety_kg = float(pal_row.get('total_kg') or 0.0)
        else:
            palety_count = int((pal_row[0] if pal_row else 0) or 0)
            palety_kg = float((pal_row[1] if pal_row else 0.0) or 0.0)

        bag_kg = (
            FolioQueries.calculate_plan_bag_weight(
                plan_meta.get('produkt'),
                plan_meta.get('typ_produkcji'),
            )
            if requires_foil
            else 0.0
        )
        expected_bags = int(round(palety_kg / bag_kg)) if bag_kg > 0 and palety_kg > 0 else 0
        return {
            'exists': True,
            'requires_foil': requires_foil,
            'palety_count': palety_count,
            'palety_kg': palety_kg,
            'bag_kg': bag_kg,
            'expected_bags': expected_bags,
        }

    @staticmethod
    def get_settled_foil_totals(cursor, plan_id: int) -> dict:
        """Aggregate closed and withdrawn film bag counts for a given order."""
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(
                    CASE WHEN typ_zdarzenia = 'WSADZENIE' THEN stan_przed ELSE 0 END
                ), 0) AS suma_pobranych,
                COALESCE(SUM(
                    CASE WHEN typ_zdarzenia = 'ZAMKNIECIE' THEN zuzyte_worki ELSE 0 END
                ), 0) AS suma_zuzyto,
                COALESCE(SUM(
                    CASE WHEN typ_zdarzenia = 'ZAMKNIECIE' THEN straty_worki ELSE 0 END
                ), 0) AS suma_strat,
                COALESCE(SUM(
                    CASE WHEN typ_zdarzenia = 'ZAMKNIECIE' THEN pozostalo_na_rolce ELSE 0 END
                ), 0) AS suma_pozostalo
            FROM agro_workowanie_rozliczenie
            WHERE plan_id = %s
            """,
            (plan_id,),
        )
        row = cursor.fetchone()
        if isinstance(row, dict):
            return {
                'suma_pobranych': float(row.get('suma_pobranych') or 0.0),
                'suma_zuzyto': float(row.get('suma_zuzyto') or 0.0),
                'suma_strat': float(row.get('suma_strat') or 0.0),
                'suma_pozostalo': float(row.get('suma_pozostalo') or 0.0),
            }
        return {
            'suma_pobranych': float((row[0] if row else 0.0) or 0.0),
            'suma_zuzyto': float((row[1] if row else 0.0) or 0.0),
            'suma_strat': float((row[2] if row else 0.0) or 0.0),
            'suma_pozostalo': float((row[3] if row else 0.0) or 0.0),
        }

    @staticmethod
    def validate_plan_foil_coverage(cursor, plan_id: int) -> tuple[bool, str | None, dict]:
        """Validate that closed film rolls cover all bags produced on pallets."""
        prod_info = FolioQueries.get_plan_produced_bags(cursor, plan_id)
        settled_info = FolioQueries.get_settled_foil_totals(cursor, plan_id)

        expected_bags = int(prod_info['expected_bags'])
        settled_bags = int(round(settled_info['suma_zuzyto']))
        missing_bags = max(expected_bags - settled_bags, 0)
        uszkodzone_worki = max(settled_bags - expected_bags, 0)

        metrics = {
            **prod_info,
            **settled_info,
            'settled_bags': settled_bags,
            'missing_bags': missing_bags,
            'uszkodzone_worki': uszkodzone_worki,
        }

        if prod_info['requires_foil'] and expected_bags > 0 and settled_bags < expected_bags:
            palety_kg = prod_info['palety_kg']
            message = (
                f"Nie można zakończyć zlecenia #{plan_id}: na paletach wyprodukowano "
                f"{expected_bags} worków ({palety_kg:.0f} kg), a z rolek folii rozliczono "
                f"tylko {settled_bags} szt. (brakuje min. {missing_bags} szt.). "
                "Pobierz i rozlicz brakującą folię przed zamknięciem zlecenia."
            )
            return False, message, metrics

        return True, None, metrics

    @staticmethod
    def get_order_close_foil_preview(plan_id: int, active_rolls: list[dict] | None = None) -> dict:
        """Build foil coverage preview for the order completion confirmation view."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            prod_info = FolioQueries.get_plan_produced_bags(cursor, plan_id)
            settled_info = FolioQueries.get_settled_foil_totals(cursor, plan_id)
        finally:
            conn.close()

        rolls = active_rolls or []
        active_withdrawn = sum(
            int(round(float(r.get('stan_poczatkowy') or 0)))
            for r in rolls
            if not r.get('is_prepared')
        )
        already_settled = int(round(settled_info['suma_zuzyto']))
        max_possible_settled = already_settled + active_withdrawn
        expected_bags = int(prod_info['expected_bags'])
        deficit_before_withdrawal = (
            max(expected_bags - max_possible_settled, 0)
            if prod_info['requires_foil'] and expected_bags > 0
            else 0
        )

        return {
            **prod_info,
            'already_settled_bags': already_settled,
            'active_withdrawn_bags': active_withdrawn,
            'max_possible_settled_bags': max_possible_settled,
            'deficit_bags': deficit_before_withdrawal,
            'is_blocked': deficit_before_withdrawal > 0,
        }

    @staticmethod
    def get_available_foil_for_plan(cursor, required_name: str | None = None) -> list[dict]:
        """Return unassigned LP01 leftover rolls first, followed by warehouse stock."""
        excluded_placeholders = ', '.join(['%s'] * len(DEPLETED_LOCATIONS))
        params: list = list(DEPLETED_LOCATIONS)
        name_clause = ''
        if required_name:
            name_clause = 'AND LOWER(TRIM(nazwa)) = LOWER(TRIM(%s))'
            params.append(required_name)

        cursor.execute(
            f"""
            SELECT id, nazwa, stan_magazynowy, lokalizacja, nr_palety, updated_at
            FROM magazyn_opakowania
            WHERE stan_magazynowy > 0
              AND COALESCE(is_blocked, 0) = 0
              AND UPPER(COALESCE(lokalizacja, '')) NOT IN ({excluded_placeholders})
              AND id NOT IN (SELECT opakowanie_id FROM agro_plan_opakowania WHERE is_active = TRUE)
              {name_clause}
            ORDER BY
              CASE WHEN UPPER(COALESCE(lokalizacja, '')) IN ('LP01', 'MASZYNA') THEN 0 ELSE 1 END,
              nazwa ASC,
              id ASC
            """,
            tuple(params),
        )
        return cursor.fetchall() or []

    @staticmethod
    def get_planning_packaging_options(cursor, exclude_labels: bool = False) -> list[dict]:
        """Return deduplicated canonical warehouse packaging options (excluding LP01/Maszyna)."""
        non_wh_placeholders = ', '.join(['%s'] * len(NON_WAREHOUSE_LOCATIONS))
        label_clause = "AND nazwa NOT LIKE '%%Etykieta%%'" if exclude_labels else ''
        cursor.execute(
            f"""
            SELECT id, nazwa, typ_opakowania, stan_magazynowy, lokalizacja
            FROM magazyn_opakowania
            WHERE UPPER(COALESCE(lokalizacja, '')) NOT IN ({non_wh_placeholders})
              {label_clause}
            ORDER BY
              (COALESCE(stan_magazynowy, 0) > 0) DESC,
              id ASC
            """,
            tuple(NON_WAREHOUSE_LOCATIONS),
        )
        rows = cursor.fetchall() or []
        seen_names: set[str] = set()
        options: list[dict] = []
        for item in rows:
            name_clean = str(item.get('nazwa') or '').strip()
            name_key = normalize_film_name(name_clean)
            if name_key and name_key not in seen_names:
                seen_names.add(name_key)
                options.append({
                    'id': item['id'],
                    'nazwa': name_clean,
                    'typ_opakowania': item.get('typ_opakowania') or 'Karton',
                })
        options.sort(key=lambda entry: entry['nazwa'].lower())
        return options

    @staticmethod
    def resolve_warehouse_packaging_id(cursor, packaging_ref) -> int | None:
        """Resolve a submitted packaging ID or name to a canonical warehouse record."""
        if packaging_ref in (None, '', 'None'):
            return None

        non_wh_placeholders = ', '.join(['%s'] * len(NON_WAREHOUSE_LOCATIONS))
        target_name: str | None = None

        try:
            candidate_id = int(packaging_ref)
        except (ValueError, TypeError):
            candidate_id = None
            target_name = str(packaging_ref).strip()

        if candidate_id is not None:
            cursor.execute(
                "SELECT id, nazwa, lokalizacja FROM magazyn_opakowania WHERE id = %s LIMIT 1",
                (candidate_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            row_id = row['id'] if isinstance(row, dict) else row[0]
            row_name = row['nazwa'] if isinstance(row, dict) else row[1]
            raw_loc = row['lokalizacja'] if isinstance(row, dict) else row[2]
            row_loc = str(raw_loc or '').strip().upper()
            if row_loc not in NON_WAREHOUSE_LOCATIONS:
                return int(row_id)
            target_name = str(row_name or '').strip()

        if not target_name:
            return candidate_id

        cursor.execute(
            f"""
            SELECT id
            FROM magazyn_opakowania
            WHERE LOWER(TRIM(nazwa)) = LOWER(TRIM(%s))
              AND UPPER(COALESCE(lokalizacja, '')) NOT IN ({non_wh_placeholders})
            ORDER BY (COALESCE(stan_magazynowy, 0) > 0) DESC, id ASC
            LIMIT 1
            """,
            tuple([target_name] + list(NON_WAREHOUSE_LOCATIONS)),
        )
        canonical = cursor.fetchone()
        if canonical:
            return int(canonical['id'] if isinstance(canonical, dict) else canonical[0])
        return candidate_id
