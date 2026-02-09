"""
Test: Logika reorderowania (bez HTTP)
"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

data_planu = str(date.today())
plan_ids = [577, 573, 575, 571]  # Nowa kolejność: Testowy4, Testowy2, Testowy3, Testowy1

print("\n" + "="*80)
print("TEST LOGIKI: Bulk reorder (NOWA LOGIKA)")
print("="*80)

# Pokaz obecny stan
print("\n[PRZED] Obecna kolejność:")
cursor.execute("SELECT id, kolejnosc, produkt, status FROM plan_produkcji WHERE data_planu=%s AND LOWER(sekcja) IN ('zasyp','czyszczenie') ORDER BY kolejnosc", (data_planu,))
for row in cursor.fetchall():
    print(f"  ID {row[0]:3} seq {row[1]:2} - {row[2]:25} ({row[3]})")

# Symuluj nową kolejność
print(f"\n[NOWA] Chcemy kolejość plan IDs: {plan_ids}")

# Get sekcja from first plan
cursor.execute("SELECT sekcja FROM plan_produkcji WHERE id=%s", (plan_ids[0],))
res = cursor.fetchone()
sekcja = res[0] if res else 'zasyp'

# Get all non-completed plans for this date and section
cursor.execute(
    "SELECT id FROM plan_produkcji WHERE DATE(data_planu)=%s AND sekcja=%s AND status NOT IN ('w toku', 'zakonczone') ORDER BY kolejnosc",
    (data_planu, sekcja)
)
all_plans = [row[0] for row in cursor.fetchall()]

# Build new order: provided plans first, then remaining plans
new_order = []
for pid in plan_ids:
    try:
        new_order.append(int(pid))
    except (ValueError, TypeError):
        pass

# Add remaining plans that weren't in the drag-and-drop
for pid in all_plans:
    if pid not in new_order:
        new_order.append(pid)

print(f"\n[ORDER] Ostateczna kolejność: {new_order}")

# Assign sequences 1, 2, 3, ... to all plans in new order
for index, plan_id in enumerate(new_order, start=1):
    cursor.execute(
        "UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s AND DATE(data_planu)=%s",
        (index, plan_id, data_planu)
    )
    print(f"  Plan {plan_id} → seq={index}")

conn.commit()

# Pokaż wynik
print("\n[PO] Nowa kolejność:")
cursor.execute("SELECT id, kolejnosc, produkt FROM plan_produkcji WHERE data_planu=%s AND LOWER(sekcja) IN ('zasyp','czyszczenie') ORDER BY kolejnosc", (data_planu,))
result = cursor.fetchall()
all_correct = True
for row in result:
    expected_seq = new_order.index(row[0]) + 1 if row[0] in new_order else '?'
    status = "✓" if row[1] == expected_seq else "✗"
    if row[1] != expected_seq:
        all_correct = False
    print(f"  {status} ID {row[0]:3} seq {row[1]:2} - {row[2]}")

conn.close()

print("\n" + "="*80)
if all_correct:
    print("✓ Logika działa PRAWIDŁOWO!")
else:
    print("✗ BŁĄD: Sekwencje nie zgadzają się!")
print("="*80 + "\n")
