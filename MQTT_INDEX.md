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
