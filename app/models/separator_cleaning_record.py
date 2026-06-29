from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

@dataclass
class SeparatorCleaningRecord:
    id: Optional[int]
    linia: str
    data_planu: date
    data_wykonania: Optional[datetime]
    login_wykonawcy: Optional[str]
    status: str
    komentarz: Optional[str]
    created_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data.get('id'),
            linia=data.get('linia'),
            data_planu=data.get('data_planu'),
            data_wykonania=data.get('data_wykonania'),
            login_wykonawcy=data.get('login_wykonawcy'),
            status=data.get('status', 'pending'),
            komentarz=data.get('komentarz'),
            created_at=data.get('created_at')
        )
