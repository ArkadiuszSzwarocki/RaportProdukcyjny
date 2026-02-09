#!/usr/bin/env python3
"""Fix sequence numbers (kolejnosc) to be unique per section."""
from app.db import get_db_connection
from datetime import date

dzisiaj = date.today()

conn = get_db_connection()
cursor = conn.cursor()

# Get all plans grouped by sekcja
cursor.execute("""
    SELECT sekcja, GROUP_CONCAT(id ORDER BY kolejnosc ASC)
    FROM plan_produkcji 
    WHERE DATE(data_planu) = %s
    GROUP BY sekcja
""", (dzisiaj,))

sekcje_data = cursor.fetchall()

if sekcje_data:
    print(f"\n=== FIX SEKWENCJI DLA DNIA {dzisiaj} ===\n")
    
    for sekcja, ids_str in sekcje_data:
        if ids_str:
            ids = [int(x) for x in ids_str.split(',')]
            print(f"Sekcja {sekcja}: Renumeruję {len(ids)} planów (IDs: {ids})...")
            
            # Renumber each plan in this sekcja
            for new_seq, plan_id in enumerate(ids, start=1):
                cursor.execute(
                    "UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s",
                    (new_seq, plan_id)
                )
            
            print(f"  ✓ {sekcja}: kolejnosc teraz 1-{len(ids)}")
    
    conn.commit()
    print("\n✓ Baza danych naprawiona!")
    
    # Verify
    cursor.execute("""
        SELECT sekcja, MIN(kolejnosc), MAX(kolejnosc), COUNT(*)
        FROM plan_produkcji 
        WHERE DATE(data_planu) = %s
        GROUP BY sekcja
    """, (dzisiaj,))
    
    print(f"\n=== WERYFIKACJA ===")
    for row in cursor.fetchall():
        sekcja, min_seq, max_seq, count = row
        print(f"  {sekcja}: MIN={min_seq}, MAX={max_seq}, COUNT={count}", "✓" if min_seq == 1 and max_seq == count else "⚠️")
else:
    print("Brak planów dla tego dnia")

cursor.close()
conn.close()
