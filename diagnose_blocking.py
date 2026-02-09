"""
Diagnostyka: Jakie statusy mają plany na Zasyp?
"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

dzisiaj = str(date.today())

print("\n" + "="*80)
print(f"DIAGNOSTYKA: Statusy planów na {dzisiaj}")
print("="*80)

# Pobierz wszystkie plany Zasyp
cursor.execute("""
    SELECT id, produkt, status, kolejnosc, sekcja
    FROM plan_produkcji 
    WHERE data_planu=%s AND LOWER(sekcja)='zasyp'
    ORDER BY kolejnosc
""", (dzisiaj,))

plany = cursor.fetchall()

print(f"\nZnaleziono {len(plany)} planów na Zasyp:\n")
print(f"{'ID':5} {'PRODUKT':25} {'STATUS':15} {'SEQ':4} {'EDYTOWALNE?':12}")
print("-"*80)

for row in plany:
    plan_id, produkt, status, seq, sekcja = row
    edytowalne = "✓ TAK" if status not in ['w toku', 'zakonczone'] else "✗ NIE"
    print(f"{plan_id:5} {produkt:25} {status:15} {seq:4} {edytowalne:12}")

print("\n" + "="*80)

# Sprawdź czy któreś plany są "w toku"
w_toku = sum(1 for row in plany if row[2] == 'w toku')
zakonczone = sum(1 for row in plany if row[2] == 'zakonczone')
zaplanowane = sum(1 for row in plany if row[2] == 'zaplanowane')

print(f"\nSTATYSTYKA:")
print(f"  Zaplanowane: {zaplanowane}")
print(f"  W toku: {w_toku}")
print(f"  Zakończone: {zakonczone}")

if w_toku > 0:
    print(f"\n⚠️ UWAGA: {w_toku} plan(ów) jest w toku!")
    print("   Pozostałe plany 'zaplanowane' powinny być EDYTOWALNE")
else:
    print(f"\n✓ Żaden plan nie jest w toku")

conn.close()

print("="*80 + "\n")
