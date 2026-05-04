from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
import logging
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Optional
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required
from app.core.audit import audit_log
from app.services.zasyp_etapy_service import ZasypEtapyService
from app.services.zasyp_start_notification_service import (
    add_start_event,
    build_sound_url_if_exists,
    build_start_tts_text,
    get_latest_start_event,
)
from app.services.zasyp_mieszanie_notification_service import (
    add_mieszanie_event,
    build_mieszanie_tts_text,
    get_latest_mieszanie_event,
    is_dosypka_stage,
    is_mieszanie_after_dosypka,
)
from app.services.zasyp_dosypka_notification_service import (
    add_dosypka_added_event,
    build_dosypka_added_tts_text,
    get_latest_dosypka_added_event,
)
from app.blueprints.routes_production_orders import register_production_order_routes
from app.blueprints.routes_production_support import register_production_support_routes
from app.blueprints.routes_production_zasyp_etapy import register_production_zasyp_etapy_routes
from app.blueprints.routes_production_zasyp_flow import register_production_zasyp_flow_routes
from app.blueprints.routes_production_notifications import register_production_notification_routes
from app.blueprints.routes_production_dosypki import register_production_dosypki_routes
from app.blueprints.routes_production_mix import register_production_mix_routes

production_bp = Blueprint('production', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    # Try to get sekcja from query string first (URL parameters), then from form
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('main.index', sekcja=sekcja, data=data, linia=linia)


def _coerce_date(d: object) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str) and d:
        try:
            return date.fromisoformat(d[:10])
        except Exception:
            return date.today()
    return date.today()


def _parse_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        s = str(value).strip().replace(',', '.')
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _get_allowed_dosypka_materials(cursor, linia: str) -> list[str]:
    """Load allowed raw material names for dosypka from available warehouse tables."""
    linia_upper = str(linia or '').upper()
    # Dosypki on PSD should use the same material dictionary as AGRO.
    if linia_upper in {'AGRO', 'PSD'}:
        candidate_tables = [
            'magazyn_agro_slownik_surowce',
            'magazyn_agro_surowce',
            'magazyn_agro_ruch',
            'mom_pozycje',
        ]
    else:
        candidate_tables = [
            'magazyn_slownik_surowce',
            'magazyn_surowce',
            'magazyn_ruch',
            'mom_pozycje',
        ]
    candidate_columns = ['nazwa', 'surowiec_nazwa', 'nazwa_surowca', 'surowiec']

    values_map = {}
    for table_name in candidate_tables:
        cursor.execute(
            "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1",
            (table_name,)
        )
        if not cursor.fetchone():
            continue

        picked_col = None
        for col_name in candidate_columns:
            cursor.execute(
                "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s LIMIT 1",
                (table_name, col_name)
            )
            if cursor.fetchone():
                picked_col = col_name
                break

        if not picked_col:
            continue

        try:
            cursor.execute(
                f"SELECT DISTINCT {picked_col} FROM {table_name} WHERE {picked_col} IS NOT NULL AND TRIM({picked_col}) <> '' ORDER BY {picked_col} ASC"
            )
            for row in cursor.fetchall():
                raw_val = row[0] if isinstance(row, (list, tuple)) else None
                name = str(raw_val or '').strip()
                if name:
                    values_map.setdefault(name.lower(), name)
        except Exception:
            current_app.logger.debug('dosypka source read failed: %s.%s', table_name, picked_col, exc_info=True)

    return sorted(values_map.values(), key=lambda s: s.lower())


def _is_modal_sequence_error(msg: str) -> bool:
    s = str(msg or '').lower()
    return ('nie może' in s and ('start' in s or 'rozpocząć' in s)) or ('najwcześniej' in s)


def _flash_zasyp_result(ok: bool, msg: str) -> None:
    prefixed = ('✅ ' if ok else '❌ ') + str(msg or '')
    if ok:
        flash(prefixed, 'success')
        return
    if _is_modal_sequence_error(msg):
        flash(prefixed, 'modal_error')
    else:
        flash(prefixed, 'danger')


def _insert_szarza_compatible(cursor, table_szarze: str, *, plan_id: int, nr_szarzy: int, waga: float,
                              godzina: str, data_dodania: datetime, pracownik_id: Optional[int],
                              produkt: Optional[str] = None, typ_produkcji: Optional[str] = None,
                              data_planu: Optional[date] = None) -> None:
    """Insert szarza row using only columns that exist in the target table schema."""
    cursor.execute(f"SHOW COLUMNS FROM {table_szarze}")
    existing_cols = {row[0] for row in cursor.fetchall() or []}

    values_map = {
        'plan_id': plan_id,
        'produkt': produkt,
        'nr_szarzy': nr_szarzy,
        'waga': waga,
        'godzina': godzina,
        'data_dodania': data_dodania,
        'pracownik_id': pracownik_id,
        'status': 'zarejestowana',
        'typ_produkcji': typ_produkcji or 'N/A',
        'data_planu': data_planu,
        'potwierdzone_workowanie': 0,
    }

    ordered_cols = [
        'plan_id', 'produkt', 'nr_szarzy', 'waga', 'godzina', 'data_dodania',
        'pracownik_id', 'status', 'typ_produkcji', 'data_planu', 'potwierdzone_workowanie'
    ]
    insert_cols = [col for col in ordered_cols if col in existing_cols]
    insert_vals = [values_map[col] for col in insert_cols]
    placeholders = ', '.join(['%s'] * len(insert_cols))
    cols_sql = ', '.join(insert_cols)
    cursor.execute(
        f"INSERT INTO {table_szarze} ({cols_sql}) VALUES ({placeholders})",
        tuple(insert_vals),
    )


def _notify_laboratory_stage_start(
    linia: str,
    plan_id: int,
    etap: int,
    produkt: str,
    szarza_nr: Optional[int] = None,
) -> None:
    """Emit laboratorium notification for start of selected Zasyp stages."""
    try:
        etap_i = int(etap)
    except Exception:
        return
    if etap_i not in (1, 2, 3, 4) and not (30 < etap_i < 50):
        return

    def _coerce_positive_int(value: object) -> Optional[int]:
        try:
            out = int(value)
            return out if out > 0 else None
        except Exception:
            return None

    # Prefer explicit session szarza passed from current request flow.
    resolved_szarza_nr = _coerce_positive_int(szarza_nr)

    if resolved_szarza_nr is None:
        conn2 = None
        try:
            conn2 = get_db_connection()
            cur2 = conn2.cursor()
            cur2.execute(
                "SELECT COALESCE(MAX(szarza_nr), 0) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s",
                (str(linia or '').upper(), int(plan_id)),
            )
            r = cur2.fetchone()
            resolved_szarza_nr = _coerce_positive_int(r[0] if r else None)

            # Legacy fallback when etapy rows are unavailable.
            if resolved_szarza_nr is None:
                table_szarze = get_table_name('szarze', linia)
                cur2.execute(f"SELECT MAX(nr_szarzy) FROM {table_szarze} WHERE plan_id=%s", (plan_id,))
                r = cur2.fetchone()
                resolved_szarza_nr = _coerce_positive_int(r[0] if r else None)
        except Exception:
            resolved_szarza_nr = None
        finally:
            try:
                if conn2:
                    conn2.close()
            except Exception:
                pass

    try:
        ts_ms = int(time.time() * 1000)
        uniq = uuid.uuid4().hex[:8]
        is_nawazanie = etap_i == 1
        filename_prefix = 'zasyp_start' if is_nawazanie else 'zasyp_mieszanie_start'
        filename = f"{filename_prefix}_{plan_id}_{ts_ms}_{uniq}.mp3"
        text = (
            build_start_tts_text(produkt, resolved_szarza_nr)
            if is_nawazanie
            else build_mieszanie_tts_text(produkt, resolved_szarza_nr, etap_i)
        )

        try:
            generate_tts_async(text, filename)
        except Exception:
            current_app.logger.exception('Failed to kick off TTS for zasyp stage notification')
            filename = None

        try:
            if is_nawazanie:
                add_start_event(linia, plan_id, produkt, resolved_szarza_nr, filename)
            else:
                add_mieszanie_event(linia, plan_id, etap_i, produkt, resolved_szarza_nr, filename)
        except Exception:
            current_app.logger.exception('Failed to register zasyp stage notification event')
    except Exception:
        current_app.logger.exception('Unexpected error while preparing zasyp stage notification event')


def _notify_agro_operator_dosypka_added(
    linia: str,
    plan_id: int,
    produkt: str,
    szarza_nr: Optional[int],
    dosypki_count: int,
) -> None:
    linia_u = str(linia or '').upper()
    if linia_u != 'AGRO':
        return

    try:
        count_i = int(dosypki_count or 0)
    except Exception:
        count_i = 0
    if count_i <= 0:
        return

    try:
        ts_ms = int(time.time() * 1000)
        uniq = uuid.uuid4().hex[:8]
        filename = f"zasyp_dosypka_added_{plan_id}_{ts_ms}_{uniq}.mp3"
        text = build_dosypka_added_tts_text(produkt, count_i, szarza_nr)

        try:
            generate_tts_async(text, filename)
        except Exception:
            current_app.logger.exception('Failed to kick off TTS for zasyp dosypka-added notification')
            filename = None

        try:
            add_dosypka_added_event(linia_u, plan_id, produkt, szarza_nr, count_i, filename)
        except Exception:
            current_app.logger.exception('Failed to register zasyp dosypka-added notification event')
    except Exception:
        current_app.logger.exception('Unexpected error while preparing zasyp dosypka-added notification event')


# --- ZWOLNIENIE MIESZALNIKA ---
import time
_mieszalnik_zwolnienia = {'AGRO': 0, 'PSD': 0}
_dosypki_updates = {'AGRO': 0, 'PSD': 0}
ZWOLNIENIE_BANNER_TTL_SECONDS = 180
import threading
ZASYP_START_BANNER_TTL_SECONDS = 900


def _dosypka_ack_session_key(linia: str) -> str:
    linia_u = str(linia or 'AGRO').upper()
    return f'zasyp_dosypka_ack_ts_{linia_u}'


def _get_dosypka_ack_ts(linia: str) -> float:
    try:
        return float(session.get(_dosypka_ack_session_key(linia), 0.0) or 0.0)
    except Exception:
        return 0.0


def _set_dosypka_ack_ts(linia: str, ts: float) -> float:
    try:
        ts_f = float(ts or 0.0)
    except Exception:
        ts_f = 0.0
    if ts_f <= 0:
        return _get_dosypka_ack_ts(linia)

    current = _get_dosypka_ack_ts(linia)
    if ts_f > current:
        session[_dosypka_ack_session_key(linia)] = ts_f
        try:
            session.modified = True
        except Exception:
            pass
        return ts_f
    return current


def _mark_dosypki_updated(linia: str) -> None:
    try:
        linia_u = str(linia or 'PSD').upper()
        _dosypki_updates[linia_u] = time.time()
    except Exception:
        pass


def _ensure_zwolnienie_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS zasyp_zwolnienia_mieszalnika (
            linia VARCHAR(16) PRIMARY KEY,
            timestamp_unix DOUBLE NOT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _set_zwolnienie_timestamp(linia: str) -> float:
    linia_u = str(linia or 'AGRO').upper()
    ts = time.time()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _ensure_zwolnienie_table(cursor)
        cursor.execute(
            """
            INSERT INTO zasyp_zwolnienia_mieszalnika (linia, timestamp_unix)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE timestamp_unix = VALUES(timestamp_unix)
            """,
            (linia_u, ts),
        )
        conn.commit()
    except Exception:
        # Safe fallback for environments where table creation/query fails.
        _mieszalnik_zwolnienia[linia_u] = ts
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
    return ts


def _get_zwolnienie_timestamp(linia: str) -> float:
    linia_u = str(linia or 'AGRO').upper()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _ensure_zwolnienie_table(cursor)
        cursor.execute(
            "SELECT timestamp_unix FROM zasyp_zwolnienia_mieszalnika WHERE linia = %s LIMIT 1",
            (linia_u,),
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            try:
                return float(row[0])
            except Exception:
                return 0.0
    except Exception:
        pass
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
    return float(_mieszalnik_zwolnienia.get(linia_u, 0.0) or 0.0)


def _tts_filename_for_linia(linia: str) -> str:
    return f"zwolnienie_{str(linia or 'AGRO').lower()}.mp3"


def generate_tts_async(text: str, filename: str) -> None:
    """Generate TTS in a background thread and save to static/sounds/filename."""
    try:
        app_root = current_app.root_path
        static_folder = current_app.static_folder
        logger = current_app.logger
    except Exception:
        # Fallbacks if no app context - try to proceed anyway
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_folder = None
        logger = logging.getLogger('raportprodukcyjny')

    def _job():
        try:
            try:
                from gtts import gTTS
            except Exception:
                logger.warning('gTTS not installed or import failed; skipping TTS generation')
                return
            if static_folder:
                out_dir = os.path.join(static_folder, 'sounds')
            else:
                out_dir = os.path.join(app_root, 'static', 'sounds')
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, filename)
            # Generate TTS (may require network)
            tts = gTTS(text=text, lang='pl')
            tts.save(out_path)
            logger.info('TTS saved: %s', out_path)
        except Exception:
            logger.exception('TTS generation failed')

    try:
        t = threading.Thread(target=_job, daemon=True)
        t.start()
    except Exception:
        logger.exception('Failed to start TTS thread')

register_production_order_routes(production_bp, bezpieczny_powrot)
register_production_support_routes(production_bp, bezpieczny_powrot)
register_production_zasyp_etapy_routes(
    production_bp,
    bezpieczny_powrot,
    _coerce_date,
    _parse_float,
)
register_production_zasyp_flow_routes(
    production_bp,
    bezpieczny_powrot,
    _coerce_date,
    _parse_float,
    lambda ok, msg: _flash_zasyp_result(ok, msg),
    lambda *args, **kwargs: _insert_szarza_compatible(*args, **kwargs),
    lambda *args, **kwargs: _notify_laboratory_stage_start(*args, **kwargs),
    lambda: get_db_connection(),
    lambda *args, **kwargs: get_table_name(*args, **kwargs),
    ZasypEtapyService,
    lambda *args, **kwargs: audit_log(*args, **kwargs),
)
register_production_notification_routes(
    production_bp,
    set_zwolnienie_timestamp=_set_zwolnienie_timestamp,
    tts_filename_for_linia=_tts_filename_for_linia,
    generate_tts_async=generate_tts_async,
    get_zwolnienie_timestamp=_get_zwolnienie_timestamp,
    zwolnienie_banner_ttl_seconds=ZWOLNIENIE_BANNER_TTL_SECONDS,
    get_latest_start_event_fn=get_latest_start_event,
    build_start_tts_text_fn=build_start_tts_text,
    get_latest_mieszanie_event_fn=get_latest_mieszanie_event,
    build_mieszanie_tts_text_fn=build_mieszanie_tts_text,
    is_dosypka_stage_fn=is_dosypka_stage,
    is_mieszanie_after_dosypka_fn=is_mieszanie_after_dosypka,
    get_latest_dosypka_added_event_fn=get_latest_dosypka_added_event,
    build_dosypka_added_tts_text_fn=build_dosypka_added_tts_text,
    get_dosypka_ack_ts_fn=_get_dosypka_ack_ts,
    set_dosypka_ack_ts_fn=_set_dosypka_ack_ts,
    zasyp_start_banner_ttl_seconds=ZASYP_START_BANNER_TTL_SECONDS,
    dosypki_updates=_dosypki_updates,
)
register_production_dosypki_routes(
    production_bp,
    bezpieczny_powrot,
    _get_allowed_dosypka_materials,
    _mark_dosypki_updated,
    _notify_agro_operator_dosypka_added,
)
register_production_mix_routes(production_bp, bezpieczny_powrot)
