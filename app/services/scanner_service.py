"""ScannerService facade maintaining full backward compatibility.
Clean Architecture facade delegating to focused domain services.
"""
from __future__ import annotations

from app.services.scanner.scanner_code_normalizer import ScannerCodeNormalizer
from app.services.scanner.scanner_item_normalizer import ScannerItemNormalizer
from app.services.scanner.scanner_lookup_service import ScannerLookupService
from app.services.scanner.scanner_location_query_service import ScannerLocationQueryService
from app.services.scanner.scanner_resolution_service import ScannerResolutionService
from app.services.scanner.scanner_movement_service import ScannerMovementService
from app.services.scanner.scanner_label_service import ScannerLabelService
from app.db import get_db_connection, get_table_name

__all__ = ["ScannerService", "get_db_connection", "get_table_name"]


class ScannerService:
    """Facade for warehouse scanner operations."""

    SCAN_TOKEN_PATTERN = ScannerCodeNormalizer.SCAN_TOKEN_PATTERN

    # Static normalizer delegates
    @staticmethod
    def _normalize_scanned_code(raw_code: str) -> str:
        return ScannerCodeNormalizer.normalize_scanned_code(raw_code)

    @staticmethod
    def _extract_prefixed_id(code: str) -> tuple[str | None, int | None]:
        return ScannerCodeNormalizer.extract_prefixed_id(code)

    @staticmethod
    def _is_sscc_code(code: str) -> bool:
        return ScannerCodeNormalizer.is_sscc_code(code)

    # Query & Lookup delegates
    @staticmethod
    def _get_active_production_qty(cur, surowiec_id: int, linia: str) -> tuple[float, str]:
        return ScannerLookupService.get_active_production_qty(cur, surowiec_id, linia)

    @staticmethod
    def _lookup_inventory_row(cur, base_table: str, linia: str, **kwargs) -> dict | None:
        return ScannerLookupService.lookup_inventory_row(cur, base_table, linia, **kwargs)

    @staticmethod
    def _lookup_finished_goods(cur, linia: str, **kwargs) -> dict | None:
        return ScannerLookupService.lookup_finished_goods(cur, linia, **kwargs)

    @staticmethod
    def _check_active_transfer_for_code(code: str):
        return ScannerLookupService.check_active_transfer_for_code(code)

    @staticmethod
    def _lookup_by_location_internal(location_code: str, linia: str) -> list[dict]:
        return ScannerLocationQueryService.lookup_by_location_internal(location_code, linia)

    @staticmethod
    def lookup_by_location(location_code: str, linia: str = 'Agro', try_all_lines: bool = True) -> dict | None:
        return ScannerResolutionService.lookup_by_location(location_code, linia, try_all_lines)

    @staticmethod
    def lookup_scanned_code(scanned_code: str, linia: str = 'Agro') -> dict | None:
        """Alias resolving scanned barcode or SSCC."""
        return ScannerResolutionService.lookup_by_location(scanned_code, linia=linia)

    # Movement & Dispatch delegates
    @staticmethod
    def dispatch_to_production(
        surowiec_id: int,
        ilosc: float,
        worker_login: str,
        linia: str = 'Agro',
        plan_id: int | None = None,
        zbiornik: str | None = None,
        komentarz: str | None = None,
        pallet_type: str = 'Surowiec',
    ) -> tuple[bool, str, dict | None]:
        return ScannerMovementService.dispatch_to_production(
            surowiec_id=surowiec_id,
            ilosc=ilosc,
            worker_login=worker_login,
            linia=linia,
            plan_id=plan_id,
            zbiornik=zbiornik,
            komentarz=komentarz,
            pallet_type=pallet_type,
        )

    @staticmethod
    def move_pallet(
        surowiec_id: int,
        nowa_lokalizacja: str,
        worker_login: str,
        linia: str = 'Agro',
        pallet_type: str = 'Surowiec',
    ) -> tuple[bool, str]:
        return ScannerMovementService.move_pallet(
            surowiec_id=surowiec_id,
            nowa_lokalizacja=nowa_lokalizacja,
            worker_login=worker_login,
            linia=linia,
            pallet_type=pallet_type,
        )

    # Label data delegates
    @staticmethod
    def get_label_data(identifier: str | int, linia: str = 'Agro', pallet_type: str | None = None) -> dict | None:
        return ScannerLabelService.get_label_data(identifier, linia, pallet_type)
