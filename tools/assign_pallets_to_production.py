#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Przypisuje 6 palet z błędnymi lokalizacjami do produkcji (zbiorniki)."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection
from datetime import datetime
import argparse

# Palety do przypisania: (surowiec_id, zbiornik, nazwa, ilosc)
# UWAGA: Tylko jedna paleta na zbiornik!
ASSIGNMENTS = [
    (466, 'BB17', 'ACP Kwaśna', 1000.0),
    (492, 'BB18', 'Bm3', 1293.0),  # Zmieniono BB17→BB18
    (511, 'BB19', 'Bm3', 1262.0),  # Zmieniono BB17→BB19
    (535, 'BB14', 'Mąka pszenna', 1030.0),
    (640, 'BB01', 'WPP', 1000.0),
    (641, 'BB02', 'WPP', 1000.0),  # Zmieniono BB01→BB02
]

def assign_to_production(surowiec_id, zbiornik, ilosc, worker_login='SYSTEM_AUTO_ASSIGN', dry_run=True):
    """Przypisuje surowiec do zbiornika produkcyjnego."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Sprawdź aktualny stan palety
        cursor.execute("""
            SELECT id, nazwa, stan_magazynowy, lokalizacja, nr_palety
            FROM magazyn_surowce
            WHERE id = %s
        """, (surowiec_id,))
        surowiec = cursor.fetchone()
        
        if not surowiec:
            return False, f"Surowiec ID={surowiec_id} nie istnieje"
        
        if float(surowiec['stan_magazynowy']) < ilosc:
            return False, f"Za mało surowca (jest {surowiec['stan_magazynowy']} kg, potrzeba {ilosc} kg)"
        
        if dry_run:
            return True, f"[DRY-RUN] Przypisano by {ilosc} kg do {zbiornik}"
        
        # Sprawdź co jest aktualnie w zbiorniku
        cursor.execute("""
            SELECT surowiec_id, ilosc, ilosc_po
            FROM magazyn_ruch
            WHERE zbiornik = %s AND status = 'aktywne' AND typ_ruchu = 'PRODUKCJA'
            ORDER BY autor_data DESC
            LIMIT 1
        """, (zbiornik,))
        current = cursor.fetchone()
        
        if current and current['ilosc_po'] > 0:
            return False, f"Zbiornik {zbiornik} jest zajęty (ID={current['surowiec_id']}, {current['ilosc_po']} kg)"
        
        # Pobierz obecny stan magazynowy przed operacją
        stan_przed = float(surowiec['stan_magazynowy'])
        stan_po = stan_przed - ilosc
        
        # Dodaj wpis do magazyn_ruch (PRODUKCJA)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO magazyn_ruch 
            (surowiec_id, typ_ruchu, zbiornik, ilosc, ilosc_po, status, autor_login, autor_data, komentarz)
            VALUES (%s, 'PRODUKCJA', %s, %s, %s, 'aktywne', %s, NOW(), %s)
        """, (
            surowiec_id,
            zbiornik,
            ilosc,
            ilosc,  # ilosc_po = ile jest w zbiorniku
            worker_login,
            f'[AUTO] Przypisanie palety do zbiornika {zbiornik}'
        ))
        
        # Zaktualizuj stan magazynowy (odejmij z magazynu)
        cursor.execute("""
            UPDATE magazyn_surowce
            SET stan_magazynowy = stan_magazynowy - %s
            WHERE id = %s
        """, (ilosc, surowiec_id))
        
        # Log do historii
        cursor.execute("""
            INSERT INTO palety_historia
            (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login, data_ruchu)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            surowiec_id,
            'PSD',
            'surowiec',
            'PRODUKCJA',
            zbiornik,
            f'[AUTO] Przypisano {ilosc} kg do zbiornika {zbiornik}',
            worker_login
        ))
        
        conn.commit()
        return True, f"✅ Przypisano {ilosc} kg do {zbiornik}"
        
    except Exception as e:
        conn.rollback()
        return False, f"❌ Błąd: {str(e)}"
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description='Przypisanie palet do produkcji')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Tryb testowy (domyślnie: True)')
    parser.add_argument('--execute', action='store_true', help='Wykonaj właściwą operację')
    
    args = parser.parse_args()
    dry_run = not args.execute
    
    print("\n" + "="*100)
    print("PRZYPISYWANIE PALET DO PRODUKCJI")
    print("="*100)
    
    if dry_run:
        print("\n⚠️  Tryb DRY-RUN - żadne zmiany nie zostaną wykonane")
        print("Użyj --execute aby wykonać właściwą operację\n")
    else:
        print("\n🚨 TRYB WYKONANIA - zmiany zostaną zapisane w bazie!\n")
        confirm = input("Kontynuować? (tak/nie): ").strip().lower()
        if confirm != 'tak':
            print("❌ Anulowano.")
            return
    
    print("\nPrzypisania do wykonania:\n")
    
    success_count = 0
    error_count = 0
    
    for surowiec_id, zbiornik, nazwa, ilosc in ASSIGNMENTS:
        print(f"\n{'─'*100}")
        print(f"📦 ID {surowiec_id} | {nazwa:20} | {ilosc:8.1f} kg → {zbiornik}")
        print(f"{'─'*100}")
        
        success, msg = assign_to_production(surowiec_id, zbiornik, ilosc, 'SYSTEM_AUTO_ASSIGN', dry_run)
        
        if success:
            print(f"   {msg}")
            success_count += 1
        else:
            print(f"   {msg}")
            error_count += 1
    
    print(f"\n{'='*100}")
    print(f"PODSUMOWANIE {'(DRY-RUN)' if dry_run else ''}")
    print(f"{'='*100}")
    print(f"   ✅ Sukces: {success_count}")
    print(f"   ❌ Błędy: {error_count}")
    
    if dry_run and success_count > 0:
        print("\n💡 Uruchom ponownie z flagą --execute aby wykonać przypisania")

if __name__ == '__main__':
    main()
