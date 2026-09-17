"""
Moduł odpowiedzialny za sprawdzanie obecności danych produkcyjnych oraz detekcję aktywności popołudniowej (po I zmianie).
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from app.core.database import get_db_connection, get_table_name
from app.repositories.downtime_repository import DowntimeRepository
from app.services.auto_report.auto_report_schedule_service import AutoReportScheduleService

logger = logging.getLogger(__name__)


class AutoReportActivityDetector:
    @classmethod
    def has_report_data(cls, linia: str = 'AGRO', date_str: Optional[str] = None) -> bool:
        """
        Weryfikuje, czy raport dla danej linii i daty zawiera jakiekolwiek dane produkcyjne, awarie lub notatki.
        Zwraca False, gdy w danym dniu nie rejestrowano żadnej produkcji ani zdarzeń dla tej linii.
        """
        if not date_str:
            date_str = str(date.today())

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', linia)
            table_szarze = 'szarze_agro' if linia == 'AGRO' else 'szarze'
            table_dosypki = 'dosypki_agro' if linia == 'AGRO' else 'dosypki'
            table_palety = get_table_name('palety_workowanie', linia)

            # 1. Sprawdź wytworzone szarże zasypu
            cursor.execute(f"SELECT id FROM {table_szarze} WHERE DATE(data_dodania) = %s LIMIT 1", (date_str,))
            if cursor.fetchone():
                cursor.close()
                return True

            # 2. Sprawdź spakowane palety workowania
            cursor.execute(
                f"SELECT id FROM {table_palety} WHERE DATE(data_dodania) = %s OR DATE(data_potwierdzenia) = %s LIMIT 1",
                (date_str, date_str)
            )
            if cursor.fetchone():
                cursor.close()
                return True

            # 3. Sprawdź potwierdzone dosypki
            cursor.execute(
                f"SELECT id FROM {table_dosypki} WHERE (DATE(data_dodania) = %s OR DATE(data_potwierdzenia) = %s) AND (anulowana = 0 OR anulowana IS NULL) LIMIT 1",
                (date_str, date_str)
            )
            if cursor.fetchone():
                cursor.close()
                return True

            # 4. Sprawdź zlecenia w planie (rozpoczęte/zakończone dzisiaj LUB zaplanowane z tonażem)
            cursor.execute(
                f"""SELECT id FROM {table_plan} 
                    WHERE ((data_planu = %s AND tonaz > 0)
                       OR DATE(real_start) = %s 
                       OR DATE(real_stop) = %s
                       OR (data_planu = %s AND tonaz_rzeczywisty > 0))
                       AND is_deleted = 0
                    LIMIT 1
                """,
                (date_str, date_str, date_str, date_str)
            )
            if cursor.fetchone():
                cursor.close()
                return True

            cursor.close()

            # 5. Sprawdź przestoje i awarie
            downtimes = DowntimeRepository().get_downtimes(linia, date_str, date_str)
            if downtimes and len(downtimes) > 0:
                return True

            # 6. Sprawdź notatki zmianowe lidera
            from app.services.shift_close_service import _load_shift_notes
            notes = _load_shift_notes(date_str, linia=linia)
            if notes and str(notes).strip():
                return True

            return False
        except Exception as e:
            logger.error("[AUTO_REPORT_DETECTOR] Błąd sprawdzania czy raport posiada dane: %s", e)
            return True
        finally:
            if conn:
                conn.close()

    @classmethod
    def has_activity_after_1500(cls, linia: str = 'AGRO', date_str: Optional[str] = None) -> bool:
        """
        Sprawdza czy zarejestrowano aktywność po zakończeniu I zmiany.
        Wyznacznikiem końca I zmiany jest zaplanowana/odroczona godzina (scheduled_time, np. 15:45, 16:30 lub domyślnie 15:00).
        """
        if not date_str:
            date_str = str(date.today())

        sched = AutoReportScheduleService.get_schedule(linia, date_str)
        cutoff_time_str = f"{sched.get('scheduled_time', '15:00')}:00" if sched else '15:00:00'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', linia)
            table_palety = get_table_name('palety_workowanie', linia)

            # 1. Sprawdź palety po godzinie granicznej
            cursor.execute(
                f"SELECT id FROM {table_palety} WHERE DATE(data_dodania) = %s AND TIME(data_dodania) >= %s LIMIT 1",
                (date_str, cutoff_time_str)
            )
            if cursor.fetchone():
                cursor.close()
                return True

            # 2. Sprawdź realizację zleceń po godzinie granicznej
            cursor.execute(
                f"""SELECT id FROM {table_plan} 
                    WHERE (data_planu = %s OR DATE(real_start) = %s OR DATE(real_stop) = %s)
                      AND (TIME(real_start) >= %s OR TIME(real_stop) >= %s)
                    LIMIT 1
                """,
                (date_str, date_str, date_str, cutoff_time_str, cutoff_time_str)
            )
            if cursor.fetchone():
                cursor.close()
                return True

            # 3. Sprawdź przestoje po godzinie granicznej
            downtimes = DowntimeRepository().get_downtimes(linia, date_str, date_str)
            cutoff_short = cutoff_time_str[:5]

            def _to_hhmm(val):
                if val is None:
                    return None
                if isinstance(val, timedelta):
                    tot = int(val.total_seconds())
                    return f"{(tot // 3600) % 24:02d}:{(tot % 3600) // 60:02d}"
                if hasattr(val, 'strftime'):
                    return val.strftime('%H:%M')
                s = str(val).strip()
                if ':' in s:
                    parts = s.split(':')
                    try:
                        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                    except Exception:
                        return None
                return None

            for dt in downtimes:
                g_start = _to_hhmm(dt.get('godzina_start'))
                g_stop = _to_hhmm(dt.get('godzina_stop'))
                if (g_start and g_start >= cutoff_short) or (g_stop and g_stop >= cutoff_short):
                    cursor.close()
                    return True

            cursor.close()
            return False
        except Exception as e:
            logger.error("[AUTO_REPORT_DETECTOR] Błąd sprawdzania aktywności po zakończeniu zmiany: %s", e)
            return False
        finally:
            if conn:
                conn.close()
