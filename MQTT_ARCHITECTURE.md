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
