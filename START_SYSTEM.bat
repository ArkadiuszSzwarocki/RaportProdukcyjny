@echo off
title SYSTEM PRODUKCYJNY - AGRONETZWERK
color 0A
echo.
echo ========================================================
echo    URUCHAMIANIE SYSTEMU PRODUKCYJNEGO (WAITRESS)
echo ========================================================
echo.

echo Zamykanie starych procesow...
taskkill /F /IM python.exe >nul 2>&1

echo.
echo --------------------------------------------------------
echo 💾 TWORZENIE KOPII ZAPASOWEJ RAPORTOW...
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe backup.py
) else (
    python backup.py
)
echo --------------------------------------------------------
echo.

echo Startowanie serwera...
echo Nie zamykaj tego okna, zminimalizuj je.
echo.

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe app.py
) else (
    python app.py
)

pause