import time
from datetime import date

from flask import current_app, jsonify, request, session

from app.db import get_db_connection, get_table_name
from app.decorators import roles_required
from app.services.zasyp_start_notification_service import build_sound_url_if_exists


def register_production_notification_routes(
    production_bp,
    set_zwolnienie_timestamp,
    tts_filename_for_linia,
    generate_tts_async,
    get_zwolnienie_timestamp,
    set_zwolnienie_ack_ts_fn,
    get_zwolnienie_ack_ts_fn,
    zwolnienie_banner_ttl_seconds,
    get_latest_start_event_fn,
    build_start_tts_text_fn,
    get_latest_mieszanie_event_fn,
    build_mieszanie_tts_text_fn,
    is_dosypka_stage_fn,
    is_mieszanie_after_dosypka_fn,
    get_latest_dosypka_added_event_fn,
    build_dosypka_added_tts_text_fn,
    get_dosypka_ack_ts_fn,
    set_dosypka_ack_ts_fn,
    zasyp_start_banner_ttl_seconds,
    dosypki_updates,
):
    @production_bp.route('/api/zasyp/zwolnij_mieszalnik', methods=['POST'])
    @roles_required('laborant', 'laboratorium', 'admin', 'zarzad')
    def api_zwolnij_mieszalnik():
        """Signalyze operatorom ze zasyp jest zwolniony."""
        linia = request.form.get('linia') or request.json.get('linia') or 'AGRO'
        linia = linia.upper()
        ts = set_zwolnienie_timestamp(linia)
        try:
            text = f"Laboratorium zwolniło mieszalnik do wysypu na linii {linia}"
            filename = tts_filename_for_linia(linia)
            generate_tts_async(text, filename)
            audio_url = build_sound_url_if_exists(filename)
        except Exception:
            audio_url = None
        return jsonify({"success": True, "timestamp": ts, "audio_url": audio_url})

    @production_bp.route('/api/zasyp/poll_zwolnienie', methods=['GET'])
    def api_poll_zwolnienie():
        """Skrypt w dashboard.html pyta co X sekund czy był sygnał."""
        role = str(session.get('rola') or '').lower()
        if role in ['laborant', 'laboratorium', 'magazyn', 'magazynier', 'planista']:
            return jsonify({"new_zwolnienie": False})

        linia = request.args.get('linia', 'PSD').upper()
        try:
            last_seen = float(request.args.get('last_seen', 0))
        except Exception:
            last_seen = 0.0
        current = get_zwolnienie_timestamp(linia)
        is_fresh = (time.time() - current) <= zwolnienie_banner_ttl_seconds if current > 0 else False
        if current > last_seen and is_fresh:
            try:
                filename = tts_filename_for_linia(linia)
                audio_url = build_sound_url_if_exists(filename)
            except Exception:
                audio_url = None
            return jsonify({"new_zwolnienie": True, "timestamp": current, "audio_url": audio_url})
        return jsonify({"new_zwolnienie": False})

    @production_bp.route('/api/zasyp/ack_zwolnienie', methods=['POST'])
    def api_ack_zwolnienie():
        """Operator potwierdził zwolnienie mieszalnika."""
        linia = (request.json.get('linia') if request.is_json else None) or request.form.get('linia') or 'AGRO'
        linia = linia.upper()
        ts = set_zwolnienie_ack_ts_fn(linia)
        return jsonify({"success": True, "timestamp": ts})

    @production_bp.route('/api/zasyp/poll_zwolnienie_ack', methods=['GET'])
    def api_poll_zwolnienie_ack():
        """Lab pyta czy operator potwierdził zwolnienie."""
        role = str(session.get('rola') or '').lower()
        if role not in ['laborant', 'laboratorium', 'admin', 'zarzad']:
            return jsonify({"new_ack": False})

        linia = request.args.get('linia', 'PSD').upper()
        try:
            last_seen = float(request.args.get('last_seen', 0))
        except Exception:
            last_seen = 0.0

        current_ack = get_zwolnienie_ack_ts_fn(linia)
        current_release = get_zwolnienie_timestamp(linia)

        # Ack must be after the last release and fresh
        is_fresh = (time.time() - current_ack) <= zwolnienie_banner_ttl_seconds if current_ack > 0 else False
        if current_ack > last_seen and current_ack >= current_release and is_fresh:
            return jsonify({"new_ack": True, "timestamp": current_ack})
        return jsonify({"new_ack": False})

    @production_bp.route('/api/zasyp/poll_etap_start', methods=['GET'])
    def api_poll_etap_start():
        """Poll for recent zasyp ETAP START events (Naważanie). Only returns events to laboratorium roles."""
        role = str(session.get('rola') or '').strip().lower()
        if role not in ['laborant', 'laboratorium']:
            return jsonify({"new_start": False})

        linia = request.args.get('linia', 'PSD').upper()
        try:
            last_seen = float(request.args.get('last_seen', 0))
        except Exception:
            last_seen = 0.0

        latest = get_latest_start_event_fn(linia, last_seen)
        if not latest:
            return jsonify({"new_start": False})

        ts = float(latest.get('event_timestamp') if 'event_timestamp' in latest else (latest.get('timestamp') or 0.0) or 0.0)
        is_fresh = (time.time() - ts) <= zasyp_start_banner_ttl_seconds if ts > 0 else False
        if ts > last_seen and is_fresh:
            audio_filename = latest.get('audio_filename') or None
            if audio_filename and not str(audio_filename).startswith('zasyp_start_'):
                audio_filename = None
            if not audio_filename and latest.get('audio_url'):
                try:
                    audio_filename = str(latest.get('audio_url')).split('/')[-1]
                except Exception:
                    audio_filename = None
            voice_text = build_start_tts_text_fn(latest.get('produkt'), latest.get('szarza_nr'))
            return jsonify(
                {
                    "new_start": True,
                    "timestamp": ts,
                    "plan_id": latest.get('plan_id'),
                    "produkt": latest.get('produkt'),
                    "szarza_nr": latest.get('szarza_nr'),
                    "tts_text": voice_text,
                    "audio_filename": audio_filename,
                    "audio_url": build_sound_url_if_exists(audio_filename),
                }
            )
        return jsonify({"new_start": False})

    @production_bp.route('/api/zasyp/poll_mieszanie_start', methods=['GET'])
    def api_poll_mieszanie_start():
        """Poll for recent zasyp Mieszanie START events. Only returns events to laboratorium roles."""
        role = str(session.get('rola') or '').strip().lower()
        if role not in ['laborant', 'laboratorium']:
            return jsonify({"new_start": False})

        linia = request.args.get('linia', 'PSD').upper()
        try:
            last_seen = float(request.args.get('last_seen', 0))
        except Exception:
            last_seen = 0.0

        latest = get_latest_mieszanie_event_fn(linia, last_seen)
        if not latest:
            return jsonify({"new_start": False})

        ts = float(latest.get('event_timestamp') if 'event_timestamp' in latest else (latest.get('timestamp') or 0.0) or 0.0)
        is_fresh = (time.time() - ts) <= zasyp_start_banner_ttl_seconds if ts > 0 else False
        if ts > last_seen and is_fresh:
            audio_filename = latest.get('audio_filename') or None
            if audio_filename and not str(audio_filename).startswith('zasyp_mieszanie_start_'):
                audio_filename = None
            etap_nr = latest.get('etap_nr')
            voice_text = build_mieszanie_tts_text_fn(latest.get('produkt'), latest.get('szarza_nr'), etap_nr)

            etap_suffix = ""
            if 30 < (etap_nr or 0) < 50:
                try:
                    etap_suffix = " " + chr(97 + (int(etap_nr) % 10) - 1)
                except Exception:
                    etap_suffix = ""

            if is_dosypka_stage_fn(etap_nr):
                banner_title = f'OPERATOR ROZPOCZĄŁ DOSYPKĘ{etap_suffix}'
            elif is_mieszanie_after_dosypka_fn(etap_nr):
                banner_title = f'OPERATOR DODAŁ DOSYPKĘ - TRWA MIESZANIE{etap_suffix}'
            else:
                banner_title = 'OPERATOR ROZPOCZĄŁ MIESZANIE'
            return jsonify(
                {
                    "new_start": True,
                    "timestamp": ts,
                    "plan_id": latest.get('plan_id'),
                    "etap_nr": etap_nr,
                    "produkt": latest.get('produkt'),
                    "szarza_nr": latest.get('szarza_nr'),
                    "banner_title": banner_title,
                    "tts_text": voice_text,
                    "audio_filename": audio_filename,
                    "audio_url": build_sound_url_if_exists(audio_filename),
                }
            )
        return jsonify({"new_start": False})

    @production_bp.route('/api/zasyp/poll_dosypka_added', methods=['GET'])
    def api_poll_dosypka_added():
        """Poll for recent dosypka-added events. Returns notifications to operators on Zasyp (PSD/AGRO)."""
        role = str(session.get('rola') or '').strip().lower()
        if role in ['laborant', 'laboratorium', 'magazyn', 'magazynier', 'planista']:
            return jsonify({"new_event": False})

        linia = request.args.get('linia', 'PSD').upper()
        if linia not in ['PSD', 'AGRO']:
            return jsonify({"new_event": False})

        try:
            last_seen = float(request.args.get('last_seen', 0))
        except Exception:
            last_seen = 0.0

        current_app.logger.info(f'[POLL_DOSYPKA] linia={linia}, role={role}, last_seen={last_seen}')

        now_ts = time.time()
        had_future_last_seen = False
        if last_seen > (now_ts + 5):
            had_future_last_seen = True
            last_seen = 0.0

        latest = get_latest_dosypka_added_event_fn(linia, last_seen)
        current_app.logger.info(f'[POLL_DOSYPKA] latest event: {latest}')
        if not latest and had_future_last_seen:
            latest = get_latest_dosypka_added_event_fn(linia, 0.0)
        if not latest:
            current_app.logger.info(f'[POLL_DOSYPKA] No event found, returning False')
            return jsonify({"new_event": False})

        ts = float(latest.get('event_timestamp') if 'event_timestamp' in latest else (latest.get('timestamp') or 0.0) or 0.0)
        ack_ts = get_dosypka_ack_ts_fn(linia)
        if ts > 0 and ack_ts > 0 and ts <= ack_ts:
            return jsonify({"new_event": False})

        is_fresh = (time.time() - ts) <= zasyp_start_banner_ttl_seconds if ts > 0 else False
        if (ts > last_seen or had_future_last_seen) and is_fresh:
            audio_filename = latest.get('audio_filename') or None
            if audio_filename and not str(audio_filename).startswith('zasyp_dosypka_added_'):
                audio_filename = None
            voice_text = build_dosypka_added_tts_text_fn(
                latest.get('produkt'),
                latest.get('dosypki_count'),
                latest.get('szarza_nr'),
            )
            return jsonify(
                {
                    "new_event": True,
                    "timestamp": ts,
                    "plan_id": latest.get('plan_id'),
                    "produkt": latest.get('produkt'),
                    "szarza_nr": latest.get('szarza_nr'),
                    "dosypki_count": latest.get('dosypki_count'),
                    "banner_title": 'LABORANT DODAŁ SKŁADNIKI DOSYPKI',
                    "tts_text": voice_text,
                    "audio_filename": audio_filename,
                    "audio_url": build_sound_url_if_exists(audio_filename),
                }
            )
        return jsonify({"new_event": False})

    @production_bp.route('/api/zasyp/ack_dosypka_added', methods=['POST'])
    def api_ack_dosypka_added():
        """Acknowledge dosypka-added event timestamp to prevent replay after page refresh."""
        linia = (request.json.get('linia') if request.is_json else None) or request.form.get('linia') or request.args.get('linia') or 'AGRO'
        linia = str(linia).upper()
        if linia not in ['AGRO', 'PSD']:
            return jsonify({"success": False, "message": "unsupported linia"}), 400

        raw_ts = (request.json.get('timestamp') if request.is_json else None)
        if raw_ts is None:
            raw_ts = request.form.get('timestamp') or request.args.get('timestamp')

        try:
            ts = float(raw_ts or 0.0)
        except Exception:
            ts = 0.0

        ack_ts = set_dosypka_ack_ts_fn(linia, ts)
        return jsonify({"success": True, "ack_timestamp": ack_ts})

    @production_bp.route('/api/zasyp/poll_dosypki_update', methods=['GET'])
    def api_poll_dosypki_update():
        """Return update timestamp for dosypki so dashboards can refresh after confirm/cancel/add."""
        linia = request.args.get('linia', 'PSD').upper()
        try:
            last_seen = float(request.args.get('last_seen', 0))
        except Exception:
            last_seen = 0.0
        current = dosypki_updates.get(linia, 0.0)
        if current > last_seen:
            return jsonify({"new_update": True, "timestamp": current})
        return jsonify({"new_update": False})

    @production_bp.route('/api/zasyp/pending_dosypki_badges', methods=['GET'])
    def api_pending_dosypki_badges():
        """Return pending dosypki badge counts per plan_id for Zasyp dashboard (PSD/AGRO)."""
        role = str(session.get('rola') or '').strip().lower()
        allowed_roles = {'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'masteradmin', 'laborant', 'laboratorium'}
        if role not in allowed_roles:
            return jsonify({"success": True, "counts": {}, "timestamp": time.time()})

        linia = request.args.get('linia', 'PSD').upper()
        if linia not in ['PSD', 'AGRO']:
            return jsonify({"success": True, "counts": {}, "timestamp": time.time()})

        date_raw = request.args.get('data') or ''
        try:
            target_day = date.fromisoformat(str(date_raw)[:10]) if date_raw else date.today()
        except Exception:
            target_day = date.today()

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            table_dosypki = get_table_name('dosypki', linia)
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(
                f"""
                SELECT d.plan_id, COUNT(*)
                FROM {table_dosypki} d
                JOIN {table_plan} p ON d.plan_id = p.id
                WHERE d.potwierdzone = 0
                  AND COALESCE(d.anulowana, 0) = 0
                  AND p.sekcja = 'Zasyp'
                  AND DATE(p.data_planu) = %s
                GROUP BY d.plan_id
                """,
                (target_day,),
            )

            counts = {}
            for plan_id, pending_count in cursor.fetchall() or []:
                try:
                    pid_s = str(int(plan_id))
                    counts[pid_s] = int(pending_count or 0)
                except Exception:
                    continue

            current_app.logger.info(f'[BADGE-DEBUG] role={role}, linia={linia}, target_day={target_day}, counts={counts}')
            return jsonify({"success": True, "counts": counts, "timestamp": time.time()})
        except Exception:
            current_app.logger.exception('Failed to load pending dosypki badge counts')
            return jsonify({"success": False, "counts": {}, "timestamp": time.time()})
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
