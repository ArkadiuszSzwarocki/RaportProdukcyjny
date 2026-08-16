"""
Model reprezentujący pojedynczą pozycję w zleceniu transferu OSIP.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class OsipTransferItemModel:
    id: Optional[int] = None
    transfer_id: Optional[int] = None
    pallet_id: Optional[int] = None
    nr_palety: Optional[str] = None
    product_name: str = ""
    item_type: str = "raw"  # raw lub fg
    requested_qty: float = 0.0
    loaded_qty: float = 0.0
    unit: str = "kg"
    status: str = "PLANNED"  # PLANNED, LOADED, RECEIVED, CANCELLED
    created_at: Optional[datetime] = None
