from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple

from app.db import get_db_connection, get_table_name


ETAP_MIN = 1
ETAP_MAX = 6


def _norm_linia(linia: Optional[str]) -> str:
    l = str(linia or 'PSD').upper()
    return 'AGRO' if l == 'AGRO' else 'PSD'


def _format_hhmm(dt: Any) -> str:
    if not dt:
        return ''
    try:
        return dt.strftime('%H:%M')
    except Exception:
        # Fallback: try simple string slice
        try:
            s = str(dt)
            if ' ' in s and ':' in s:
                # YYYY-MM-DD HH:MM:SS -> HH:MM
                return s.split(' ')[1][:5]
            if ':' in s:
                return s[:5]
        except Exception:
            pass
    return ''


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return '0m'
    mins = seconds // 60
    h = mins // 60
    m = mins % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def _parse_hhmm_to_dt(d: date, hhmm: Optional[str]) -> Optional[datetime]:
    s = str(hhmm or '').strip()
    if not s:
        return None
    s = s.replace('.', ':')
    parts = s.split(':')
    if len(parts) < 2:
        return None
    try:
        h = int(parts[0])
        m = int(parts[1])
    except Exception:
        return None
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    try:
        return datetime.combine(d, time(hour=h, minute=m))
    except Exception:
        return None


@dataclass(frozen=True)
class EtapRow:
    etap: int
    czas_start: Optional[datetime]
    czas_stop: Optional[datetime]
    start_login: Optional[str]
    stop_login: Optional[str]


class ZasypEtapyService:
    @staticmethod
    def get_etapy(plan_id: int, linia: str) -> Dict[str, Any]:
        """Return etap 1..6 status for a given Zasyp plan.

        Safe-by-default: on any DB error, returns empty (all stages unset).
        """
        linia_u = _norm_linia(linia)
        etapy_by_nr: Dict[int, EtapRow] = {}

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT MAX(szarza_nr) as c FROM zasyp_etapy WHERE linia=%s AND plan_id=%s", (linia_u, int(plan_id)))
            r_sz = cursor.fetchone()
            curr_szarza_nr = r_sz.get('c') if r_sz and r_sz.get('c') else 1
            cursor.execute(
                """
                SELECT etap, czas_start, czas_stop, start_login, stop_login
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s
                ORDER BY etap ASC
                """,
                (linia_u, int(plan_id), curr_szarza_nr),
            )
            for r in cursor.fetchall() or []:
                try:
                    etap_nr = int(r.get('etap'))
                except Exception:
                    continue
                etapy_by_nr[etap_nr] = EtapRow(
                    etap=etap_nr,
                    czas_start=r.get('czas_start'),
                    czas_stop=r.get('czas_stop'),
                    start_login=r.get('start_login'),
                    stop_login=r.get('stop_login'),
                )
            cursor.close()
            conn.close()
        except Exception:
            etapy_by_nr = {}

        now = datetime.now()
        out: List[Dict[str, Any]] = []
        active_etap: Optional[int] = None
        total_s = 0

        for etap_nr in range(ETAP_MIN, ETAP_MAX + 1):
            row = etapy_by_nr.get(etap_nr)
            start_dt = row.czas_start if row else None
            stop_dt = row.czas_stop if row else None
            is_running = bool(start_dt and not stop_dt)
            if is_running:
                active_etap = etap_nr

            dur_s = 0
            if start_dt:
                end_dt = stop_dt or now
                try:
                    dur_s = int((end_dt - start_dt).total_seconds())
                except Exception:
                    dur_s = 0
            if dur_s < 0:
                dur_s = 0

            total_s += dur_s
            out.append(
                {
                    'etap': etap_nr,
                    'czas_start': start_dt,
                    'czas_stop': stop_dt,
                    'czas_start_str': _format_hhmm(start_dt),
                    'czas_stop_str': _format_hhmm(stop_dt),
                    'duration_s': dur_s,
                    'duration_str': _format_duration(dur_s),
                    'is_running': is_running,
                    'start_login': (row.start_login if row else None) or '',
                    'stop_login': (row.stop_login if row else None) or '',
                }
            )

        return {
            'plan_id': int(plan_id),
            'linia': linia_u,
            'active_etap': active_etap,
            'total_duration_s': total_s,
            'total_duration_str': _format_duration(total_s),
            'etapy': out,
            'curr_szarza_nr': curr_szarza_nr,
        }

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
            return True, f"Przełączono pomiar na szarżę #{new_nr}"
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
                    return False, 'Wielkość szarży musi być > 0'

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
            return True, 'Zapisano wielkość szarży'
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
            return False, 'Błąd zapisu wielkości szarży'

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
    def start_etap(plan_id: int, linia: str, data_planu: date, etap: int, user_login: str) -> Tuple[bool, str]:
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
        except Exception:
            return False, 'Nieprawidłowy etap'
        if etap_nr < ETAP_MIN or etap_nr > ETAP_MAX:
            return False, 'Nieprawidłowy etap'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(szarza_nr) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s", (linia_u, int(plan_id)))
            r_sz = cursor.fetchone()
            curr_szarza_nr = r_sz[0] if r_sz and r_sz[0] else 1

            running = ZasypEtapyService._get_running_etap(cursor, plan_id, linia_u, curr_szarza_nr)
            if running is not None and running != etap_nr:
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
                    return False, f'Etap {etap_nr} jest już zakończony'
                # exists but empty — set start
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
    def stop_etap(plan_id: int, linia: str, etap: int, user_login: str) -> Tuple[bool, str]:
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
        except Exception:
            return False, 'Nieprawidłowy etap'
        if etap_nr < ETAP_MIN or etap_nr > ETAP_MAX:
            return False, 'Nieprawidłowy etap'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(szarza_nr) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s", (linia_u, int(plan_id)))
            r_sz = cursor.fetchone()
            curr_szarza_nr = r_sz[0] if r_sz and r_sz[0] else 1

            cursor.execute(
                """
                SELECT czas_start, czas_stop
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s
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

            cursor.execute(
                """
                UPDATE zasyp_etapy
                SET czas_stop = NOW(), stop_login = %s
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s AND czas_stop IS NULL
                """,
                ((user_login or '')[:100], linia_u, int(plan_id), curr_szarza_nr, etap_nr),
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
    def stop_any_running_etap(plan_id: int, linia: str, user_login: str) -> None:
        """Best-effort: stop any running etap for plan."""
        linia_u = _norm_linia(linia)
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(szarza_nr) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s", (linia_u, int(plan_id)))
            r_sz = cursor.fetchone()
            curr_szarza_nr = r_sz[0] if r_sz and r_sz[0] else 1

            cursor.execute(
                """
                UPDATE zasyp_etapy
                SET czas_stop = NOW(), stop_login = %s
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
        if etap_nr < ETAP_MIN or etap_nr > ETAP_MAX:
            return False, 'Nieprawidłowy etap'

        start_dt_in = _parse_hhmm_to_dt(data_planu, czas_start_hhmm)
        stop_dt_in = _parse_hhmm_to_dt(data_planu, czas_stop_hhmm)
        if czas_start_hhmm and start_dt_in is None:
            return False, 'Nieprawidłowy format START (HH:MM)'
        if czas_stop_hhmm and stop_dt_in is None:
            return False, 'Nieprawidłowy format STOP (HH:MM)'

        if start_dt_in is None and stop_dt_in is None:
            return False, 'Wpisz START i/lub STOP do zapisania'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(szarza_nr) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s", (linia_u, int(plan_id)))
            r_sz = cursor.fetchone()
            curr_szarza_nr = r_sz[0] if r_sz and r_sz[0] else 1

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
                    data_planu,
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
    def reset_etap(plan_id: int, linia: str, etap: int) -> Tuple[bool, str]:
        """Delete etap row (clears manual/auto times and signatures)."""
        linia_u = _norm_linia(linia)
        try:
            etap_nr = int(etap)
        except Exception:
            return False, 'Nieprawidłowy etap'
        if etap_nr < ETAP_MIN or etap_nr > ETAP_MAX:
            return False, 'Nieprawidłowy etap'

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            table_szarze = get_table_name('szarze', linia_u)
            cursor.execute(f"SELECT COUNT(*) FROM {table_szarze} WHERE plan_id=%s", (int(plan_id),))
            r_sz = cursor.fetchone()
            curr_szarza_nr = (r_sz[0] if r_sz else 0) + 1

            cursor.execute(
                "DELETE FROM zasyp_etapy WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s",
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
                    z.plan_id, p.produkt, p.data_planu,
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
