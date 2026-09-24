import re
from datetime import datetime
from typing import Tuple, List, Dict, Any
from app.utils.location_validator import validate_warehouse_location, validate_centrala_osip_move

KNOWN_SOURCE_LOCATIONS = {
    'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02',
    'OSIP', 'BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'BFOS', 'PSD', 'PSD01',
    'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP', 'W_TRANZYCIE', 'OCZEKUJĄCE', 'OCZEKUJACE', 'OCZEKUJE',
}
KNOWN_SOURCE_LOCATIONS.update({f'KO{i:02d}' for i in range(1, 23)})
KNOWN_TARGET_LOCATIONS = {'BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'BFOS', 'MS01', 'MP01', 'PSD01'}


def norm_loc(value: Any) -> str:
    return str(value or '').strip().upper()


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on', 'tak')


def is_route_conflict(source_loc: str, target_loc: str) -> bool:
    source = norm_loc(source_loc)
    target = norm_loc(target_loc)
    if not source or not target:
        return False
    if source in {'OCZEKUJĄCE', 'OCZEKUJACE', 'OCZEKUJE'} and target not in {'OCZEKUJĄCE', 'OCZEKUJACE', 'OCZEKUJE'}:
        return False
    if source == target:
        return True
    return source.startswith(target) or target.startswith(source)


def is_known_source_location(value: Any) -> bool:
    loc = norm_loc(value)
    if not loc:
        return False

    clean_loc = loc.replace('_', '').replace('-', '').replace(' ', '')
    if clean_loc in {'BFMS01', 'BFMP01', 'BFOS', 'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02', 'OSIP', 'PSD', 'PSD01', 'RAMPA', 'MIX01', 'WTRANZYCIEOSIP', 'WTRANZYCIE', 'OCZEKUJACE', 'OCZEKUJĄCE', 'OCZEKUJE'}:
        return True

    if loc in KNOWN_SOURCE_LOCATIONS:
        return True

    if re.match(r'^R0([1-7])(\d{2})(\d{2})$', loc):
        return True

    osip_match = re.match(r'^OS(\d{2})$', loc)
    if osip_match:
        return 1 <= int(osip_match.group(1)) <= 77

    bb_match = re.match(r'^BB(\d{2})$', loc)
    if bb_match:
        nr = int(bb_match.group(1))
        return (1 <= nr <= 24) and (nr not in (7, 8, 9, 10, 23, 24))

    mz_simple = re.match(r'^MZ(\d{2})$', loc)
    if mz_simple:
        return int(mz_simple.group(1)) in (7, 8, 9, 10, 23, 24)

    ko_match = re.match(r'^KO(\d{2})$', loc)
    if ko_match:
        return 1 <= int(ko_match.group(1)) <= 22

    return loc.startswith(('MD', 'MDO', 'BF'))


class DeliveryOrderValidator:
    """Validates delivery and transfer payloads before DB persistence."""

    @classmethod
    def validate(cls, data: Dict[str, Any], items: List[Dict[str, Any]], is_external: bool, lokalizacja_do: str, source_locations: List[str], global_skip_lookup: bool) -> Tuple[bool, str]:
        # Validate target location is not a production tank
        if lokalizacja_do and not is_external:
            is_valid, error_msg = validate_warehouse_location(lokalizacja_do, allow_empty=False)
            if not is_valid:
                return False, error_msg

        # Validate source locations
        for source_loc in source_locations:
            is_valid, error_msg = validate_warehouse_location(source_loc, allow_empty=False)
            if not is_valid:
                return False, f"Błąd w lokalizacji źródłowej: {error_msg}"

        unknown_sources = sorted([loc for loc in source_locations if not is_known_source_location(loc)])
        if unknown_sources and not global_skip_lookup:
            preview = ', '.join(unknown_sources[:5])
            suffix = ', ...' if len(unknown_sources) > 5 else ''
            return False, f"Nieznane lokalizacje źródłowe: {preview}{suffix}."

        if lokalizacja_do and lokalizacja_do not in KNOWN_TARGET_LOCATIONS and lokalizacja_do != 'OCZEKUJĄCE':
            return False, f"Nieznana lokalizacja docelowa: {lokalizacja_do}."

        unaccepted_sources = sorted({
            norm_loc(it.get('sourceSpot'))
            for it in items
            if norm_loc(it.get('sourceSpot')) and not it.get('accepted')
        })

        if lokalizacja_do and any(is_route_conflict(loc, lokalizacja_do) for loc in unaccepted_sources):
            return False, f"Operacja niemożliwa: Skąd i Dokąd nie mogą być takie same ({lokalizacja_do})."

        # Check Centrala <-> OSIP route validation
        if not is_external and lokalizacja_do and lokalizacja_do != 'OCZEKUJĄCE':
            for it in items:
                src_spot = norm_loc(it.get('sourceSpot'))
                pal_no = it.get('palletNo') or it.get('nr_palety')
                if src_spot and src_spot != lokalizacja_do:
                    is_trf_valid, trf_err = validate_centrala_osip_move(
                        source_location=src_spot,
                        target_location=lokalizacja_do,
                        nr_palety=pal_no
                    )
                    if not is_trf_valid:
                        return False, trf_err

        # Validate item dates
        today_date = datetime.now().strftime('%Y-%m-%d')
        for idx, it in enumerate(items):
            prod_date = str(it.get('data_produkcji') or '').strip()
            expiry_date = str(it.get('data_przydatnosci') or '').strip()

            if prod_date and prod_date > today_date:
                return False, f"Pozycja {idx + 1}: Data produkcji ({prod_date}) jest późniejsza niż dzisiejsza data ({today_date})."

            if prod_date and expiry_date and expiry_date < prod_date:
                return False, f"Pozycja {idx + 1}: Data przydatności ({expiry_date}) jest wcześniejsza niż data produkcji ({prod_date})."

        return True, ""
