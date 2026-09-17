from typing import Tuple, List, Dict, Any
from app.services.magazyn_dostawy.commands.delivery_save_service import DeliverySaveService
from app.services.magazyn_dostawy.commands.delivery_cancellation_service import DeliveryCancellationService
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
from app.services.magazyn_dostawy.commands.draft_pallet_sync_service import DraftPalletSyncService
from app.services.magazyn_dostawy.commands.live_transfer_service import LiveTransferService


class DeliveryCommandService:
    """
    Facade maintaining backwards compatibility with all existing routes and callers.
    Delegates commands to specialized single-responsibility services.
    """

    @classmethod
    def save_dostawa(cls, data: Dict[str, Any], login: str = 'system') -> Tuple[bool, Any]:
        """Saves or updates delivery (PZ) and internal transfer (MM) orders."""
        return DeliverySaveService.save_dostawa(data, login)

    @classmethod
    def cancel_dostawa(cls, dostawa_id: str, login: str = 'system') -> Tuple[bool, str]:
        """Cancels a delivery or transfer order, unblocking reserved pallets."""
        return DeliveryCancellationService.cancel_dostawa(dostawa_id, login)

    @staticmethod
    def lock_draft_pallets(items: List[Dict[str, Any]], linia: str = 'AGRO', user_login: str = 'system') -> Tuple[bool, str]:
        """Locks pallets added to a draft transfer list."""
        return PalletLockManager.lock_draft_pallets(items, linia, user_login)

    @staticmethod
    def unlock_draft_pallets(items: List[Dict[str, Any]], linia: str = 'AGRO', user_login: str = 'system') -> Tuple[bool, str]:
        """Unlocks pallets removed from a draft transfer list."""
        return PalletLockManager.unlock_draft_pallets(items, linia, user_login)

    @staticmethod
    def sync_draft_pallets(items: List[Dict[str, Any]], linia: str = 'AGRO', user_login: str = 'system') -> Tuple[bool, Any]:
        """Refreshes draft item quantities, locations, and locks with current stock state."""
        return DraftPalletSyncService.sync_draft_pallets(items, linia, user_login)

    @staticmethod
    def init_live_transfer(linia: str = 'AGRO', order_ref: str = None, login: str = 'system') -> Tuple[bool, Any]:
        """Initializes a new open live transfer order in the database."""
        return LiveTransferService.init_live_transfer(linia, order_ref, login)

    @staticmethod
    def add_live_transfer_item(dostawa_id: str, item: Dict[str, Any], linia: str = 'AGRO', login: str = 'system') -> Tuple[bool, Any]:
        """Adds a single pallet to an active live transfer order and locks it."""
        return LiveTransferService.add_live_transfer_item(dostawa_id, item, linia, login)

    @staticmethod
    def remove_live_transfer_item(dostawa_id: str, item_id: str = None, nr_palety: str = None, linia: str = 'AGRO', login: str = 'system') -> Tuple[bool, Any]:
        """Removes a pallet from an active live transfer order and unblocks it."""
        return LiveTransferService.remove_live_transfer_item(dostawa_id, item_id, nr_palety, linia, login)

    @staticmethod
    def close_live_transfer(dostawa_id: str, login: str = 'system') -> Tuple[bool, str]:
        """Closes an active live transfer order and marks status as COMPLETED."""
        return LiveTransferService.close_live_transfer(dostawa_id, login)
