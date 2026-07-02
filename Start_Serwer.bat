@echo off
title Serwer RaportProdukcyjny
echo ===================================================
echo Uruchamianie serwera aplikacji RaportProdukcyjny...
echo ===================================================
cd /d "%~dp0"
IF EXIST ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)
python app.py
pause
