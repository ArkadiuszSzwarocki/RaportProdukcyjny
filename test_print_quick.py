"""
Szybki test drukowania - bez reportlab, z prostym HTML→PDF
"""

def test_quick():
    print("\n🔍 SZYBKI TEST DRUKOWANIA\n")
    
    # Test 1: Połączenie z printer_server
    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        print("1️⃣ Sprawdzam printer_server...")
        r = requests.get("http://localhost:3001/status", timeout=3)
        if r.status_code == 200:
            print("   ✅ Printer_server działa")
        else:
            print(f"   ❌ Błąd: {r.status_code}")
            return
    except Exception as e:
        print(f"   ❌ Błąd połączenia: {e}")
        print("\n💡 Uruchom: python printer_server/server.py")
        return
    
    # Test 2: Drukarka w bazie
    try:
        from app.db import get_db_connection
        
        print("\n2️⃣ Sprawdzam konfigurację drukarki...")
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM przypisania_raportow "
            "WHERE typ_raportu = 'raport_przesuniecia' AND aktywne = 1 LIMIT 1"
        )
        assignment = cur.fetchone()
        conn.close()
        
        if not assignment:
            print("   ❌ Brak przypisania drukarki w bazie")
            return
        
        printer_name = assignment['nazwa_drukarki']
        print(f"   ✅ Drukarka: '{printer_name}'")
        
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return
    
    # Test 3: Drukarka w Windows
    try:
        import win32print
        
        print("\n3️⃣ Sprawdzam drukarkę w Windows...")
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        printer_names = [name for flags, desc, name, comment in printers]
        
        if printer_name in printer_names:
            print(f"   ✅ Drukarka '{printer_name}' dostępna")
        else:
            print(f"   ❌ Drukarka '{printer_name}' NIE istnieje")
            print("\n   Dostępne drukarki:")
            for name in printer_names:
                print(f"      - {name}")
            return
            
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return
    
    print("\n" + "=" * 60)
    print("✅ WSZYSTKIE SPRAWDZENIA POMYŚLNE")
    print("=" * 60)
    print("\n💡 System automatycznego drukowania jest gotowy!")
    print("   Po zakończeniu przesunięcia raport powinien drukować się automatycznie.")
    print("\n📝 WAŻNE:")
    print("   - Printer_server musi być uruchomiony: python printer_server/server.py")
    print("   - Drukarka musi być włączona i gotowa")
    print("   - Aplikacja główna musi działać: python app.py")

if __name__ == "__main__":
    test_quick()
