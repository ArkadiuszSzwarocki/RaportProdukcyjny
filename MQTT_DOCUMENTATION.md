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
