"""
Warehouse V2 Service Facade.
Provides a unified, backward-compatible API delegating to focused domain services.
"""

from app.services.warehouse_v2.pallet_history_service import PalletHistoryService
from app.services.warehouse_v2.pallet_relocation_service import PalletRelocationService
from app.services.warehouse_v2.pallet_status_service import PalletStatusService
from app.services.warehouse_v2.pallet_modification_service import PalletModificationService
from app.services.warehouse_v2.pallet_material_service import PalletMaterialService
from app.services.warehouse_v2.pallet_restore_service import PalletRestoreService

class WarehouseV2Service:
    """Facade for Warehouse V2 operations."""

    @staticmethod
    def get_pallet_history(pallet_id, pallet_type, linia='PSD', sscc=None):
        """Fetch comprehensive pallet movement and lifecycle history."""
        return PalletHistoryService.get_pallet_history(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            linia=linia,
            sscc=sscc
        )

    @staticmethod
    def move_pallet(pallet_id, pallet_type, new_location, worker_login, linia='PSD', amount_to_move=None):
        """Relocate pallet or perform split/partial movement."""
        return PalletRelocationService.move_pallet(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            new_location=new_location,
            worker_login=worker_login,
            linia=linia,
            amount_to_move=amount_to_move
        )

    @staticmethod
    def toggle_block(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Toggle pallet quality/warehouse block."""
        return PalletStatusService.toggle_block(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            worker_login=worker_login,
            linia=linia
        )

    @staticmethod
    def dispatch_pallet(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Dispatch pallet to EXPEDITION and archive."""
        return PalletStatusService.dispatch_pallet(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            worker_login=worker_login,
            linia=linia
        )

    @staticmethod
    def archive_pallet(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Archive pallet from active inventory."""
        return PalletStatusService.archive_pallet(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            worker_login=worker_login,
            linia=linia
        )

    @staticmethod
    def rename_pallet(pallet_id, pallet_type, new_name, worker_login, linia='PSD'):
        """Rename product on a pallet."""
        return PalletModificationService.rename_pallet(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            new_name=new_name,
            worker_login=worker_login,
            linia=linia
        )

    @staticmethod
    def update_weight(pallet_id, pallet_type, new_weight, worker_login, linia='PSD'):
        """Update pallet weight/quantity."""
        return PalletModificationService.update_weight(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            new_weight=new_weight,
            worker_login=worker_login,
            linia=linia
        )

    @staticmethod
    def return_pallet_to_raw(pallet_id, pallet_type, worker_login, linia='PSD'):
        """Return finished good to raw materials buffer."""
        return PalletModificationService.return_pallet_to_raw(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            worker_login=worker_login,
            linia=linia
        )

    @staticmethod
    def update_packaging_type(pallet_id, pallet_type, new_packaging_type, worker_login, linia='PSD'):
        """Update packaging type descriptor."""
        return PalletMaterialService.update_packaging_type(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            new_packaging_type=new_packaging_type,
            worker_login=worker_login,
            linia=linia
        )

    @staticmethod
    def update_material_type(pallet_id, pallet_type, new_material_type, worker_login, linia='PSD'):
        """Update material type category."""
        return PalletMaterialService.update_material_type(
            pallet_id=pallet_id,
            pallet_type=pallet_type,
            new_material_type=new_material_type,
            worker_login=worker_login,
            linia=linia
        )

    @staticmethod
    def bulk_update_material_type(pallet_ids: list, pallet_type: str, new_material_type: str, worker_login: str, linia: str = 'PSD') -> tuple[bool, str, int]:
        """Bulk update material types for multiple pallets."""
        return PalletMaterialService.bulk_update_material_type(
            pallet_ids=pallet_ids,
            pallet_type=pallet_type,
            new_material_type=new_material_type,
            worker_login=worker_login,
            linia=linia
        )

    @staticmethod
    def restore_pallet_from_archive(archive_id: int = None, nr_palety: str = None, new_weight: float = None, new_location: str = None, user_login: str = 'admin') -> tuple[bool, str, dict]:
        """Restore pallet from archive back to active stock."""
        return PalletRestoreService.restore_pallet_from_archive(
            archive_id=archive_id,
            nr_palety=nr_palety,
            new_weight=new_weight,
            new_location=new_location,
            user_login=user_login
        )
