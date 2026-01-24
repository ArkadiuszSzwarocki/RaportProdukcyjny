#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test skryptu połączenia z bazą danych
Uruchom ten skrypt aby sprawdzić czy połączenie z MySQL działa poprawnie
"""

import mysql.connector
from mysql.connector import Error
import pytest

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
    
    conn = None
    cursor = None
    try:
        print("Próba połączenia...")
        # Ustaw krótki timeout połączenia, aby test nie czekał długo gdy serwer jest niedostępny
        conn = mysql.connector.connect(connection_timeout=5, **DB_CONFIG)

        assert conn.is_connected(), "Nie udało się nawiązać połączenia z bazą danych"
        print("✅ SUKCES! Połączenie z bazą danych działa!")

        # Pobierz informacje o serwerze
        db_info = conn.server_info
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

        print()
        print("=" * 60)
        print("Test zakończony pomyślnie!")
        print("Możesz uruchomić aplikację: python app.py")
        print("=" * 60)
        assert True

    except Error as e:
        # Jeśli serwer MySQL jest niedostępny (np. błąd 2003) => pomiń test zamiast przerywać całą suitę
        err_no = getattr(e, 'errno', None)
        msg = str(e)
        if err_no == 2003 or 'Can\'t connect' in msg or 'Nie można połączyć' in msg or 'Connection refused' in msg:
            pytest.skip(f"Pomijam test – nie można połączyć się z serwerem MySQL: {msg}")
        pytest.fail(f"Błąd połączenia z bazą danych: {e}")
    except Exception as e:
        pytest.fail(f"Nieoczekiwany błąd: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

if __name__ == "__main__":
    test_connection()
    input("\nNaciśnij Enter aby zakończyć...")
