@echo off
echo ==========================================
echo   Biblioteka - Uruchomienie Aplikacji
echo ==========================================
echo.

REM Check if virtual environment exists
if not exist ".venv" (
    echo [ERROR] Wirtualne srodowisko nie istnieje!
    echo.
    echo Najpierw uruchom: setup.bat
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
echo [INFO] Aktywacja srodowiska...
call .venv\Scripts\activate.bat

REM Check if Flask is installed
python -c "import flask" 2>nul
if errorlevel 1 (
    echo [ERROR] Flask nie jest zainstalowany!
    echo.
    echo Uruchom: setup.bat
    echo.
    pause
    exit /b 1
)

echo [OK] Srodowisko gotowe
echo.

REM Run the application
echo ==========================================
echo   Uruchamianie serwera...
echo ==========================================
echo.
echo Aplikacja bedzie dostepna pod adresem:
echo.
echo    http://localhost:5000
echo.
echo Aby zatrzymac serwer, nacisnij Ctrl+C
echo.
echo ==========================================
echo.

python app.py

pause
