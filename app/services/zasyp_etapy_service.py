from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple

from app.db import get_db_connection, get_table_name


ETAP_MIN = 1
ETAP_MAX = 6


def _visible_etaps_for_linia(linia: str) -> List[int]:
    if _norm_linia(linia) == 'AGRO':
        # AGRO: 1,2,3,4,5 (continuous sequence)
        return [1, 2, 3, 4, 5]
    return list(range(ETAP_MIN, ETAP_MAX + 1))


def _is_valid_etap_for_linia(etap_nr: int, linia: str) -> bool:
    linia_u = _norm_linia(linia)
    if linia_u == 'AGRO':
        if etap_nr in [1, 2, 3, 4, 5]:
            return True
        # Allow sub-stages like 31/41, 310/410, 311/411... for unlimited cycles.
        try:
            etap_s = str(int(etap_nr))
            if len(etap_s) > 1 and etap_s[0] in ['3', '4']:
                return True
        except Exception:
            pass
        return False
    return etap_nr in _visible_etaps_for_linia(linia)


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
    sec = int(seconds)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


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


def _agro_suffix_for_etap(etap_nr: int) -> Optional[int]:
    try:
        s = str(int(etap_nr))
    except Exception:
        return None
    if len(s) > 1 and s[0] in ['3', '4']:
        try:
            return int(s[1:])
        except Exception:
            return None
    return None


def _build_sequence_for_szarza(linia_u: str, existing_etaps: List[int], include_etap: Optional[int] = None) -> List[int]:
    if linia_u != 'AGRO':
        return list(range(ETAP_MIN, ETAP_MAX + 1))

    suffixes: set[int] = set()
    for e in existing_etaps:
        suf = _agro_suffix_for_etap(e)
        if suf is not None:
            suffixes.add(suf)
    if include_etap is not None:
        suf = _agro_suffix_for_etap(include_etap)
        if suf is not None:
            suffixes.add(suf)

    ordered: List[int] = [1, 2, 3, 4]
    for suf in sorted(suffixes):
        ordered.append(int(f'3{suf}'))
        ordered.append(int(f'4{suf}'))
    ordered.append(5)

    # Deduplicate while preserving order.
    out: List[int] = []
    seen: set[int] = set()
    for e in ordered:
        if e in seen:
            continue
        seen.add(e)
        out.append(e)
    return out


def _prev_next_etap_in_sequence(seq: List[int], etap_nr: int) -> Tuple[Optional[int], Optional[int]]:
    try:
        idx = seq.index(int(etap_nr))
    except Exception:
        return None, None
    prev_etap = seq[idx - 1] if idx > 0 else None
    next_etap = seq[idx + 1] if idx + 1 < len(seq) else None
    return prev_etap, next_etap


def _etap_display_name(linia_u: str, etap_nr: int) -> str:
    e = int(etap_nr)
    if linia_u == 'AGRO':
        if e == 1:
            return 'Naważanie'
        if e == 2:
            return 'Mieszanie i oczekiwanie na LAB'
        if e == 3:
            return 'Dosypka'
        if e == 4:
            return 'Mieszanie i oczekiwanie na LAB po dosypce'
        if e == 5:
            return 'Opróżnianie'
        if 30 < e < 40:
            return f'Dosypka ({e})'
        if 40 < e < 50:
            return f'Mieszanie po dosypce ({e})'
        return f'Etap {e}'

    if e == 1:
        return 'Naważanie'
    if e == 2:
        return 'Mieszanie'
    if e == 3:
        return 'Oczekiwanie na LAB'
    if e == 4:
        return 'Dosypka'
    if e == 5:
        return 'Mieszanie'
    if e == 6:
        return 'Opróżnianie'
    return f'Etap {e}'


@dataclass(frozen=True)
class EtapRow:
    etap: int
    czas_start: Optional[datetime]
    czas_stop: Optional[datetime]
    start_login: Optional[str]
    stop_login: Optional[str]


class ZasypEtapyService:
    @staticmethod
    def _max_szarza_from_batches(cursor, plan_id: int, linia_u: str) -> int:
        """Return max batch number from szarze table (fallback when zasyp_etapy is empty)."""
        table_szarze = get_table_name('szarze', linia_u)
        cursor.execute(
            f"SELECT COALESCE(MAX(COALESCE(nr_szarzy, 1)), 0) FROM {table_szarze} WHERE plan_id=%s",
            (int(plan_id),),
        )
        row = cursor.fetchone()
        try:
            value = int(row[0] if row else 0)
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
            "SELECT COALESCE(MAX(szarza_nr), 1) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s",
            (linia_u, int(plan_id)),
        )
        row = cursor.fetchone()
        try:
            resolved = int(row[0] if row else 1)
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
            SELECT DISTINCT szarza_nr
            FROM zasyp_etapy
            WHERE linia=%s AND plan_id=%s
            ORDER BY szarza_nr DESC
            """,
            (linia_u, int(plan_id)),
        )
        out: List[int] = []
        for row in cursor.fetchall() or []:
            try:
                out.append(int(row[0] if isinstance(row, (tuple, list)) else row.get('szarza_nr')))
            except Exception:
                continue
        if out:
            return out

        batch_nr = ZasypEtapyService._max_szarza_from_batches(cursor, plan_id, linia_u)
        return [batch_nr] if batch_nr > 0 else [1]

    @staticmethod
    def _load_etapy_rows(cursor, plan_id: int, linia_u: str, szarza_nr: int) -> Dict[int, EtapRow]:
        etapy_by_nr: Dict[int, EtapRow] = {}
        cursor.execute(
            """
            SELECT etap, czas_start, czas_stop, start_login, stop_login
            FROM zasyp_etapy
            WHERE linia = %s AND plan_id = %s AND szarza_nr = %s
            ORDER BY etap ASC
            """,
            (linia_u, int(plan_id), int(szarza_nr)),
        )
        for r in cursor.fetchall() or []:
            try:
                etap_nr = int(r.get('etap') if isinstance(r, dict) else r[0])
            except Exception:
                continue
            etapy_by_nr[etap_nr] = EtapRow(
                etap=etap_nr,
                czas_start=(r.get('czas_start') if isinstance(r, dict) else r[1]),
                czas_stop=(r.get('czas_stop') if isinstance(r, dict) else r[2]),
                start_login=(r.get('start_login') if isinstance(r, dict) else r[3]),
                stop_login=(r.get('stop_login') if isinstance(r, dict) else r[4]),
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
            to_process = base_etaps

        for etap_nr in to_process:
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
                    'exists': row is not None,
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
            'szarza_nr': int(szarza_nr),
            'active_etap': active_etap,
            'has_running': active_etap is not None,
            'total_duration_s': total_s,
            'total_duration_str': _format_duration(total_s),
            'etapy': out,
            'curr_szarza_nr': int(szarza_nr),
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
        except Exception:
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
        except Exception:
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
                return False, f'Punkt kontrolny szarży #{target_szarza_nr} jest już pusty'

            # Keep realized tonnage consistent after removing a batch.
            table_plan = get_table_name('plan_produkcji', linia_u)
            table_dosypki = get_table_name('dosypki', linia_u)
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id=%s), 0) + "
                f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id=%s AND potwierdzone=1 AND COALESCE(anulowana, 0)=0), 0) "
                "WHERE id=%s",
                (int(plan_id), int(plan_id), int(plan_id)),
            )
            conn.commit()

            if deleted_etapy > 0 and deleted_szarze > 0:
                return True, f'Usunięto cały punkt kontrolny szarży #{target_szarza_nr}'
            if deleted_szarze > 0:
                return True, f'Usunięto szarżę #{target_szarza_nr} i odświeżono punkt kontrolny'
            return True, f'Usunięto wpisy punktu kontrolnego szarży #{target_szarza_nr}'
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
    def start_etap(plan_id: int, linia: str, data_planu: date, etap: int, user_login: str, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
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
            if prev_etap is not None:
                prev_stop = (etap_times.get(prev_etap) or (None, None))[1]
                curr_name = _etap_display_name(linia_u, etap_nr)
                prev_name = _etap_display_name(linia_u, prev_etap)
                if prev_stop is None:
                    return False, f'{curr_name} nie może się rozpocząć przed zakończeniem: {prev_name} (najpierw ustaw STOP)'
                if prev_stop > datetime.now():
                    return False, f'{curr_name} może rozpocząć się najwcześniej o {_format_hhmm(prev_stop)} (po STOP: {prev_name})'

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
                                    if prev_extra_stop > datetime.now():
                                        return False, f'{curr_extra_name} może rozpocząć się najwcześniej o {_format_hhmm(prev_extra_stop)} (po STOP: {prev_extra_name})'
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
    def stop_etap(plan_id: int, linia: str, etap: int, user_login: str, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
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

        start_dt_in = _parse_hhmm_to_dt(data_planu, czas_start_hhmm)
        stop_dt_in = _parse_hhmm_to_dt(data_planu, czas_stop_hhmm)
        if czas_start_hhmm and start_dt_in is None:
            return False, 'Nieprawidłowy format START (HH:MM)'
        if czas_stop_hhmm and stop_dt_in is None:
            return False, 'Nieprawidłowy format STOP (HH:MM)'

        now_dt = datetime.now()
        if start_dt_in is not None and start_dt_in > now_dt:
            return False, 'START nie może być późniejszy niż aktualny czas'
        if stop_dt_in is not None and stop_dt_in > now_dt:
            return False, 'STOP nie może być późniejszy niż aktualny czas'

        if start_dt_in is None and stop_dt_in is None:
            return False, 'Wpisz START i/lub STOP do zapisania'

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

            new_start = start_dt_in if start_dt_in is not None else existing_start
            new_stop = stop_dt_in if stop_dt_in is not None else existing_stop

            if new_stop is not None and new_start is None:
                return False, 'Nie można ustawić STOP bez START'
            if new_start is not None and new_stop is not None and new_stop < new_start:
                return False, 'STOP nie może być wcześniejszy niż START'

            cursor.execute(
                """
                SELECT etap, czas_start, czas_stop
                FROM zasyp_etapy
                WHERE linia = %s AND plan_id = %s AND szarza_nr = %s
                """,
                (linia_u, int(plan_id), curr_szarza_nr),
            )
            seq_rows = cursor.fetchall() or []
            etap_times: Dict[int, Tuple[Optional[datetime], Optional[datetime]]] = {}
            existing_etaps: List[int] = []
            for r in seq_rows:
                try:
                    e = int(r[0] if isinstance(r, (tuple, list)) else r.get('etap'))
                except Exception:
                    continue
                existing_etaps.append(e)
                start_dt = r[1] if isinstance(r, (tuple, list)) else r.get('czas_start')
                stop_dt = r[2] if isinstance(r, (tuple, list)) else r.get('czas_stop')
                etap_times[e] = (start_dt, stop_dt)

            seq = _build_sequence_for_szarza(linia_u, existing_etaps, include_etap=etap_nr)
            prev_etap, next_etap = None, None
            try:
                idx = seq.index(int(etap_nr))
                for i in range(idx - 1, -1, -1):
                    pe = seq[i]
                    if pe in etap_times:
                        prev_etap = pe
                        break
                for i in range(idx + 1, len(seq)):
                    ne = seq[i]
                    if ne in etap_times:
                        next_etap = ne
                        break
            except Exception:
                pass
            curr_name = _etap_display_name(linia_u, etap_nr)

            if prev_etap is not None and new_start is not None:
                prev_stop = (etap_times.get(prev_etap) or (None, None))[1]
                prev_name = _etap_display_name(linia_u, prev_etap)
                if prev_stop is None:
                    return False, f'{curr_name} nie może się rozpocząć przed zakończeniem: {prev_name} (najpierw ustaw STOP)'
                if new_start < prev_stop:
                    return False, f'START: {curr_name} nie może być wcześniejszy niż {_format_hhmm(prev_stop)} (STOP: {prev_name})'

            if next_etap is not None:
                next_start = (etap_times.get(next_etap) or (None, None))[0]
                if next_start is not None:
                    next_name = _etap_display_name(linia_u, next_etap)
                    if new_start is not None and new_start > next_start:
                        return False, f'START: {curr_name} nie może być późniejszy niż {_format_hhmm(next_start)} (START: {next_name})'
                    if new_stop is not None and new_stop > next_start:
                        return False, f'STOP: {curr_name} nie może być późniejszy niż {_format_hhmm(next_start)} (START: {next_name})'

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
    def reset_etap(plan_id: int, linia: str, etap: int, szarza_nr: Optional[int] = None) -> Tuple[bool, str]:
        """Delete etap row (clears manual/auto times and signatures)."""
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
                "DELETE FROM zasyp_etapy WHERE linia = %s AND plan_id = %s AND szarza_nr = %s AND etap = %s",
                (linia_u, int(plan_id), curr_szarza_nr, etap_nr),
            )
            
            # AGRO pairs are non-separable: resetting one side also resets its pair.
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
