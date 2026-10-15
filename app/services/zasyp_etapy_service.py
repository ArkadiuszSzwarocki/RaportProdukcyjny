# cspell:words TINYINT calkowita zapauzowanego zapauzowany
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.db import get_db_connection, get_table_name
from app.services.zasyp_etapy_support import (
    ETAP_MAX,
    ETAP_MIN,
    EtapRow,
    _agro_suffix_for_etap,
    _build_sequence_for_szarza,
    _etap_display_name,
    _format_duration,
    _format_hhmm,
    _format_date,
    _is_valid_etap_for_linia,
    _norm_linia,
    _parse_hhmm_to_dt,
    _prev_next_etap_in_sequence,
    _visible_etaps_for_linia,
)

logger = logging.getLogger(__name__)


class ZasypEtapyService:
    _pause_columns_checked: bool = False

    @classmethod
    def _ensure_pause_columns(cls, cursor) -> None:
        """Safely ensure pause columns exist in zasyp_etapy table without failing."""
        if cls._pause_columns_checked:
            return
        try:
            cursor.execute("SHOW COLUMNS FROM zasyp_etapy LIKE 'is_paused'")
            r = cursor.fetchone()
            if not r:
                cursor.execute("ALTER TABLE zasyp_etapy ADD COLUMN is_paused TINYINT(1) NOT NULL DEFAULT 0")
                cursor.execute("ALTER TABLE zasyp_etapy ADD COLUMN pauza_start DATETIME NULL DEFAULT NULL")
                cursor.execute("ALTER TABLE zasyp_etapy ADD COLUMN pauza_sekundy INT NOT NULL DEFAULT 0")
            cls._pause_columns_checked = True
        except Exception:
            pass

    @staticmethod
    def _max_szarza_from_batches(cursor, plan_id: int, linia_u: str) -> int:
        """Return max batch number from szarze table (fallback when zasyp_etapy is empty)."""
        table_szarze = get_table_name('szarze', linia_u)
        cursor.execute(
            f"SELECT COALESCE(MAX(COALESCE(nr_szarzy, 1)), 0) AS max_val FROM {table_szarze} WHERE plan_id=%s",
            (int(plan_id),),
        )
        row = cursor.fetchone()
        try:
            val = row.get('max_val') if isinstance(row, dict) else (row[0] if row else 0)
            value = int(val or 0)
            return value if value > 0 else 0
        except Exception:
            return 0

    @staticmethod
    def _resolve_szarza_nr(cursor, plan_id: int, linia_u: str, szarza_nr: Optional[int] = None) -> int:
        if szarza_nr is not None:
            try:
                candidate = int(szarza_nr)
                if candidate > 0:
                    return candidate
            except Exception:
                pass

        cursor.execute(
            "SELECT COALESCE(MAX(COALESCE(szarza_nr, 1)), 1) AS max_val FROM zasyp_etapy WHERE linia=%s AND plan_id=%s",
            (linia_u, int(plan_id)),
        )
        row = cursor.fetchone()
        try:
            val = row.get('max_val') if isinstance(row, dict) else (row[0] if row else 1)
            resolved = int(val or 1)
            if resolved > 0:
                return resolved
        except Exception:
            pass

        # Fallback for legacy/partial data: no etapy rows, but there are production batches.
        batch_nr = ZasypEtapyService._max_szarza_from_batches(cursor, plan_id, linia_u)
        if batch_nr > 0:
            return batch_nr
        return 1

    @staticmethod
    def _list_szarza_nrs(cursor, plan_id: int, linia_u: str) -> List[int]:
        cursor.execute(
            """
            SELECT DISTINCT COALESCE(szarza_nr, 1) AS szarza_nr
            FROM zasyp_etapy
            WHERE linia=%s AND plan_id=%s
            ORDER BY szarza_nr DESC
            """,
            (linia_u, int(plan_id)),
        )
        out: List[int] = []
        for row in cursor.fetchall() or []:
            try:
                val = row.get('szarza_nr') if isinstance(row, dict) else (row[0] if row else None)
                if val is not None:
                    out.append(max(1, int(val)))
            except Exception:
                continue
        if out:
            return sorted(list(set(out)), reverse=True)

        batch_nr = ZasypEtapyService._max_szarza_from_batches(cursor, plan_id, linia_u)
        return [batch_nr] if batch_nr > 0 else [1]

    @staticmethod
    def _load_etapy_rows(cursor, plan_id: int, linia_u: str, szarza_nr: int) -> Dict[int, EtapRow]:
        etapy_by_nr: Dict[int, EtapRow] = {}
        ZasypEtapyService._ensure_pause_columns(cursor)

        target_nr = int(szarza_nr)
        cursor.execute(
            """
            SELECT *
            FROM zasyp_etapy
            WHERE linia = %s AND plan_id = %s AND (szarza_nr = %s OR ((szarza_nr IS NULL OR szarza_nr = 0) AND %s = 1))
            ORDER BY etap ASC
            """,
            (linia_u, int(plan_id), target_nr, target_nr),
        )
        col_names = [d[0] for d in cursor.description] if cursor.description else []
        for r in cursor.fetchall() or []:
            row_dict = r if isinstance(r, dict) else dict(zip(col_names, r))
            try:
                etap_nr = int(row_dict.get('etap'))
            except Exception:
                continue

            if etap_nr <= 0:
                continue

            etapy_by_nr[etap_nr] = EtapRow(
                etap=etap_nr,
                czas_start=row_dict.get('czas_start'),
                czas_stop=row_dict.get('czas_stop'),
                start_login=row_dict.get('start_login'),
                stop_login=row_dict.get('stop_login'),
                is_paused=bool(row_dict.get('is_paused', 0)),
                pauza_start=row_dict.get('pauza_start'),
                pauza_sekundy=int(row_dict.get('pauza_sekundy', 0) or 0),
            )
        return etapy_by_nr

    @staticmethod
    def _build_etapy_payload(plan_id: int, linia_u: str, szarza_nr: int, etapy_by_nr: Dict[int, EtapRow]) -> Dict[str, Any]:
        now = datetime.now()
        out: List[Dict[str, Any]] = []
        active_etap: Optional[int] = None
        total_s = 0

        # Define the order and sub-stages for AGRO
        base_etaps = _visible_etaps_for_linia(linia_u)
        
        # We will build a list of etapy to show.
        # For AGRO 3 and 4, we support unlimited suffixes: 31/41, 32/42 ... 310/410 ...
        to_process = []
        if linia_u == 'AGRO':
            # Order: 1, 2, then (3,4), then existing extra pairs ordered by suffix, then 5
            to_process.append(1)
            to_process.append(2)

            extra_suffixes: set[int] = set()
            for en in etapy_by_nr.keys():
                try:
                    etap_s = str(int(en))
                except Exception:
                    continue
                if len(etap_s) > 1 and etap_s[0] in ['3', '4']:
                    try:
                        extra_suffixes.add(int(etap_s[1:]))
                    except Exception:
                        continue

            to_process.extend([3, 4])
            for suffix in sorted(extra_suffixes):
                to_process.append(int(f'3{suffix}'))
                to_process.append(int(f'4{suffix}'))
            
            to_process.append(5)
        else:
            to_process = list(base_etaps)

        # Ensure any stage that physically exists in database is never omitted
        for en in sorted(etapy_by_nr.keys()):
            if en > 0 and en not in to_process:
                to_process.append(en)

        for etap_nr in to_process:
            row = etapy_by_nr.get(etap_nr)
            start_dt = row.czas_start if row else None
            stop_dt = row.czas_stop if row else None
            is_paused = bool(row.is_paused) if row else False
            pauza_start = row.pauza_start if row else None
            pauza_sekundy = int(row.pauza_sekundy or 0) if row else 0

            is_running = bool(start_dt and not stop_dt and not is_paused)
            if start_dt and not stop_dt:
                active_etap = etap_nr

            dur_s = 0
            if start_dt:
                if is_paused and pauza_start:
                    end_dt = pauza_start
                else:
                    end_dt = stop_dt or now
                try:
                    dur_raw = int((end_dt - start_dt).total_seconds())
                    dur_s = max(0, dur_raw - pauza_sekundy)
                except Exception:
                    dur_s = 0
            if dur_s < 0:
                dur_s = 0

            total_s += dur_s
            out.append(
                {
                    'etap': etap_nr,
                    'exists': row is not None,
                    'czas_start': start_dt,
                    'czas_stop': stop_dt,
                    'czas_start_str': _format_hhmm(start_dt),
                    'czas_stop_str': _format_hhmm(stop_dt),
                    'data_start_str': _format_date(start_dt),
                    'data_stop_str': _format_date(stop_dt),
                    'duration_s': dur_s,
                    'duration_str': _format_duration(dur_s),
                    'is_running': is_running,
                    'is_paused': is_paused,
                    'pauza_sekundy': pauza_sekundy,
                    'start_login': (row.start_login if row else None) or '',
                    'stop_login': (row.stop_login if row else None) or '',
                }
            )

        return {
            'plan_id': int(plan_id),
            'linia': linia_u,
            'szarza_nr': int(szarza_nr),
            'zasyp_nr': int(szarza_nr),
            'active_etap': active_etap,
            'has_running': active_etap is not None,
            'total_duration_s': total_s,
            'total_duration_str': _format_duration(total_s),
            'etapy': out,
            'curr_szarza_nr': int(szarza_nr),
            'curr_zasyp_nr': int(szarza_nr),
        }

    @staticmethod
    def get_etapy(plan_id: int, linia: str, szarza_nr: Optional[int] = None) -> Dict[str, Any]:
        """Return etap status for one selected szarza/session.

        Safe-by-default: on any DB error, returns a default empty session payload.
        """
        linia_u = _norm_linia(linia)

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            target_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)
            etapy_by_nr = ZasypEtapyService._load_etapy_rows(cursor, plan_id, linia_u, target_szarza_nr)
            cursor.close()
            conn.close()
            return ZasypEtapyService._build_etapy_payload(plan_id, linia_u, target_szarza_nr, etapy_by_nr)
        except Exception as e:
            logger.warning("get_etapy failed for plan %s, linia %s: %s", plan_id, linia_u, e, exc_info=True)
            target_szarza_nr = 1
            if szarza_nr is not None:
                try:
                    target_szarza_nr = max(1, int(szarza_nr))
                except Exception:
                    target_szarza_nr = 1
            return ZasypEtapyService._build_etapy_payload(plan_id, linia_u, target_szarza_nr, {})

    @staticmethod
    def get_etapy_sessions(plan_id: int, linia: str) -> List[Dict[str, Any]]:
        """Return all measurement sessions (szarza_nr) for a plan, newest first."""
        linia_u = _norm_linia(linia)
        sessions: List[Dict[str, Any]] = []

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            for session_szarza_nr in ZasypEtapyService._list_szarza_nrs(cursor, plan_id, linia_u):
                etapy_by_nr = ZasypEtapyService._load_etapy_rows(cursor, plan_id, linia_u, session_szarza_nr)
                sessions.append(
                    ZasypEtapyService._build_etapy_payload(plan_id, linia_u, session_szarza_nr, etapy_by_nr)
                )
            cursor.close()
            conn.close()
        except Exception as e:
            logger.warning("get_etapy_sessions failed for plan %s, linia %s: %s", plan_id, linia_u, e, exc_info=True)
            sessions = [ZasypEtapyService._build_etapy_payload(plan_id, linia_u, 1, {})]

        for idx, session_data in enumerate(sessions):
            session_data['is_current'] = idx == 0
        return sessions

    @staticmethod
    def kolejny_pomiar(plan_id: int, linia: str, user_login: str) -> Tuple[bool, str]:
        linia_u = _norm_linia(linia)
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(szarza_nr) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s", (linia_u, int(plan_id)))
            r = cursor.fetchone()
            curr = r[0] if r and r[0] else 1
            new_nr = curr + 1
            
            cursor.execute(
                """
                INSERT INTO zasyp_etapy (linia, plan_id, data_planu, szarza_nr, etap, czas_start, czas_stop, start_login, stop_login)
                VALUES (%s, %s, CURDATE(), %s, 0, NULL, NULL, %s, NULL)
                """,
                (linia_u, int(plan_id), new_nr, (user_login or '')[:100])
            )
            conn.commit()
            return True, f"Przełączono pomiar na zasyp #{new_nr}"
        except Exception as e:
            if conn:
                try: conn.rollback()
                except: pass
            return False, f"Błąd przygotowania nowego pomiaru: {e}"
        finally:
            if conn:
                try: conn.close()
                except: pass

    @staticmethod
    def add_agro_dosypka_pair(plan_id: int, linia: str, data_planu: date, user_login: str, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
        linia_u = _norm_linia(linia)
        if linia_u != 'AGRO':
            return False, 'Para dosypki jest dostępna tylko dla AGRO'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            target_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                "SELECT etap FROM zasyp_etapy WHERE linia=%s AND plan_id=%s AND szarza_nr=%s",
                (linia_u, int(plan_id), target_szarza_nr),
            )
            existing = {
                int(row[0] if isinstance(row, (tuple, list)) else row.get('etap'))
                for row in (cursor.fetchall() or [])
            }

            if 3 not in existing and 4 not in existing:
                pair = (3, 4)
            else:
                used_suffixes: set[int] = set()
                for etap_nr in existing:
                    try:
                        etap_s = str(int(etap_nr))
                    except Exception:
                        continue
                    if len(etap_s) > 1 and etap_s[0] in ['3', '4']:
                        try:
                            used_suffixes.add(int(etap_s[1:]))
                        except Exception:
                            continue

                suffix = 1
                while suffix in used_suffixes:
                    suffix += 1
                pair = (int(f'3{suffix}'), int(f'4{suffix}'))

            created_any = False
            for etap_nr in pair:
                if etap_nr in existing:
                    continue
                cursor.execute(
                    """
                    INSERT INTO zasyp_etapy (linia, plan_id, data_planu, szarza_nr, etap, czas_start, czas_stop, start_login, stop_login)
                    VALUES (%s, %s, %s, %s, %s, NULL, NULL, %s, NULL)
                    """,
                    (linia_u, int(plan_id), data_planu, target_szarza_nr, etap_nr, (user_login or '')[:100]),
                )
                created_any = True

            conn.commit()
            if not created_any:
                return True, f'Para etapów {pair[0]} / {pair[1]} już istnieje'
            return True, f'Dodano parę etapów {pair[0]} / {pair[1]}'
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False, f'Błąd dodawania pary dosypki: {e}'
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def remove_last_agro_dosypka_pair(plan_id: int, linia: str, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
        """Remove the latest AGRO pair in current session: 39/49..31/41, then 3/4."""
        linia_u = _norm_linia(linia)
        if linia_u != 'AGRO':
            return False, 'Usuwanie pary dosypki jest dostępne tylko dla AGRO'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            target_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                "SELECT etap FROM zasyp_etapy WHERE linia=%s AND plan_id=%s AND szarza_nr=%s",
                (linia_u, int(plan_id), target_szarza_nr),
            )
            existing = {
                int(row[0] if isinstance(row, (tuple, list)) else row.get('etap'))
                for row in (cursor.fetchall() or [])
            }

            pair = None
            for suffix in range(9, 0, -1):
                candidate = (30 + suffix, 40 + suffix)
                if candidate[0] in existing or candidate[1] in existing:
                    pair = candidate
                    break

            if pair is None and (3 in existing or 4 in existing):
                pair = (3, 4)

            if pair is None:
                return False, 'Brak par dosypki do usunięcia'

            cursor.execute(
                "DELETE FROM zasyp_etapy WHERE linia=%s AND plan_id=%s AND szarza_nr=%s AND etap IN (%s, %s)",
                (linia_u, int(plan_id), target_szarza_nr, pair[0], pair[1]),
            )
            conn.commit()
            return True, f'Usunięto parę etapów {pair[0]} / {pair[1]}'
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False, f'Błąd usuwania pary dosypki: {e}'
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def remove_kontrolny_session(plan_id: int, linia: str, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
        """Delete all control-point rows for one measurement session (szarza_nr)."""
        linia_u = _norm_linia(linia)
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            target_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                "SELECT COUNT(*) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s AND szarza_nr=%s",
                (linia_u, int(plan_id), target_szarza_nr),
            )
            row = cursor.fetchone()
            rows_count = int(row[0] if row else 0)

            cursor.execute(
                "DELETE FROM zasyp_etapy WHERE linia=%s AND plan_id=%s AND szarza_nr=%s",
                (linia_u, int(plan_id), target_szarza_nr),
            )
            deleted_etapy = int(cursor.rowcount or 0)

            # Keep production batches in sync with control points: remove matching szarza row too.
            table_szarze = get_table_name('szarze', linia_u)
            cursor.execute(
                f"DELETE FROM {table_szarze} WHERE plan_id=%s AND nr_szarzy=%s",
                (int(plan_id), int(target_szarza_nr)),
            )
            deleted_szarze = int(cursor.rowcount or 0)

            # Legacy fallback: old rows may have NULL nr_szarzy.
            if deleted_szarze <= 0 and int(target_szarza_nr) == 1:
                cursor.execute(
                    f"DELETE FROM {table_szarze} WHERE plan_id=%s AND (nr_szarzy IS NULL OR nr_szarzy=0) ORDER BY data_dodania DESC LIMIT 1",
                    (int(plan_id),),
                )
                deleted_szarze = int(cursor.rowcount or 0)

            if rows_count <= 0 and deleted_szarze <= 0:
                return False, f'Punkt kontrolny zasypu #{target_szarza_nr} jest już pusty'

            # Keep realized tonnage consistent after removing a batch.
            table_plan = get_table_name('plan_produkcji', linia_u)
            table_dosypki = get_table_name('dosypki', linia_u)
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id=%s), 0) + "
                f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id=%s AND potwierdzone=1 AND COALESCE(anulowana, 0)=0), 0) + "
                f"COALESCE((SELECT SUM(waga_calkowita) FROM wiaderka_maluchy WHERE plan_id=%s AND UPPER(linia) = '{'AGRO' if table_plan.endswith('_agro') else 'PSD'}' AND status = 'wrzucone_do_mieszalnika'), 0) "
                "WHERE id=%s",
                (int(plan_id), int(plan_id), int(plan_id), int(plan_id)),
            )
            conn.commit()

            if deleted_etapy > 0 and deleted_szarze > 0:
                return True, f'Usunięto cały punkt kontrolny zasypu #{target_szarza_nr}'
            if deleted_szarze > 0:
                return True, f'Usunięto zasyp #{target_szarza_nr} i odświeżono punkt kontrolny'
            return True, f'Usunięto wpisy punktu kontrolnego zasypu #{target_szarza_nr}'
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False, f'Błąd usuwania punktu kontrolnego: {e}'
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def get_parametry(plan_id: int, linia: str) -> Dict[str, Any]:
        """Return per-plan parameters (batch size)."""
        linia_u = _norm_linia(linia)
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT wielkosc_szarzy_kg
                FROM zasyp_etapy_parametry
                WHERE linia = %s AND plan_id = %s
                """,
                (linia_u, int(plan_id)),
            )
            row = cursor.fetchone() or {}
            cursor.close()
            conn.close()
            raw = row.get('wielkosc_szarzy_kg')
            return {
                'wielkosc_szarzy_kg': float(raw) if raw is not None else None,
            }
        except Exception:
            return {
                'wielkosc_szarzy_kg': None,
            }

    @staticmethod
    def set_wielkosc_szarzy(plan_id: int, linia: str, data_planu: date, kg: Optional[float], user_login: str) -> Tuple[bool, str]:
        linia_u = _norm_linia(linia)
        conn = None
        try:
            kg_val: Optional[float]
            if kg is None:
                kg_val = None
            else:
                kg_val = float(kg)
                if kg_val <= 0:
                    return False, 'Wielkość zasypu musi być > 0'

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO zasyp_etapy_parametry (linia, plan_id, data_planu, wielkosc_szarzy_kg, updated_by_login)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    data_planu = VALUES(data_planu),
                    wielkosc_szarzy_kg = VALUES(wielkosc_szarzy_kg),
                    updated_by_login = VALUES(updated_by_login),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (linia_u, int(plan_id), data_planu, kg_val, (user_login or '')[:100]),
            )
            conn.commit()
            cursor.close()
            conn.close()
            return True, 'Zapisano wielkość zasypu'
        except Exception:
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            return False, 'Błąd zapisu wielkości zasypu'

    @staticmethod
    def _get_running_etap(cursor, plan_id: int, linia_u: str, szarza_nr: int) -> Optional[int]:
        cursor.execute(
            """
            SELECT etap
            FROM zasyp_etapy
            WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND czas_start IS NOT NULL AND czas_stop IS NULL
            LIMIT 1
            """,
            (linia_u, int(plan_id), szarza_nr),
        )
        row = cursor.fetchone()
        if not row:
            return None
        try:
            return int(row[0] if isinstance(row, (tuple, list)) else row.get('etap'))
        except Exception:
            return None

    @staticmethod
    def start_etap(plan_id: int, linia: str, data_planu: date, etap: int, user_login: str, szarza_nr: Optional[int] = None, allow_restart: bool = False) -> Tuple[bool, str]:
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
        except Exception:
            return False, 'Nieprawidłowy etap'
        if not _is_valid_etap_for_linia(etap_nr, linia_u):
            return False, 'Nieprawidłowy etap'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            curr_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                """
                SELECT etap, czas_start, czas_stop
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s
                """,
                (linia_u, int(plan_id), curr_szarza_nr),
            )
            all_rows = cursor.fetchall() or []
            etap_times: Dict[int, Tuple[Optional[datetime], Optional[datetime]]] = {}
            existing_etaps: List[int] = []
            for r in all_rows:
                try:
                    e = int(r[0] if isinstance(r, (tuple, list)) else r.get('etap'))
                except Exception:
                    continue
                existing_etaps.append(e)
                start_dt = r[1] if isinstance(r, (tuple, list)) else r.get('czas_start')
                stop_dt = r[2] if isinstance(r, (tuple, list)) else r.get('czas_stop')
                etap_times[e] = (start_dt, stop_dt)

            seq = _build_sequence_for_szarza(linia_u, existing_etaps, include_etap=etap_nr)
            prev_etap, _ = _prev_next_etap_in_sequence(seq, etap_nr)
            
            # Skip prev_stop validation if this is a restart of the same stage
            if not allow_restart and prev_etap is not None:
                prev_stop = (etap_times.get(prev_etap) or (None, None))[1]
                curr_name = _etap_display_name(linia_u, etap_nr)
                prev_name = _etap_display_name(linia_u, prev_etap)
                if prev_stop is None:
                    return False, f'{curr_name} nie może się rozpocząć przed zakończeniem: {prev_name} (najpierw ustaw STOP)'

            running = ZasypEtapyService._get_running_etap(cursor, plan_id, linia_u, curr_szarza_nr)
            if running is not None and running != etap_nr:
                if allow_restart:
                    # Restart ma pierwszeństwo: domykamy aktualnie trwający etap,
                    # aby nie zostawić równolegle dwóch etapów "w toku".
                    cursor.execute(
                        """
                        UPDATE zasyp_etapy
                        SET czas_stop = NOW(), stop_login = %s
                        WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s AND czas_start IS NOT NULL AND czas_stop IS NULL
                        """,
                        ((user_login or '')[:100], linia_u, int(plan_id), curr_szarza_nr, int(running)),
                    )
                else:
                    return False, f'Trwa już punkt kontrolny {running} — zakończ go przed startem punktu kontrolnego {etap_nr}'

            cursor.execute(
                """
                SELECT czas_start, czas_stop
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s
                """,
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            row = cursor.fetchone()
            if row:
                # row is tuple (czas_start, czas_stop)
                czas_start, czas_stop = row[0], row[1]
                if czas_start and not czas_stop:
                    return True, f'Etap {etap_nr} już trwa'
                if czas_start and czas_stop:
                    if allow_restart:
                        cursor.execute(
                            """
                            UPDATE zasyp_etapy
                            SET czas_start = NOW(), czas_stop = NULL, start_login = %s, stop_login = NULL
                            WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s
                            """,
                            ((user_login or '')[:100], linia_u, int(plan_id), curr_szarza_nr, etap_nr),
                        )
                        conn.commit()
                        return True, f'Uruchomiono ponownie etap {etap_nr}'

                    # AGRO: if stage 3 or 4 is done, we can ADD a new one (incremental sub-stages 3a, 4a...)
                    base_etap = etap_nr
                    if 30 < etap_nr < 50:
                        base_etap = etap_nr // 10
                        
                    if linia_u == 'AGRO' and base_etap in [3, 4]:
                        # Find next available suffix (3 -> 31 -> 32...)
                        base = base_etap
                        suffix = 1
                        while True:
                            check_etap = base * 10 + suffix
                            cursor.execute(
                                "SELECT id FROM zasyp_etapy WHERE linia=%s AND plan_id=%s AND szarza_nr=%s AND etap=%s",
                                (linia_u, int(plan_id), curr_szarza_nr, check_etap)
                            )
                            if not cursor.fetchone():
                                seq_extra = _build_sequence_for_szarza(linia_u, existing_etaps, include_etap=check_etap)
                                prev_extra, _ = _prev_next_etap_in_sequence(seq_extra, check_etap)
                                if prev_extra is not None:
                                    prev_extra_stop = (etap_times.get(prev_extra) or (None, None))[1]
                                    curr_extra_name = _etap_display_name(linia_u, check_etap)
                                    prev_extra_name = _etap_display_name(linia_u, prev_extra)
                                    if prev_extra_stop is None:
                                        return False, f'{curr_extra_name} nie może się rozpocząć przed zakończeniem: {prev_extra_name} (najpierw ustaw STOP)'
                                # This suffix is available
                                cursor.execute(
                                    """
                                    INSERT INTO zasyp_etapy (linia, plan_id, data_planu, szarza_nr, etap, czas_start, czas_stop, start_login, stop_login)
                                    VALUES (%s, %s, %s, %s, %s, NOW(), NULL, %s, NULL)
                                    """,
                                    (linia_u, int(plan_id), data_planu, curr_szarza_nr, check_etap, (user_login or '')[:100]),
                                )
                                conn.commit()
                                return True, f'Dodano kolejną sekcję: {check_etap}'
                            suffix += 1
                            if suffix > 9: break # limit to 9 extra stages
                        return False, 'Osiągnięto limit dodatkowych sekcji'
                    else:
                        return False, f'Etap {etap_nr} jest już zakończony'
                # exists but empty — set start
                else:
                    cursor.execute(
                        """
                        UPDATE zasyp_etapy
                        SET czas_start = NOW(), czas_stop = NULL, start_login = %s, stop_login = NULL
                        WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s
                        """,
                        ((user_login or '')[:100], linia_u, int(plan_id), curr_szarza_nr, etap_nr),
                    )
            else:
                cursor.execute(
                    """
                    INSERT INTO zasyp_etapy (linia, plan_id, data_planu, szarza_nr, etap, czas_start, czas_stop, start_login, stop_login)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NULL, %s, NULL)
                    """,
                    (linia_u, int(plan_id), data_planu, curr_szarza_nr, etap_nr, (user_login or '')[:100]),
                )

            conn.commit()
            return True, f'Start etapu {etap_nr} zapisany'
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False, 'Błąd startu etapu'
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    @staticmethod
    def advance_after_confirmed_dosypka(cursor, plan_id: int, batch_id: int, user_login: str) -> Optional[int]:
        """Stop mixing and start the addition in the caller's confirmation transaction."""
        cursor.execute(
            f"SELECT s.nr_szarzy FROM {get_table_name('szarze', 'AGRO')} s "
            f"JOIN {get_table_name('plan_produkcji', 'AGRO')} p ON p.id=s.plan_id "
            "WHERE s.id=%s AND s.plan_id=%s AND p.sekcja='Zasyp' AND p.status='w toku'",
            (int(batch_id), int(plan_id)),
        )
        batch = cursor.fetchone()
        if not batch or batch[0] is None:
            return None
        batch_number = int(batch[0])
        cursor.execute(
            "SELECT etap,czas_start,czas_stop,data_planu FROM zasyp_etapy "
            "WHERE linia='AGRO' AND plan_id=%s AND szarza_nr=%s FOR UPDATE",
            (int(plan_id), batch_number),
        )
        stages = cursor.fetchall() or []
        mixing = next((item for item in stages if (int(item[0]) == 2 or str(item[0]).startswith('4'))
                       and item[1] and not item[2]), None)
        if not mixing:
            return None
        cursor.execute(
            f"SELECT COUNT(*) FROM {get_table_name('dosypki', 'AGRO')} "
            "WHERE plan_id=%s AND szarza_id=%s AND potwierdzone=0 AND COALESCE(anulowana,0)=0 FOR UPDATE",
            (int(plan_id), int(batch_id)),
        )
        if cursor.fetchone()[0]:
            return None
        login = (user_login or '')[:100]
        pending_stage = next((int(item[0]) for item in stages
                              if str(item[0]).startswith('3') and not item[1] and not item[2]), None)
        if pending_stage is None:
            existing = {int(item[0]) for item in stages}
            suffixes = [_agro_suffix_for_etap(item) for item in existing]
            suffixes = [item for item in suffixes if item is not None]
            suffix = max(suffixes, default=0) + 1 if existing.intersection({3, 4}) or suffixes else 0
            pair = (3, 4) if suffix == 0 else (int(f'3{suffix}'), int(f'4{suffix}'))
            for new_stage in pair:
                cursor.execute(
                    "INSERT INTO zasyp_etapy (linia,plan_id,data_planu,szarza_nr,etap,start_login) "
                    "VALUES ('AGRO',%s,%s,%s,%s,%s)",
                    (int(plan_id), mixing[3], batch_number, new_stage, login),
                )
            pending_stage = pair[0]
        cursor.execute(
            "UPDATE zasyp_etapy SET czas_stop=NOW(),stop_login=%s "
            "WHERE linia='AGRO' AND plan_id=%s AND szarza_nr=%s AND etap=%s AND czas_stop IS NULL",
            (login, int(plan_id), batch_number, int(mixing[0])),
        )
        cursor.execute(
            "UPDATE zasyp_etapy SET czas_start=NOW(),start_login=%s "
            "WHERE linia='AGRO' AND plan_id=%s AND szarza_nr=%s AND etap=%s "
            "AND czas_start IS NULL AND czas_stop IS NULL",
            (login, int(plan_id), batch_number, pending_stage),
        )
        return pending_stage

    @staticmethod
    def stop_etap(plan_id: int, linia: str, etap: int, user_login: str, szarza_nr: Optional[int] = None, powod_opoznienia: Optional[str] = None) -> Tuple[bool, str]:
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
        except Exception:
            return False, 'Nieprawidłowy etap'
        if not _is_valid_etap_for_linia(etap_nr, linia_u):
            return False, 'Nieprawidłowy etap'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            curr_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                """
                SELECT czas_start, czas_stop
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s
                FOR UPDATE
                """,
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            row = cursor.fetchone()
            if not row:
                return False, f'Etap {etap_nr} nie ma START'

            czas_start, czas_stop = row[0], row[1]
            if not czas_start:
                return False, f'Etap {etap_nr} nie ma START'
            if czas_stop:
                return True, f'Etap {etap_nr} już jest STOP'

            if (linia_u == 'AGRO' and etap_nr == 5) or (linia_u != 'AGRO' and etap_nr == 6):
                table_dosypki = get_table_name('dosypki', linia_u)
                table_szarze = get_table_name('szarze', linia_u)
                cursor.execute(
                    f"SELECT d.potwierdzone FROM {table_dosypki} d "
                    f"JOIN {table_szarze} s ON s.id=d.szarza_id AND s.plan_id=d.plan_id "
                    "WHERE d.plan_id=%s AND s.nr_szarzy=%s AND COALESCE(d.anulowana,0)=0 FOR UPDATE",
                    (int(plan_id), curr_szarza_nr),
                )
                additions = cursor.fetchall() or []
                if any(not item[0] for item in additions):
                    conn.rollback()
                    return False, 'Najpierw potwierdź wszystkie dosypki przypisane do tego zasypu przed zakończeniem opróżniania.'

            cursor.execute(
                """
                UPDATE zasyp_etapy
                SET czas_stop = NOW(),
                    stop_login = %s,
                    powod_opoznienia = %s,
                    pauza_sekundy = COALESCE(pauza_sekundy, 0) + CASE
                        WHEN is_paused = 1 AND pauza_start IS NOT NULL THEN TIMESTAMPDIFF(SECOND, pauza_start, NOW())
                        ELSE 0
                    END,
                    pauza_start = NULL,
                    is_paused = 0
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s AND czas_stop IS NULL
                """,
                ((user_login or '')[:100], powod_opoznienia, linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            conn.commit()
            return True, f'Stop etapu {etap_nr} zapisany'
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False, 'Błąd stopu etapu'
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    @staticmethod
    def pause_etap(plan_id: int, linia: str, etap: int, user_login: str, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
        """Pauza trwającego etapu Zasyp."""
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
        except Exception:
            return False, 'Nieprawidłowy etap'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            curr_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                """
                SELECT czas_start, czas_stop, COALESCE(is_paused, 0)
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s
                """,
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return False, f'Etap {etap_nr} nie został rozpoczęty'
            if row[1]:
                return False, f'Etap {etap_nr} jest już zakończony'
            if row[2]:
                return True, f'Etap {etap_nr} jest już zapauzowany'

            cursor.execute(
                """
                UPDATE zasyp_etapy
                SET is_paused = 1, pauza_start = NOW()
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s AND czas_start IS NOT NULL AND czas_stop IS NULL
                """,
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            conn.commit()
            return True, f'Etap {etap_nr} został zapauzowany'
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False, f'Błąd pauzowania etapu: {e}'
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def resume_etap(plan_id: int, linia: str, etap: int, user_login: str, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
        """Wznowienie zapauzowanego etapu Zasyp."""
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
        except Exception:
            return False, 'Nieprawidłowy etap'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            curr_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                """
                SELECT czas_start, czas_stop, COALESCE(is_paused, 0), pauza_start, COALESCE(pauza_sekundy, 0)
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s
                """,
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return False, f'Etap {etap_nr} nie został rozpoczęty'
            if row[1]:
                return False, f'Etap {etap_nr} jest już zakończony'
            if not row[2]:
                return True, f'Etap {etap_nr} nie jest zapauzowany'

            cursor.execute(
                """
                UPDATE zasyp_etapy
                SET is_paused = 0,
                    pauza_sekundy = COALESCE(pauza_sekundy, 0) + CASE
                        WHEN pauza_start IS NOT NULL THEN TIMESTAMPDIFF(SECOND, pauza_start, NOW())
                        ELSE 0
                    END,
                    pauza_start = NULL
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s AND czas_start IS NOT NULL AND czas_stop IS NULL
                """,
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            conn.commit()
            return True, f'Wznowiono etap {etap_nr}'
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False, f'Błąd wznawiania etapu: {e}'
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def stop_any_running_etap(plan_id: int, linia: str, user_login: str, szarza_nr: Optional[int] = None) -> None:
        """Best-effort: stop any running etap for plan."""
        linia_u = _norm_linia(linia)
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            curr_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                """
                UPDATE zasyp_etapy
                SET czas_stop = NOW(),
                    stop_login = %s,
                    pauza_sekundy = COALESCE(pauza_sekundy, 0) + CASE
                        WHEN is_paused = 1 AND pauza_start IS NOT NULL THEN TIMESTAMPDIFF(SECOND, pauza_start, NOW())
                        ELSE 0
                    END,
                    pauza_start = NULL,
                    is_paused = 0
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND czas_start IS NOT NULL AND czas_stop IS NULL
                """,
                ((user_login or '')[:100], linia_u, int(plan_id), curr_szarza_nr),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

    @staticmethod
    def set_etap_manual_times(
        plan_id: int,
        linia: str,
        data_planu: date,
        etap: int,
        czas_start_hhmm: Optional[str],
        czas_stop_hhmm: Optional[str],
        user_login: str,
        szarza_nr: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Manual override of etap start/stop times (HH:MM on plan date).

        - Blank inputs mean "do not change".
        - Validates STOP >= START.
        - Prevents multiple running stages.
        """
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
        except Exception:
            return False, 'Nieprawidłowy etap'
        if not _is_valid_etap_for_linia(etap_nr, linia_u):
            return False, 'Nieprawidłowy etap'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            curr_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                """
                SELECT czas_start, czas_stop, start_login, stop_login
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s
                """,
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            row = cursor.fetchone()

            existing_start = row[0] if row else None
            existing_stop = row[1] if row else None
            existing_start_login = row[2] if row else None
            existing_stop_login = row[3] if row else None

            # Manual editing is allowed only for finished stages.
            if existing_stop is None:
                return False, 'Ręczna edycja czasu jest dozwolona tylko dla zakończonych etapów'

            ref_date = existing_start.date() if existing_start else (existing_stop.date() if existing_stop else data_planu)
            start_dt_in = _parse_hhmm_to_dt(ref_date, czas_start_hhmm)
            stop_dt_in = _parse_hhmm_to_dt(ref_date, czas_stop_hhmm)

            if czas_start_hhmm and start_dt_in is None:
                return False, 'Nieprawidłowy format START (HH:MM)'
            if czas_stop_hhmm and stop_dt_in is None:
                return False, 'Nieprawidłowy format STOP (HH:MM)'
            if start_dt_in is None and stop_dt_in is None:
                return False, 'Wpisz START i/lub STOP do zapisania'

            # Handle midnight crossover (e.g. 23:50 to 00:20)
            if start_dt_in and stop_dt_in and stop_dt_in < start_dt_in:
                from datetime import timedelta
                stop_dt_in = stop_dt_in + timedelta(days=1)

            now_dt = datetime.now()
            if ref_date == date.today():
                from datetime import timedelta
                allowed_max = now_dt + timedelta(minutes=5)
                if start_dt_in is not None and start_dt_in > allowed_max:
                    return False, 'START nie może być późniejszy niż aktualny czas'
                if stop_dt_in is not None and stop_dt_in > allowed_max:
                    return False, 'STOP nie może być późniejszy niż aktualny czas'

            new_start = start_dt_in if start_dt_in is not None else existing_start
            new_stop = stop_dt_in if stop_dt_in is not None else existing_stop

            if new_stop is not None and new_start is None:
                return False, 'Nie można ustawić STOP bez START'
            if new_start is not None and new_stop is not None and new_stop < new_start:
                return False, 'STOP nie może być wcześniejszy niż START'

            # Prevent two stages "running" at once.
            would_be_running = bool(new_start and not new_stop)
            if would_be_running:
                running = ZasypEtapyService._get_running_etap(cursor, plan_id, linia_u, curr_szarza_nr)
                if running is not None and running != etap_nr:
                    return False, f'Trwa już punkt kontrolny {running} — zakończ go przed ustawieniem etapu {etap_nr} jako W TOKU'

            # Determine login signatures for changed fields.
            start_login_val = existing_start_login
            if start_dt_in is not None:
                start_login_val = (user_login or '')[:100]
            if new_start is None:
                start_login_val = None

            stop_login_val = existing_stop_login
            if stop_dt_in is not None:
                stop_login_val = (user_login or '')[:100]
            if new_stop is None:
                stop_login_val = None

            cursor.execute(
                """
                INSERT INTO zasyp_etapy (linia, plan_id, data_planu, szarza_nr, etap, czas_start, czas_stop, start_login, stop_login)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    data_planu = VALUES(data_planu),
                    czas_start = VALUES(czas_start),
                    czas_stop = VALUES(czas_stop),
                    start_login = VALUES(start_login),
                    stop_login = VALUES(stop_login),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    linia_u,
                    int(plan_id),
                    ref_date,
                    curr_szarza_nr,
                    etap_nr,
                    new_start,
                    new_stop,
                    start_login_val,
                    stop_login_val,
                ),
            )
            conn.commit()
            return True, f'Zapisano czasy etapu {etap_nr}'
        except Exception:
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            return False, 'Błąd zapisu czasów etapu'
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    @staticmethod
    def reset_etap(plan_id: int, linia: str, etap: int, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
        """Reset etap times/signatures without deleting the etap row."""
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
        except Exception:
            return False, 'Nieprawidłowy etap'
        if not _is_valid_etap_for_linia(etap_nr, linia_u):
            return False, 'Nieprawidłowy etap'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            curr_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                "SELECT id FROM zasyp_etapy WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s LIMIT 1",
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            row = cursor.fetchone()

            if not row:
                conn.commit()
                return True, f'Etap {etap_nr} już był zresetowany'

            cursor.execute(
                """
                UPDATE zasyp_etapy
                SET czas_start = NULL,
                    czas_stop = NULL,
                    start_login = NULL,
                    stop_login = NULL,
                    is_paused = 0,
                    pauza_start = NULL,
                    pauza_sekundy = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s
                """,
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )

            conn.commit()
            return True, f'Zresetowano etap {etap_nr}'
        except Exception:
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            return False, 'Błąd resetu etapu'
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    @staticmethod
    def delete_etap(plan_id: int, linia: str, etap: int, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
        """Permanently delete etap row (specifically for sub-stages)."""
        # Logic is the same as reset, but with a different message
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
            conn = get_db_connection()
            cursor = conn.cursor()
            curr_szarza_nr = ZasypEtapyService._resolve_szarza_nr(cursor, plan_id, linia_u, szarza_nr)

            cursor.execute(
                "DELETE FROM zasyp_etapy WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s",
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )

            # AGRO pairs are non-separable: deleting one side also deletes its pair.
            # Supported pairs: 3<->4, 31<->41, 32<->42, ...
            paired_etap = None
            if linia_u == 'AGRO':
                if etap_nr == 3:
                    paired_etap = 4
                elif etap_nr == 4:
                    paired_etap = 3
                elif 30 < etap_nr < 40:
                    paired_etap = etap_nr + 10
                elif 40 < etap_nr < 50:
                    paired_etap = etap_nr - 10

            if paired_etap is not None:
                cursor.execute(
                    "DELETE FROM zasyp_etapy WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s",
                    (linia_u, int(plan_id), curr_szarza_nr, paired_etap),
                )
                
            conn.commit()
            cursor.close()
            conn.close()
            return True, f'Usunięto etap {etap_nr}'
        except Exception:
            return False, 'Błąd usuwania etapu'
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    @staticmethod
    def get_plan_stats(plan_id: int, linia: str) -> Dict[str, Any]:
        """Return counts/sums used in the Zasyp panel (szarże + dosypki)."""
        linia_u = _norm_linia(linia)
        table_szarze = get_table_name('szarze', linia_u)
        table_dosypki = get_table_name('dosypki', linia_u)

        out = {
            'szarze_count': 0,
            'szarze_kg': 0.0,
            'dosypki_count': 0,
            'dosypki_kg': 0.0,
            'dosypki_pending_count': 0,
        }

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                f"SELECT COUNT(*), COALESCE(SUM(waga), 0) FROM {table_szarze} WHERE plan_id=%s",
                (int(plan_id),),
            )
            r = cursor.fetchone()
            if r:
                out['szarze_count'] = int(r[0] or 0)
                out['szarze_kg'] = float(r[1] or 0.0)

            cursor.execute(
                f"""
                SELECT COUNT(*), COALESCE(SUM(kg), 0)
                FROM {table_dosypki}
                WHERE plan_id=%s AND potwierdzone=1 AND COALESCE(anulowana, 0)=0
                """,
                (int(plan_id),),
            )
            r = cursor.fetchone()
            if r:
                out['dosypki_count'] = int(r[0] or 0)
                out['dosypki_kg'] = float(r[1] or 0.0)

            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM {table_dosypki}
                WHERE plan_id=%s AND potwierdzone=0 AND COALESCE(anulowana, 0)=0
                """,
                (int(plan_id),),
            )
            r = cursor.fetchone()
            if r:
                out['dosypki_pending_count'] = int(r[0] or 0)

            cursor.close()
            conn.close()
        except Exception:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

        return out

    @staticmethod
    def get_summary(d_od: date, d_do: date, linia: str) -> List[Dict[str, Any]]:
        """Aggregate etap durations per date (plus szarże/dosypki totals for tracked plans)."""
        linia_u = _norm_linia(linia)

        # 1) Etapy durations per date
        etap_rows: Dict[str, Dict[str, Any]] = {}
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    data_planu,
                    COUNT(DISTINCT plan_id) AS tracked_zlecen,
                    SUM(CASE WHEN etap = 1 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS etap1_s,
                    SUM(CASE WHEN etap = 2 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS etap2_s,
                    SUM(CASE WHEN etap = 3 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS etap3_s,
                    SUM(CASE WHEN etap = 4 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS etap4_s,
                    SUM(CASE WHEN etap = 5 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS etap5_s,
                    SUM(CASE WHEN etap = 6 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS etap6_s,
                    SUM(TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW()))) AS total_s
                FROM zasyp_etapy
                WHERE linia = %s AND data_planu BETWEEN %s AND %s AND czas_start IS NOT NULL
                GROUP BY data_planu
                ORDER BY data_planu DESC
                """,
                (linia_u, d_od, d_do),
            )
            for r in cursor.fetchall() or []:
                d = r[0]
                key = d.isoformat() if hasattr(d, 'isoformat') else str(d)
                etap_rows[key] = {
                    'data': d,
                    'tracked_zlecen': int(r[1] or 0),
                    'etap_s': [
                        int(r[2] or 0),
                        int(r[3] or 0),
                        int(r[4] or 0),
                        int(r[5] or 0),
                        int(r[6] or 0),
                        int(r[7] or 0),
                    ],
                    'total_s': int(r[8] or 0),
                }
            cursor.close()
            conn.close()
        except Exception:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

        # 2) Production totals (szarże + confirmed dosypki) for tracked plans
        prod_rows: Dict[str, Dict[str, Any]] = {}
        table_szarze = get_table_name('szarze', linia_u)
        table_dosypki = get_table_name('dosypki', linia_u)

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT
                    t.data_planu,
                    COALESCE(SUM(COALESCE(sz.szarze_kg, 0)), 0) AS szarze_kg,
                    COALESCE(SUM(COALESCE(sz.szarze_count, 0)), 0) AS szarze_count,
                    COALESCE(SUM(COALESCE(d.dosypki_kg, 0)), 0) AS dosypki_kg,
                    COALESCE(SUM(COALESCE(d.dosypki_count, 0)), 0) AS dosypki_count
                FROM (
                    SELECT DISTINCT plan_id, data_planu
                    FROM zasyp_etapy
                    WHERE linia = %s AND data_planu BETWEEN %s AND %s AND czas_start IS NOT NULL
                ) t
                LEFT JOIN (
                    SELECT plan_id, COALESCE(SUM(waga), 0) AS szarze_kg, COUNT(*) AS szarze_count
                    FROM {table_szarze}
                    GROUP BY plan_id
                ) sz ON sz.plan_id = t.plan_id
                LEFT JOIN (
                    SELECT plan_id,
                           COALESCE(SUM(kg), 0) AS dosypki_kg,
                           COUNT(*) AS dosypki_count
                    FROM {table_dosypki}
                    WHERE potwierdzone = 1 AND COALESCE(anulowana, 0) = 0
                    GROUP BY plan_id
                ) d ON d.plan_id = t.plan_id
                GROUP BY t.data_planu
                ORDER BY t.data_planu DESC
                """,
                (linia_u, d_od, d_do),
            )
            for r in cursor.fetchall() or []:
                d = r[0]
                key = d.isoformat() if hasattr(d, 'isoformat') else str(d)
                prod_rows[key] = {
                    'szarze_kg': float(r[1] or 0.0),
                    'szarze_count': int(r[2] or 0),
                    'dosypki_kg': float(r[3] or 0.0),
                    'dosypki_count': int(r[4] or 0),
                }
            cursor.close()
            conn.close()
        except Exception:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

        # 3) Merge by date
        merged: List[Dict[str, Any]] = []
        for key, r in etap_rows.items():
            pr = prod_rows.get(key) or {
                'szarze_kg': 0.0,
                'szarze_count': 0,
                'dosypki_kg': 0.0,
                'dosypki_count': 0,
            }

            total_s = int(r.get('total_s') or 0)
            total_kg = float(pr.get('szarze_kg') or 0.0) + float(pr.get('dosypki_kg') or 0.0)
            kg_h = (total_kg / (total_s / 3600.0)) if total_s > 0 else 0.0
            kg_h_elapsed = (total_kg / 8.0) if total_kg > 0 else 0.0

            merged.append(
                {
                    'data': r.get('data'),
                    'data_str': key,
                    'tracked_zlecen': int(r.get('tracked_zlecen') or 0),
                    'etap_s': r.get('etap_s') or [0, 0, 0, 0, 0, 0],
                    'etap_str': [_format_duration(int(s or 0)) for s in (r.get('etap_s') or [])],
                    'total_s': total_s,
                    'total_str': _format_duration(total_s),
                    'szarze_count': int(pr.get('szarze_count') or 0),
                    'szarze_kg': float(pr.get('szarze_kg') or 0.0),
                    'dosypki_count': int(pr.get('dosypki_count') or 0),
                    'dosypki_kg': float(pr.get('dosypki_kg') or 0.0),
                    'total_kg': total_kg,
                    'kg_h': kg_h,
                    'kg_h_elapsed': kg_h_elapsed,
                }
            )

        return merged

    @staticmethod
    def get_zlecenia_summary(d_od: date, d_do: date, linia: str) -> List[Dict[str, Any]]:
        """Aggregate etap durations and production per ZLECENIE (plan_id)."""
        linia_u = _norm_linia(linia)
        table_plan = get_table_name('plan_produkcji', linia_u)
        table_szarze = get_table_name('szarze', linia_u)
        table_dosypki = get_table_name('dosypki', linia_u)
        
        conn = None
        merged: List[Dict[str, Any]] = []
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"""
                SELECT 
                    z.plan_id, p.produkt, p.data_planu, p.real_start, p.real_stop,
                    SUM(CASE WHEN z.etap = 1 THEN TIMESTAMPDIFF(SECOND, z.czas_start, COALESCE(z.czas_stop, NOW())) ELSE 0 END) AS e1,
                    SUM(CASE WHEN z.etap = 2 THEN TIMESTAMPDIFF(SECOND, z.czas_start, COALESCE(z.czas_stop, NOW())) ELSE 0 END) AS e2,
                    SUM(CASE WHEN z.etap = 3 THEN TIMESTAMPDIFF(SECOND, z.czas_start, COALESCE(z.czas_stop, NOW())) ELSE 0 END) AS e3,
                    SUM(CASE WHEN z.etap = 4 THEN TIMESTAMPDIFF(SECOND, z.czas_start, COALESCE(z.czas_stop, NOW())) ELSE 0 END) AS e4,
                    SUM(CASE WHEN z.etap = 5 THEN TIMESTAMPDIFF(SECOND, z.czas_start, COALESCE(z.czas_stop, NOW())) ELSE 0 END) AS e5,
                    SUM(CASE WHEN z.etap = 6 THEN TIMESTAMPDIFF(SECOND, z.czas_start, COALESCE(z.czas_stop, NOW())) ELSE 0 END) AS e6,
                    SUM(TIMESTAMPDIFF(SECOND, z.czas_start, COALESCE(z.czas_stop, NOW()))) AS total_s
                FROM zasyp_etapy z
                JOIN {table_plan} p ON z.plan_id = p.id
                WHERE z.linia = %s AND z.data_planu BETWEEN %s AND %s AND z.czas_start IS NOT NULL
                GROUP BY z.plan_id
                ORDER BY p.data_planu DESC, z.plan_id DESC
            """, (linia_u, d_od, d_do))
            zlecenia = cursor.fetchall() or []
            
            now_dt = datetime.now()
            for r in zlecenia:
                plan_id = r.get('plan_id')
                cursor.execute(f"SELECT COUNT(*), COALESCE(SUM(waga),0) FROM {table_szarze} WHERE plan_id=%s", (plan_id,))
                sz = cursor.fetchone()
                
                cursor.execute(f"SELECT COUNT(*), COALESCE(SUM(kg),0) FROM {table_dosypki} WHERE plan_id=%s AND potwierdzone=1 AND COALESCE(anulowana,0)=0", (plan_id,))
                dos = cursor.fetchone()
                
                sz_kg = float(sz['COALESCE(SUM(waga),0)'] if isinstance(sz, dict) else sz[1])
                dos_kg = float(dos['COALESCE(SUM(kg),0)'] if isinstance(dos, dict) else dos[1])
                total_kg = sz_kg + dos_kg
                total_s = int(r.get('total_s') or 0)
                kg_h = (total_kg / (total_s / 3600.0)) if total_s > 0 else 0.0

                # elapsed (real) time since plan real_start until real_stop (or now if running)
                kg_h_elapsed = None
                try:
                    real_start = r.get('real_start')
                    real_stop = r.get('real_stop')
                    if total_kg > 0 and real_start:
                        end_dt = real_stop or now_dt
                        elapsed_hours = max(0.0, (end_dt - real_start).total_seconds() / 3600.0)
                        if elapsed_hours > 0:
                            kg_h_elapsed = total_kg / elapsed_hours
                except Exception:
                    kg_h_elapsed = None

                cursor.execute("""
                    SELECT szarza_nr, 
                        SUM(CASE WHEN etap = 1 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS e1,
                        SUM(CASE WHEN etap = 2 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS e2,
                        SUM(CASE WHEN etap = 3 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS e3,
                        SUM(CASE WHEN etap = 4 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS e4,
                        SUM(CASE WHEN etap = 5 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS e5,
                        SUM(CASE WHEN etap = 6 THEN TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW())) ELSE 0 END) AS e6,
                        SUM(TIMESTAMPDIFF(SECOND, czas_start, COALESCE(czas_stop, NOW()))) AS total_s
                    FROM zasyp_etapy
                    WHERE linia=%s AND plan_id=%s AND czas_start IS NOT NULL AND etap > 0
                    GROUP BY szarza_nr ORDER BY szarza_nr ASC
                """, (linia_u, plan_id))
                
                szarze_det = []
                for s_row in cursor.fetchall():
                    szarze_det.append({
                        'szarza_nr': s_row.get('szarza_nr'),
                        'e1': _format_duration(int(s_row.get('e1') or 0)),
                        'e2': _format_duration(int(s_row.get('e2') or 0)),
                        'e3': _format_duration(int(s_row.get('e3') or 0)),
                        'e4': _format_duration(int(s_row.get('e4') or 0)),
                        'e5': _format_duration(int(s_row.get('e5') or 0)),
                        'e6': _format_duration(int(s_row.get('e6') or 0)),
                        'total_str': _format_duration(int(s_row.get('total_s') or 0))
                    })
                
                avg_szarza_str = _format_duration(int(total_s / len(szarze_det))) if len(szarze_det) > 0 else "0m"
                
                merged.append({
                    'plan_id': plan_id,
                    'produkt': r.get('produkt'),
                    'data_planu': r.get('data_planu'),
                    'etap_s': [
                        int(r.get('e1') or 0),
                        int(r.get('e2') or 0),
                        int(r.get('e3') or 0),
                        int(r.get('e4') or 0),
                        int(r.get('e5') or 0),
                        int(r.get('e6') or 0),
                    ],
                    'etap_str': [
                        _format_duration(int(r.get('e1') or 0)),
                        _format_duration(int(r.get('e2') or 0)),
                        _format_duration(int(r.get('e3') or 0)),
                        _format_duration(int(r.get('e4') or 0)),
                        _format_duration(int(r.get('e5') or 0)),
                        _format_duration(int(r.get('e6') or 0)),
                    ],
                    'total_str': _format_duration(total_s),
                    'szarze_count': int(sz['COUNT(*)'] if isinstance(sz, dict) else sz[0]),
                    'szarze_kg': sz_kg,
                    'dosypki_count': int(dos['COUNT(*)'] if isinstance(dos, dict) else dos[0]),
                    'dosypki_kg': dos_kg,
                    'total_kg': total_kg,
                    'kg_h': kg_h,
                    'kg_h_elapsed': kg_h_elapsed,
                    'avg_szarza_str': avg_szarza_str,
                    'szarze_det': szarze_det
                })
        except Exception:
            pass
        finally:
            if conn:
                try: conn.close()
                except: pass
        return merged
