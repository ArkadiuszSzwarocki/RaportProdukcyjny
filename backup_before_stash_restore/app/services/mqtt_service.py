"""MQTT bridge service for machine status updates.

This module intentionally keeps backward-compatible function names used by
older runtime wiring: ``start_mqtt_bridge`` and ``get_latest_data``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

OFFLINE = "OFFLINE"
NO_DATA = "Brak danych"

_latest_machine_data: dict[str, Any] = {
    "status": OFFLINE,
    "receptura": NO_DATA,
    "is_wrapped": False,
    "last_update": None,
}

_mqtt_thread: threading.Thread | None = None
_stop_event = threading.Event()


def on_connect(client, userdata, flags, rc):
    """Subscribe to all machine topics after successful connect."""
    try:
        client.subscribe("iot-2/type/cMT2108X2/id/agroPakowaczka")
        client.subscribe("iot-2/type/cMT2108X2/id/agroOwijarka")
    except Exception:
        # Keep bridge resilient in production thread.
        pass


def on_message(client, userdata, msg):
    """Parse MQTT payload and refresh in-memory latest machine state."""
    try:
        topic = str(getattr(msg, "topic", "") or "")
        payload_raw = getattr(msg, "payload", b"")
        payload = payload_raw.decode("utf-8", errors="ignore") if isinstance(payload_raw, (bytes, bytearray)) else str(payload_raw)
        data = json.loads(payload or "{}")

        if "agroPakowaczka" in topic:
            status_raw = data.get("status", 0)
            status_val = status_raw[0] if isinstance(status_raw, list) and status_raw else status_raw
            if status_val == 4:
                _latest_machine_data["status"] = "PRACA"
            elif status_val == 0:
                _latest_machine_data["status"] = "STOP"
            else:
                _latest_machine_data["status"] = str(status_val)

            receptura_raw = data.get("nazwaReceptury", NO_DATA)
            if isinstance(receptura_raw, list):
                receptura_val = receptura_raw[0] if receptura_raw else ""
            else:
                receptura_val = receptura_raw
            _latest_machine_data["receptura"] = receptura_val or NO_DATA

        elif "agroOwijarka" in topic:
            wrapped_raw = data.get("wyjazdPaletaOwinieta", False)
            if isinstance(wrapped_raw, list):
                wrapped_val = wrapped_raw[0] if wrapped_raw else False
            else:
                wrapped_val = wrapped_raw
            _latest_machine_data["is_wrapped"] = bool(wrapped_val)

        _latest_machine_data["last_update"] = time.time()
    except Exception:
        # Ignore malformed payloads to keep the bridge running.
        pass


def _run_mqtt_client():
    """Run reconnecting MQTT client loop in background thread."""
    try:
        import paho.mqtt.client as mqtt
    except ModuleNotFoundError:
        print("[MQTT-SERVER] Brak pakietu paho-mqtt. Zainstaluj: pip install paho-mqtt")
        return

    # Keep defaults close to prior runtime behavior, but allow env overrides.
    mqtt_host = os.getenv("MQTT_BROKER_HOST", "176790fd232549269f80005dd8281ccb.s1.eu.hivemq.cloud")
    mqtt_port = int(os.getenv("MQTT_BROKER_PORT", "8883"))
    mqtt_username = os.getenv("MQTT_BROKER_USERNAME", "")
    mqtt_password = os.getenv("MQTT_BROKER_PASSWORD", "")

    try:
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    except Exception:
        # Backward compatibility with older paho API.
        client = mqtt.Client()

    if mqtt_username:
        client.username_pw_set(mqtt_username, mqtt_password)

    if mqtt_port == 8883:
        try:
            client.tls_set()
        except Exception:
            pass

    client.on_connect = on_connect
    client.on_message = on_message

    while not _stop_event.is_set():
        try:
            print(f"[MQTT-SERVER] Proba polaczenia z {mqtt_host}...")
            client.connect(mqtt_host, mqtt_port, 60)
            client.loop_forever()
        except Exception as exc:
            print(f"[MQTT-SERVER] Wyjatek: {exc}. Reconnect za 10s...")
            time.sleep(10)


def start_mqtt_bridge():
    """Start MQTT bridge thread only once."""
    global _mqtt_thread

    if _mqtt_thread is not None and _mqtt_thread.is_alive():
        return

    _stop_event.clear()
    _mqtt_thread = threading.Thread(target=_run_mqtt_client, daemon=True, name="mqtt-bridge")
    _mqtt_thread.start()
    print("[MQTT-SERVER] Mostek MQTT uruchomiony w tle.")


def get_latest_data() -> dict[str, Any]:
    """Return latest cached machine data for API responses."""
    return dict(_latest_machine_data)
