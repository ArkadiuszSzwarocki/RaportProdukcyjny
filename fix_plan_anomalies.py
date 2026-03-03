#!/usr/bin/env python3
"""
Script to fix plan anomalies - plans with tonaz_rzeczywisty but wrong status
"""
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

def fix_anomalies():
    """Skanuj i napraw anomalie"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        print("=" * 80)
        print("SKANOWANIE ANOMALII W PLANACH PRODUKCJI")
        print("=" * 80)
        print("\nZnajdowanie planów z anomaliami:")
        print("  - status = 'zaplanowane'")
        print("  - tonaz_rzeczywisty > 0")
        print("  - real_start IS NULL\n")
        
        # Szukaj anomalii
        query = """
            SELECT id, produkt, status, tonaz, tonaz_rzeczywisty, real_start, real_stop
            FROM plan_produkcji
            WHERE status='zaplanowane' AND COALESCE(tonaz_rzeczywisty, 0) > 0 AND real_start IS NULL
            ORDER BY data_planu DESC
        """
        
        cursor.execute(query)
        anomalies = cursor.fetchall()
        
        if not anomalies:
            print("✓ Nie znaleziono anomalii!")
            conn.close()
            return
        
        print(f"✗ Znalazłem {len(anomalies)} anomalii:\n")
        
        for i, anomaly in enumerate(anomalies, 1):
            print(f"{i}. ID: {anomaly['id']}")
            print(f"   Produkt: {anomaly['produkt']}")
            print(f"   Status: {anomaly['status']}")
            print(f"   Tonż plan: {anomaly['tonaz']} kg")
            print(f"   Tonż rzeczywisty: {anomaly['tonaz_rzeczywisty']} kg")
            print(f"   Real start: {anomaly['real_start']}")
            print()
        
        # Pytanie czy naprawić
        response = input(f"\nNaprawić wszystkie {len(anomalies)} anomalii? (tak/nie): ").strip().lower()
        
        if response not in ['tak', 'yes', 'y']:
            print("Anulowano.")
            conn.close()
            return
        
        print(f"\n▶ Naprawianie {len(anomalies)} anomalii...\n")
        
        fixed_count = 0
        for anomaly in anomalies:
            plan_id = anomaly['id']
            produkt = anomaly['produkt']
            tonaz_rz = anomaly['tonaz_rzeczywisty']
            
            try:
                # Fix: Set status to 'zakonczone' since tonaz_rzeczywisty is already set
                cursor.execute("""
                    UPDATE plan_produkcji 
                    SET status='zakonczone', 
                        real_start=IFNULL(real_start, NOW()),
                        real_stop=IFNULL(real_stop, NOW())
                    WHERE id=%s
                """, (plan_id,))
                
                conn.commit()
                fixed_count += 1
                print(f"✓ [{fixed_count}] Naprawiono plan ID {plan_id}: {produkt} (tonaz={tonaz_rz}kg)")
                
            except Exception as e:
                print(f"✗ Błąd przy naprawie ID {plan_id}: {e}")
                conn.rollback()
        
        print(f"\n{'=' * 80}")
        print(f"✓ GOTOWE: Naprawiono {fixed_count} anomalii")
        print(f"{'=' * 80}")
        
        # Pokaż wynik
        print("\nWeryfikacja - szukam pozostałych anomalii...")
        cursor.execute(query)
        remaining = cursor.fetchall()
        
        if remaining:
            print(f"! Pozostało {len(remaining)} anomalii depois naprawy (mogą to być nowe):")
            for a in remaining:
                print(f"  - ID {a['id']}: {a['produkt']} (tonaz={a['tonaz_rzeczywisty']})")
        else:
            print("✓ Brak pozostałych anomalii - wszystko naprawione!")
        
        conn.close()
        
    except mysql.connector.Error as e:
        print(f"✗ Błąd bazy danych: {e}")
    except Exception as e:
        print(f"✗ Błąd: {e}")

if __name__ == '__main__':
    fix_anomalies()
