# PODSUMOWANIE NAPRAWY: Skaner Główny - Wyroby Gotowe

## Problem 1: Wyroby gotowe nie były widoczne w skanerze
**Przyczyna:** Hardkodowana lokalizacja `'MGW01'` w funkcji `_lookup_finished_goods()` w [app/services/scanner_service.py](app/services/scanner_service.py) linia 148.

**Rozwiązanie:** Zmieniono na `COALESCE(lokalizacja, 'MGW01')` aby czytać rzeczywistą wartość z bazy danych.

```python
# PRZED:
f"SELECT id, produkt AS nazwa, waga_netto AS ilosc, 'MGW01' AS lokalizacja, "

# PO NAPRAWIE:
f"SELECT id, produkt AS nazwa, waga_netto AS ilosc, COALESCE(lokalizacja, 'MGW01') AS lokalizacja, "
```

## Problem 2: Nie można było dodać wyrobów gotowych do przesunięcia
**Przyczyna:** Ta sama hardkodowana lokalizacja powodowała, że system:
1. Pokazywał zawsze MGW01 niezależnie od rzeczywistej lokalizacji
2. Backend faktycznie przenosił paletę, ale frontend nadal widział starą lokalizację
3. Walidacja miejsc magazynowych blokowała przesunięcie bo "już jest w tym miejscu"

**Rozwiązanie:** Po naprawieniu lookup'a system teraz:
- ✅ Wyświetla rzeczywistą lokalizację palety
- ✅ Pozwala przenosić wyroby gotowe między lokalizacjami MGW01/MGW02
- ✅ Aktualizuje widok po przeniesieniu
- ✅ Zapisuje historię w tabeli `palety_historia`

## Dodatkowe naprawy w tej sesji:

### Kod skanera SUR bez myślnika
**Problem:** Kody typu `SUR0000017791467317720` nie były rozpoznawane.  
**Rozwiązanie:** Rozszerzono regex w [app/services/scanner_service.py](app/services/scanner_service.py):
- `SUR-?\d+` - akceptuje zarówno `SUR-123` jak i `SUR123`
- `[A-Z]{3}\d{18,20}` - obsługuje SSCC z 18-20 cyframi
- Dodano logikę rozróżniania ID vs nr_palety (>10 cyfr = nr_palety)

### System automatycznego drukowania PDF
**Problem:** Wydruki nie docierały do drukarki.  
**Rozwiązanie:**
1. Dodano brakujące biblioteki: `pywin32`, `PyMuPDF`, `Pillow`
2. Zaktualizowano nazwę drukarki w bazie: `"Brother MFC-L2710DW BIURO Handel"` → `"BIURO Handel"`
3. Utworzono [printer_server/requirements.txt](printer_server/requirements.txt) z wymaganymi zależnościami

## Weryfikacja:
```bash
python test_scanner_flow.py
```

## Wykorzystane pliki:
- [app/services/scanner_service.py](app/services/scanner_service.py) - naprawiono hardkodowaną lokalizację
- [app/services/magazyny_nowe_service.py](app/services/magazyny_nowe_service.py) - obsługa przesunięć wyrobów gotowych
- [static/js/scanner/scanner.js](static/js/scanner/scanner.js) - obsługa PAL- prefix już działała
- [templates/scanner/index.html](templates/scanner/index.html) - typ badge już był zaimplementowany

## Status: ✅ NAPRAWIONO
