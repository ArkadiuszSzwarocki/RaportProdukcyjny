@echo off
REM Plik uruchamiający skrypt rollover (uruchamiać codziennie o 06:00)
SETLOCAL

REM --- KONFIGURACJA ŚCIEŻEK (DYNAMICZNA) ---

REM Ustal folder projektu (jeden poziom wyżej niż ten skrypt, bo skrypt jest w folderze 'scripts')
pushd "%~dp0.."
set PROJECT_DIR=%CD%
popd

REM Ustal ścieżki do Pythona i skryptu względem folderu projektu
set PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe
set SCRIPT=%PROJECT_DIR%\scripts\rollover.py
set LOG_DIR=%PROJECT_DIR%\logs

REM --- KONIEC KONFIGURACJI ---

REM Utwórz folder logów jeśli nie istnieje
IF NOT EXIST "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Przejdź do folderu projektu (ważne dla importów w Pythonie)
cd /d "%PROJECT_DIR%"

echo [%DATE% %TIME%] Uruchomiono rollover >> "%LOG_DIR%\rollover.log"

REM Uruchom skrypt
"%PYTHON%" "%SCRIPT%" >> "%LOG_DIR%\rollover.log" 2>&1

echo [%DATE% %TIME%] Zakonczono (kod=%ERRORLEVEL%) >> "%LOG_DIR%\rollover.log"

ENDLOCAL
exit /b %ERRORLEVEL%