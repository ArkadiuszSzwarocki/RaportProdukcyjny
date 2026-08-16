import json
import time
import paho.mqtt.client as mqtt

# Konfiguracja identyczna jak w aplikacji
MQTT_HOST = "4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "Lstech"
MQTT_PW = "Lstech123"
TOPIC = "iot-2/type/cMT2108X2/id/agroOwijarka"

def trigger_pallet():
    # Używamy najnowszej wersji API paho-mqtt
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PW)
    client.tls_set()
    
    print(f"Łączenie z {MQTT_HOST}...")
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        
        # 1. Najpierw upewniamy się, że bit jest False (reset)
        payload_off = {"d": {"wyjazdPaletaOwinieta": False}}
        client.publish(TOPIC, json.dumps(payload_off))
        print("Wysłano reset (False)")
        time.sleep(2)
        
        # 2. Wysyłamy True (Zbocze narastające - to powinno wyzwolić dodanie palety)
        payload_on = {"d": {"wyjazdPaletaOwinieta": True}}
        client.publish(TOPIC, json.dumps(payload_on))
        print("Wysłano sygnał PALETA OWINIĘTA (True)!")
        
        time.sleep(1)
        client.disconnect()
        print("\n[OK] Sygnał wysłany. Sprawdź dashboard AGRO Workowanie.")
        print("Pamiętaj, że musisz mieć AKTYWNE zlecenie (status 'w toku') na Workowaniu AGRO.")
    except Exception as e:
        print(f"[BŁĄD] Nie udało się wysłać sygnału: {e}")

if __name__ == "__main__":
    trigger_pallet()
