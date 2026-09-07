# 📡 MQTT Szybka Referenca – Komendy i Topicy

## Dane Brokerowe
```
Host:     4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud
Port:     8883 (TLS)
User:     Lstech
Pass:     Lstech123
```

---

## 🌐 Topicy Odbioru (Subskrypcja)

### Pakowaczka
```
iot-2/type/cMT2108X2/id/agroPakowaczka
```
**Pola:** `wydajnoscAktualna`, `licznikGlobalny`, `status`, `nazwaReceptury`, `wagaAktualna`, `klapaZrzutuOtwarta`, `licznikOdrzutow`

### Paletyzator
```
iot-2/type/cMT2108X2/id/agroPaletyzator
```
**Pola:** `licznikPalet_global`, `nrWarstwy`, `nrWorka`, `oproznianie`, `sygnalDoOwijarkiStart`, `magazynekPaletIlosc`

### Owijarka
```
iot-2/type/cMT2108X2/id/agroOwijarka
```
**Pola:** `wyjazdPaletaOwinieta`, `postepOwijania`, `kapturekZalozony`, `etapOwijania`

---

## ⚙️ Topicy Wysyłania Komend (Publikacja)

### 1️⃣ RESET LICZNIKA PAKOWACZKI
```
Topic:    iot-2/type/cMT2108X2/id/agroPakowaczka/send
QoS:      1
Payload:  {"d": {"zerowanieLicznikow": [1]}, "ts": "2026-09-07T14:30:45.123Z"}
```
**Kiedy:** Po koniec zlecenia (AGRO Workowanie/Czyszczenie)  
**Efekt:** Liczniki pakowaczki się resetują

---

### 2️⃣ KONFIGURACJA WZORU PALETYZATORA
```
Topic:    iot-2/type/cMT2108X2/id/agroPaletyzator/setPattern
QoS:      1
Payload:  {
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
  "ts": "2026-09-07T14:30:45.123Z"
}
```
**Kiedy:** Zmiana konfiguracji palety w admin panelu  
**Efekt:** Paletyzator zmienia wzór ułożenia worków

---

### 3️⃣ SYGNAŁ Z OWIJARKI (TEST)
```
Topic:    iot-2/type/cMT2108X2/id/agroOwijarka
QoS:      0
Payload:  {"d": {"wyjazdPaletaOwinieta": true}, "ts": "2026-09-07T14:30:45.123Z"}
```
**Kiedy:** Symulacja – paleta opuścił owniarkę  
**Efekt:** Aplikacja nalicza paletę jako gotową do odbioru

---

## 🔌 Połączenie z Python (paho-mqtt)

### Instalacja
```bash
pip install paho-mqtt==2.1.0
```

### Kod
```python
import paho.mqtt.client as mqtt
import json
from datetime import datetime

# Konfiguracja
BROKER = "4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud"
PORT = 8883
USER = "Lstech"
PASS = "Lstech123"

# Callback
def on_message(client, userdata, msg):
    print(f"[{msg.topic}] {msg.payload.decode()}")

# Połączenie
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(USER, PASS)
client.tls_set()

client.on_message = on_message
client.connect(BROKER, PORT, 60)

# Subskrypcja
client.subscribe("iot-2/type/cMT2108X2/id/agroPakowaczka")
client.subscribe("iot-2/type/cMT2108X2/id/agroPaletyzator")
client.subscribe("iot-2/type/cMT2108X2/id/agroOwijarka")

# Pętla
client.loop_forever()
```

---

## 📤 Wysyłanie Komendy

```python
# Wysłanie zerowania licznika
topic = "iot-2/type/cMT2108X2/id/agroPakowaczka/send"
payload = {
    "d": {"zerowanieLicznikow": [1]},
    "ts": datetime.now().isoformat()
}
client.publish(topic, json.dumps(payload), qos=1)
```

---

## 🛠️ REST API (Flask)

### Pobranie Live Danych
```bash
curl -X GET http://localhost:8082/api/machines/telemetry/live \
  -H "Cookie: session=YOUR_SESSION"
```

### Wysłanie Komendy
```bash
curl -X POST http://localhost:8082/api/machines/telemetry/command \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "topic": "iot-2/type/cMT2108X2/id/agroPakowaczka/send",
    "command": {
      "d": {"zerowanieLicznikow": [1]},
      "ts": "2026-09-07T14:30:45.123Z"
    }
  }'
```

---

## 📊 Struktura Danych – Pola Maszyn

### Pakowaczka
| Pole | Typ | Opis | Zakres |
|------|-----|------|--------|
| `wydajnoscAktualna` | float | BPM (worki/min) | 0-999 |
| `licznikGlobalny` | int | Licznik całkowity | 0-∞ |
| `licznikLokalny` | int | Licznik lokalny | 0-∞ |
| `status` | int | 4=PRACA, 0=STOP | 0-255 |
| `nazwaReceptury` | str | Program/receptura | text |
| `wagaAktualna` | float | Waga worka [kg] | 20-30 |
| `wagaZadana` | float | Waga docelowa [kg] | 20-30 |
| `klapaZrzutuOtwarta` | bool | Reject klapa | true/false |
| `licznikOdrzutow` | int | Liczba odrzutów | 0-∞ |

### Paletyzator
| Pole | Typ | Opis | Zakres |
|------|-----|------|--------|
| `licznikPalet_global` | int | Licznik palet | 0-∞ |
| `nrWarstwy` | int | Nr warstwy | 0-13 |
| `nrWorka` | int | Nr worka w warstwie | 0-4 |
| `oproznianie` | bool | Czy opróżnianie? | true/false |
| `sygnalDoOwijarkiStart` | bool | Sygnał do owijarki | true/false |
| `magazynekPaletIlosc` | int | Palet w magazynku | 0-20 |
| `obracakPraca` | bool | Bag turner | true/false |
| `popychaczPraca` | bool | Pusher | true/false |

### Owijarka
| Pole | Typ | Opis | Zakres |
|------|-----|------|--------|
| `wyjazdPaletaOwinieta` | bool | Paleta gotowa | true/false |
| `postepOwijania` | float | Postęp [%] | 0-100 |
| `kapturekZalozony` | bool | Top sheet | true/false |
| `obrotyStolu` | int | Obroty | 0-999 |
| `etapOwijania` | str | Faza | IDLE/BOTTOM_WRAP/ASCENDING/TOP_SHEET/DESCENDING/DONE |

---

## 🧪 Test Połączenia

### Uruchom Test Suite
```bash
python mqtt_test_suite.py
```

**Dostępne testy:**
1. Test połączenia
2. Test odbioru telemetrii
3. Wysłanie komendy (RESET)
4. Wysłanie config (PALETYZATOR)
5. Symulacja owijarki
6. Wszystkie testy

---

## 📋 Zmienne Środowiskowe

```env
# .env
MQTT_BROKER_HOST=4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud
MQTT_BROKER_PORT=8883
MQTT_BROKER_USERNAME=Lstech
MQTT_BROKER_PASSWORD=Lstech123
MQTT_SUBSCRIBE_TOPICS=#
MQTT_RECENT_MESSAGES_LIMIT=60
```

---

## 🐛 Debugging

### Włącz Verbose Logging
```python
client.enable_logger()  # Wyświetla debug logs
```

### Odczytaj Ostatnie Dane
```python
from app.services.mqtt_service import get_latest_data
data = get_latest_data()
print(data['counter'])          # Licznik worków
print(data['pallet_counter'])   # Licznik palet
print(data['status'])           # Status
print(data['recent_messages'])  # Ostatnie wiadomości
print(data['recent_errors'])    # Ostatnie błędy
```

### Logi
```bash
tail -f logs/app.log        # Główny log
tail -f logs/error.log      # Błędy
```

---

## ⏱️ Timeouty i Limity

- **Heartbeat timeout:** 30 sekund (maszyna → OFFLINE)
- **QoS dla komend:** 1 (at least once)
- **Max przechowywanych wiadomości:** 60
- **Max przechowywanych błędów:** 25

---

## 🔒 Bezpieczeństwo

✅ **TLS/SSL** na porcie 8883  
✅ **Autentykacja** – user/pass  
✅ **QoS 1** dla komend – garantuje dostarczenie  
⚠️ **Nie wklejaj** poświadczeń w kodzie – użyj `.env`

---

**Ostatnia aktualizacja:** 2026-09-07
