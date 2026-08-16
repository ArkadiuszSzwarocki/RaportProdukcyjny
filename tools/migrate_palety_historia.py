#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt migracyjny: dodaje historię dla starych palet, które nie mają żadnych wpisów.

Problem: Wiele palet powstało zanim zaimplementowano logowanie do palety_historia,
co powoduje że nie mają one żadnej historii ruchów.

Rozwiązanie: Skrypt dodaje wpisy historyczne dla palet które:
- Istnieją w magazynie ale nie mają historii
- Używa dat z rekordów jako punktu odniesienia

Użycie:
    python tools/migrate_palety_historia.py [--dry-run]
"""

import sys
from datetime import datetime
from app.db import get_db_connection


def migrate_history(dry_run=False):
    """Dodaje historię dla palet bez wpisów."""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    action_prefix = "[DRY-RUN] " if dry_run else ""
    
    try:
        # ========================================
        # 1. WYROBY GOTOWE (magazyn_palety)
        # ========================================
        print("=" * 80)
        print(f"{action_prefix}1. MIGRACJA HISTORII - WYROBY GOTOWE")
        print("=" * 80)
        
        # Znajdź palety bez historii
        cur.execute("""
            SELECT 
                mp.id, 
                mp.nr_palety, 
                mp.produkt, 
                mp.waga_netto,
                mp.lokalizacja,
                mp.data_potwierdzenia,
                mp.user_login,
                COALESCE(mp.linia, 'PSD') as linia,
                pp.data_produkcji
            FROM magazyn_palety mp
            LEFT JOIN palety_historia ph ON mp.id = ph.paleta_id AND ph.typ_palety IN ('wyrob_gotowy', 'wyrób gotowy')
            LEFT JOIN plan_produkcji pp ON mp.plan_id = pp.id
            WHERE ph.id IS NULL
            ORDER BY mp.data_potwierdzenia DESC
        """)
        wyroby_gotowe = cur.fetchall()
        
        print(f"Znaleziono {len(wyroby_gotowe)} wyrobów gotowych bez historii")
        
        wg_migrated = 0
        for row in wyroby_gotowe:
            paleta_id = row['id']
            nr_palety = row['nr_palety'] or f"ID_{paleta_id}"
            produkt = row['produkt'] or 'Produkt nieznany'
            waga = row['waga_netto'] or 0
            lokalizacja = row['lokalizacja']
            data_potwierdzenia = row['data_potwierdzenia']
            user_login = row['user_login'] or 'system'
            linia = row['linia']
            data_produkcji = row['data_produkcji']
            
            # Ustal datę dla wpisu historycznego
            data_ruchu = data_potwierdzenia or data_produkcji or datetime.now()
            
            if not dry_run:
                # Wpis 1: UTWORZENIE (jeśli mamy datę produkcji)
                if data_produkcji and data_produkcji != data_potwierdzenia:
                    try:
                        cur.execute("""
                            INSERT INTO palety_historia 
                            (paleta_id, linia, typ_palety, akcja, komentarz, user_login, data_ruchu) 
                            VALUES (%s, %s, 'wyrob_gotowy', 'UTWORZENIE', %s, %s, %s)
                        """, (paleta_id, linia, f"[MIGRACJA] Utworzono paletę: {produkt}, waga: {waga} kg", user_login, data_produkcji))
                    except Exception as e:
                        print(f"  ⚠️  Błąd przy UTWORZENIE dla {nr_palety}: {e}")
                
                # Wpis 2: PRZYJECIE do magazynu
                try:
                    cur.execute("""
                        INSERT INTO palety_historia 
                        (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login, data_ruchu) 
                        VALUES (%s, %s, 'wyrob_gotowy', 'PRZYJECIE', %s, %s, %s, %s)
                    """, (paleta_id, linia, lokalizacja, f"[MIGRACJA] Przyjęcie do magazynu: {produkt}, {waga} kg", user_login, data_ruchu))
                    wg_migrated += 1
                except Exception as e:
                    print(f"  ⚠️  Błąd przy PRZYJECIE dla {nr_palety}: {e}")
            else:
                wg_migrated += 1
            
            if wg_migrated % 50 == 0 and wg_migrated > 0:
                print(f"  {action_prefix}Przetworzono: {wg_migrated}/{len(wyroby_gotowe)}")
        
        print(f"✅ {action_prefix}Wyroby gotowe: {wg_migrated} palet z dodaną historią")
        
        # ========================================
        # 2. SUROWCE (magazyn_surowce)
        # ========================================
        print("\n" + "=" * 80)
        print(f"{action_prefix}2. MIGRACJA HISTORII - SUROWCE")
        print("=" * 80)
        
        cur.execute("""
            SELECT 
                ms.id,
                ms.nr_palety,
                ms.nazwa,
                ms.stan_magazynowy,
                ms.lokalizacja,
                ms.created_at,
                COALESCE(ms.linia, 'PSD') as linia
            FROM magazyn_surowce ms
            LEFT JOIN palety_historia ph ON ms.id = ph.paleta_id AND ph.typ_palety = 'surowiec'
            WHERE ph.id IS NULL
            ORDER BY ms.created_at DESC
        """)
        surowce = cur.fetchall()
        
        print(f"Znaleziono {len(surowce)} surowców bez historii")
        
        sur_migrated = 0
        for row in surowce:
            paleta_id = row['id']
            nr_palety = row['nr_palety'] or f"ID_{paleta_id}"
            nazwa = row['nazwa'] or 'Surowiec nieznany'
            stan = row['stan_magazynowy'] or 0
            lokalizacja = row['lokalizacja']
            created_at = row['created_at'] or datetime.now()
            linia = row['linia']
            
            if not dry_run:
                try:
                    cur.execute("""
                        INSERT INTO palety_historia 
                        (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login, data_ruchu) 
                        VALUES (%s, %s, 'surowiec', 'PRZYJECIE', %s, %s, 'system', %s)
                    """, (paleta_id, linia, lokalizacja, f"[MIGRACJA] Przyjęcie surowca: {nazwa}, stan: {stan} kg", created_at))
                    sur_migrated += 1
                except Exception as e:
                    print(f"  ⚠️  Błąd dla surowca {nr_palety}: {e}")
            else:
                sur_migrated += 1
            
            if sur_migrated % 50 == 0 and sur_migrated > 0:
                print(f"  {action_prefix}Przetworzono: {sur_migrated}/{len(surowce)}")
        
        print(f"✅ {action_prefix}Surowce: {sur_migrated} palet z dodaną historią")
        
        # ========================================
        # 3. OPAKOWANIA (magazyn_opakowania)
        # ========================================
        print("\n" + "=" * 80)
        print(f"{action_prefix}3. MIGRACJA HISTORII - OPAKOWANIA")
        print("=" * 80)
        
        cur.execute("""
            SELECT 
                mo.id,
                mo.nr_palety,
                mo.nazwa,
                mo.stan_magazynowy,
                mo.lokalizacja,
                mo.created_at,
                COALESCE(mo.linia, 'PSD') as linia
            FROM magazyn_opakowania mo
            LEFT JOIN palety_historia ph ON mo.id = ph.paleta_id AND ph.typ_palety = 'opakowanie'
            WHERE ph.id IS NULL
            ORDER BY mo.created_at DESC
        """)
        opakowania = cur.fetchall()
        
        print(f"Znaleziono {len(opakowania)} opakowań bez historii")
        
        opak_migrated = 0
        for row in opakowania:
            paleta_id = row['id']
            nr_palety = row['nr_palety'] or f"ID_{paleta_id}"
            nazwa = row['nazwa'] or 'Opakowanie nieznane'
            stan = row['stan_magazynowy'] or 0
            lokalizacja = row['lokalizacja']
            created_at = row['created_at'] or datetime.now()
            linia = row['linia']
            
            if not dry_run:
                try:
                    cur.execute("""
                        INSERT INTO palety_historia 
                        (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login, data_ruchu) 
                        VALUES (%s, %s, 'opakowanie', 'PRZYJECIE', %s, %s, 'system', %s)
                    """, (paleta_id, linia, lokalizacja, f"[MIGRACJA] Przyjęcie opakowania: {nazwa}, stan: {stan} szt", created_at))
                    opak_migrated += 1
                except Exception as e:
                    print(f"  ⚠️  Błąd dla opakowania {nr_palety}: {e}")
            else:
                opak_migrated += 1
            
            if opak_migrated % 50 == 0 and opak_migrated > 0:
                print(f"  {action_prefix}Przetworzono: {opak_migrated}/{len(opakowania)}")
        
        print(f"✅ {action_prefix}Opakowania: {opak_migrated} palet z dodaną historią")
        
        # ========================================
        # PODSUMOWANIE
        # ========================================
        print("\n" + "=" * 80)
        print(f"{action_prefix}PODSUMOWANIE MIGRACJI")
        print("=" * 80)
        
        total_migrated = wg_migrated + sur_migrated + opak_migrated
        print(f"Wyroby gotowe:  {wg_migrated:4d} palet")
        print(f"Surowce:        {sur_migrated:4d} palet")
        print(f"Opakowania:     {opak_migrated:4d} palet")
        print(f"{'—' * 30}")
        print(f"RAZEM:          {total_migrated:4d} palet z dodaną historią")
        
        if not dry_run:
            conn.commit()
            print("\n✅ Migracja zakończona pomyślnie!")
            print("💾 Zmiany zostały zapisane do bazy danych.")
        else:
            print("\n⚠️  Tryb DRY-RUN - żadne zmiany nie zostały zapisane.")
            print("    Uruchom bez --dry-run aby zapisać zmiany.")
        
    except Exception as e:
        print(f"\n❌ Błąd podczas migracji: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()


def main():
    """Główna funkcja."""
    dry_run = '--dry-run' in sys.argv
    
    if dry_run:
        print("🔍 Uruchomiono w trybie DRY-RUN (symulacja bez zmian w bazie)")
        print()
    
    print("MIGRACJA HISTORII PALET")
    print("Skrypt doda wpisy historyczne dla wszystkich palet które nie mają historii.")
    print()
    
    if not dry_run:
        confirm = input("Czy chcesz kontynuować? (tak/nie): ").lower().strip()
        if confirm not in ['tak', 't', 'yes', 'y']:
            print("Anulowano.")
            return
        print()
    
    migrate_history(dry_run=dry_run)


if __name__ == '__main__':
    main()
