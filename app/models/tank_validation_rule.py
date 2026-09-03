from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TankValidationRule:
    """Domain model representing a validation rule for a production tank."""
    id: Optional[int] = None
    kod_zbiornika: str = ""
    nazwa_surowca: str = ""
    surowiec_id: Optional[int] = None
    opis: Optional[str] = None
    is_active: bool = True
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
