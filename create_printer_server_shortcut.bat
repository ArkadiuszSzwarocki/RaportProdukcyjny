@echo off
REM ================================================================
REM Skrypt do tworzenia skrotu dla Printer Server na Pulpicie
REM ================================================================

setlocal

set "SCRIPT_DIR=%~dp0"
set "BAT_FILE=%SCRIPT_DIR%Start_PrinterServer.bat"
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT_NAME=Printer Server.lnk"
set "SHORTCUT_PATH=%DESKTOP%\%SHORTCUT_NAME%"
set "ICON_PATH=%SystemRoot%\System32\printui.exe"

echo ================================================================
echo   Tworzenie skrotu Printer Server na Pulpicie
echo ================================================================
echo.
echo Lokalizacja skryptu: %BAT_FILE%
echo Pulpit: %DESKTOP%
echo.

REM Sprawdz czy plik .bat istnieje
if not exist "%BAT_FILE%" (
    echo [ERROR] Nie znaleziono pliku Start_PrinterServer.bat!
    echo Upewnij sie ze ten skrypt jest w glownym folderze projektu.
    pause
    exit /b 1
)

REM Utwórz skrót używając PowerShell
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%BAT_FILE%'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.IconLocation = '%ICON_PATH%,0'; $s.Description = 'Uruchamia Printer Server (port 3001) - obsluga ZPL i PDF'; $s.Save()"

if %errorlevel% equ 0 (
    echo.
    echo [OK] Skrot utworzony pomyslnie!
    echo      Lokalizacja: %SHORTCUT_PATH%
    echo.
    echo Mozesz teraz uruchomic Printer Server z Pulpitu.
) else (
    echo.
    echo [ERROR] Nie udalo sie utworzyc skrotu!
    echo Sprobuj uruchomic ten skrypt jako Administrator.
)

echo.
pause
