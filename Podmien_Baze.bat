@echo off
:: ==============================================================================
:: SKRYPT: Podmien_Baze.bat
:: OPIS: Automatyczna procedura podmiany bazy danych (Środowisko Docker / Windows & Ubuntu)
:: PROJEKT: Raport Produkcyjny
:: ==============================================================================
chcp 65001 > nul
title PROCEDURA PODMIANY BAZY DANYCH - RAPORT PRODUKCYJNY

set "PROJECT_DIR=C:\Users\arkad\Documents\github\RaportProdukcyjny"
set "DB_PASS=VVezyr$$"
set "DB_NAME=biblioteka"
set "SQL_FILE=nowa_baza.sql"

color 0A
echo ======================================================================
echo    PROCEDURA AUTOMATYCZNEJ PODMIANY BAZY DANYCH (DOCKER)
echo    Projekt: Raport Produkcyjny
echo ======================================================================
echo.

if exist "%PROJECT_DIR%" (
    cd /d "%PROJECT_DIR%"
    echo [OK] Przejscie do katalogu projektu: %PROJECT_DIR%
) else (
    echo [INFO] Praca w biezacym katalogu: %CD%
)

:: KROK 1: Przygotowanie pliku
echo.
echo --- KROK 1: Przygotowanie pliku SQL ---
if not exist "%SQL_FILE%" (
    color 0C
    echo [BLAD] Plik '%SQL_FILE%' nie zostal znaleziony w katalogu projektu!
    echo.
    echo Upewnij sie, ze plik zrzutu bazy z QNAP-a (np. nowa_baza.sql)
    echo znajduje sie w katalogu projektu (%CD%).
    echo.
    pause
    exit /b 1
)

echo [OK] Znaleziono plik bazy danych: %SQL_FILE%
echo.
set /p CONFIRM="Czy na pewno chcesz USUNAC obecna baze danych i zaimportowac '%SQL_FILE%'? (T/N): "
if /i not "%CONFIRM%"=="T" (
    color 0E
    echo Anulowano procedure podmiany bazy.
    pause
    exit /b 0
)

:: KROK 2: Czyszczenie starego środowiska
echo.
echo --- KROK 2: Czyszczenie starego srodowiska Docker ---
echo Zatrzymywanie kontenerow i usuwanie starego wolumenu bazy...
docker-compose down -v
if %errorlevel% neq 0 (
    echo [UWAGA] Wykonuje polecenie z docker compose (v2)...
    docker compose down -v
)

:: KROK 3: Uruchomienie czystej bazy danych
echo.
echo --- KROK 3: Uruchomienie czystego kontenera bazy MySQL ---
docker-compose up -d db
if %errorlevel% neq 0 (
    docker compose up -d db
)

echo.
echo Oczekiwanie 20 sekund na pelna inicjalizacje serwera MySQL...
timeout /t 20 /nobreak

:: KROK 4: Import nowych danych
echo.
echo --- KROK 4: Tworzenie bazy '%DB_NAME%' i import danych ---
docker-compose exec -T db mysql -u root -p"%DB_PASS%" -e "CREATE DATABASE IF NOT EXISTS %DB_NAME%;"
if %errorlevel% neq 0 (
    docker compose exec -T db mysql -u root -p"%DB_PASS%" -e "CREATE DATABASE IF NOT EXISTS %DB_NAME%;"
)

echo Wgrywanie pliku %SQL_FILE% do bazy '%DB_NAME%'...
docker-compose exec -T db mysql -u root -p"%DB_PASS%" %DB_NAME% < "%SQL_FILE%"
if %errorlevel% neq 0 (
    docker compose exec -T db mysql -u root -p"%DB_PASS%" %DB_NAME% < "%SQL_FILE%"
)

echo [OK] Dane zostaly pomyslnie zaimportowane!

:: KROK 5: Uruchomienie kontenera z aplikacją
echo.
echo --- KROK 5: Uruchomienie kontenera z aplikacja ---
docker-compose up -d app
if %errorlevel% neq 0 (
    docker compose up -d app
)

:: KROK 6: Weryfikacja
color 0A
echo.
echo ======================================================================
echo    PROCEDURA PODMIANY BAZY DANYCH ZAKONCZONA SUKCESEM! 🎉
echo ======================================================================
echo KROK 6: Weryfikacja
echo 1. Wejdz do przegladarki pod adres: https://localhost:5005
echo 2. Zaloguj sie i sprawdz poprawnosc danych.
echo.
pause
