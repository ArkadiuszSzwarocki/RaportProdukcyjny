import json
import os
import threading
import time
from copy import deepcopy

# Global storage for latest machine data
_latest_machine_data = {
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


def _first_or_default(value, default):
    if isinstance(value, list):
        return value[0] if value else default
    return value if value is not None else default


def _append_error(message):
    import datetime
    current_hour = datetime.datetime.now().hour
    
    # Ignoruj błędy łączenia (maszyna wyłączona), jeśli jesteśmy poza godzinami pracy (7-15)
    is_working_hours = (7 <= current_hour < 15)
    msg_str = str(message).lower()
    
    if not is_working_hours and ("reconnect" in msg_str or "connect" in msg_str or "timeout" in msg_str):
        return

    ts = time.time()
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
        print(f"[MQTT-SERVER] Blad polaczenia, kod: {rc}")


def on_message(client, userdata, msg):
    topic = str(getattr(msg, "topic", "") or "")
    payload_raw = getattr(msg, "payload", b"")
    payload_text = payload_raw.decode("utf-8", errors="replace").strip('\x00').strip() if isinstance(payload_raw, (bytes, bytearray)) else str(payload_raw).strip('\x00').strip()
    received_ts = time.time()

    try:
        parsed_payload = json.loads(payload_text)
    except Exception as e:
        import traceback
        with open("C:/Users/Admin/Documents/GitHub/RaportProdukcyjny/json_error.log", "w") as f:
            f.write(f"Error: {e}\nTraceback: {traceback.format_exc()}\nString: {repr(payload_text)}")
        parsed_payload = {"_raw": payload_text}

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

            if "agroPakowaczka" in topic:
                _latest_machine_data["bpm"] = _first_or_default(payload_data.get("wydajnoscAktualna"), 0)
                
                real_counter = _first_or_default(payload_data.get("licznikGlobalny"), 0)
                _latest_machine_data["counter"] = real_counter + _simulated_offsets["counter"]

                local_counter = _first_or_default(payload_data.get("licznikLokalny"), 0)
                _latest_machine_data["local_counter"] = local_counter

                status_val = _first_or_default(payload_data.get("status"), 0)
                _latest_machine_data["status"] = "PRACA" if status_val == 4 else ("STOP" if status_val == 0 else str(status_val))

                receptura_val = _first_or_default(payload_data.get("nazwaReceptury"), "Brak danych")
                _latest_machine_data["receptura"] = receptura_val or "Brak danych"

            elif "agroOwijarka" in topic:
                wrapped = _first_or_default(payload_data.get("wyjazdPaletaOwinieta"), False)
                _latest_machine_data["is_wrapped"] = bool(wrapped)

            elif "agroPaletyzator" in topic:
                real_pallets = _first_or_default(payload_data.get("licznikPalet_global"), 0)
                _latest_machine_data["pallet_counter"] = real_pallets + _simulated_offsets["pallet_counter"]
                
                current_layer = _first_or_default(payload_data.get("nrWarstwy"), 0)
                current_bag = _first_or_default(payload_data.get("nrWorka"), 0)
                
                _latest_machine_data["nrWarstwy"] = current_layer
                _latest_machine_data["nrWorka"] = current_bag
                
                oproznianie = _first_or_default(payload_data.get("oproznianie"), False)
                _latest_machine_data["oproznianie"] = bool(oproznianie)
                
                # Snapshot values when oproznianie becomes active
                if oproznianie and "oproznianie_snapshot" not in _latest_machine_data:
                    _latest_machine_data["oproznianie_snapshot"] = {
                        "nrWarstwy": current_layer,
                        "nrWorka": current_bag,
                        "timestamp": time.time()
                    }
                elif not oproznianie and "oproznianie_snapshot" in _latest_machine_data:
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

    mqtt_host = os.getenv("MQTT_BROKER_HOST", "4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud")
    mqtt_port = int(os.getenv("MQTT_BROKER_PORT", "8883"))
    mqtt_username = os.getenv("MQTT_BROKER_USERNAME", "Lstech")
    mqtt_password = os.getenv("MQTT_BROKER_PASSWORD", "Lstech123")

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    global _active_mqtt_client
    _active_mqtt_client = client
    
    if mqtt_username:
        client.username_pw_set(mqtt_username, mqtt_password)
    if mqtt_port == 8883:
        client.tls_set()

    client.on_connect = on_connect
    client.on_message = on_message

    while not _stop_event.is_set():
        try:
            print(f"[MQTT-SERVER] Proba polaczenia z {mqtt_host}:{mqtt_port}...")
            client.connect(mqtt_host, mqtt_port, 60)
            client.loop_forever()
        except Exception as exc:
            print(f"[MQTT-SERVER] Wyjatek: {exc}. Reconnect za 10s...")
            _append_error(f"mqtt reconnect loop exception: {exc}")
            time.sleep(10)


def start_mqtt_bridge():
    global _mqtt_thread
    if _mqtt_thread is not None and _mqtt_thread.is_alive():
        return
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
    global _active_mqtt_client
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
