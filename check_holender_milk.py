#!/usr/bin/env python3
import mysql.connector
from dotenv import load_dotenv
import os
from datetime import datetime

# Załaduj zmienne środowiskowe
load_dotenv()

# Konfiguracja bazy
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '3306')),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'raport_produkcyjny'),
}

try:
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    print("=" * 80)
    print("SZUKAM ZLECENIA 'HOLENDER MILK'")
    print("=" * 80)
    
    # Szukaj w plan_produkcji
    query = """
        SELECT 
            id, data_planu, produkt, tonaz, status, 
            real_start, real_stop, tonaz_rzeczywisty, 
            sekcja, typ_produkcji
        FROM plan_produkcji
        WHERE produkt LIKE '%holender milk%' OR produkt LIKE '%Holender%' OR produkt LIKE '%HOLENDER%'
        ORDER BY data_planu DESC
        LIMIT 10
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    # Szukaj historii dla ID 885 (HOLENDER - BUFOR)
    print("=" * 80)
    print("HISTORIA ZMIAN DLA ZLECENIA ID: 885")
    print("=" * 80)
    
    history_query = """
        SELECT action, changes, user_login, created_at
        FROM plan_history
        WHERE plan_id = 885
        ORDER BY created_at DESC
        LIMIT 20
    """
    
    cursor.execute(history_query)
    history_results = cursor.fetchall()
    
    if history_results:
        print(f"\n✓ Znalazłem {len(history_results)} zmian:")
        for i, row in enumerate(history_results, 1):
            print(f"\n{i}. [{row['created_at']}] {row['user_login']}")
            print(f"   Akcja: {row['action']}")
            print(f"   Zmiany: {row['changes'][:200] if row['changes'] else 'brak danych'}")
    else:
        print("\n✗ Brak historii dla tego zlecenia")
    
    print("\n" + "=" * 80)
    print("WYNIKI SZUKANIA NA 'HOLENDER MILK'")
    print("=" * 80)
    
    if results:
        print(f"\n✓ Znalazłem {len(results)} zlecenia:\n")
        for i, row in enumerate(results, 1):
            print(f"{i}. ID: {row['id']}")
            print(f"   Data: {row['data_planu']}")
            print(f"   Produkt: {row['produkt']}")
            print(f"   Status: {row['status']}")
            print(f"   Tonż plan: {row['tonaz']} kg")
            print(f"   Tonż rzeczywisty: {row['tonaz_rzeczywisty']} kg")
            print(f"   Real start: {row['real_start']}")
            print(f"   Real stop: {row['real_stop']}")
            print(f"   Typ produkcji: {row['typ_produkcji']}")
            print(f"   Sekcja: {row['sekcja']}")
            print()
    else:
        print("✗ Nie znalazłem żadnego zlecenia 'holender milk'")
        print("\nSzukam ALL produktów zawierających 'holand' lub 'milk'...")
        
        query2 = """
            SELECT id, data_planu, produkt, status, real_start, real_stop
            FROM plan_produkcji
            WHERE produkt LIKE '%holand%' OR produkt LIKE '%milk%' OR produkt LIKE '%MILK%'
            ORDER BY data_planu DESC
            LIMIT 20
        """
        cursor.execute(query2)
        results2 = cursor.fetchall()
        
        if results2:
            print(f"\nZnalazłem {len(results2)} zbliżonych produktów:\n")
            for row in results2:
                print(f"• [{row['id']}] {row['produkt']} | Status: {row['status']} | Data: {row['data_planu']}")
        else:
            print("✗ Nie znalazłem żadnych zbliżonych produktów")
            
    cursor.close()
    conn.close()
    
except mysql.connector.Error as e:
    print(f"✗ Błąd bazy danych: {e}")
except Exception as e:
    print(f"✗ Błąd: {e}")
