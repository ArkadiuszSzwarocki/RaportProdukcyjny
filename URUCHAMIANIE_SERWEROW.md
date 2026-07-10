# Uruchamianie Aplikacji - Instrukcja

## 🚀 Dwa Serwery

Aplikacja RaportProdukcyjny wymaga uruchomienia **dwóch oddzielnych serwerów**:

### 1️⃣ Serwer Główny (app.py)
**Port:** 8082  
**Funkcja:** Główna aplikacja webowa (Flask)  
**Uruchomienie:**
- **Ręcznie:** `python app.py`
- **Skrót:** Dwuklik na `Start Serwer RaportProdukcyjny.lnk` na Pulpicie

### 2️⃣ Printer Server (printer_server/server.py)
**Port:** 3001  
**Funkcja:** Most do drukarek (ZPL + PDF)  
**Uruchomienie:**
- **Ręcznie:** `python printer_server/server.py`
- **Skrót:** Dwuklik na `Printer Server.lnk` na Pulpicie

---

## 📋 Co obsługuje Printer Server?

Printer Server to **jeden serwer** obsługujący dwa typy drukowania:

### Drukowanie ZPL (Zebra)
- Endpoint: `/drukuj-zpl`
- Drukarki: Zebra (etykiety magazynowe)
- Format: Surowy kod ZPL przez TCP (port 9100)

### Drukowanie PDF (Biuro)
- Endpoint: `/drukuj-pdf`
- Drukarki: Brother, HP (raporty biurowe)
- Format: PDF renderowany przez Windows API

---

## 🔧 Konfiguracja

### Wymagane Biblioteki
```bash
pip install -r printer_server/requirements.txt
pip install pywin32 PyMuPDF Pillow
```

### Konfiguracja Drukarek Biurowych
1. Otwórz panel admin w aplikacji głównej
2. Menu → **Zarządzanie Drukarkami Biurowymi**
3. Wybierz drukarkę z systemu Windows:
   - **BIURO Handel** - 192.168.1.239
   - **Brother MFC-L2710DW LABORATORIUM** - 192.168.1.238

### Konfiguracja Drukarek ZPL (Zebra)
- Zdefiniowane w `printer_server/server.py`
- Domyślna mapa IP:
  ```python
  PRINTER_IP_MAP = {
      'Biuro': '192.168.1.236',
      'Magazyn': '192.168.1.237',
      'Handel': '192.168.1.240',
      'OSIP': '192.168.1.160',
  }
  ```

---

## ✅ Weryfikacja

### Sprawdź czy Printer Server działa:
```bash
curl http://localhost:3001/status
```

Odpowiedź:
```json
{
  "success": true,
  "message": "Serwer druku (Python) działa poprawnie."
}
```

### Sprawdź dostępne drukarki:
```bash
curl http://localhost:3001/printers
```

---

## 🐛 Rozwiązywanie Problemów

### Printer Server nie startuje
**Problem:** `ModuleNotFoundError: No module named 'win32print'`  
**Rozwiązanie:**
```bash
pip install pywin32 PyMuPDF Pillow
```

### Port 3001 zajęty
**Problem:** `OSError: [WinError 10048] Address already in use`  
**Rozwiązanie:** Zamknij inne instancje Printer Server lub zmień port w kodzie

### Drukarka nie drukuje
**Problem:** Wydruki nie docierają do drukarki  
**Rozwiązanie:**
1. Sprawdź nazwę drukarki w panelu admin
2. Porównaj z nazwą w Windows (PowerShell: `Get-Printer`)
3. Zaktualizuj nazwę w bazie jeśli się różni

---

## 📝 Pliki Startowe

### Utworzone Pliki
- `Start_Serwer.bat` - uruchamia główną aplikację
- `Start_PrinterServer.bat` - uruchamia Printer Server
- `create_shortcut.ps1` - tworzy skrót dla głównej aplikacji
- `create_printer_server_shortcut.bat` - tworzy skrót dla Printer Server

### Skróty na Pulpicie
Po uruchomieniu skryptów tworzących, na Pulpicie pojawią się:
- `Start Serwer RaportProdukcyjny.lnk` ⚙️
- `Printer Server.lnk` 🖨️

---

## 🚦 Kolejność Uruchamiania

**Zalecana kolejność:**
1. **Najpierw:** Printer Server (port 3001)
2. **Potem:** Serwer Główny (port 8082)

Aplikacja główna będzie próbowała łączyć się z Printer Server przy automatycznym drukowaniu raportów.

---

## 📊 Status Serwerów

Gdy oba serwery działają:
- Aplikacja główna: http://localhost:8082
- Printer Server: http://localhost:3001
- Status Printer Server: http://localhost:3001/status
- Lista drukarek: http://localhost:3001/printers
