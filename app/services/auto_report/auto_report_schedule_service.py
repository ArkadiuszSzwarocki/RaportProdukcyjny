"""
Moduł zarządzania harmonogramem wysyłki auto-raportów oraz odraczaniem czasu przez liderów.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Tuple, List

from app.core.database import get_db_connection
from app.core.audit import audit_log
from app.services.auto_report.auto_report_history_service import AutoReportHistoryService

logger = logging.getLogger(__name__)


class AutoReportScheduleService:
    @classmethod
    def get_schedule(cls, linia: str = 'AGRO', date_str: Optional[str] = None) -> Dict[str, Any]:
        """Pobiera aktualnie zaplanowany czas auto-raportu dla danej linii i daty."""
        if not date_str:
            date_str = str(date.today())

        conn = None
        try:
            conn = get_db_connection()
            AutoReportHistoryService.ensure_history_tables(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT linia, scheduled_time, is_paused, postponed_by, updated_at
                FROM auto_report_schedule
                WHERE data_dnia = %s AND linia IN (%s, 'ALL', 'WSZYSTKO')
                ORDER BY CASE WHEN linia = %s THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (date_str, linia, linia)
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                st = row['scheduled_time']
                st_str = '15:00'
                if st is not None:
                    try:
                        if isinstance(st, str):
                            parts = st.split(':')
                            st_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                        elif hasattr(st, 'total_seconds'):
                            tot = int(st.total_seconds())
                            st_str = f"{(tot // 3600) % 24:02d}:{(tot % 3600) // 60:02d}"
                        elif hasattr(st, 'hour'):
                            st_str = f"{st.hour:02d}:{st.minute:02d}"
                    except Exception:
                        st_str = str(st)[:5]

                raw_paused = row.get('is_paused')
                if isinstance(raw_paused, (bytes, bytearray)):
                    is_paused = (raw_paused != b'\x00' and raw_paused != b'0')
                elif isinstance(raw_paused, str):
                    is_paused = raw_paused.strip().lower() in ('1', 'true', 'yes')
                else:
                    is_paused = bool(raw_paused)

                return {
                    'data_dnia': date_str,
                    'linia': linia,
                    'scheduled_time': st_str,
                    'scheduled_time_full': f"{st_str}:00",
                    'is_paused': is_paused,
                    'postponed_by': row.get('postponed_by'),
                    'is_custom': (st_str != '15:00' or is_paused)
                }

            return {
                'data_dnia': date_str,
                'linia': linia,
                'scheduled_time': '15:00',
                'scheduled_time_full': '15:00:00',
                'is_paused': False,
                'postponed_by': None,
                'is_custom': False
            }
        except Exception as e:
            logger.error("[AUTO_REPORT_SCHEDULE] Błąd pobierania harmonogramu: %s", e)
            return {
                'data_dnia': date_str,
                'linia': linia,
                'scheduled_time': '15:00',
                'scheduled_time_full': '15:00:00',
                'is_paused': False,
                'postponed_by': None,
                'is_custom': False
            }
        finally:
            if conn:
                conn.close()

    @classmethod
    def set_schedule(cls, linia: str, date_str: str, scheduled_time: str, is_paused: bool = False, user_name: str = 'Lider') -> Tuple[bool, str]:
        """Zapisuje lub aktualizuje czas wysyłki raportu."""
        conn = None
        try:
            parts = scheduled_time.strip().split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            formatted_time = f"{h:02d}:{m:02d}:00"

            target_lines = ['AGRO', 'PSD', 'ALL'] if str(linia).upper() in ('ALL', 'WSZYSTKO', 'NONE', '') else [str(linia).upper()]
            if str(linia).upper() in ('ALL', 'WSZYSTKO') and 'ALL' not in target_lines:
                target_lines.append('ALL')

            conn = get_db_connection()
            AutoReportHistoryService.ensure_history_tables(conn)
            cursor = conn.cursor()

            for t_line in target_lines:
                cursor.execute(
                    """
                    INSERT INTO auto_report_schedule (data_dnia, linia, scheduled_time, is_paused, postponed_by, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        scheduled_time = VALUES(scheduled_time),
                        is_paused = VALUES(is_paused),
                        postponed_by = VALUES(postponed_by),
                        updated_at = NOW()
                    """,
                    (date_str, t_line, formatted_time, 1 if is_paused else 0, user_name)
                )

            conn.commit()
            cursor.close()

            audit_log(
                'Zaktualizowano czas wysyłki auto-raportu',
                f'Linia={linia} (target={target_lines}), Data={date_str}, Godzina={formatted_time}, Wstrzymany={is_paused}, Przez={user_name}'
            )
            return True, f"Czas wysyłki auto-raportu dla {linia} został ustawiony na {formatted_time[:5]}."
        except Exception as e:
            logger.error("[AUTO_REPORT_SCHEDULE] Błąd zapisu harmonogramu: %s", e)
            return False, f"Błąd zapisu: {e}"
        finally:
            if conn:
                conn.close()

    @classmethod
    def postpone_report(cls, linia: str = 'AGRO', date_str: Optional[str] = None,
                        add_minutes: Optional[int] = None, new_time: Optional[str] = None,
                        pause_completely: bool = False, reset_to_default: bool = False,
                        user_name: str = 'Lider') -> Tuple[bool, str, Dict[str, Any]]:
        """Odracza lub modyfikuje czas wysyłki auto-raportu."""
        if not date_str:
            date_str = str(date.today())

        if reset_to_default:
            ok, msg = cls.set_schedule(linia, date_str, '15:00:00', is_paused=False, user_name=user_name)
            return ok, "Przywrócono domyślną godzinę wysyłki (15:00).", cls.get_schedule(linia, date_str)

        if pause_completely:
            ok, msg = cls.set_schedule(linia, date_str, '23:59:00', is_paused=True, user_name=user_name)
            return ok, "Automatyczna wysyłka została wstrzymana (raport wyślesz ręcznie).", cls.get_schedule(linia, date_str)

        if new_time:
            ok, msg = cls.set_schedule(linia, date_str, new_time, is_paused=False, user_name=user_name)
            return ok, f"Czas wysyłki został ustawiony na {new_time[:5]}.", cls.get_schedule(linia, date_str)

        if add_minutes:
            curr_sched = cls.get_schedule(linia, date_str)
            curr_time_str = curr_sched['scheduled_time']
            try:
                curr_dt = datetime.strptime(f"{date_str} {curr_time_str}", "%Y-%m-%d %H:%M")
            except Exception:
                curr_dt = datetime.strptime(f"{date_str} 15:00", "%Y-%m-%d %H:%M")

            now_dt = datetime.now()
            base_dt = now_dt if (now_dt.strftime('%Y-%m-%d') == date_str and now_dt > curr_dt) else curr_dt
            new_dt = base_dt + timedelta(minutes=int(add_minutes))
            new_time_str = new_dt.strftime('%H:%M:00')

            ok, msg = cls.set_schedule(linia, date_str, new_time_str, is_paused=False, user_name=user_name)
            return ok, f"Wysyłka została odłożona o +{add_minutes} min (nowa godzina: {new_time_str[:5]}).", cls.get_schedule(linia, date_str)

        return False, "Nie podano parametrów odroczenia.", cls.get_schedule(linia, date_str)
