#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pokazuje szczegóły dzisiejszych pobrań: skąd pobrano i dokąd przypisano."""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection, get_table_name

conn = get_db_connection()
try:
    cur = conn.cursor(dictionary=True)
    table_ruch = get_table_name('magazyn_ruch', 'Agro')
    table_surowce = get_table_name('magazyn_surowce', 'Agro')
    
    dzis = date.today()
    
    print(f"\n{'='*100}")
    print(f"SZCZEGÓŁY DZISIEJSZYCH POBRAŃ NA PRODUKCJĘ - {dzis}")
    print(f"{'='*100}\n")
    print("Format: Z MAGAZYNU (lokalizacja palety) → DO ZBIORNIKA (produkcja)\n")
    
    # Pobierz dzisiejsze pobrania z pełnymi szczegółami
    query = f"""
        SELECT 
            r.id,
            r.surowiec_id,
            COALESCE(s.nazwa, r.surowiec_nazwa) as nazwa_surowca,
            s.lokalizacja as lokalizacja_w_magazynie,
            r.zbiornik as zbiornik_produkcyjny,
            ABS(r.ilosc) as ilosc_kg,
            r.autor_login,
            r.autor_data,
            r.komentarz
        FROM {table_ruch} r
        LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id
        WHERE r.typ_ruchu = 'PRODUKCJA'
          AND DATE(r.autor_data) = %s
        ORDER BY r.autor_data DESC
    """
    
    cur.execute(query, (dzis,))
    pobrania = cur.fetchall()
    
    if not pobrania:
        print("❌ Brak dzisiejszych pobrań na produkcję")
    else:
        print(f"✅ Znaleziono {len(pobrania)} pobrań:\n")
        
        for i, p in enumerate(pobrania, 1):
            print(f"{'─'*100}")
            print(f"POBRANIE #{i} (ID: {p['id']}) - {p['autor_data']}")
            print(f"{'─'*100}")
            print(f"  📦 Surowiec:              {p['nazwa_surowca']}")
            print(f"  ⚖️  Ilość:                 {p['ilosc_kg']:.1f} kg")
            print(f"  📍 Z magazynu (regał):    {p['lokalizacja_w_magazynie'] or '❌ BRAK LOKALIZACJI'}")
            print(f"  🏭 Do zbiornika (prod):   {p['zbiornik_produkcyjny'] or '❌ NIE PRZYPISANO'}")
            print(f"  👤 Operator:              {p['autor_login']}")
            if p['komentarz']:
                print(f"  💬 Komentarz:             {p['komentarz']}")
            print()
            
            # Sprawdź co teraz jest na tym zbiorniku
            if p['zbiornik_produkcyjny']:
                print(f"  🔍 Sprawdzam aktualny stan zbiornika {p['zbiornik_produkcyjny']}...")
                
                # Znajdź wszystkie pobrania na ten zbiornik (nie tylko dzisiejsze)
                cur.execute(f"""
                    SELECT 
                        r.id,
                        COALESCE(s.nazwa, r.surowiec_nazwa) as nazwa,
                        ABS(r.ilosc) as pobrana,
                        COALESCE((SELECT SUM(z.ilosc) FROM {table_ruch} z 
                                  WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT'), 0) as zwrocona,
                        r.autor_data
                    FROM {table_ruch} r
                    LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id
                    WHERE r.typ_ruchu = 'PRODUKCJA'
                      AND r.status = 'POTWIERDZONE'
                      AND UPPER(TRIM(r.zbiornik)) = UPPER(TRIM(%s))
                    ORDER BY r.autor_data DESC
                    LIMIT 5
                """, (p['zbiornik_produkcyjny'],))
                
                historia = cur.fetchall()
                if historia:
                    print(f"     Ostatnie ruchy na tym zbiorniku:")
                    for h in historia:
                        pobrana = float(h['pobrana'] or 0)
                        zwrocona = float(h['zwrocona'] or 0)
                        stan = pobrana - zwrocona
                        dzis_flag = '📅 DZISIAJ' if h['autor_data'].date() == dzis else ''
                        if stan > 0:
                            print(f"       • {h['nazwa']:30s} | Stan: {stan:8.1f} kg | {h['autor_data']} {dzis_flag}")
                        else:
                            print(f"       • {h['nazwa']:30s} | ✅ Zużyte całkowicie | {h['autor_data']} {dzis_flag}")
            print()
    
    print(f"{'='*100}")
    print("PODSUMOWANIE:")
    print(f"{'='*100}\n")
    print("❗ WAŻNE: To są DWA RÓŻNE MIEJSCA:")
    print("   1. MAGAZYN (lokalizacja regału, np. BB01, BB17) - gdzie paleta LEŻY przed pobraniem")
    print("   2. ZBIORNIKI PRODUKCYJNE (np. BB15, BB18) - gdzie surowiec JEST podczas produkcji")
    print()
    print("🔍 Widok 'Surowce w Produkcji' pokazuje ZBIORNIKI PRODUKCYJNE (punkt 2)")
    print("🔍 Magazyn surowców pokazuje REGAŁY (punkt 1)")
    print()
    
finally:
    conn.close()
