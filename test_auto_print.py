"""
Skrypt testowy dla automatycznego drukowania PDF.
Symuluje proces drukowania raportu po zakończeniu przesunięcia.
"""

import tempfile
import os

def test_printer_server_connection():
    """Test 1: Sprawdź czy printer_server działa"""
    print("=" * 60)
    print("TEST 1: Połączenie z printer_server")
    print("=" * 60)
    
    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        response = requests.get("http://localhost:3001/status", timeout=5)
        if response.status_code == 200:
            print("✅ Printer_server działa poprawnie")
            print(f"   Odpowiedź: {response.json()}")
            return True
        else:
            print(f"❌ Printer_server zwrócił błąd: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Nie można połączyć z printer_server: {e}")
        print("   Uruchom printer_server: python printer_server/server.py")
        return False

def test_required_libraries():
    """Test 2: Sprawdź czy wymagane biblioteki są zainstalowane"""
    print("\n" + "=" * 60)
    print("TEST 2: Wymagane biblioteki")
    print("=" * 60)
    
    libraries = {
        'win32print': 'pywin32',
        'win32api': 'pywin32',
        'win32ui': 'pywin32',
        'fitz': 'PyMuPDF',
        'PIL': 'Pillow',
    }
    
    all_ok = True
    for module, package in libraries.items():
        try:
            __import__(module)
            print(f"✅ {module:15} ({package})")
        except ImportError:
            print(f"❌ {module:15} ({package}) - BRAK!")
            all_ok = False
    
    return all_ok

def test_printer_availability():
    """Test 3: Sprawdź czy drukarka jest dostępna"""
    print("\n" + "=" * 60)
    print("TEST 3: Dostępność drukarki")
    print("=" * 60)
    
    try:
        import win32print
        from app.db import get_db_connection
        
        # Pobierz nazwę drukarki z bazy
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT nazwa_drukarki FROM przypisania_raportow "
            "WHERE typ_raportu = 'raport_przesuniecia' AND aktywne = 1 LIMIT 1"
        )
        assignment = cur.fetchone()
        conn.close()
        
        if not assignment:
            print("❌ Brak aktywnego przypisania drukarki w bazie")
            return False
        
        printer_name = assignment['nazwa_drukarki']
        print(f"Drukarka z bazy: '{printer_name}'")
        
        # Sprawdź czy drukarka istnieje w systemie
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        printer_names = [name for flags, desc, name, comment in printers]
        
        if printer_name in printer_names:
            print(f"✅ Drukarka '{printer_name}' jest dostępna w systemie")
            
            # Sprawdź szczegóły drukarki
            try:
                handle = win32print.OpenPrinter(printer_name)
                info = win32print.GetPrinter(handle, 2)
                win32print.ClosePrinter(handle)
                print(f"   Port: {info.get('pPortName', 'N/A')}")
                print(f"   Status: {info.get('Status', 0)}")
            except Exception as e:
                print(f"⚠️  Nie można odczytać szczegółów: {e}")
            
            return True
        else:
            print(f"❌ Drukarka '{printer_name}' NIE istnieje w systemie")
            print("\nDostępne drukarki:")
            for name in printer_names:
                print(f"  - {name}")
            return False
            
    except ImportError:
        print("❌ Brak biblioteki win32print")
        return False
    except Exception as e:
        print(f"❌ Błąd: {e}")
        return False

def test_pdf_generation():
    """Test 4: Wygeneruj testowy PDF"""
    print("\n" + "=" * 60)
    print("TEST 4: Generowanie testowego PDF")
    print("=" * 60)
    
    try:
        # Stwórz prosty testowy PDF
        from reportlab.pdfgen import canvas
        
        fd, pdf_path = tempfile.mkstemp(suffix=".pdf", prefix="test_raport_")
        os.close(fd)
        
        c = canvas.Canvas(pdf_path)
        c.drawString(100, 750, "TEST AUTOMATYCZNEGO DRUKOWANIA")
        c.drawString(100, 700, "Raport Przesunięcia - Test")
        c.drawString(100, 650, f"Data: {__import__('datetime').datetime.now()}")
        c.save()
        
        print(f"✅ PDF wygenerowany: {pdf_path}")
        print(f"   Rozmiar: {os.path.getsize(pdf_path)} bajtów")
        
        return pdf_path
    except ImportError:
        print("⚠️  Brak biblioteki reportlab - pomijam test generowania PDF")
        print("   (System używa Playwright do generowania PDF)")
        return None
    except Exception as e:
        print(f"❌ Błąd generowania PDF: {e}")
        return None

def test_send_to_printer(pdf_path):
    """Test 5: Wyślij testowy PDF do drukarki"""
    if not pdf_path or not os.path.exists(pdf_path):
        print("\n⚠️  Pomijam test wysyłki - brak testowego PDF")
        return False
    
    print("\n" + "=" * 60)
    print("TEST 5: Wysyłka do printer_server")
    print("=" * 60)
    
    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        from app.db import get_db_connection
        
        # Pobierz nazwę drukarki
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT nazwa_drukarki FROM przypisania_raportow "
            "WHERE typ_raportu = 'raport_przesuniecia' AND aktywne = 1 LIMIT 1"
        )
        assignment = cur.fetchone()
        conn.close()
        
        if not assignment:
            print("❌ Brak przypisania drukarki")
            return False
        
        printer_name = assignment['nazwa_drukarki']
        
        # Wyślij do printer_server
        url = "http://localhost:3001/drukuj-pdf"
        
        with open(pdf_path, 'rb') as f:
            files = {'file': (os.path.basename(pdf_path), f, 'application/pdf')}
            data = {'drukarka': printer_name, 'ip': printer_name}
            
            print(f"Wysyłam do: {url}")
            print(f"Drukarka: {printer_name}")
            
            response = requests.post(url, files=files, data=data, verify=False, timeout=30)
        
        resp_json = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
        
        if response.status_code == 200 and resp_json.get('success'):
            print("✅ PDF wysłany pomyślnie do drukarki!")
            print("   Sprawdź czy drukarka wydrukowała dokument.")
            return True
        else:
            error_msg = resp_json.get('message', response.text)
            print(f"❌ Błąd wysyłki: {error_msg}")
            return False
            
    except Exception as e:
        print(f"❌ Błąd wysyłki: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Usuń testowy PDF
        try:
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
                print(f"\n🧹 Usunięto testowy PDF: {pdf_path}")
        except Exception:
            pass

def main():
    print("\n" + "=" * 60)
    print("TEST AUTOMATYCZNEGO DRUKOWANIA PDF")
    print("=" * 60)
    print()
    
    # Test 1: Połączenie z printer_server
    if not test_printer_server_connection():
        print("\n❌ TEST NIEUDANY: Printer_server nie działa")
        print("\n💡 ROZWIĄZANIE:")
        print("   1. Uruchom printer_server w osobnym terminalu:")
        print("      python printer_server/server.py")
        print("   2. Upewnij się że port 3001 jest wolny")
        return
    
    # Test 2: Biblioteki
    if not test_required_libraries():
        print("\n❌ TEST NIEUDANY: Brakujące biblioteki")
        print("\n💡 ROZWIĄZANIE:")
        print("   pip install -r printer_server/requirements.txt")
        return
    
    # Test 3: Dostępność drukarki
    if not test_printer_availability():
        print("\n❌ TEST NIEUDANY: Drukarka niedostępna")
        print("\n💡 ROZWIĄZANIE:")
        print("   1. Sprawdź czy drukarka jest zainstalowana w Windows")
        print("   2. Zaktualizuj nazwę drukarki w panelu admin:")
        print("      Menu → Zarządzanie Drukarkami Biurowymi")
        return
    
    # Test 4: Generowanie PDF
    pdf_path = test_pdf_generation()
    
    # Test 5: Wysyłka do drukarki
    if pdf_path:
        test_send_to_printer(pdf_path)
    
    print("\n" + "=" * 60)
    print("TESTY ZAKOŃCZONE")
    print("=" * 60)

if __name__ == "__main__":
    main()
