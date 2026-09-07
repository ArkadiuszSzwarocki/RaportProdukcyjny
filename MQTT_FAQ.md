# ❓ MQTT – FAQ & Poradniki Szybkie

## Spis Treści
1. [Jak się połączyć?](#jak-się-połączyć)
2. [Jak wysłać komendę?](#jak-wysłać-komendę)
3. [Jak odczytać dane?](#jak-odczytać-dane)
4. [Jak debugować?](#jak-debugować)
5. [Odpowiedzi na Pytania](#odpowiedzi-na-pytania)

---

## Jak się połączyć?

### ⚡ Najszybciej – Python + paho-mqtt

```bash
# 1. Instalacja
pip install paho-mqtt==2.1.0

# 2. Stwórz skrypt connect.py
cat > connect.py << 'EOF'
import paho.mqtt.client as mqtt
import json

BROKER = "4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud"
PORT = 8883
USER = "Lstech"
PASS = "Lstech123"

def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    print(f"[{msg.topic}] {json.dumps(data, indent=2)}")

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(USER, PASS)
client.tls_set()
client.on_message = on_message

print("Łączę...")
client.connect(BROKER, PORT, 60)
client.subscribe("iot-2/type/cMT2108X2/id/agroPakowaczka")
client.subscribe("iot-2/type/cMT2108X2/id/agroPaletyzator")
client.subscribe("iot-2/type/cMT2108X2/id/agroOwijarka")

print("✅ Połączono! Nasłuchuję (CTRL+C aby wyjść)...")
client.loop_forever()
EOF

# 3. Uruchom
python connect.py
```

### 🎯 Z Aplikacji Flask

Aplikacja automatycznie się łączy w `app.py`:

```python
if __name__ == '__main__':
    # ...
    from app.core.daemon import start_daemon_threads
    start_daemon_threads()  # ← Uruchamia MQTT bridge
    app.run(...)
```

### 🔍 Sprawdź Status Połączenia

```bash
# Odwiedź admin panel
http://localhost:8082/admin/master/mqtt

# Lub użyj API
curl http://localhost:8082/admin/master/mqtt/api
```

---

## Jak wysłać komendę?

### 1️⃣ Reset Licznika Pakowaczki

#### Przez API (REST)
```bash
curl -X POST http://localhost:8082/api/machines/telemetry/command \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_ID" \
  -d '{
    "topic": "iot-2/type/cMT2108X2/id/agroPakowaczka/send",
    "command": {
      "d": {"zerowanieLicznikow": [1]},
      "ts": "2026-09-07T14:30:45.123Z"
    }
  }'
```

**Odpowiedź:**
```json
{
  "success": true,
  "message": "Komenda została pomyślnie wysłana do brokera (Topic: ...)",
  "data": {
    "topic": "...",
    "payload": {...}
  }
}
```

#### Przez Python
```python
from app.services.mqtt_service import publish_command
from datetime import datetime

topic = "iot-2/type/cMT2108X2/id/agroPakowaczka/send"
payload = {
    "d": {"zerowanieLicznikow": [1]},
    "ts": datetime.now().isoformat()
}

success = publish_command(topic, payload)
if success:
    print("✅ Komenda wysłana!")
else:
    print("❌ Błąd wysyłania!")
```

#### Bezpośrednio MQTT
```python
import paho.mqtt.client as mqtt
import json
from datetime import datetime

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set("Lstech", "Lstech123")
client.tls_set()
client.connect("4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud", 8883)

payload = {
    "d": {"zerowanieLicznikow": [1]},
    "ts": datetime.now().isoformat()
}

client.publish(
    "iot-2/type/cMT2108X2/id/agroPakowaczka/send",
    json.dumps(payload),
    qos=1
)

print("✅ Wysłano!")
client.disconnect()
```

---

### 2️⃣ Zmiana Konfiguracji Paletyzatora

#### Przez API
```bash
curl -X POST http://localhost:8082/api/machines/palletizer/config \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "preset_name": "STANDARD_100x120",
    "pallet_type": "INDUSTRIAL_100x120",
    "pallet_width_m": 1.0,
    "pallet_length_m": 1.2,
    "full_layers": 12,
    "total_layers": 13,
    "bags_per_layer": 4,
    "top_layer_bags": 2,
    "bag_weight_kg": 25.0,
    "sync_to_machine": true
  }'
```

#### Przez Python
```python
from app.services.machine_telemetry_service import MachineTelemetryService

result = MachineTelemetryService.send_machine_command(
    topic="agroPaletyzator/setPattern",
    command_payload={
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
    }
)

print("✅" if result.success else "❌", result.message)
```

---

### 3️⃣ Symulacja Sygnału z Owijarki (Test)

```bash
# Uruchom test suite
python mqtt_test_suite.py

# Wybierz opcję: 5 (Test symulacji owijarki)
# Lub ręcznie:
```

```python
import paho.mqtt.client as mqtt
import json
from datetime import datetime
import time

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set("Lstech", "Lstech123")
client.tls_set()
client.connect("4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud", 8883)

# Reset
print("1. Reset...")
client.publish("iot-2/type/cMT2108X2/id/agroOwijarka", 
               json.dumps({"d": {"wyjazdPaletaOwinieta": False}, "ts": datetime.now().isoformat()}))
time.sleep(2)

# Sygnał
print("2. Sygnał (paleta gotowa)...")
client.publish("iot-2/type/cMT2108X2/id/agroOwijarka",
               json.dumps({"d": {"wyjazdPaletaOwinieta": True}, "ts": datetime.now().isoformat()}))

print("✅ Wysłano! Sprawdź dashboard AGRO")
time.sleep(1)
client.disconnect()
```

---

## Jak odczytać dane?

### 📊 Ostatnie Dane Telemetryczne

#### Przez API
```bash
# Live dashboard data
curl http://localhost:8082/api/machines/telemetry/live \
  -H "Cookie: session=YOUR_SESSION"
```

**Zwraca:**
```json
{
  "timestamp": 1725880245.123,
  "broker": {
    "is_connected": true,
    "host": "HiveMQ Cloud TLS",
    "last_update_ts": 1725880245,
    "time_since_update_sec": 0.5
  },
  "machines": {
    "bagger": {
      "status": "PRACA",
      "bpm": 45.5,
      "counter_global": 12450,
      "recipe_name": "KREDA_NAWOZOWA"
    },
    "palletizer": {
      "current_layer": 5,
      "current_bag": 2,
      "pallets_completed": 1234,
      "is_emptying": false
    },
    "wrapper": {
      "status": "OWIJANIE",
      "progress_percent": 35,
      "phase_label": "Wznoszenie wózka z folią stretch"
    }
  }
}
```

#### Z Python (Application Context)
```python
from app.services.mqtt_service import get_latest_data

# W aplikacji Flask
with app.app_context():
    data = get_latest_data()
    
    print("Pakowaczka:")
    print(f"  BPM: {data['bpm']}")
    print(f"  Licznik: {data['counter']}")
    print(f"  Status: {data['status']}")
    print(f"  Receptura: {data['receptura']}")
    
    print("\nPaletyzator:")
    print(f"  Warstwa: {data['nrWarstwy']}")
    print(f"  Worek: {data['nrWorka']}")
    print(f"  Palet: {data['pallet_counter']}")
    
    print("\nOwijarka:")
    print(f"  Paleta owinięta: {data['is_wrapped']}")
    
    print("\nOstatnie wiadomości:")
    for msg in data['recent_messages'][-5:]:
        print(f"  {msg['topic']}: {msg['data']}")
```

### 🔍 Ostatnie Wiadomości MQTT

```bash
# Przez API
curl http://localhost:8082/admin/master/mqtt/api | jq '.data.recent_messages[-5:]'
```

### 📋 Ostatnie Błędy

```bash
curl http://localhost:8082/api/machines/errors \
  -H "Cookie: session=YOUR_SESSION" | jq '.'
```

---

## Jak debugować?

### 🐛 Test Połączenia

```bash
# Uruchom test suite
python mqtt_test_suite.py

# Opcja 1: Test połączenia
# Opcja 2: Test odbioru telemetrii (15 sekund)
# Opcja 6: Wszystkie testy
```

### 📊 Live Monitoring w Admin Panelu

```
http://localhost:8082/admin/master/mqtt
```

Pokaże:
- Status połączenia (✅ Connected / ❌ Offline)
- Ostatnie wiadomości z każdej maszyny
- Licznik całkowity wiadomości
- Raw JSON payload

### 🔎 Sprawdzenie Logów

```bash
# Główny log (MQTT events)
tail -f logs/app.log | grep MQTT

# Błędy
tail -f logs/error.log

# Ostatnie 100 linii
tail -100 logs/app.log
```

### 🔧 Debug Print z Aplikacji

```python
# Dodaj w kodzie produkcji_service.py lub innym
from app.services.mqtt_service import get_latest_data
import json

# Gdziekolwiek w kodzie:
data = get_latest_data()
print("[DEBUG-MQTT]")
print(json.dumps(data, indent=2, default=str))
```

### 📡 Sniffer MQTT (Zaawansowane)

```bash
# Jeśli masz dostęp do HiveMQ Cloud:
# 1. Wejdź na https://console.hivemq.cloud
# 2. Zaloguj się (cloud.lstech123@gmail.com ?)
# 3. Sprawdź Client Connections i Message Broker Usage
```

---

## Odpowiedzi na Pytania

### ❓ "Jak wiedzieć czy maszyna jest online?"

```python
from app.services.mqtt_service import get_latest_data
import time

data = get_latest_data()
now = time.time()
last_update = data.get('last_update', 0)
time_since = now - last_update

if time_since <= 30:  # 30 sekund = timeout
    print("✅ Maszyna ONLINE")
else:
    print("❌ Maszyna OFFLINE (brak danych >30s)")
```

---

### ❓ "Co to QoS?"

| QoS | Opis | Użycie |
|-----|------|--------|
| **0** | At Most Once | Telemetria (dane mogą się powtórzyć/zgubić) |
| **1** | At Least Once | **Komendy** (muszą dojść do maszyny) |
| **2** | Exactly Once | Nie używamy (droższe) |

```python
# Telemetria (QoS 0 – domyślnie)
client.subscribe("iot-2/type/cMT2108X2/id/agroPakowaczka")

# Komenda (QoS 1 – wymuszamy)
client.publish(topic, payload, qos=1)
```

---

### ❓ "Po ile czasu zostanie wysłana komenda?"

**Teoretycznie:** < 100ms (zazwyczaj natychmiast)  
**W praktyce:** 1-2 sekundy (zależy od internetu)  
**Timeout:** Jeśli maszyna jest offline – nigdy (ale broker zapamiętuje ostatnią wiadomość)

---

### ❓ "Czy komenda może zostać "stracona"?"

**Rozłącze gwarantuje QoS 1:**
- Jeśli maszyna jest offline, broker będzie ponawiać wysyłkę (zwykle przez kilka godzin)
- Kod aplikacji sprawdza czy publikacja się powiodła

```python
result = client.publish(topic, payload, qos=1)
if result.rc != mqtt.MQTT_ERR_SUCCESS:
    print(f"❌ Błąd wysyłania (rc={result.rc})")
```

---

### ❓ "Ile topików mogę monitorować?"

**Domyślnie:** `#` (wildcard – wszystkie)  
**Limit:** Teoretycznie nieograniczony  
**W praktyce:** Rozważ wydajność (każdy topic = callback)

```env
# .env
MQTT_SUBSCRIBE_TOPICS=iot-2/type/cMT2108X2/id/agroPakowaczka,iot-2/type/cMT2108X2/id/agroPaletyzator
```

---

### ❓ "Czy mogę wysłać komendę do nieistniejącego topiku?"

**Tak** – broker zaakceptuje, ale maszyna nie będzie słuchać.

```python
# To się wyśle, ale nikt nie będzie słuchać
client.publish("iot-2/type/cMT2108X2/id/nieistniejacy", "{...}", qos=1)
# ⚠️ Brak błędu!
```

---

### ❓ "Jak zmienić poświadczenia MQTT?"

**Nie możesz ze strony aplikacji** – trzeba:

1. Wejdź na HiveMQ Cloud Console
2. Zmień hasło dla usera `Lstech`
3. Zaktualizuj `.env`:
   ```env
   MQTT_BROKER_PASSWORD=NoweHaslo123
   ```
4. Reboot aplikacji:
   ```bash
   pkill -f "python app.py"
   python app.py
   ```

---

### ❓ "Czy mogę wysyłać komendy z dowolnego IP?"

**Tak** – broker HiveMQ Cloud jest dostępny z internetu.  
**UWAGA:** Upewnij się że używasz TLS (port 8883, nie 1883)!

```python
# ✅ SECURE
client.tls_set()  # Aktywuj TLS
client.connect("...hivemq.cloud", 8883)

# ❌ DANGEROUS (bez TLS)
# client.connect("...hivemq.cloud", 1883)  # NIE RÓB TEGO!
```

---

### ❓ "Czy wiadomości są szyfrowane?"

**Tak:**
- **TLS/SSL** (port 8883) – wszystkie wiadomości zaszyfrowane
- **Username/Password** – autentykacja
- **Payload** – JSON (nie dodatkowe szyfrowanie wewnątrz)

---

### ❓ "Ile maksymalnie mogę przechowywać wiadomości?"

```env
# .env
MQTT_RECENT_MESSAGES_LIMIT=60  # Default
```

Aplikacja przechowuje ostatnie 60 wiadomości + 25 błędów w pamięci.  
**Po restarcie aplikacji** – historia się zeruje.

---

### ❓ "Czy mogę zapisywać wiadomości do bazy?"

**Tak**, ale trzeba dodać kod w `on_message()`:

```python
# W mqtt_service.py, w funkcji on_message():
def on_message(client, userdata, msg):
    # ... istniejący kod ...
    
    # Dodaj:
    try:
        from app.repositories.mqtt_history_repository import save_message
        save_message(topic, parsed_payload, received_ts)
    except Exception as e:
        print(f"[WARN] Błąd zapisu do bazy: {e}")
```

Wtedy będą dostępne na dashboard'u.

---

### ❓ "Czy mogę testować bez fizycznych maszyn?"

**Tak!** Uruchom:

```bash
python mqtt_test_suite.py
# Opcja: 5 (Symulacja sygnału owijarki)
```

Lub:

```python
# Symuluj wydajność pakowaczki
from app.services.mqtt_service import simulate_machine_data

simulate_machine_data(
    add_counter=50,      # Dodaj 50 do licznika worków
    add_pallets=1,       # Dodaj 1 paletę
    set_status="PRACA"   # Ustaw status
)
```

---

### ❓ "Ile czasu MQTT bridge pracuje po restarcie?"

```
Restart aplikacji
   ↓
20-30 sekund startup (inicjalizacja Flask)
   ↓
start_daemon_threads()
   ↓
MQTT bridge uruchamia się (1-2 sekundy)
   ↓
Próba połączenia z brokerem
   ↓
Jeśli nie uda się: retry co 10 sekund
   ↓
✅ Podłączenie OK → Subskrypcja topików
```

---

**Ostatnia aktualizacja:** 2026-09-07  
**Dokument:** MQTT_FAQ.md
