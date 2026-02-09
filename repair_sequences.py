"""
Repair: Renormalize all sequences to be continuous (1, 2, 3, ...)
"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

data_planu = str(date.today())

print("\n" + "="*80)
print("REPAIR: Normalizacja sekwencji")
print("="*80)

# Pobierz wszystkie plany z Zasyp + Czyszczenie (nie w toku, nie zakończone)
cursor.execute("""
    SELECT id, kolejnosc, produkt FROM plan_produkcji 
    WHERE data_planu=%s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
    ORDER BY kolejnosc, id
""", (data_planu,))

plany = cursor.fetchall()
print(f"\n[PRZED] Znaleziono {len(plany)} planów:")
for row in plany:
    print(f"  ID {row[0]:3} seq {row[1]:2} - {row[2]}")

# Reassign sequences 1, 2, 3, ... to all plans
print(f"\n[NOWA] Assignuję sekwencje 1, 2, 3, ...:")
for index, (plan_id, old_seq, produkt) in enumerate(plany, start=1):
    cursor.execute(
        "UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s",
        (index, plan_id)
    )
    print(f"  {produkt:25} → seq {index}")

conn.commit()

# Verify
cursor.execute("""
    SELECT id, kolejnosc, produkt FROM plan_produkcji 
    WHERE data_planu=%s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
    ORDER BY kolejnosc, id
""", (data_planu,))

plany_new = cursor.fetchall()
print(f"\n[PO] Zweryfikowana kolejność:")
for row in plany_new:
    print(f"  ID {row[0]:3} seq {row[1]:2} - {row[2]}")

conn.close()

print("\n" + "="*80)
print("✓ Sekwencje znormalizowane!")
print("="*80 + "\n")
