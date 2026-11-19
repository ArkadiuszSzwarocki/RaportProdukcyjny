# cspell:words agroowijarka agropakowaczka agropaletyzator hivemq lstech palletizer pelny stolu sygnal
import json
import logging
import os
import threading
import time
from copy import deepcopy

# Global storage for latest machine data
_latest_machine_data = {
    "broker_connected": False,
    "broker_connected_at": 0,
    "bpm": 0,
    "counter": 0,
    "local_counter": 0,
    "nrWarstwy": 0,
    "nrWorka": 0,
    "status": "OFFLINE",
    "receptura": "Brak danych",
    "last_update": 0,
    "is_wrapped": False,
    "pallet_counter": 0,
    "messages_total": 0,
    "topics_seen": [],
    "topic_payloads": {},
    "topic_raw_payloads": {},
    "topic_last_update": {},
    "recent_messages": [],
    "recent_errors": [],
    # Czujniki rolek buforowych
    "rolki1zajete": False,           # Czujnik rolki 1 (bufor oczekujący)
    "rolki2zajete": False,           # Czujnik rolki 2 (bufor oczekujący)
    "buforPelny": False,             # Czy bufor jest pełny?
    "bagger_jaws_closed": False,     # Szczęki zgrzewające wagopakowaczki (worek zrobiony)
    "oproznianie": False,
    "is_emptying": False,
    "last_oproznianie_ts": 0,
}

_simulated_offsets = {
    "counter": 0,
    "pallet_counter": 0
}


def _safe_env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return int(default)


def _parse_subscribe_topics(raw_value):
    topics = [part.strip() for part in str(raw_value or "").split(",") if part.strip()]
    return topics or ["#"]


_RECENT_MESSAGES_LIMIT = max(10, _safe_env_int("MQTT_RECENT_MESSAGES_LIMIT", 60))
_RECENT_ERRORS_LIMIT = 25
_SUBSCRIBE_TOPICS = _parse_subscribe_topics(os.getenv("MQTT_SUBSCRIBE_TOPICS", "#"))
_mqtt_thread = None
_active_mqtt_client = None
_stop_event = threading.Event()
_data_lock = threading.Lock()

_latest_machine_data["subscribed_topics"] = list(_SUBSCRIBE_TOPICS)


def _load_or_sync_db_mqtt_password(env_password: str) -> str:
    """Persist env MQTT password into MySQL or load it when container env omits it."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return env_password
    try:
        from app.db import get_db_connection
        conn = get_db_connection()
    except Exception:
        return env_password

    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS konfiguracja_mqtt (
                id INT PRIMARY KEY,
                broker_host VARCHAR(255) NOT NULL DEFAULT '',
                broker_port INT NOT NULL DEFAULT 8883,
                broker_username VARCHAR(255) NOT NULL DEFAULT '',
                broker_password VARCHAR(255) NOT NULL DEFAULT '',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        host = (os.getenv("MQTT_BROKER_HOST") or "").strip() or "4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud"
        port = _safe_env_int("MQTT_BROKER_PORT", 8883)
        username = (os.getenv("MQTT_BROKER_USERNAME") or "").strip() or "Lstech"
        if env_password:
            cur.execute(
                """
                INSERT INTO konfiguracja_mqtt (id, broker_host, broker_port, broker_username, broker_password)
                VALUES (1, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    broker_host = VALUES(broker_host),
                    broker_port = VALUES(broker_port),
                    broker_username = VALUES(broker_username),
                    broker_password = VALUES(broker_password)
                """,
                (host, port, username, env_password),
            )
            conn.commit()
            return env_password

        cur.execute("SELECT broker_password FROM konfiguracja_mqtt WHERE id = 1 LIMIT 1")
        row = cur.fetchone()
        conn.commit()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return env_password


def _get_required_mqtt_password():
    """Return the MQTT password from env or database, or fail closed if missing."""
    env_password = (os.getenv("MQTT_BROKER_PASSWORD") or "").strip()
    mqtt_password = _load_or_sync_db_mqtt_password(env_password)
    if not mqtt_password:
        raise RuntimeError(
            "Brak wymaganej zmiennej MQTT_BROKER_PASSWORD. "
            "Mostek MQTT nie zostanie uruchomiony."
        )
    return mqtt_password


def _first_or_default(value, default):
    if isinstance(value, list):
        return value[0] if value else default
    return value if value is not None else default


def _pick_field(payload_data: dict, *keys, default=None):
    """Return the first present (non-None) field value, preserving False, 0, and ''."""
    for key in keys:
        if key in payload_data:
            val = _first_or_default(payload_data.get(key), None)
            if val is not None:
                return val
    return default


def _to_bool(value) -> bool:
    """Convert PLC/JSON scalar values cleanly to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in ("1", "true", "tak", "on", "yes"):
            return True
        if cleaned in ("0", "false", "nie", "off", "no", ""):
            return False
    return bool(value)


def _append_error(message):
    import datetime
    current_hour = datetime.datetime.now().hour
    
    # Ignoruj błędy łączenia (maszyna wyłączona), jeśli jesteśmy poza godzinami pracy (7-15)
    is_working_hours = (7 <= current_hour < 15)
    msg_str = str(message).lower()
    
    if not is_working_hours and ("reconnect" in msg_str or "connect" in msg_str or "timeout" in msg_str):
        return

    ts = time.time()
    try:
        from app.services.machine_error_log_service import MachineErrorLogService
        MachineErrorLogService.log_error(
            machine="BROKER_MQTT",
            description=str(message),
            severity="COMMUNICATION",
            code="MQTT-ERR"
        )
    except Exception:
        pass

    with _data_lock:
        _latest_machine_data["recent_errors"].append(
            {
                "timestamp": ts,
                "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
                "message": str(message),
            }
        )
        if len(_latest_machine_data["recent_errors"]) > _RECENT_ERRORS_LIMIT:
            _latest_machine_data["recent_errors"] = _latest_machine_data["recent_errors"][-_RECENT_ERRORS_LIMIT:]


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        with _data_lock:
            _latest_machine_data["broker_connected"] = True
            _latest_machine_data["broker_connected_at"] = time.time()
        print("[MQTT-SERVER] POLACZONO z HiveMQ Cloud")
        for topic in _SUBSCRIBE_TOPICS:
            try:
                sub_result = client.subscribe(topic)
                result_code = sub_result[0] if isinstance(sub_result, tuple) else sub_result
                if result_code == 0:
                    print(f"[MQTT-SERVER] Subskrypcja OK: {topic}")
                else:
                    err_msg = f"subscribe failed (rc={result_code}) for topic={topic}"
                    print(f"[MQTT-SERVER] {err_msg}")
                    _append_error(err_msg)
            except Exception as exc:
                err_msg = f"subscribe exception for topic={topic}: {exc}"
                print(f"[MQTT-SERVER] {err_msg}")
                _append_error(err_msg)
    else:
        with _data_lock:
            _latest_machine_data["broker_connected"] = False
        err_msg = f"connect failed, rc={rc}"
        print(f"[MQTT-SERVER] Blad polaczenia, kod: {rc}")
        _append_error(err_msg)


def on_disconnect(client, userdata, disconnect_flags=None, rc=None, properties=None):
    with _data_lock:
        _latest_machine_data["broker_connected"] = False
    if rc not in (0, None):
        _append_error(f"mqtt disconnected rc={rc}")


def on_message(client, userdata, msg):
    topic = str(getattr(msg, "topic", "") or "")
    payload_raw = getattr(msg, "payload", b"")
    payload_text = payload_raw.decode("utf-8", errors="replace").strip('\x00').strip() if isinstance(payload_raw, (bytes, bytearray)) else str(payload_raw).strip('\x00').strip()
    received_ts = time.time()

    try:
        parsed_payload = json.loads(payload_text)
    except (ValueError, TypeError):
        logging.getLogger(__name__).warning('Rejected invalid MQTT JSON on topic %s', topic)
        return

    if isinstance(parsed_payload, dict):
        payload_data = parsed_payload.get("d", parsed_payload)
    else:
        payload_data = {"value": parsed_payload}
    if not isinstance(payload_data, dict):
        payload_data = {"value": payload_data}

    try:
        with _data_lock:
            _latest_machine_data["messages_total"] += 1
            _latest_machine_data["last_update"] = received_ts
            _latest_machine_data["topic_payloads"][topic] = payload_data
            _latest_machine_data["topic_raw_payloads"][topic] = parsed_payload
            _latest_machine_data["topic_last_update"][topic] = received_ts

            if topic and topic not in _latest_machine_data["topics_seen"]:
                _latest_machine_data["topics_seen"].append(topic)

            _latest_machine_data["recent_messages"].append(
                {
                    "topic": topic,
                    "received_at": received_ts,
                    "received_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(received_ts)),
                    "payload": parsed_payload,
                    "data": payload_data,
                }
            )
            if len(_latest_machine_data["recent_messages"]) > _RECENT_MESSAGES_LIMIT:
                _latest_machine_data["recent_messages"] = _latest_machine_data["recent_messages"][-_RECENT_MESSAGES_LIMIT:]

            # Parse and record machine alarms into persistent error service
            try:
                from app.services.machine_error_log_service import MachineErrorLogService
                MachineErrorLogService.parse_and_record_payload(topic, payload_data)
            except Exception:
                pass

            topic_lower = topic.lower()
            is_bagger_topic = ("agropakowaczka" in topic_lower) or any(
                k in payload_data for k in ("wydajnoscAktualna", "licznikGlobalny", "szczekiZamkniete", "wagaOstatniegoWorka")
            )
            is_wrapper_topic = ("agroowijarka" in topic_lower) or any(
                k in payload_data for k in ("wyjazdPaletaOwinieta", "postepOwijania", "obrotyStolu", "etapOwijania")
            )
            is_palletizer_topic = ("agropaletyzator" in topic_lower) or any(
                k in payload_data for k in ("licznikPalet_global", "nrWarstwy", "nrWorka", "oproznianie", "sygnalDoOwijarkiStart")
            )

            if is_bagger_topic:
                bpm_val = _pick_field(payload_data, "wydajnoscAktualna", default=None)
                if bpm_val is not None:
                    _latest_machine_data["bpm"] = bpm_val
                
                real_counter = _pick_field(payload_data, "licznikGlobalny", default=None)
                if real_counter is not None:
                    _latest_machine_data["counter"] = int(real_counter) + _simulated_offsets["counter"]

                local_counter = _pick_field(payload_data, "licznikLokalny", default=None)
                if local_counter is not None:
                    _latest_machine_data["local_counter"] = int(local_counter)

                status_val = _pick_field(payload_data, "status", default=None)
                if status_val is not None:
                    _latest_machine_data["status"] = "PRACA" if status_val == 4 else ("STOP" if status_val == 0 else str(status_val))

                receptura_val = _pick_field(payload_data, "nazwaReceptury", default="Brak danych")
                _latest_machine_data["receptura"] = receptura_val or "Brak danych"

                # Form-Fill-Seal Sealing Jaws Telemetry (Szczęki zgrzewające worki)
                jaws_val = _pick_field(
                    payload_data,
                    "szczekiZamkniete", "szczeki", "szczekiZgrzewajace", "zgrzewanieWorka", "szczeki_zamkniete",
                    default=None,
                )
                if jaws_val is not None:
                    _latest_machine_data["bagger_jaws_closed"] = _to_bool(jaws_val)

                # Checkweigher (Waga Dynamiczna & Klapa Zrzutu) Telemetry
                weight_val = _pick_field(
                    payload_data,
                    "wagaOstatniegoWorka", "wagaWorka", "wagaAktualna", "waga",
                    default=None,
                )
                if weight_val is not None:
                    _latest_machine_data["checkweigher_weight"] = float(weight_val)

                target_w = _pick_field(payload_data, "wagaZadana", "wagaNominalna", default=25.0)
                _latest_machine_data["checkweigher_target_weight"] = float(target_w)

                reject_flap = _pick_field(
                    payload_data,
                    "klapaZrzutuOtwarta", "zrzutAktywny", "odrzutPraca", "zrzutOdrzut",
                    default=None,
                )
                reject_flap_bool = _to_bool(reject_flap) if reject_flap is not None else False
                if reject_flap is not None:
                    _latest_machine_data["checkweigher_reject_active"] = reject_flap_bool

                reject_reason = _pick_field(
                    payload_data,
                    "powodOdrzutu", "kodBleduWagi", "rejectReason",
                    default=None,
                )
                if reject_reason:
                    _latest_machine_data["checkweigher_reject_reason"] = str(reject_reason)

                reject_count_val = _pick_field(
                    payload_data,
                    "licznikOdrzutow", "licznikZrzutow", "rejectCount",
                    default=None,
                )
                if reject_count_val is not None:
                    _latest_machine_data["checkweigher_reject_count"] = int(reject_count_val)

                # Trigger reject logger if reject flap is active
                if reject_flap_bool:
                    try:
                        from app.services.machine_reject_log_service import MachineRejectLogService
                        cur_w = float(weight_val) if weight_val is not None else 24.10
                        tgt_w = float(target_w)
                        r_code = str(reject_reason).upper() if reject_reason else ("UNDERWEIGHT" if cur_w < tgt_w else "OVERWEIGHT")
                        MachineRejectLogService.log_reject(
                            weight_kg=cur_w,
                            target_weight_kg=tgt_w,
                            reason_code=r_code,
                            recipe_name=receptura_val,
                            raw_data=payload_data
                        )
                    except Exception:
                        pass

            if is_wrapper_topic:
                wrapped = _pick_field(payload_data, "wyjazdPaletaOwinieta", default=None)
                if wrapped is not None:
                    _latest_machine_data["is_wrapped"] = _to_bool(wrapped)
                
                # Wrapping cycle telemetry
                progress_val = _pick_field(payload_data, "postepOwijania", "progress", default=None)
                if progress_val is not None:
                    _latest_machine_data["wrapping_progress"] = float(progress_val)
                    
                top_sheet_val = _pick_field(payload_data, "kapturekZalozony", "top_sheet", default=None)
                if top_sheet_val is not None:
                    _latest_machine_data["top_sheet_applied"] = _to_bool(top_sheet_val)
                    
                rotations_val = _pick_field(payload_data, "obrotyStolu", "rotations", default=None)
                if rotations_val is not None:
                    _latest_machine_data["wrapper_rotations"] = int(rotations_val)
                    
                phase_val = _pick_field(payload_data, "etapOwijania", "phase", default=None)
                if phase_val is not None:
                    _latest_machine_data["wrapper_phase"] = str(phase_val)

            if is_palletizer_topic:
                real_pallets = _pick_field(payload_data, "licznikPalet_global", default=None)
                if real_pallets is not None:
                    _latest_machine_data["pallet_counter"] = int(real_pallets) + _simulated_offsets["pallet_counter"]
                
                current_layer = _pick_field(payload_data, "nrWarstwy", default=0)
                current_bag = _pick_field(payload_data, "nrWorka", default=0)
                
                _latest_machine_data["nrWarstwy"] = current_layer
                _latest_machine_data["nrWorka"] = current_bag
                
                # Bag turner / rotation angle if provided by PLC
                rotation_val = _pick_field(
                    payload_data,
                    "obrotWorka", "katObrotu", "orientacja", "obracak",
                    default=None,
                )
                if rotation_val is not None:
                    _latest_machine_data["bag_rotation_deg"] = rotation_val
                
                turner_active = _pick_field(payload_data, "obracakPraca", "obracakAktywny", default=None)
                if turner_active is not None:
                    _latest_machine_data["turner_active"] = _to_bool(turner_active)

                pusher_active = _pick_field(payload_data, "popychaczPraca", "popychaczAktywny", default=None)
                if pusher_active is not None:
                    _latest_machine_data["pusher_active"] = _to_bool(pusher_active)
                
                # Pallet dispenser / infeed magazine telemetry
                dispenser_count = _pick_field(
                    payload_data,
                    "magazynekPaletIlosc", "magazynekIloscPalet", "liczbaPaletMagazynek",
                    default=None,
                )
                if dispenser_count is not None:
                    _latest_machine_data["dispenser_pallet_count"] = int(dispenser_count)

                dispenser_active = _pick_field(
                    payload_data,
                    "podawaniePalety", "podajnikPaletPraca", "podawaniePaletyAktywne",
                    default=None,
                )
                if dispenser_active is not None:
                    _latest_machine_data["dispenser_active"] = _to_bool(dispenser_active)

                oproznianie = _pick_field(payload_data, "oproznianie", default=None)
                if oproznianie is not None:
                    oproznianie_bool = _to_bool(oproznianie)
                    _latest_machine_data["oproznianie"] = oproznianie_bool
                    _latest_machine_data["is_emptying"] = oproznianie_bool
                    if oproznianie_bool:
                        _latest_machine_data["last_oproznianie_ts"] = time.time()
                
                sygnal_owijarki = _pick_field(payload_data, "sygnalDoOwijarkiStart", default=None)
                if sygnal_owijarki is not None:
                    _latest_machine_data["sygnal_do_owijarki_start"] = _to_bool(sygnal_owijarki)
                
                # Czujniki rolek buforowych (transport -> magazyn)
                rolki1_zajete = _pick_field(payload_data, "rolki1zajete", default=None)
                if rolki1_zajete is not None:
                    _latest_machine_data["rolki1zajete"] = _to_bool(rolki1_zajete)
                
                rolki2_zajete = _pick_field(payload_data, "rolki2zajete", default=None)
                if rolki2_zajete is not None:
                    _latest_machine_data["rolki2zajete"] = _to_bool(rolki2_zajete)
                
                bufor_pelny = _pick_field(payload_data, "buforPelny", default=None)
                if bufor_pelny is not None:
                    _latest_machine_data["buforPelny"] = _to_bool(bufor_pelny)
                
                # Snapshot values when oproznianie becomes active
                is_emptying_now = bool(_latest_machine_data.get("oproznianie"))
                if is_emptying_now and "oproznianie_snapshot" not in _latest_machine_data:
                    _latest_machine_data["oproznianie_snapshot"] = {
                        "nrWarstwy": current_layer,
                        "nrWorka": current_bag,
                        "timestamp": time.time()
                    }
                elif not is_emptying_now and "oproznianie_snapshot" in _latest_machine_data:
                    del _latest_machine_data["oproznianie_snapshot"]

    except Exception as exc:
        _append_error(f"on_message exception: {exc}")


def _run_mqtt_client():
    try:
        import paho.mqtt.client as mqtt
    except Exception as exc:
        print(f"[MQTT-SERVER] Brak paho-mqtt: {exc}")
        _append_error(f"paho-mqtt missing: {exc}")
        return

    mqtt_host = (os.getenv("MQTT_BROKER_HOST") or "").strip() or "4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud"
    mqtt_port = _safe_env_int("MQTT_BROKER_PORT", 8883)
    mqtt_username = (os.getenv("MQTT_BROKER_USERNAME") or "").strip() or "Lstech"
    mqtt_password = _get_required_mqtt_password()

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    global _active_mqtt_client
    _active_mqtt_client = client
    
    if mqtt_username:
        client.username_pw_set(mqtt_username, mqtt_password)
    if mqtt_port == 8883:
        client.tls_set()

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    while not _stop_event.is_set():
        try:
            print(f"[MQTT-SERVER] Proba polaczenia z {mqtt_host}:{mqtt_port}...")
            client.connect(mqtt_host, mqtt_port, 60)
            client.loop_forever()
        except Exception as exc:
            with _data_lock:
                _latest_machine_data["broker_connected"] = False
            print(f"[MQTT-SERVER] Wyjatek: {exc}. Reconnect za 10s...")
            _append_error(f"mqtt reconnect loop exception: {exc}")
            time.sleep(10)


def start_mqtt_bridge():
    global _mqtt_thread
    if _mqtt_thread is not None and _mqtt_thread.is_alive():
        return
    # Validate secrets synchronously so the caller gets a clear startup error
    # instead of a silently failing background thread.
    _get_required_mqtt_password()
    _mqtt_thread = threading.Thread(target=_run_mqtt_client, daemon=True, name="mqtt-bridge")
    _mqtt_thread.start()
    print("[MQTT-SERVER] Mostek MQTT uruchomiony w tle.")


def get_latest_data():
    with _data_lock:
        return deepcopy(_latest_machine_data)

def simulate_machine_data(add_counter=0, add_pallets=0, set_status="PRACA"):
    """
    Służy do symulacji pracy maszyny bez fizycznego podłączenia do MQTT.
    Pozwala m.in. przetestować rozliczanie zużycia folii.
    """
    with _data_lock:
        _simulated_offsets["counter"] += add_counter
        _simulated_offsets["pallet_counter"] += add_pallets
        
        _latest_machine_data["counter"] += add_counter
        _latest_machine_data["pallet_counter"] += add_pallets
        if set_status:
            _latest_machine_data["status"] = set_status
        _latest_machine_data["last_update"] = time.time()

def publish_command(topic: str, payload_dict: dict):
    """
    Asynchronously publishes a JSON command message to the specified topic using the active MQTT client.
    Example payload_dict: {"d": {"zerowanieLicznikow": [1]}, "ts": "2026-06-24T..."}
    """
    from app.core.instance_mode import is_test_instance
    if is_test_instance():
        return False
    if _active_mqtt_client is None:
        print(f"[MQTT-SERVER] Ostrzezenie: Nie mozna opublikowac - brak podlaczonego klienta dla topic={topic}")
        return False
        
    try:
        payload_json = json.dumps(payload_dict)
        # Using QoS 1 for reliable delivery to the machine
        info = _active_mqtt_client.publish(topic, payload_json, qos=1)
        # wait_for_publish can be used, but since it's background we'll let paho handle queueing 
        # so it won't block the caller too much. We can just trust it's in the client's queue.
        print(f"[MQTT-SERVER] Opublikowano komende: {topic} -> {payload_json}")
        return True
    except Exception as e:
        print(f"[MQTT-SERVER] Blad publikacji komendy: {str(e)}")
        _append_error(f"publish_command error: {e}")
        return False


def publish_message(topic: str, payload_dict: dict):
    """Backward-compatible alias used by older production notification paths."""
    return publish_command(topic, payload_dict)
