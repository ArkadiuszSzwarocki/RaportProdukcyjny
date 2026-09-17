import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from app.utils.pallet_label import is_packaging_item


class ScannerItemNormalizer:
    """Normalizes database row into a unified dictionary format for the scanner frontend."""

    @staticmethod
    def normalize_lookup_item(
        row: dict,
        *,
        inventory_type: str,
        inventory_key: str,
        code_prefix: str,
        can_dispatch: bool,
        can_split: bool,
        can_print_label: bool,
        location_fallback: str = '',
    ) -> dict:
        qty = float(row.get('ilosc', row.get('stan_magazynowy', 0)) or 0)
        is_used_up = qty <= 0
        raw_location = str(row.get('lokalizacja') or location_fallback or '').strip().upper()
        location = f"ZUZYTA (ostatnio: {raw_location})" if (is_used_up and raw_location and not raw_location.startswith('ZUZY')) else raw_location

        dp = row.get('data_produkcji')
        dp_str = dp.strftime('%Y-%m-%d') if hasattr(dp, 'strftime') else (str(dp) if dp else '')

        dz = row.get('data_przydatnosci')
        dz_str = ''
        if dz:
            if hasattr(dz, 'strftime'):
                dz_str = dz.strftime('%Y-%m-%d')
            else:
                dz_str = str(dz).strip()
                match = re.search(r'^(\d+)\s*mies', dz_str, re.IGNORECASE)
                if match and dp:
                    try:
                        months = int(match.group(1))
                        dp_date = dp if hasattr(dp, 'strftime') else datetime.strptime(dp_str, '%Y-%m-%d').date()
                        dz_str = (dp_date + relativedelta(months=months)).strftime('%Y-%m-%d')
                    except Exception:
                        pass

        is_pkg = (inventory_type == 'Opakowanie') or is_packaging_item(
            row.get('nazwa'),
            unit=row.get('jednostka') or row.get('unit'),
            typ=row.get('typ') or row.get('typ_opakowania'),
            pallet_nr=row.get('nr_palety'),
        )
        unit_str = 'szt.' if is_pkg else (row.get('jednostka') or row.get('unit') or 'kg')

        return {
            'id': row['id'],
            'nazwa': row.get('nazwa') or '',
            'stan_magazynowy': qty,
            'lokalizacja': location,
            'nr_palety': row.get('nr_palety') or f"{code_prefix}-{row['id']}",
            'nr_partii': row.get('nr_partii', ''),
            'data_produkcji': dp_str,
            'data_przydatnosci': dz_str,
            'inventory_type': inventory_type,
            'inventory_key': inventory_key,
            'inventory_code': f"{code_prefix}-{row['id']}",
            'is_used_up': is_used_up,
            'status_pl': 'Zużyta / Rozchodowana' if is_used_up else inventory_type,
            'used_up_info': f"Pozycja posiada stan 0 {unit_str} (ostatnia znana lokalizacja: {raw_location})" if is_used_up else '',
            'can_dispatch': bool(can_dispatch) and not is_used_up,
            'can_split': bool(can_split) and not is_used_up,
            'can_print_label': bool(can_print_label),
            'unit': unit_str,
            'jednostka': unit_str,
            'is_pkg': is_pkg,
        }

    @staticmethod
    def normalize_pallet(row: dict) -> dict:
        return ScannerItemNormalizer.normalize_lookup_item(
            row,
            inventory_type='Wyrób Gotowy',
            inventory_key='WYROB_GOTOWY',
            code_prefix='PAL',
            can_dispatch=False,
            can_split=False,
            can_print_label=False,
            location_fallback='MGW01',
        )


# Backward compatibility module functions
normalize_lookup_item = ScannerItemNormalizer.normalize_lookup_item
normalize_pallet = ScannerItemNormalizer.normalize_pallet
