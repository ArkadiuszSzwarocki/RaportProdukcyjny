from app.db import get_db_connection
import datetime

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# 1. Search in magazyn_palety
print("--- SEARCH IN magazyn_palety (PSD) ---")
cursor.execute("SELECT id, produkt, data_planu, data_produkcji FROM magazyn_palety WHERE produkt LIKE '%milkimix%'")
for r in cursor.fetchall():
    print(r)

# 2. Search in magazyn_palety_agro
print("\n--- SEARCH IN magazyn_palety_agro (AGRO) ---")
cursor.execute("SELECT id, produkt, data_planu, data_produkcji FROM magazyn_palety_agro WHERE produkt LIKE '%milkimix%'")
for r in cursor.fetchall():
    print(r)

# 3. Search in plan_produkcji
print("\n--- SEARCH IN plan_produkcji (PSD) ---")
cursor.execute("SELECT id, produkt, data_planu, data_produkcji, status FROM plan_produkcji WHERE produkt LIKE '%milkimix%'")
for r in cursor.fetchall():
    print(r)

# 4. Search in plan_produkcji_agro (AGRO)
print("\n--- SEARCH IN plan_produkcji_agro (AGRO) ---")
cursor.execute("SELECT id, produkt, data_planu, data_produkcji, status FROM plan_produkcji_agro WHERE produkt LIKE '%milkimix%'")
for r in cursor.fetchall():
    print(r)

conn.close()
