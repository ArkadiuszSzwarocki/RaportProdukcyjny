from db import get_db_connection
from datetime import date

data_dzisiaj = str(date.today())

print(f"\n{'='*60}")
print(f"SPRAWDZENIE LOGIKI BUFORA - {data_dzisiaj}")
print(f"{'='*60}\n")

conn = get_db_connection()
cursor = conn.cursor()

# Pobierz stan PRZED dodaniem czegokolwiek
print("STAN BAZY PRZED TESTAMI:")
print("-" * 60)

# Sprawdź wszystkie plany dla produktu 'test' dzisiaj
cursor.execute("""
    SELECT id, produkt, tonaz, sekcja, status, tonaz_rzeczywisty 
    FROM plan_produkcji 
    WHERE produkt='test' AND data_planu=%s AND sekcja IN ('Zasyp', 'Workowanie')
    ORDER BY sekcja, status DESC, id
""", (data_dzisiaj,))

zasyp_plan = None
workowanie_plan = None

for row in cursor.fetchall():
    plan_id, produkt, tonaz, sekcja, status, tonaz_rzeczywisty = row
    print(f"ID={plan_id:3d} | {sekcja:12s} | Status: {status:12s} | Tonaz={tonaz:6.0f} | Realizacja={tonaz_rzeczywisty:6.0f}")
    
    if sekcja == 'Zasyp' and status == 'w toku':
        zasyp_plan = (plan_id, tonaz, tonaz_rzeczywisty)
    elif sekcja == 'Workowanie' and status == 'w toku':
        workowanie_plan = (plan_id, tonaz, tonaz_rzeczywisty)

print("\n" + "="*60)
print("PODSUMOWANIE STANÓW:")
print("="*60)

if zasyp_plan:
    print(f"\n✓ Zasyp (w toku):")
    print(f"  - ID: {zasyp_plan[0]}")
    print(f"  - Tonaz (plan): {zasyp_plan[1]} kg")
    print(f"  - Tonaz rzeczywisty (realizacja): {zasyp_plan[2]} kg")
else:
    print(f"\n✗ Brak otwartego planu Zasyp")

if workowanie_plan:
    print(f"\n✓ Workowanie/Bufor (w toku):")
    print(f"  - ID: {workowanie_plan[0]}")
    print(f"  - Tonaz (plan): {workowanie_plan[1]} kg")
    print(f"  - Tonaz rzeczywisty (BUFOR): {workowanie_plan[2]} kg")
    
    # Oblicz pozostałość w buforze
    pozostalosc = workowanie_plan[1] - workowanie_plan[2]
    print(f"  - Pozostałość w buforze: {pozostalosc} kg")
else:
    print(f"\n✗ Brak bufora w Workowanie")

print("\n" + "="*60)
print("INTERPRETACJA:")
print("="*60)

if zasyp_plan and workowanie_plan:
    print(f"""
✓ LOGIKA BUFORA DZIAŁA:
  - Szarża (Zasyp): {zasyp_plan[2]} kg
  - Bufor (Workowanie): {workowanie_plan[2]} kg
  
  Jeśli dodasz szarżę 500 kg:
    → Bufor zwiększy się do {workowanie_plan[2] + 500} kg
  
  Jeśli dodasz paletę 300 kg:
    → Bufor zmniejszy się do {workowanie_plan[2] - 300} kg
""")
else:
    print("✗ Nie można w pełni sprawdzić logiki bufora")

conn.close()
