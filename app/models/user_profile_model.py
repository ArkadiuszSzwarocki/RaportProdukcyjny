"""
Model reprezentujący profil użytkownika w systemie.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class UserProfileModel:
    user_id: int
    login: str
    imie_nazwisko: str
    rola: str
    grupa: str
    email: str = ""
    pracownik_id: Optional[int] = None
    urlop_biezacy: int = 0
    urlop_zalegly: int = 0
    urlop_wykorzystany: int = 0
