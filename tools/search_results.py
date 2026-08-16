from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

print("--- SEARCH IN magazyn_palety (PSD) ---")
cursor.execute("SELECT * FROM magazyn_palety WHERE produkt LIKE '%milk%' OR produkt LIKE '%milkmix%'")
for row in cursor.fetchall():
    print(row)

print("\n--- SEARCH IN magazyn_palety_agro (AGRO) ---")
cursor.execute("SELECT * FROM magazyn_palety_agro WHERE produkt LIKE '%milk%' OR produkt LIKE '%milkmix%'")
for row in cursor.fetchall():
    print(row)
    
print("\n--- SEARCH IN plan_produkcji (PSD) ---")
cursor.execute("SELECT DISTINCT produkt FROM plan_produkcji WHERE produkt LIKE '%milk%' OR produkt LIKE '%milkmix%'")
for row in cursor.fetchall():
    print(row)

print("\n--- SEARCH IN plan_produkcji_agro (AGRO) ---")
cursor.execute("SELECT DISTINCT produkt FROM plan_produkcji_agro WHERE produkt LIKE '%milk%' OR produkt LIKE '%milkmix%'")
for row in cursor.fetchall():
    print(row)

conn.close()
