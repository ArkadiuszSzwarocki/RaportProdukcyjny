@echo off
echo ==========================================
echo   Biblioteka - Setup Script
echo   System Zarzadzania Produkcja
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python nie jest zainstalowany!
    echo Pobierz Python z: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Python jest zainstalowany
echo.

REM Check if virtual environment exists
if exist ".venv" (
    echo [INFO] Wirtualne srodowisko juz istnieje
) else (
    echo [INFO] Tworzenie wirtualnego srodowiska...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Nie udalo sie utworzyc wirtualnego srodowiska!
        pause
        exit /b 1
    )
    echo [OK] Wirtualne srodowisko utworzone
)
echo.

REM Activate virtual environment
echo [INFO] Aktywacja wirtualnego srodowiska...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Nie udalo sie aktywowac wirtualnego srodowiska!
    pause
    exit /b 1
)
echo [OK] Wirtualne srodowisko aktywne
echo.

REM Install dependencies
echo [INFO] Instalacja zaleznosci z requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Nie udalo sie zainstalowac zaleznosci!
    pause
    exit /b 1
)
echo [OK] Wszystkie zaleznosci zainstalowane
echo.

echo ==========================================
echo   Instalacja zakonczona pomyslnie!
echo ==========================================
echo.
echo Aby uruchomic aplikacje:
echo   1. Aktywuj srodowisko: .venv\Scripts\activate
echo   2. Uruchom: python app.py
echo   3. Otworz przegladarke: http://localhost:5000
echo.
echo UWAGA: Przed uruchomieniem skonfiguruj baze danych w app.py (linie 11-18)
echo.
pause
