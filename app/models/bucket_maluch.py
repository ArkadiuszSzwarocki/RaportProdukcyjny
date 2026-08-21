from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class BucketItem:
    id: Optional[int] = None
    wiaderko_id: Optional[int] = None
    stacja_kod: str = ""
    surowiec_nazwa: str = ""
    waga_faktyczna: float = 0.0
    data_nawazenia: Optional[datetime] = None
    operator_login: Optional[str] = None


@dataclass
class BucketMaluch:
    id: Optional[int] = None
    kod_wiadra: str = ""
    nr_sscc: Optional[str] = None
    plan_id: int = 0
    linia: str = "PSD"
    status: str = "w_trakcie_nawazania"  # 'w_trakcie_nawazania', 'skompletowane', 'wrzucone_do_mieszalnika', 'anulowane'
    waga_calkowita: float = 0.0
    operator_nawazyl_login: Optional[str] = None
    operator_zasypal_login: Optional[str] = None
    szarza_id: Optional[int] = None
    mieszalnik_kod: str = "MI01"
    data_produkcji: Optional[datetime] = None
    data_przydatnosci: Optional[datetime] = None
    data_rozpoczecia: Optional[datetime] = None
    data_skompletowania: Optional[datetime] = None
    data_zasypania: Optional[datetime] = None
    created_at: Optional[datetime] = None
    pozycje: List[BucketItem] = field(default_factory=list)
