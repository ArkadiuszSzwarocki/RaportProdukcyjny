from db import get_db_connection
from datetime import date

data_dzisiaj = str(date.today())

conn = get_db_connection()
cursor = conn.cursor()

print("\n" + "="*70)
print("WSZYSTKIE PLANY WORKOWANIE dla produktu 'test'")
print("="*70 + "\n")

# Sprawdź co zwraca query dla Workowanie
cursor.execute("""
    SELECT 
        id, 
        produkt, 
        tonaz, 
        status,
        tonaz_rzeczywisty,
        typ_produkcji
    FROM plan_produkcji 
    WHERE data_planu=%s AND sekcja='Workowanie' AND produkt='test'
    ORDER BY id
""", (data_dzisiaj,))

for i, row in enumerate(cursor.fetchall(), 1):
    plan_id, prod, tonaz, status, tonaz_rz, typ = row
    print(f"Wiersz {i}:")
    print(f"  ID={plan_id} | Produkt={prod} | Tonaz={tonaz} | Status={status}")
    print(f"  Tonaz_rzeczywisty (Realizacja)={tonaz_rz}")
    print()

conn.close()
