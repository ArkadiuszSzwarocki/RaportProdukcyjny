"""DTO representing an available warehouse pallet for production station feeding."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StationWarehousePallet:
    """Represents a pallet of raw material available in warehouse locations."""
    id: int
    nr_palety: str
    nazwa: str
    stan_magazynowy: float
    lokalizacja: str
    nr_partii: str = ""
    data_produkcji: str = ""
    data_przydatnosci: str = ""
    typ: str = "Surowiec"
    jednostka: str = "kg"
