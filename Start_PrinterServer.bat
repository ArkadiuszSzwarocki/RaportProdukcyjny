@echo off
title Printer Server (ZPL + PDF)
color 0A
echo ================================================================
echo   PRINTER SERVER - Most do Drukarek
echo   Port: 3001 (HTTP/HTTPS)
echo ================================================================
echo.
echo Obsluguje:
echo   - Etykiety ZPL (Zebra) - /drukuj-zpl
echo   - Raporty PDF (Biuro)  - /drukuj-pdf
echo.
echo ================================================================
cd /d "%~dp0"

REM Aktywuj srodowisko wirtualne jesli istnieje
IF EXIST ".venv\Scripts\activate.bat" (
    echo [INFO] Aktywacja srodowiska wirtualnego...
    call .venv\Scripts\activate.bat
) ELSE (
    echo [WARN] Brak .venv - uzywam systemowego Python
)

echo.
echo [START] Uruchamiam Printer Server...
echo.

REM Sprawdz czy port 3001 jest wolny (szukamy tylko LISTENING, ignorujemy TIME_WAIT)
netstat -ano | findstr ":3001" | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [WARN] Port 3001 jest zajety! Mozliwe ze serwer juz dziala.
    echo.
    pause
    exit /b 1
)

REM Uruchom printer server
python printer_server\server.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Blad uruchamiania serwera!
    echo.
    echo Sprawdz:
    echo   1. Czy zainstalowane sa zaleznosci: pip install -r printer_server\requirements.txt
    echo   2. Czy biblioteki Windows sa zainstalowane: pip install pywin32 PyMuPDF Pillow
    echo.
)

pause
