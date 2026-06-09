#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sprawdza aktualny stan zbiorników BB15 i BB18."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection, get_table_name

conn = get_db_connection()
try:
    cursor = conn.cursor(dictionary=True)
    table_ruch = get_table_name('magazyn_ruch', 'Agro')
    table_surowce = get_table_name('magazyn_surowce', 'Agro')
    
    print("\n" + "="*80)
    print("AKTUALNY STAN ZBIORNIKÓW BB15 i BB18")
    print("="*80 + "\n")
    
    for zbiornik in ['BB15', 'BB18']:
        cursor.execute(
            f"SELECT r.zbiornik, COALESCE(s.nazwa, r.surowiec_nazwa) as nazwa, "
            f"SUM(CASE WHEN r.typ_ruchu = 'PRODUKCJA' THEN -r.ilosc ELSE 0 END) as pobrano, "
            f"SUM(CASE WHEN r.typ_ruchu = 'ZWROT' THEN r.ilosc ELSE 0 END) as zwrocono, "
            f"SUM(CASE WHEN r.typ_ruchu = 'INWENTARYZACJA_PROD' THEN r.ilosc ELSE 0 END) as korekta, "
            f"SUM(CASE WHEN r.typ_ruchu = 'PRODUKCJA' THEN -r.ilosc ELSE 0 END) + "
            f"SUM(CASE WHEN r.typ_ruchu = 'ZWROT' THEN r.ilosc ELSE 0 END) + "
            f"SUM(CASE WHEN r.typ_ruchu = 'INWENTARYZACJA_PROD' THEN r.ilosc ELSE 0 END) as stan "
            f"FROM {table_ruch} r "
            f"LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id "
            f"WHERE r.zbiornik LIKE %s AND r.status = 'POTWIERDZONE' "
            f"GROUP BY r.zbiornik, COALESCE(s.nazwa, r.surowiec_nazwa) "
            f"HAVING stan > 0 "
            f"ORDER BY MAX(r.autor_data) DESC",
            (zbiornik,)
        )
        results = cursor.fetchall()
        
        print(f"🏭 ZBIORNIK {zbiornik}:")
        if results:
            for row in results:
                print(f"   ✅ {row['nazwa']:<30} | Stan: {row['stan']:>8.1f} kg")
        else:
            print(f"   ⚪ PUSTY (brak aktywnych surowców)")
        print()
    
finally:
    conn.close()
