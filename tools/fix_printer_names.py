"""
Skrypt do aktualizacji nazw drukarek w bazie danych.
Zmienia nazwę z formatu "Brother MFC-L2710DW BIURO Handel" 
na dokładną nazwę z systemu Windows "BIURO Handel".
"""

from app.db import get_db_connection

def main():
    print("=" * 60)
    print("AKTUALIZACJA NAZW DRUKAREK")
    print("=" * 60)
    
    # Mapa starych nazw na nowe (z Windows)
    printer_mapping = {
        "Brother MFC-L2710DW BIURO Handel": "BIURO Handel",
        "Brother MFC-L2710DW LABORATORIUM": "Brother MFC-L2710DW LABORATORIUM",
    }
    
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        
        # Pobierz aktualne przypisania
        cur.execute("SELECT * FROM przypisania_raportow")
        assignments = cur.fetchall()
        
        print("\nAktualne przypisania:")
        for a in assignments:
            print(f"  {a['id']}. {a['nazwa_raportu']}")
            print(f"     Drukarka: {a['nazwa_drukarki']}")
            print(f"     Aktywne: {'TAK' if a['aktywne'] else 'NIE'}")
            print()
        
        # Aktualizuj nazwy
        updated_count = 0
        for old_name, new_name in printer_mapping.items():
            cur.execute(
                "UPDATE przypisania_raportow SET nazwa_drukarki = %s WHERE nazwa_drukarki = %s",
                (new_name, old_name)
            )
            if cur.rowcount > 0:
                print(f"✅ Zaktualizowano {cur.rowcount} rekordów:")
                print(f"   '{old_name}' → '{new_name}'")
                updated_count += cur.rowcount
        
        if updated_count > 0:
            conn.commit()
            print(f"\n✅ SUKCES: Zaktualizowano łącznie {updated_count} przypisań drukarek.")
        else:
            print("\nℹ️  Brak zmian - nazwy drukarek są aktualne.")
        
        # Pokaż zaktualizowane przypisania
        cur.execute("SELECT * FROM przypisania_raportow")
        assignments = cur.fetchall()
        
        print("\n" + "=" * 60)
        print("PRZYPISANIA PO AKTUALIZACJI:")
        print("=" * 60)
        for a in assignments:
            print(f"  {a['id']}. {a['nazwa_raportu']}")
            print(f"     Drukarka: {a['nazwa_drukarki']}")
            print(f"     Aktywne: {'TAK' if a['aktywne'] else 'NIE'}")
            print()
            
    except Exception as e:
        print(f"❌ BŁĄD: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
    
    print("\n" + "=" * 60)
    print("DOSTĘPNE DRUKARKI W WINDOWS:")
    print("=" * 60)
    try:
        import win32print
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        for i, (flags, desc, name, comment) in enumerate(printers, 1):
            print(f"  {i}. {name}")
        print()
        
        default = win32print.GetDefaultPrinter()
        print(f"Domyślna drukarka: {default}")
    except ImportError:
        print("⚠️  Biblioteka win32print nie jest dostępna - nie można wyświetlić drukarek.")
    except Exception as e:
        print(f"⚠️  Błąd odczytu drukarek: {e}")

if __name__ == "__main__":
    main()
