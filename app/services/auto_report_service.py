"""
Serwis automatycznego raportowania (AutoReportService).
Odpowiedzialny za:
1. Automatyczną wysyłkę raportu I zmiany o godz. 15:00.
2. Detekcję aktywności produkcyjnej po godz. 15:00 (nadgodziny / II zmiana).
3. Generowanie i opcjonalną wysyłkę dedykowanego raportu popołudniowego / II zmiany.
"""

import os
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any, Union

import pandas as pd

from app.db import get_db_connection, get_table_name
from app.services.email_service import EmailService
from app.services.email_report_builder import EmailReportBuilder
from app.repositories.user_email_settings_repository import UserEmailSettingsRepository
from app.repositories.downtime_repository import DowntimeRepository
from app.core.audit import audit_log
from scripts.generator_raportow import generuj_paczke_raportow

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class AutoReportService:
    """Zarządza automatycznym generowaniem i wysyłką raportów o 15:00 oraz po 15:00."""

    @staticmethod
    def _ensure_history_table(conn):
        """Zapewnia istnienie tabeli historii wysyłek auto-raportów."""
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_report_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    data_raportu DATE NOT NULL,
                    linia VARCHAR(20) NOT NULL,
                    typ_raportu VARCHAR(50) NOT NULL,
                    odbiorcy TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_rep (data_raportu, linia, typ_raportu)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_report_schedule (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    data_dnia DATE NOT NULL,
                    linia VARCHAR(20) NOT NULL,
                    scheduled_time TIME NOT NULL DEFAULT '15:00:00',
                    is_paused TINYINT(1) NOT NULL DEFAULT 0,
                    postponed_by VARCHAR(100) DEFAULT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY idx_linia_data (data_dnia, linia)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_report_config (
                    id INT PRIMARY KEY,
                    active_days VARCHAR(50) NOT NULL DEFAULT '0,1,2,3,4',
                    enabled_lines VARCHAR(50) NOT NULL DEFAULT 'AGRO,PSD',
                    updated_by VARCHAR(100) DEFAULT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                INSERT IGNORE INTO auto_report_config (id, active_days, enabled_lines, updated_by)
                VALUES (1, '0,1,2,3,4', 'AGRO,PSD', 'System');
            """)
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.warning("[AUTO_REPORT] Nie udalo sie utworzyc tabel raportowych: %s", e)

    @classmethod
    def get_schedule(cls, linia: str = 'AGRO', date_str: Optional[str] = None) -> Dict[str, Any]:
        """Pobiera aktualnie zaplanowany czas auto-raportu dla danej linii i daty."""
        if not date_str:
            date_str = str(date.today())

        conn = None
        try:
            conn = get_db_connection()
            cls._ensure_history_table(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT scheduled_time, is_paused, postponed_by, updated_at
                FROM auto_report_schedule
                WHERE data_dnia = %s AND linia = %s
                LIMIT 1
                """,
                (date_str, linia)
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

                return {
                    'data_dnia': date_str,
                    'linia': linia,
                    'scheduled_time': st_str,
                    'scheduled_time_full': f"{st_str}:00",
                    'is_paused': bool(row['is_paused']),
                    'postponed_by': row.get('postponed_by'),
                    'is_custom': (st_str != '15:00' or bool(row['is_paused']))
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
            logger.error("[AUTO_REPORT] Blad pobierania harmonogramu: %s", e)
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
            # formatuj czas na HH:MM:00
            parts = scheduled_time.strip().split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            formatted_time = f"{h:02d}:{m:02d}:00"

            conn = get_db_connection()
            cls._ensure_history_table(conn)
            cursor = conn.cursor()
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
                (date_str, linia, formatted_time, 1 if is_paused else 0, user_name)
            )

            # Gdy ustawiono nową godzinę wysyłki (i nie wstrzymano automatu), usuwamy flagę wcześniejszego wysłania
            if not is_paused:
                cursor.execute(
                    "DELETE FROM auto_report_history WHERE data_raportu = %s AND linia = %s AND typ_raportu = '15:00'",
                    (date_str, linia)
                )

            conn.commit()
            cursor.close()

            audit_log(
                'Zaktualizowano czas wysyłki auto-raportu',
                f'Linia={linia}, Data={date_str}, Godzina={formatted_time}, Wstrzymany={is_paused}, Przez={user_name}'
            )
            return True, f"Czas wysyłki auto-raportu dla {linia} został ustawiony na {formatted_time[:5]}."
        except Exception as e:
            logger.error("[AUTO_REPORT] Blad zapisu harmonogramu: %s", e)
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

            from datetime import timedelta
            # Jeśli obecny czas jest już po 15:00, odliczamy od teraz
            now_dt = datetime.now()
            base_dt = now_dt if (now_dt.strftime('%Y-%m-%d') == date_str and now_dt > curr_dt) else curr_dt
            new_dt = base_dt + timedelta(minutes=int(add_minutes))
            new_time_str = new_dt.strftime('%H:%M:00')

            ok, msg = cls.set_schedule(linia, date_str, new_time_str, is_paused=False, user_name=user_name)
            return ok, f"Wysyłka została odłożona o +{add_minutes} min (nowa godzina: {new_time_str[:5]}).", cls.get_schedule(linia, date_str)

        return False, "Nie podano parametrów odroczenia.", cls.get_schedule(linia, date_str)

    @staticmethod
    def get_default_recipients(linia: str = 'AGRO') -> List[str]:
        """Pobiera domyślną listę odbiorców e-mail dla raportu."""
        emails = []
        try:
            repo = UserEmailSettingsRepository()
            recipients = repo.get_all_recipients()
            for r in recipients:
                em = (r.get('email') or '').strip()
                if em and em not in emails:
                    emails.append(em)
            if emails:
                return emails
        except Exception as e:
            logger.warning("[AUTO_REPORT] Nie udalo sie pobrac odbiorcow ze slownika: %s", e)

        # Fallback z bazy z konfiguracji użytkowników
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT domyslni_odbiorcy FROM uzytkownik_email_settings WHERE domyslni_odbiorcy IS NOT NULL AND domyslni_odbiorcy != '' LIMIT 1")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row and row.get('domyslni_odbiorcy'):
                raw = row['domyslni_odbiorcy']
                parsed = [e.strip() for e in raw.replace(';', ',').split(',') if e.strip()]
                if parsed:
                    return parsed
        except Exception:
            pass

        env_recipients = os.getenv('DEFAULT_REPORT_RECIPIENTS', '')
        if env_recipients:
            return [e.strip() for e in env_recipients.replace(';', ',').split(',') if e.strip()]
        return []

    @classmethod
    def is_1500_report_sent(cls, linia: str, date_str: str) -> bool:
        """Sprawdza czy raport o 15:00 został już dzisiaj wysłany."""
        conn = None
        try:
            conn = get_db_connection()
            cls._ensure_history_table(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id FROM auto_report_history 
                WHERE data_raportu = %s AND linia = %s AND typ_raportu = '15:00'
                LIMIT 1
                """,
                (date_str, linia)
            )
            row = cursor.fetchone()
            cursor.close()
            return row is not None
        except Exception as e:
            logger.error("[AUTO_REPORT] Blad sprawdzania historii wysylek: %s", e)
            return False
        finally:
            if conn:
                conn.close()

    @classmethod
    def mark_report_sent(cls, linia: str, date_str: str, typ_raportu: str, recipients_str: str):
        """Rejestruje wysłanie raportu w historii."""
        conn = None
        try:
            conn = get_db_connection()
            cls._ensure_history_table(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO auto_report_history (data_raportu, linia, typ_raportu, odbiorcy)
                VALUES (%s, %s, %s, %s)
                """,
                (date_str, linia, typ_raportu, recipients_str)
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error("[AUTO_REPORT] Blad zapisu do auto_report_history: %s", e)
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

        # Pobierz godzinę graniczną z harmonogramu (odroczenie przez lidera)
        sched = cls.get_schedule(linia, date_str)
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
            for dt in downtimes:
                g_start = str(dt.get('godzina_start') or '')[:5]
                g_stop = str(dt.get('godzina_stop') or '')[:5]
                if (g_start and g_start >= cutoff_short) or (g_stop and g_stop >= cutoff_short):
                    cursor.close()
                    return True

            cursor.close()
            return False
        except Exception as e:
            logger.error("[AUTO_REPORT] Blad sprawdzania aktywnosci po zakonczeniu zmiany: %s", e)
            return False
        finally:
            if conn:
                conn.close()

    @classmethod
    def get_global_config(cls) -> Dict[str, Any]:
        """Pobiera globalną konfigurację automatycznego raportowania (aktywne dni tygodnia, włączone linie)."""
        conn = None
        try:
            conn = get_db_connection()
            cls._ensure_history_table(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT active_days, enabled_lines, updated_by, updated_at FROM auto_report_config WHERE id = 1 LIMIT 1")
            row = cursor.fetchone()
            cursor.close()

            active_days_str = row['active_days'] if row and row.get('active_days') is not None else '0,1,2,3,4'
            enabled_lines_str = row['enabled_lines'] if row and row.get('enabled_lines') is not None else 'AGRO,PSD'

            active_days = []
            for d in str(active_days_str).split(','):
                d = d.strip()
                if d.isdigit():
                    val = int(d)
                    if 0 <= val <= 6:
                        active_days.append(val)
            active_days = sorted(list(set(active_days)))

            enabled_lines = [l.strip().upper() for l in str(enabled_lines_str).split(',') if l.strip().upper() in ['AGRO', 'PSD']]

            days_labels = {
                0: 'Poniedziałek',
                1: 'Wtorek',
                2: 'Środa',
                3: 'Czwartek',
                4: 'Piątek',
                5: 'Sobota',
                6: 'Niedziela'
            }

            return {
                'active_days': active_days,
                'enabled_lines': enabled_lines,
                'agro_enabled': 'AGRO' in enabled_lines,
                'psd_enabled': 'PSD' in enabled_lines,
                'days_map': {day_idx: (day_idx in active_days) for day_idx in range(7)},
                'days_labels': days_labels,
                'updated_by': row.get('updated_by') if row else None,
                'updated_at': str(row.get('updated_at')) if row and row.get('updated_at') else None
            }
        except Exception as e:
            logger.error("[AUTO_REPORT] Błąd pobierania konfiguracji globalnej: %s", e)
            return {
                'active_days': [0, 1, 2, 3, 4],
                'enabled_lines': ['AGRO', 'PSD'],
                'agro_enabled': True,
                'psd_enabled': True,
                'days_map': {0: True, 1: True, 2: True, 3: True, 4: True, 5: False, 6: False},
                'days_labels': {
                    0: 'Poniedziałek', 1: 'Wtorek', 2: 'Środa', 3: 'Czwartek', 4: 'Piątek', 5: 'Sobota', 6: 'Niedziela'
                },
                'updated_by': None,
                'updated_at': None
            }
        finally:
            if conn:
                conn.close()

    @classmethod
    def save_global_config(cls, active_days: List[int], enabled_lines: List[str], user_name: str = 'Admin') -> Tuple[bool, str]:
        """Zapisuje globalną konfigurację automatycznego raportowania."""
        conn = None
        try:
            valid_days = sorted(list(set(int(d) for d in active_days if str(d).isdigit() and 0 <= int(d) <= 6)))
            valid_lines = sorted(list(set(str(l).strip().upper() for l in enabled_lines if str(l).strip().upper() in ['AGRO', 'PSD'])))

            active_days_str = ','.join(str(d) for d in valid_days)
            enabled_lines_str = ','.join(valid_lines)

            conn = get_db_connection()
            cls._ensure_history_table(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO auto_report_config (id, active_days, enabled_lines, updated_by, updated_at)
                VALUES (1, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    active_days = VALUES(active_days),
                    enabled_lines = VALUES(enabled_lines),
                    updated_by = VALUES(updated_by),
                    updated_at = NOW()
                """,
                (active_days_str, enabled_lines_str, user_name)
            )
            conn.commit()
            cursor.close()

            audit_log(
                'Zaktualizowano globalną konfigurację auto-raportów',
                f'Dni={active_days_str}, Linie={enabled_lines_str}, Przez={user_name}'
            )
            return True, "Zapisano konfigurację automatycznego wysyłania raportów."
        except Exception as e:
            logger.error("[AUTO_REPORT] Błąd zapisu konfiguracji globalnej: %s", e)
            return False, f"Błąd zapisu: {e}"
        finally:
            if conn:
                conn.close()

    @classmethod
    def is_line_enabled(cls, linia: str) -> bool:
        """Sprawdza czy dana linia (AGRO / PSD) ma włączoną automatyczną wysyłkę raportu."""
        if not linia:
            return False
        config = cls.get_global_config()
        enabled_lines = config.get('enabled_lines', ['AGRO', 'PSD'])
        return linia.strip().upper() in enabled_lines

    @classmethod
    def is_report_day(cls, target_date: Optional[Union[str, date, datetime]] = None) -> bool:
        """Sprawdza, czy podana data przypada w dzień wybrany w konfiguracji do automatycznej wysyłki."""
        if target_date is None:
            target_date = date.today()
        if isinstance(target_date, str):
            try:
                target_date = datetime.strptime(target_date[:10], '%Y-%m-%d').date()
            except Exception:
                return False
        elif isinstance(target_date, datetime):
            target_date = target_date.date()
        elif not isinstance(target_date, date):
            return False

        config = cls.get_global_config()
        active_days = config.get('active_days', [0, 1, 2, 3, 4])
        return target_date.weekday() in active_days

    @classmethod
    def is_weekday(cls, target_date: Optional[Union[str, date, datetime]] = None) -> bool:
        """Kompatybilny alias sprawdzający, czy data jest aktywnym dniem raportowym."""
        return cls.is_report_day(target_date)

    @classmethod
    def send_shift1_report_at_1500(cls, linia: str = 'AGRO', date_str: Optional[str] = None, force: bool = False) -> Tuple[bool, str]:
        """Generuje i wysyła automatyczny raport o 15:00 dla I zmiany (zgodnie z konfiguracją linii i dni)."""
        if not date_str:
            date_str = str(date.today())

        if not force and not cls.is_line_enabled(linia):
            msg = f"Automatyczny raport dla linii {linia} jest wyłączony w konfiguracji."
            logger.info("[AUTO_REPORT] %s", msg)
            return True, msg

        if not force and not cls.is_report_day(date_str):
            msg = f"Automatyczny raport dla {linia} w dniu {date_str} pominięty - dzień nie jest aktywny w harmonogramie wysyłek."
            logger.info("[AUTO_REPORT] %s", msg)
            return True, msg

        if cls.is_1500_report_sent(linia, date_str):
            msg = f"Raport o 15:00 dla {linia} w dniu {date_str} zostal juz wyslany."
            logger.info("[AUTO_REPORT] %s", msg)
            return True, msg

        to_emails = cls.get_default_recipients(linia)
        if not to_emails:
            msg = f"Brak skonfigurowanych odbiorcow e-mail dla linii {linia}. Anulowano wysylke o 15:00."
            logger.warning("[AUTO_REPORT] %s", msg)
            return False, msg

        logger.info("[AUTO_REPORT] Rozpoczynam generowanie raportu o 15:00 dla linii %s (odbiorcy: %s)", linia, to_emails)

        try:
            from app.services.shift_close_service import _load_shift_notes, _generate_report_files

            uwagi = _load_shift_notes(date_str, linia=linia)
            lider_name = "System Auto-Raport (I Zmiana)"
            xls_path, txt_path, pdf_path = _generate_report_files(date_str, uwagi, lider_name, linia=linia)

            valid_attachments = [p for p in [pdf_path, xls_path] if p and os.path.exists(p)]
            att_filenames = [os.path.basename(p) for p in valid_attachments]

            # Pobierz aktualne tonaze z rzeczywistych szarz i palet
            suma_zasyp = 0
            suma_workowanie = 0
            palety_count = 0
            try:
                conn = get_db_connection()
                table_szarze = 'szarze_agro' if linia == 'AGRO' else 'szarze'
                table_palety = 'palety_agro' if linia == 'AGRO' else 'palety_workowanie'
                c_prod = conn.cursor(dictionary=True)
                c_prod.execute(f"SELECT COALESCE(SUM(waga), 0) as s FROM {table_szarze} WHERE DATE(data_dodania) = %s", (date_str,))
                r_z = c_prod.fetchone()
                suma_zasyp = int(r_z['s']) if r_z else 0

                c_prod.execute(f"SELECT COUNT(id) as cnt, COALESCE(SUM(waga), 0) as s FROM {table_palety} WHERE DATE(data_dodania) = %s", (date_str,))
                r_w = c_prod.fetchone()
                if r_w:
                    palety_count = int(r_w['cnt'] or 0)
                    suma_workowanie = int(r_w['s'] or 0)
                c_prod.close()
                conn.close()
            except Exception:
                pass

            downtimes = DowntimeRepository().get_downtimes(linia, date_str, date_str)
            total_downtime_min = sum(int(dt.get('czas_trwania_min') or 0) for dt in downtimes)

            sched = cls.get_schedule(linia, date_str)
            sched_time_display = sched.get('scheduled_time') or '15:00'

            body_html = EmailReportBuilder.build_shift_report_html(
                linia=linia,
                date_str=date_str,
                lider_name=f"Automatyczny Raport I Zmiany (godz. {sched_time_display})",
                suma_zasyp=suma_zasyp,
                suma_workowanie=suma_workowanie,
                downtimes=downtimes,
                total_downtime_min=total_downtime_min,
                notes_text=uwagi,
                attachments_names=att_filenames,
                palety_count=palety_count
            )

            subject = f"📊 Raport Produkcyjny {linia} — I Zmiana ({sched_time_display}) — {date_str}"

            email_service = EmailService()
            success, message = email_service.send_report_email(
                to_emails=to_emails,
                subject=subject,
                body_html=body_html,
                attachments=valid_attachments
            )

            if success:
                cls.mark_report_sent(linia, date_str, '15:00', ", ".join(to_emails))
                audit_log(
                    'Automatyczna wysyłka raportu o 15:00',
                    f'Linia={linia}, Data={date_str}, Odbiorcy={", ".join(to_emails)}'
                )
                logger.info("[AUTO_REPORT] Raport o 15:00 wyslany pomyslnie na %s", to_emails)
                return True, f"Raport o 15:00 wysłany pomyślnie do {len(to_emails)} odbiorców."
            else:
                logger.error("[AUTO_REPORT] Blad wysylki email o 15:00: %s", message)
                return False, message
        except Exception as e:
            logger.exception("[AUTO_REPORT] Wyjatek podczas generowania raportu o 15:00: %s", e)
            return False, str(e)

    @classmethod
    def generate_and_send_post_1500_report(cls, linia: str = 'AGRO', date_str: Optional[str] = None, to_emails: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Tworzy i wysyła nowy dedykowany raport dla pracy po godz. 15:00 (II zmiana / nadgodziny)."""
        if not date_str:
            date_str = str(date.today())

        if not to_emails:
            to_emails = cls.get_default_recipients(linia)

        if not to_emails:
            return False, "Brak odbiorców e-mail dla raportu po 15:00."

        try:
            from app.services.shift_close_service import _load_shift_notes

            uwagi = _load_shift_notes(date_str, linia=linia)
            lider_name = "Raport Popołudniowy / II Zmiana (po 15:00)"

            xls_path, txt_path, pdf_path = generuj_paczke_raportow(
                data_raportu=date_str,
                uwagi_lidera=uwagi,
                lider_name=lider_name,
                linia=linia
            )

            valid_attachments = [p for p in [pdf_path, xls_path] if p and os.path.exists(p)]
            att_filenames = [os.path.basename(p) for p in valid_attachments]

            # Pobierz aktualne tonaze z rzeczywistych szarz i palet
            suma_zasyp = 0
            suma_workowanie = 0
            palety_count = 0
            try:
                conn = get_db_connection()
                table_szarze = 'szarze_agro' if linia == 'AGRO' else 'szarze'
                table_palety = 'palety_agro' if linia == 'AGRO' else 'palety_workowanie'
                c_prod = conn.cursor(dictionary=True)
                c_prod.execute(f"SELECT COALESCE(SUM(waga), 0) as s FROM {table_szarze} WHERE DATE(data_dodania) = %s", (date_str,))
                r_z = c_prod.fetchone()
                suma_zasyp = int(r_z['s']) if r_z else 0

                c_prod.execute(f"SELECT COUNT(id) as cnt, COALESCE(SUM(waga), 0) as s FROM {table_palety} WHERE DATE(data_dodania) = %s", (date_str,))
                r_w = c_prod.fetchone()
                if r_w:
                    palety_count = int(r_w['cnt'] or 0)
                    suma_workowanie = int(r_w['s'] or 0)
                c_prod.close()
                conn.close()
            except Exception:
                pass

            downtimes = DowntimeRepository().get_downtimes(linia, date_str, date_str)
            total_downtime_min = sum(int(dt.get('czas_trwania_min') or 0) for dt in downtimes)

            body_html = EmailReportBuilder.build_shift_report_html(
                linia=linia,
                date_str=date_str,
                lider_name="Raport Popołudniowy / II Zmiana (po godz. 15:00)",
                suma_zasyp=suma_zasyp,
                suma_workowanie=suma_workowanie,
                downtimes=downtimes,
                total_downtime_min=total_downtime_min,
                notes_text=uwagi,
                attachments_names=att_filenames,
                palety_count=palety_count
            )

            subject = f"📊 Raport Produkcyjny {linia} — Praca po 15:00 / II Zmiana — {date_str}"

            email_service = EmailService()
            success, message = email_service.send_report_email(
                to_emails=to_emails,
                subject=subject,
                body_html=body_html,
                attachments=valid_attachments
            )

            if success:
                cls.mark_report_sent(linia, date_str, 'po_15:00', ", ".join(to_emails))
                audit_log(
                    'Wysyłka raportu popołudniowego po 15:00',
                    f'Linia={linia}, Data={date_str}, Odbiorcy={", ".join(to_emails)}'
                )
                logger.info("[AUTO_REPORT] Raport po 15:00 wyslany pomyslnie na %s", to_emails)
                return True, "Raport popołudniowy (po 15:00) został pomyślnie wygenerowany i wysłany."
            else:
                return False, message
        except Exception as e:
            logger.exception("[AUTO_REPORT] Blad generowania raportu po 15:00: %s", e)
            return False, str(e)
