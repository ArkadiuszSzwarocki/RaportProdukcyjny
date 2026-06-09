#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt do naprawy błędnych lokalizacji magazynowych (BB/MZ/KO → R*).
Znajduje palety z kodami zbiorników produkcyjnych jako lokalizacjami
i pozwala je poprawić na właściwe kody regałów.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection
from app.utils.location_validator import is_production_tank_code, validate_warehouse_location
from datetime import datetime
import argparse

def find_wrong_locations():
    """Znajduje wszystkie palety z błędnymi lokalizacjami."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Różne tabele mają różne schematy
    table_configs = [
        {
            'table': 'magazyn_surowce',
            'typ': 'Surowiec',
            'nazwa_col': 'nazwa',
            'waga_col': 'stan_magazynowy'
        },
        {
            'table': 'magazyn_opakowania',
            'typ': 'Opakowanie',
            'nazwa_col': 'nazwa',
            'waga_col': 'stan_magazynowy'
        },
        {
            'table': 'magazyn_palety',
            'typ': 'Wyrób Gotowy',
            'nazwa_col': 'produkt',
            'waga_col': 'waga_netto'
        },
        {
            'table': 'magazyn_dodatki',
            'typ': 'Dodatek',
            'nazwa_col': 'nazwa',
            'waga_col': 'stan_magazynowy'
        },
    ]
    
    wrong_pallets = []
    
    for config in table_configs:
        table = config['table']
        typ = config['typ']
        nazwa_col = config['nazwa_col']
        waga_col = config['waga_col']
        
        try:
            cursor.execute(f"""
                SELECT id, {nazwa_col} as nazwa, lokalizacja, 
                       {waga_col} as waga
                FROM {table}
                WHERE lokalizacja IS NOT NULL 
                  AND lokalizacja != ''
                ORDER BY id
            """)
            
            for row in cursor.fetchall():
                loc = row['lokalizacja']
                if is_production_tank_code(loc):
                    wrong_pallets.append({
                        'table': table,
                        'typ': typ,
                        'id': row['id'],
                        'nazwa': row['nazwa'],
                        'lokalizacja': loc,
                        'waga': float(row['waga']) if row['waga'] else 0.0,
                        'nazwa_col': nazwa_col,
                        'waga_col': waga_col
                    })
        except Exception as e:
            print(f"⚠️  Błąd sprawdzania tabeli {table}: {e}")
    
    conn.close()
    return wrong_pallets

def get_current_location(table, pallet_id):
    """Pobiera aktualną lokalizację palety (na wszelki wypadek sprawdzamy)."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT lokalizacja FROM {table} WHERE id = %s", (pallet_id,))
    row = cursor.fetchone()
    conn.close()
    return row['lokalizacja'] if row else None

def fix_location(table, pallet_id, old_location, new_location, nazwa_col, waga_col, worker_login='SYSTEM', dry_run=True):
    """Poprawia lokalizację palety."""
    
    # Walidacja nowej lokalizacji
    is_valid, error_msg = validate_warehouse_location(new_location, allow_empty=False)
    if not is_valid:
        return False, f"Nowa lokalizacja jest nieprawidłowa: {error_msg}"
    
    # Sprawdź czy to nadal jest ten sam błąd
    current_loc = get_current_location(table, pallet_id)
    if current_loc != old_location:
        return False, f"Lokalizacja się zmieniła! Obecnie: {current_loc}, oczekiwano: {old_location}"
    
    if dry_run:
        return True, f"[DRY-RUN] Zmieniono by: {old_location} → {new_location}"
    
    # Wykonaj update
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Update lokalizacji
        cursor.execute(f"""
            UPDATE {table} 
            SET lokalizacja = %s 
            WHERE id = %s
        """, (new_location, pallet_id))
        
        # Log do historii
        cursor.execute(f"""
            INSERT INTO palety_historia 
            (nr_palety, produkt_nazwa, waga, akcja, szczegoly, autor_login, autor_data, linia)
            SELECT 
                COALESCE(nr_palety, CONCAT('ID:', id)),
                {nazwa_col},
                {waga_col},
                'KOREKTA_LOKALIZACJI',
                CONCAT('[NAPRAWA] Zmieniono lokalizację: ', %s, ' → ', %s, ' (błędnie przypisany kod zbiornika produkcyjnego)'),
                %s,
                NOW(),
                'PSD'
            FROM {table}
            WHERE id = %s
        """, (old_location, new_location, worker_login, pallet_id))
        
        conn.commit()
        return True, f"✅ Poprawiono: {old_location} → {new_location}"
        
    except Exception as e:
        conn.rollback()
        return False, f"❌ Błąd: {str(e)}"
    finally:
        conn.close()

def interactive_fix():
    """Interaktywny tryb naprawy."""
    print("\n" + "="*80)
    print("NAPRAWA BŁĘDNYCH LOKALIZACJI MAGAZYNOWYCH")
    print("="*80)
    
    wrong = find_wrong_locations()
    
    if not wrong:
        print("\n✅ Nie znaleziono palet z błędnymi lokalizacjami!")
        return
    
    print(f"\n🔍 Znaleziono {len(wrong)} palet z błędnymi lokalizacjami:\n")
    
    # Grupuj po lokalizacji
    by_location = {}
    for p in wrong:
        loc = p['lokalizacja']
        if loc not in by_location:
            by_location[loc] = []
        by_location[loc].append(p)
    
    # Wyświetl podsumowanie
    for loc in sorted(by_location.keys()):
        pallets = by_location[loc]
        print(f"\n📍 {loc} (błędna lokalizacja - to zbiornik produkcyjny!):")
        for p in pallets:
            print(f"   • ID {p['id']:4} | {p['typ']:15} | {p['nazwa']:30} | {p['waga']:8.1f} kg")
    
    print("\n" + "-"*80)
    print("OPCJE NAPRAWY:")
    print("1. Automatyczna naprawa - usuń lokalizację (ustaw NULL)")
    print("2. Interaktywna naprawa - podaj nowe lokalizacje dla każdej palety")
    print("3. Anuluj")
    
    choice = input("\nWybierz opcję (1/2/3): ").strip()
    
    if choice == '1':
        # Automatyczna naprawa - NULL
        print("\n⚠️  UWAGA: Wszystkie błędne lokalizacje zostaną usunięte (ustawione na NULL)")
        confirm = input("Kontynuować? (tak/nie): ").strip().lower()
        
        if confirm != 'tak':
            print("❌ Anulowano.")
            return
        
        dry_run = True
        test = input("\nCzy wykonać najpierw test (dry-run)? (tak/nie): ").strip().lower()
        if test != 'tak':
            confirm2 = input("⚠️  WYKONASZ WŁAŚCIWĄ ZMIANĘ W BAZIE! Kontynuować? (tak/nie): ").strip().lower()
            if confirm2 == 'tak':
                dry_run = False
            else:
                print("❌ Anulowano.")
                return
        
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Naprawa w toku...\n")
        
        success_count = 0
        error_count = 0
        
        for p in wrong:
            success, msg = fix_location(
                p['table'], 
                p['id'], 
                p['lokalizacja'], 
                None,  # NULL
                p['nazwa_col'],
                p['waga_col'],
                'SYSTEM_AUTO_FIX',
                dry_run=dry_run
            )
            
            if success:
                print(f"✅ {p['typ']} ID={p['id']} ({p['nazwa'][:30]}): {msg}")
                success_count += 1
            else:
                print(f"❌ {p['typ']} ID={p['id']}: {msg}")
                error_count += 1
        
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Podsumowanie:")
        print(f"   ✅ Poprawiono: {success_count}")
        print(f"   ❌ Błędy: {error_count}")
        
        if dry_run and success_count > 0:
            print("\n💡 Uruchom ponownie i wybierz 'nie' dla dry-run aby wykonać właściwą zmianę.")
    
    elif choice == '2':
        # Interaktywna naprawa
        print("\n📝 Tryb interaktywny - podaj nowe lokalizacje\n")
        
        dry_run = True
        test = input("Czy wykonać najpierw test (dry-run)? (tak/nie): ").strip().lower()
        if test != 'tak':
            confirm2 = input("⚠️  WYKONASZ WŁAŚCIWĄ ZMIANĘ W BAZIE! Kontynuować? (tak/nie): ").strip().lower()
            if confirm2 == 'tak':
                dry_run = False
            else:
                print("❌ Anulowano.")
                return
        
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Podaj nowe lokalizacje:\n")
        
        fixes = []
        for p in wrong:
            print(f"\n{p['typ']} ID={p['id']} | {p['nazwa'][:40]} | {p['waga']:.1f} kg")
            print(f"   Aktualna (błędna) lokalizacja: {p['lokalizacja']}")
            
            new_loc = input("   Nowa lokalizacja (lub ENTER aby pominąć, NULL aby wyczyścić): ").strip().upper()
            
            if not new_loc:
                print("   ⏭️  Pominięto")
                continue
            
            if new_loc == 'NULL':
                new_loc = None
            
            # Walidacja
            if new_loc:
                is_valid, error_msg = validate_warehouse_location(new_loc, allow_empty=False)
                if not is_valid:
                    print(f"   ❌ {error_msg}")
                    retry = input("   Spróbuj ponownie? (tak/nie): ").strip().lower()
                    if retry == 'tak':
                        new_loc = input("   Nowa lokalizacja: ").strip().upper()
                        is_valid, error_msg = validate_warehouse_location(new_loc, allow_empty=False)
                        if not is_valid:
                            print(f"   ❌ {error_msg} - pomijam tę paletę")
                            continue
                    else:
                        continue
            
            fixes.append({
                'pallet': p,
                'new_location': new_loc
            })
        
        if not fixes:
            print("\n❌ Brak zmian do wykonania.")
            return
        
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Wykonuję zmiany...\n")
        
        success_count = 0
        error_count = 0
        
        for fix in fixes:
            p = fix['pallet']
            new_loc = fix['new_location']
            
            success, msg = fix_location(
                p['table'],
                p['id'],
                p['lokalizacja'],
                new_loc,
                p['nazwa_col'],
                p['waga_col'],
                'SYSTEM_MANUAL_FIX',
                dry_run=dry_run
            )
            
            if success:
                print(f"✅ {p['typ']} ID={p['id']}: {msg}")
                success_count += 1
            else:
                print(f"❌ {p['typ']} ID={p['id']}: {msg}")
                error_count += 1
        
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Podsumowanie:")
        print(f"   ✅ Poprawiono: {success_count}")
        print(f"   ❌ Błędy: {error_count}")
        
        if dry_run and success_count > 0:
            print("\n💡 Uruchom ponownie i wybierz 'nie' dla dry-run aby wykonać właściwą zmianę.")
    
    else:
        print("❌ Anulowano.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Naprawa błędnych lokalizacji magazynowych')
    parser.add_argument('--list', action='store_true', help='Tylko wyświetl listę błędnych lokalizacji')
    
    args = parser.parse_args()
    
    if args.list:
        wrong = find_wrong_locations()
        if not wrong:
            print("✅ Nie znaleziono palet z błędnymi lokalizacjami!")
        else:
            print(f"\n🔍 Znaleziono {len(wrong)} palet z błędnymi lokalizacjami:\n")
            for p in wrong:
                print(f"{p['typ']:15} | ID {p['id']:4} | {p['lokalizacja']:10} | {p['nazwa']:30} | {p['waga']:8.1f} kg")
    else:
        interactive_fix()
