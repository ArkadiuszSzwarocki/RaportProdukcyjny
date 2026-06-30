from datetime import date, datetime, timedelta
from typing import List
from app.repositories.separator_cleaning_repository import SeparatorCleaningRepository
from app.models.separator_cleaning_record import SeparatorCleaningRecord

class SeparatorCleaningService:
    def __init__(self):
        self.repository = SeparatorCleaningRepository()
        self.lines = ['SE01', 'SEPSD']

    def _get_last_friday(self, reference_date: date) -> date:
        """Zwraca datę ostatniego piątku (włączając dzisiejszy dzień, jeśli jest piątkiem)."""
        offset = (reference_date.weekday() - 4) % 7
        return reference_date - timedelta(days=offset)

    def initialize_weekly_cleanings(self) -> None:
        """Sprawdza i ewentualnie inicjalizuje wpisy do czyszczenia na najbliższy wymagany termin."""
        today = date.today()
        last_friday = self._get_last_friday(today)

        for line in self.lines:
            existing = self.repository.get_by_date_and_line(last_friday, line)
            if not existing:
                new_record = SeparatorCleaningRecord(
                    id=None,
                    linia=line,
                    data_planu=last_friday,
                    data_wykonania=None,
                    login_wykonawcy=None,
                    status='pending',
                    komentarz=None
                )
                self.repository.create(new_record)

    def get_pending_tasks(self) -> List[SeparatorCleaningRecord]:
        """Zwraca wszystkie zaległe i obecne zadania do potwierdzenia."""
        self.initialize_weekly_cleanings()
        return self.repository.get_pending_cleanings(max_date=date.today())

    def confirm_cleaning(self, record_id: int, user_login: str, komentarz: str = None) -> bool:
        """Potwierdza wyczyszczenie separatora."""
        return self.repository.mark_as_completed(record_id, user_login, datetime.now(), komentarz)

    def get_cleaning_history(self, limit: int = 100) -> List[SeparatorCleaningRecord]:
        """Zwraca historię czyszczenia separatorów."""
        return self.repository.get_all(limit)

    def record_adhoc_cleaning(self, linia: str, user_login: str, komentarz: str = None) -> int:
        """Dodaje i automatycznie potwierdza wpis czyszczenia wykonanego poza harmonogramem."""
        now = datetime.now()
        record = SeparatorCleaningRecord(
            id=None,
            linia=linia,
            data_planu=now.date(),
            data_wykonania=now,
            login_wykonawcy=user_login,
            status='completed',
            komentarz=komentarz or 'Wykonane poza harmonogramem'
        )
        return self.repository.create(record)
