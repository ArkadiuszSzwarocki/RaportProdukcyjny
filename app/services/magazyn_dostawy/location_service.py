from app.db import get_db_connection, get_table_name
import json
from datetime import datetime
import uuid
import re
from app.utils.pallet_id import generate_pallet_id
from app.utils.location_validator import validate_warehouse_location, is_production_tank_code

class LocationService:

    OPEN_LOCATIONS_PREFIXES = [
        'MS01', 'MP01', 'MD01', 'MOP01', 'BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'BFOS', 'MDM01',
        'PSD01', 'MGW01', 'MGW02', 'OSIP', 'KO01', 'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP', 'PSD'
    ]

    @staticmethod
    def check_location(lokalizacja, linia='PSD'):
            if any(str(lokalizacja or '').upper().startswith(ol) for ol in LocationService.OPEN_LOCATIONS_PREFIXES):
                return False, "", [] # Always free for open locations

            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                table_sur = get_table_name('magazyn_surowce', linia)
                table_opk = get_table_name('magazyn_opakowania', linia)
                cursor.execute(f"SELECT nazwa, stan_magazynowy, 'Surowiec' as typ FROM {table_sur} WHERE lokalizacja = %s AND stan_magazynowy > 0", (lokalizacja,))
                items_sur = cursor.fetchall()
                cursor.execute(f"SELECT nazwa, stan_magazynowy, 'Opakowanie' as typ FROM {table_opk} WHERE lokalizacja = %s AND stan_magazynowy > 0", (lokalizacja,))
                items_opk = cursor.fetchall()
                all_items = items_sur + items_opk
                if all_items:
                    content_desc = ", ".join([f"{i['nazwa']} ({i['stan_magazynowy']})" for i in all_items])
                    return True, content_desc, all_items
                return False, "", []
            finally:
                conn.close()

    @staticmethod
    def validate_slot_capacity(target_location: str, linia: str = 'PSD', excluding_pallet_code: str = None) -> tuple[bool, str]:
        """
        Validates rack slot capacity.
        Standard high-storage racks (R01-R07) have a hard capacity limit of 1 pallet per slot.
        Open buffer zones (RAMPA, BUFOR, KO, BB) allow multiple pallets.
        """
        norm_loc = LocationService._normalize_location_code(target_location)
        if not norm_loc:
            return False, "Nie podano lokalizacji docelowej."

        if any(norm_loc.startswith(p) for p in LocationService.OPEN_LOCATIONS_PREFIXES):
            return True, "Lokalizacja otwarta - nieograniczona pojemność."

        if LocationService._is_rack_location_code(norm_loc):
            is_occupied, content_desc, items = LocationService.check_location(target_location, linia)
            if is_occupied:
                if excluding_pallet_code:
                    items = [it for it in items if str(it.get('nr_palety') or '').upper() != excluding_pallet_code.upper()]
                if items:
                    return False, f"Gniazdo regałowe {target_location} jest już zajęte przez: {content_desc} (Limit: 1 paleta / gniazdo)."

        return True, "Lokalizacja dostępna."

    @staticmethod
    def get_location_suggestions(prefix, linia='PSD', only_free_for_racks=True, limit=40):
            prefix_normalized = LocationService._normalize_location_code(prefix)
            if not prefix_normalized:
                return []

            safe_limit = max(1, min(int(limit or 40), 100))

            candidates = LocationService._build_static_location_candidates()
            occupied_locations = set()

            try:
                db_locations, occupied_locations = LocationService._load_db_location_sets(linia)
                candidates.update(db_locations)
            except Exception:
                # Fallback to static dictionary if DB lookup is temporarily unavailable.
                pass

            matched = []
            for location in candidates:
                if not LocationService._normalize_location_code(location).startswith(prefix_normalized):
                    continue

                if only_free_for_racks and LocationService._is_rack_location_code(location):
                    if location in occupied_locations:
                        continue

                matched.append(location)

            matched.sort(key=lambda value: (0, *LocationService._rack_sort_key(value)) if LocationService._is_rack_location_code(value) else (1, value))
            return matched[:safe_limit]

    @staticmethod
    def _normalize_location_code(value):
            return str(value or '').strip().upper().replace('_', '').replace('-', '').replace(' ', '')

    @staticmethod
    def _is_rack_location_code(value):
            return bool(re.match(r'^R0[1-9]\d{4}$', LocationService._normalize_location_code(value)))

    @staticmethod
    def _rack_sort_key(location_code):
            normalized = LocationService._normalize_location_code(location_code)
            match = re.match(r'^R(\d{2})(\d{2})(\d{2})$', normalized)
            if not match:
                return (999, 999, 999)
            return (int(match.group(1)), int(match.group(2)), int(match.group(3)))

    @staticmethod
    def _build_static_location_candidates():
            candidates = {
                'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02',
                'OSIP', 'BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'BFOS', 'PSD', 'PSD01',
                'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP',
                'R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07', 'R09',
                'MDO01', 'MD01',
            }

            # Standard rack map: R01-R07 - R04 has 6 places, R07 has 11 places x 4 rows, others have up to 10 places x 3 rows
            for rack_no in range(1, 8):
                rack_prefix = f"R{rack_no:02d}"
                max_places = 6 if rack_prefix == 'R04' else (11 if rack_prefix == 'R07' else 10)
                max_rows = 4 if rack_prefix == 'R07' else 3
                for place in range(1, max_places + 1):
                    for row in range(1, max_rows + 1):
                        candidates.add(f"{rack_prefix}{place:02d}{row:02d}")

            # Regał półkowy R09: 4 kolumny/rzędy x 6 poziomów/półek (R090101 - R090406)
            for place in range(1, 5):
                for row in range(1, 7):
                    candidates.add(f"R09{place:02d}{row:02d}")

            for idx in range(1, 78):
                candidates.add(f"OS{idx:02d}")

            for idx in (i for i in range(1, 25) if i not in (7, 8, 9, 10, 23, 24)):
                candidates.add(f"BB{idx:02d}")

            for idx in (7, 8, 9, 10, 23, 24):
                candidates.add(f"MZ{idx:02d}")

            for idx in range(1, 23):
                candidates.add(f"KO{idx:02d}")

            return candidates

    @staticmethod
    def _append_locations_from_query(cursor, query, params, target_set):
            try:
                cursor.execute(query, params)
                rows = cursor.fetchall()
            except Exception:
                return

            for row in rows:
                location = LocationService._normalize_location_code((row or {}).get('lokalizacja'))
                if location:
                    target_set.add(location)

    @staticmethod
    def _load_db_location_sets(linia='PSD'):
            normalized_line = str(linia or 'PSD').upper()
            all_locations = set()
            occupied_locations = set()

            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                table_sur = get_table_name('magazyn_surowce', normalized_line)
                table_opk = get_table_name('magazyn_opakowania', normalized_line)
                table_wg = get_table_name('magazyn_palety', normalized_line)

                all_queries = [
                    (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_sur} WHERE lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                    (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_opk} WHERE lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                    ("SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM magazyn_dodatki WHERE linia = %s AND lokalizacja IS NOT NULL AND lokalizacja <> ''", (normalized_line,)),
                    (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_wg} WHERE lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                ]

                occupied_queries = [
                    (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_sur} WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                    (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_opk} WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                    ("SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM magazyn_dodatki WHERE linia = %s AND stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''", (normalized_line,)),
                    (f"SELECT DISTINCT UPPER(lokalizacja) AS lokalizacja FROM {table_wg} WHERE waga_netto > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''", ()),
                ]

                for query, params in all_queries:
                    LocationService._append_locations_from_query(cursor, query, params, all_locations)

                for query, params in occupied_queries:
                    LocationService._append_locations_from_query(cursor, query, params, occupied_locations)
            finally:
                conn.close()

            return all_locations, occupied_locations

    @staticmethod
    def _derive_target_zone(location):
            normalized = LocationService._normalize_location_code(location)
            if not normalized:
                return ''

            for prefix in sorted(LocationService.OPEN_LOCATIONS_PREFIXES, key=len, reverse=True):
                if normalized.startswith(prefix):
                    return prefix

            if '_' in normalized:
                return normalized.split('_', 1)[0]
            if '-' in normalized:
                return normalized.split('-', 1)[0]

            match = re.match(r'^([A-Z]+\d{2})', normalized)
            if match:
                return match.group(1)

            return normalized[:4]
