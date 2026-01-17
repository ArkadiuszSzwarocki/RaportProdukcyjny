@echo off
title SYSTEM PRODUKCJI - AGRONETZWERK
color 0A
echo.
echo ========================================================
echo    URUCHAMIANIE SYSTEMU PRODUKCYJNEGO (WAITRESS)
echo ========================================================
echo.
echo Zamykanie starych procesow...
taskkill /F /IM python.exe >nul 2>&1

echo.
echo Startowanie serwera...
echo Nie zamykaj tego okna, zminimalizuj je.
echo.

:: Tutaj upewniamy się, że używamy pythona z venv, jeśli go masz
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe app.py
) else (
    python app.py
)

pause