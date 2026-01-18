@echo off
REM Plik uruchamiający skrypt rollover (uruchamiać codziennie o 06:00)
SETLOCAL

REM Zmień poniższe ścieżki jeśli Twoje środowisko jest w innym miejscu
set PYTHON=C:\Users\arkad\Documents\GitHub\RaportProdukcyjny\.venv\Scripts\python.exe
set PROJECT_DIR=C:\Users\arkad\Documents\GitHub\RaportProdukcyjny
set SCRIPT=%PROJECT_DIR%\scripts\rollover.py
set LOG_DIR=%PROJECT_DIR%\logs









exit /b %ERRORLEVEL%ENDLOCALecho [%DATE% %TIME%] Zakonczono (kod=%ERRORLEVEL%) >> "%LOG_DIR%\rollover.log"%PYTHON% %SCRIPT% >> "%LOG_DIR%\rollover.log" 2>&1echo [%DATE% %TIME%] Uruchomiono rollover >> "%LOG_DIR%\rollover.log"cd /d "%PROJECT_DIR%"IF NOT EXIST "%LOG_DIR%" mkdir "%LOG_DIR%"n