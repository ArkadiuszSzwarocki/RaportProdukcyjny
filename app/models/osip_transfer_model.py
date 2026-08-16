"""
Model reprezentujący zlecenie transferu wewnętrznego pomiędzy magazynami (np. Centrala <-> OSIP).
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from app.models.osip_transfer_item_model import OsipTransferItemModel


@dataclass
class OsipTransferModel:
    id: Optional[int] = None
    transfer_code: str = ""
    source_warehouse: str = "MS01"
    destination_warehouse: str = "OSIP"
    status: str = "PLANNED"  # PLANNED, IN_TRANSIT, COMPLETED, CANCELLED
    created_by: str = ""
    dispatched_by: Optional[str] = None
    completed_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    items: List[OsipTransferItemModel] = field(default_factory=list)

    def is_planned(self) -> bool:
        return self.status == "PLANNED"

    def is_in_transit(self) -> bool:
        return self.status == "IN_TRANSIT"

    def is_completed(self) -> bool:
        return self.status == "COMPLETED"

    def is_cancelled(self) -> bool:
        return self.status == "CANCELLED"
