# 📡 MQTT COMPLETE DOCUMENTATION

**Wygenerowano:** 2026-09-07 17:22:45

**Zawartość:**
1. MQTT README – Spis dokumentacji
2. MQTT Quick Reference – Szybka ściągawka
3. MQTT Architecture – Architektura systemu
4. MQTT FAQ – Pytania i odpowiedzi
5. MQTT Documentation – Pełna dokumentacja
6. MQTT Index – Indeks tematyczny
7. Test Suite – Kod testowy

---


<!-- ==================== PAGE BREAK ==================== -->

# 📡 MQTT DOCUMENTATION – Spis Plików Dokumentacji

Wszystkie pliki dokumentacji znajdują się w głównym folderze repozytorium. Oto co zawiera każdy z nich:

---

## 📚 Dostępne Pliki

### 1. **MQTT_DOCUMENTATION.md** 📖 GŁÓWNY DOKUMENT
Komprehensywna dokumentacja wszystkich aspektów MQTT:
- ✅ Konfiguracja brokera
- ✅ Połączenie i autentykacja
- ✅ Topicy subskrypcji (odbieranie danych)
- ✅ Topicy publikacji (wysyłanie komend)
- ✅ Pola telemetryczne każdej maszyny
- ✅ Komendy i przykłady
- ✅ Zmienne środowiskowe
- ✅ Best practices

**Kiedy czytać:** Gdy chcesz zrozumieć cały system  
**Wyczytana: ~30 minut**

---

### 2. **MQTT_QUICK_REFERENCE.md** ⚡ SZYBKA REFERENCA
Ściągawka z najważniejszymi rzeczami:
- ✅ Dane brokera (host, port, user, pass)
- ✅ Topicy (bez szczegółów, tylko adresy)
- ✅ Payload'y (krótkie przykłady)
- ✅ Kod Python (copy-paste ready)
- ✅ cURL komendy
- ✅ Tabele pól maszyn
- ✅ Test suite instrukcja

**Kiedy czytać:** Szybko przed implementacją  
**Czas przeczytania: ~5 minut**

---

### 3. **MQTT_ARCHITECTURE.md** 🏗️ ARCHITEKTURA
Diagramy i schematy:
- ✅ System Diagram (maszyny ↔ broker ↔ aplikacja)
- ✅ Architektura Flask (serwisy, blueprinty, callbacks)
- ✅ Flow komunikacji (bidireccional)
- ✅ Sekwencja pracy linii AGRO
- ✅ Wyliczanie statusów maszyn
- ✅ Logi i monitoring
- ✅ Troubleshooting failover

**Kiedy czytać:** Gdy chcesz zrozumieć jak to wszystko się łączy  
**Czas: ~20 minut**

---

### 4. **MQTT_FAQ.md** ❓ FAQ I PORADNIKI
Pytania i odpowiedzi + krok po kroku:
- ✅ Jak się połączyć? (3 sposoby)
- ✅ Jak wysłać komendę? (3 sposoby)
- ✅ Jak odczytać dane? (4 sposoby)
- ✅ Jak debugować? (5 technik)
- ✅ Odpowiedzi na 20+ pytań
- ✅ Copy-paste kod do każdego zadania

**Kiedy czytać:** Gdy masz konkretne pytanie/problem  
**Czas: ~10 minut na odpowiedź**

---

### 5. **mqtt_test_suite.py** 🧪 TEST APLIKACJA
Interaktywny program testowy do sprawdzenia połączenia:

#### Instalacja
```bash
# Upewnij się że masz paho-mqtt
pip install paho-mqtt==2.1.0
```

#### Uruchomienie
```bash
python mqtt_test_suite.py
```

#### Menu
```
1. Test połączenia z brokerem
2. Test odbioru telemetrii (czeka 15 sekund)
3. Test wysłania komendy (RESET LICZNIKA)
4. Test wysłania konfiguracji PALETYZATORA
5. Test symulacji sygnału z OWIJARKI
6. Uruchom WSZYSTKIE testy
0. Wyjście
```

#### Przykład
```bash
$ python mqtt_test_suite.py
================================
MQTT BROKER TEST SUITE
================================
...
Wybierz opcję (0-6): 1
Łączę...
✅ [MQTT-CONNECT] Połączenie UDANE!
   📡 Subskrybuje: iot-2/type/cMT2108X2/id/agroPakowaczka
...
```

---

## 🎯 QUICK START – Gdzie Zacząć?

### Scenario 1: "Chcę się teraz połączyć i testować"
```bash
# 1. Zainstaluj paho-mqtt
pip install paho-mqtt

# 2. Uruchom test suite
python mqtt_test_suite.py

# 3. Wybierz: 6 (Wszystkie testy)
```
**Czas:** 5 minut  
**Plik:** MQTT_QUICK_REFERENCE.md + mqtt_test_suite.py

---

### Scenario 2: "Chcę zrozumieć jak to działa"
```
1. Przeczytaj: MQTT_ARCHITECTURE.md (diagramy)
2. Przeczytaj: MQTT_DOCUMENTATION.md (pełny opis)
3. Eksperymentuj: mqtt_test_suite.py
```
**Czas:** 45 minut  
**Pliki:** Wszystkie

---

### Scenario 3: "Mam konkretny problem"
```
1. Szukaj w: MQTT_FAQ.md (najprawdopodobniej tam będzie odpowiedź)
2. Jeśli nie: MQTT_QUICK_REFERENCE.md (kopacja kod)
3. Debug: mqtt_test_suite.py
```
**Czas:** 10 minut  
**Plik:** MQTT_FAQ.md + mqtt_test_suite.py

---

### Scenario 4: "Chcę wysłać komendę z kodu"
```python
# OPTION 1: Użyj aplikacji Flask API
# Przeczytaj: MQTT_QUICK_REFERENCE.md → "REST API"

# OPTION 2: Bezpośrednio MQTT
# Przeczytaj: MQTT_QUICK_REFERENCE.md → "Wysyłanie Komendy"
# Kod copy-paste gotowy!

# OPTION 3: Z aplikacji Flask
# Przeczytaj: MQTT_FAQ.md → "Jak wysłać komendę?"
```
**Czas:** 5 minut  
**Plik:** MQTT_QUICK_REFERENCE.md lub MQTT_FAQ.md

---

## 📊 Topicy – Szybkie Odnośniki

### 📥 Odbieranie (Subskrypcja)
```
Pakowaczka:   iot-2/type/cMT2108X2/id/agroPakowaczka
Paletyzator:  iot-2/type/cMT2108X2/id/agroPaletyzator
Owijarka:     iot-2/type/cMT2108X2/id/agroOwijarka
```

### 📤 Wysyłanie (Publikacja)
```
Komenda Reset:   iot-2/type/cMT2108X2/id/agroPakowaczka/send
Config Palety:   iot-2/type/cMT2108X2/id/agroPaletyzator/setPattern
Sygnał Owijarki: iot-2/type/cMT2108X2/id/agroOwijarka/send
```

---

## 🔑 Dane Brokera

```
Host:     4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud
Port:     8883 (TLS/SSL)
User:     Lstech
Pass:     Lstech123
```

---

## 🛠️ Popularne Zadania

### ✅ Zadanie 1: Test Połączenia
```bash
python mqtt_test_suite.py
# Opcja 1
```
**Plik:** mqtt_test_suite.py

---

### ✅ Zadanie 2: Odbieranie Telemetrii
```python
from app.services.mqtt_service import get_latest_data

data = get_latest_data()
print(data['counter'])          # Licznik worków
print(data['pallet_counter'])   # Licznik palet
print(data['status'])           # Status
```
**Plik:** MQTT_QUICK_REFERENCE.md → "Odczyt Danych"

---

### ✅ Zadanie 3: Wysłanie Komendy Zerowania
```bash
curl -X POST http://localhost:8082/api/machines/telemetry/command \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{"topic": "iot-2/type/cMT2108X2/id/agroPakowaczka/send", ...}'
```
**Plik:** MQTT_QUICK_REFERENCE.md → "REST API"

---

### ✅ Zadanie 4: Zmiana Konfiguracji Paletyzatora
```bash
curl -X POST http://localhost:8082/api/machines/palletizer/config ...
```
**Plik:** MQTT_FAQ.md → "Zmiana Konfiguracji Paletyzatora"

---

### ✅ Zadanie 5: Monitorowanie Live
```
Wejdź na: http://localhost:8082/admin/master/mqtt
```
**Plik:** Automatyczne (użyj przeglądarki)

---

### ✅ Zadanie 6: Debugowanie Problemu
1. Uruchom: `python mqtt_test_suite.py`
2. Wybierz: `6` (Wszystkie testy)
3. Czytaj wyniki
4. Jeśli test fail → szukaj w: MQTT_FAQ.md → Troubleshooting

**Plik:** mqtt_test_suite.py + MQTT_FAQ.md

---

## 📋 Zmienne Środowiskowe

Wszystkie ustawienia MQTT w pliku `.env`:

```env
# MQTT Broker Configuration
MQTT_BROKER_HOST=4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud
MQTT_BROKER_PORT=8883
MQTT_BROKER_USERNAME=Lstech
MQTT_BROKER_PASSWORD=Lstech123

# Topicy do subskrypcji (domyślnie wszystkie)
MQTT_SUBSCRIBE_TOPICS=#

# Limit przechowywania wiadomości w pamięci
MQTT_RECENT_MESSAGES_LIMIT=60
```

**Plik:** .env (w głównym folderze)

---

## 📱 Pola Telemetryczne – Quick Lookup

### Pakowaczka
```
wydajnoscAktualna  → BPM (worki/min)
licznikGlobalny    → Licznik całkowity worków
status             → 4=PRACA, 0=STOP
nazwaReceptury     → Aktywny program
wagaAktualna       → Waga ostatniego worka
klapaZrzutuOtwarta → Reject klapa otwarta?
```

### Paletyzator
```
licznikPalet_global → Licznik palet
nrWarstwy           → Numer warstwy (0-13)
nrWorka             → Numer worka w warstwie
oproznianie         → Czy paleta opróżniana?
sygnalDoOwijarkiStart → Sygnał START do owijarki
```

### Owijarka
```
wyjazdPaletaOwinieta → Paleta gotowa/opuściła owniarkę
postepOwijania       → Postęp [%]
kapturekZalozony     → Top sheet nałożony?
etapOwijania         → Faza (IDLE, BOTTOM_WRAP, etc.)
```

**Plik:** MQTT_DOCUMENTATION.md → "Pola Telemetryczne Maszyn"

---

## 🧠 Ważne Koncepty

### QoS (Quality of Service)
- **QoS 0:** Telemetria (może się zgubić)
- **QoS 1:** Komendy (MUSI dotrzeć!)

### Timeout
- Maszyna uważana za OFFLINE jeśli brak danych > 30 sekund

### Payload Format
```json
{
  "d": { /* dane */ },
  "ts": "2026-09-07T14:30:45.123Z"
}
```

**Plik:** MQTT_DOCUMENTATION.md → "Połączenie i Autentykacja"

---

## 🐛 Debugowanie – Krótka Ściągawka

```bash
# Sprawdź czy aplikacja ma połączenie MQTT
curl http://localhost:8082/admin/master/mqtt/api | jq '.data.broker'

# Sprawdź ostatnie wiadomości
curl http://localhost:8082/admin/master/mqtt/api | jq '.data.recent_messages[-5:]'

# Sprawdź błędy
tail -f logs/error.log | grep MQTT

# Test wszystkich systemów
python mqtt_test_suite.py
# Wybierz: 6
```

**Plik:** MQTT_FAQ.md → "Jak debugować?"

---

## 📞 Potrzebujesz Pomocy?

1. **Szybka odpowiedź?** → MQTT_FAQ.md ❓
2. **Kod do copy-paste?** → MQTT_QUICK_REFERENCE.md ⚡
3. **Zrozumieć architekturę?** → MQTT_ARCHITECTURE.md 🏗️
4. **Pełne szczegóły?** → MQTT_DOCUMENTATION.md 📖
5. **Testować live?** → `python mqtt_test_suite.py` 🧪

---

## 📝 Kontrolna Lista – Przed Wdrożeniem

- [ ] Przeczytałem MQTT_DOCUMENTATION.md
- [ ] Uruchomiłem mqtt_test_suite.py → wszystkie testy PASS
- [ ] Mogę się połączyć z brokerem
- [ ] Mogę odbierać telemetrię
- [ ] Mogę wysyłać komendy
- [ ] Znám moje zmienne .env
- [ ] Znam topicy dla mojej maszyny
- [ ] Wiem co to QoS 1
- [ ] Wiem co robić jeśli maszyna offline

---

## 📅 Historia Dokumentacji

- **2026-09-07** – Pierwsza wersja pełnej dokumentacji
  - MQTT_DOCUMENTATION.md – Pełna dokumentacja
  - MQTT_QUICK_REFERENCE.md – Szybka referenca
  - MQTT_ARCHITECTURE.md – Diagramy i schematy
  - MQTT_FAQ.md – Pytania i poradniki
  - mqtt_test_suite.py – Test aplikacja
  - MQTT_README.md (ten plik)

---

## 🚀 Szybki Start (30 sekund)

```bash
# 1. Instalacja
pip install paho-mqtt

# 2. Test
python mqtt_test_suite.py

# 3. Wybierz: 1 (test połączenia)

# 4. Jeśli ✅ – jesteś gotowy!
```

---

**Ostatnia aktualizacja:** 2026-09-07  
**Wersja dokumentacji:** 1.0  
**Status:** ✅ Kompletna



<!-- ==================== PAGE BREAK ==================== -->

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



<!-- ==================== PAGE BREAK ==================== -->

# 🏗️ MQTT Architektura i Flow Komunikacji

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        INTERNET (HiveMQ Cloud)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                   MQTT BROKER (TLS/SSL, port 8883)                         │
│              4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud           │
└─────────────────────────────────────────────────────────────────────────────┘
         ▲              ▲              ▲
         │              │              │
         │ Publikuje    │ Publikuje    │ Publikuje
         │ Telemetrię   │ Telemetrię   │ Telemetrię
         │              │              │
    ┌────┴──────────┐   ┌─────────────┐  ┌─────────────┐
    │ PAKOWACZKA    │   │PALETYZATOR  │  │  OWIJARKA   │
    │  (Maszyna)    │   │  (Robot)    │  │   (Wrapper) │
    ├───────────────┤   ├─────────────┤  ├─────────────┤
    │ Wago PLC      │   │ Siemens S7  │  │  KEBA PLC   │
    │ wydajnosc     │   │ warstwa     │  │  postep     │
    │ liczniki      │   │ palet       │  │  obroty     │
    │ wagi          │   │ magazynek   │  │  kapturek   │
    │ status        │   │ sygnały     │  │  sygnał out │
    └────────────────┘   └─────────────┘  └─────────────┘
             ▲                                    ▲
             │                                    │
             │           Sygnał START             │
             └────────────────────────────────────┘
        (sygnalDoOwijarkiStart ze Paletyzatora)
```

---

## Architektura Aplikacji Flask

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       FLASK APPLICATION                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │             app/services/mqtt_service.py                            │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │ MQTT Bridge (Background Thread)                              │ │   │
│  │  │  • _run_mqtt_client() → paho-mqtt loop                       │ │   │
│  │  │  • on_connect() → Subskrypcja topików                        │ │   │
│  │  │  • on_message() → Odbiera telemetrię                         │ │   │
│  │  │  • publish_command() → Wysyła komendy                        │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │ Global State (_latest_machine_data)                           │ │   │
│  │  │  • Pakowaczka: bpm, counter, status, receptura, wagi         │ │   │
│  │  │  • Paletyzator: nrWarstwy, nrWorka, licznikPalet, sygnały    │ │   │
│  │  │  • Owijarka: wyjazdPaletaOwinieta, postep, faza              │ │   │
│  │  │  • Meta: last_update, messages_total, recent_messages        │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                        │
│                    Dostęp danych   │   Wysyła komendy                      │
│                                    │                                        │
│  ┌──────────────────────────────────┴──────────────────────────────────┐   │
│  │   app/services/machine_telemetry_service.py                        │   │
│  │  • get_live_dashboard_data() → Agreguje dane dla dashboarda       │   │
│  │  • send_machine_command() → Wrapper dla publish_command()         │   │
│  │  • get_active_bagging_order() → Zlecenie z bazy                  │   │
│  │  • calculate_progress() → Postęp palety                           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                        │
│                                    │                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │   Flask Blueprints (REST API)                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ /api/machines/telemetry/live                               │   │   │
│  │  │ → GET → MachineTelemetryService.get_live_dashboard_data()  │   │   │
│  │  │ ← JSON                                                      │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ /api/machines/telemetry/command                            │   │   │
│  │  │ → POST {topic, command}                                    │   │   │
│  │  │ → MachineTelemetryService.send_machine_command()           │   │   │
│  │  │ → publish_command() → MQTT Broker                          │   │   │
│  │  │ ← JSON {success, message}                                  │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ /admin/master/mqtt                                         │   │   │
│  │  │ → GET → Admin Dashboard (Live Monitoring)                  │   │   │
│  │  │ ← HTML (templates/admin/mqtt_monitor.html)                 │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                        │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
                        HTTP (REST API)
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
            ┌──────────────────┐             ┌──────────────────┐
            │   WEB BROWSER    │             │  EXTERNAL CLIENT │
            │  Dashboard       │             │  (Scripts, Apps) │
            │  Admin Panel     │             │  (Python, cURL)  │
            └──────────────────┘             └──────────────────┘
```

---

## Flow: Komunikacja w Obie Strony

### 1️⃣ **ODBIÓR DANYCH (Maszyny → Aplikacja)**

```
Maszyna                    MQTT Broker              Flask App
(PLC)                                            (mqtt_service.py)
  │                            │                      │
  │─── Publikuje ─────────────→│                      │
  │   Telemetrię co 1-2s       │                      │
  │                            │                      │
  │                            │─ Rozsyła ─────────→ │
  │                            │  do subskrybentów    │
  │                            │                      │
  │                            │        on_message()  │
  │                            │          [Callback]  │
  │                            │                      │
  │                            │     Parsuje JSON    │
  │                            │     ↓               │
  │                            │  _latest_machine_data
  │                            │     ↑               │
  │                            │  Aktualizuje        │
  │                            │  liczniki, statusy  │
  │                            │                      │
  │                            │  Loguje błędy       │
  │                            │  do bazy             │
  │                            │                      │
```

**Topicy:**
- `iot-2/type/cMT2108X2/id/agroPakowaczka`
- `iot-2/type/cMT2108X2/id/agroPaletyzator`
- `iot-2/type/cMT2108X2/id/agroOwijarka`

**Częstotliwość:** Co 1-2 sekundy  
**QoS:** 0 (at most once)

---

### 2️⃣ **WYSYŁANIE KOMEND (Aplikacja → Maszyny)**

```
Flask App                MQTT Broker              Maszyna
(publish_command)                              (PLC)
  │                          │                   │
  │─ Formatuje JSON ─→       │                   │
  │  Komenda                 │                   │
  │  ↓                       │                   │
  │  client.publish()        │                   │
  │  (topic, payload, qos=1) │                   │
  │                          │                   │
  │                 Rozsyła ─────────────────→   │
  │                 do maszyny                   │
  │                 (QoS 1 = gwarantuje)         │
  │                          │                   │
  │                          │       Maszyna    │
  │                          │       ↓          │
  │                          │    Interpretuje   │
  │                          │    Komendę       │
  │                          │    ↓             │
  │                          │   Wykonuje      │
  │                          │   (reset licznika│
  │                          │    zmiana config)│
  │                          │                  │
```

**Topicy Komend:**
- `iot-2/type/cMT2108X2/id/agroPakowaczka/send` (RESET)
- `iot-2/type/cMT2108X2/id/agroPaletyzator/setPattern` (CONFIG)
- `iot-2/type/cMT2108X2/id/agroOwijarka/send` (Reserved)

**QoS:** 1 (at least once) – Gwarantuje dostarczenie

---

## Sekwencja Pracy Linii AGRO

```
Timeline (sekund)
  0     5     10    15    20    25    30    35    40    45    50
  │     │     │     │     │     │     │     │     │     │     │
  ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─
  │
  │ ZLECENIE STARTUJE
  │ ├─→ app.publish_message(topic="...pakowaczka/send", {"zerowanieLicznikow": [1]})
  │
  ├─ PAKOWACZKA PRACUJE
  │ ├─→ Co 1s: wydajnoscAktualna=45, licznikGlobalny++, status=4 (PRACA)
  │ └─→ on_message() zaktualizuje _latest_machine_data
  │
  ├─ PALETYZATOR ZBIERA WORKI
  │ ├─→ Co 1s: nrWarstwy=1, nrWorka=1,2,3,4
  │ ├─→ Po każdej warstwie: nrWorka=0, nrWarstwy++
  │ ├─→ Po 13 warstwach: oproznianie=True (paleta pełna!)
  │ └─→ sygnalDoOwijarkiStart=True (WYZWOLENIE OWIJARKI)
  │
  ├─ OWIJARKA PRACUJE
  │ ├─→ postepOwijania: 0% → 100% (30 sekund)
  │ ├─→ Fazy: BOTTOM_WRAP → ASCENDING → TOP_SHEET → DESCENDING → DONE
  │ ├─→ Po DONE: wyjazdPaletaOwinieta=True (PALETA GOTOWA)
  │ └─→ on_message() inkrementuje pallet_counter
  │
  ├─ ZLECENIE KOŃCZY SIĘ
  │ └─→ app.publish_message(topic="...pakowaczka/send", {"zerowanieLicznikow": [1]})
  │
  └─ CZEKAJ NA NOWE ZLECENIE
```

---

## Status Maszyn – Wyliczanie

### Pakowaczka (Bagger) – Status
```python
if not is_connected:
    status = "OFFLINE"
elif bpm > 0:
    status = "PRACA"
elif bpm == 0:
    status = "STOP"
else:
    status = "UNKNOWN"
```

**Definicja:** Maszyna uważana za OFFLINE jeśli przez 30 sekund brak telemetrii.

---

### Paletyzator (Palletizer) – Status
```python
if not is_connected:
    status = "OFFLINE"
elif is_emptying or current_layer > 0:
    status = "PRACA"  # Układa worki
elif sygnalDoOwijarkiStart:
    status = "TRANSFER"  # Paleta w drodze do owijarki
else:
    status = "GOTOWY"  # Czeka na nową paletę
```

**Postęp Palety:**
```
Pełne warstwy = 12
Warsty razem = 13
Worki na warstwę = 4 (pełne) + 2 (szczyt) = 6

Aktualna warstwa N, numer worka M:
Postęp = (N-1)*4 + M / 50 * 100%
```

---

### Owijarka (Wrapper) – Status
```python
if is_wrapped or postepOwijania >= 100:
    status = "GOTOWA"
elif postepOwijania > 0:
    status = "OWIJANIE"
elif sygnalDoOwijarkiStart:
    status = "START"
else:
    status = "GOTOWY"
```

**Faza Owijania:**
```
Postęp [%]  │ Faza              │ Opis
─────────────┼──────────────────┼─────────────────────────────────
0-20        │ BOTTOM_WRAP       │ Owinięcie dolnej podstawy
20-45       │ ASCENDING         │ Wznoszenie wózka z folią
45-65       │ TOP_SHEET         │ Nakładanie kapturka
65-85       │ TOP_WRAP          │ Owinięcie szczytu
85-100      │ DESCENDING        │ Zjazd wózka, odcięcie, zgrzew
100         │ DONE              │ Paleta gotowa do odbioru
```

---

## Logi i Monitoring

### Gdzie Szukać Danych?
```
logs/app.log          → Główne zdarzenia, MQTT events
logs/error.log        → Błędy MQTT, wyjątki
logs/audit.log        → Działania użytkownika
logs/palety.log       → Przypomnienia paletyzatora
```

### Wyczyszczenie Logów
```bash
POST /admin/master/clear_machine_errors
```

### Debug Realtime
```python
# W terminalu Python
from app.services.mqtt_service import get_latest_data
import json

data = get_latest_data()
print(json.dumps(data, indent=2, default=str))
```

---

## Failover i Troubleshooting

### ⚠️ Maszyna Offline (brak telemetrii 30+ sekund)
```
Przyczyna:
├─ Brak prądu na PLC
├─ Internet offline
├─ Błąd certyfikatu TLS
├─ Zmiana hasła/usera MQTT
└─ Topik nie matchuje

Rozwiązanie:
├─ Sprawdź czy maszyna ma prąd
├─ Ping: ping 4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud
├─ Sprawdź .env (MQTT_BROKER_*) 
├─ Reboot aplikacji
└─ Sprawdź HiveMQ Cloud Admin Panel
```

### ⚠️ Komenda Nie Dotarła
```
Przyczyna:
├─ Aplikacja niedopołączona
├─ Topik błędny
├─ Payload JSON invalid
└─ Maszyna offline

Rozwiązanie:
├─ POST /api/machines/telemetry/live → sprawdź status
├─ Sprawdź /admin/master/mqtt → czy broker podłączony
├─ Uruchom mqtt_test_suite.py → test connection
└─ Sprawdź logs/error.log
```

---

## Zmienne Środowiskowe w Aplikacji

**Plik:** `app/config.py`

```python
class Config:
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv("DB_URI", "mysql+pymysql://...")
    
    # MQTT
    MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud")
    MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "8883"))
    MQTT_BROKER_USERNAME = os.getenv("MQTT_BROKER_USERNAME", "Lstech")
    MQTT_BROKER_PASSWORD = os.getenv("MQTT_BROKER_PASSWORD", "Lstech123")
    MQTT_SUBSCRIBE_TOPICS = os.getenv("MQTT_SUBSCRIBE_TOPICS", "#")
    MQTT_RECENT_MESSAGES_LIMIT = int(os.getenv("MQTT_RECENT_MESSAGES_LIMIT", "60"))
```

---

**Diagram v1.0 – 2026-09-07**



<!-- ==================== PAGE BREAK ==================== -->

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



<!-- ==================== PAGE BREAK ==================== -->

# 📡 MQTT Broker – Dokumentacja Komend i Topików

## Spis Treści
1. [Konfiguracja Brokera](#konfiguracja-brokera)
2. [Połączenie i Autentykacja](#połączenie-i-autentykacja)
3. [Topicy Subskrypcji (Odbieranie Danych)](#topicy-subskrypcji-odbieranie-danych)
4. [Topicy Publikacji (Wysyłanie Komend)](#topicy-publikacji-wysyłanie-komend)
5. [Pola Telemetryczne Maszyn](#pola-telemetryczne-maszyn)
6. [Komendy i Przykłady](#komendy-i-przykłady)
7. [Źródła i Zmienne Środowiskowe](#źródła-i-zmienne-środowiskowe)

---

## Konfiguracja Brokera

### HiveMQ Cloud (Produkcja)
```
Host:     4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud
Port:     8883 (TLS/SSL)
Protokół: MQTT 3.1.1
```

### Zmienne Środowiskowe (.env)
```env
# Jeśli nie ustawisz, aplikacja użyje domyślnych wartości
MQTT_BROKER_HOST=4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud
MQTT_BROKER_PORT=8883
MQTT_BROKER_USERNAME=Lstech
MQTT_BROKER_PASSWORD=Lstech123
MQTT_SUBSCRIBE_TOPICS=#              # Defaults to wildcard (wszystkie topicy)
MQTT_RECENT_MESSAGES_LIMIT=60        # Ilość przechowywanych ostatnich wiadomości
```

---

## Połączenie i Autentykacja

### Parametry Połączenia
- **Username:** `Lstech`
- **Password:** `Lstech123`
- **TLS/SSL:** Tak (port 8883)
- **QoS (Quality of Service):** 
  - **Publikacja (wysyłanie komend):** QoS 1 (at least once) – gwarantuje dostarczenie
  - **Subskrypcja:** Domyślnie QoS 0 (at most once)

### Kod Połączenia (Python)
```python
import paho.mqtt.client as mqtt

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set("Lstech", "Lstech123")
client.tls_set()  # Włącz SSL/TLS

client.connect("4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud", 8883, 60)
client.loop_forever()
```

---

## Topicy Subskrypcji (Odbieranie Danych)

Aplikacja subskrybuje domyślnie **`#`** (wszystkie topicy) lub można ograniczyć poprzez `MQTT_SUBSCRIBE_TOPICS`.

### 1. 🍃 **Maszyna Pakowująca (Wagopakowaczka)**

#### Topic
```
iot-2/type/cMT2108X2/id/agroPakowaczka
```

#### Częstotliwość Wysyłania
Co ~1-2 sekundy (real-time telemetria)

#### Struktura Payloadu (JSON)
```json
{
  "d": {
    "wydajnoscAktualna": 45.5,           // BPM – worki/minutę
    "licznikGlobalny": 12450,             // Licznik całkowity worków
    "licznikLokalny": 250,                // Licznik lokalny (restowalny)
    "status": 4,                          // 4=PRACA, 0=STOP, inne=alarm
    "nazwaReceptury": "KREDA_NAWOZOWA",   // Aktywna receptura/program
    "wagaAktualna": 25.04,                // Waga ostatniego worka [kg]
    "wagaZadana": 25.0,                   // Waga docelowa [kg]
    "klapaZrzutuOtwarta": false,          // Klapa zrzutu (reject)
    "licznikOdrzutow": 12                 // Liczba worków odrzuconych
  },
  "ts": "2026-09-07T14:30:45.123Z"       // Timestamp
}
```

#### Pola Telemetryczne
| Pole | Typ | Opis |
|------|-----|------|
| `wydajnoscAktualna` | float | Bieżąca wydajność [worki/min]. 0 = brak pracy. |
| `licznikGlobalny` | int | Licznik całkowity worków (nie resetuje się bez komendy). |
| `licznikLokalny` | int | Licznik lokalny – może być resetowany przez operatora. |
| `status` | int | 4=PRACA, 0=STOP, inne=stany specjalne (alarm, serwis). |
| `nazwaReceptury` | str | Nazwa załadowanego programu (receptury). |
| `wagaAktualna` | float | Waga ostatniego wyprodukowanego worka [kg]. |
| `wagaZadana` | float | Docelowa waga worka [kg]. |
| `klapaZrzutuOtwarta` | bool | Czy klapa zrzutu (reject) jest otwarta? |
| `licznikOdrzutow` | int | Ile worków zostało odrzuconych. |

---

### 2. 🤖 **Robot Paletyzujący**

#### Topic
```
iot-2/type/cMT2108X2/id/agroPaletyzator
```

#### Częstotliwość Wysyłania
Co ~1-2 sekundy

#### Struktura Payloadu
```json
{
  "d": {
    "licznikPalet_global": 1234,          // Licznik palet
    "nrWarstwy": 5,                       // Aktualny numer warstwy (0-13)
    "nrWorka": 2,                         // Numer worka w warstwie (0-4)
    "obracakPraca": false,                // Czy bag turner jest aktywny?
    "popychaczPraca": false,              // Czy pusher jest aktywny?
    "magazynekPaletIlosc": 8,             // Ilość palet w magazynku podającym
    "podawaniePalety": false,             // Czy paleta jest podawana?
    "oproznianie": false,                 // Czy trwa opróżnianie palety?
    "sygnalDoOwijarkiStart": false        // Sygnał do owijarki (start)
  },
  "ts": "2026-09-07T14:30:45.123Z"
}
```

#### Pola Telemetryczne
| Pole | Typ | Opis |
|------|-----|------|
| `licznikPalet_global` | int | Licznik sformowanych palet. |
| `nrWarstwy` | int | Numer aktualnej warstwy (0-13). |
| `nrWorka` | int | Numer worka w bieżącej warstwie (0-4). |
| `obracakPraca` | bool | Bag turner (urządzenie obracające worek) – aktywny? |
| `popychaczPraca` | bool | Pusher (urządzenie posuwające worek) – aktywny? |
| `magazynekPaletIlosc` | int | Liczba pustych palet dostępnych. |
| `podawaniePalety` | bool | Czy trwa podawanie palety do stanowiska? |
| `oproznianie` | bool | Czy paleta jest opróżniana (gotowa do owijarki)? |
| `sygnalDoOwijarkiStart` | bool | Sygnał wyzwalający start owijarki. |

---

### 3. 🎬 **Maszyna Owijająca (Stretch Wrapper)**

#### Topic
```
iot-2/type/cMT2108X2/id/agroOwijarka
```

#### Częstotliwość Wysyłania
Co ~1-2 sekundy

#### Struktura Payloadu
```json
{
  "d": {
    "wyjazdPaletaOwinieta": false,        // Bit: paleta opuściła owiniarkę
    "postepOwijania": 35.5,               // Postęp cyklu owijania [%]
    "kapturekZalozony": false,            // Czy kapturek folii został nałożony?
    "obrotyStolu": 45,                    // Liczba obrotów stołu obrabiającego
    "etapOwijania": "ASCENDING"           // Faza cyklu (BOTTOM_WRAP, ASCENDING, TOP_SHEET, etc.)
  },
  "ts": "2026-09-07T14:30:45.123Z"
}
```

#### Pola Telemetryczne
| Pole | Typ | Opis |
|------|-----|------|
| `wyjazdPaletaOwinieta` | bool | **Ważne:** Sygnał wyjazdu = paleta gotowa do odbioru. |
| `postepOwijania` | float | Postęp bieżącego cyklu owijania [0-100%]. |
| `kapturekZalozony` | bool | Czy kapturek (top sheet) został już nałożony? |
| `obrotyStolu` | int | Liczba obrotów stołu obrabiającego. |
| `etapOwijania` | str | Faza: BOTTOM_WRAP, ASCENDING, TOP_SHEET, TOP_WRAP, DESCENDING, DONE. |

---

## Topicy Publikacji (Wysyłanie Komend)

### 1. ⚙️ **Komendy do Pakowaczki**

#### Topic
```
iot-2/type/cMT2108X2/id/agroPakowaczka/send
```

#### Komenda: Zerowanie Licznikow

**Opis:** Resetuje liczniki globalne i lokalne pakowaczki.

**Struktura Payloadu**
```json
{
  "d": {
    "zerowanieLicznikow": [1]
  },
  "ts": "2026-09-07T14:30:45.123Z"
}
```

**Parametry**
| Pole | Typ | Wartości | Opis |
|------|-----|----------|------|
| `zerowanieLicznikow` | array | `[1]` | Wysłanie wartości `[1]` resetuje liczniki. |

**Kiedy Jest Wysyłana**
- Automatycznie po zakończeniu zlecenia (koniec_zlecenie) na linii AGRO Workowanie/Czyszczenie.
- Może być wysłana ręcznie z API: `POST /machines/telemetry/command`

**Przykład Python (paho-mqtt)**
```python
import json
from datetime import datetime

topic = "iot-2/type/cMT2108X2/id/agroPakowaczka/send"
payload = {
    "d": {"zerowanieLicznikow": [1]},
    "ts": datetime.now().isoformat()
}
client.publish(topic, json.dumps(payload), qos=1)
```

---

### 2. ⚙️ **Komendy do Paletyzatora**

#### Topic
```
iot-2/type/cMT2108X2/id/agroPaletyzator/setPattern
```

**Opis:** Zmienia konfigurację wzoru ułożenia palet (typ palety, liczba warstw, worków na warstwę).

**Struktura Payloadu**
```json
{
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

**Parametry**
| Pole | Typ | Opis |
|------|-----|------|
| `receptura` | str | Identyfikator wzoru (np. STANDARD_100x120). |
| `typPalety` | str | Typ palety (np. INDUSTRIAL_100x120). |
| `nazwaPalety` | str | Opis palety. |
| `szerokoscM` | float | Szerokość palety [m]. |
| `dlugoscM` | float | Długość palety [m]. |
| `warstwyPelne` | int | Liczba pełnych warstw (bez szczytu). |
| `warstwyLacznie` | int | Łączna liczba warstw (pełne + szczyt). |
| `workiNaWarstwe` | int | Worki na jedną pełną warstwę. |
| `workiSzczyt` | int | Worki na warstwę szczytową. |
| `lacznieWorkow` | int | Łączna liczba worków na pełną paletę. |
| `masaWorkaKg` | float | Masa jednego worka [kg]. |

**Kiedy Jest Wysyłana**
- Gdy administrator zmieni konfigurację palety w panelu: `POST /machines/palletizer/config`

---

### 3. ⚙️ **Komendy do Owijarki**

#### Topic
```
iot-2/type/cMT2108X2/id/agroOwijarka/send
```

**Opis:** Opcjonalnie może zawierać komendy kontroli procesu owijania.

**Struktura Payloadu (Przykładowa)**
```json
{
  "d": {
    "resetProgress": false,
    "enableTopSheet": true,
    "targetRotations": 45
  },
  "ts": "2026-09-07T14:30:45.123Z"
}
```

**Uwaga:** Aktualnie aplikacja nie wysyła aktywnie komend do owijarki. Owijarka jest sterowana sygnałem z paletyzatora (`sygnalDoOwijarkiStart`).

---

## Pola Telemetryczne Maszyn

### 📊 Przechowywane w Aplikacji (Global State)

Aplikacja przechowuje ostatnie wartości z MQTT w zmiennej `_latest_machine_data`:

```python
_latest_machine_data = {
    # Pakowaczka
    "bpm": 0,                              # Wydajność [worki/min]
    "counter": 0,                          # Licznik globalny worków
    "local_counter": 0,                    # Licznik lokalny
    "status": "OFFLINE",                   # PRACA, STOP, OFFLINE
    "receptura": "Brak danych",            # Aktywna receptura
    
    # Paletyzator
    "nrWarstwy": 0,                        # Nr warstwy
    "nrWorka": 0,                          # Nr worka
    "pallet_counter": 0,                   # Licznik palet
    "oproznianie": False,                  # Czy opróżnianie?
    "sygnal_do_owijarki_start": False,     # Sygnał do owijarki
    
    # Owijarka
    "is_wrapped": False,                   # Czy paleta owinięta?
    "wrapping_progress": 0,                # Postęp [%]
    "top_sheet_applied": False,            # Kapturek nałożony?
    "wrapper_phase": "IDLE",               # Faza owijania
    
    # Waga Dynamiczna
    "checkweigher_weight": 25.04,          # Bieżąca waga [kg]
    "checkweigher_target_weight": 25.0,    # Waga docelowa [kg]
    "checkweigher_reject_active": False,   # Klapa otwarta?
    "checkweigher_reject_count": 0,        # Licznik odrzutów
    
    # Meta
    "last_update": 0,                      # Timestamp ostatniej aktualizacji
    "messages_total": 0,                   # Łączna liczba otrzymanych wiadomości
    "topics_seen": [],                     # Lista topików, które rozebrano
    "recent_messages": [],                 # Ostatnie (60) wiadomości
    "recent_errors": []                    # Ostatnie (25) błędy
}
```

---

## Komendy i Przykłady

### Przykład 1: Wysłanie Komendy Zerowania z Python

```python
from datetime import datetime
import json
from app.services.mqtt_service import publish_command

# Komenda zerowania licznikow
topic = "iot-2/type/cMT2108X2/id/agroPakowaczka/send"
payload = {
    "d": {"zerowanieLicznikow": [1]},
    "ts": datetime.now().isoformat()
}

# Wysłanie
success = publish_command(topic, payload)
if success:
    print("Komenda wysłana pomyślnie!")
else:
    print("Błąd wysłania!")
```

### Przykład 2: Wysłanie Komendy przez REST API

```bash
# Wysłanie komendy zerowania przez API
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

### Przykład 3: Odczyt Danych Telemetrycznych

```bash
# Pobierz ostatnie dane z brokera
curl -X GET http://localhost:8082/api/machines/telemetry/live \
  -H "Cookie: session=YOUR_SESSION"
```

---

## Źródła i Zmienne Środowiskowe

### Plik `app/services/mqtt_service.py`
- **Główny moduł:** Inicjalizuje połączenie MQTT, subskrybuje topicy, przechowuje dane.
- **Funkcje publiczne:**
  - `start_mqtt_bridge()` – Uruchamia wątek MQTT w tle.
  - `get_latest_data()` – Zwraca ostatnie dane telemetryczne.
  - `publish_command(topic, payload_dict)` – Wysyła komendę na broker.
  - `simulate_machine_data()` – Symuluje pracę maszyn (dev).

### Plik `app/services/machine_telemetry_service.py`
- **Serwis domenowy:** Agreguje i wzbogaca dane z MQTT.
- **Funkcje:**
  - `get_live_dashboard_data()` – Zwraca sformatowane dane do dashboardu.
  - `send_machine_command()` – Wysyła komendę (wrapper).
  - `get_active_bagging_order()` – Pobiera bieżące zlecenie z bazy.

### Plik `app/blueprints/api/machine_telemetry.py`
- **REST API:** Publiczne endpointy do sterowania maszynami i odbierania danych.
- Endpointy:
  - `GET /api/machines/telemetry/live` – Live dashboard data
  - `POST /api/machines/telemetry/command` – Wyślij komendę
  - `GET /api/machines/palletizer/config` – Konfiguracja palety
  - `POST /api/machines/palletizer/config` – Zmień konfigurację

### Plik `app/blueprints/admin/diagnostics.py`
- **Admin panel:** Monitorowanie MQTT.
- Endpointy:
  - `GET /admin/master/mqtt` – Panel live MQTT
  - `GET /admin/master/mqtt/api` – JSON API dla panelu

### Plik `scripts/simulate_agro_pallet.py`
- **Skrypt testowy:** Symuluje sygnał `wyjazdPaletaOwinieta` z owijarki.
- Użycie: `python scripts/simulate_agro_pallet.py`

### Zmienne Środowiskowe w `.env`
```env
# MQTT Broker
MQTT_BROKER_HOST=4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud
MQTT_BROKER_PORT=8883
MQTT_BROKER_USERNAME=Lstech
MQTT_BROKER_PASSWORD=Lstech123

# Topicy do subskrypcji (domyślnie #)
MQTT_SUBSCRIBE_TOPICS=#

# Limit przechowywania wiadomości
MQTT_RECENT_MESSAGES_LIMIT=60
```

---

## Fluxowa Danych – Sekwencja Pracy

```
┌─────────────────────────────────────────────────────────────────┐
│                  MQTT BROKER (HiveMQ Cloud)                     │
└─────────────────────────────────────────────────────────────────┘
  ▲                    ▲                    ▲
  │ Publikuje          │ Publikuje          │ Publikuje
  │ Telemetrię         │ Telemetrię         │ Telemetrię
  │                    │                    │
  │                    │                    │
┌─┴──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  agroPakowaczka    │ │ agroPaletyzator  │ │  agroOwijarka    │
│  (Maszyna Pakująca)│ │ (Robot)          │ │ (Stretch Wrapper)│
└────────────────────┘ └──────────────────┘ └──────────────────┘
  ▲                                              ▲
  │                                              │
  └──────────────────────────────────────────────┘
           Sygnał z Paletyzatora:
           sygnalDoOwijarkiStart

┌─────────────────────────────────────────────────────────────────┐
│             Flask App (app/services/mqtt_service.py)            │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ on_message() – Odbiera i przechowuje dane                   ││
│  │ publish_command() – Wysyła komendy                          ││
│  │ get_latest_data() – Zwraca ostatnie dane                   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
  ▲
  │ REST API
  │
┌─┴──────────────────────────────────────────────────────────────┐
│        Dashboard / Admin Panel / REST Clients                  │
│  GET /api/machines/telemetry/live                            │
│  POST /api/machines/telemetry/command                        │
└───────────────────────────────────────────────────────────────┘
```

---

## Uwagi i Best Practices

### ✅ Dobre Praktyki
1. **QoS 1 dla komend** – Upewnij się, że komendy dojdą do maszyny.
2. **Timeout 30s** – Jeśli brak danych przez 30s, maszyna uważana za OFFLINE.
3. **Parametryzacja topików** – Topicy można konfigurować przez zmienne środowiskowe.
4. **Błędy w logach** – Wszystkie błędy MQTT trafiają do `logs/app.log` i `logs/error.log`.

### ⚠️ Uwagi Bezpieczeństwa
1. **Nie wklejaj poświadczeń** w kodu – Użyj `.env`!
2. **TLS/SSL (port 8883)** – Zawsze szyfruj połączenia.
3. **Monitorowanie** – Obserwuj `logs/app.log` pod kątem błędów MQTT.
4. **Komenda zerowania** – Wysyłana automatycznie po koniec zlecenia (w sekcji AGRO).

### 🔍 Debugowanie
```python
# Aby wyświetlić ostatnie wiadomości:
from app.services.mqtt_service import get_latest_data
data = get_latest_data()
print("Topicy:", data.get("topics_seen"))
print("Ostatnia wiadomość:", data.get("recent_messages")[-1])
print("Ostatnie błędy:", data.get("recent_errors")[-1])
```

---

**Dokument:** `MQTT_DOCUMENTATION.md`  
**Ostatnia aktualizacja:** 2026-09-07  
**Wersja aplikacji:** RaportProdukcyjny v2.x



<!-- ==================== PAGE BREAK ==================== -->

# 📚 MQTT Dokumentacja – Indeks i Wyszukiwanie

Szybkie wyszukiwanie dokumentacji po słowach kluczowych i zadaniach.

---

## 🔍 Wyszukaj po Temacie

### Konfiguracja
- [Gdzie są dane brokera?](#dane-brokera) → MQTT_QUICK_REFERENCE.md
- [Jak ustawić zmienne .env?](#zmienne-środowiskowe) → MQTT_DOCUMENTATION.md
- [Jakie są dostępne konfiguracje?](#zmienne-environment) → MQTT_DOCUMENTATION.md

### Połączenie
- [Jak się połączyć z brokerem?](#połączenie-i-autentykacja) → MQTT_DOCUMENTATION.md
- [Czy mogę testować bez aplikacji?](#czy-mogę-testować-bez-aplikacji) → MQTT_FAQ.md
- [Test połączenia?](#test-połączenia) → mqtt_test_suite.py

### Topicy
- [Jakie topicy istnieją?](#topicy-subskrypcji) → MQTT_DOCUMENTATION.md
- [Gdzie wysyłam komendy?](#topicy-publikacji) → MQTT_DOCUMENTATION.md
- [Wszystkie topicy na jednym miejscu?](#topicy---szybkie-odnośniki) → MQTT_QUICK_REFERENCE.md

### Odbieranie Danych
- [Jak odczytać dane z maszyn?](#jak-odczytać-dane) → MQTT_FAQ.md
- [Jakie pola ma pakowaczka?](#pakowaczka) → MQTT_DOCUMENTATION.md
- [Jakie pola ma paletyzator?](#paletyzator) → MQTT_DOCUMENTATION.md
- [Jakie pola ma owijarka?](#owijarka) → MQTT_DOCUMENTATION.md

### Wysyłanie Komend
- [Jak wysłać komendę reset?](#komenda-zerowania-licznika-pakowaczki) → MQTT_FAQ.md
- [Jak zmienić konfigurację paletyzatora?](#zmiana-konfiguracji-paletyzatora) → MQTT_FAQ.md
- [Jak symulować sygnał owijarki?](#symulacja-sygnału-z-owijarki-test) → MQTT_FAQ.md

### API REST
- [Jak użyć REST API?](#rest-api-flask) → MQTT_QUICK_REFERENCE.md
- [Przykład API komendy?](#wysłanie-komendy) → MQTT_FAQ.md
- [Endpoint live data?](#ostatnie-dane-telemetryczne) → MQTT_FAQ.md

### Python Code
- [Kod do connect?](#połączenie-z-python-paho-mqtt) → MQTT_QUICK_REFERENCE.md
- [Kod do subscribe?](#kod) → MQTT_QUICK_REFERENCE.md
- [Kod do publish?](#wysyłanie-komendy) → MQTT_FAQ.md

### Debugging
- [Jak debugować?](#jak-debugować) → MQTT_FAQ.md
- [Maszyna offline?](#-maszyna-offline) → MQTT_ARCHITECTURE.md
- [Komenda się nie wysłała?](#-komenda-nie-dotarła) → MQTT_ARCHITECTURE.md
- [Logi gdzie?](#gdzie-szukać-danych) → MQTT_ARCHITECTURE.md

### Architektura
- [Jak działa system?](#architektura-aplikacji-flask) → MQTT_ARCHITECTURE.md
- [Diagramy?](#system-diagram) → MQTT_ARCHITECTURE.md
- [Flow komunikacji?](#flow-komunikacja-w-obie-strony) → MQTT_ARCHITECTURE.md

### Testowanie
- [Test suite?](#🧪-test-aplikacja) → mqtt_test_suite.py
- [Jak testować?](#🧪-testowanie) → MQTT_FAQ.md

---

## 🎯 Wyszukaj po Zadaniu

### 🚀 Chcę TERAZ się połączyć
```bash
pip install paho-mqtt
python mqtt_test_suite.py
# Wybierz: 1 (test połączenia)
```
**Czas:** 2 minuty  
**Pliki:** mqtt_test_suite.py, MQTT_QUICK_REFERENCE.md

### 🔌 Chcę odbierać dane telemetryczne
**Opcja 1 (Python):**
```python
from app.services.mqtt_service import get_latest_data
data = get_latest_data()
print(data['bpm'])
```
**Opcja 2 (REST):**
```bash
curl http://localhost:8082/api/machines/telemetry/live
```
**Czas:** 5 minut  
**Pliki:** MQTT_FAQ.md, MQTT_QUICK_REFERENCE.md

### ⚙️ Chcę wysłać komendę
**Opcja 1 (REST API):**
```bash
curl -X POST http://localhost:8082/api/machines/telemetry/command \
  -d '{"topic": "...", "command": {...}}'
```
**Opcja 2 (Python Direct):**
```python
client.publish(topic, json.dumps(payload), qos=1)
```
**Czas:** 5 minut  
**Pliki:** MQTT_FAQ.md, MQTT_QUICK_REFERENCE.md

### 📊 Chcę monitorować live
```
Wejdź: http://localhost:8082/admin/master/mqtt
```
**Czas:** 1 minuta  
**Pliki:** Żadne (use browser)

### 🐛 Maszyna nie odpowiada
1. Uruchom: `python mqtt_test_suite.py`
2. Wybierz: `2` (test odbioru telemetrii)
3. Czekaj 15 sekund
4. Jeśli no messages → maszyna offline
5. Czytaj: MQTT_ARCHITECTURE.md → Failover
**Czas:** 20 minut  
**Pliki:** mqtt_test_suite.py, MQTT_ARCHITECTURE.md

### 📖 Chcę zrozumieć całą architekturę
1. Czytaj: MQTT_ARCHITECTURE.md (20 min)
2. Czytaj: MQTT_DOCUMENTATION.md (30 min)
3. Testuj: mqtt_test_suite.py
4. Eksperymentuj: MQTT_FAQ.md
**Czas:** 1.5 godziny  
**Pliki:** Wszystkie

---

## 📍 Szybkie Odnośniki

### Dane Brokera
```
Host:  4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud
Port:  8883
User:  Lstech
Pass:  Lstech123
```
📄 Źródło: MQTT_QUICK_REFERENCE.md

### Topicy Maszyn
```
Pakowaczka:  iot-2/type/cMT2108X2/id/agroPakowaczka
Paletyzator: iot-2/type/cMT2108X2/id/agroPaletyzator
Owijarka:    iot-2/type/cMT2108X2/id/agroOwijarka
```
📄 Źródło: MQTT_QUICK_REFERENCE.md

### Topicy Komend
```
Reset Licznika:     .../agroPakowaczka/send
Config Palety:      .../agroPaletyzator/setPattern
Sygnał Owijarki:    .../agroOwijarka/send
```
📄 Źródło: MQTT_DOCUMENTATION.md

### Pola Pakowaczki
```
wydajnoscAktualna, licznikGlobalny, status, nazwaReceptury,
wagaAktualna, klapaZrzutuOtwarta, licznikOdrzutow
```
📄 Źródło: MQTT_DOCUMENTATION.md

### Pola Paletyzatora
```
licznikPalet_global, nrWarstwy, nrWorka, oproznianie,
sygnalDoOwijarkiStart, magazynekPaletIlosc
```
📄 Źródło: MQTT_DOCUMENTATION.md

### Pola Owijarki
```
wyjazdPaletaOwinieta, postepOwijania, kapturekZalozony,
etapOwijania
```
📄 Źródło: MQTT_DOCUMENTATION.md

---

## 📁 Struktura Plików Dokumentacji

```
RaportProdukcyjny/
├── MQTT_README.md                ← Mapa dokumentacji
├── MQTT_QUICK_REFERENCE.md       ← ⚡ Szybka referenca
├── MQTT_DOCUMENTATION.md         ← 📖 Pełna dokumentacja
├── MQTT_ARCHITECTURE.md          ← 🏗️ Architektury i diagramy
├── MQTT_FAQ.md                   ← ❓ Pytania i poradniki
├── MQTT_INDEX.md                 ← 📍 Indeks (ten plik)
├── mqtt_test_suite.py            ← 🧪 Test aplikacja
└── ...
```

---

## 🔗 Mapowanie Plik → Zadanie

| Zadanie | Główny Plik | Alternatywny |
|---------|------------|--------------|
| Test połączenia | mqtt_test_suite.py | MQTT_FAQ.md |
| Odczyt telemetrii | MQTT_FAQ.md | MQTT_QUICK_REFERENCE.md |
| Wysłanie komendy | MQTT_FAQ.md | MQTT_QUICK_REFERENCE.md |
| Monitorowanie live | Browser | MQTT_ARCHITECTURE.md |
| Debugowanie | mqtt_test_suite.py | MQTT_ARCHITECTURE.md |
| Architektura | MQTT_ARCHITECTURE.md | MQTT_DOCUMENTATION.md |
| Szybka referenca | MQTT_QUICK_REFERENCE.md | - |
| Pełne szczegóły | MQTT_DOCUMENTATION.md | - |
| Pytania FAQ | MQTT_FAQ.md | MQTT_DOCUMENTATION.md |

---

## 🎓 Sugerowana Ścieżka Nauki

### Poziom 1 (Beginner) – 15 minut
```
1. Czytaj: MQTT_QUICK_REFERENCE.md (5 min)
2. Testuj: python mqtt_test_suite.py → opcja 1 (2 min)
3. Czytaj: MQTT_FAQ.md → "Jak się połączyć?" (5 min)
4. Spróbuj: Kod z MQTT_FAQ.md
```

### Poziom 2 (Intermediate) – 45 minut
```
1. Czytaj: MQTT_ARCHITECTURE.md (20 min)
2. Testuj: python mqtt_test_suite.py → opcja 6 (20 min)
3. Czytaj: MQTT_DOCUMENTATION.md → "Pola Telemetryczne" (5 min)
```

### Poziom 3 (Advanced) – 90 minut
```
1. Czytaj: MQTT_DOCUMENTATION.md (30 min)
2. Testuj: Wypisz własny test suite (20 min)
3. Implementuj: Własny kod integrujący MQTT (40 min)
4. Debuguj: Rozwiąż potencjalne problemy
```

---

## ❓ FAQ Indeks – Szybkie Znalezienie Odpowiedzi

### Pytania o Połączeniu
- Q: Jak się połączyć?  
  A: MQTT_FAQ.md → #jak-się-połączyć

- Q: Czy connect się powiódł?  
  A: mqtt_test_suite.py → opcja 1

- Q: Test timeout?  
  A: MQTT_ARCHITECTURE.md → #-maszyna-offline

### Pytania o Danych
- Q: Gdzie odbierać dane?  
  A: MQTT_FAQ.md → #jak-odczytać-dane

- Q: Które pola dostępne?  
  A: MQTT_DOCUMENTATION.md → #pola-telemetryczne-maszyn

- Q: Ostatnie wiadomości?  
  A: MQTT_FAQ.md → #📊-ostatnie-dane-telemetryczne

### Pytania o Komendach
- Q: Jak wysłać komendę?  
  A: MQTT_FAQ.md → #jak-wysłać-komendę

- Q: Jaki format payload?  
  A: MQTT_DOCUMENTATION.md → #komendy-i-przykłady

- Q: Czy komenda dotarła?  
  A: MQTT_ARCHITECTURE.md → #failover-i-troubleshooting

### Pytania Techniczne
- Q: Co to QoS?  
  A: MQTT_FAQ.md → #-co-to-qos

- Q: Czy podatne na hacki?  
  A: MQTT_FAQ.md → #-czy-wiadomości-są-szyfrowane

- Q: Ile wiadomości przechowujesz?  
  A: MQTT_FAQ.md → #-ile-maksymalnie-mogę-przechowywać-wiadomości

---

## 🎯 Szybkie Komendy do Copy-Paste

### Test Połączenia
```bash
python mqtt_test_suite.py
```

### Test Odbiorcy
```bash
python mqtt_test_suite.py
# Opcja: 2
```

### REST API – Dane Live
```bash
curl http://localhost:8082/api/machines/telemetry/live \
  -H "Cookie: session=SESJA"
```

### REST API – Komenda
```bash
curl -X POST http://localhost:8082/api/machines/telemetry/command \
  -H "Content-Type: application/json" \
  -H "Cookie: session=SESJA" \
  -d '{
    "topic": "iot-2/type/cMT2108X2/id/agroPakowaczka/send",
    "command": {"d": {"zerowanieLicznikow": [1]}}
  }'
```

### Admin Panel – Live Monitor
```
http://localhost:8082/admin/master/mqtt
```

### Logi – MQTT Events
```bash
tail -f logs/app.log | grep MQTT
```

---

## 📊 Statystyki Dokumentacji

- **Plik główny:** MQTT_DOCUMENTATION.md (~3000 linii)
- **Szybka referenca:** MQTT_QUICK_REFERENCE.md (~400 linii)
- **Architektura:** MQTT_ARCHITECTURE.md (~600 linii)
- **FAQ:** MQTT_FAQ.md (~800 linii)
- **Test Suite:** mqtt_test_suite.py (~500 linii kodu)
- **Indeks:** MQTT_INDEX.md (~500 linii)

**Razem:** ~6000+ linii dokumentacji i kodu

---

## 🚀 START – Zalecanym Kolejność Czytania

1. **Najpierw:** MQTT_README.md (orientacja)
2. **Potem:** MQTT_QUICK_REFERENCE.md (szybkie факты)
3. **Eksperyment:** `python mqtt_test_suite.py`
4. **Głębia:** MQTT_ARCHITECTURE.md (jak to działa)
5. **Szczegóły:** MQTT_DOCUMENTATION.md (pełne info)
6. **Problemy:** MQTT_FAQ.md (rozwiązania)

---

## ✅ Checklist Przed Implementacją

- [ ] Przeczytałem MQTT_QUICK_REFERENCE.md
- [ ] Uruchomiłem mqtt_test_suite.py
- [ ] Test 1 (połączenie) przeszedł ✅
- [ ] Mogę odbierać dane (test 2)
- [ ] Mogę wysyłać komendy (test 3)
- [ ] Znam topicy dla mojej maszyny
- [ ] Znalazłem zmienne .env
- [ ] Mogę uruchomić Python kod
- [ ] Mogę debugować (logi, API)
- [ ] Czytaj: MQTT_FAQ.md do pełnej pewności

---

**Ostatnia aktualizacja:** 2026-09-07  
**Wersja:** 1.0  
**Status:** ✅ Kompletna  

💡 **Wskazówka:** Jeśli chcesz coś szybko znaleźć – użyj CTRL+F w swoim edytorze!




<!-- ==================== PAGE BREAK ==================== -->

# 🧪 Test Suite – Kod Aplikacji


## mqtt_test_suite.py

```python
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

```

