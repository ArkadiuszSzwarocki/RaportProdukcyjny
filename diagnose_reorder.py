"""
Diagnostyka: Jaki jest obecny stan kolejności planów?
"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

dzisiaj = str(date.today())

print("\n" + "="*80)
print(f"DIAGNOSTYKA: Stan kolejności dla daty {dzisiaj}")
print("="*80)

# Pobierz plany zasyp/czyszczenie
cursor.execute("""
    SELECT id, kolejnosc, produkt, sekcja, status
    FROM plan_produkcji 
    WHERE data_planu=%s AND LOWER(sekcja) IN ('zasyp', 'czyszczenie')
    ORDER BY kolejnosc
""", (dzisiaj,))

plany = cursor.fetchall()

print(f"\nZnaleziono {len(plany)} planów:\n")
print(f"{'ID':5} {'KOLEJKA':8} {'PRODUKT':20} {'SEKCJA':12} {'STATUS':15}")
print("-"*80)

for p in plany:
    plan_id, seq, produkt, sekcja, status = p
    print(f"{plan_id:5} {seq:8} {produkt:20} {sekcja:12} {status:15}")

print("\n" + "="*80)

# Teraz symuluj co się stanie jeśli klikniemy move-up/move-down sekwencyjnie

print("\n❓ PYTANIE: Co chcesz osiągnąć?")
print("   Obecna kolejka: 1(Testowy1) → 2(Testowy2) → 3(Testowy3) → 4(Testowy4)")
print("   Chcesz: 4(Testowy4) → 2(Testowy2) → 3(Testowy3) → 1(Testowy1)?")
print("\n✗ PROBLEM: Current swap-based system nie może to zarobić!")
print("  System tylko swapuje sąsiednie elementy, nie pozwala na direct reorder.")
print("\n✓ ROZWIĄZANIE: Drag-and-drop lub bulk reorder endpoint")

conn.close()
