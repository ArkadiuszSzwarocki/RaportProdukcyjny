# Skrypt do szybkiego otwierania widoku zbiorników produkcyjnych
# Użycie: .\tools\open_zbiorniki.ps1

$baseUrl = "http://localhost:5000"

Write-Host "🏭 ZBIORNIKI PRODUKCYJNE BB, MZ, KO" -ForegroundColor Cyan
Write-Host ""
Write-Host "Wybierz widok:" -ForegroundColor Yellow
Write-Host "  [1] Surowce w Produkcji (karty zbiorników) ✅ POLECAM" -ForegroundColor Green
Write-Host "  [2] Inwentaryzacja Produkcji (tabela)"
Write-Host "  [3] Magazyn AGRO (główny)"
Write-Host ""

$wybor = Read-Host "Wybierz (1-3)"

switch ($wybor) {
    "1" { 
        $url = "$baseUrl/agro/magazyn/surowce-w-produkcji"
        Write-Host "Otwieranie: Surowce w Produkcji..." -ForegroundColor Green
    }
    "2" { 
        $url = "$baseUrl/agro/magazyn/inwentaryzacja-produkcji"
        Write-Host "Otwieranie: Inwentaryzacja Produkcji..." -ForegroundColor Green
    }
    "3" { 
        $url = "$baseUrl/agro/magazyn"
        Write-Host "Otwieranie: Magazyn AGRO..." -ForegroundColor Green
    }
    default {
        Write-Host "❌ Nieprawidłowy wybór" -ForegroundColor Red
        exit 1
    }
}

Write-Host "URL: $url" -ForegroundColor Cyan
Start-Process $url
