# MQTT Process Flow - Paletyzacja End-to-End

Dokument opisuje rzeczywisty przeplyw procesu od wjazdu worka do owiniecia palety na podstawie aktualnej logiki aplikacji.

## Zakres i zrodla

- Logika odbioru i parsowania MQTT: app/services/mqtt_service.py
- Agregacja pod dashboard/API: app/services/machine_telemetry_service.py
- Wysylanie komend: app/blueprints/api/machine_telemetry.py, app/blueprints/production/orders.py
- Podglad operatorski: app/blueprints/admin/diagnostics.py

## 1) Pelna mapa topicow (uzywanych w tej logice)

### Telemetria (subskrypcja)

1. iot-2/type/cMT2108X2/id/agroPakowaczka
2. iot-2/type/cMT2108X2/id/agroPaletyzator
3. iot-2/type/cMT2108X2/id/agroOwijarka

Uwaga:
- Subskrypcja w runtime jest konfigurowalna przez MQTT_SUBSCRIBE_TOPICS.
- Domyslnie aplikacja subskrybuje # (wszystkie topiki).

### Komendy (publikacja)

1. iot-2/type/cMT2108X2/id/agroPakowaczka/send
2. iot-2/type/cMT2108X2/id/agroPaletyzator/setPattern

### Dodatkowy topic zdarzeniowy (poza samym flow paletyzacji)

1. agro/dosypka/<linia>

## 2) Proces krok po kroku: od worka do owiniecia

Ponizej sekwencja jest opisana tylko przez sygnaly, ktore realnie sa widoczne lub obslugiwane w kodzie.

### Krok 0 - Warunek startowy i heartbeat

Telemetria musi naplywac regularnie; brak danych > 30 s powoduje status OFFLINE.

- Zrodlo: time_since_update i HEARTBEAT_TIMEOUT_SECONDS = 30
- Skutek: UI/API uznaje maszyny za offline

---

### Krok 1 - Worek wchodzi na wage dynamiczna (Pakowaczka)

Topic:
- iot-2/type/cMT2108X2/id/agroPakowaczka

Kluczowe pola:
- wydajnoscAktualna
- status
- wagaAktualna / wagaWorka / wagaOstatniegoWorka / waga
- wagaZadana / wagaNominalna
- klapaZrzutuOtwarta / zrzutAktywny / odrzutPraca / zrzutOdrzut
- licznikOdrzutow / licznikZrzutow / rejectCount

Interpretacja:
1. Waga porownywana jest do celu.
2. Jesli klapa odrzutu aktywna, worek wypada poza proces paletyzacji.
3. Odrzut moze byc logowany przez MachineRejectLogService.

---

### Krok 2 - Worek OK jedzie do obracaka (Paletyzator)

Topic:
- iot-2/type/cMT2108X2/id/agroPaletyzator

Kluczowe pola:
- obracakPraca / obracakAktywny
- obrotWorka / katObrotu / orientacja / obracak
- nrWorka

Interpretacja:
1. obracakPraca=true oznacza cykl obrotu worka.
2. Po zakonczeniu obracaka sygnal wraca do false i worek idzie dalej.

---

### Krok 3 - Przepychacz uklada worek na plycie/warstwie

Topic:
- iot-2/type/cMT2108X2/id/agroPaletyzator

Kluczowe pola:
- popychaczPraca / popychaczAktywny
- nrWorka
- nrWarstwy

Interpretacja:
1. popychaczPraca=true - przepychacz aktywny.
2. Po odlozeniu worka nrWorka postepuje.
3. Po zamknieciu warstwy nrWarstwy przechodzi na kolejna.

---

### Krok 4 - Podawanie palety i stan magazynku palet

Topic:
- iot-2/type/cMT2108X2/id/agroPaletyzator

Kluczowe pola:
- magazynekPaletIlosc / magazynekIloscPalet / liczbaPaletMagazynek
- podawaniePalety / podajnikPaletPraca / podawaniePaletyAktywne

Interpretacja:
1. Ilosc palet steruje gotowoscia stanowiska.
2. Podawanie palety moze byc w trakcie niezaleznie od pracy worka.

---

### Krok 5 - Kompletowanie palety i sygnal opróżniania

Topic:
- iot-2/type/cMT2108X2/id/agroPaletyzator

Kluczowe pola:
- nrWarstwy
- nrWorka
- licznikPalet_global
- oproznianie

Interpretacja:
1. Narastanie nrWarstwy/nrWorka opisuje postep przepisu palety.
2. Gdy oproznianie=true, paleta jest wypychana z paletyzatora.
3. W aplikacji tworzony jest snapshot momentu wejscia w oproznianie.

---

### Krok 6 - Trigger owijarki z paletyzatora

Topic:
- iot-2/type/cMT2108X2/id/agroPaletyzator

Kluczowe pole:
- sygnalDoOwijarkiStart

Interpretacja:
1. sygnalDoOwijarkiStart=true oznacza przekazanie palety do sekcji owijania.

---

### Krok 7 - Owijarka: start, postep, faza, top-sheet

Topic:
- iot-2/type/cMT2108X2/id/agroOwijarka

Kluczowe pola:
- postepOwijania / progress
- etapOwijania / phase
- kapturekZalozony / top_sheet
- obrotyStolu / rotations

Interpretacja:
1. postep 0-100 prowadzi przez fazy (BOTTOM_WRAP, ASCENDING, TOP_SHEET, TOP_WRAP, DESCENDING, DONE).
2. kapturekZalozony sygnalizuje etap top-sheet.
3. obrotyStolu daje licznik obrotow stolu.

---

### Krok 8 - Koniec owijania i sygnal wyjazdu palety

Topic:
- iot-2/type/cMT2108X2/id/agroOwijarka

Kluczowe pole:
- wyjazdPaletaOwinieta

Interpretacja:
1. wyjazdPaletaOwinieta=true traktowane jest jako gotowosc palety do odbioru.
2. W dashboardzie powoduje stan gotowej palety.

---

### Krok 9 - Bufor odbiorczy (rolki)

Topic:
- iot-2/type/cMT2108X2/id/agroPaletyzator

Kluczowe pola:
- rolki1zajete (u Ciebie: [true]/[false])
- rolki2zajete (u Ciebie: [true]/[false])
- buforPelny

Interpretacja:
1. Zajetosc rolek jest normalizowana do bool.
2. UI stacji odbioru pokazuje zajetosc rolek i stan pelnego bufora.
3. To jest faktyczny sygnal pozycji palety po owijarce.

## 3) Komendy i ich miejsce w procesie

### A) Reset licznikow pakowaczki

Topic:
- iot-2/type/cMT2108X2/id/agroPakowaczka/send

Payload (uzywany):
```json
{
  "d": { "zerowanieLicznikow": [1] },
  "ts": "2026-09-07T12:00:00"
}
```

Kiedy:
1. Po zakonczeniu zlecenia AGRO (Workowanie/Czyszczenie).

### B) Wgranie receptury ukladu palety

Topic:
- iot-2/type/cMT2108X2/id/agroPaletyzator/setPattern

Payload (aktualny format):
```json
{
  "d": {
    "receptura": "STANDARD_100x120",
    "typPalety": "INDUSTRIAL_100x120",
    "nazwaPalety": "Paleta Przemyslowa (1000 x 1200 mm)",
    "szerokoscM": 1.0,
    "dlugoscM": 1.2,
    "warstwyPelne": 12,
    "warstwyLacznie": 13,
    "workiNaWarstwe": 4,
    "workiSzczyt": 2,
    "lacznieWorkow": 50,
    "masaWorkaKg": 25.0
  },
  "ts": "2026-09-07T12:00:00"
}
```

Kiedy:
1. Po zmianie konfiguracji paletyzatora w API.

## 4) Co jeszcze jest wazne poza topicami

1. QoS komend: publikacja komend dziala z QoS=1.
2. Przychodzace wartosci [true]/[false]: parser bierze pierwszy element listy i mapuje na bool.
3. topics_seen: aplikacja zapamietuje wszystkie faktycznie zaobserwowane topiki.
4. recent_messages: trzymane jest ostatnie okno wiadomosci MQTT.
5. Bledy i alarmy: payloady sa dodatkowo analizowane i logowane do serwisu bledow.

## 5) Czego ten flow nadal nie ma (realne luki sygnalowe)

To sa luki diagnostyczne, ale nie blokuja podstawowego flow topicow:

1. Bezposredni sygnal pozycji windy paletyzatora (gora/dol).
2. Bezposredni sygnal pozycji windy owijarki (gora/dol).
3. Bezposredni sygnal jakosci zgrzewu (poza inferencja z fazy).

## 6) Minimalna checklista poprawnosci procesu

1. Pakowaczka publikuje wage/status i licznik odrzutow.
2. Paletyzator publikuje nrWarstwy i nrWorka.
3. Paletyzator publikuje sygnalDoOwijarkiStart przy transferze.
4. Owijarka publikuje postep/faze i finalnie wyjazdPaletaOwinieta=true.
5. Paletyzator publikuje rolki1zajete/rolki2zajete/buforPelny.

Jesli wszystkie 5 punktow dziala, proces od worka do owiniecia i odbioru jest widoczny end-to-end w MQTT.

---

Dokument: MQTT_PROCESS_FLOW.md
Wersja: 2.0
Data: 2026-09-07