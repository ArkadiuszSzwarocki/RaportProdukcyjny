"""
Warehouse 3D Data Transfer Objects (DTO).
Encapsulates structured data for warehouse rack configurations, slots, and 3D pallet representations.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class PalletPayload3dDTO:
    id: int
    display_id: str
    product_name: str
    pallet_type: str        # 'surowiec', 'opakowanie', 'dodatek', 'wyrób gotowy'
    packaging_type: str     # 'BIG_BAG', 'BAGS', 'WRAPPED_PALLET', 'BOXES'
    amount: float
    unit: str
    location: str
    batch: str
    date_prod: str
    date_exp: str
    date_added: str
    is_blocked: bool
    block_reason: Optional[str] = None
    linia: str = 'PSD'
    is_first_fifo: bool = False
    fifo_rank: Optional[int] = None
    is_expired: bool = False
    is_expiring_soon: bool = False
    days_to_exp: Optional[int] = None
    exp_status_label: Optional[str] = None
    exp_status_color: Optional[str] = None

@dataclass
class RackSlot3dDTO:
    location_code: str      # e.g. 'R010302'
    rack_id: str            # e.g. 'R01'
    column: int             # 1-indexed bay/column (X position)
    level: int              # 1-indexed shelf level (Y position)
    is_occupied: bool
    is_blocked: bool
    pallets: List[PalletPayload3dDTO] = field(default_factory=list)
    primary_payload_type: str = 'EMPTY' # 'BIG_BAG', 'BAGS', 'WRAPPED_PALLET', 'EMPTY'

@dataclass
class RackStructure3dDTO:
    rack_id: str            # e.g. 'R01'
    name: str               # e.g. 'Regał R01 (Wysokiego Składowania)'
    rack_type: str          # 'HIGH_BAY', 'SHELVING', 'FLOOR_BUFFER'
    columns_count: int      # e.g. 10
    levels_count: int       # e.g. 3
    depth_m: float          # e.g. 1.25
    bay_width_m: float      # e.g. 1.40
    level_height_m: float   # e.g. 1.65
    position_x: float       # Global X in 3D warehouse coordinate space
    position_z: float       # Global Z in 3D warehouse coordinate space
    slots: Dict[str, RackSlot3dDTO] = field(default_factory=dict)
    total_slots: int = 0
    occupied_slots: int = 0
    blocked_slots: int = 0
    occupancy_percent: float = 0.0

@dataclass
class Warehouse3dStateDTO:
    linia: str
    timestamp: str
    racks: List[RackStructure3dDTO] = field(default_factory=list)
    total_slots_count: int = 0
    total_occupied_count: int = 0
    total_blocked_count: int = 0
    total_big_bags_count: int = 0
    total_bags_count: int = 0
    total_fifo_count: int = 0
    total_expiring_count: int = 0
    total_expired_count: int = 0
    global_occupancy_percent: float = 0.0
