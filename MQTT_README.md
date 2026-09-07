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
