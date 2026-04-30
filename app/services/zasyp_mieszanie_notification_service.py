import threading
import time
from typing import Optional

from app.db import get_db_connection

# In-memory fallback when DB is temporarily unavailable.
_mieszanie_events: list[dict] = []
_mieszanie_events_lock = threading.Lock()


def is_mieszanie_after_dosypka(etap_nr: Optional[int]) -> bool:
    try:
        e = int(etap_nr)
    except Exception:
        return False
    return e == 4 or (40 < e < 50)


def build_mieszanie_tts_text(produkt: Optional[str], szarza_nr: Optional[int], etap_nr: Optional[int] = None) -> str:
    produkt_text = str(produkt or '').strip()
    if is_mieszanie_after_dosypka(etap_nr):
        text = "Operator dodał dosypkę do mieszania i trwa proces mieszania"
        if produkt_text:
            text += f" {produkt_text}"
    else:
        text = f"Operator rozpoczął mieszanie {produkt_text}" if produkt_text else "Operator rozpoczął mieszanie"
    if szarza_nr is not None:
        text += f" szarża nr {szarza_nr}"
    return text


def _ensure_zasyp_mieszanie_events_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS zasyp_mieszanie_start_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            linia VARCHAR(16) NOT NULL,
            plan_id INT NULL,
            etap_nr INT NULL,
            produkt VARCHAR(255) NULL,
            szarza_nr INT NULL,
            event_timestamp DOUBLE NOT NULL,
            audio_filename VARCHAR(255) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_zasyp_mieszanie_start_events_linia_ts (linia, event_timestamp)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    try:
        cursor.execute("SHOW COLUMNS FROM zasyp_mieszanie_start_events LIKE 'etap_nr'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE zasyp_mieszanie_start_events ADD COLUMN etap_nr INT NULL AFTER plan_id")
    except Exception:
        pass


def add_mieszanie_event(
    linia: str,
    plan_id: int,
    etap_nr: int,
    produkt: str,
    szarza_nr: Optional[int],
    audio_filename: Optional[str],
) -> float:
    ts = time.time()
    linia_u = str(linia or 'AGRO').upper()
    plan_id_i = int(plan_id) if plan_id is not None else None
    etap_i = int(etap_nr) if etap_nr is not None else None
    produkt_s = str(produkt or '')[:200]
    szarza_i = int(szarza_nr) if szarza_nr is not None else None
    audio_file_s = str(audio_filename or '')[:250] or None

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _ensure_zasyp_mieszanie_events_table(cursor)
        cursor.execute(
            """
            INSERT INTO zasyp_mieszanie_start_events (linia, plan_id, etap_nr, produkt, szarza_nr, event_timestamp, audio_filename)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (linia_u, plan_id_i, etap_i, produkt_s, szarza_i, ts, audio_file_s),
        )
        conn.commit()

        ev = {
            'timestamp': ts,
            'linia': linia_u,
            'plan_id': plan_id_i,
            'etap_nr': etap_i,
            'produkt': produkt_s,
            'szarza_nr': szarza_i,
            'audio_filename': audio_file_s,
        }
        with _mieszanie_events_lock:
            _mieszanie_events.append(ev)
        return ts
    except Exception:
        try:
            with _mieszanie_events_lock:
                _mieszanie_events.append({
                    'timestamp': ts,
                    'linia': linia_u,
                    'plan_id': plan_id_i,
                    'etap_nr': etap_i,
                    'produkt': produkt_s,
                    'szarza_nr': szarza_i,
                    'audio_filename': audio_file_s,
                })
        except Exception:
            pass
        return ts
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def get_latest_mieszanie_event(linia: str, last_seen: float) -> Optional[dict]:
    linia_u = str(linia or 'AGRO').upper()
    db_ev = None
    mem_ev = None
    conn = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_zasyp_mieszanie_events_table(cursor)
        cursor.execute(
            """
            SELECT linia, plan_id, etap_nr, produkt, szarza_nr, event_timestamp, audio_filename
            FROM zasyp_mieszanie_start_events
            WHERE linia = %s AND event_timestamp > %s
            ORDER BY event_timestamp DESC
            LIMIT 1
            """,
            (linia_u, float(last_seen or 0.0)),
        )
        db_ev = cursor.fetchone()
    except Exception:
        db_ev = None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    try:
        with _mieszanie_events_lock:
            events = [
                e for e in _mieszanie_events
                if e.get('linia') == linia_u and float(e.get('timestamp', 0) or 0) > float(last_seen or 0.0)
            ]
            if events:
                mem_ev = max(events, key=lambda x: x.get('timestamp', 0))
    except Exception:
        mem_ev = None

    def _ev_ts(ev: Optional[dict]) -> float:
        try:
            if not ev:
                return 0.0
            if 'event_timestamp' in ev:
                return float(ev.get('event_timestamp') or 0.0)
            return float(ev.get('timestamp') or 0.0)
        except Exception:
            return 0.0

    return db_ev if _ev_ts(db_ev) >= _ev_ts(mem_ev) else mem_ev
