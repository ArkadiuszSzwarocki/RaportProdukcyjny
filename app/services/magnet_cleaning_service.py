from datetime import date, datetime, timedelta
from typing import List, Dict
from app.repositories.magnet_cleaning_repository import MagnetCleaningRepository
from app.models.magnet_cleaning_record import MagnetCleaningRecord

class MagnetCleaningService:
    def __init__(self):
        self.repository = MagnetCleaningRepository()
        self.lines = ['EL01', 'EL02', 'PSD']

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
                # Tworzymy nowe, zaległe lub bieżące zadanie dla tego piątku
                new_record = MagnetCleaningRecord(
                    id=None,
                    linia=line,
                    data_planu=last_friday,
                    data_wykonania=None,
                    login_wykonawcy=None,
                    status='pending',
                    komentarz=None
                )
                self.repository.create(new_record)

    def get_pending_tasks(self) -> List[MagnetCleaningRecord]:
        """Zwraca wszystkie zaległe i obecne zadania do potwierdzenia (do wczoraj lub dzisiaj)."""
        self.initialize_weekly_cleanings() # Upewnijmy się, że na ten tydzień są utworzone
        return self.repository.get_pending_cleanings(max_date=date.today())

    def confirm_cleaning(self, record_id: int, user_login: str, komentarz: str = None) -> bool:
        """Potwierdza wyczyszczenie magnesu."""
        return self.repository.mark_as_completed(record_id, user_login, datetime.now(), komentarz)

    def get_cleaning_history(self, limit: int = 100) -> List[MagnetCleaningRecord]:
        """Zwraca historię logów (dla laborantów, adminów)."""
        return self.repository.get_all(limit)

    def record_adhoc_cleaning(self, linia: str, user_login: str, komentarz: str = None) -> int:
        """Dodaje i automatycznie potwierdza wpis czyszczenia wykonanego poza harmonogramem."""
        now = datetime.now()
        record = MagnetCleaningRecord(
            id=None,
            linia=linia,
            data_planu=now.date(),
            data_wykonania=now,
            login_wykonawcy=user_login,
            status='completed',
            komentarz=komentarz or 'Wykonane poza harmonogramem'
        )
        return self.repository.create(record)
