"""Putaway location suggestion service.

Suggests optimal warehouse location for incoming pallets based on the selected algorithm.
Currently supports MANUAL mode. Extendable to NEAREST_EMPTY and ABC_ROTATION.
"""

from typing import Tuple, Optional, List, Dict, Any
from app.db import get_db_connection, get_table_name


class PutawaySuggestionService:
    """Generates putaway location suggestions for delivery pallets."""

    @staticmethod
    def suggest_location(
        item: Dict[str, Any],
        linia: str,
        algorithm: str = 'MANUAL'
    ) -> Optional[str]:
        """Return a suggested location string or None for manual assignment.

        Args:
            item: Pallet item dict from magazyn_dostawy.items JSON.
            linia: Warehouse line (PSD/AGRO).
            algorithm: Putaway strategy — MANUAL, NEAREST_EMPTY, ABC_ROTATION.

        Returns:
            Suggested location code or None if manual.
        """
        if algorithm == 'MANUAL':
            return None

        if algorithm == 'NEAREST_EMPTY':
            return PutawaySuggestionService._find_nearest_empty(item, linia)

        return None

    @staticmethod
    def _find_nearest_empty(item: Dict[str, Any], linia: str) -> Optional[str]:
        """Find the nearest empty rack slot from the allowed locations dictionary.

        Checks magazyn_dozwolone_lokalizacje for all prefixes, then scans
        inventory tables for unoccupied slots matching those prefixes.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT nazwa FROM magazyn_dozwolone_lokalizacje ORDER BY nazwa")
            allowed_prefixes = [row['nazwa'] for row in cursor.fetchall()]

            if not allowed_prefixes:
                return None

            table_sur = get_table_name('magazyn_surowce', linia)
            table_opk = get_table_name('magazyn_opakowania', linia)

            cursor.execute(f"""
                SELECT lokalizacja FROM {table_sur}
                WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja != ''
                UNION
                SELECT lokalizacja FROM {table_opk}
                WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja != ''
                UNION
                SELECT lokalizacja FROM magazyn_dodatki
                WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja != ''
            """)
            occupied = {row['lokalizacja'].upper() for row in cursor.fetchall()}

            # Rack-style locations: R + row(2) + col(2) + level(2) e.g. R010101
            import re
            for prefix in allowed_prefixes:
                prefix_upper = prefix.upper().strip()
                if not re.match(r'^R\d{2}', prefix_upper):
                    continue
                # Generate candidate slots under this prefix
                for col in range(1, 100):
                    for level in range(1, 6):
                        candidate = f"{prefix_upper}{str(col).zfill(2)}{str(level).zfill(2)}"
                        if candidate not in occupied:
                            return candidate

            return None
        except Exception:
            return None
        finally:
            conn.close()

    @staticmethod
    def validate_putaway_location(
        location: str,
        suggested_location: Optional[str],
        strict_mode: bool = False
    ) -> Tuple[bool, str]:
        """Validate the scanned putaway location against the suggestion.

        Args:
            location: Actually scanned location code.
            suggested_location: System-suggested location (if any).
            strict_mode: If True, mismatch causes rejection. If False, just a warning.

        Returns:
            Tuple of (is_valid, warning_message).
        """
        if not suggested_location:
            return True, ''

        if location.upper().strip() == suggested_location.upper().strip():
            return True, ''

        if strict_mode:
            return False, f"Lokalizacja '{location}' nie zgadza się z sugerowaną '{suggested_location}'. Strict mode aktywny."

        return True, f"Uwaga: paleta postawiona na '{location}' zamiast sugerowanej '{suggested_location}'."
