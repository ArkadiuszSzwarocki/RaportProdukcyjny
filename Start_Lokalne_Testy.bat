@echo off
cd /d "%~dp0"
title Lokalne testy - biblioteka_testowa
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\run_local_test.py
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        python scripts\run_local_test.py
    ) else (
        py -3 scripts\run_local_test.py
    )
)
pause
