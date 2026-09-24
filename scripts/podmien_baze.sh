#!/bin/bash
# ==============================================================================
# SCRIPT: podmien_baze.sh
# OPIS: Automatyczna procedura podmiany bazy danych MySQL w środowisku Docker
# PROJEKT: Raport Produkcyjny
# ŚRODOWISKO: Serwer Ubuntu (Localhost)
# ==============================================================================

set -e

# Kolory do komunikatów
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Zmienne domyślne
PROJECT_DIR="${HOME}/raportprodukcyjny"
SQL_FILE="${1:-nowa_baza.sql}"

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}    PROCEDURA PODMIANY BAZY DANYCH (ŚRODOWISKO DOCKER)               ${NC}"
echo -e "${BLUE}    Projekt: Raport Produkcyjny | Serwer Ubuntu (Localhost)          ${NC}"
echo -e "${BLUE}======================================================================${NC}\n"

# Przejście do katalogu projektu
if [ -d "$PROJECT_DIR" ]; then
    cd "$PROJECT_DIR"
    echo -e "${GREEN}[OK] Przejście do katalogu projektu: ${PROJECT_DIR}${NC}"
else
    echo -e "${YELLOW}[INFO] Katalog ${PROJECT_DIR} nie istnieje. Praca w bieżącym katalogu: $(pwd)${NC}"
fi

# KROK 1: Przygotowanie pliku
echo -e "\n${YELLOW}--- KROK 1: Przygotowanie pliku ---${NC}"
if [ ! -f "$SQL_FILE" ]; then
    echo -e "${RED}[BŁĄD] Plik '$SQL_FILE' nie został znaleziony!${NC}"
    echo -e "Upewnij się, że nowy zrzut bazy z QNAP-a (np. nowa_baza.sql) znajduje się w katalogu projektu."
    echo -e "Dostępne pliki .sql w bieżącym katalogu:"
    ls -lh *.sql 2>/dev/null || echo "Brak plików .sql."
    echo -e "\nUżycie: ./scripts/podmien_baze.sh [nazwa_pliku.sql]"
    exit 1
fi

echo -e "${GREEN}[OK] Znaleziono plik bazy danych: ${SQL_FILE} ($(du -h "$SQL_FILE" | cut -f1))${NC}"

# Potwierdzenie od użytkownika
read -p "Czy na pewno chcesz usunąć stary wolumen bazy i wgrać '${SQL_FILE}'? (t/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Tt]$ ]]; then
    echo -e "${YELLOW}Anulowano procedurę podmiany bazy.${NC}"
    exit 0
fi

# KROK 2: Czyszczenie starego środowiska
echo -e "\n${YELLOW}--- KROK 2: Czyszczenie starego środowiska ---${NC}"
echo -e "Zatrzymywanie kontenerów i usuwanie starego wolumenu bazy..."
sudo docker-compose down -v
echo -e "${GREEN}[OK] Wolumeny i kontenery zostały pomyślnie usunięte.${NC}"

# KROK 3: Uruchomienie czystej bazy danych
echo -e "\n${YELLOW}--- KROK 3: Uruchomienie czystej bazy danych ---${NC}"
echo -e "Podnoszenie kontenera bazy danych..."
sudo docker-compose up -d db

echo -e "Oczekiwanie około 15-20 sekund na pełne uruchomienie i inicjalizację MySQL..."
for i in {20..1}; do
    echo -ne "Inicjalizacja MySQL... pozostało ${i}s \r"
    sleep 1
done
echo -e "\n${GREEN}[OK] Kontener db gotowy.${NC}"

# KROK 4: Import nowych danych
echo -e "\n${YELLOW}--- KROK 4: Import nowych danych ---${NC}"
echo -e "Weryfikacja bazy skonfigurowanej jako MYSQL_DATABASE..."
sudo docker-compose exec -T db sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysqladmin -u root ping'

echo -e "Wgrywanie pliku ${SQL_FILE} do skonfigurowanej bazy..."
sudo docker-compose exec -T db sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysql -u root "$MYSQL_DATABASE"' < "$SQL_FILE"
echo -e "${GREEN}[OK] Import zakończył się bez błędów!${NC}"

# KROK 5: Uruchomienie aplikacji
echo -e "\n${YELLOW}--- KROK 5: Uruchomienie aplikacji ---${NC}"
echo -e "Uruchamianie kontenera z aplikacją..."
sudo docker-compose up -d app
echo -e "${GREEN}[OK] Kontener app został uruchomiony.${NC}"

# KROK 6: Weryfikacja
echo -e "\n${BLUE}======================================================================${NC}"
echo -e "${GREEN}    PROCEDURA PODMIANY BAZY DANYCH ZAKOŃCZONA SUKCESEM!              ${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo -e "KROK 6: Weryfikacja"
echo -e "Wejdź do przeglądarki pod adres: ${GREEN}https://localhost:5005${NC}"
echo -e "Zaloguj się i sprawdź, czy nowe dane są widoczne. Procedura zakończona!\n"
