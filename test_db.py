#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test skryptu połączenia z bazą danych
Uruchom ten skrypt aby sprawdzić czy połączenie z MySQL działa poprawnie
"""

import mysql.connector
from mysql.connector import Error

# Konfiguracja - zmień te wartości na swoje
DB_CONFIG = {
    'host': '192.168.0.18',      # Adres serwera MySQL
    'port': 3307,                # Port MySQL
    'database': 'biblioteka',    # Nazwa bazy
    'user': 'biblioteka',        # Użytkownik
    'password': 'Filipinka2025', # Hasło
    'charset': 'utf8mb4'
}

def test_connection():
    """Testuje połączenie z bazą danych"""
    print("=" * 60)
    print("  TEST POŁĄCZENIA Z BAZĄ DANYCH")
    print("=" * 60)
    print()
    
    print("Konfiguracja:")
    print(f"  Host: {DB_CONFIG['host']}")
    print(f"  Port: {DB_CONFIG['port']}")
    print(f"  Baza: {DB_CONFIG['database']}")
    print(f"  User: {DB_CONFIG['user']}")
    print()
    
    try:
        print("Próba połączenia...")
        conn = mysql.connector.connect(**DB_CONFIG)
        
        if conn.is_connected():
            print("✅ SUKCES! Połączenie z bazą danych działa!")
            print()
            
            # Pobierz informacje o serwerze
            db_info = conn.get_server_info()
            print(f"Wersja MySQL: {db_info}")
            
            # Sprawdź czy tabele istnieją
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            if tables:
                print(f"\nZnalezione tabele ({len(tables)}):")
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
                    count = cursor.fetchone()[0]
                    print(f"  - {table[0]}: {count} rekordów")
            else:
                print("\n⚠️  Baza jest pusta - tabele zostaną utworzone przy pierwszym uruchomieniu app.py")
            
            cursor.close()
            conn.close()
            print()
            print("=" * 60)
            print("Test zakończony pomyślnie!")
            print("Możesz uruchomić aplikację: python app.py")
            print("=" * 60)
            return True
            
    except Error as e:
        print(f"❌ BŁĄD POŁĄCZENIA!")
        print(f"Szczegóły: {e}")
        print()
        print("Możliwe przyczyny:")
        print("  1. MySQL Server nie jest uruchomiony")
        print("  2. Nieprawidłowe dane logowania")
        print("  3. Baza danych nie istnieje")
        print("  4. Firewall blokuje połączenie")
        print("  5. Nieprawidłowy host lub port")
        print()
        print("Rozwiązanie:")
        print("  - Sprawdź czy MySQL działa")
        print("  - Zweryfikuj dane w pliku app.py (linie 11-18)")
        print("  - Upewnij się, że baza 'biblioteka' istnieje")
        print()
        return False
    except Exception as e:
        print(f"❌ NIEOCZEKIWANY BŁĄD: {e}")
        return False

if __name__ == "__main__":
    test_connection()
    input("\nNaciśnij Enter aby zakończyć...")
