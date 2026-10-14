# Pomiary iPomiar na Zasypie AGRO

Zasyp AGRO wyświetla wszystkie skonfigurowane czujniki: temperaturę,
wilgotność, czas odczytu i ostrzeżenie po 15 minutach bez nowego pomiaru.
Panel odświeża się co minutę, zgodnie z uprawnieniem strony `agro.zasyp`.
Raport dobowy AGRO PDF zawiera minimum, maksimum, średnią i liczebność
odczytów. Excel dodatkowo zawiera wszystkie dostępne odczyty.
Pozostałe linie nie otrzymują sekcji pomiarów.

## Źródło i konfiguracja

Oficjalna dokumentacja:
https://www.oferta.ipomiar.pl/blog/integracja-z-api-serwisu-ipomiar-pl-kompletny-przewodnik

API udostępnia dane urządzeń z włączoną opcją PUBLIKUJ DANE. Włączenie
tej opcji udostępnia nazwę i pomiary przez publiczny adres. Konfiguracja
nie zawiera hasła konta; klucze urządzeń należy trzymać poza repozytorium.

`IPOMIAR_CONFIG_FILE` wskazuje prywatny plik JSON, np.:

```json
{
  "devices": [
    {
      "name": "Hala AGRO",
      "device": "IDENTYFIKATOR-Z-LINKU-API",
      "temperature": "Temperatura wewnętrzna",
      "humidity": "Wilgotność wewnętrzna",
      "timezone": "UTC"
    }
  ]
}
```

Nazwy pól muszą odpowiadać odpowiedzi urządzenia. Różne urządzenia mają
różne nazwy, również zawierające literówki. Pole timezone musi odpowiadać
czasowi źródłowemu: na badanych urządzeniach API podawało UTC, podczas gdy
portal pokazywał czas polski. Archiwum i raporty używają Europe/Warsaw.
Pobieranie uwzględnia poprzedni dzień UTC, żeby nie pomijać początku doby.

`IPOMIAR_ARCHIVE_DIR` wskazuje katalog trwałego archiwum. Domyślnie jest
to ignorowany przez Git katalog `instance/ipomiar`. Zachowaj go przy
wdrożeniu i obejmij kopią zapasową.

## Kolektor

Uruchom osobny proces pod nadzorem systemowym, z tymi samymi zmiennymi:

```
python scripts/sync_ipomiar.py --watch
```

Kolektor co minutę pobiera bieżącą i poprzednią dobę. Endpoint i domena
ipomiar są stałe; przekierowania są odrzucane, czas i rozmiar odpowiedzi
ograniczone. Dane są łączone z archiwum bez duplikatów i zapisywane
w całości przez zastąpienie pliku. Niedostępność źródła nie usuwa ostatnich odczytów.
Żądania aplikacji i generowanie raportu tylko odczytują lokalne archiwum,
więc awaria ipomiar nie blokuje produkcji. Kolektor nie uruchamia MQTT,
drukarek ani innych procesów produkcyjnych.

Starszą dobę można uzupełnić przed wygenerowaniem raportu:

```
python scripts/sync_ipomiar.py --date 2026-10-01
```

Historia sprzed uruchomienia kolektora wymaga takiego importu i dostępnej
historii w ipomiar. Raport nie pobiera dowolnej starszej doby automatycznie.
Brak pomiarów jest opisany jawnie. Raport nigdy nie zastępuje brakującej
doby starszym odczytem, nawet jeśli dashboard pokazuje ostatni znany odczyt.
Średnia jest średnią dostępnych próbek, bez interpolacji i uzupełniania
przerw. Pokazany zakres i liczba odczytów pozwalają ocenić kompletność.

## Test lokalny PR17

W środowisku na A kolektor działa jako osobny proces tylko do odczytu
ipomiar. Izolacja sieci aplikacji i wyłączone procesy produkcyjne są
zachowane. Konfiguracja, archiwum i log kolektora znajdują się na A.
Identyfikator procesu jest w `private/ipomiar-collector.pid`; przy
zatrzymywaniu należy sprawdzić, czy proces nadal uruchamia ten kolektor.
