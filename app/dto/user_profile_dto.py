"""
DTO (Data Transfer Object) dla profilu użytkownika.
"""
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class UserProfileDTO:
    user_id: int
    login: str
    imie_nazwisko: str
    rola: str
    grupa: str
    email: str
    pracownik_id: Optional[int]
    urlop_biezacy: int
    urlop_zalegly: int
    urlop_wykorzystany: int
    urlop_laczny: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserProfileUpdateDTO:
    email: Optional[str] = None
    urlop_biezacy: Optional[int] = None
    urlop_zalegly: Optional[int] = None
    imie_nazwisko: Optional[str] = None
