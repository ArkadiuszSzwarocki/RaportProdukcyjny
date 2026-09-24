"""
Moduł zarządzania globalną konfiguracją automatycznego raportowania (dni tygodnia, włączone linie).
"""
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Union, Tuple

from app.core.database import get_db_connection
from app.core.audit import audit_log

logger = logging.getLogger(__name__)


class AutoReportConfigService:
    @classmethod
    def get_global_config(cls) -> Dict[str, Any]:
        """Pobiera globalną konfigurację automatycznego raportowania (aktywne dni tygodnia, włączone linie)."""
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT active_days, enabled_lines, updated_by, updated_at FROM auto_report_config WHERE id = 1 LIMIT 1")
            row = cursor.fetchone()
            cursor.close()

            active_days_str = row['active_days'] if row and row.get('active_days') is not None else '0,1,2,3,4'
            enabled_lines_str = row['enabled_lines'] if row and row.get('enabled_lines') is not None else 'AGRO'

            active_days = []
            for d in str(active_days_str).split(','):
                d = d.strip()
                if d.isdigit():
                    val = int(d)
                    if 0 <= val <= 6:
                        active_days.append(val)
            active_days = sorted(list(set(active_days)))

            enabled_lines = [l.strip().upper() for l in str(enabled_lines_str).split(',') if l.strip().upper() in ['AGRO']]
            if not enabled_lines:
                enabled_lines = ['AGRO']

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
                'psd_enabled': False,
                'days_map': {day_idx: (day_idx in active_days) for day_idx in range(7)},
                'days_labels': days_labels,
                'updated_by': row.get('updated_by') if row else None,
                'updated_at': str(row.get('updated_at')) if row and row.get('updated_at') else None
            }
        except Exception as e:
            logger.error("[AUTO_REPORT_CONFIG] Błąd pobierania konfiguracji globalnej: %s", e)
            return {
                'active_days': [0, 1, 2, 3, 4],
                'enabled_lines': ['AGRO'],
                'agro_enabled': True,
                'psd_enabled': False,
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
            valid_lines = sorted(list(set(str(l).strip().upper() for l in enabled_lines if str(l).strip().upper() in ['AGRO'])))
            if not valid_lines:
                valid_lines = ['AGRO']

            active_days_str = ','.join(str(d) for d in valid_days)
            enabled_lines_str = ','.join(valid_lines)

            conn = get_db_connection()
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
            logger.error("[AUTO_REPORT_CONFIG] Błąd zapisu konfiguracji globalnej: %s", e)
            return False, f"Błąd zapisu: {e}"
        finally:
            if conn:
                conn.close()

    @classmethod
    def is_line_enabled(cls, linia: str) -> bool:
        """Sprawdza czy dana linia (AGRO / PSD) ma włączoną automatyczną wysyłkę raportu."""
        if not linia or linia.strip().upper() != 'AGRO':
            return False
        config = cls.get_global_config()
        enabled_lines = config.get('enabled_lines', ['AGRO'])
        return 'AGRO' in enabled_lines

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
