#!/usr/bin/env python3
"""
MQTT Broker Test Suite – Połącz się i testuj komendy
Użycie: python mqtt_test_suite.py
"""

import json
import time
import paho.mqtt.client as mqtt
from datetime import datetime

# ============= KONFIGURACJA =============
MQTT_HOST = "4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "Lstech"
MQTT_PW = "Lstech123"

# ============= TOPICY =============
TOPIC_PAKOWACZKA = "iot-2/type/cMT2108X2/id/agroPakowaczka"
TOPIC_PAKOWACZKA_CMD = "iot-2/type/cMT2108X2/id/agroPakowaczka/send"
TOPIC_PALETYZATOR = "iot-2/type/cMT2108X2/id/agroPaletyzator"
TOPIC_PALETYZATOR_CMD = "iot-2/type/cMT2108X2/id/agroPaletyzator/setPattern"
TOPIC_OWIJARKA = "iot-2/type/cMT2108X2/id/agroOwijarka"
TOPIC_OWIJARKA_CMD = "iot-2/type/cMT2108X2/id/agroOwijarka/send"

# ============= ZMIENNE GLOBALNE =============
client = None
received_messages = []
connected = False


# ============= CALLBACK'I =============
def on_connect(client, userdata, flags, rc, properties=None):
    global connected
    if rc == 0:
        print("✅ [MQTT-CONNECT] Połączenie UDANE!")
        connected = True
        # Subskrybuj wszystkie maszyny
        for topic in [TOPIC_PAKOWACZKA, TOPIC_PALETYZATOR, TOPIC_OWIJARKA]:
            client.subscribe(topic)
            print(f"   📡 Subskrybuje: {topic}")
    else:
        print(f"❌ [MQTT-CONNECT] Błąd połączenia (kod: {rc})")
        connected = False


def on_message(client, userdata, msg):
    global received_messages
    try:
        payload = msg.payload.decode('utf-8')
        parsed = json.loads(payload)
        
        received_messages.append({
            'topic': msg.topic,
            'payload': parsed,
            'timestamp': datetime.now().isoformat()
        })
        
        # Wyświetl wiadomość
        print(f"\n📨 WIADOMOŚĆ ODEBRANA ({msg.topic}):")
        print(f"   {json.dumps(parsed, indent=2)}")
        
    except json.JSONDecodeError:
        print(f"⚠️  [PARSE-ERROR] Nie udało się sparsować JSON: {msg.payload}")
    except Exception as e:
        print(f"❌ [ERROR] {str(e)}")


def on_disconnect(client, userdata, rc, properties=None):
    global connected
    connected = False
    if rc != 0:
        print(f"⚠️  [DISCONNECT] Nieoczekiwane rozłączenie (kod: {rc})")
    else:
        print("✅ [DISCONNECT] Rozłączenie zaplanowane")


# ============= FUNKCJE TESTU =============
def test_connection():
    """Test 1: Połączenie z brokerem"""
    print("\n" + "="*70)
    print("TEST 1: POŁĄCZENIE Z MQTT BROKEREM")
    print("="*70)
    
    global client, connected
    
    try:
        print(f"Łączenie z: {MQTT_HOST}:{MQTT_PORT}")
        print(f"Username: {MQTT_USER}")
        
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set(MQTT_USER, MQTT_PW)
        client.tls_set()
        
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        
        # Start pętli w tle
        client.loop_start()
        
        # Czekaj na połączenie
        for i in range(10):
            if connected:
                print("✅ Połączenie nawiązane!")
                return True
            time.sleep(1)
        
        print("❌ Timeout – nie udało się połączyć w 10 sekund")
        return False
        
    except Exception as e:
        print(f"❌ Błąd: {str(e)}")
        return False


def test_receive_telemetry():
    """Test 2: Odbiór telemetrii z maszyn"""
    print("\n" + "="*70)
    print("TEST 2: ODBIÓR TELEMETRII (czeka 15 sekund)")
    print("="*70)
    
    global received_messages
    received_messages = []
    
    print("Słuchanie na:")
    print(f"  • {TOPIC_PAKOWACZKA}")
    print(f"  • {TOPIC_PALETYZATOR}")
    print(f"  • {TOPIC_OWIJARKA}")
    print("\nCzekam na wiadomości (15 sekund)...\n")
    
    time.sleep(15)
    
    if received_messages:
        print(f"\n✅ Otrzymano {len(received_messages)} wiadomości!")
        return True
    else:
        print("\n⚠️  Brak wiadomości – maszyny mogą być wyłączone lub offline")
        return False


def test_command_reset_counter():
    """Test 3: Wysłanie komendy zerowania licznika"""
    print("\n" + "="*70)
    print("TEST 3: WYSŁANIE KOMENDY ZEROWANIA LICZNIKA")
    print("="*70)
    
    try:
        payload = {
            "d": {"zerowanieLicznikow": [1]},
            "ts": datetime.now().isoformat()
        }
        
        print(f"Topic: {TOPIC_PAKOWACZKA_CMD}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        # Publish z QoS 1
        result = client.publish(
            TOPIC_PAKOWACZKA_CMD,
            json.dumps(payload),
            qos=1
        )
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("✅ Komenda wysłana pomyślnie!")
            print("   Sprawdź panel pakowaczki – liczniki powinny się wyzerowały")
            return True
        else:
            print(f"❌ Błąd wysłania (kod: {result.rc})")
            return False
            
    except Exception as e:
        print(f"❌ Błąd: {str(e)}")
        return False


def test_command_palletizer_config():
    """Test 4: Wysłanie konfiguracji paletyzatora"""
    print("\n" + "="*70)
    print("TEST 4: WYSŁANIE KONFIGURACJI PALETYZATORA")
    print("="*70)
    
    try:
        payload = {
            "d": {
                "receptura": "STANDARD_100x120",
                "typPalety": "INDUSTRIAL_100x120",
                "nazwaPalety": "Paleta Przemysłowa (1000 × 1200 mm)",
                "szerokoscM": 1.0,
                "dlugoscM": 1.2,
                "warstwyPelne": 12,
                "warstwyLacznie": 13,
                "workiNaWarstwe": 4,
                "workiSzczyt": 2,
                "lacznieWorkow": 50,
                "masaWorkaKg": 25.0
            },
            "ts": datetime.now().isoformat()
        }
        
        print(f"Topic: {TOPIC_PALETYZATOR_CMD}")
        print(f"Payload (skrót):")
        print(f"  receptura: {payload['d']['receptura']}")
        print(f"  typPalety: {payload['d']['typPalety']}")
        print(f"  warstwyPelne: {payload['d']['warstwyPelne']}")
        print(f"  workiNaWarstwe: {payload['d']['workiNaWarstwe']}")
        
        result = client.publish(
            TOPIC_PALETYZATOR_CMD,
            json.dumps(payload),
            qos=1
        )
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("\n✅ Konfiguracja wysłana pomyślnie!")
            print("   Paletyzator powinien zaktualizować wzór ułożenia")
            return True
        else:
            print(f"❌ Błąd wysłania (kod: {result.rc})")
            return False
            
    except Exception as e:
        print(f"❌ Błąd: {str(e)}")
        return False


def test_wrapper_simulation():
    """Test 5: Symulacja sygnału z owijarki"""
    print("\n" + "="*70)
    print("TEST 5: SYMULACJA SYGNAŁU Z OWIJARKI")
    print("="*70)
    
    try:
        # Najpierw False (reset)
        print("\n[1/3] Wysyłanie RESET (False)...")
        payload_off = {"d": {"wyjazdPaletaOwinieta": False}, "ts": datetime.now().isoformat()}
        client.publish(TOPIC_OWIJARKA, json.dumps(payload_off), qos=1)
        time.sleep(2)
        print("✅ Reset wysłany")
        
        # Potem True (sygnał)
        print("\n[2/3] Wysyłanie SYGNAŁ (True)...")
        payload_on = {"d": {"wyjazdPaletaOwinieta": True}, "ts": datetime.now().isoformat()}
        client.publish(TOPIC_OWIJARKA, json.dumps(payload_on), qos=1)
        time.sleep(2)
        print("✅ Sygnał wysłany")
        
        print("\n[3/3] Czekam na potwierdzenie od aplikacji (5 sekund)...")
        time.sleep(5)
        
        print("\n✅ Symulacja zakończona!")
        print("   Sprawdź dashboard AGRO – powinna być nowa paleta w buforze odboru")
        return True
        
    except Exception as e:
        print(f"❌ Błąd: {str(e)}")
        return False


def show_menu():
    """Pokaż menu opcji"""
    print("\n" + "="*70)
    print("MQTT BROKER TEST SUITE")
    print("="*70)
    print("\nDostępne testy:")
    print("  1. Test połączenia z brokerem")
    print("  2. Test odbioru telemetrii")
    print("  3. Test wysłania komendy (RESET LICZNIKA)")
    print("  4. Test wysłania konfiguracji PALETYZATORA")
    print("  5. Test symulacji sygnału z OWIJARKI")
    print("  6. Uruchom WSZYSTKIE testy")
    print("  0. Wyjście")
    print("\n" + "="*70)


def run_all_tests():
    """Uruchom wszystkie testy sekwencyjnie"""
    print("\n🚀 URUCHAMIANIE WSZYSTKICH TESTÓW...")
    
    results = {
        "Połączenie": test_connection(),
        "Telemetria": test_receive_telemetry(),
        "Reset licznika": test_command_reset_counter(),
        "Config paletyzatora": test_command_palletizer_config(),
        "Symulacja owijarki": test_wrapper_simulation(),
    }
    
    # Podsumowanie
    print("\n" + "="*70)
    print("PODSUMOWANIE TESTÓW")
    print("="*70)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:10} {test_name}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\nWynik: {passed}/{total} testów przeszło")
    
    if passed == total:
        print("\n🎉 WSZYSTKIE TESTY PRZESZŁY!")
    else:
        print("\n⚠️  Kilka testów nie przeszło – sprawdź brokerem/siecią")


def cleanup():
    """Czyścienie – rozłącz się"""
    global client
    if client:
        print("\n\nRozłączam się z brokerem...")
        client.loop_stop()
        client.disconnect()
        print("✅ Rozłączono")


# ============= MAIN =============
if __name__ == "__main__":
    try:
        while True:
            show_menu()
            choice = input("Wybierz opcję (0-6): ").strip()
            
            if choice == "1":
                if test_connection():
                    print("✅ Możesz teraz wysyłać komendy lub słuchać telemetrii")
            
            elif choice == "2":
                if test_receive_telemetry():
                    pass
            
            elif choice == "3":
                if not connected:
                    print("❌ Najpierw połącz się (opcja 1)")
                    continue
                test_command_reset_counter()
            
            elif choice == "4":
                if not connected:
                    print("❌ Najpierw połącz się (opcja 1)")
                    continue
                test_command_palletizer_config()
            
            elif choice == "5":
                if not connected:
                    print("❌ Najpierw połącz się (opcja 1)")
                    continue
                test_wrapper_simulation()
            
            elif choice == "6":
                run_all_tests()
                break
            
            elif choice == "0":
                print("\n👋 Do widzenia!")
                break
            
            else:
                print("❌ Nieprawidłowa opcja!")
                continue
    
    except KeyboardInterrupt:
        print("\n\n⛔ Przerwane przez użytkownika")
    
    finally:
        cleanup()
