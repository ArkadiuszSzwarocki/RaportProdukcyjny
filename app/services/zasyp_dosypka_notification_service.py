import threading
import time
from typing import Optional

from app.db import get_db_connection
from app.services.tts_product_utils import normalize_product_for_tts, should_speak_product_for_szarza

# In-memory fallback when DB is temporarily unavailable.
_dosypka_added_events: list[dict] = []
_dosypka_added_events_lock = threading.Lock()


def build_dosypka_added_tts_text(
    produkt: Optional[str],
    dosypki_count: Optional[int],
    szarza_nr: Optional[int],
) -> str:
    produkt_text = normalize_product_for_tts(produkt)
    parts = ['Uwaga operatorze. Laborant dodał składniki dosypki.']

    try:
        count_i = int(dosypki_count) if dosypki_count is not None else None
    except Exception:
        count_i = None

    if count_i and count_i > 0:
        parts.append(f'Liczba pozycji: {count_i}.')
    if produkt_text and should_speak_product_for_szarza(szarza_nr):
        parts.append(f'Nazwa zlecenia: {produkt_text}.')
    if szarza_nr is not None:
        parts.append(f'Szarża numer: {szarza_nr}.')
    return ' '.join(parts)


def _ensure_zasyp_dosypka_added_events_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS zasyp_dosypka_added_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            linia VARCHAR(16) NOT NULL,
            plan_id INT NULL,
            produkt VARCHAR(255) NULL,
            szarza_nr INT NULL,
            dosypki_count INT NULL,
            event_timestamp DOUBLE NOT NULL,
            audio_filename VARCHAR(255) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_zasyp_dosypka_added_events_linia_ts (linia, event_timestamp)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def add_dosypka_added_event(
    linia: str,
    plan_id: int,
    produkt: str,
    szarza_nr: Optional[int],
    dosypki_count: Optional[int],
    audio_filename: Optional[str],
) -> float:
    ts = time.time()
    linia_u = str(linia or 'AGRO').upper()
    plan_id_i = int(plan_id) if plan_id is not None else None
    produkt_s = str(produkt or '')[:200]
    szarza_i = int(szarza_nr) if szarza_nr is not None else None
    count_i = int(dosypki_count) if dosypki_count is not None else None
    audio_file_s = str(audio_filename or '')[:250] or None

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _ensure_zasyp_dosypka_added_events_table(cursor)
        cursor.execute(
            """
            INSERT INTO zasyp_dosypka_added_events
                (linia, plan_id, produkt, szarza_nr, dosypki_count, event_timestamp, audio_filename)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (linia_u, plan_id_i, produkt_s, szarza_i, count_i, ts, audio_file_s),
        )
        conn.commit()

        ev = {
            'timestamp': ts,
            'linia': linia_u,
            'plan_id': plan_id_i,
            'produkt': produkt_s,
            'szarza_nr': szarza_i,
            'dosypki_count': count_i,
            'audio_filename': audio_file_s,
        }
        with _dosypka_added_events_lock:
            _dosypka_added_events.append(ev)
        return ts
    except Exception:
        try:
            with _dosypka_added_events_lock:
                _dosypka_added_events.append({
                    'timestamp': ts,
                    'linia': linia_u,
                    'plan_id': plan_id_i,
                    'produkt': produkt_s,
                    'szarza_nr': szarza_i,
                    'dosypki_count': count_i,
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


def get_latest_dosypka_added_event(linia: str, last_seen: float) -> Optional[dict]:
    linia_u = str(linia or 'AGRO').upper()
    db_ev = None
    mem_ev = None
    conn = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_zasyp_dosypka_added_events_table(cursor)
        cursor.execute(
            """
            SELECT linia, plan_id, produkt, szarza_nr, dosypki_count, event_timestamp, audio_filename
            FROM zasyp_dosypka_added_events
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
        with _dosypka_added_events_lock:
            events = [
                e for e in _dosypka_added_events
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
