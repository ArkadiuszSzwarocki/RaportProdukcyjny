"""
Serwis obliczania dynamicznego czasu trwania zmiany.
Zapewnia spójne wyliczanie czasu brutto i netto od startu zmiany (07:00) do momentu zamknięcia/raportu.
"""

from datetime import datetime, date, time
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ShiftTimeService:
    """Zarządza czasem trwania zmiany do momentu zamknięcia raportu."""

    DEFAULT_SHIFT_START_HOUR = 7
    DEFAULT_SHIFT_START_MINUTE = 0

    @classmethod
    def get_shift_time_range(cls, date_str: str, end_datetime: Optional[datetime] = None) -> Tuple[int, str, str]:
        """
        Zwraca: (czas_brutto_min, start_str, end_str).
        
        Args:
            date_str: 'YYYY-MM-DD'
            end_datetime: opcjonalny konkretny datetime zamknięcia (np. teraz)
        """
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            target_date = date.today()

        start_dt = datetime.combine(target_date, time(cls.DEFAULT_SHIFT_START_HOUR, cls.DEFAULT_SHIFT_START_MINUTE))
        today = date.today()

        # Sprawdź czy jest zaplanowana nowa godzina (odroczenie/wydłużenie I zmiany)
        sched_hour, sched_min = 15, 0
        try:
            from app.services.auto_report_service import AutoReportService
            sched = AutoReportService.get_schedule('AGRO', date_str)
            if sched and sched.get('scheduled_time'):
                parts = sched['scheduled_time'].split(':')
                sched_hour = int(parts[0])
                sched_min = int(parts[1]) if len(parts) > 1 else 0
        except Exception:
            pass

        if target_date == today:
            now_dt = end_datetime or datetime.now()
            if end_datetime:
                end_dt = end_datetime
            else:
                if now_dt < start_dt:
                    end_dt = datetime.combine(target_date, time(sched_hour, sched_min))
                else:
                    end_dt = now_dt
        else:
            end_dt = datetime.combine(target_date, time(sched_hour, sched_min))

        diff_seconds = max(60, int((end_dt - start_dt).total_seconds()))
        diff_minutes = max(1, diff_seconds // 60)

        start_str = start_dt.strftime('%H:%M')
        end_str = end_dt.strftime('%H:%M')

        return diff_minutes, start_str, end_str

    @classmethod
    def calculate_productivity(cls, mass_kg: float, awarie_min: int, date_str: str, end_datetime: Optional[datetime] = None) -> dict:
        """
        Oblicza dynamiczną wydajność efektywną (netto) i rzeczywistą (brutto).
        """
        brutto_min, start_str, end_str = cls.get_shift_time_range(date_str, end_datetime)
        netto_min = max(1, brutto_min - int(awarie_min or 0))

        m_kg = float(mass_kg or 0.0)
        wyd_efektywna = (m_kg / netto_min) * 60.0 if m_kg > 0 else 0.0
        wyd_rzeczywista = (m_kg / brutto_min) * 60.0 if m_kg > 0 else 0.0

        return {
            'brutto_min': brutto_min,
            'netto_min': netto_min,
            'awarie_min': int(awarie_min or 0),
            'start_str': start_str,
            'end_str': end_str,
            'wydajnosc_efektywna': round(wyd_efektywna, 1),
            'wydajnosc_rzeczywista': round(wyd_rzeczywista, 1),
        }
