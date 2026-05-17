import json
import os
import threading
import time
import logging
from flask import current_app

# Global storage for latest machine data
_latest_machine_data = {
    "bpm": 0,
    "counter": 0,
    "status": "OFFLINE",
    "receptura": "Brak danych",
    "last_update": 0,
    "is_wrapped": False # Nowy bit z owijarki
}

_mqtt_thread = None
_stop_event = threading.Event()

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("[MQTT-SERVER] POŁĄCZONO z HiveMQ Cloud")
        # Subskrybujemy konkretne urządzenia dla porządku
        client.subscribe("iot-2/type/cMT2108X2/id/agroPakowaczka")
        client.subscribe("iot-2/type/cMT2108X2/id/agroOwijarka")
    else:
        print(f"[MQTT-SERVER] Błąd połączenia, kod: {rc}")

def on_message(client, userdata, msg):
    global _latest_machine_data
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode())
        d = payload.get("d", {})
        
        # 1. Dane z Pakowaczki
        if "agroPakowaczka" in topic:
            _latest_machine_data["bpm"] = d.get("wydajnoscAktualna", [0])[0] if isinstance(d.get("wydajnoscAktualna"), list) else d.get("wydajnoscAktualna", 0)
            _latest_machine_data["counter"] = d.get("licznikGlobalny", [0])[0] if isinstance(d.get("licznikGlobalny"), list) else d.get("licznikGlobalny", 0)
            
            status_val = d.get("status", [0])[0] if isinstance(d.get("status"), list) else d.get("status", 0)
            _latest_machine_data["status"] = "PRACA" if status_val == 4 else ("STOP" if status_val == 0 else str(status_val))
            
            _latest_machine_data["receptura"] = d.get("nazwaReceptury", [""])[0] if isinstance(d.get("nazwaReceptury"), list) else d.get("nazwaReceptury", "Brak danych")
        
        # 2. Dane z Owijarki (Bit 'Paleta owinięta')
        elif "agroOwijarka" in topic:
            wrapped = d.get("wyjazdPaletaOwinieta", [False])[0] if isinstance(d.get("wyjazdPaletaOwinieta"), list) else d.get("wyjazdPaletaOwinieta", False)
            _latest_machine_data["is_wrapped"] = wrapped

        _latest_machine_data["last_update"] = time.time()
        
    except Exception as e:
        logging.error(f"[MQTT-SERVER] Błąd w parsowaniu on_message: {e}")

def _run_mqtt_client():
    import paho.mqtt.client as mqtt
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    
    mqtt_user = os.environ.get("MQTT_USER", "Lstech")
    mqtt_pass = os.environ.get("MQTT_PASS", "Lstech123")
    mqtt_host = os.environ.get("MQTT_HOST", "176790fd232549269f80005dd8281ccb.s1.eu.hivemq.cloud")
    
    client.username_pw_set(mqtt_user, mqtt_pass)
    client.tls_set() # Wymagane dla HiveMQ Cloud
    
    client.on_connect = on_connect
    client.on_message = on_message
    
    while not _stop_event.is_set():
        try:
            print(f"[MQTT-SERVER] Próba połączenia z {mqtt_host}...")
            client.connect(mqtt_host, 8883, 60)
            client.loop_forever()
        except Exception as e:
            print(f"[MQTT-SERVER] Wyjątek: {e}. Reconnect za 10s...")
            time.sleep(10)

def start_mqtt_bridge():
    global _mqtt_thread
    if _mqtt_thread is None:
        _mqtt_thread = threading.Thread(target=_run_mqtt_client, daemon=True)
        _mqtt_thread.start()
        print("[MQTT-SERVER] Mostek MQTT uruchomiony w tle.")

def get_latest_data():
    return _latest_machine_data
