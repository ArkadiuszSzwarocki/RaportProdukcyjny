#!/usr/bin/env python3
"""Diagnose kolejnosc (sequence) values for plans."""
from app.db import get_db_connection
from datetime import date

dzisiaj = date.today()

conn = get_db_connection()
cursor = conn.cursor()

# Check all plans for today
cursor.execute("""
    SELECT id, produkt, sekcja, status, kolejnosc, data_planu
    FROM plan_produkcji 
    WHERE DATE(data_planu) = %s
    ORDER BY sekcja, kolejnosc
""", (dzisiaj,))

rows = cursor.fetchall()
cursor.close()
conn.close()

print(f"\n=== KOLEJNOSC DLA DNIA {dzisiaj} ===\n")
if rows:
    for row in rows:
        plan_id, produkt, sekcja, status, kolejnosc, data_pl = row
        print(f"ID={plan_id:3d} | {produkt:15s} | {sekcja:12s} | {status:12s} | kolejnosc={kolejnosc}")
        
    print("\n=== DIAGNOSTYKA ===")
    
    # Check for duplicates
    seen = {}
    for row in rows:
        key = (row[2], row[4])  # (sekcja, kolejnosc)
        if key in seen:
            print(f"⚠️ DUPLICATE: {row[2]} ma dwa plany z kolejnosc={row[4]}")
        seen[key] = row[1]
    
    # Check for gaps
    by_sekcja = {}
    for row in rows:
        sekcja = row[2]
        kolejnosc = row[4]
        if sekcja not in by_sekcja:
            by_sekcja[sekcja] = []
        by_sekcja[sekcja].append(kolejnosc)
    
    for sekcja, sequences in by_sekcja.items():
        sequences = sorted(sequences)
        expected = list(range(1, len(sequences) + 1))
        if sequences != expected:
            print(f"⚠️ GAP w {sekcja}: mamy {sequences}, spodziewaliśmy się {expected}")
        else:
            print(f"✓ OK {sekcja}: kolejnosc jest ciągłe i poprawne")
            
else:
    print("Brak planów dla dnia")
