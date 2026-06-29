@echo off
title Serwer RaportProdukcyjny
echo ===================================================
echo Uruchamianie serwera aplikacji RaportProdukcyjny...
echo ===================================================
cd /d "a:\GitHub\RaportProdukcyjny"
call .venv\Scripts\activate.bat
python app.py
pause
