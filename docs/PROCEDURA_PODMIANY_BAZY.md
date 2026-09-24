# PROCEDURA PODMIANY BAZY DANYCH (ŚRODOWISKO DOCKER)

* **Projekt:** Raport Produkcyjny
* **Środowisko:** Serwer Ubuntu (Localhost)
* **Wygodny skrypt automatyczny:** `./scripts/podmien_baze.sh [plik_bazy.sql]` lub `python scripts/podmien_baze.py`

---

## KROK 1: Przygotowanie pliku
Upewnij się, że nowy zrzut bazy z QNAP-a (np. `nowa_baza.sql`) znajduje się w Twoim głównym katalogu projektu na Ubuntu:
```bash
~/raportprodukcyjny
```

---

## KROK 2: Czyszczenie starego środowiska
Otwórz terminal w katalogu projektu i zatrzymaj wszystkie kontenery, jednocześnie usuwając stary wolumen z danymi bazy:
```bash
sudo docker-compose down -v
```

---

## KROK 3: Uruchomienie czystej bazy danych
Podnieś sam kontener bazy danych MySQL:
```bash
sudo docker-compose up -d db
```
> ⚠️ **Ważne:** Odczekaj około 15-20 sekund po wykonaniu tego polecenia, aby serwer MySQL zdążył w pełni wystartować i zainicjować pliki.

---

## KROK 4: Import nowych danych
Sprawdź gotowość bazy wskazanej przez `MYSQL_DATABASE`, a następnie wgraj do niej nowy plik SQL:

```bash
sudo docker-compose exec -T db sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysqladmin -u root ping'
```

```bash
sudo docker-compose exec -T db sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysql -u root "$MYSQL_DATABASE"' < nowa_baza.sql
```
> 💡 **Uwaga:** Upewnij się, że nazwa pliku na końcu drugiego polecenia zgadza się z nazwą Twojego pliku SQL.

---

## KROK 5: Uruchomienie aplikacji
Gdy import zakończy się bez błędów, uruchom kontener z aplikacją:
```bash
sudo docker-compose up -d app
```

---

## KROK 6: Weryfikacja
1. Wejdź do przeglądarki pod adres:
   👉 **[https://localhost:5005](https://localhost:5005)**
2. Zaloguj się i sprawdź, czy nowe dane są widoczne. Procedura zakończona!
