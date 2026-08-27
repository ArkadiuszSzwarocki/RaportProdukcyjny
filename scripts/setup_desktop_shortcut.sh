#!/bin/bash
# ==============================================================================
# SCRIPT: setup_desktop_shortcut.sh
# OPIS: Tworzy skrót do procedury podmiany bazy na Pulpicie Ubuntu
# PROJEKT: Raport Produkcyjny
# ==============================================================================

set -e

SCRIPT_SRC="$(dirname "$(readlink -f "$0")")/podmien_baze.sh"

# Wykrycie katalogu Pulpitu (Pulpit dla PL, Desktop dla EN)
if [ -d "${HOME}/Pulpit" ]; then
    DESKTOP_DIR="${HOME}/Pulpit"
elif [ -d "${HOME}/Desktop" ]; then
    DESKTOP_DIR="${HOME}/Desktop"
else
    DESKTOP_DIR="${HOME}/Pulpit"
    mkdir -p "$DESKTOP_DIR"
fi

TARGET_LINK="${DESKTOP_DIR}/Podmien_Baze.sh"

# Kopiowanie i zmiana praw
cp "$SCRIPT_SRC" "$TARGET_LINK"
chmod +x "$TARGET_LINK"
chmod +x "$SCRIPT_SRC"

echo "======================================================================"
echo " ✅ SKRÓT ZOSTAŁ POMYŚLNIE STWORZONY NA PULPICIE UBUNTU!"
echo " Ścieżka pliku: ${TARGET_LINK}"
echo "======================================================================"
echo ""
echo "Aby uruchomić skrypt z Pulpitu:"
echo " 1. Otwórz terminal na Pulpicie i wpisz: ./Podmien_Baze.sh"
echo " LUB"
echo " 2. Kliknij prawym na plik na Pulpicie -> 'Zezwól na uruchomienie' -> Uruchom."
echo ""
