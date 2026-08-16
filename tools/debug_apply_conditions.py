#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Debug: sprawdza dokładnie warunki dla wpisów inwentaryzacji.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import db

def debug_conditions():
    sesja_id = 9
    
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM magazyn_inwentaryzacja_produkcji_wpisy WHERE sesja_id = %s", (sesja_id,))
    wpisy = cursor.fetchall()
    
    print("=" * 80)
    print(f"DEBUG WARUNKÓW DLA SESJI #{sesja_id}")
    print("=" * 80)
    
    for wpis in wpisy:
        waga_sys = float(wpis['waga_systemowa'] or 0)
        waga_fakt = float(wpis['waga_faktyczna'] or 0)
        
        zbiornik = wpis['zbiornik']
        nazwa = wpis['surowiec_nazwa']
        
        print(f"\n--- {zbiornik} ---")
        print(f"  surowiec_nazwa: '{nazwa}' (type: {type(nazwa)})")
        print(f"  waga_systemowa: {waga_sys}")
        print(f"  waga_faktyczna: {waga_fakt}")
        print(f"  ruch_id: {wpis['ruch_id']}")
        print(f"  old_ruch_id: {wpis.get('old_ruch_id')}")
        print(f"  paleta_id: {wpis.get('paleta_id')}")
        
        # Sprawdź warunki
        print(f"\n  WARUNKI:")
        print(f"    wpis['ruch_id'] = {wpis['ruch_id']} → {'TRUE (istniejący)' if wpis['ruch_id'] else 'FALSE (nowy)'}")
        
        if not wpis['ruch_id']:
            print(f"    waga_fakt > 0 = {waga_fakt} > 0 → {waga_fakt > 0}")
            print(f"    wpis['surowiec_nazwa'] = '{nazwa}' → {bool(nazwa)}")
            print(f"    wpis['surowiec_nazwa'] != 'PUSTY ZBIORNIK' = '{nazwa}' != 'PUSTY ZBIORNIK' → {nazwa != 'PUSTY ZBIORNIK'}")
            
            condition = waga_fakt > 0 and nazwa and nazwa != 'PUSTY ZBIORNIK'
            print(f"    RAZEM: {condition}")
            
            if condition:
                print(f"    → POWINIEN STWORZYĆ WPIS PRODUKCJA!")
            else:
                print(f"    → NIE stworzy wpisu (warunek FALSE)")
    
    cursor.close()
    conn.close()
    print("\n" + "=" * 80)

if __name__ == '__main__':
    debug_conditions()
