"""Production execution routes.
Handles production plan views, start/stop actions, and weight reporting for various sections.
"""
from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
import logging
import threading
import time
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
from .orders import register_production_order_routes
from .support import register_production_support_routes
from .zasyp_etapy import register_production_zasyp_etapy_routes
from .zasyp_flow import register_production_zasyp_flow_routes
from .notifications import register_production_notification_routes
from .dosypki import register_production_dosypki_routes
from .mix import register_production_mix_routes
from .reports import register_production_reports_routes

production_bp = Blueprint('production', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    data_val = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data')
    sekcja = request.args.get('sekcja') or request.form.get('sekcja')
    linia = request.args.get('linia') or request.form.get('linia')

    if request.referrer:
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(request.referrer)
            qs = parse_qs(parsed.query)
            if not data_val:
                if 'data' in qs: data_val = qs['data'][0]
                elif 'dzisiaj' in qs: data_val = qs['dzisiaj'][0]
            if not sekcja and 'sekcja' in qs:
                sekcja = qs['sekcja'][0]
            if not linia and 'linia' in qs:
                linia = qs['linia'][0]
        except Exception:
            pass

    data_val = data_val or str(date.today())
    sekcja = sekcja or 'Zasyp'
    linia = linia or session.get('selected_hall_view') or 'PSD'

    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        return url_for('planista.panel_planisty', data=data_val)
    
    return url_for('main.index', sekcja=sekcja, data=data_val, linia=linia)


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
    
    # We only want raw materials and additives (no packaging), and no duplicates/locations.
    if linia_upper == 'AGRO':
        candidate_tables = [
            'magazyn_agro_slownik_surowce'
        ]
    else:
        candidate_tables = [
            'magazyn_agro_slownik_surowce'
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
            # For 'magazyn_surowce' and 'magazyn_dodatki' we can just select DISTINCT nazwa
            cursor.execute(
                f"SELECT DISTINCT {picked_col} FROM {table_name} WHERE {picked_col} IS NOT NULL AND TRIM({picked_col}) <> '' ORDER BY {picked_col} ASC"
            )
            for row in cursor.fetchall():
                raw_val = row[0] if isinstance(row, (list, tuple)) else None
                name = str(raw_val or '').strip()
                if name:
                    # Deduplicate by lowercase name
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
            row = cur2.fetchone()
            resolved_szarza_nr = _coerce_positive_int(row[0] if row else None)

            if resolved_szarza_nr is None:
                table_szarze = get_table_name('szarze', linia)
                cur2.execute(f"SELECT MAX(nr_szarzy) FROM {table_szarze} WHERE plan_id=%s", (plan_id,))
                row = cur2.fetchone()
                resolved_szarza_nr = _coerce_positive_int(row[0] if row else None)
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


def _proxy_insert_szarza_compatible(*args, **kwargs):
    return _insert_szarza_compatible(*args, **kwargs)


def _proxy_notify_laboratory_stage_start(*args, **kwargs):
    return _notify_laboratory_stage_start(*args, **kwargs)


def _proxy_get_db_connection(*args, **kwargs):
    return get_db_connection(*args, **kwargs)


def _proxy_get_table_name(*args, **kwargs):
    return get_table_name(*args, **kwargs)


def _proxy_audit_log(*args, **kwargs):
    return audit_log(*args, **kwargs)


class _ZasypEtapyServiceProxy:
    def __getattr__(self, name):
        return getattr(ZasypEtapyService, name)


_zasyp_etapy_service_proxy = _ZasypEtapyServiceProxy()


_dosypki_updates_dict = {}
_dosypka_ack_dict = {}

def _mark_dosypki_updated(linia: str) -> None:
    """Mark dosypki as updated"""
    _dosypki_updates_dict[str(linia).upper()] = time.time()


def _notify_agro_operator_dosypka_added(plan_id: int, linia: str, produkt: str = "", szarza_nr: int = None, dosypki_count: int = 1) -> None:
    """Notify agro operator about dosypka"""
    try:
        from app.services.mqtt_service import publish_message
        publish_message(f"agro/dosypka/{str(linia).lower()}", {"event": "dosypka_added", "plan_id": plan_id})
    except Exception:
        pass
    try:
        from app.services.zasyp_dosypka_notification_service import add_dosypka_added_event
        add_dosypka_added_event(
            linia=linia,
            plan_id=plan_id,
            produkt=produkt,
            szarza_nr=szarza_nr,
            dosypki_count=dosypki_count,
            audio_filename=None
        )
    except Exception:
        pass

def _get_dosypka_ack(linia: str) -> float:
    return _dosypka_ack_dict.get(str(linia).upper(), 0.0)

def _set_dosypka_ack(linia: str, ts: float) -> float:
    _dosypka_ack_dict[str(linia).upper()] = ts
    return ts


_zwolnienie_timestamp_dict = {}
_zwolnienie_ack_dict = {}

def _set_zwolnienie_timestamp(linia: str) -> float:
    ts = time.time()
    _zwolnienie_timestamp_dict[str(linia).upper()] = ts
    return ts

def _get_zwolnienie_timestamp(linia: str) -> float:
    return _zwolnienie_timestamp_dict.get(str(linia).upper(), 0.0)

def _set_zwolnienie_ack_timestamp(linia: str) -> float:
    ts = time.time()
    _zwolnienie_ack_dict[str(linia).upper()] = ts
    return ts

def _get_zwolnienie_ack_timestamp(linia: str) -> float:
    return _zwolnienie_ack_dict.get(str(linia).upper(), 0.0)

def _tts_filename_for_linia(linia: str) -> str:
    """Get TTS filename for linia"""
    return f"zwolnienie_{str(linia).lower()}.mp3"

def generate_tts_async(text: str, linia: str) -> None:
    """Pre-generated files are used"""
    pass


# Register sub-routes
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
    _flash_zasyp_result,
    _proxy_insert_szarza_compatible,
    _proxy_notify_laboratory_stage_start,
    _proxy_get_db_connection,
    _proxy_get_table_name,
    _zasyp_etapy_service_proxy,
    _proxy_audit_log,
)
register_production_notification_routes(
    production_bp,
    set_zwolnienie_timestamp=_set_zwolnienie_timestamp,
    tts_filename_for_linia=_tts_filename_for_linia,
    generate_tts_async=generate_tts_async,
    get_zwolnienie_timestamp=_get_zwolnienie_timestamp,
    set_zwolnienie_ack_ts_fn=_set_zwolnienie_ack_timestamp,
    get_zwolnienie_ack_ts_fn=_get_zwolnienie_ack_timestamp,
    zwolnienie_banner_ttl_seconds=300,
    get_latest_start_event_fn=get_latest_start_event,
    build_start_tts_text_fn=build_start_tts_text,
    get_latest_mieszanie_event_fn=get_latest_mieszanie_event,
    build_mieszanie_tts_text_fn=build_mieszanie_tts_text,
    is_dosypka_stage_fn=is_dosypka_stage,
    is_mieszanie_after_dosypka_fn=is_mieszanie_after_dosypka,
    get_latest_dosypka_added_event_fn=get_latest_dosypka_added_event,
    build_dosypka_added_tts_text_fn=build_dosypka_added_tts_text,
    get_dosypka_ack_ts_fn=_get_dosypka_ack,
    set_dosypka_ack_ts_fn=_set_dosypka_ack,
    zasyp_start_banner_ttl_seconds=300,
    dosypki_updates=_dosypki_updates_dict,
)
register_production_dosypki_routes(
    production_bp,
    bezpieczny_powrot,
    _get_allowed_dosypka_materials,
    _mark_dosypki_updated,
    _notify_agro_operator_dosypka_added,
)
register_production_mix_routes(production_bp, bezpieczny_powrot)
register_production_reports_routes(production_bp)
