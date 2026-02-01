from db import get_db_connection
from datetime import date

data_dzisiaj = str(date.today())

conn = get_db_connection()
cursor = conn.cursor()

print("\n" + "="*70)
print("ANALIZA typ_produkcji")
print("="*70 + "\n")

# Sprawdź co się ma w bazie
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, typ_produkcji, tonaz_rzeczywisty
    FROM plan_produkcji 
    WHERE data_planu=%s AND produkt='test'
    ORDER BY sekcja, id
""", (data_dzisiaj,))

print("WSZYSTKIE PLANY DLA PRODUKTU 'test':\n")
for row in cursor.fetchall():
    plan_id, sekcja, prod, tonaz, status, typ, tonaz_rz = row
    print(f"ID={plan_id:3d} | {sekcja:12s} | Status={status:12s} | Typ='{typ}' | Realizacja={tonaz_rz}")

print("\n" + "="*70)
print("SPRAWDZENIE typ_produkcji")
print("="*70)

# Zapytanie jak kod robi
print("\nQuery: WHERE typ_produkcji='worki_zgrzewane_25'")
cursor.execute("""
    SELECT id, typ_produkcji
    FROM plan_produkcji
    WHERE data_planu=%s AND sekcja='Workowanie' AND status='w toku' AND COALESCE(typ_produkcji,'')=%s
    ORDER BY id LIMIT 1
""", (data_dzisiaj, 'worki_zgrzewane_25'))

result = cursor.fetchone()
if result:
    print(f"  ✓ ZNALEZIONO: ID={result[0]}, typ='{result[1]}'")
else:
    print(f"  ✗ NIE ZNALEZIONO!")

# Sprawdzenie co się dzieje z COALESCE
print("\nQuery: WHERE COALESCE(typ_produkcji,'')='worki_zgrzewane_25'")
cursor.execute("""
    SELECT id, typ_produkcji, COALESCE(typ_produkcji,'')
    FROM plan_produkcji
    WHERE data_planu=%s AND sekcja='Workowanie' AND status='w toku'
    ORDER BY id
""", (data_dzisiaj,))

for row in cursor.fetchall():
    plan_id, typ, coalesce_typ = row
    print(f"  ID={plan_id} | typ='{typ}' | COALESCE='{coalesce_typ}'")

conn.close()
