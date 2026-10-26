# Lokalna aplikacja z bazą testową na QNAP

Uruchom `Start_Lokalne_Testy.bat` lub `python scripts/run_local_test.py`.
Aplikacja działa wyłącznie na komputerze pod `http://127.0.0.1:8082`.
Parametry połączenia SQL (host, port i dane konta) pobiera z istniejącego `.env`, a początkowo wybiera `biblioteka_testowa`. Masteradmin może zmienić bazę na stronie **Baza danych**.

Przy pierwszym uruchomieniu powstaje ignorowany przez Git plik `.env.local-test` z osobnym kluczem sesji.
Pozostałe ustawienia lokalne opisano w `local-test.env.example`.
Nie trzeba zmieniać `.env` aplikacji produkcyjnej ani uruchamiać kontenera na QNAP.

Przed startem wykonywany jest wyłącznie odczyt `SELECT DATABASE()` w transakcji READ ONLY.
Samo sprawdzenie połączenia można uruchomić poleceniem:

```sh
python scripts/run_local_test.py --check-only
```

Na stronach aplikacji widnieje pasek **LOKALNA KOPIA — aktywna baza**.
Dane i logowanie pochodzą z tej bazy; sesja przeglądarki ma osobną nazwę.
Wysyłanie e-maili, fizyczny druk, komendy do maszyn i zadania w tle są aktywne. Automatyczne migracje schematu przy starcie i przełączaniu baz pozostają wyłączone.
Nie jest odczytywany ani nadpisywany zapamiętany wybór z `.active_db_name`.
Awaria połączenia z QNAP nie powoduje połączenia z innym, lokalnym serwerem MySQL.

Działania wykonywane ręcznie zapisują dane w aktualnie wybranej bazie na QNAP. Wybranie `biblioteka` oznacza pracę na danych produkcyjnych.

Po przełączeniu trzeba zalogować się kontem istniejącym w wybranej bazie. Przełącznik nie kopiuje kont, haseł ani uprawnień i nie wykonuje migracji. Wybór zapamiętuje lokalny, ignorowany przez Git plik `.active_db_name.local`. Aplikacja na QNAP nadal korzysta ze swojej konfiguracji.
Zatrzymanie lokalnego serwera nie wpływa na aplikację produkcyjną.
